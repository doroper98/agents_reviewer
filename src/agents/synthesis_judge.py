"""Synthesis Judge — V3 Step 4 (v2.8.0).

Findings 의 결론들을 비교해 *모순을 봉합하지 않고 드러내는* 종합 판단 산출.
Anti-pattern #5 (모순 봉합) 절대 위반 금지 — 모순은 ``contradictions`` 필드에 들어간다.

책무:
1. 렌즈 간 결론 정합성 매트릭스 작성 → ``contradictions`` 필드
2. 모순 발견 시 어느 쪽이 더 가능성 높은지 판정 (봉합 X — 한 쪽 채택은 명시적 ``resolution`` 으로 기록)
3. ConfidenceProfile 3축 분해 산출
4. counter_hypothesis + counter_evidence_needed 작성
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from typing import Any

from src.config import Config
from src.models import (
    AnalyticalFinding,
    ConfidenceProfile,
    JudgmentVerdict,
)

logger = logging.getLogger(__name__)


# Heuristic keyword pairs for fast contradiction detection. Each tuple is
# (positive_marker, negative_marker) — if one finding contains the positive and another
# the negative on the same topic, surface as a contradiction.
_CONFLICT_LEXICON: list[tuple[str, str]] = [
    ("상승", "하락"),
    ("증가", "감소"),
    ("강세", "약세"),
    ("확대", "축소"),
    ("호재", "악재"),
    ("우위", "열위"),
    ("개선", "악화"),
    ("회복", "침체"),
    ("긍정", "부정"),
    ("높음", "낮음"),
    ("성공", "실패"),
    ("동맹", "대립"),
]


class SynthesisJudge:
    """Findings → JudgmentVerdict. Heuristic-first, LLM-augmented when CLI available."""

    def __init__(self, config: Config) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    async def judge(self, findings: list[AnalyticalFinding]) -> JudgmentVerdict:
        if not findings:
            # Even with empty findings, we must return a fully-formed verdict so gate 2
            # can decide. Empty contradictions, but main_judgment / counter_hypothesis
            # marked clearly so gate 2 will reject.
            return JudgmentVerdict(
                main_judgment="(분석 finding 없음 — 종합 판단 불가)",
                base_scenario="(미정)",
                biggest_uncertainty="(finding 부재)",
                contradictions=[],
                counter_hypothesis="(반대 가설 산출 불가 — finding 부재)",
                counter_evidence_needed=[],
                confidence=ConfidenceProfile(
                    source_diversity=0.0, data_freshness=0.0, expert_consensus=0.0,
                ),
            )

        # 1) 모순 매트릭스 — heuristic 으로 lens 간 충돌 추출
        contradictions = self._detect_contradictions(findings)

        # 2) 신뢰도 3축 분해 — finding 들의 평균 + 모순 페널티
        confidence = self._aggregate_confidence(findings, contradictions)

        # 3) main_judgment / base_scenario / counter_hypothesis 산출
        #    LLM 이 가능하면 LLM 으로, 아니면 heuristic 으로.
        try:
            verdict_extras = await self._llm_synthesize(findings, contradictions)
        except Exception as e:
            logger.info("[synthesis_judge] LLM synthesize fallback to heuristic: %s", e)
            verdict_extras = self._heuristic_synthesize(findings, contradictions)

        return JudgmentVerdict(
            main_judgment=verdict_extras["main_judgment"],
            base_scenario=verdict_extras["base_scenario"],
            biggest_uncertainty=verdict_extras["biggest_uncertainty"],
            contradictions=contradictions,
            counter_hypothesis=verdict_extras["counter_hypothesis"],
            counter_evidence_needed=verdict_extras.get("counter_evidence_needed", []),
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Contradiction detection (Anti-pattern #5: 봉합 금지)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_contradictions(
        findings: list[AnalyticalFinding],
    ) -> list[dict[str, Any]]:
        """Pairwise conflict scan. 모순은 *드러나야* 한다 — 발견 시 resolution 에 명시적
        판정 (어느 쪽이 더 가능성 높은가) 을 적되, 그 적은 것이 봉합이 되어선 안 됨.
        """
        contradictions: list[dict[str, Any]] = []
        for i, fa in enumerate(findings):
            for fb in findings[i + 1:]:
                stmt_a = fa.main_claim.statement
                stmt_b = fb.main_claim.statement
                if not stmt_a or not stmt_b:
                    continue
                # counter_hypothesis 명시적 모순
                if fa.counter_hypothesis and fa.counter_hypothesis.strip() in stmt_b:
                    contradictions.append({
                        "lens_a": fa.lens_id,
                        "lens_b": fb.lens_id,
                        "conflict": (
                            f"{fa.lens_id} 의 반대 가설이 {fb.lens_id} 의 본 결론과 일치"
                        ),
                        "resolution": (
                            f"{fb.lens_id} 가 더 무게 있음 (confidence "
                            f"{fb.confidence.aggregate:.2f} vs "
                            f"{fa.confidence.aggregate:.2f}) — 단 봉합 아님, "
                            f"{fa.lens_id} 의 입장은 counter_hypothesis 로 보존"
                        ),
                    })
                    continue
                # 어휘 기반 충돌
                for pos, neg in _CONFLICT_LEXICON:
                    if (pos in stmt_a and neg in stmt_b) or (neg in stmt_a and pos in stmt_b):
                        # 더 confidence 높은 쪽을 채택, 다른 쪽은 명시 보존.
                        if fa.confidence.aggregate >= fb.confidence.aggregate:
                            winner, loser = fa, fb
                        else:
                            winner, loser = fb, fa
                        contradictions.append({
                            "lens_a": fa.lens_id,
                            "lens_b": fb.lens_id,
                            "conflict": (
                                f"방향성 충돌 ({pos}↔{neg}) — "
                                f"{fa.lens_id}: {stmt_a[:60]} / "
                                f"{fb.lens_id}: {stmt_b[:60]}"
                            ),
                            "resolution": (
                                f"{winner.lens_id} 채택 (confidence "
                                f"{winner.confidence.aggregate:.2f} > "
                                f"{loser.confidence.aggregate:.2f}). 단 "
                                f"{loser.lens_id} 의 입장은 봉합되지 않고 "
                                f"counter_hypothesis 로 노출됨."
                            ),
                        })
                        break
        return contradictions

    # ------------------------------------------------------------------
    # Confidence aggregation (3-axis)
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_confidence(
        findings: list[AnalyticalFinding],
        contradictions: list[dict[str, Any]],
    ) -> ConfidenceProfile:
        if not findings:
            return ConfidenceProfile()
        n = len(findings)
        sd = sum(f.confidence.source_diversity for f in findings) / n
        df = sum(f.confidence.data_freshness for f in findings) / n
        ec = sum(f.confidence.expert_consensus for f in findings) / n
        # 모순 1건당 expert_consensus 0.1 씩 차감 (최소 0.0)
        ec = max(0.0, ec - 0.1 * len(contradictions))
        return ConfidenceProfile(
            source_diversity=round(sd, 3),
            data_freshness=round(df, 3),
            expert_consensus=round(ec, 3),
        )

    # ------------------------------------------------------------------
    # LLM-augmented synthesis (optional, with heuristic fallback)
    # ------------------------------------------------------------------

    async def _llm_synthesize(
        self,
        findings: list[AnalyticalFinding],
        contradictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.config.use_cli_mode:
            raise RuntimeError("CLI mode disabled")
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError("claude CLI not found")

        findings_brief = [
            {
                "lens_id": f.lens_id,
                "answers_question": f.answers_question,
                "claim": f.main_claim.statement[:300],
                "counter_hypothesis": f.counter_hypothesis[:200],
                "confidence": round(f.confidence.aggregate, 2),
            }
            for f in findings
        ]
        prompt = (
            "당신은 종합 판단관 (Synthesis Judge). "
            "여러 렌즈가 산출한 finding 들을 검토해 종합 판단을 만든다.\n\n"
            "절대 규칙:\n"
            "- 모순을 봉합하지 마라. 모순은 contradictions 에 그대로 노출되어 있고 너의 main_judgment 는 어느 쪽을 채택했는지 명시해야 한다.\n"
            "- 반대 가설 (counter_hypothesis) 을 반드시 만들어라. 이게 옳다면 어떤 증거가 추가로 필요한지 (counter_evidence_needed) 도 함께.\n\n"
            f"finding 들 (요약): {json.dumps(findings_brief, ensure_ascii=False)[:2000]}\n\n"
            f"이미 발견된 모순: {json.dumps(contradictions, ensure_ascii=False)[:1000]}\n\n"
            "JSON 만 출력 (다른 텍스트 금지):\n"
            '{"main_judgment":"종합 판단 1~2문장","base_scenario":"기준 시나리오 1문장",'
            '"biggest_uncertainty":"가장 큰 불확실성 1문장","counter_hypothesis":"반대 가설 1~2문장",'
            '"counter_evidence_needed":["반대 가설이 옳다면 필요한 증거 1","증거 2"]}'
        )
        proc = await asyncio.create_subprocess_exec(
            claude_bin, "-p", prompt,
            "--output-format", "text",
            "--model", self.config.model_name,
            "--dangerously-skip-permissions",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        raw = stdout.decode().strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("no JSON in LLM response")
        data = json.loads(match.group())
        # Fill in missing keys with heuristic fallback values.
        heuristic = self._heuristic_synthesize(findings, contradictions)
        for k in ("main_judgment", "base_scenario", "biggest_uncertainty",
                  "counter_hypothesis"):
            if not data.get(k):
                data[k] = heuristic[k]
        if not data.get("counter_evidence_needed"):
            data["counter_evidence_needed"] = heuristic.get(
                "counter_evidence_needed", []
            )
        return data

    @staticmethod
    def _heuristic_synthesize(
        findings: list[AnalyticalFinding],
        contradictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # 가장 confidence 높은 finding 의 claim 을 main_judgment 로.
        top = max(findings, key=lambda f: f.confidence.aggregate)
        # counter_hypothesis 는 *충돌하는* 가장 높은 finding 또는 top 의 자체 counter_hypothesis.
        if contradictions:
            losers = [c for c in contradictions if "채택" in c.get("resolution", "")]
            if losers:
                # 가장 첫 모순의 lens_b 를 반대 가설로 인용.
                first = losers[0]
                ch = (
                    f"{first.get('lens_b')} 입장도 무시할 수 없음 — "
                    f"{first.get('conflict', '')[:120]}"
                )
            else:
                ch = top.counter_hypothesis or "(반대 가설 미산출)"
        else:
            ch = top.counter_hypothesis or "(반대 가설 미산출)"

        biggest_uncertainty = (
            f"{len(contradictions)}건의 렌즈 간 충돌이 미해소"
            if contradictions
            else "데이터 신선도 — 분석 시점 이후 변동 가능성"
        )
        return {
            "main_judgment": top.main_claim.statement[:300],
            "base_scenario": (
                f"{top.lens_id} 가 답한 '{top.answers_question}' 에 대한 결론 채택"
            ),
            "biggest_uncertainty": biggest_uncertainty,
            "counter_hypothesis": ch,
            "counter_evidence_needed": top.counter_required_evidence or [
                "반대 가설을 뒷받침할 1차 출처 추가 수집",
            ],
        }
