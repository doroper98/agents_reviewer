"""Token-efficiency telemetry (v3.1.0).

분석 1건당 LLM 호출 수, 입력/출력 char 길이, 단계별 elapsed time, 모드/렌즈/스킵된
에이전트를 기록한다. 종료 시 ``log_summary()`` 가 INFO 로그로 efficiency summary 를 남긴다.

본 모듈은 process-local. 텔레그램 봇 멀티-요청 환경에서는 사건당 ``RunTelemetry`` 인스턴스를
새로 만들어 사용 (orchestrator 가 책임).

v5.2.14 — 차트 type usage 추적 추가 (chart starvation 회귀 방지, 캔들 회귀 교훈).
``emitted_chart_types`` 와 ``record_chart_types()`` 가 보고서당 emit 된 type 분포를
기록. ``src/visual/usage_log.py`` 가 영구 JSONL 로 누적 저장.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    """단일 LLM 호출 기록."""

    agent_name: str
    input_chars: int
    output_chars: int
    elapsed_ms: int


@dataclass
class StageTiming:
    """단계별 시작/끝 타임스탬프."""

    name: str
    start_ts: float
    end_ts: Optional[float] = None

    @property
    def elapsed_ms(self) -> int:
        if self.end_ts is None:
            return 0
        return int((self.end_ts - self.start_ts) * 1000)


@dataclass
class RunTelemetry:
    """한 분석 사건의 telemetry 레지스트리.

    Orchestrator 와 각 에이전트가 본 인스턴스를 공유한다. 종료 시 ``log_summary()`` 호출.
    """

    mode: str = "standard"
    event_name: str = ""
    selected_lenses: list[str] = field(default_factory=list)
    skipped_agents: list[str] = field(default_factory=list)
    skipped_llm_steps: list[str] = field(default_factory=list)
    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    stages: list[StageTiming] = field(default_factory=list)
    emitted_chart_types: list[str] = field(default_factory=list)
    start_ts: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Recording API
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        agent_name: str,
        input_chars: int,
        output_chars: int,
        elapsed_ms: int,
    ) -> None:
        self.llm_calls.append(LLMCallRecord(
            agent_name=agent_name,
            input_chars=input_chars,
            output_chars=output_chars,
            elapsed_ms=elapsed_ms,
        ))

    def record_skip(self, agent_name: str, reason: str = "") -> None:
        tag = f"{agent_name}" + (f" ({reason})" if reason else "")
        self.skipped_agents.append(tag)

    def record_llm_skip(self, step_name: str, reason: str = "") -> None:
        tag = f"{step_name}" + (f" ({reason})" if reason else "")
        self.skipped_llm_steps.append(tag)

    def stage_start(self, name: str) -> StageTiming:
        st = StageTiming(name=name, start_ts=time.time())
        self.stages.append(st)
        return st

    def stage_end(self, stage: StageTiming) -> None:
        stage.end_ts = time.time()

    def record_chart_types(self, chart_types: list[str]) -> None:
        """Composer 가 emit 한 chart type 목록 누적.

        Orchestrator 가 composed_report 의 모든 section.charts 순회 후 1회 호출.
        Starvation alarm 의 SSOT — type 별 0회 감지 시 ``usage_log`` 가 경고.
        """
        self.emitted_chart_types.extend(chart_types)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @property
    def total_llm_calls(self) -> int:
        return len(self.llm_calls)

    @property
    def total_input_chars(self) -> int:
        return sum(c.input_chars for c in self.llm_calls)

    @property
    def total_output_chars(self) -> int:
        return sum(c.output_chars for c in self.llm_calls)

    @property
    def total_duration_ms(self) -> int:
        return int((time.time() - self.start_ts) * 1000)

    def log_summary(self) -> None:
        """INFO 레벨 효율 요약. 보고서 생성 완료 후 orchestrator 가 호출."""
        per_call_avg_in = (
            self.total_input_chars // self.total_llm_calls
            if self.total_llm_calls else 0
        )
        per_call_avg_out = (
            self.total_output_chars // self.total_llm_calls
            if self.total_llm_calls else 0
        )
        stage_lines = [
            f"    · {s.name}: {s.elapsed_ms} ms"
            for s in self.stages if s.end_ts is not None
        ]
        agent_lines = [
            f"    · {c.agent_name}: in={c.input_chars}c out={c.output_chars}c "
            f"({c.elapsed_ms} ms)"
            for c in self.llm_calls
        ]
        chart_dist = Counter(self.emitted_chart_types)
        chart_line = ", ".join(
            f"{t}={n}" for t, n in chart_dist.most_common()
        ) or "(none)"
        logger.info(
            "[telemetry] efficiency summary\n"
            "  event: %s\n"
            "  mode: %s\n"
            "  selected_lenses: %s\n"
            "  skipped_agents: %s\n"
            "  skipped_llm_steps: %s\n"
            "  total_llm_calls: %d\n"
            "  total_input_chars: %d (avg/call=%d)\n"
            "  total_output_chars: %d (avg/call=%d)\n"
            "  total_duration_ms: %d\n"
            "  chart_types: %s\n"
            "  llm_calls:\n%s\n"
            "  stages:\n%s",
            self.event_name or "(unknown)",
            self.mode,
            self.selected_lenses or "(none)",
            self.skipped_agents or "(none)",
            self.skipped_llm_steps or "(none)",
            self.total_llm_calls,
            self.total_input_chars, per_call_avg_in,
            self.total_output_chars, per_call_avg_out,
            self.total_duration_ms,
            chart_line,
            "\n".join(agent_lines) or "    (none)",
            "\n".join(stage_lines) or "    (none)",
        )
