"""v8.2.4 — 생성 중단/열화 보고서 구조 플래그 회귀 (WRITE-AP-25).

2026-06-25 마이크론 deep 보고서 2건이 편집장 타임아웃(900s) → 부분 살림 없음 →
None → 1-섹션 minimal fallback 으로 발행됐는데, 텔레그램엔 "✅ 분석 완료" + 정상
URL 이 가서 사용자가 열어봐야만 미완성을 알았다. 재발방지 = 모든 "끝까지 못 짠 채
발행되는" 경로가 ComposedReport.degraded=True 를 세팅하고, 텔레그램·배너가 이를
읽어 명시한다. 본 테스트는 그 플래그 plumbing 을 고정한다.
"""

from __future__ import annotations

import json

from src.models import ComposedReport
from src.agents.narrative_composer import NarrativeComposer


# --------------------------------------------------------------------------
# 모델 기본값 — 정상 보고서는 열화 아님
# --------------------------------------------------------------------------

def test_composed_report_not_degraded_by_default() -> None:
    cr = ComposedReport(headline="정상 보고서")
    assert cr.degraded is False
    assert cr.degradation_reason == ""


# --------------------------------------------------------------------------
# 절단 JSON 복구본 → degraded
# --------------------------------------------------------------------------

def test_truncated_json_recovery_is_degraded() -> None:
    # sections 배열 중간에서 끊긴 응답 (마지막 섹션 prose 가 닫히지 않음).
    truncated = (
        '{"headline":"끊긴 보고서","deck":"부제",'
        '"sections":[{"heading":"첫 섹션","prose":"완결된 첫 섹션 본문입니다."},'
        '{"heading":"둘째 섹션","prose":"여기서 응답이 갑자기 잘'
    )
    composed = NarrativeComposer._parse_response(truncated)
    assert composed is not None, "절단 JSON 에서 최소 1섹션은 복구돼야 함"
    assert composed.degraded is True
    assert composed.degradation_reason  # 비어있지 않음


# --------------------------------------------------------------------------
# head-loss 복구본 → degraded
# --------------------------------------------------------------------------

def test_head_loss_recovery_is_degraded() -> None:
    # 응답 시작(``{`` / headline / sections)을 통째로 빠뜨리고 섹션 객체 중간 줄부터.
    head_lost = (
        '      "heading": "복구된 섹션",\n'
        '      "prose": "응답 시작이 누락됐지만 본문은 살아있는 케이스입니다."\n'
        '    }'
    )
    recovered = NarrativeComposer._recover_head_loss(head_lost)
    assert recovered is not None, "head-loss 케이스는 1섹션으로 복구돼야 함"
    assert recovered.degraded is True
    assert recovered.degradation_reason


# --------------------------------------------------------------------------
# 정상 완결 응답 → 열화 아님
# --------------------------------------------------------------------------

def test_clean_response_not_degraded() -> None:
    clean = json.dumps({
        "headline": "정상 보고서",
        "deck": "부제 한 줄",
        "sections": [
            {"heading": "섹션 1", "prose": "완결된 본문 1." * 3},
            {"heading": "섹션 2", "prose": "완결된 본문 2." * 3},
        ],
        "confidence_score": 0.7,
    }, ensure_ascii=False)
    composed = NarrativeComposer._parse_response(clean)
    assert composed is not None
    assert composed.degraded is False
    assert len(composed.sections) == 2
