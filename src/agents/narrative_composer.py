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
    FullAnalysisResult,
)
from src.telemetry import RunTelemetry

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "당신은 사건 분석 보고서의 편집장. 7명의 분석가가 수집한 evidence + claim 을 받아 "
    "독자에게 전달할 *완성된 보고서* 를 작성한다.\n\n"
    "=== 형식 자유 ===\n"
    "- 섹션 수 / 길이 / 순서 / 톤 모두 사건 성격에 맞게 자유 결정.\n"
    "- 정형 템플릿 슬롯에 데이터를 끼워맞추지 말 것. 글이 데이터를 끌고 가야 함.\n"
    "- 한 사건엔 3~7개 섹션이 적당. 사건이 단순하면 더 적게, 복잡하면 더 많이.\n"
    "- heading 은 사건 본질을 가리키는 한국어. 'PART I' 같은 영문 라벨 금지.\n"
    "- prose 는 마크다운 단락 자유. 짧은 문단을 권장하나 강제하지 않음.\n\n"
    "=== 음슴체 + 쉬운 우리말 ===\n"
    "- 음슴체 (~함, ~임, ~없음).\n"
    "- 학부생 수준 어휘. '베이스라인/컨센서스/내러티브' 같은 외래어 남발 금지.\n"
    "- 영어 약어 첫 등장 시 괄호로 풀어쓸 것.\n\n"
    "=== Evidence 추적성 (필수) ===\n"
    "- 본문에 등장하는 *핵심 주장* 은 ``cited_claim_ids`` 에 적용된 claim_id 를 적는다.\n"
    "- claim 카탈로그 (입력에 포함) 외의 claim_id 를 만들지 말 것.\n"
    "- evidence 가 부족한 주장은 *작성하지 말 것*. 모르는 건 모른다고 쓰는 게 낫다.\n\n"
    "=== 차트 (선택) ===\n"
    "- 입력의 ``available_charts`` 에 *지금 가용한* 차트만 listing 됨.\n"
    "- 본문에서 강조하고 싶은 지점에 ``embedded_charts: [chart-id]`` 로 박는다.\n"
    "- 같은 섹션에 여러 차트 가능. 0개여도 무방.\n"
    "- 가용 외의 chart_id 를 적지 말 것.\n\n"
    "=== 정형 블록 임베드 (선택) ===\n"
    "- 풍부한 정형 데이터 (행위자 카드, 시나리오 그리드 등) 를 그대로 끼우고 싶으면 \n"
    "  ``embedded_blocks: [block_type]`` 에 BlockType 을 적는다.\n"
    "- 가용 BlockType: actor_cards, scenario_table, timeline, flow_chain, watchlist,\n"
    "  data_series, risk_matrix, decomposition, counter_hypothesis, callout.\n"
    "- 본문에서 같은 정보를 길게 풀어 적었다면 블록 embed 는 생략.\n\n"
    "=== 모순 (Anti-pattern #5) ===\n"
    "- judgment.contradictions 가 있으면 *드러내라*. 봉합하지 말 것.\n"
    "- 어느 쪽 손을 들어줬는지, 패배한 입장은 어떤 조건에서 살아나는지 명시.\n\n"
    "=== JSON 응답 형식 (반드시 준수) ===\n"
    "```json\n"
    "{\n"
    '  "headline": "사건의 본질을 가리키는 한 줄 (~30자)",\n'
    '  "deck": "부제 1~2 문장 (~80자). 헤드라인이 못 담은 핵심.",\n'
    '  "sections": [\n'
    "    {\n"
    '      "heading": "섹션 제목",\n'
    '      "kicker": "도입구 한 문장 (생략 가능, 빈 문자열도 OK)",\n'
    '      "prose": "본문. 단락 사이는 \\n\\n. 마크다운 강조(*..*)·인용(>) 사용 가능.",\n'
    '      "embedded_charts": ["chart-id"],\n'
    '      "embedded_blocks": ["block_type"],\n'
    '      "pull_quote": "강조 인용 한 문장 (생략 가능)",\n'
    '      "cited_claim_ids": ["C-..."]\n'
    "    }\n"
    "  ],\n"
    '  "closing": "에필로그 1~2 문장. 분석가의 한계와 유보 (생략 가능)."\n'
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

    async def compose(
        self,
        result: FullAnalysisResult,
        chart_catalog: list[dict],
    ) -> ComposedReport | None:
        """Run a single Opus 4.7 call → ComposedReport.

        Args:
            result: 분석 결과 전체 (judgment 포함, visuals 채워진 상태).
            chart_catalog: ``visual_builder.build_chart_catalog(chart_payload)`` 결과.
                          데이터 가용한 차트만 [{"id","title","hint"}] 형식.

        Returns:
            ComposedReport 또는 실패 시 None.
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
