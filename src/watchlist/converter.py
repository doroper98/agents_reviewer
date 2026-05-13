"""Convert ``ScenarioAnalysis.watch_signals`` (dict[]) → ``list[WatchSignal]``.

V3 Step 5-B (v2.9.5). Anti-pattern #11 회피의 어댑터 — orchestrator 가 분석 종료 시점에
호출, 결과를 ``WatchlistRegistry.register()`` 로 영구 저장.

기존 dict 스키마 (ScenarioArchitect 산출):
    {"signal": str, "description": str, "indicates": str, "icon": str (optional)}

발화 trigger 두 가지뿐 (deadline 자동 / 사용자 수동) 이라 dict 입력에 명시적 deadline 이
없는 경우 ``default_deadline_days`` 후로 설정 (기본 30 일).
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from src.models import WatchDirection, WatchSignal


def _infer_direction(indicates: str) -> WatchDirection:
    """Heuristic: indicates 텍스트의 어휘로 direction 추정. 모호하면 ambiguous."""
    if not indicates:
        return "ambiguous"
    text = indicates.lower()
    confirms_markers = ("확인", "지속", "유지", "기준", "baseline", "확정", "정상")
    rejects_markers = ("위험", "악화", "꺾", "역전", "이탈", "위반", "급변", "충격")
    if any(m in indicates for m in rejects_markers) or any(m in text for m in rejects_markers):
        return "rejects_base"
    if any(m in indicates for m in confirms_markers) or any(m in text for m in confirms_markers):
        return "confirms_base"
    return "ambiguous"


def _make_signal_id(parent_report_id: str, idx: int, signal_text: str) -> str:
    """Deterministic ID — 같은 보고서 + 같은 신호 텍스트면 같은 ID 가 나와 idempotent register."""
    seed = f"{parent_report_id}|{idx}|{signal_text}".encode("utf-8")
    short_hash = hashlib.sha256(seed).hexdigest()[:8]
    today = date.today().strftime("%Y%m%d")
    return f"WS-{today}-{short_hash}"


def convert_watch_signals(
    scenario_signals: list[dict],
    parent_report_url: str = "",
    parent_report_id: str = "",
    parent_chat_id: int = 0,
    default_deadline_days: int = 30,
    chain_depth: int = 0,
) -> list[WatchSignal]:
    """Convert a ScenarioArchitect dict-list into validated WatchSignal models.

    빈 리스트 / 누락 필드 입력은 안전하게 건너뜀 (skip + return empty / partial). 신호의
    ``signal`` 텍스트가 비어있으면 그 항목은 스킵.
    """
    if not scenario_signals:
        return []

    out: list[WatchSignal] = []
    deadline_default = (date.today() + timedelta(days=default_deadline_days)).isoformat()

    for idx, raw in enumerate(scenario_signals, start=1):
        if not isinstance(raw, dict):
            continue
        signal_text = (raw.get("signal") or "").strip()
        if not signal_text:
            continue
        description = signal_text
        measurement = (raw.get("description") or "").strip()
        indicates = (raw.get("indicates") or "").strip()
        deadline = (raw.get("deadline") or deadline_default).strip()
        follow_up = (raw.get("follow_up_action") or raw.get("follow_up") or "").strip()
        if not follow_up and indicates:
            follow_up = f"{indicates} 시 후속 분석 재요청 권장"

        try:
            ws = WatchSignal(
                signal_id=_make_signal_id(parent_report_id or "no-parent", idx, signal_text),
                description=description,
                measurement=measurement,
                direction=_infer_direction(indicates),
                deadline=deadline,
                follow_up_action=follow_up,
                parent_report_url=parent_report_url,
                parent_report_id=parent_report_id,
                parent_chat_id=parent_chat_id,
                chain_depth=chain_depth,
            )
        except Exception:
            # Pydantic validation failed (e.g. invalid direction/deadline) — skip.
            continue
        out.append(ws)

    return out
