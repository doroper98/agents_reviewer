"""v8.2.8 — 편집장 CLI 출력 head-loss 회귀 (`--output-format json` envelope 캡처).

2026-06-27 르포(`analysis_20260627_123516`) 588자 미파싱 + bot.log 상 수개월
누적된 systemic 결함: `--output-format text` 캡처가 *긴 응답에서 stdout 머리*
(앞부분 — 여는 `{`·headline·앞 섹션)를 잃어 raw 가 본문 *중간*부터 시작 →
파싱·복구 전부 실패 → minimal fallback. 재발방지 = json envelope 캡처
(`{...,"result":"<본문>"}`)에서 전체 본문을 안전 추출. 본 테스트는 추출기
(`_extract_cli_result` / `_decode_json_string_prefix`)를 고정한다.
"""

from __future__ import annotations

import json

from src.agents.narrative_composer import NarrativeComposer


def test_extracts_result_from_complete_envelope() -> None:
    report = json.dumps({"headline": "정상", "sections": [{"heading": "h", "prose": "p"}]},
                        ensure_ascii=False)
    envelope = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "duration_ms": 1234, "result": report, "session_id": "abc",
    }, ensure_ascii=False)
    extracted = NarrativeComposer._extract_cli_result(envelope)
    assert extracted == report
    # 추출된 본문이 그대로 ComposedReport 로 파싱돼야 (head 손실 없음).
    composed = NarrativeComposer._parse_response(extracted)
    assert composed is not None and composed.headline == "정상"


def test_extracts_result_with_escaped_content() -> None:
    # result 본문에 따옴표·개행·유니코드가 escape 된 envelope.
    report = '{"headline":"인용 \\"칩값\\"","sections":[{"heading":"요약","prose":"줄1\\n줄2"}]}'
    envelope = json.dumps({"type": "result", "result": report}, ensure_ascii=False)
    extracted = NarrativeComposer._extract_cli_result(envelope)
    composed = NarrativeComposer._parse_response(extracted)
    assert composed is not None
    assert composed.headline == '인용 "칩값"'
    assert "줄1\n줄2" in composed.sections[0].prose


def test_truncated_envelope_recovers_partial_result() -> None:
    """타임아웃으로 envelope 가 중간에 끊겨도 result 본문 시작을 살린다."""
    # result 문자열이 닫히기 전에 절단된 envelope (앞부분은 온전).
    truncated = (
        '{"type":"result","subtype":"success","result":"'
        '{\\"headline\\":\\"끊긴 르포\\",\\"sections\\":[{\\"heading\\":\\"발단\\",'
        '\\"prose\\":\\"완결된 첫 섹션입니다.\\"},{\\"heading\\":\\"전개\\",\\"prose\\":\\"여기서 끊'
    )
    extracted = NarrativeComposer._extract_cli_result(truncated)
    # 추출 결과는 (절단된) 보고서 JSON 텍스트여야 — head(여는 {) 가 살아있음.
    assert extracted.startswith('{"headline":"끊긴 르포"')
    # 절단 복구로 최소 1섹션 살아야 (degraded).
    composed = NarrativeComposer._parse_response(extracted)
    assert composed is not None
    assert composed.degraded is True
    assert composed.sections and composed.sections[0].heading == "발단"


def test_non_envelope_passthrough() -> None:
    """envelope 가 아니면(text 모드 잔재/예상외) raw 를 그대로 반환 (graceful)."""
    plain = '{"headline":"직접 JSON","sections":[{"heading":"h","prose":"p"}]}'
    assert NarrativeComposer._extract_cli_result(plain) == plain
    # 본문 키 없는 dict (예상외 envelope) 도 원본 유지 → 파서가 판단.
    weird = '{"type":"result","session_id":"x"}'
    assert NarrativeComposer._extract_cli_result(weird) == weird
    # 빈 입력 안전.
    assert NarrativeComposer._extract_cli_result("") == ""


def test_decode_json_string_prefix_handles_escapes_and_unicode() -> None:
    dec = NarrativeComposer._decode_json_string_prefix
    assert dec(r'hello\nworld"tail') == "hello\nworld"  # 닫는 따옴표에서 종료
    assert dec(r'안녕') == "안녕"               # \uXXXX
    assert dec(r'no close quote') == "no close quote"   # 절단(닫는 따옴표 없음)
    assert dec(r'trailing backslash\\') == "trailing backslash\\"


def test_config_flag_default_on() -> None:
    from src.config import Config
    cfg = Config(_env_file=None)
    assert cfg.cli_json_output is True  # 기본 ON (head-loss 차단)
