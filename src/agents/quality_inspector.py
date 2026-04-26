"""Quality Inspector — V3 Step 4 (v2.8.0).

두 개의 quality gate 를 노출한다.

- ``gate_1_plan_sanity(strategy)`` — 분석 시작 전 strategy 가 분석 가능한지 검사.
- ``gate_2_coverage_check(strategy, findings, judgment)`` — 분석 산출물의 커버리지 검사.

각 게이트는 ``(passed: bool, reason: str)`` 튜플을 반환한다. 실패 시 사유는 짧고 사용자에게
그대로 노출 가능 (텔레그램 알림에 들어감). Anti-pattern #7 회피 — 게이트 우회 금지.

설계 원칙
- **Heuristic-first**: LLM 호출 없이 명확히 잡을 수 있는 위반은 먼저 휴리스틱으로 잡는다.
  유닛 테스트 가능성 + 빠른 응답 + 토큰 절약. 휴리스틱이 통과해도 LLM 검증으로 보조 가능.
- **LLM-as-judge** (선택적): config.use_cli_mode 일 때 ``claude -p`` 로 judge call. CLI 가 없거나
  실패하면 휴리스틱 결과를 최종으로 채택 (게이트 자체가 죽지 않게).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from typing import TYPE_CHECKING

from src.config import Config
from src.models import (
    AnalysisStrategy,
    AnalyticalFinding,
    JudgmentVerdict,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class QualityInspector:
    """Two-gate validator. Heuristic-first, optional LLM augmentation."""

    def __init__(self, config: Config) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Gate 1: Plan Sanity
    # ------------------------------------------------------------------

    async def gate_1_plan_sanity(
        self, strategy: AnalysisStrategy | None
    ) -> tuple[bool, str]:
        """검사 항목:
        - core_questions 존재 + 분석 가능한 질문인지
        - lens-intent 정합성 (recommended_lenses 가 user_intent 와 호환)
        - evidence_plan 실행 가능성 (있다면 expected_source_types 명시)
        """
        # Heuristic checks
        passed, reason = self._gate_1_heuristics(strategy)
        if not passed:
            return False, reason

        # Optional LLM augmentation. CLI 미설치 또는 실패 시 휴리스틱 결과 채택.
        try:
            llm_pass, llm_reason = await self._gate_1_llm_judge(strategy)
            if not llm_pass:
                return False, llm_reason
        except Exception as e:
            logger.info(
                "[quality_inspector] gate_1 LLM judge skipped: %s "
                "(heuristic still PASSED)", e,
            )
        return True, "ok"

    @staticmethod
    def _gate_1_heuristics(
        strategy: AnalysisStrategy | None,
    ) -> tuple[bool, str]:
        if strategy is None:
            return False, "strategy is None"
        if not strategy.core_questions:
            return False, "core_questions 비어있음"
        if not strategy.recommended_lenses:
            return False, "recommended_lenses 비어있음"
        # Each core_question 은 의미 있는 길이여야 함.
        for q in strategy.core_questions:
            if not q or len(q.strip()) < 4:
                return False, f"core_question 너무 짧음: {q!r}"
        # evidence_plan 이 있다면 각 EvidenceNeed 가 expected_source_types 를 채웠는지.
        for need in strategy.evidence_plan:
            if not need.expected_source_types:
                return False, (
                    f"evidence_plan[{need.need_id}].expected_source_types 비어있음"
                )
        return True, "ok"

    async def _gate_1_llm_judge(
        self, strategy: AnalysisStrategy
    ) -> tuple[bool, str]:
        """LLM 에게 plan sanity 를 묻는다. CLI 모드 + claude 바이너리 존재 시에만 동작."""
        if not self.config.use_cli_mode:
            return True, "ok"
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            return True, "ok"

        prompt = (
            "당신은 분석 계획 점검관. 아래 strategy 가 실행 가능한 분석 계획인지 판정.\n\n"
            "검사 기준:\n"
            "1) core_questions 가 분석으로 답할 수 있는 형태인가\n"
            "2) recommended_lenses 가 user_intent 와 호환되는가\n"
            "3) 명백한 실행 불가 요소가 있는가\n\n"
            'JSON 만 출력 (다른 텍스트 금지): {"pass": true|false, "reason": "짧은 사유"}\n\n'
            f"strategy: {strategy.model_dump_json(by_alias=False)[:1500]}"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt,
                "--output-format", "text",
                "--model", self.config.model_name_light,
                "--dangerously-skip-permissions",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            raw = stdout.decode().strip()
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return True, "ok"
            data = json.loads(match.group())
            if not data.get("pass", True):
                return False, str(data.get("reason", "LLM judge rejected"))[:160]
        except (asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.info("[quality_inspector] gate_1 LLM judge soft-skip: %s", e)
        return True, "ok"

    # ------------------------------------------------------------------
    # Gate 2: Coverage Check
    # ------------------------------------------------------------------

    async def gate_2_coverage_check(
        self,
        strategy: AnalysisStrategy | None,
        findings: list[AnalyticalFinding],
        judgment: JudgmentVerdict | None,
    ) -> tuple[bool, str]:
        """검사 항목:
        - 모든 core_question 에 finding 매칭
        - 모든 claim 에 evidence 연결 (Pydantic 이 이미 강제하지만 추가 가드)
        - 모순 판정 존재 (judgment 가 contradictions 에 명시적으로 다루었는가 — 빈 배열도 OK)
        """
        return self._gate_2_heuristics(strategy, findings, judgment)

    @staticmethod
    def _gate_2_heuristics(
        strategy: AnalysisStrategy | None,
        findings: list[AnalyticalFinding],
        judgment: JudgmentVerdict | None,
    ) -> tuple[bool, str]:
        if judgment is None:
            return False, "judgment is None (Synthesis Judge 미실행)"
        if strategy is None:
            return False, "strategy is None"

        # 1) core_questions 매칭
        answered = {f.answers_question for f in findings if f.answers_question}
        unanswered = [q for q in strategy.core_questions if q not in answered]
        if unanswered:
            return False, (
                f"미답변 core_question {len(unanswered)}건"
                f" (예: {unanswered[0][:60]!r})"
            )

        # 2) Claim → Evidence 연결 (Pydantic validator 가 이미 잡지만 한 번 더)
        for f in findings:
            if not f.main_claim.evidence_ids:
                return False, f"finding {f.finding_id} claim 에 evidence_id 없음"
            evidence_pool = {e.evidence_id for e in f.evidence}
            missing = [
                eid for eid in f.main_claim.evidence_ids
                if eid not in evidence_pool
            ]
            if missing:
                return False, (
                    f"finding {f.finding_id} 의 claim 이 참조하는 evidence_id "
                    f"{missing!r} 가 finding.evidence 에 없음"
                )

        # 3) 모순 판정 존재 — judgment.contradictions 가 명시적으로 채워졌는가.
        #    빈 리스트도 "모순 없음을 명시" 한 것으로 간주 (Anti-pattern #5: 봉합 금지 — 별개).
        #    main_judgment 와 base_scenario 는 비어있으면 안 됨.
        if not judgment.main_judgment.strip():
            return False, "judgment.main_judgment 비어있음 (종합 판단 누락)"
        if not judgment.counter_hypothesis.strip():
            return False, "judgment.counter_hypothesis 비어있음 (반대 가설 누락)"

        return True, "ok"
