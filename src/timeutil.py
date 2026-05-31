"""시간대 SSOT — 봇 전체의 '오늘' 기준은 KST (Asia/Seoul).

배경 (왜 만들었나 — WRITE-AP-11 회귀의 진짜 원인):
  봇이 도는 VM/컨테이너가 UTC 로 설정된 경우, timezone 없는 ``datetime.now()`` 는
  KST 보다 9시간 느린 시각을 돌려준다. 일일 브리핑은 06:00 KST 에 트리거되는데,
  그 시각의 UTC 는 *전날* 21:00 이다. 따라서 스케줄러는 ``ZoneInfo("Asia/Seoul")``
  로 올바르게 05-31 을 계산해 안내·스코프 문구를 만들지만, ContextAnalyst /
  NarrativeComposer 가 naive ``datetime.now()`` 로 ``current_date`` /
  ``publication_date`` 를 만들면 05-30 이 박혀 제목·본문이 하루 어긋난다.

원칙:
  사용자에게 노출되는 '오늘' 날짜는 *항상* 이 모듈의 ``today_kst()`` /
  ``now_kst()`` 를 거친다. naive ``datetime.now()`` 로 사용자 노출 날짜를 만들지
  말 것 (이 회귀의 SSOT 차단점). report_synthesizer.py 의 기존 KST 상수도
  의미상 동일 — 점진적으로 이 모듈을 참조하도록 통합.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Asia/Seoul 은 DST 가 없어 고정 +09:00 으로 충분 (report_synthesizer.py 와 동일 패턴).
# ZoneInfo 대신 고정 오프셋을 쓰는 이유: tzdata 미설치 환경에서도 무조건 동작.
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 시각 (KST, tz-aware). VM 의 시스템 시간대와 무관하게 항상 KST."""
    return datetime.now(KST)


def today_kst() -> str:
    """오늘 날짜 문자열 (``YYYY-MM-DD``, KST 기준)."""
    return now_kst().strftime("%Y-%m-%d")
