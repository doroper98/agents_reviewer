"""v8.5.4 — 장마감 브리핑 소급 발행 회귀 (사용자 요청 2026-08-01).

"어제자 장마감 보고서를 만들게 할 수 있나?"

정시 스케줄러(18:30)가 못 돈 날의 브리핑을 나중에 손으로 만드는 경로.
가드하는 것:

  ① **스케줄러 무영향** — ``published_on`` 을 안 주거나 대상일==발행일이면
     프롬프트가 기존과 byte-equal. 소급 블록이 정시 브리핑에 새면 매일 나가는
     보고서 문체가 바뀐다.
  ② **소급 시점 규율** — 대상일≠발행일이면 두 날짜를 *본문이* 구분하도록
     지시가 들어가야 한다 (WRITE-AP-11/22 계열: 시점 표기·시점 선택 회귀).
  ③ **브리핑 계약 유지** — 소급 경로도 ``fetch_kr_market_internals=True``
     (선물·옵션·시장 폭 실데이터) + ``report_kind="market_briefing"``
     (목록 [장마감브리핑] 배지, v8.5.3) 를 반드시 넘겨야 한다. 하나라도 빠지면
     소급 보고서만 데이터·배지가 없는 반쪽이 된다.
  ④ **휴장일 가드** — 주말·공휴일은 종가가 없으므로 기본 거부.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.scheduler.market_briefing import (
    _build_market_briefing_prompt,
    _resolve_target_date,
    run_backfill_market_briefing,
)

_ROOT = Path(__file__).resolve().parents[2]
_KST = ZoneInfo("Asia/Seoul")
_ANCHOR = datetime(2026, 7, 31, 18, 30, tzinfo=_KST)  # 금요일 (거래일)


# --------------------------------------------------------------------------
# ① 스케줄러 경로 byte-equal
# --------------------------------------------------------------------------


def test_scheduled_prompt_unchanged() -> None:
    base = _build_market_briefing_prompt(_ANCHOR, "페르소나")
    assert _build_market_briefing_prompt(_ANCHOR, "페르소나", published_on=None) == base
    assert _build_market_briefing_prompt(
        _ANCHOR, "페르소나", published_on=_ANCHOR.date(),
    ) == base, "대상일==발행일인데 소급 블록이 붙음 — 정시 브리핑 문체 오염"


# --------------------------------------------------------------------------
# ② 소급 시점 규율
# --------------------------------------------------------------------------


def test_backfill_prompt_separates_target_and_publication_date() -> None:
    p = _build_market_briefing_prompt(_ANCHOR, "", published_on=date(2026, 8, 1))
    assert "2026-07-31" in p and "2026-08-01" in p, "두 날짜가 모두 명시돼야 함"
    assert "소급" in p
    # 대상일 이후 사건 혼입 금지 + '오늘' 로 뭉개기 금지 (WRITE-AP-11/22).
    assert "소급해 섞지 말 것" in p
    assert "'오늘'" in p


# --------------------------------------------------------------------------
# ③ 브리핑 계약 (실데이터 + 배지)
# --------------------------------------------------------------------------


class _StubOrchestrator:
    calls: list[dict] = []

    def __init__(self, config, **kwargs) -> None:
        self.config = config

    async def run_analysis(self, **kwargs):  # type: ignore[no-untyped-def]
        _StubOrchestrator.calls.append(kwargs)
        return object()


class _StubConfig:
    market_briefing_persona_path = ""
    market_briefing_tz = "Asia/Seoul"
    market_briefing_time = "18:30"
    telegram_bot_token = ""
    report_output_dir = "reports"


def _run_backfill(monkeypatch, **over):  # type: ignore[no-untyped-def]
    import src.orchestrator as orch_mod

    _StubOrchestrator.calls = []
    monkeypatch.setattr(orch_mod, "Orchestrator", _StubOrchestrator)
    monkeypatch.setattr(
        "src.scheduler.market_briefing._is_krx_trading_day",
        lambda d: (True, None),
    )
    kwargs = {"target": date(2026, 7, 31), "config": _StubConfig(), "chat_ids": []}
    kwargs.update(over)
    asyncio.run(run_backfill_market_briefing(**kwargs))
    return _StubOrchestrator.calls[-1]


def test_backfill_keeps_market_briefing_contract(monkeypatch) -> None:
    call = _run_backfill(monkeypatch)
    assert call["fetch_kr_market_internals"] is True, (
        "선물·옵션 그릭 + 시장 폭 실데이터 fetch 누락 (v7.9.0 계약)"
    )
    assert call["report_kind"] == "market_briefing", (
        "report_kind 누락 — 보고서 목록에서 [장마감브리핑] 배지를 못 받는다 (v8.5.3)"
    )
    assert call["mode"] == "deep"
    assert "한국 주식장 마감 후 자동 브리핑" in call["event_description"], (
        "스케줄러와 같은 고정 문구여야 구 발행분 판별(report_kind.py)과 정합"
    )
    assert "[소급 발행" in call["event_description"], (
        "published_on 미전달 — 지난 날짜 브리핑인데 본문이 발행일과 대상일을 뭉갠다"
    )


def test_backfill_prompt_targets_requested_date(monkeypatch) -> None:
    call = _run_backfill(monkeypatch, target=date(2026, 7, 30))
    assert "2026-07-30" in call["event_description"]
    assert "2026-07-31" not in call["event_description"]


# --------------------------------------------------------------------------
# ④ 휴장일 가드 + 날짜 파싱
# --------------------------------------------------------------------------


def test_backfill_notifies_start_and_failure(monkeypatch) -> None:
    """v8.5.5 — 소급 발행도 시작·실패를 텔레그램에 알려야 한다.

    2026-08-01 실사고: 사실수집 타임아웃으로 통째 실패했는데 텔레그램엔 *아무
    메시지도* 안 갔다. 정시 스케줄러는 시작 안내(_market_brief_for_chat)와 실패
    안내(_run_one_market_cycle)를 둘 다 보내는데, 소급 경로엔 성공 시 송신밖에
    없었다 — 터미널을 안 보고 있으면 실패한 줄도 모른다.
    """
    import src.orchestrator as orch_mod
    import src.scheduler.market_briefing as mb

    sent: list[str] = []

    async def _fake_notify(config, chat_ids, text):  # type: ignore[no-untyped-def]
        sent.extend(text for _ in chat_ids)

    class _Boom:
        def __init__(self, config, **kw) -> None: ...
        async def run_analysis(self, **kw):  # type: ignore[no-untyped-def]
            raise RuntimeError("claude CLI failed after 3 attempt(s): timeout after 300s")

    monkeypatch.setattr(orch_mod, "Orchestrator", _Boom)
    monkeypatch.setattr(mb, "_notify_backfill", _fake_notify)
    monkeypatch.setattr(mb, "_is_krx_trading_day", lambda d: (True, None))

    with pytest.raises(RuntimeError):
        asyncio.run(run_backfill_market_briefing(
            target=date(2026, 7, 31), config=_StubConfig(), chat_ids=[7],
        ))

    assert len(sent) == 2, f"시작·실패 알림 2건이어야 하는데 {len(sent)}건"
    assert "시작" in sent[0]
    assert "실패" in sent[1] and "timeout after 300s" in sent[1], (
        "실패 알림에 원인이 안 담김 — 사용자가 왜 실패했는지 모른다"
    )


def test_holiday_is_rejected_unless_forced() -> None:
    saturday = date(2026, 8, 1)
    with pytest.raises(ValueError, match="휴장일"):
        asyncio.run(run_backfill_market_briefing(
            target=saturday, config=_StubConfig(), chat_ids=[],
        ))


def test_resolve_target_date_forms() -> None:
    assert _resolve_target_date("20260731", "Asia/Seoul") == date(2026, 7, 31)
    assert _resolve_target_date("2026-07-31", "Asia/Seoul") == date(2026, 7, 31)
    today = datetime.now(_KST).date()
    assert (today - _resolve_target_date("yesterday", "Asia/Seoul")).days == 1
    with pytest.raises(ValueError):
        _resolve_target_date("어제자", "Asia/Seoul")


def test_cli_entry_point_exists() -> None:
    """`python3 -m src.scheduler.market_briefing` 로 돌아야 한다 (VM 운영 경로)."""
    src = (_ROOT / "src" / "scheduler" / "market_briefing.py").read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in src
    for opt in ("--no-send", "--chat-id", "--force", "--mode"):
        assert opt in src, f"CLI 옵션 {opt} 누락"
