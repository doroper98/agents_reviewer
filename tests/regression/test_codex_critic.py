"""V6 Phase V6-1 — CodexCritic 외부 경로 회귀 (T-C1/T-C2/T-C3).

REFACTOR_V6_PLAN.md §4.2. codex CLI 호출은 *모킹* (CI 결정적) — 실연동은 VM
수동 1회 (DoD). 검증 대상:
  T-C1  headless 호출·JSON 파싱·절단복구 (모킹된 codex stdout)
  T-C2  graceful degrade — 미설치/인증실패/한도/timeout/flag_off → skip → 발행
  T-C3  측정 hook — 호출수·latency·degrade 사유 JSONL 적립

모킹 전략: ``_resolve_bin`` 과 ``_call_codex_cli`` 를 인스턴스에서 교체한다
(실제 subprocess/PATH 의존 제거).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.agents.codex_critic import CodexCritic
from src.config import Config
from src.models import ComposedReport, ComposedSection, ContextAnalysis


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------


def _make_config(**overrides) -> Config:
    base = dict(enable_codex_critic=True, codex_bin="codex")
    base.update(overrides)
    return Config(_env_file=None, **base)


def _make_report() -> ComposedReport:
    return ComposedReport(
        headline="27년 만의 PC 칩 RTX 스파크",
        deck="엔비디아가 타이베이에서 공개",
        sections=[
            ComposedSection(heading="발표 요지", prose="베라 루빈 보드 한 장에 부품 130만 개"),
        ],
    )


def _make_context() -> ContextAnalysis:
    return ContextAnalysis(
        event_name="NVIDIA GTC Taipei",
        date="2026-06-01",
        summary="젠슨 황 키노트",
        sources=["https://nvidianews.nvidia.com/"],
    )


def _critic_with_stub(config: Config, *, bin_path="/usr/bin/codex", call_stub=None) -> CodexCritic:
    critic = CodexCritic(config)
    critic._resolve_bin = lambda: bin_path  # type: ignore[method-assign]
    if call_stub is not None:
        critic._call_codex_cli = call_stub  # type: ignore[method-assign]
    return critic


def _stub_returning(stdout: str, stderr: str = "", returncode: int = 0, elapsed_ms: int = 42):
    async def _stub(bin_path, prompt):  # noqa: ANN001
        return stdout, stderr, returncode, elapsed_ms
    return _stub


def _run(coro):
    return asyncio.run(coro)


_VALID_VERDICT = json.dumps(
    {
        "verdict_status": "violations",
        "claims": [
            {
                "location": "headline",
                "error_class": "unsourced_number",
                "quote": "27년 만의 PC 칩",
                "evidence_conflict": "공식 표현은 '30년'. '27년 만'은 출처에 없음.",
                "source_urls": ["https://blogs.nvidia.com/"],
                "fix_instruction": "'27년 만'을 '30년 기술'로 교정.",
                "severity": "high",
            }
        ],
        "cited_urls": ["https://blogs.nvidia.com/"],
    },
    ensure_ascii=False,
)


# --------------------------------------------------------------------------
# T-C1 — headless 호출·파싱·절단복구
# --------------------------------------------------------------------------


def test_parse_valid_verdict() -> None:
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(_VALID_VERDICT))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.verdict_status == "violations"
    assert v.violation_count == 1
    assert v.claims[0].error_class == "unsourced_number"
    assert v.is_actionable
    assert v.latency_ms == 42
    assert v.model_label == "OpenAI Codex"
    assert not v.truncation_repaired


def test_parse_verdict_wrapped_in_code_fence() -> None:
    fenced = f"여기 결과입니다:\n```json\n{_VALID_VERDICT}\n```\n"
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(fenced))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.violation_count == 1


def test_truncation_recovery() -> None:
    # 마지막 claim 이 절단된 stdout — _repair_truncated_json 으로 복구.
    truncated = _VALID_VERDICT[: _VALID_VERDICT.rindex("]")] + ', {"location":"deck"'
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(truncated))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.truncation_repaired is True
    # 절단된 부분 claim 은 드롭, 완결된 1건만 남는다.
    assert v.violation_count == 1


def test_clean_verdict_parses() -> None:
    clean = json.dumps({"verdict_status": "clean", "claims": []})
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(clean))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.verdict_status == "clean"
    assert not v.is_actionable
    assert not v.skipped


def test_ungrounded_claim_dropped() -> None:
    # AP-V6-8 — evidence_conflict 없는 claim 은 드롭, 근거 있는 것만 살린다.
    mixed = json.dumps(
        {
            "claims": [
                {  # 근거 없음 → 드롭
                    "location": "deck",
                    "error_class": "causal_overreach",
                    "quote": "직격탄",
                    "evidence_conflict": "",
                    "fix_instruction": "완화",
                    "severity": "low",
                },
                {  # 근거 있음 → 유지
                    "location": "headline",
                    "error_class": "unsourced_number",
                    "quote": "27년 만",
                    "evidence_conflict": "출처는 30년",
                    "fix_instruction": "교정",
                    "severity": "high",
                },
            ]
        },
        ensure_ascii=False,
    )
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(mixed))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.violation_count == 1
    assert v.claims[0].location == "headline"


def test_unparseable_stdout_degrades() -> None:
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning("총체적 난국, JSON 아님"))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped is True
    assert v.skip_reason == "parse_failed"


# --------------------------------------------------------------------------
# T-C2 — graceful degrade 5경로 (모두 단일패스로 발행 가능)
# --------------------------------------------------------------------------


def test_degrade_flag_off() -> None:
    critic = CodexCritic(_make_config(enable_codex_critic=False))
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "flag_off"


def test_degrade_codex_not_found() -> None:
    critic = CodexCritic(_make_config())
    critic._resolve_bin = lambda: None  # type: ignore[method-assign]
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "codex_not_found"


def test_degrade_auth_failed() -> None:
    stub = _stub_returning("", stderr="Error: 401 Unauthorized (not logged in)", returncode=1)
    critic = _critic_with_stub(_make_config(), call_stub=stub)
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "auth_failed"


def test_degrade_rate_limited() -> None:
    stub = _stub_returning("", stderr="429 Too Many Requests: usage limit reached", returncode=1)
    critic = _critic_with_stub(_make_config(), call_stub=stub)
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "rate_limited"


def test_degrade_generic_error() -> None:
    stub = _stub_returning("", stderr="segfault somewhere", returncode=139)
    critic = _critic_with_stub(_make_config(), call_stub=stub)
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "codex_error"


def test_degrade_timeout() -> None:
    async def _timeout_stub(bin_path, prompt):  # noqa: ANN001
        raise asyncio.TimeoutError()

    critic = _critic_with_stub(_make_config(), call_stub=_timeout_stub)
    v = _run(critic.critique(_make_report(), _make_context()))
    assert v.skipped and v.skip_reason == "timeout"


# --------------------------------------------------------------------------
# T-C3 — 측정 hook (telemetry JSONL 적립)
# --------------------------------------------------------------------------


def test_telemetry_records_call(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "codex_calls.jsonl"
    monkeypatch.setenv("V6_CODEX_LOG_PATH", str(log_path))
    critic = _critic_with_stub(_make_config(), call_stub=_stub_returning(_VALID_VERDICT))
    _run(critic.critique(_make_report(), _make_context()))
    assert log_path.exists()
    rec = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert rec["verdict_status"] == "violations"
    assert rec["violations"] == 1
    assert rec["latency_ms"] == 42
    assert rec["skipped"] is False


def test_telemetry_records_degrade(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "codex_calls.jsonl"
    monkeypatch.setenv("V6_CODEX_LOG_PATH", str(log_path))
    critic = CodexCritic(_make_config())
    critic._resolve_bin = lambda: None  # type: ignore[method-assign]
    _run(critic.critique(_make_report(), _make_context()))
    rec = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert rec["skipped"] is True
    assert rec["skip_reason"] == "codex_not_found"


# --------------------------------------------------------------------------
# 호출 형태 (VM spike 가 확정할 cmd) — config override 가능 검증
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# 검수자 페르소나 (V6-2) — 기본 로드 + graceful + 본문작성 금지 정합
# --------------------------------------------------------------------------


def test_default_persona_loads() -> None:
    critic = CodexCritic(Config(_env_file=None))
    assert critic.critic_persona, "기본 페르소나(prompts/codex_critic_persona.md)가 로드돼야 함"
    # V6 핵심 가드가 페르소나에 살아있는지 (AP-V6-8 근거인용 / AP-V6-11 본문작성금지).
    assert "AP-V6-8" in critic.critic_persona
    assert "AP-V6-11" in critic.critic_persona
    assert "팩트체크 데스크" in critic.critic_persona


def test_persona_forbids_body_writing() -> None:
    # 페르소나는 *검수자* 여야 한다 — 본문을 쓰지 않는다는 지시가 있어야 (AP-V6-11).
    critic = CodexCritic(Config(_env_file=None))
    assert "본문을 다시 쓰지" in critic.critic_persona or "본문 작성 금지" in critic.critic_persona


def test_missing_persona_graceful() -> None:
    cfg = _make_config(codex_critic_persona_path="/nonexistent/persona.md")
    critic = CodexCritic(cfg)
    assert critic.critic_persona == ""  # 파일 없으면 빈 문자열 (degrade), 예외 안 남


def test_explicit_empty_persona_overrides_default() -> None:
    critic = CodexCritic(Config(_env_file=None), persona="")
    assert critic.critic_persona == ""


def test_build_cmd_respects_config() -> None:
    critic = CodexCritic(
        _make_config(codex_subcommand="exec", codex_extra_args="--json --cd /tmp", codex_model="gpt-5")
    )
    cmd = critic._build_cmd("/usr/bin/codex")
    assert cmd == ["/usr/bin/codex", "exec", "--json", "--cd", "/tmp", "-m", "gpt-5"]
