"""Narrative Composer Agent (v3.3.0) — Opus 4.7 freeform editorial pass.

7개 분석 에이전트가 evidence/claim 을 수집한 뒤, 본 에이전트가 *편집장* 으로
전체 보고서를 자유 형식으로 짠다. 기존 17 BlockType 슬롯에 데이터를 부어넣는
대신 사건 성격에 맞춰 섹션 수/길이/순서/톤을 결정한다.

설계 원칙:
- 단일 LLM 호출 (Opus 4.7). max_tokens 8K. deep 모드만 활성.
- 모든 주장은 ``cited_claim_ids`` 로 claim_id 인용 — Anti-pattern #4 우회 금지.
- 차트는 ``embedded_charts`` 의 chart_id 로 본문에 박는다 (charts.js auto-init).
- BaseAgent 를 *상속하지 않는다* — 시스템 프롬프트는 ``.replace()`` 로만 빌드
  (CLAUDE.md rule #7), JSON 응답을 ComposedReport Pydantic 모델로 검증.
- 실패 시 ``None`` 반환. Orchestrator 가 freeform_essay → six_act_theater 폴백.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from typing import Optional

from src.config import Config
from src.models import (
    ComposedReport,
    ComposedSection,
    ContextAnalysis,
    FullAnalysisResult,
)
from src.telemetry import RunTelemetry

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "당신은 사건 분석가이자 편집장. 1차 사실 자료(웹 검색으로 수집된 사실/타임라인/"
    "핵심 수치/출처 URL)를 받아 *단독으로* 분석하고 보고서를 작성한다.\n\n"
    "v4.0.0 Tier 4: 별도의 행위자/구조/시나리오/판단 분석가가 없음. 본 호출 한 번에\n"
    "다음을 모두 수행: ① 핵심 행위자 식별 ② 구조적 동인 분석 ③ 인과 사슬 추적 ④\n"
    "시나리오 설계 ⑤ 모순/반대 가설 표면화 ⑥ 보고서 본문 작성 ⑦ 감시 신호 추출.\n\n"
    "=== 분석 깊이 (mode 인자에 따라) ===\n"
    "- fast:     핵심만 간결. 3~4 섹션. 시나리오 2~3개. 모순 명시 선택.\n"
    "- standard: 다각도 4~6 섹션. 시나리오 3~5개. 모순 1~2건 명시 권장.\n"
    "- deep:     5~7 섹션. 시나리오 4~5개. 모순/반대 가설 *필수*. 감시 신호 ≥3건.\n\n"
    "=== 분석 단계 (자율 결정, 본문에 녹여서) ===\n"
    "1. 행위자 식별 — 누가 결정권자 / 이득 / 손해 / 숨은 영향력자.\n"
    "2. 구조적 동인 — 왜 이 사건이 *지금* 일어났나. 비대칭 / 피드백 루프 / 전환점.\n"
    "3. 인과 사슬 — 단기·중기·장기 파급. 차단 가능 지점 + 와일드카드.\n"
    "4. 시나리오 — 3~5개. 각각 트리거 / 확률 / 영향 / 신호.\n"
    "5. 모순 표면화 — 관점 충돌 / 데이터 모순. 봉합 금지 (Anti-pattern #5).\n"
    "6. 감시 신호 — 앞으로 무엇을 보면 시나리오 분기가 결정되는가.\n\n"
    "=== 형식 자유 (보고서 본문) ===\n"
    "- 섹션 수 / 길이 / 순서 / 톤 모두 사건 성격에 맞게 자유 결정.\n"
    "- 정형 템플릿 슬롯에 데이터 끼워맞추지 말 것. 글이 데이터를 끌고 가야 함.\n"
    "- heading 은 사건 본질을 가리키는 한국어. 'PART I' 같은 영문 라벨 금지.\n"
    "- prose 는 마크다운 단락 자유. 짧은 문단 권장.\n\n"
    "=== 음슴체 + 쉬운 우리말 ===\n"
    "- 음슴체 (~함, ~임, ~없음).\n"
    "- 학부생 수준 어휘. '베이스라인/컨센서스/내러티브' 같은 외래어 남발 금지.\n"
    "- 영어 약어 첫 등장 시 괄호로 풀어쓸 것.\n\n"
    "=== 출처 추적성 (필수) ===\n"
    "- 입력의 ``event.sources`` 에 1차 출처 URL 목록이 있음.\n"
    "- 본문에서 *수치/날짜/구체 사실* 을 인용할 땐 가능하면 출처 URL 을 직접 본문에\n"
    "  '(출처: example.com)' 형식으로 표기하거나 cited_sources 에 정리.\n"
    "- 출처가 없는 추론은 '~라고 추정' / '~할 가능성' 같은 보수 표현으로 명시.\n\n"
    "=== 차트 (v4.2.0 — 데이터까지 직접 emit) ===\n"
    "- *수치 비교가 본문 이해에 결정적* 일 때만 emit. 사건당 0~3개가 적당.\n"
    "- 무관한 차트 박지 말 것 (mono guide §6 anti-pattern).\n"
    "- 섹션의 ``charts`` 배열에 차트 1개당 dict 1개. 형식:\n"
    "  ```json\n"
    "  {\n"
    '    \"type\": \"donut|bar|line|gantt|network|stacked|bubble|heatmap\",\n'
    '    \"title\": \"차트 제목\",\n'
    '    \"data\": [...],            // type 별 스키마 (아래 참조)\n'
    '    \"note\": \"caption (선택)\"\n'
    "  }\n"
    "  ```\n"
    "- type 별 data 스키마:\n"
    "  · donut:   [{label, value:number, note?}]                   비중 비교 (3개 이상, 균등 X)\n"
    "  · bar:     [{label, value:number, note?}]                   순위·분포\n"
    "  · line:    [{x, y:number, event?}]                          시계열 추이\n"
    "  · gantt:   [{label, start, end, note?}]                     사건 구간 (start/end 는 상대 인덱스 또는 날짜)\n"
    "  · network: {nodes:[{id,label,group?}], links:[{source,target,type?}]}  관계도\n"
    "  · stacked: {scenarios:[{name, segments:[{label,value:number}]}]}  시나리오 × 행위자 영향\n"
    "  · bubble:  [{label, x:number, y:number, size?:number}]      확률 × 영향 매트릭스\n"
    "  · heatmap: [{title, severity:'low'|'medium'|'high'}]        단계별 위험도\n"
    "- 모든 차트는 mono guide 의 45° 패턴 + 단일 골드 액센트. 색은 자동 적용.\n"
    "- 데이터 없으면 차트도 없음. 모르는 수치를 *추정해서* 차트 만들지 말 것.\n\n"
    "=== 지도 (v4.2.0 — 지리적 사건일 때만) ===\n"
    "- 사건이 *명백히 지리적* 일 때만 (해협 봉쇄 / 무역 회랑 / 분쟁 지역 등).\n"
    "- 보고서 레벨 1개 (top-level ``embedded_map``). 섹션별 지도 없음.\n"
    "- 형식:\n"
    "  ```json\n"
    "  {\n"
    '    \"center\": [경도, 위도],\n'
    '    \"zoom\": 3.0,\n'
    '    \"markers\": [{\"id\":\"hormuz\",\"name\":\"호르무즈\",\"lng\":56.4,\"lat\":26.6,\"highlight\":true}],\n'
    '    \"arcs\": [{\"from_id\":\"hormuz\",\"to_id\":\"singapore\",\"highlight\":true,\"label\":\"원유 회랑\"}],\n'
    '    \"legend\": [{\"label\":\"중점 회랑\",\"kind\":\"line\",\"highlight\":true}]\n'
    "  }\n"
    "  ```\n"
    "- d3-geo + TopoJSON 베이스맵 위에 mono 톤으로 렌더 (외부 타일 의존 없음).\n\n"
    "=== 정형 블록 (선택, 보수적) ===\n"
    "- 풍부한 정형 데이터를 본문 외에 따로 보여줘야 할 때만.\n"
    "- ``embedded_blocks``: actor_cards / scenario_table / timeline / flow_chain /\n"
    "  watchlist / data_series / risk_matrix / decomposition / counter_hypothesis /\n"
    "  callout. v4.2.0 Tier 4 에선 데이터 출처 (players/scenarios 등) 가 비어있어\n"
    "  대부분 렌더 안 됨. 본문에 풀어쓰는 것을 기본으로.\n\n"
    "=== 모순 / 반대 가설 (Anti-pattern #5) ===\n"
    "- contradictions 배열에 명시적 list 로 보존. 본문 안에서도 한 섹션은 모순/\n"
    "  반대 가설을 다루는 것을 권장.\n"
    "- 어느 쪽 손을 들어줬는지, 패배한 입장은 어떤 조건에서 살아나는지 명시.\n\n"
    "=== 감시 신호 (Watchlist 통합) ===\n"
    "- watch_signals 배열 — Watchlist 시스템이 SQLite 에 INSERT.\n"
    "- 형식: [{signal, description, indicates, deadline?, icon?}]\n"
    "  · signal: 짧은 식별자 (예: 'Fed 6월 FOMC 점도표')\n"
    "  · description: 신호 설명 한 문장\n"
    "  · indicates: 이 신호가 어느 시나리오 분기를 가리키는지\n"
    "  · deadline: 'YYYY-MM-DD' 또는 '6월 중' 등 (생략 가능)\n"
    "  · icon: 이모지 1~2자 (생략 가능)\n\n"
    "=== JSON 응답 형식 (반드시 준수) ===\n"
    "```json\n"
    "{\n"
    '  "headline": "사건의 본질을 가리키는 한 줄 (~30자)",\n'
    '  "deck": "부제 1~2 문장 (~80자). 헤드라인이 못 담은 핵심.",\n'
    '  "sections": [\n'
    "    {\n"
    '      "heading": "섹션 제목",\n'
    '      "kicker": "도입구 한 문장 (생략 가능)",\n'
    '      "prose": "본문. 단락 사이는 \\n\\n. 마크다운 강조(*..*)·인용(>) 가능.",\n'
    '      "charts": [\n'
    "        {\n"
    '          \"type\": \"donut\",\n'
    '          \"title\": \"호르무즈 의존 비중\",\n'
    '          \"data\": [\n'
    '            {\"label\":\"한국\",\"value\":12,\"note\":\"원유\"},\n'
    '            {\"label\":\"일본\",\"value\":11},\n'
    '            {\"label\":\"기타\",\"value\":77}\n'
    "          ]\n"
    "        }\n"
    "      ],\n"
    '      "embedded_blocks": [],\n'
    '      "pull_quote": "강조 인용 한 문장 (생략 가능)"\n'
    "    }\n"
    "  ],\n"
    '  "closing": "에필로그 1~2 문장 (생략 가능).",\n'
    '  "embedded_map": null,\n'
    '  "watch_signals": [\n'
    "    {\n"
    '      \"signal\": \"Fed 6월 FOMC 점도표\",\n'
    '      \"description\": \"추가 인하 시그널 여부\",\n'
    '      \"indicates\": \"기준선 vs 인하 가속 시나리오 분기\",\n'
    '      \"deadline\": \"2026-06-18\",\n'
    '      \"icon\": \"📊\"\n'
    "    }\n"
    "  ],\n"
    '  "contradictions": [\n'
    "    {\n"
    '      \"side_a\": \"관점 A 한 줄\",\n'
    '      \"side_b\": \"반대 관점 B 한 줄\",\n'
    '      \"evidence\": \"양 관점이 충돌하는 데이터/논거 (생략 가능)\",\n'
    '      \"resolution\": \"현 시점 어느 손 들었는지 + 패배 입장 살아나는 조건\"\n'
    "    }\n"
    "  ],\n"
    '  "confidence_summary": "출처 다양성/신선도/확신도 한 줄 자유 평가",\n'
    '  "confidence_score": 0.0~1.0\n'
    "}\n"
    "```\n"
    "JSON 만 출력. 추가 설명 텍스트 금지.\n"
)


class NarrativeComposer:
    """Opus 4.7 단일 콜로 보고서를 자유 형식으로 작성.

    Orchestrator 가 deep 모드에서 ``synthesis_judge`` 직후 호출.
    실패 시 ``compose()`` 가 ``None`` 반환 → 호출자가 폴백 archetype 으로 재라우팅.
    """

    # Opus 4.7 모델 ID. config.model_name 이 4.6 이라도 composer 만 4.7 사용.
    COMPOSER_MODEL: str = "claude-opus-4-7"
    MAX_TOKENS: int = 8192

    def __init__(self, config: Config) -> None:
        self.config = config
        self._api_client: object | None = None
        self.telemetry: Optional[RunTelemetry] = None
        if not config.use_cli_mode:
            import anthropic
            self._api_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def compose_unified(
        self,
        context: ContextAnalysis,
        mode: str = "standard",
    ) -> ComposedReport | None:
        """v4.0.0 Tier 4 — ContextAnalysis 만 받아 *단독 분석 + 작성*.

        이전 ``compose()`` 는 7개 분석가 결과를 받아 편집만 했음. 본 메서드는
        composer 가 행위자/구조/시나리오/모순 분석까지 *모두* Opus 4.7 단일 호출에서
        수행. orchestrator 가 v4.0.0 부터 본 경로를 호출.
        """
        user_payload = self._build_unified_payload(context, mode)
        user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(user_message)
            else:
                raw = await self._call_api(user_message)
        except Exception as e:
            logger.warning("[unified_composer] LLM call failed: %s", e)
            return None

        composed = self._parse_response(raw)
        if composed is None:
            return None
        # v4.0.0: chart_catalog 가 비었으니 embedded_charts 도 빈 list 로 강제 (검증 layer).
        composed = self._validate_references(composed, chart_catalog=[])
        logger.info(
            "[unified_composer] Composed: %d sections, headline=%r, "
            "watch_signals=%d, contradictions=%d, conf=%.2f",
            len(composed.sections), composed.headline[:40],
            len(composed.watch_signals), len(composed.contradictions),
            composed.confidence_score,
        )
        return composed

    @staticmethod
    def _build_unified_payload(context: ContextAnalysis, mode: str) -> dict:
        """v4.0.0 Tier 4 — ContextAnalysis + mode → composer 입력.

        멀티 에이전트 시절의 풍부한 입력 (players/dynamics/chain_reaction/...) 없이
        1차 사실 자료만 제공. composer 가 그 위에서 분석을 수행.
        """
        return {
            "mode": mode,
            "event": {
                "name": context.event_name,
                "category": context.category,
                "date": context.date,
                "summary": context.summary,
                "background": context.background,
                "key_figures": context.key_figures,
                "timeline": context.timeline,
                "sources": context.sources,
            },
        }

    async def compose(
        self,
        result: FullAnalysisResult,
        chart_catalog: list[dict],
    ) -> ComposedReport | None:
        """[Legacy v3.3.0~v3.5.0] 7개 분석가 결과를 받아 편집만 하는 경로.

        v4.0.0 Tier 4 부터는 ``compose_unified()`` 가 기본 경로. 본 메서드는
        하위 호환을 위해 보존하지만 orchestrator 는 호출하지 않음. 향후 정리 시 제거.
        """
        user_payload = self._build_user_payload(result, chart_catalog)
        # JSON 직렬화 — compact (한국어 nested JSON 토큰 절약, base.py 와 동일).
        user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(user_message)
            else:
                raw = await self._call_api(user_message)
        except Exception as e:
            logger.warning("[narrative_composer] LLM call failed: %s", e)
            return None

        composed = self._parse_response(raw)
        if composed is None:
            return None
        # 출력의 chart_id / block_type 을 catalog 와 대조하여 invalid 항목 제거.
        composed = self._validate_references(composed, chart_catalog)
        logger.info(
            "[narrative_composer] Composed report: %d sections, headline=%r",
            len(composed.sections), composed.headline[:40],
        )
        return composed

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_payload(
        result: FullAnalysisResult, chart_catalog: list[dict]
    ) -> dict:
        """Composer 에 전달할 입력 dict.

        토큰 절약 목적: 빈 필드 생략, glossary 같은 비핵심 필드 제외.
        """
        payload: dict = {}

        if result.context:
            ctx = result.context
            payload["event"] = {
                "name": ctx.event_name,
                "category": ctx.category,
                "date": ctx.date,
                "summary": ctx.summary,
                "background": ctx.background,
                "key_figures": ctx.key_figures,
                "timeline": ctx.timeline,
                "sources": ctx.sources,
            }

        if result.players and result.players.players:
            payload["players"] = {
                "list": result.players.players,
                "alliances": result.players.alliances,
                "power_dynamics": result.players.power_dynamics,
            }

        if result.dynamics:
            d = result.dynamics
            payload["dynamics"] = {
                "framework": d.framework,
                "core_tension": d.core_tension,
                "asymmetries": d.asymmetries,
                "feedback_loops": d.feedback_loops,
                "tipping_points": d.tipping_points,
                "key_insight": d.key_insight,
                "counter_view": d.counter_view,
            }

        if result.chain_reaction and result.chain_reaction.chain:
            cr = result.chain_reaction
            payload["chain_reaction"] = {
                "chain": cr.chain,
                "feedback_loops": cr.feedback_loops,
                "wildcards": cr.wildcards,
                "worst_case": cr.worst_case,
            }

        if result.scenarios:
            sc = result.scenarios
            payload["scenarios"] = {
                "list": sc.scenarios,
                "watch_signals": sc.watch_signals,
                "invalidation_conditions": sc.invalidation_conditions,
                "base_case_summary": sc.base_case_summary,
            }

        # Findings / Claims catalog — composer 가 cite 할 수 있도록 ID + 본문만 노출.
        if result.findings:
            claims_catalog = []
            for f in result.findings:
                claims_catalog.append({
                    "claim_id": f.main_claim.claim_id,
                    "lens": f.lens_id,
                    "type": f.main_claim.claim_type,
                    "statement": f.main_claim.statement,
                    "answers": f.answers_question,
                    "counter_hypothesis": f.counter_hypothesis,
                })
            payload["claims"] = claims_catalog

        if result.judgment:
            j = result.judgment
            payload["judgment"] = {
                "main": j.main_judgment,
                "base_scenario": j.base_scenario,
                "biggest_uncertainty": j.biggest_uncertainty,
                "contradictions": j.contradictions,
                "counter_hypothesis": j.counter_hypothesis,
            }

        # Strategy intent — composer 가 무엇에 답해야 하는지.
        if result.strategy:
            payload["intent"] = {
                "user_intent": result.strategy.user_intent,
                "core_questions": result.strategy.core_questions,
                "event_type": result.strategy.event_type,
            }

        # 차트 catalog — composer 가 referencing 할 수 있는 차트 목록.
        if chart_catalog:
            payload["available_charts"] = chart_catalog

        return payload

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_cli(self, user_message: str) -> str:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{user_message}"
        cmd = [
            claude_bin,
            "-p", full_prompt,
            "--output-format", "text",
            "--model", self.COMPOSER_MODEL,
            "--dangerously-skip-permissions",
        ]
        logger.info(
            "[narrative_composer] Starting CLI call (%s, prompt=%d chars)",
            self.COMPOSER_MODEL, len(full_prompt),
        )
        start = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed_ms = int((time.time() - start) * 1000)
        if proc.returncode != 0:
            err = stderr.decode().strip() if stderr else "unknown"
            raise RuntimeError(f"narrative_composer CLI exit={proc.returncode}: {err}")
        raw = stdout.decode().strip()
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name="narrative_composer",
                input_chars=len(full_prompt),
                output_chars=len(raw),
                elapsed_ms=elapsed_ms,
            )
        logger.info(
            "[narrative_composer] CLI response (%d chars, %dms)", len(raw), elapsed_ms,
        )
        return raw

    async def _call_api(self, user_message: str) -> str:
        assert self._api_client is not None, "API client not initialised"
        start = time.time()
        response = await self._api_client.messages.create(  # type: ignore[union-attr]
            model=self.COMPOSER_MODEL,
            max_tokens=self.MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text  # type: ignore[index]
        elapsed_ms = int((time.time() - start) * 1000)
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name="narrative_composer",
                input_chars=len(SYSTEM_PROMPT) + len(user_message),
                output_chars=len(raw),
                elapsed_ms=elapsed_ms,
            )
        return raw

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> ComposedReport | None:
        """Extract JSON from raw text and validate as ComposedReport."""
        if "```json" in raw:
            json_str = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            json_str = raw.split("```", 1)[1].split("```", 1)[0].strip()
        else:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[narrative_composer] No JSON object in response")
                return None
            json_str = match.group()
        try:
            data = json.loads(json_str)
            return ComposedReport.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[narrative_composer] Parse/validation failed: %s", e)
            return None

    @staticmethod
    def _validate_references(
        composed: ComposedReport, chart_catalog: list[dict]
    ) -> ComposedReport:
        """Composer 가 적은 chart_id 와 block_type 중 invalid 한 것을 제거.

        - chart_id 는 catalog 의 id 와 매칭되어야 함.
        - block_type 은 화이트리스트 (BlockType Literal) 내여야 함.
        """
        valid_chart_ids = {c["id"] for c in chart_catalog}
        valid_block_types = {
            "actor_cards", "scenario_table", "timeline", "flow_chain",
            "watchlist", "data_series", "risk_matrix", "decomposition",
            "counter_hypothesis", "callout", "narrative", "matrix",
            "argument_pair", "claim_card", "evidence_table", "qna",
            "decision_matrix",
        }
        for sec in composed.sections:
            sec.embedded_charts = [
                cid for cid in sec.embedded_charts if cid in valid_chart_ids
            ]
            sec.embedded_blocks = [
                bt for bt in sec.embedded_blocks if bt in valid_block_types
            ]
        return composed
