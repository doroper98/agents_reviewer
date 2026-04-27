"""LensRunner ABC + 공통 LLM 호출 헬퍼.

V3 Step 5-A (v2.9.0). Spec: REFACTOR_V3_PLAN.md §5 Step 5.

각 lens 는 본 ABC 를 구현해 ``async run(evidence, directive) -> list[AnalyticalFinding]``
형태로 분석 결과를 산출한다. 기존 v2 페르소나 (BaseAgent 상속) 과 별개의 트랙 — Step 5-C
에서 PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst 가 각각 stakeholder/structural/cascade
lens 로 이전될 예정.

토큰 절약을 위해 본 base 는 prompt 를 매우 좁게 고정 (사건 메타 + evidence id+quote 일부 + directive).
본격 prompt 튜닝은 v3.x 패치에서.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from abc import ABC, abstractmethod
from typing import Any

from src.config import Config
from src.models import (
    AnalyticalFinding,
    Claim,
    ConfidenceProfile,
    Evidence,
    UserIntent,
)

logger = logging.getLogger(__name__)


_LENS_OUTPUT_SCHEMA = (
    'JSON 만 출력. 다음 형식 정확히 준수:\n'
    '{\n'
    '  "main_claim": {\n'
    '    "statement": "이 lens 의 핵심 주장 1~2 문장",\n'
    '    "claim_type": "fact|inference|prediction|judgment",\n'
    '    "evidence_ids": ["E-001", ...]  # 아래 Evidence 풀에서 인용\n'
    '  },\n'
    '  "supporting_findings": [],\n'
    '  "evidence_picked": ["E-001", ...],\n'
    '  "confidence": {\n'
    '    "source_diversity": 0.0~1.0,\n'
    '    "data_freshness": 0.0~1.0,\n'
    '    "expert_consensus": 0.0~1.0\n'
    '  },\n'
    '  "counter_hypothesis": "본 결론의 반대 가설 1 문장",\n'
    '  "counter_required_evidence": ["반대 가설 입증에 필요한 증거 1", ...]\n'
    '}\n'
    '\nevidence_ids 는 비어 있으면 안 됨 (Anti-pattern #4: claim 에 evidence 1개 이상 강제). '
    'Evidence 풀이 비어있다고 판단되면 evidence_ids 에 "E-INF-001" 을 넣어 model_inference 임을 명시.\n'
)


class LensRunner(ABC):
    """Lens 추상 베이스 클래스.

    하위 구현은 다음을 정의한다:
    - 클래스 속성: ``lens_id``, ``name``, ``suitable_intents``, ``suitable_event_types``,
      ``method_steps``, ``failure_modes``
    - ``system_prompt`` 속성 또는 클래스 변수
    - ``answers_question_for(question)`` (선택) — round-robin 매칭 외 더 똑똑한 매칭
    """

    lens_id: str
    name: str
    suitable_intents: list[UserIntent]
    suitable_event_types: list[str]
    method_steps: list[str]
    failure_modes: list[str]
    system_prompt: str

    def __init__(self, config: Config) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    async def run(
        self,
        evidence: list[Evidence],
        directive: str = "",
        event_meta: dict[str, Any] | None = None,
        answers_question: str = "",
    ) -> list[AnalyticalFinding]:
        """Evidence + directive → list[AnalyticalFinding].

        ``event_meta`` 는 사건 정보 (event_name, summary, category) 를 담는 dict — 호출자가 채움.
        ``answers_question`` 는 strategy.core_questions 중 본 lens 가 답해야 할 질문 (orchestrator 가
        round-robin 으로 배정 후 전달).
        """
        prompt = self._build_prompt(evidence, directive, event_meta or {}, answers_question)
        try:
            raw = await self._call_llm(prompt)
        except Exception as e:
            logger.warning(
                "[lens:%s] LLM call failed: %s; emitting heuristic-fallback finding",
                self.lens_id, e,
            )
            return self._fallback_finding(evidence, directive, answers_question)

        try:
            data = self._parse_json(raw)
        except Exception as e:
            logger.warning(
                "[lens:%s] JSON parse failed: %s; emitting heuristic-fallback finding",
                self.lens_id, e,
            )
            return self._fallback_finding(evidence, directive, answers_question)

        try:
            finding = self._build_finding(data, evidence, answers_question)
        except Exception as e:
            logger.warning(
                "[lens:%s] finding build failed (likely Pydantic validator): %s; "
                "fallback used. Anti-pattern #4 가드 — claim 에 evidence 가 정상 연결되었는지 점검.",
                self.lens_id, e,
            )
            return self._fallback_finding(evidence, directive, answers_question)

        return [finding]

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        evidence: list[Evidence],
        directive: str,
        event_meta: dict[str, Any],
        answers_question: str,
    ) -> str:
        # Evidence 풀은 토큰 절약 차원에서 상위 N개만 inline.
        ev_lines: list[str] = []
        for e in evidence[:10]:
            quote = (e.quote_or_data or e.source_url or "")[:120]
            ev_lines.append(
                f"  {e.evidence_id} [{e.reliability}] {quote}"
            )
        evidence_block = "\n".join(ev_lines) or "  (Evidence 풀 비어있음 — model_inference 로 처리 가능)"

        method_block = "\n".join(f"  · {step}" for step in self.method_steps)
        failure_block = "\n".join(f"  · {fm}" for fm in self.failure_modes)
        return (
            self.system_prompt
            + "\n\n=== 분석 method_steps (이 순서대로 사고 적용) ===\n"
            + method_block
            + "\n\n=== 본 lens 의 약점 (해당 시 finding 에서 명시) ===\n"
            + failure_block
            + "\n\n=== 사건 ===\n"
            + f"  사건명: {event_meta.get('event_name', '')}\n"
            + f"  분류: {event_meta.get('category', '')}\n"
            + f"  요약: {(event_meta.get('summary') or '')[:400]}\n"
            + f"\n=== 답해야 할 핵심 질문 ===\n  {answers_question or '(미지정 — 본 lens 의 자체 결론)'}\n"
            + (f"\n=== 전략 지시 (있는 경우) ===\n  {directive[:300]}\n" if directive else "")
            + "\n=== 가용 Evidence 풀 ===\n"
            + evidence_block
            + "\n\n"
            + _LENS_OUTPUT_SCHEMA
        )

    # ------------------------------------------------------------------
    # LLM call (CLI or API), parse, build
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        if self.config.use_cli_mode:
            claude_bin = shutil.which("claude")
            if claude_bin is None:
                raise RuntimeError("claude CLI not found")
            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt,
                "--output-format", "text",
                "--model", self.config.model_name_light,
                "--dangerously-skip-permissions",
                "--allowedTools", "WebFetch,WebSearch",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"claude CLI exited {proc.returncode}: "
                    f"{stderr.decode()[:200] if stderr else ''}"
                )
            return stdout.decode().strip().replace("**", "")
        # API path — lazy import
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
        resp = await client.messages.create(
            model=self.config.model_name_light, max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text  # type: ignore[index]

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("no JSON object in response")
        return json.loads(match.group())

    def _build_finding(
        self,
        data: dict[str, Any],
        evidence: list[Evidence],
        answers_question: str,
    ) -> AnalyticalFinding:
        claim_data = data.get("main_claim") or {}
        statement = (claim_data.get("statement") or "").strip()
        if not statement:
            raise ValueError("main_claim.statement empty")
        evidence_ids_in_claim = list(claim_data.get("evidence_ids") or [])
        evidence_ids_picked = list(data.get("evidence_picked") or evidence_ids_in_claim)

        # Filter to evidence_ids that actually exist in pool. Anti-pattern #4 guard:
        # if claim's evidence_ids are all unknown, fall back to "E-INF-001" (model_inference).
        pool_ids = {e.evidence_id for e in evidence}
        valid_ids = [eid for eid in evidence_ids_in_claim if eid in pool_ids]
        if not valid_ids:
            valid_ids = ["E-INF-001"]
            inf_evidence = Evidence(
                evidence_id="E-INF-001",
                source_url="",
                quote_or_data=f"({self.lens_id}) 1차 출처 미수집 — 모델 추론 기반",
                reliability="model_inference",
            )
            picked_evidence = [inf_evidence]
        else:
            picked_evidence = [e for e in evidence if e.evidence_id in evidence_ids_picked]
            if not picked_evidence:
                picked_evidence = [e for e in evidence if e.evidence_id in valid_ids]

        # Build the Claim — Pydantic validator enforces evidence_ids ≥ 1 (Anti-pattern #4).
        claim_type = claim_data.get("claim_type", "inference")
        if claim_type not in {"fact", "inference", "prediction", "judgment"}:
            claim_type = "inference"
        claim = Claim(
            claim_id=f"C-{self.lens_id}-001",
            statement=statement[:500],
            claim_type=claim_type,  # type: ignore[arg-type]
            evidence_ids=valid_ids,
        )

        confidence_data = data.get("confidence") or {}
        confidence = ConfidenceProfile(
            source_diversity=_clamp01(confidence_data.get("source_diversity", 0.5)),
            data_freshness=_clamp01(confidence_data.get("data_freshness", 0.6)),
            expert_consensus=_clamp01(confidence_data.get("expert_consensus", 0.5)),
        )

        return AnalyticalFinding(
            finding_id=f"F-{self.lens_id}-001",
            lens_id=self.lens_id,
            answers_question=answers_question,
            main_claim=claim,
            supporting_findings=list(data.get("supporting_findings") or []),
            evidence=picked_evidence,
            confidence=confidence,
            counter_hypothesis=(data.get("counter_hypothesis") or "")[:500],
            counter_required_evidence=list(data.get("counter_required_evidence") or [])[:5],
        )

    def _fallback_finding(
        self,
        evidence: list[Evidence],
        directive: str,
        answers_question: str,
    ) -> list[AnalyticalFinding]:
        """LLM 호출 또는 파싱 실패 시 사용. Pydantic 가드 통과를 위해 inferred placeholder 산출."""
        picked = evidence[:1] if evidence else [Evidence(
            evidence_id="E-INF-001",
            source_url="",
            quote_or_data=f"({self.lens_id}) lens 호출 실패 — fallback finding",
            reliability="model_inference",
        )]
        evidence_ids = [picked[0].evidence_id]
        claim = Claim(
            claim_id=f"C-{self.lens_id}-FALLBACK",
            statement=(
                f"({self.lens_id}) lens 가 정상 finding 을 산출하지 못함. "
                f"이 placeholder 는 게이트 통과 + 보고서 일관성 유지를 위한 것."
            ),
            claim_type="inference",
            evidence_ids=evidence_ids,
        )
        return [AnalyticalFinding(
            finding_id=f"F-{self.lens_id}-FALLBACK",
            lens_id=self.lens_id,
            answers_question=answers_question,
            main_claim=claim,
            evidence=picked,
            confidence=ConfidenceProfile(
                source_diversity=0.1, data_freshness=0.1, expert_consensus=0.1,
            ),
            counter_hypothesis="(lens 호출 실패 — 반대 가설 산출 불가)",
        )]

    @abstractmethod
    def _abstract_marker(self) -> None:
        """No-op abstract marker. 구체 lens 가 ``pass`` 만 정의해도 OK — class 속성으로 lens
        의 정체를 표현하는 것이 본 ABC 의 역할이고 run() 은 base 가 일괄 처리한다.
        """
        ...


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))
