"""v8.2.7 — 모델 안전망 회귀 (WRITE-AP-25 계열). v8.5.0 — 전 포맷 확장.

2026-06-27 회귀: v8.2.6 르포(reportage, 당시 Opus 4.8) 1건이 편집장 응답 588자
미파싱 → 모든 재시도/살림 실패 → None → 1-섹션 minimal fallback 으로 *열화
발행*. 재발방지 = 주 모델이 끝내 파싱 가능한 보고서를 못 내면, 발행 가능
보고서 0건으로 떨어지기 전에 *검증된 안정 모델(COMPOSER_MODEL_STABLE=4.7)* 로
마지막 한 번 더 시도한다. v8.5.0 부터 주 모델이 일반·르포 모두 Opus 5(신모델)
로 통일되며 안전망도 전 포맷에 적용.
"""

from __future__ import annotations

import asyncio
import json

import src.agents.narrative_composer as nc_mod
from src.agents.narrative_composer import NarrativeComposer
from src.config import Config
from src.models import ContextAnalysis


async def _instant_sleep(_seconds: float) -> None:
    """재시도 backoff 를 즉시 통과시켜 테스트 속도 보존."""
    return None


def _valid_report_json() -> str:
    return json.dumps({
        "headline": "안정 모델이 받아낸 르포",
        "deck": "부제",
        "sections": [
            {"heading": "발단", "prose": "완결된 본문입니다." * 4},
            {"heading": "전개", "prose": "두 번째 완결 본문입니다." * 4},
        ],
        "confidence_score": 0.6,
    }, ensure_ascii=False)


def _make_composer() -> NarrativeComposer:
    cfg = Config(_env_file=None)
    # CLI 경로를 타게 강제 (use_cli_mode 는 키 없으면 True 가 기본).
    object.__setattr__(cfg, "use_cli_mode", True)
    return NarrativeComposer(cfg)


def test_reportage_falls_back_to_stable_model_on_parse_failure() -> None:
    """주 모델(Opus 5)이 미파싱 응답(588자류)만 주면 안정 모델(4.7) 폴백이 살린다."""
    nc = _make_composer()
    calls: list[str] = []

    async def fake_cli(user_message, timeout_s=480.0, system_prompt=None, model=None):
        calls.append(model or "")
        if model == nc.COMPOSER_MODEL_REPORTAGE:  # 주 모델 → 미파싱 단문 (588자 회귀 재현)
            return "죄송하지만 이 보고서를 바로 작성하긴 어렵습니다." * 3
        return _valid_report_json()  # 안정 모델(COMPOSER_MODEL_STABLE) → 정상 JSON

    nc._call_cli = fake_cli  # type: ignore[assignment]
    nc_mod.asyncio.sleep = _instant_sleep  # type: ignore[assignment]
    ctx = ContextAnalysis(event_name="반도체", summary="요약")
    composed = asyncio.run(nc.compose_unified(ctx, mode="deep", report_format="reportage"))

    assert composed is not None, "안정 모델 폴백으로 보고서가 살아야 함 (minimal fallback 회피)"
    assert composed.headline == "안정 모델이 받아낸 르포"
    assert len(composed.sections) == 2
    # 주 모델(Opus 5)을 (재시도 포함) 먼저 쓰고, 끝으로 안정 모델 폴백을 정확히 1회.
    assert nc.COMPOSER_MODEL_REPORTAGE in calls
    assert calls.count(nc.COMPOSER_MODEL_STABLE) == 1
    # v8.5.0 불변식 — 안전망이 작동하려면 주 모델과 안정 모델은 반드시 달라야 한다.
    assert nc.COMPOSER_MODEL_STABLE != nc.COMPOSER_MODEL


def test_standard_report_also_gets_stable_fallback() -> None:
    """v8.5.0 — 일반 보고서도 주 모델(Opus 5) 전부 실패 시 안정 모델 폴백 1회.

    (v8.2.7 당시엔 일반=4.7 이 곧 안정 모델이라 분기 자체가 없었지만, v8.5.0 부터
    주 모델이 신모델 Opus 5 로 바뀌며 일반 보고서도 안전망 대상이 됐다.)"""
    nc = _make_composer()
    calls: list[str] = []

    async def fake_cli(user_message, timeout_s=480.0, system_prompt=None, model=None):
        calls.append(model or "")
        return "파싱 불가 단문."  # 항상 미파싱

    nc._call_cli = fake_cli  # type: ignore[assignment]
    nc_mod.asyncio.sleep = _instant_sleep  # type: ignore[assignment]
    ctx = ContextAnalysis(event_name="X", summary="요약")
    composed = asyncio.run(nc.compose_unified(ctx, mode="deep", report_format="standard"))

    assert composed is None, "전부 미파싱이면 None → orchestrator minimal fallback"
    # 주 모델 재시도(COMPOSE_MAX_ATTEMPTS) + 안정 모델 폴백 1회.
    assert calls.count(nc.COMPOSER_MODEL) == nc.COMPOSE_MAX_ATTEMPTS
    assert calls.count(nc.COMPOSER_MODEL_STABLE) == 1
    assert len(calls) == nc.COMPOSE_MAX_ATTEMPTS + 1


def test_reportage_block_scopes_length_to_json_contract() -> None:
    """v8.2.7 — 분량 강령이 JSON sections 배열 안으로 한정된다는 가드.

    v8.2.6 의 강한 '길어야 한다' 가 모델을 산문/메타 코멘트로 흘려 JSON 계약을
    이탈(588자 미파싱)할 위험을 막는 프롬프트 문구.
    """
    from src.agents.narrative_composer import _REPORTAGE_BLOCK
    for marker in ("sections`` 배열 안", "단일 JSON 객체", "출력 계약"):
        assert marker in _REPORTAGE_BLOCK, f"JSON 계약 스코핑 marker '{marker}' 누락"
