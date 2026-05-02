"""Orchestrator -- mode-aware analysis pipeline coordinator (v3.1.0)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from typing import Any, Callable, Coroutine, Optional

from src.archetypes.registry import get_archetype, list_archetypes, select_archetype
from src.config import Config
from src.lens_policy import select_lenses, select_theme
from src.lenses.registry import get_lens, list_lenses
from src.models import (
    AnalysisRequest, AnalysisStrategy, AnalyticalFinding, Claim, ConfidenceProfile,
    Evidence, FullAnalysisResult, JudgmentVerdict,
)
from src.telemetry import RunTelemetry
from src.token_budget import AnalysisMode, TokenBudget, resolve_mode
from src.visual_builder import needs_advanced_visuals
from src.watchlist import WatchlistRegistry, convert_watch_signals
from src.agents.context_analyst import ContextAnalyst
from src.agents.player_analyst import PlayerAnalyst
from src.agents.dynamics_analyst import DynamicsAnalyst
from src.agents.chain_reaction_analyst import ChainReactionAnalyst
from src.agents.scenario_architect import ScenarioArchitect
from src.agents.visual_analyst import VisualAnalyst
from src.agents.report_synthesizer import ReportSynthesizer
from src.agents.quality_inspector import QualityInspector
from src.agents.synthesis_judge import SynthesisJudge
from src.agents.narrative_composer import NarrativeComposer
from src.visual_builder import build_chart_catalog

logger = logging.getLogger(__name__)

VERSION = "v4.0.0"


# v3.4.1 — 봇 프로세스 시작 시점에 git 상태를 캡처해 두 곳에서 표시한다:
#   ① 시작 로그 (tmux/journal 으로 운영자가 즉시 확인)
#   ② /status 명령 응답 (텔레그램에서 어떤 commit 이 돌고 있는지 명시)
# pull 만 하고 재기동을 안 했다면 BUILD_INFO 는 "이미 실행 중인" 코드의 commit 을 가리킨다 —
# 그래야 "v3.4.0 머지했는데 왜 v3.3.0 이 뜨지?" 류 디버깅이 즉시 풀린다.
def _capture_build_info() -> dict:
    """Capture git branch + commit at process start. Static — does not refresh post-start."""
    import subprocess as _sp
    info = {"branch": "?", "commit": "?", "commit_date": "?", "dirty": False}
    try:
        info["branch"] = _sp.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["commit"] = _sp.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["commit_date"] = _sp.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["dirty"] = bool(_sp.check_output(
            ["git", "status", "--porcelain"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip())
    except (OSError, _sp.SubprocessError, _sp.TimeoutExpired):
        # git 미설치 / repo 밖 / 권한 없음 — 모두 "?" 로 graceful degrade.
        pass
    return info


BUILD_INFO = _capture_build_info()

# v3.1.0: legacy keywords map → fast mode (quick mode 와 같은 의미).
QUICK_MODE_KEYWORDS = {"짧게", "간략히", "간략하게", "빠르게", "요약", "간단히", "간단하게"}

StatusCallback = Optional[Callable[[str], Coroutine[Any, Any, None]]]


class Orchestrator:
    """Coordinates the 4-phase analysis pipeline."""

    def __init__(
        self,
        config: Config,
        watchlist_registry: "WatchlistRegistry | None" = None,
    ) -> None:
        self.config = config
        self.context_analyst = ContextAnalyst(config)
        # v3.1.0: legacy persona 인스턴스는 보존하지만 fast/standard 에서는 호출하지 않음.
        # deep 모드에서만 6막 보고서 풍부 데이터 보존을 위해 호출 (FUT-LEGACY-001).
        self.player_analyst = PlayerAnalyst(config)
        self.dynamics_analyst = DynamicsAnalyst(config)
        self.chain_reaction_analyst = ChainReactionAnalyst(config)
        self.scenario_architect = ScenarioArchitect(config)
        self.visual_analyst = VisualAnalyst(config)
        self.report_synthesizer = ReportSynthesizer(config)
        # V3 Step 4 (v2.8.0)
        self.quality_inspector = QualityInspector(config)
        self.synthesis_judge = SynthesisJudge(config)
        # v3.3.0 — freeform editorial pass (Opus 4.7). deep 모드만 호출.
        self.narrative_composer = NarrativeComposer(config)
        # V3 Step 5-B (v2.9.5) — Watchlist Registry. None 이면 watchlist 등록 스킵
        # (단위 테스트 / standalone orchestrator 인스턴스 시 안전).
        self.watchlist_registry = watchlist_registry
        # Counters for gate stats — reset per process. Logged at INFO at end of run.
        self._gate_stats = {
            "gate_1_attempts": 0, "gate_1_passes": 0, "gate_1_retries": 0, "gate_1_partial": 0,
            "gate_2_attempts": 0, "gate_2_passes": 0, "gate_2_retries": 0, "gate_2_partial": 0,
        }
        # v3.1.0: telemetry — 사건당 새 인스턴스를 ``run_analysis`` 가 만든다.
        self.telemetry: Optional[RunTelemetry] = None

    def _wire_telemetry(self) -> None:
        """현재 ``self.telemetry`` 를 모든 BaseAgent 후속에 전파."""
        for agent in (
            self.context_analyst, self.player_analyst, self.dynamics_analyst,
            self.chain_reaction_analyst, self.scenario_architect, self.visual_analyst,
        ):
            agent.telemetry = self.telemetry
        # narrative_composer 는 BaseAgent 가 아니지만 telemetry 속성 보유.
        self.narrative_composer.telemetry = self.telemetry

    @staticmethod
    def _progress_bar(step: int, total: int = 7) -> str:
        """Generate a text progress bar."""
        pct = int(step / total * 100)
        filled = int(step / total * 20)
        bar = "▓" * filled + "░" * (20 - filled)
        return f"{bar} {pct}%"

    @staticmethod
    def _empty_strategy_fallback() -> AnalysisStrategy:
        """LLM 호출 실패 또는 파싱 실패 시 사용할 최소 유효 AnalysisStrategy.

        Anti-pattern #3 (dict 회귀) 방지를 위해 빈 dict 가 아닌 빈 객체로 폴백.
        Pydantic validator 를 통과해야 하므로 core_questions/recommended_lenses 에
        한 항목씩 더미를 채운다.
        """
        return AnalysisStrategy(
            event_type="unknown",
            user_intent="what_happened",
            intent_confidence=0.5,
            core_questions=["사건의 핵심 사실을 파악한다"],
            recommended_lenses=["context"],
            evidence_plan=[],
            report_archetype="six_act_theater",
            section_plan=[],
            visualization_plan=[],
            theme="burgundy_mono",
            legacy_directives={},
        )

    async def _generate_analysis_strategy(
        self,
        event_name: str,
        category: str,
        summary: str,
        mode: AnalysisMode = "standard",
    ) -> AnalysisStrategy:
        """Generate AnalysisStrategy based on the event context.

        v3.1.0: Strategy Planner 프롬프트를 대폭 축소.
        LLM 은 ``event_type`` / ``user_intent`` / ``intent_confidence`` /
        ``core_questions`` / ``complexity`` (선택) 만 출력.
        - archetype 선택은 ``select_archetype()`` 매트릭스가 최종 결정자.
        - theme 선택은 ``lens_policy.select_theme()`` (코드 규칙).
        - recommended_lenses 는 ``lens_policy.select_lenses()`` 가 mode 기반으로 결정.
        - per-agent directive (legacy_directives) 는 더 이상 LLM 으로 생성하지 않음.
        """
        intent_confidence_default = 0.5
        prompt = (
            "당신은 분석 전략 기획자. 아래 사건에 대해 4가지만 출력.\n\n"
            f"사건명: {event_name}\n"
            f"분류: {category}\n"
            f"요약: {summary[:400]}\n\n"
            "출력 항목:\n"
            "1) event_type — 한 단어 (financial/tech/accident/policy/geopolitical/industry/general 중 가장 가까운 것)\n"
            "2) user_intent — 7종 중 1: what_happened|why_happened|who_benefits|where_spreads|"
            "what_next|where_vulnerable|what_to_do\n"
            "3) intent_confidence — 0.0~1.0\n"
            "4) core_questions — 이 사건이 답해야 할 핵심 질문 1~4개\n\n"
            "JSON 만 출력 (다른 텍스트 금지):\n"
            '{"event_type":"...","user_intent":"...",'
            '"intent_confidence":0.0,"core_questions":["q1","q2"]}\n'
        )

        try:
            claude_bin = shutil.which("claude")
            if claude_bin is None:
                logger.warning("[orchestrator] claude CLI not found; using empty strategy")
                return self._empty_strategy_fallback()

            cmd = [
                claude_bin,
                "-p", prompt,
                "--output-format", "text",
                "--model", self.config.model_name_light,
                "--dangerously-skip-permissions",
            ]

            llm_start = time.time()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            llm_elapsed_ms = int((time.time() - llm_start) * 1000)

            if proc.returncode != 0:
                logger.warning("[orchestrator] Strategy generation failed; using empty strategy")
                return self._empty_strategy_fallback()

            raw = stdout.decode().strip()
            if self.telemetry is not None:
                self.telemetry.record_llm_call(
                    agent_name="strategy_planner",
                    input_chars=len(prompt),
                    output_chars=len(raw),
                    elapsed_ms=llm_elapsed_ms,
                )

            import re
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[orchestrator] No JSON in strategy response; using empty strategy")
                return self._empty_strategy_fallback()

            raw_dict = json.loads(match.group())
            event_type = (raw_dict.get("event_type") or "general").strip().lower()
            user_intent = (raw_dict.get("user_intent") or "what_happened").strip()
            intent_confidence = float(
                raw_dict.get("intent_confidence", intent_confidence_default)
            )
            core_questions = list(raw_dict.get("core_questions") or [])
            core_questions = [q.strip() for q in core_questions if q and q.strip()]
            if not core_questions:
                core_questions = [f"{event_name} 의 핵심 사실을 파악한다"]

            # Lens 결정은 코드 규칙으로. 미사용 LLM 추천은 우선순위 보정에만 활용.
            recommended_lenses = select_lenses(
                event_type=event_type,
                user_intent=user_intent,
                mode=mode,
            )
            theme = select_theme(event_type)

            strategy = AnalysisStrategy(
                event_type=event_type,
                user_intent=user_intent,  # type: ignore[arg-type]
                intent_confidence=max(0.0, min(1.0, intent_confidence)),
                core_questions=core_questions[:5],
                recommended_lenses=recommended_lenses,
                report_archetype="six_act_theater",  # matrix 가 곧 덮어씀
                theme=theme,
                legacy_directives={},
            )

            logger.info(
                "[orchestrator] AnalysisStrategy generated for: %s\n"
                "  mode: %s\n"
                "  user_intent: %s (confidence=%.2f)\n"
                "  event_type: %s\n"
                "  core_questions: %s\n"
                "  recommended_lenses: %s (cap by mode)\n"
                "  theme: %s",
                event_name, mode,
                strategy.user_intent, strategy.intent_confidence,
                strategy.event_type,
                strategy.core_questions,
                strategy.recommended_lenses,
                strategy.theme,
            )
            return strategy

        except Exception as e:
            logger.warning(
                "[orchestrator] Strategy generation error: %s; using empty strategy", e
            )
            return self._empty_strategy_fallback()

    # ------------------------------------------------------------------
    # V3 Step 4 — Findings wrapper (v2 analyses → AnalyticalFinding list)
    # ------------------------------------------------------------------
    #
    # Wraps the existing ContextAnalysis / PlayerAnalysis / ... outputs into
    # AnalyticalFinding instances so Synthesis Judge + Gate 2 can operate on a
    # unified shape. ContextAnalysis.sources are converted to Evidence (real URLs).
    # Lenses without a real source get a single ``model_inference`` evidence with
    # quote_or_data marking the limitation explicitly.
    #
    # Step 5 (Lens Pool) will replace this wrapper — lens runners will produce
    # AnalyticalFinding directly.

    @staticmethod
    def _confidence_from_score(
        score: float, sources_count: int = 0
    ) -> ConfidenceProfile:
        """Convert legacy ``confidence_score: float`` (deprecated) to ConfidenceProfile."""
        # source_diversity: linear ramp on independent source count, capped at 5.
        sd = min(1.0, max(0.0, sources_count / 5.0))
        # data_freshness: web-search era assumption — moderate-to-high.
        df = 0.7
        # expert_consensus: legacy scalar maps here as a rough proxy.
        ec = max(0.0, min(1.0, score))
        return ConfidenceProfile(
            source_diversity=round(sd, 3),
            data_freshness=round(df, 3),
            expert_consensus=round(ec, 3),
        )

    @staticmethod
    def _make_evidence_pool(
        result: FullAnalysisResult,
    ) -> tuple[list[Evidence], list[str]]:
        """Build a shared Evidence pool from result.context.sources + lens-level fallback.

        Returns (evidence_list, evidence_ids). Always returns at least one Evidence
        so that Claim validators (evidence_ids min_length=1) never fail at wrap time.
        """
        evs: list[Evidence] = []
        if result.context and result.context.sources:
            for i, src in enumerate(result.context.sources, 1):
                # source can be a URL or free-text — store as source_url if it looks like URL.
                if src.startswith(("http://", "https://")):
                    ev = Evidence(
                        evidence_id=f"E-{i:03d}",
                        source_url=src,
                        quote_or_data=src,
                        reliability="secondary",
                        timestamp=result.context.date or "",
                    )
                else:
                    ev = Evidence(
                        evidence_id=f"E-{i:03d}",
                        source_url="",
                        quote_or_data=src[:200],
                        reliability="secondary",
                        timestamp=result.context.date or "",
                    )
                evs.append(ev)
        if not evs:
            # Fallback: one model_inference evidence so claims can still validate.
            evs.append(Evidence(
                evidence_id="E-INF-001",
                source_url="",
                quote_or_data="1차 출처 미수집 — 모델 추론 기반",
                reliability="model_inference",
                timestamp="",
            ))
        return evs, [e.evidence_id for e in evs]

    @staticmethod
    def _assign_question(
        strategy: AnalysisStrategy | None, lens_id: str, idx: int
    ) -> str:
        """Round-robin assignment of strategy.core_questions to findings.
        If strategy is None or core_questions empty, returns generic placeholder.
        """
        if strategy is None or not strategy.core_questions:
            return f"({lens_id} 가 답변하는 질문 미지정)"
        return strategy.core_questions[idx % len(strategy.core_questions)]

    def _wrap_findings(
        self, result: FullAnalysisResult
    ) -> list[AnalyticalFinding]:
        """Wrap available v2 analyses into AnalyticalFinding list."""
        if result.strategy is None:
            logger.warning("[orchestrator] _wrap_findings called with no strategy")
            return []
        evidence_pool, evidence_ids = self._make_evidence_pool(result)
        findings: list[AnalyticalFinding] = []
        idx = 0

        def _add(
            lens_id: str,
            statement: str,
            counter_hyp: str,
            score: float,
            claim_type: str = "inference",
        ) -> None:
            nonlocal idx
            statement = (statement or "").strip()
            if not statement:
                return
            try:
                claim = Claim(
                    claim_id=f"C-{lens_id[:6]}-{idx + 1:03d}",
                    statement=statement[:500],
                    claim_type=claim_type,  # type: ignore[arg-type]
                    evidence_ids=evidence_ids,
                )
            except Exception as e:
                # Anti-pattern #4 guard — must NOT silently downgrade by passing empty
                # evidence. If we can't build a valid claim, log and skip the finding.
                logger.warning(
                    "[orchestrator] Skipping finding for lens=%s; claim invalid: %s",
                    lens_id, e,
                )
                return
            findings.append(AnalyticalFinding(
                finding_id=f"F-{lens_id}-{idx + 1:03d}",
                lens_id=lens_id,
                answers_question=self._assign_question(result.strategy, lens_id, idx),
                main_claim=claim,
                evidence=evidence_pool,
                confidence=self._confidence_from_score(
                    score,
                    len(result.context.sources) if result.context else 0,
                ),
                counter_hypothesis=counter_hyp,
            ))
            idx += 1

        if result.context:
            _add(
                "context_analyst",
                result.context.summary,
                "",
                result.context.confidence_score,
                claim_type="fact",
            )
        if result.players:
            _add(
                "player_analyst",
                result.players.power_dynamics or result.players.summary,
                "",
                result.players.confidence_score,
                claim_type="inference",
            )
        if result.dynamics:
            _add(
                "dynamics_analyst",
                result.dynamics.key_insight or result.dynamics.summary,
                result.dynamics.counter_view or "",
                result.dynamics.confidence_score,
                claim_type="inference",
            )
        if result.chain_reaction:
            chain_summary = result.chain_reaction.worst_case
            if not chain_summary and result.chain_reaction.chain:
                chain_summary = " → ".join(
                    s.get("title", "") for s in result.chain_reaction.chain[:5]
                )
            _add(
                "chain_reaction_analyst",
                chain_summary,
                "",
                result.chain_reaction.confidence_score,
                claim_type="prediction",
            )
        if result.scenarios:
            sc_summary = (
                result.scenarios.base_case_summary or result.scenarios.summary
            )
            _add(
                "scenario_architect",
                sc_summary,
                "",
                result.scenarios.confidence_score,
                claim_type="prediction",
            )
        return findings

    # ------------------------------------------------------------------
    # V3 Step 5-A — Lens Pool execution
    # ------------------------------------------------------------------
    #
    # AnalysisStrategy.recommended_lenses 의 lens_id 들을 registry 로 resolve 해서 sequential
    # 실행 (Anti-pattern: 병렬 실행 금지 — 1GB VM 메모리 보호, FUT-001 까지 보류).
    # 사건당 최대 4개 (Anti-pattern #6 cap). 각 lens 가 산출한 finding 을 list 로 누적.

    LENS_CAP_PER_EVENT: int = 4

    async def _run_lenses(
        self,
        result: FullAnalysisResult,
        evidence: list[Evidence],
        status_callback: StatusCallback,
    ) -> list[AnalyticalFinding]:
        if result.strategy is None:
            return []
        requested = list(result.strategy.recommended_lenses or [])
        # 등록된 lens 만 통과 + cap 적용 (Anti-pattern #6).
        registered = set(list_lenses())
        valid = [lid for lid in requested if lid in registered]
        skipped = [lid for lid in requested if lid not in registered]
        if skipped:
            logger.warning(
                "[orchestrator] Skipping unregistered lens IDs: %s "
                "(registered: %s)", skipped, list(registered),
            )
        if len(valid) > self.LENS_CAP_PER_EVENT:
            logger.warning(
                "[orchestrator] Lens cap exceeded — strategy requested %d, "
                "truncating to %d (Anti-pattern #6)",
                len(valid), self.LENS_CAP_PER_EVENT,
            )
            valid = valid[: self.LENS_CAP_PER_EVENT]

        if not valid:
            logger.info("[orchestrator] No registered lenses to run")
            return []

        event_meta = {
            "event_name": result.context.event_name if result.context else "",
            "summary": result.context.summary if result.context else "",
            "category": result.context.category if result.context else "",
        }
        core_questions = result.strategy.core_questions or []
        directives = result.strategy.legacy_directives or {}

        await self._notify(
            f"🔬 Lens 풀 실행: {valid} ({len(valid)}/{self.LENS_CAP_PER_EVENT} cap)",
            status_callback,
        )

        lens_findings: list[AnalyticalFinding] = []
        for idx, lens_id in enumerate(valid):
            lens = get_lens(lens_id, self.config)
            answers_q = (
                core_questions[idx % len(core_questions)] if core_questions else ""
            )
            # Reuse legacy directive when key matches (transitional shim).
            directive = directives.get(lens_id, "")
            try:
                produced = await lens.run(
                    evidence=evidence,
                    directive=directive,
                    event_meta=event_meta,
                    answers_question=answers_q,
                )
                logger.info(
                    "[orchestrator] lens=%s produced %d finding(s)",
                    lens_id, len(produced),
                )
                lens_findings.extend(produced)
            except Exception as e:
                logger.warning(
                    "[orchestrator] lens=%s execution error: %s; skipping",
                    lens_id, e,
                )
        return lens_findings

    # ------------------------------------------------------------------
    # V3 Step 4 — Gate runner (with retry + partial-analysis alert)
    # ------------------------------------------------------------------

    async def _run_gate_with_retries(
        self,
        gate_name: str,
        gate_fn,
        regenerate_fn,
        status_callback: "StatusCallback",
        max_retries: int = 2,
    ) -> tuple[bool, str]:
        """Run a quality gate with retries. On final failure, emit partial-analysis alert.

        Args:
            gate_name: e.g. "gate_1" or "gate_2" (used in stats + alert text).
            gate_fn: async () -> (passed, reason).
            regenerate_fn: async () -> None — called between retries to refresh inputs.
        Returns:
            (final_passed, final_reason). Even if False, caller should continue with
            partial output (Anti-pattern #7: never silently bypass).
        """
        attempts_key = f"{gate_name}_attempts"
        passes_key = f"{gate_name}_passes"
        retries_key = f"{gate_name}_retries"
        partial_key = f"{gate_name}_partial"

        self._gate_stats[attempts_key] += 1
        passed, reason = await gate_fn()
        if passed:
            self._gate_stats[passes_key] += 1
            return True, reason

        for attempt in range(1, max_retries + 1):
            self._gate_stats[retries_key] += 1
            logger.info(
                "[quality_inspector] %s failed (%s). retry %d/%d",
                gate_name, reason, attempt, max_retries,
            )
            try:
                await regenerate_fn()
            except Exception as e:
                logger.warning("[orchestrator] %s regenerate error: %s", gate_name, e)
            self._gate_stats[attempts_key] += 1
            passed, reason = await gate_fn()
            if passed:
                self._gate_stats[passes_key] += 1
                return True, reason

        self._gate_stats[partial_key] += 1
        await self._notify(
            f"⚠️ 부분 분석 완료. {gate_name} 실패 ({reason})",
            status_callback,
        )
        return False, reason

    async def _notify(
        self, message: str, status_callback: StatusCallback
    ) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if status_callback:
            await status_callback(message)

    def _build_text_report(self, result: FullAnalysisResult) -> str:
        """Build a clean text summary for Telegram (without glossary)."""
        lines: list[str] = []

        event_name = ""
        if result.context:
            event_name = result.context.event_name or result.context.event_name_en
        lines.append(f"<{event_name or 'Event Analysis'}>")
        lines.append("")

        if result.context:
            lines.append("[상황인식]")
            lines.append("")
            lines.append(result.context.summary)
            lines.append("")
            for fig in result.context.key_figures[:6]:
                label = fig.get("label", "")
                value = fig.get("value", "")
                context = fig.get("context", "")
                ctx_str = f" ({context})" if context else ""
                lines.append(f" -> {label}: {value}{ctx_str}")
            lines.append("")

        if result.players:
            lines.append("[이해관계자]")
            lines.append("")
            for i, p in enumerate(result.players.players[:8], 1):
                name = p.get("name", "")
                role = p.get("role_tag", "")
                lines.append(f"{i}) {name} : {role}")
            lines.append("")

        if result.dynamics:
            lines.append("[구조 및 상호작용]")
            lines.append("")
            lines.append(f"a. 프레임: {result.dynamics.framework}")
            lines.append(f"b. 긴장: {result.dynamics.core_tension}")
            lines.append(f"c. 통찰: {result.dynamics.key_insight}")
            lines.append("")

        if result.chain_reaction:
            lines.append("[연쇄반응]")
            lines.append("")
            for step in result.chain_reaction.chain[:12]:
                title = step.get("title", "")
                desc = step.get("description", "")
                if desc:
                    lines.append(f"→ {title}")
                else:
                    lines.append(f"→ {title}")
            lines.append("")

        if result.scenarios:
            lines.append("[향후 시나리오]")
            lines.append("")
            circled = ["①", "②", "③", "④"]
            for i, sc in enumerate(result.scenarios.scenarios[:4]):
                c = circled[i] if i < len(circled) else f"{i+1}."
                name = sc.get("name", "")
                prob = sc.get("probability", "")
                lines.append(f"{c} {name} ({prob})")
            lines.append("")

        if result.scenarios and result.scenarios.watch_signals:
            lines.append("[지켜봐야 할 시그널]")
            lines.append("")
            for ws in result.scenarios.watch_signals[:5]:
                icon = ws.get("icon", "●")
                signal = ws.get("signal", "")
                lines.append(f"{icon} {signal}")
            lines.append("")

        if result.context and result.context.sources:
            lines.append(f"출처: {', '.join(result.context.sources[:8])}")

        return "\n".join(lines)

    def _build_glossary_text(self, result: FullAnalysisResult) -> str:
        """Build glossary as a separate text for Telegram."""
        all_terms: list[dict] = []
        for section in [result.context, result.players, result.dynamics, result.chain_reaction, result.scenarios]:
            if section and hasattr(section, "glossary") and section.glossary:
                all_terms.extend(section.glossary)
        seen: set[str] = set()
        unique_terms: list[dict] = []
        for t in all_terms:
            term = t.get("term", "")
            if term and term not in seen:
                seen.add(term)
                unique_terms.append(t)
        if not unique_terms:
            return ""
        lines: list[str] = ["[용어 정의]", ""]
        for t in unique_terms:
            lines.append(f"  {t.get('term', '')} : {t.get('definition', '')}")
        return "\n".join(lines)

    async def run_analysis(
        self,
        event_description: str,
        chat_id: int,
        status_callback: StatusCallback = None,
        mode: AnalysisMode | None = None,
    ) -> FullAnalysisResult:
        """v4.0.0 Tier 4: 2-call unified pipeline.

        Phase 1 — ContextAnalyst (Sonnet 4.6, 웹검색): 사실/타임라인/출처 수집.
        Phase 2 — UnifiedComposer (Opus 4.7): 행위자/구조/시나리오/모순 분석 +
                  보고서 본문 작성을 *단일 LLM 호출*로 모두 수행.
        Phase 3 — HTML 렌더 + Cloudflare Pages 배포.
        Phase 4 — composed_report.watch_signals → SQLite Watchlist.

        legacy 멀티 에이전트 (player/dynamics/chain_reaction/scenario/synthesis_judge/
        quality_inspector/visual_analyst/lens_pool) 는 v4.0.0 부터 호출 안 함.
        모듈 자체는 보존 (향후 정리 commit 에서 제거).
        """
        from src.models import ComposedReport, ComposedSection

        start_time = time.time()

        if mode is None:
            mode = resolve_mode(event_description)

        # Telemetry per-run.
        self.telemetry = RunTelemetry(mode=mode)
        self._wire_telemetry()

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
            mode=mode,
        )
        result = FullAnalysisResult(request=request)

        mode_label = {"fast": " ⚡fast", "deep": " 🔬deep"}.get(mode, " 🟢standard")

        # In fast mode, downgrade context_analyst to light model for speed.
        original_context_model = None
        if mode == "fast":
            original_context_model = self.context_analyst.model_name
            self.context_analyst.model_name = self.config.model_name_light

        # -- Phase 1: 상황 분석관 (사실 수집 + 웹 검색) --
        await self._notify(
            f"🔍 상황 분석관: \"{event_description}\" 사실 수집 중.\n"
            f"Analysis Team {VERSION}{mode_label}",
            status_callback,
        )
        stage = self.telemetry.stage_start("context_analyst")
        result.context = await self.context_analyst.analyze(request)
        self.telemetry.stage_end(stage)

        event_name = result.context.event_name or event_description[:30]
        self.telemetry.event_name = event_name
        await self._notify(
            f"📋 상황 분석관: \"{event_name}\" 사실 정리 완료.\n"
            f"  · 사건 분류: {result.context.category}\n"
            f"  · 타임라인 {len(result.context.timeline)}건, "
            f"핵심 지표 {len(result.context.key_figures)}건, "
            f"출처 {len(result.context.sources)}건\n"
            f"{self._progress_bar(1, total=2)}",
            status_callback,
        )

        # -- Phase 2: UnifiedComposer (Opus 4.7) — 분석 + 작성 단일 호출 --
        await self._notify(
            "✍️ 편집장 (Opus 4.7): 행위자/구조/시나리오/모순 분석 + 보고서 작성 (단일 호출)",
            status_callback,
        )
        stage = self.telemetry.stage_start("unified_composer")
        try:
            result.composed_report = await self.narrative_composer.compose_unified(
                result.context, mode=mode,
            )
        except Exception as e:
            logger.warning("[orchestrator] unified_composer error: %s", e)
            result.composed_report = None
        self.telemetry.stage_end(stage)

        # composer 실패 시 graceful fallback — minimal report from context only
        if result.composed_report is None:
            logger.warning("[orchestrator] composer failed; emitting minimal fallback")
            result.composed_report = ComposedReport(
                headline=event_name,
                deck=(result.context.summary or "")[:200],
                sections=[ComposedSection(
                    heading="요약",
                    prose=result.context.summary or "(분석 실패 — composer 호출 오류)",
                )],
                confidence_score=0.0,
                confidence_summary="composer 호출 실패. 사실 자료만 표시.",
            )
            self.telemetry.record_llm_skip(
                "unified_composer", "failed → minimal fallback",
            )

        n_sections = len(result.composed_report.sections)
        n_signals = len(result.composed_report.watch_signals)
        n_contradictions = len(result.composed_report.contradictions)
        await self._notify(
            f"✍️ 보고서 완성: {n_sections}개 섹션, "
            f"감시 신호 {n_signals}건, 모순 {n_contradictions}건 명시.\n"
            f"  · 신뢰도: {result.composed_report.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(2, total=2)}",
            status_callback,
        )

        # -- Phase 3: HTML 렌더링 + Cloudflare Pages 배포 --
        result.total_duration_seconds = time.time() - start_time

        # composer 산출 → executive_summary (markdown/index 공통 텍스트로 사용).
        result.executive_summary = (
            result.composed_report.deck or result.composed_report.headline or ""
        )

        # Theme: code-rule via lens_policy.select_theme — mono 2종만 emit
        result.report_theme = select_theme(result.context.category or "general")
        archetype = get_archetype("freeform_essay")
        logger.info(
            "[orchestrator] Tier 4 routing — theme=%s, archetype=%s, mode=%s",
            result.report_theme, archetype.archetype_id, mode,
        )

        stage = self.telemetry.stage_start("report_synthesis")
        report_url = await self.report_synthesizer.synthesize(
            result, theme=result.report_theme, archetype=archetype,
        )
        self.telemetry.stage_end(stage)
        result.report_url = report_url

        # -- Phase 4: Watchlist 등록 (composed_report.watch_signals 에서) --
        if self.watchlist_registry is not None and result.composed_report.watch_signals:
            try:
                report_id = ""
                if result.report_path:
                    import os as _os
                    report_id = _os.path.splitext(_os.path.basename(result.report_path))[0]
                signals = convert_watch_signals(
                    scenario_signals=result.composed_report.watch_signals,
                    parent_report_url=result.report_url or "",
                    parent_report_id=report_id,
                    parent_chat_id=request.chat_id,
                )
                inserted = sum(
                    1 for sig in signals if self.watchlist_registry.register(sig)
                )
                logger.info(
                    "[orchestrator] Watchlist: %d/%d signals registered (chat=%d)",
                    inserted, len(signals), request.chat_id,
                )
                if inserted:
                    await self._notify(
                        f"📒 감시 신호 {inserted}건 DB 등록. /watchlist 로 확인.",
                        status_callback,
                    )
            except Exception as e:
                logger.warning("[orchestrator] Watchlist register error: %s", e)

        # Restore model if downgraded for fast mode.
        if original_context_model is not None:
            self.context_analyst.model_name = original_context_model

        # Gate stats logging (변경 없음).
        s = self._gate_stats
        for g in ("gate_1", "gate_2"):
            attempts = s[f"{g}_attempts"]
            passes = s[f"{g}_passes"]
            retries = s[f"{g}_retries"]
            partial = s[f"{g}_partial"]
            pass_rate = (passes / attempts * 100.0) if attempts else 0.0
            retry_rate = (retries / attempts * 100.0) if attempts else 0.0
            logger.info(
                "[quality_inspector] %s stats: attempts=%d passes=%d retries=%d "
                "partial=%d (pass_rate=%.1f%% retry_rate=%.1f%%)",
                g, attempts, passes, retries, partial, pass_rate, retry_rate,
            )

        # Telemetry summary.
        if self.telemetry is not None:
            self.telemetry.log_summary()
            # Soft warning if budget exceeded.
            if self.telemetry.total_llm_calls > budget.max_llm_calls:
                logger.warning(
                    "[telemetry] LLM call budget exceeded: %d > %d (mode=%s). "
                    "Consider reviewing per-step decisions.",
                    self.telemetry.total_llm_calls, budget.max_llm_calls, mode,
                )

        return result
