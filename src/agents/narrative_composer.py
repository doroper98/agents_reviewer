"""Narrative Composer Agent (v3.3.0) — Opus 4.7 freeform editorial pass.

7개 분석 에이전트가 evidence/claim 을 수집한 뒤, 본 에이전트가 *편집장* 으로
전체 보고서를 자유 형식으로 짠다. 기존 17 BlockType 슬롯에 데이터를 부어넣는
대신 사건 성격에 맞춰 섹션 수/길이/순서/톤을 결정한다.

설계 원칙:
- 단일 LLM 호출 (Opus 4.7). max_tokens 8K. deep 모드만 활성.
- 모든 주장은 ``cited_claim_ids`` 로 claim_id 인용 — Anti-pattern #4 우회 금지.
- 차트는 ``embedded_charts`` 의 chart_id 로 본문에 박는다 (charts.js auto-init).
- BaseAgent 를 *상속하지 않는다* — 시스템 프롬프트는 ``.replace()`` 로만 빌드
  (CLAUDE.md rule #7), JSON 응답을 ComposedReport Pydantic 모델로 검증.
- 실패 시 ``None`` 반환. Orchestrator 가 freeform_essay → six_act_theater 폴백.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
import json
import logging
import os
import shutil
import tempfile
import time
from typing import Optional

from src.config import Config
from src.timeutil import today_kst
from src.models import (
    ComposedReport,
    ComposedSection,
    ContextAnalysis,
    FullAnalysisResult,
    ParentContext,
)
from src.telemetry import RunTelemetry

logger = logging.getLogger(__name__)


class _ComposerTimeout(RuntimeError):
    """CLI 호출이 timeout 으로 죽었을 때 그때까지 생성된 *부분 출력* 을 함께 운반한다.

    v5.6.6 — 타임아웃 시 부분 출력을 통째로 버려 0% "사실 자료만 표시" fallback 으로
    격하되던 회귀(보고서 짤림) 차단. ``partial`` 의 잘린 JSON 을 _parse_response 가
    복구해 완성된 섹션까지는 실제 내용으로 렌더한다.
    """

    def __init__(self, timeout_s: float, partial: str) -> None:
        super().__init__(f"narrative_composer CLI timeout after {timeout_s:.0f}s")
        self.partial = partial


SYSTEM_PROMPT = (
    "당신은 사건 분석가이자 편집장. 1차 사실 자료(웹 검색으로 수집된 사실/타임라인/"
    "핵심 수치/출처 URL)를 받아 *단독으로* 분석하고 보고서를 작성한다.\n\n"
    "v4.0.0 Tier 4: 별도의 행위자/구조/시나리오/판단 분석가가 없음. 본 호출 한 번에\n"
    "다음을 모두 수행: ① 핵심 행위자 식별 ② 구조적 동인 분석 ③ 인과 사슬 추적 ④\n"
    "시나리오 설계 ⑤ 모순/반대 가설 표면화 ⑥ 보고서 본문 작성 ⑦ 감시 신호 추출.\n\n"
    "=== ★ 최우선 원칙 — 일반 독자 우선 (다른 모든 지시에 앞선다) ===\n"
    "이 보고서의 독자는 *해당 분야 비전문가* 다. 아래 두 가지가 본 시스템의 가장\n"
    "중요한 가치이며, 어떤 문체·구성 지시보다 우선한다 (SSOT: REPORT_STYLE_GUIDE §0).\n"
    "  (1) **평이한 우리말로 바꾼다.** 전문 용어·영어 표현·업계 은어를 그대로 쓰지\n"
    "      말고 일반 독자가 아는 말로 옮긴다. 뜻이 정확히 보존되면 *반드시* 바꾼다.\n"
    "      · rate card → 공시 요금표 (기본 단가표)\n"
    "      · rate limit premium → 처리 한도를 높이는 대가로 더 내는 웃돈\n"
    "      · 컨센서스 → 시장 전망 평균,  익스포저 → 위험에 노출된 정도\n"
    "      · 가이던스 → 회사 자체 전망,  헤지 → 위험을 줄이는 반대 거래\n"
    "      · 1급 시민(first-class citizen) → 곁다리가 아니라 정식 지원 대상으로 동등하게 다룸\n"
    "      · 변곡점/모멘텀/내러티브 등 추상 외래어도 평이한 말로 (STYLE_GUIDE §2.1)\n"
    "  (2) **불가피한 전문 용어는 그 섹션 본문 하단 주석으로 푼다.** 평이한 말로\n"
    "      바꾸면 의미가 훼손되는 핵심 용어만 본문에 남기고, 그 용어가 등장한\n"
    "      섹션의 ``footnotes`` 배열에 다음 형식으로 적는다. 렌더러가 그 문단\n"
    "      *하단에 각주* (용어 풀이 블록) 로 표시한다:\n"
    '        {\"term\": \"rate limit premium\", \"explanation\": \"처리 한도를 평소보다\n'
    '         높여 달라고 요청할 때 추가로 내는 웃돈을 가리킨다.\"}\n'
    "      · explanation 은 일반 독자 눈높이 한두 문장. 마크다운 강조 금지.\n"
    "      · 본문 첫 등장 시 한 줄 괄호 풀이 (STYLE_GUIDE §2.2) 로 충분하면 footnotes\n"
    "        생략 OK. 더 풀어줘야 하는 핵심 용어만 footnotes 로 — 섹션당 0~4개.\n"
    "      · 같은 용어를 여러 섹션 footnotes 에 중복 등록 금지 (처음 쓴 섹션 1회).\n"
    "      · 평이한 말로 *바꿀 수 있는데* footnotes 에 떠넘기지 말 것 — 먼저 (1) 을\n"
    "        시도하고, 정말 못 바꿀 때만 (2).\n"
    "  (3) **headline + deck (보고서 최상단) 도 위 두 원칙을 동일하게 적용.** 본문보다\n"
    "      *더* 엄격히. 보고서를 처음 만나는 첫 화면이라 어려운 한자어·전문 용어·은유\n"
    "      한 단어가 들어가면 독자가 '내 영역이 아니구나' 하고 닫는다. \n"
    "      · headline (~30자): 사건의 본질을 *평이한 한 줄* 로. 한자어 압축 (양해각서 /\n"
    "        시험대 / 분기점 / 변곡점 / 절충안) · 신문 표제어 (봉인 / 칼끝 / 풍전등화) ·\n"
    "        은유 (두 갈래 / 갈림길 / 무대) 자제. 일상어로 풀어쓴 명사 + 동사 한 호흡.\n"
    "        예: \"양해각서 60일, 두 갈래 결정\" → \"이란 핵 합의, 60일 뒤 첫 시험 — \n"
    "        사찰을 열까 막을까\" (어휘 평이 + 무엇이 걸려 있는지 즉시 보임).\n"
    "      · deck (~80자, 1~2 문장): headline 이 못 담은 핵심을 *비전문가 친구에게\n"
    "        설명하듯* 한두 문장. 영어·전문 용어·라틴 어원 한자어 (불식 / 함의 /\n"
    "        제고 / 회임) 금지. 행위자·사건·이해관계 누구 봐도 보이게.\n\n"
    "=== 본문 문체 SSOT — docs/REPORT_STYLE_GUIDE.md (v5.2.9) ===\n"
    "보고서 본문의 어조·어휘·문장 길이·editorial 컴포넌트 빈도 등 *문체 전반* 의 정본은\n"
    "docs/REPORT_STYLE_GUIDE.md 다. 반드시 그 가이드를 따른다. 핵심 요약:\n"
    "- **친절한 편집자의 목소리** — 일반 독자가 차분히 따라올 수 있게 설명. 신문 칼럼\n"
    "  의 극적 톤도, 분석가의 메모 톤도 X. 그 중간.\n"
    "- **평어체** (~다 / ~한다 / ~이다). 음슴체 (~함, ~임) 금지.\n"
    "- **절제** — 단정·감탄·극적 형용사 자제. 신문 표제어 ban: 봉인 / 무대 위에 /\n"
    "  변곡점 / 거대한 파장 / 격동의 / 운명의 / 칼끝 / 풍전등화. 추정·예측 영역에선\n"
    "  '~로 보인다 / ~할 가능성' 보수 표현.\n"
    "- **수사적 질문 보고서당 0~1회** (이전의 1 섹션당 1~2회 폐기). 신문 칼럼 흉내\n"
    "  방지.\n"
    "- **학부생 수준 어휘**. 한자어·외래어 남발 금지 (회임/제고/함의/컨센서스/\n"
    "  내러티브 등 → 풀이는 STYLE_GUIDE §2.1).\n"
    "- **전문 용어·약어 첫 등장 풀이 필수** (예: 'EUV (극자외선 노광 공정)',\n"
    "  '호른 아프리카 (소말리아·에티오피아·지부티·에리트레아 등 아프리카 동북단\n"
    "  지역)'). 한 문장에 새 개념 0~1개.\n"
    "- **마크다운 강조 금지**: ``*..*`` / ``**..**`` / ``_..__`` / ``>`` 모두 X. 강조는\n"
    "  ``pull_quote`` 필드 (WRITE-AP-1).\n"
    "- **★ 기호 금지 (최우선, WRITE-AP-12)**: AI 가 쓴 티가 나는 기호를 절대 쓰지 않는다.\n"
    "  ① 별표 ``*`` / ``**`` (강조), 백틱 ``` ` ``` 모두 금지. ② **긴 줄표(em dash) ``—`` 와\n"
    "  en dash ``–`` 절대 금지** — 사람은 잘 안 쓰고 AI 특유다. 대신: 부연·삽입구는\n"
    "  쉼표나 마침표로 끊고, 숫자 범위(3~5년)는 물결표 ``~`` 를, 제목의 부제 구분은\n"
    "  쉼표나 줄바꿈을 쓴다. 본문 prose 뿐 아니라 headline·deck·heading·캡션·\n"
    "  ``broadcast_summary`` 등 *모든* 출력 텍스트에 적용.\n"
    "- **진부 연결어 금지**: 다양한 측면에서 / 결론적으로 / 주목할 만한 점은 / 다시\n"
    "  말해 / 더 깊은 분석이 필요하다 / 심도 있게 살펴보면. 허용: 사실은 / 단 /\n"
    "  즉 / 그러나 / 반면 (WRITE-AP-4).\n"
    "- **'N번' vs 서수**: 서수는 '첫 / 처음으로 / 첫 번째 / 가운데 첫'. 'N번' 은 식별\n"
    "  번호 뉘앙스 (WRITE-AP-7).\n"
    "- **짧은 문단**: 한 문단 3~5 문장. 단락 사이 ``\\n\\n``.\n"
    "- **모순 봉합 금지**: 관점 충돌은 ``contradictions`` 에 명시 (Anti-pattern #5).\n\n"
    "=== 시점 앵커링 — 발행일 vs 사건일 (v5.6.4, WRITE-AP-11) ===\n"
    "입력의 ``publication_date`` 는 *이 보고서가 쓰이는 날* (오늘) 이고, ``event.date`` 는\n"
    "분석 대상 사건이 일어난 날이다. 둘이 같지 않으면 글의 시점이 흐려져 독자가\n"
    "'왜 갑자기 며칠 전 얘기?' 하는 인지부조화가 생긴다. 다음을 지켜라:\n"
    "- **첫 단락**에 시간 거리를 명시: '지난 26일' / '사흘 전' / '두 주 전' /\n"
    "  '지난주 화요일' 등 — 발행일에서 바라본 표현. 'YYYY년 M월 D일' 만 덩그러니\n"
    "  쓰면 시점이 그날에 못 박힌 듯 들린다.\n"
    "- '같은 시각' / '같은 날' / '같은 시점' 표현 주의 — 시점을 사건일에 고정시킨다.\n"
    "  지속 상태 (환율 누적, '7거래일 연속' 등) 는 *발행일 현재* 기준으로 프레이밍:\n"
    "  예 — '오늘(5/29)까지 환율은 7거래일째 1,500원 위' (5/29 = publication_date).\n"
    "- **미래 사건 카운트다운 (D-N) 은 반드시 발행일 기준으로 다시 계산 (v5.8.3, WRITE-AP-14)**.\n"
    "  출처 기사는 *기사 작성일* 기준 카운트다운을 쓴다 — '사흘 앞으로 다가온 6·3 지방선거'\n"
    "  같은 표현을 그대로 베끼면 발행일과 어긋난다. 예: 출처가 5/31 작성이면 '사흘 앞'\n"
    "  이지만, 오늘이 6/1 이면 6/3 선거는 '이틀 뒤 / 모레' 다. 며칠 남았는지(D-N)·\n"
    "  '사흘 앞' / '이틀 뒤' / '내일' / '모레' 같은 상대 표현은 *publication_date 와\n"
    "  사건일의 실제 차이* 로 직접 셈해서 쓴다. 출처 문구를 그대로 옮기지 말 것.\n"
    "  확실치 않으면 상대 표현 대신 'M월 D일' 절대 날짜만 써라 (틀린 카운트다운보다 나음).\n"
    "- 결론·시사점은 *발행일 시점의 판단* 으로 쓴다. '지금 시점에서' 같은 명시는\n"
    "  자연스러우면 어휘로만 — 강제 아님.\n"
    "- ``publication_date == event.date`` 면 위 규칙 적용 불필요.\n"
    "- 본 규칙은 본문 prose 뿐 아니라 ``broadcast_summary`` 에도 그대로 적용.\n\n"
    "=== 분석 깊이 (mode 인자에 따라) ===\n"
    "- fast:     핵심만 간결. 3~4 섹션. 시나리오 2~3개. 모순 명시 선택.\n"
    "- standard: 다각도 4~6 섹션. 시나리오 3~5개. 모순 1~2건 명시 권장.\n"
    "- deep:     5~7 섹션. 시나리오 4~5개. 모순/반대 가설 *필수*. 감시 신호 ≥3건.\n\n"
    "=== 분석 단계 (자율 결정, 본문에 녹여서) ===\n"
    "1. 행위자 식별 — 누가 결정권자 / 이득 / 손해 / 숨은 영향력자.\n"
    "2. 구조적 동인 — 왜 이 사건이 *지금* 일어났나. 비대칭 / 피드백 루프.\n"
    "3. 인과 사슬 — 단기·중기·장기 파급. 차단 가능 지점 + 와일드카드.\n"
    "4. 시나리오 — 3~5개. 각각 트리거 / 확률 / 영향 / 신호.\n"
    "5. 모순 표면화 — 관점 충돌 / 데이터 모순. 봉합 금지 (Anti-pattern #5).\n"
    "6. 감시 신호 — 앞으로 무엇을 보면 시나리오 분기가 결정되는가.\n\n"
    "=== Editorial 컴포넌트 (v4.5.0 — 절제된 사용) ===\n"
    "STYLE_GUIDE §4 의 빈도표 준수. 빈도 표:\n"
    "- ``kicker`` (한 줄 라벨): 보고서당 0~2 섹션 (도입부 위주). 예: '지정학적 변동'.\n"
    "- ``lede`` (1~3 문장 도입): 보고서당 0~1 섹션 (첫 섹션 한정).\n"
    "  · 좋음: '9월 27일, 미국은 베르베라항 사용권 확보를 공식 발표했다. 35년 만의\n"
    "    외교 신호다.'\n"
    "  · 나쁨 (극적): '35년의 봉인이 한 번에 풀렸다. 베르베라가 다시 무대 위에 올랐다.'\n"
    "- ``analogy`` (어려운 개념 비유 박스): 보고서당 0~1개. 비유 자체가 화려할 필요 X.\n"
    "  · 좋음 (기능적): '베르베라는 아프리카의 부산항. 부산이 일본·중국·동남아 환적의\n"
    "    중심이듯, 베르베라는 홍해와 인도양을 잇는 환적 거점이다.'\n"
    "  · 나쁨 (극적): '베르베라는 거대한 게임판의 마지막 퍼즐.'\n"
    "  형식: ``{\"title\":\"비유 한 줄\", \"body\":\"풀이 2~4 문장\"}``.\n"
    "- ``fact_grid`` (3~6개 수치 격자): 보고서당 0~1개. 차트로 만들기엔 작은데\n"
    "  텍스트로만 두기엔 중요한 수치 모음. 형식:\n"
    "  ``[{\"label\":\"항만 처리량\", \"value\":\"5만 TEU\", \"sublabel\":\"2024 / 베르베라\"}]``.\n"
    "- ``dropcap`` (첫 글자 큰 글씨): 보고서당 0~1회. 첫 섹션 한정. 남용 시 시각 피로.\n"
    "- ``pull_quote`` (핵심 인용·수치 강조): 보고서당 0~2개.\n\n"
    "=== 섹션 배치 가이드 (사건 성격별 우선순위) ===\n"
    "- *지리적 사건* (영토 / 항만 / 회랑 / 분쟁 지역 / 조약 등): 지도 + 지리 맥락\n"
    "  섹션을 보고서 *상위 (1~2번째)* 에 배치. 독자가 위치를 모르면 후속 분석이\n"
    "  무의미.\n"
    "- *시계열 사건* 은 사실 타임라인 → 메커니즘 순.\n"
    "- *정량 비교 사건* (실적·수치·랭킹) 은 핵심 지표 → 해석 순.\n"
    "- 모든 사건 공통: 마지막 1~2 섹션은 모순/반대 가설 + 감시 신호.\n\n"
    "=== 출처 추적성 (필수) ===\n"
    "- 입력의 ``event.sources`` 에 1차 출처 URL 목록이 있음.\n"
    "- 본문에서 *수치/날짜/구체 사실* 을 인용할 땐 가능하면 출처 URL 을 직접 본문에\n"
    "  '(출처: example.com)' 형식으로 표기하거나 cited_sources 에 정리.\n"
    "- 출처가 없는 추론은 '~라고 추정' / '~할 가능성' 같은 보수 표현으로 명시.\n\n"
    "=== 차트 (v4.4.0 — 메타데이터 + 본문 결합 + 신규 type 3종) ===\n"
    "- *수치 비교가 본문 이해에 결정적* 일 때만 emit. 사건당 0~3개가 적당.\n"
    "- 무관한 차트 박지 말 것 (mono guide §6 anti-pattern).\n"
    "- 차트 *직전* 단락에서 thesis 한 줄 미리 제시 (예: '...의존도가 평균의 4배\n"
    "  다 (아래 차트).'). 차트 *직후* 단락에서 패턴을 한 단계 해석. 차트 단독\n"
    "  emit 금지 — 본문 흐름 안에서만.\n"
    "- 섹션의 ``charts`` 배열에 차트 1개당 dict 1개. 형식 (v4.4.0):\n"
    "  ```json\n"
    "  {\n"
    '    \"type\": \"bar|donut|line|gantt|network|stacked|bubble|heatmap|dual_line|forecast|choropleth|candle|area|scatter|stacked_area|lollipop|slope|small_multiples|waterfall|range_bar|sankey\",\n'
    '    \"title\": \"차트 제목\",\n'
    '    \"subtitle\": \"한 줄 thesis — 제목과 다른 결론. 예: 동진 7.9는 OP 기준, 회계는 23.08\",\n'
    '    \"data\": [...],            // type 별 스키마 (아래 참조)\n'
    '    \"annotations\": [          // 선택. 최대 3개. (vline 2 + hline 1 등)\n'
    '      {\"kind\":\"vline\", \"x\":\"2024-09\", \"label\":\"Fed 첫 인하\", \"sublabel\":\"2024-09\"},\n'
    '      {\"kind\":\"hline\", \"y\":26.4, \"label\":\"동종 평균 PER\"},\n'
    '      {\"kind\":\"band\",  \"x_from\":\"2025-07\", \"x_to\":\"2025-12\", \"label\":\"박스권\"},\n'
    '      {\"kind\":\"point\", \"x\":\"2024-12\", \"y\":150, \"label\":\"전환점\"}\n'
    "    ],\n"
    '    \"source\": \"Bloomberg, KRX / 2026-04 종가 기준 · N=5\",\n'
    '    \"takeaway\": \"차트가 보여준 한 줄 인사이트 (선택)\",\n'
    '    \"note\": \"부가 설명 (선택, 더 긴 caption 용)\"\n'
    "  }\n"
    "  ```\n"
    "- annotations 사용 가이드:\n"
    "  · vline: 사건 트리거 (Fed 회의 / 위기 시점 / 정책 발표). *최대 2개*.\n"
    "  · hline: 평균선·목표치·임계값. *최대 1개*.\n"
    "  · band:  음영 영역 (침체기·박스권·위기 구간). *최대 1개*.\n"
    "  · point: 인플렉션 데이터 점 강조. *최대 2개*.\n"
    "  · 차트 1개에 4종 모두 박지 말 것 (산만). 합산 최대 3개.\n"
    "- subtitle 은 *제목과 다른 thesis*. '5종목 PER 비교' (제목) 와 '동진 7.9는\n"
    "  OP 기준 — 회계 PER 23.08' (subtitle) 같이 *서로 다른 정보*.\n"
    "- source 는 출처·시점·관측 N 항상 함께 (예: 'Bloomberg / 2026-04 / N=5').\n"
    "- takeaway 는 차트가 *보여준* 패턴의 한 줄 해석. 본문 단락의 thesis 와 중복\n"
    "  되면 생략 (양쪽 모두 같은 말 X).\n\n"
    "[type 별 data 스키마]\n"
    "기존 8종 (Tier 1):\n"
    "  · donut:   [{label, value:number, note?}]                   비중 비교 (*반드시 3개 이상, 균등 X*)\n"
    "             2 segment 도넛은 emit 금지 (CHART-AP-16). '기타' 같은 잡탕 segment 강제로 만들지 말 것 —\n"
    "             정보 손실 + subtitle 잉여. 비율 카드 또는 본문 한 문장으로 대체.\n"
    "  · bar:     [{label, value:number, note?}]                   순위·분포\n"
    "  · line:    [{x, y:number, event?}]                          시계열 추이 — *지수·환율·금리* 기본\n"
    "  · candle:  [{date, open, high, low, close, volume?, event?}]   일간 OHLC — *개별주* 전용 (삼성전자 등)\n"
    "             v5.2.0 신규. composer 가 직접 만들지 말 것 — available_time_series 의 OHLC 데이터만 사용.\n"
    "  · area:    [{x, y:number, event?}]                          line 의 그라데이션 변형 — *원자재·금* (WTI, 금)\n"
    "             v5.2.0 신규. line 과 데이터 shape 동일.\n"
    "  · gantt:   [{label, start, end, note?}]                     *사건 구간* (start ≠ end 가 ≥30%)\n"
    "             point-in-time 이벤트 모음 (모든 row 가 start==end) 은 emit 금지 (CHART-AP-15).\n"
    "             그 경우 본문 list 또는 line + event marker (point 에 event 라벨) 로.\n"
    "  · network: {nodes:[{id,label,group?}], links:[{source,target,type?}]}  관계도\n"
    "  · stacked: {scenarios:[{name, segments:[{label,value:number}]}]}  시나리오 × 행위자\n"
    "             (value 는 *양수 magnitude 만*. 부호 있는 점수면 bar 로)\n"
    "  · bubble:  [{label, x:number, y:number, size?:number}]      확률 × 영향\n"
    "  · heatmap: [{title, severity:'low'|'medium'|'high'}]        단계별 위험도\n\n"
    "신규 3종 (Tier 2 — v4.4.0):\n"
    "  · dual_line:  {                                                두 metric *상관관계* — 금리 vs 환율 등\n"
    '      \"left\":  {\"label\":\"원유\", \"unit\":\"$/bbl\", \"series\":[{x,y},...]},\n'
    '      \"right\": {\"label\":\"환율\", \"unit\":\"USD/KRW\", \"series\":[{x,y},...]}\n'
    "    }\n"
    "    좌·우 y축 분리. 두 시리즈가 *함께 변하는지* 보여줄 때만.\n\n"
    "  · forecast:   {                                                기준선 + 불확실성 — 시나리오 분석에\n"
    '      \"actual\":   [{x, y}, ...],          // 실측\n'
    '      \"forecast\": [{x, mid, low, high}, ...],  // 중앙선 + 신뢰구간\n'
    '      \"fork_at\":  \"2026-04\"               // 실측↔예측 경계\n'
    "    }\n"
    "    실측은 실선, 예측은 점선 + 음영 cone. 단순 추세 연장 X — *진짜 예측* 일 때만.\n\n"
    "  · choropleth: 국가별 색농도 지도 — 지정학·무역·금융 사건의 *국가간 통계 비교*\n"
    '    [{country_code:\"KR\", value:12.4}, {country_code:\"JP\", value:10.8}, ...]\n'
    "    + value_label (예: '원유 의존도 (%)') + scale ('linear'|'quantile'|'log')\n"
    "    country_code 는 ISO-3166-1 alpha-2 (KR, JP, US, CN, IN 등).\n\n"
    "신규 7종 (v5.2.14 — FT/Economist 스타일):\n"
    "  · scatter:  [{label, x:number, y:number, accent?:bool}]            라벨 산점도 (FT 좌측 스타일)\n"
    "              size 인코딩 없음 — 그것은 bubble. 국가/그룹 비교, 이상치 식별에.\n"
    "              ≥3 포인트. accent=true 면 강조색 (1개 권장, 비교 anchor).\n"
    "              + optional: x_label, y_label (축 캡션)\n\n"
    "  · stacked_area: {series:[{name, values:[{x,y}]}]}                  시계열 누적 영역 (FT 우측 스타일)\n"
    "              점유율 *연속 변화* (시점 ≥10). 시점이 이산 (4분기 등) → stacked.\n"
    "              ≤5 시리즈, 각 ≥5 포인트, 모든 시리즈 동일 x 격자 필요.\n\n"
    "  · lollipop: [{label, value:number}]                                 bar 의 우아한 대안\n"
    "              8-15 항목 (그 미만은 bar, 초과는 본문 + heatmap).\n"
    "              순위 차이가 큰 데이터에 적합. 첫 항목 자동 액센트.\n\n"
    "  · slope:    {left_label, right_label, items:[{label, a:number, b:number}]}  2 시점 비교\n"
    "              3-10 항목. b>a 면 자동 액센트 (상승). 순위 역전 시각화의 SSOT.\n"
    "              예: {left_label:'2020', right_label:'2025', items:[{label:'IT', a:14, b:24}, ...]}\n\n"
    "  · small_multiples: {panels:[{label, series:[{x,y}]}]}              4-9 패널 그리드 비교\n"
    "              같은 구조의 여러 그룹을 한 번에 비교 (4국 인플레이션 등).\n"
    "              각 패널 ≥5 포인트. 공통 y 도메인.\n\n"
    "  · waterfall: [{label, value:number, type:'total'|'pos'|'neg'}]      증감 누적 분해\n"
    "              첫·끝 row 는 *반드시* type='total' (시작값/종료값).\n"
    "              중간 row 는 pos (증가) / neg (감소). P&L brücke, GDP 기여도 분해.\n"
    "              ≥3 항목. value 는 절대값 magnitude (음수 표기 X — type='neg' 가 부호).\n\n"
    "  · range_bar: [{label, low:number, high:number}]                     두 값 사이 갭 (Dumbbell)\n"
    "              low < high 강제. 3-15 항목. 남녀 임금격차, min-max 범위 등.\n"
    "              + optional: low_label, high_label (legend)\n\n"
    "  · sankey:   {nodes:[{id, label, accent?:bool, value_label?:str}],   다단계 흐름 분해 (재무·수익성 분석)\n"
    "              links:[{source, target, value:number, negative?:bool}]}\n"
    "              재무제표 brücke (매출→COGS/판관비/R&D→영업이익), 세그먼트 매출\n"
    "              분해 (총매출→사업부→지역→마진), 자본 배분 (영업CF→배당/자사주/\n"
    "              CAPEX/M&A), EBITDA bridge 등. waterfall 보다 multi-stage 분배에\n"
    "              강함 (waterfall 은 1차원 시퀀스).\n"
    "              **재무·수익성 보고서면 이 차트가 *주연*. 본문이 '매출 →\n"
    "              사업부 → 비용 → 이익' 같은 흐름을 다루면 emit 거의 강제.**\n"
    "              구체 예 — 삼성전자 1Q 보고서: nodes=[총매출 133.9조 / DS /\n"
    "              모바일 / 디스플레이 / 가전 / 비용 / 영업이익 57.2조 (accent)],\n"
    "              links=[총매출→DS 70조, 총매출→모바일 38조, DS→영업이익 46조,\n"
    "              모바일→영업이익 4조, ...]. negative=true 는 영업적자 사업부.\n"
    "              가드: 노드 2-12, 링크 ≥1, source/target 가 nodes.id 존재,\n"
    "              self-loop 금지, DAG (순환 금지). 적자/손실 flow 는 negative=true\n"
    "              (빨간 색 자동). accent=true 면 강조 노드 (보통 최종 이익 노드).\n\n"
    "- 모든 차트는 mono guide 의 45° 패턴 + 단일 액센트. 색은 자동 적용.\n"
    "- *데이터가 비어있으면 차트 자체를 emit 하지 말 것* (charts 배열에 추가 금지).\n"
    "  · bar/donut/line/gantt/heatmap/candle/area: data 가 빈 배열이면 emit X\n"
    "  · network: data.nodes 가 2개 미만이면 emit X\n"
    "  · stacked: data.scenarios 가 빈 배열이면 emit X\n"
    "  · dual_line: left.series 또는 right.series 가 비면 emit X\n"
    "  · forecast: data.actual 이 2개 미만이면 emit X\n"
    "  · scatter: data 가 3 포인트 미만이면 emit X\n"
    "  · stacked_area: series 가 비거나 첫 시리즈 values <5 면 emit X\n"
    "  · lollipop: data 가 8 미만 또는 15 초과면 emit X (bar 또는 본문으로 대체)\n"
    "  · slope: items 가 3 미만 또는 10 초과면 emit X\n"
    "  · small_multiples: panels 가 4 미만 또는 9 초과면 emit X\n"
    "  · waterfall: 첫·끝 row 가 type='total' 이 아니면 emit X\n"
    "  · range_bar: 임의 row 의 low >= high 면 emit X\n"
    "  · sankey: nodes <2 또는 >12, links <1, 참조 깨짐 (source/target 미존재), self-loop, 순환 그래프면 emit X\n"
    "  · 모르는 수치를 *추정해서* 차트 만들지 말 것 — 진짜 출처 데이터만.\n\n"

    "[차트 type 결정 트리 — v5.2.14 신설, v5.4.3 보강]\n"
    "캔들/donut/bar 만 반복 emit 회귀 (~70%) 방지의 SSOT. 데이터 형태부터 시작:\n\n"
    "  0. 사건 카테고리가 *재무·수익성·기업 분석* 인가?\n"
    "     (event.category 가 '기업 재무' / '재무제표' / '실적' / '수익성' /\n"
    "      '기업 분석' / '재무 분석' / '...산업' + 본문이 매출·영업이익·\n"
    "      마진·세그먼트 분해를 다루는 경우)\n"
    "     → **반드시 sankey 또는 waterfall 중 *최소 1개* 보고서에 emit.**\n"
    "       · 1차원 분해 (시작값 → 증감 항목들 → 종료값): waterfall\n"
    "         예: '2024 영업이익 6.6조 → DS 흑자전환 +24.5조 → 모바일 -3조 →\n"
    "              디스플레이 +2조 → ... → 2026 1Q 영업이익 57.2조'\n"
    "       · 다단계 N→M 흐름 (매출 → 사업부/세그먼트 → 비용 → 이익): sankey\n"
    "         예: '총매출 → DS / 모바일 / 디스플레이 / 가전 → COGS / R&D / 판관비\n"
    "              → 영업이익 → 순이익 (적자 사업부는 negative=true 빨간 flow)'\n"
    "     v5.4.2 회귀 (삼성전자 1Q 보고서) — 본문이 명백히 재무 분해인데\n"
    "     composer 가 시계열 분기 (1번) 로 먼저 collapse 해 line/slope 만 박고\n"
    "     sankey/waterfall 누락. 이 step 0 가 *반드시 step 1 보다 먼저* 매칭됨.\n"
    "     시계열·추이는 여전히 emit OK, 단 분해 차트가 *함께* 1개 이상 있어야.\n\n"
    "  1. 시간축 있음?\n"
    "     ├─ 단일 시리즈 + OHLC 있음 → candle (line 금지)\n"
    "     ├─ 단일 시리즈 + 원자재/누적 부피 → area\n"
    "     ├─ 단일 시리즈 + 예측·신뢰구간 → forecast (line 금지)\n"
    "     ├─ 단일 시리즈 (그 외) → line\n"
    "     ├─ 두 시리즈 (다른 단위/비교 anchor) → dual_line\n"
    "     ├─ 시리즈 ≥3 + 합 의미 (점유율) → stacked_area (line 금지)\n"
    "     └─ 같은 구조 그룹 4-9개 → small_multiples\n"
    "  2. 지리 데이터 있음?\n"
    "     ├─ 경로/이동/마커 → embedded_map\n"
    "     └─ 지역별 값 (≥3 국가) → choropleth\n"
    "  3. 카테고리 비교? (시계열 X, 지리 X)\n"
    "     ├─ 카테고리 ≤8, 순위/크기 → bar\n"
    "     ├─ 카테고리 8-15, 격차 강조 → lollipop (bar 의 우아한 대안)\n"
    "     ├─ 2 시점 비교 (같은 카테고리 a vs b) → slope\n"
    "     ├─ 두 값 갭 (low/high) → range_bar (Dumbbell)\n"
    "     ├─ 시작값 → 증감 → 종료값 1차원 분해 → waterfall (P&L 스타일)\n"
    "     └─ 다단계 N→M 흐름 분배 (매출→segment→비용→이익) → sankey (재무 분해)\n"
    "  4. 구성비?\n"
    "     ├─ 단일 시점, 3-6 segment → donut (≤2 면 본문, ≥7 이면 bar)\n"
    "     └─ 이산 시점 다중 (4분기 등) → stacked\n"
    "  5. 다차원 관계?\n"
    "     ├─ 3 변수 (x, y, size 모두 의미) → bubble\n"
    "     ├─ 2 변수 + 라벨 (size 균일) → scatter (FT 좌측 스타일)\n"
    "     └─ 관계망 (노드-엣지) → network\n"
    "  6. 2D 격자 + 강도? → heatmap (≥4×4 권장)\n"
    "  7. 이벤트 일정 (start≠end 가 ≥30%)? → gantt\n\n"
    "[반-편향 (anti-bias) 가드 — line/bar/donut 으로 collapse 금지]\n"
    "  · 같은 보고서 안에 *같은 type 3개 이상* 박지 말 것 — 시각 단조.\n"
    "  · standard 모드면 *서로 다른 type 4개 이상* 박을 것을 권장 (강제 X).\n"
    "  · deep 모드면 *서로 다른 type 6개 이상* 권장.\n"
    "  · '시계열 데이터인데 안전하게 line' 회피 — 위 결정 트리의 OHLC / 예측 /\n"
    "    부피 분기를 *반드시 먼저* 점검할 것.\n"
    "  · '카테고리 비교인데 자동 bar' 회피 — 항목 ≥8 이면 lollipop, 2 시점이면\n"
    "    slope, 분해형이면 waterfall 가 더 적절한 경우가 많음.\n"
    "  · **재무·수익성 보고서인데 시계열 + bar 만** 회피 (v5.4.3 신설). 매출·\n"
    "    영업이익·세그먼트 분해 narrative 면 sankey/waterfall *최소 1개* 필수.\n"
    "    추이만 박고 분해 누락은 회귀 (삼성전자 1Q 보고서, line ×4 + slope +\n"
    "    bar + range_bar + forecast — sankey 0).\n\n"

    "=== 시계열 차트 (v5.2.0) — available_time_series ===\n"
    "입력에 ``available_time_series`` 가 있으면 orchestrator 가 KRX/FRED/ECOS/Yahoo\n"
    "에서 fetch 한 *실 OHLC 데이터*. 각 entry 는:\n"
    "  {instrument, source, code, unit, chart_type, start_date, end_date,\n"
    "   data: [{date:'YYYY-MM-DD', open, high, low, close, volume?}, ...]}\n\n"
    "★ 강제 규칙 (v5.2.0+, 예외 없음):\n"
    "  ① available_time_series 가 비어있지 않으면, 본문에서 그 instrument 들 중\n"
    "     1개 이상을 다루는 *모든 보고서* 는 *반드시 최소 1개 시계열 차트*\n"
    "     (line/candle/area) 를 emit. 0개 emit 절대 금지.\n"
    "  ② 가장 본문 narrative 의 핵심인 instrument 를 *첫 1~2번째 섹션* 의\n"
    "     charts 배열 *첫번째* 에 박음 (사건성 보고서일수록 강조).\n"
    "     예: '코스피 8000 돌파 + 폭락' narrative → sections[0].charts[0] 에\n"
    "         코스피 line 차트 (이벤트 일자 표시 + 폭락 지점 event 마커).\n"
    "  ③ '사건 보고서' (변동·급등·급락·폭락·돌파·붕괴 등 변동성 narrative) 는\n"
    "     관련 instrument *전부* 차트로 (예: 코스피·삼성·하이닉스 동시 사건 →\n"
    "     3개 차트 모두). 한 종목만 emit 하고 나머지 빠뜨리는 것 금지.\n\n"
    "차트 type 매핑 (각 series 의 chart_type 추천 *그대로 따름*):\n"
    "  - 지수·환율·금리 (코스피/코스닥/DXY/UST/국고채) → line\n"
    "  - 개별주 (삼성전자/SK하이닉스/...)            → candle\n"
    "  - 원자재 (WTI/금)                              → area\n\n"
    "데이터 mapping:\n"
    "  - line/area:  data 의 각 row 를 [{x: row.date, y: row.close}] 로 변환\n"
    "  - candle:     data 의 각 row 를 [{date, open, high, low, close}] 그대로 유지\n"
    "  - 절대 일간 OHLC 추정·생성 금지. available_time_series 의 row 만 사용.\n\n"
    "이벤트 마커:\n"
    "  - 본문에서 언급한 *날짜* 와 매치되는 data row 에 ``event: '한 줄 설명'``\n"
    "    필드 추가 (예: row.date='2026-05-15' + event='8000 첫 돌파, 장 마감 -6%').\n"
    "    charts.js 가 자동으로 번호 배지 + 하단 footnote 로 렌더.\n"
    "  - 사건 보고서의 변곡점·돌파·급락 일자에 *반드시* 이벤트 마커. 본문이\n"
    "    'XX가 YY% 폭락' 같은 단정 narrative 면 그 일자에 event 표시는 필수.\n\n"
    "주의:\n"
    "  - '데이터 있다고 무조건 차트 만들지 말 것' 룰은 *v5.2.0 이전*. v5.2.0+ 부터\n"
    "    available_time_series 가 채워진 시점에서 이미 ContextAnalyst 가\n"
    "    *본문 다룸* 으로 판정한 것 — 차트 emit 이 기본값. 차트 안 만들면 회귀.\n"
    "  - orchestrator 의 ``_ensure_time_series_chart`` 안전망이 composer 가\n"
    "    빠뜨려도 첫 섹션에 자동 보충. 하지만 *composer 가 직접 정확한 위치·\n"
    "    이벤트 마커와 함께 emit 하는 것이 1순위*. hook 은 fallback.\n\n"
    "=== 지도 (v4.2.0 — 지리적 사건일 때만) ===\n"
    "- 사건이 *명백히 지리적* 일 때만 (해협 봉쇄 / 무역 회랑 / 분쟁 지역 등).\n"
    "- 보고서 레벨 1개 (top-level ``embedded_map``). 섹션별 지도 없음.\n"
    "- 형식:\n"
    "  ```json\n"
    "  {\n"
    '    \"center\": [경도, 위도],\n'
    '    \"zoom\": 3.0,\n'
    '    \"markers\": [{\"id\":\"hormuz\",\"name\":\"호르무즈\",\"lng\":56.4,\"lat\":26.6,\"highlight\":true}],\n'
    '    \"arcs\": [{\"from_id\":\"hormuz\",\"to_id\":\"singapore\",\"highlight\":true,\"label\":\"원유 회랑\"}],\n'
    '    \"legend\": [{\"label\":\"중점 회랑\",\"kind\":\"line\",\"highlight\":true}]\n'
    "  }\n"
    "  ```\n"
    "- d3-geo + TopoJSON 베이스맵 위에 mono 톤으로 렌더 (외부 타일 의존 없음).\n\n"
    "=== 사진 (v5.4.0 — 출처 기사의 og:image) ===\n"
    "- 입력에 ``available_images`` 가 있을 때만 사용 가능 — orchestrator 가\n"
    "  context.sources URL 각각에서 og:image / og:title / og:description /\n"
    "  publisher 를 추출해 채운 list. 비어있으면 사진 emit 절대 X.\n"
    "- 각 entry 형식:\n"
    "  ``{source_url, image_url, title, description, publisher}``\n"
    "  · source_url: 원문 기사 URL (ContextAnalyst 가 인용한 출처)\n"
    "  · image_url: og:image 절대 URL (FT/Reuters/한겨레 등 매체의 lead 사진)\n"
    "  · title / description: 원문 기사의 og:title / og:description\n"
    "  · publisher: 도메인 기반 표시명 (예: 'FT', 'Reuters', '한겨레')\n\n"
    "[사진 선택 원칙 — 매우 보수적]\n"
    "  1. **본문 narrative 와 직접 맥락이 닿는 사진만**. 출처 기사의 og:image 가\n"
    "     본문이 다루는 사건/인물/장소를 담고 있는지 og:title 로 검증. title 이\n"
    "     본문 주제와 무관하면 (예: 매체 메인 페이지의 generic image) emit X.\n"
    "  2. **추정 금지**. 사진에 *누가 / 무엇이* 찍혀 있는지 모르면 (og:title 이\n"
    "     사진 주제를 명시 안 함) 사진 자체를 emit X. WRITE-AP-5 (추정 단정)\n"
    "     원칙. 캡션에서 사진의 인물·장소·행위를 *지어내지* 말 것.\n"
    "  3. **품질**: 사용자가 광고/로고/매체 placeholder 이미지가 와도 분간 못 함\n"
    "     — title 에 'logo' / 'newsletter' / 'subscribe' / 매체 이름만 있는\n"
    "     경우는 placeholder 일 가능성 — emit X.\n\n"
    "[배치]\n"
    "  - hero_image (보고서 최상위, 1장만): 보고서 narrative 의 *핵심 인물 /\n"
    "    장면* 사진. 보고서당 0~1 개. 자신 없으면 null.\n"
    "    형식: ``{image_url, caption, credit, source_url, alt}``\n"
    "  - 섹션 inline images (sec.images 배열): 그 섹션 본문 흐름에 맞는 사진.\n"
    "    섹션당 0~1 개 (드물게 2). 보고서 전체 0~3 개. 사진 없는 섹션이 디폴트.\n"
    "    형식: ``[{image_url, caption, credit, source_url, alt}]``\n\n"
    "[캡션 + credit 작성 — FT 스타일]\n"
    "  - caption: 1 문장. 사진이 *보여주는 것* 을 본문 흐름과 잇는 한 문장.\n"
    "    · 좋음: '파월 의장은 기자회견 내내 데이터 의존을 일곱 차례 반복했다.'\n"
    "      (사진=파월 기자회견 / 본문이 다루는 핵심 행위 묘사)\n"
    "    · 나쁨 (추정): '그는 그날 무거운 표정으로 입을 열었다.' (찍힌 표정을\n"
    "      안 봤음에도 묘사 — 추정 단정. WRITE-AP-5)\n"
    "    · 나쁨 (반복): '아래 사진은 파월 의장이다.' (본문이 이미 말한 정보 X)\n"
    "    · 평어체 (~다 / ~한다 / ~이다). 한국어 editorial 톤. mark down 강조 X.\n"
    "    · 가능하면 사진의 *날짜 / 장소* 를 og:description 에서 가져와 caption\n"
    "      시작부에 박음 (예: '5월 16일, 워싱턴 — ...').\n"
    "  - credit: ``© Publisher`` 형식. publisher 는 available_images 의 값.\n"
    "    composer 가 임의로 'AP / Getty' 같은 진짜 사진 출처 매체로 바꾸지 말 것\n"
    "    — og:image 의 원래 소유자를 모름. 인용한 기사의 publisher 만 사용.\n"
    "  - alt: 접근성 텍스트. 사진의 시각 정보를 짧게 (예: '단상에서 발언하는\n"
    "    Fed 의장의 정면 사진'). 캡션을 그대로 복붙하지 말 것.\n"
    "  - source_url: available_images 의 source_url 그대로. 클릭 시 원문 기사로\n"
    "    이동하는 용도.\n\n"
    "[Anti-pattern]\n"
    "  - available_images 에 없는 사진 URL 임의로 생성 X (LLM 환각 차단).\n"
    "  - hero_image 와 sec.images 에 *같은 image_url* 중복 사용 X.\n"
    "  - title 이 광고 / SEO / 매체 보일러플레이트면 emit X. 본문과 맥락 닿은\n"
    "    1~2 장만 신중하게.\n\n"
    "=== 정형 블록 (선택, 보수적) ===\n"
    "- 풍부한 정형 데이터를 본문 외에 따로 보여줘야 할 때만.\n"
    "- ``embedded_blocks``: actor_cards / scenario_table / timeline / flow_chain /\n"
    "  watchlist / data_series / risk_matrix / decomposition / counter_hypothesis /\n"
    "  callout. v4.2.0 Tier 4 에선 데이터 출처 (players/scenarios 등) 가 비어있어\n"
    "  대부분 렌더 안 됨. 본문에 풀어쓰는 것을 기본으로.\n\n"
    "=== 모순 / 반대 가설 (Anti-pattern #5) ===\n"
    "- contradictions 배열에 명시적 list 로 보존. 본문 안에서도 한 섹션은 모순/\n"
    "  반대 가설을 다루는 것을 권장.\n"
    "- 어느 쪽 손을 들어줬는지, 패배한 입장은 어떤 조건에서 살아나는지 명시.\n"
    "- **resolution 은 판단으로 단락을 닫는다 (WRITE-AP-9)**: 독자가 의심이 아니라\n"
    "  분석가의 착지로 끝나도록, 어느 쪽에 무게를 두는지 *결론적 문장* 으로 쓴다.\n"
    "  패배 입장이 살아나는 조건은 그 뒤에 붙인다. side_a/side_b 는 각각 완결된\n"
    "  문장으로 (템플릿이 '그러나' 로 잇는다).\n"
    "- **contradictions_heading 을 *내용에 맞게* 직접 짓는다**: 쟁점의 본질을 한\n"
    "  구절로 (예: '정전이냐 잠복이냐', '안전판의 한계', '인하인가 경보인가').\n"
    "  '봉합하지 않은 충돌' / '모순' / '반대 관점' 같은 *정적 메타-라벨 금지* —\n"
    "  보고서마다 달라야 하고, 결론을 회피하는 인상을 줘선 안 된다 (WRITE-AP-9).\n\n"
    "=== 시간 흐름도 (timeline_flow, 선택 — v5.5.2) ===\n"
    "- 감시 신호 직후에 보고서의 *시간 척추* 가 렌더된다 (과거→현재→미래 capstone).\n"
    "- 비워도 된다 — 그러면 context.timeline(과거) + watch_signals(미래) 로 자동 조립.\n"
    "- 윤색하고 싶으면 timeline_flow.past 에 *서사 아크에 맞는 milestone 라벨* 을\n"
    "  (raw 사건명보다 의미 중심으로), future 에 *시나리오 분기점* 을 날짜와 함께.\n"
    "- **미래는 토픽이 받쳐줄 때만** (예측 가능한 사건). 과신 금지 — 렌더가 점선/\n"
    "  '예상' 으로 투사 표시하니 단정하지 말 것. 미정 토픽은 future 비워두면 된다.\n\n"
    "=== 감시 신호 (Watchlist 통합) ===\n"
    "- watch_signals 배열 — Watchlist 시스템이 SQLite 에 INSERT.\n"
    "- 형식: [{signal, description, indicates, deadline?, icon?}]\n"
    "  · signal: 짧은 식별자 (예: 'Fed 6월 FOMC 점도표')\n"
    "  · description: 신호 설명 한 문장\n"
    "  · indicates: 이 신호가 어느 시나리오 분기를 가리키는지\n"
    "  · deadline: 'YYYY-MM-DD' 또는 '6월 중' 등 (생략 가능)\n"
    "  · icon: 이모지 1~2자 (생략 가능)\n\n"
    "=== broadcast_summary (X 구독자용 요약, v5.6.1) ===\n"
    "보고서를 안 읽는 X(트위터) 구독자가 이 글만 보고도 맥락·핵심·시사점을 얻게 쓴다.\n"
    "  · 해요체와 습니다체를 자연스럽게 *섞어* 쓴다 (한 톤으로 고정 금지).\n"
    "  · 한 문단은 최대 2문장. 문단마다 빈 줄(\\n\\n)로 분리한다.\n"
    "  · 5~6개의 짧은 문단. 라벨/제목/이모지/불릿/머리말 금지 — 본문만.\n"
    "  · 무슨 일 → 왜 그런가 → 그래서 무엇(시사점) 흐름. 핵심 숫자는 문장에 자연스럽게 녹인다 (표 금지).\n"
    "  · AI 티 절대 금지: '안녕하세요/이 보고서는/결론적으로/요약하자면' 류 메타·상투어, 과한 존댓말 반복 금지.\n"
    "  · 뉴스레터 잘 쓰는 사람이 아는 사람에게 설명하듯 — 친절하지만 군더더기 없이.\n"
    "  · 맨 마지막 문단은 전체 보고서로 부드럽게 안내하는 한 문장으로 닫는다 (예: '자세한 건\n"
    "    보고서에 정리해 뒀어요', '나머지 맥락은 본문에서 이어집니다', '숫자와 근거는 보고서에서\n"
    "    더 볼 수 있어요'). 단 *매 보고서마다 다른 표현* 으로 — 똑같은 마무리 문구를 반복하면\n"
    "    AI 티가 나므로 그때그때 자연스럽게 바꾼다.\n\n"
    "=== JSON 응답 형식 (반드시 준수) ===\n"
    "★★★ **응답은 반드시 ``{`` 한 글자로 시작한다.** ★★★\n"
    "코드펜스 ```json 직후 첫 비공백 글자가 ``{`` 가 아니면 그 응답은 *전부 무효*\n"
    "다. 아래 예시의 *중간 줄* (예: ``      \"prose\":`` / ``      \"side_a\":`` /\n"
    "``      \"lede\":``) 부터 시작하지 말 것. 예시를 외워 깊은 줄부터 출력하면\n"
    "응답이 폐기되고 보고서가 minimal fallback 으로 격하된다. 반드시 최상위 ``{``\n"
    "→ ``\"headline\":`` → ``\"deck\":`` → ``\"sections\": [`` 순으로 *처음부터* 짠다.\n"
    "응답 마지막 글자는 ``}`` (선택적으로 그 뒤에 닫는 ``` ).\n\n"
    "```json\n"
    "{\n"
    '  "headline": "사건의 본질을 가리키는 한 줄 (~30자)",\n'
    '  "deck": "부제 1~2 문장 (~80자). 헤드라인이 못 담은 핵심.",\n'
    '  "sections": [\n'
    "    {\n"
    '      "heading": "섹션 제목",\n'
    '      "kicker": "도입구 한 줄 라벨 (예: 지정학적 변곡 / 1)",\n'
    '      "lede": "긴 도입 1~3 문장 (선택, 보고서 첫 1~2 섹션만 권장)",\n'
    '      "prose": "본문. 단락 사이는 \\n\\n. 평어체 (~다). 마크다운 강조 금지.",\n'
    '      "dropcap": false,\n'
    '      "analogy": null,                 // 또는 {"title":"...", "body":"..."}\n'
    '      "fact_grid": [],                 // 또는 [{label, value, sublabel?}, ...]\n'
    '      "charts": [\n'
    "        {\n"
    '          \"type\": \"donut\",\n'
    '          \"title\": \"호르무즈 의존 비중\",\n'
    '          \"data\": [\n'
    '            {\"label\":\"한국\",\"value\":12,\"note\":\"원유\"},\n'
    '            {\"label\":\"일본\",\"value\":11},\n'
    '            {\"label\":\"기타\",\"value\":77}\n'
    "          ]\n"
    "        }\n"
    "      ],\n"
    '      "images": [\n'
    "        {\n"
    '          \"image_url\": \"https://...\",                  // available_images 의 image_url 그대로\n'
    '          \"caption\": \"5월 16일, 워싱턴 — 파월 의장은 기자회견 내내 데이터 의존을 일곱 차례 반복했다.\",\n'
    '          \"credit\": \"© Reuters\",                        // © + publisher\n'
    '          \"source_url\": \"https://reuters.com/...\",      // 원문 기사 URL\n'
    '          \"alt\": \"단상에서 발언하는 Fed 의장의 정면 사진\"\n'
    "        }\n"
    "      ],\n"
    '      "footnotes": [\n'
    "        {\n"
    '          \"term\": \"rate limit premium\",\n'
    '          \"explanation\": \"처리 한도를 평소보다 높여 달라고 요청할 때 추가로 내는 웃돈을 가리킨다.\"\n'
    "        }\n"
    "      ],\n"
    '      "embedded_blocks": [],\n'
    '      "pull_quote": "강조 인용 한 문장 (생략 가능)"\n'
    "    }\n"
    "  ],\n"
    '  "closing": "에필로그 1~2 문장 (생략 가능).",\n'
    '  "embedded_map": null,\n'
    '  "hero_image": null,                          // 또는 {image_url, caption, credit, source_url, alt}\n'
    '  "watch_signals": [\n'
    "    {\n"
    '      \"signal\": \"Fed 6월 FOMC 점도표\",\n'
    '      \"description\": \"추가 인하 시그널 여부\",\n'
    '      \"indicates\": \"기준선 vs 인하 가속 시나리오 분기\",\n'
    '      \"deadline\": \"2026-06-18\",\n'
    '      \"icon\": \"📊\"\n'
    "    }\n"
    "  ],\n"
    '  "contradictions_heading": "이 모순 섹션의 판단형 제목 (예: 정전이냐 잠복이냐). 정적 메타-라벨 금지",\n'
    '  "contradictions": [\n'
    "    {\n"
    '      \"side_a\": \"관점 A — 완결된 문장\",\n'
    '      \"side_b\": \"반대 관점 B — 완결된 문장\",\n'
    '      \"evidence\": \"양 관점이 충돌하는 데이터/논거 (생략 가능)\",\n'
    '      \"resolution\": \"판단으로 착지: 어느 쪽에 무게 + 패배 입장 살아나는 조건\"\n'
    "    }\n"
    "  ],\n"
    '  "timeline_flow": {\n'
    '    \"heading\": \"흐름도 제목 (선택, 예: 사건의 궤적)\",\n'
    '    \"past\": [{\"date\":\"YYYY-MM-DD\",\"label\":\"과거 milestone 한 구절\",\"note\":\"\"}],\n'
    '    \"future\": [{\"date\":\"YYYY-MM-DD\",\"label\":\"향후 분기점\",\"branch\":\"어느 시나리오\"}]\n'
    "  },\n"
    '  "confidence_summary": "출처 다양성/신선도/확신도 한 줄 자유 평가",\n'
    '  "confidence_score": 0.0~1.0,\n'
    '  "broadcast_summary": "broadcast_summary 지침대로 — 5~6개 짧은 문단, 해요/습니다 혼합, 문단당 2문장 이내, 라벨 없이 본문만"\n'
    "}\n"
    "```\n"
    "JSON 만 출력. 추가 설명 텍스트 금지.\n"
)


# V6 Phase V6-2 — 사실 규율 블록 (opt-in, V6_FACT_PROMPT). SYSTEM_PROMPT 에 *직교*
# 추가 (V5 어조·시각 지시와 충돌 없음). 2026-06-03 일일 브리핑 회귀(WRITE-AP-11/14~21)를
# 작성 단계에서 선제 차단. flag OFF 면 미주입 → compose 프롬프트 byte-equal.
_FACT_DISCIPLINE_BLOCK = (
    "\n\n=== 사실 규율 (V6 — 최우선, 문체보다 사실) ===\n"
    "아래는 사실 정확성 규율이다. 생생함·문체보다 우선한다. 출처 없는 생생함은 과장이다.\n"
    "1) 시장 수치(지수·환율·주가·등락률)는 입력 time_series 의 단일 소스 값만 쓴다. "
    "값이 없으면 그 수치를 *생략* — 기억·추정으로 지어내지 말 것 (WRITE-AP-15).\n"
    "2) 시계열·시장 수치엔 시점 라벨을 붙인다('직전 정규장 종가', '장중', '주간거래 종가'). "
    "'직전 반응' 처럼 모호한 근접 단정 금지.\n"
    "3) 출처에 없는 특정 수치(년수·개수·%·임계선)를 단정하지 말 것. 근거가 뒷받침하는 "
    "표현으로만. 트레이딩 임계선은 산출 근거가 없으면 제시 금지.\n"
    "4) 대형 수치엔 scope(단위·전체/부분)를 명시한다. '130만' 단독 금지 → '랙 전체 130만'.\n"
    "5) 신규성: 출처 작성일과 사건일이 다르면 '오늘 발표/방금' 류 단정 금지. 발행일"
    "(publication_date) 기준으로 시점을 환산하고, 미래 카운트다운(D-N·'사흘 앞')도 "
    "발행일↔사건일 실제 차이로 직접 센다 (WRITE-AP-11/14).\n"
    "6) 한쪽(정부·군·정치 행위자)의 주장은 사실로 단정하지 말고 '...측은 주장했다'로 "
    "귀속한다 (WRITE-AP-16).\n"
    "7) 인과는 중간단계를 생략하거나 강도를 과장하지 말 것. 불확실하면 '기여했을 수 있다/"
    "압박 요인/간접 영향'으로 헤지 (WRITE-AP-17).\n"
    "8) 별개 행사·사건을 하나로 혼동하지 말 것(예: 컴퓨텍스 ↔ GTC Taipei) (WRITE-AP-18).\n"
    "9) 한 방향 서사로 몰지 말고 반대 관점·반증을 함께 다룬다 (WRITE-AP-19). 제목과 본문의 "
    "확정 강도를 일치시킨다 (WRITE-AP-20).\n"
    "10) 신뢰도 %를 독자에게 노출하지 말 것 (WRITE-AP-21). 목록은 전체를 단정하지 말고 "
    "'대표 몇 + 등'으로.\n"
)


# V7 Track B — 서사 단계 라벨 블록 (opt-in, V7_SCROLL_ARC). 각 섹션에 기/승/전/결
# 1자 라벨을 emit — 스크롤 아크 배경(起承轉結 워터마크)의 섹션 매핑에만 쓰인다.
# 누락·오기는 ComposedSection validator 가 "" 로 회복 → 위치 기반 폴백 (AP-V7-4).
# flag OFF 면 미주입 → compose 프롬프트 byte-equal.
_SCROLL_ARC_BLOCK = (
    "\n\n=== 서사 단계 라벨 (V7 scroll arc) ===\n"
    "각 sections[i] 객체에 \"narrative_phase\" 필드를 추가하라 — 값은 \"기\"|\"승\"|"
    "\"전\"|\"결\" 중 1자.\n"
    "- 기(사건 제시) → 승(전개·심화) → 전(쟁점·반전) → 결(전망·착지) 순서를 따르고,\n"
    "  단계는 섹션 순서에서 *되돌아가지 않는다* (예: 전 다음에 승 금지).\n"
    "- 첫 섹션은 \"기\". 이 필드는 페이지 배경 연출에만 쓰이며 본문 내용·문체에 영향을\n"
    "  주지 않는다 — 본문을 이 라벨에 맞춰 변형하지 마라.\n"
)


# V7 Track C — 기준시점 계약 블록 (opt-in, V7_REF_FRAME). 작성 단계에서 "옛 날짜의
# 정확한 수치" 채택 자체를 차단 (WRITE-AP-22, REFACTOR_V7_PLAN.md §3.4). flag OFF
# 면 미주입 → compose 프롬프트 byte-equal.
_REF_FRAME_BLOCK = (
    "\n\n=== 기준시점 계약 (V7 — reference_frame) ===\n"
    "입력에 ``reference_frame.instruments`` 가 있으면, 시장 수치(지수·환율·주가)는 각\n"
    "종목의 ``last_available_date`` 데이터를 *기본 시점* 으로 쓴다 (WRITE-AP-22).\n"
    "- 그보다 옛 날짜의 값을 인용할 때는 반드시 절대 날짜를 명기하고, 왜 그 시점을\n"
    "  쓰는지(예: 사건 당일 종가 비교)가 문장에 드러나야 한다.\n"
    "- '현재/지금/최근' 으로 서술하는 시장 수치는 last_available_date 의 값만 허용.\n"
    "- 옛 날짜의 수치가 사실로서 정확해도, 무표기로 쓰면 시점 오류다.\n"
)


class NarrativeComposer:
    """Opus 4.7 단일 콜로 보고서를 자유 형식으로 작성.

    Orchestrator 가 deep 모드에서 ``synthesis_judge`` 직후 호출.
    실패 시 ``compose()`` 가 ``None`` 반환 → 호출자가 폴백 archetype 으로 재라우팅.
    """

    # Opus 4.7 모델 ID. config.model_name 이 4.6 이라도 composer 만 4.7 사용.
    COMPOSER_MODEL: str = "claude-opus-4-7"
    # v4.5.4: mode 별 분기. 이전엔 8192 단일 → deep 보고서 본문 중간 절단 회귀.
    # Opus 4.7 출력 한도가 충분히 크므로 deep 은 32K. fast 는 짧은 응답 권장.
    # v5.5.11: 한도 1.5배 확장. 사용자 요청 — "그 길이까지 가야 할 내용에 더 충실"
    # 모델은 한도의 자연 sweet spot (보통 60~80%) 으로 출력하므로 한도 확장이 곧
    # *모든* 보고서가 길어진다는 뜻이 아님. 분량 더 필요한 주제만 더 깊게 다룰
    # 여지가 생김. v4.5.4 → v5.5.11:  fast 12K→18K / standard 20K→30K / deep 32K→48K.
    MAX_TOKENS_BY_MODE: dict[str, int] = {
        "fast": 18000,
        "standard": 30000,
        "deep": 48000,
    }
    MAX_TOKENS: int = 48000  # 기본값 (mode 정보 없을 때)

    # v5.5.9 — composer 복원력. CLI 가 degraded 응답(짧음/잘림/prose)을 줘 파싱이
    # None 이 되거나, 호출이 hang/timeout 날 때 보고서 전체가 confidence-0 fallback
    # 으로 격하되던 회귀 대응. CLI 무한 대기 차단(타임아웃) + 1회 재시도.
    # 정상 composer 는 1~3분 — degraded 시 10분+ hang 관측됨.
    # v5.6.6 — deep 한도 540→900 상향. CAPEX/실적류 큰 deep 보고서가 540s 안에 못
    # 끝나 두 번 다 timeout → 부분 폐기 → 0% fallback 회귀 (Duration 1306s = 540+540+ctx
    # 더블 timeout 의 산술 증거). timeout 시 부분 출력을 살리므로(아래) 한도 초과해도
    # 완성 섹션은 건진다. 정상 composer 는 1~3분 — 900s 는 degraded 안전망.
    CLI_TIMEOUT_BY_MODE: dict[str, float] = {
        "fast": 300.0,
        "standard": 480.0,
        "deep": 900.0,
    }
    COMPOSE_MAX_ATTEMPTS: int = 2          # 최초 1 + 재시도 1 (timeout 은 부분 살린 뒤 재시도 X)
    COMPOSE_RETRY_BACKOFF_S: float = 4.0   # attempt N 전 대기 = backoff * (N-1)

    def __init__(self, config: Config) -> None:
        self.config = config
        self._api_client: object | None = None
        self.telemetry: Optional[RunTelemetry] = None
        if not config.use_cli_mode:
            import anthropic
            self._api_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def _compose_system_prompt(self) -> str:
        """compose 용 system prompt — V6_FACT_PROMPT 켜지면 사실 규율 블록을 직교 추가.

        flag OFF 면 모듈 SYSTEM_PROMPT 그대로 → ``_call_cli(system_prompt=SYSTEM_PROMPT)``
        는 미지정(None) 경로와 byte-equal (full_prompt 동일).
        """
        prompt = SYSTEM_PROMPT
        if getattr(self.config, "enable_fact_prompt", False):
            prompt += _FACT_DISCIPLINE_BLOCK
        if getattr(self.config, "enable_ref_frame", False):
            prompt += _REF_FRAME_BLOCK
        if getattr(self.config, "enable_scroll_arc", False):
            prompt += _SCROLL_ARC_BLOCK
        return prompt

    async def compose_unified(
        self,
        context: ContextAnalysis,
        mode: str = "standard",
        parent_context: ParentContext | None = None,
    ) -> ComposedReport | None:
        """v4.0.0 Tier 4 — ContextAnalysis 만 받아 *단독 분석 + 작성*.

        이전 ``compose()`` 는 7개 분석가 결과를 받아 편집만 했음. 본 메서드는
        composer 가 행위자/구조/시나리오/모순 분석까지 *모두* Opus 4.7 단일 호출에서
        수행. orchestrator 가 v4.0.0 부터 본 경로를 호출.

        v5.1.1 — ``parent_context`` 가 주어지면 payload 에 ``followup`` 필드 주입.
        composer 가 부모 시나리오 중 어느 가지가 실현 중인지 판정하고, 그 가지에서
        다시 분기를 생성. 부모와 새 시나리오 간 모순은 봉합하지 말고 contradictions
        에 명시 (Anti-pattern #5).
        """
        user_payload = self._build_unified_payload(context, mode, parent_context)
        # V7 Track C — 기준시점 계약 데이터 주입 (flag OFF = payload byte-equal).
        if getattr(self.config, "enable_ref_frame", False):
            from src.factcheck.reference_frame import build_reference_frame
            frame = build_reference_frame(context)
            if frame.get("instruments"):
                user_payload["reference_frame"] = frame
        user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        # v5.5.9 — 복원력: CLI 가 degraded/짧은/잘린 응답을 줘 _parse_response 가 None 인
        # 경우(returncode 0 이지만 파싱 불가) + 호출 자체 실패/timeout 시 *재시도*.
        # rate-limit 비정상 종료가 아니라 "성공했는데 쓸 수 없는 응답" 회귀라 재시도 안전.
        timeout_s = self.CLI_TIMEOUT_BY_MODE.get(mode, 360.0)
        sys_prompt = self._compose_system_prompt()
        composed = None
        for attempt in range(1, self.COMPOSE_MAX_ATTEMPTS + 1):
            try:
                if self.config.use_cli_mode:
                    raw = await self._call_cli(
                        user_message, timeout_s=timeout_s, system_prompt=sys_prompt,
                    )
                else:
                    raw = await self._call_api(
                        user_message, mode=mode, system_prompt=sys_prompt,
                    )
            except _ComposerTimeout as e:
                # v5.6.6 — timeout 으로 잘린 부분 출력을 살린다. 완성 섹션이 1개 이상이면
                # 그대로 사용하고 *재시도하지 않는다* (재시도해도 또 timeout — 시간 2배 낭비).
                salvaged = self._parse_response(e.partial) if e.partial else None
                if salvaged is not None and salvaged.sections:
                    composed = salvaged
                    if not composed.confidence_summary:
                        composed.confidence_summary = (
                            "생성이 제한 시간 내 완료되지 않아 마지막 일부가 생략됐을 수 있음."
                        )
                    logger.warning(
                        "[unified_composer] attempt %d timed out; using salvaged "
                        "partial (%d sections)", attempt, len(composed.sections),
                    )
                    break
                logger.warning(
                    "[unified_composer] attempt %d/%d timed out; nothing salvageable",
                    attempt, self.COMPOSE_MAX_ATTEMPTS,
                )
                break  # 재시도해도 또 timeout
            except Exception as e:
                logger.warning(
                    "[unified_composer] LLM call failed (attempt %d/%d): %s",
                    attempt, self.COMPOSE_MAX_ATTEMPTS, e,
                )
                raw = None
            else:
                if raw is not None:
                    composed = self._parse_response(raw)
                    if composed is not None:
                        break
                    logger.warning(
                        "[unified_composer] parse returned None (attempt %d/%d): "
                        "raw=%d chars, head=%r",
                        attempt, self.COMPOSE_MAX_ATTEMPTS, len(raw), raw[:300],
                    )
            if attempt < self.COMPOSE_MAX_ATTEMPTS:
                await asyncio.sleep(self.COMPOSE_RETRY_BACKOFF_S * attempt)
        if composed is None:
            return None
        # v4.0.0: chart_catalog 가 비었으니 embedded_charts 도 빈 list 로 강제 (검증 layer).
        composed = self._validate_references(composed, chart_catalog=[])
        # v5.6.7 — AI 가 인지되는 기호(마크다운 강조 / em·en dash) 결정적 제거. 사용자
        # 최우선 규칙. 프롬프트 지시만으론 LLM 이 100% 안 지키므로 출력 후처리로 강제.
        self._sanitize_symbols(composed)
        logger.info(
            "[unified_composer] Composed: %d sections, headline=%r, "
            "watch_signals=%d, contradictions=%d, conf=%.2f, followup=%s",
            len(composed.sections), composed.headline[:40],
            len(composed.watch_signals), len(composed.contradictions),
            composed.confidence_score, parent_context is not None,
        )
        return composed

    @staticmethod
    def _build_unified_payload(
        context: ContextAnalysis,
        mode: str,
        parent_context: ParentContext | None = None,
    ) -> dict:
        """v4.0.0 Tier 4 — ContextAnalysis + mode → composer 입력.

        멀티 에이전트 시절의 풍부한 입력 (players/dynamics/chain_reaction/...) 없이
        1차 사실 자료만 제공. composer 가 그 위에서 분석을 수행.

        v5.2.9: persona dict 채널 폐기 — 본문 문체 SSOT 는 SYSTEM_PROMPT 안에 인라인
        + docs/REPORT_STYLE_GUIDE.md 참조. payload 에 persona 필드 더 이상 안 들어감.

        v5.1.1: ``parent_context`` 가 있으면 ``followup`` 필드 추가 — composer 가 부모
        시나리오 / 발화 신호를 인지하고 분기 잇기 작업 수행.
        """
        # v5.6.4 — 발행일(오늘) 주입. composer 가 event.date 와 비교해 시간 거리를
        # 본문에 명시할 수 있게 (WRITE-AP-11).
        # v5.7.0 — KST 기준. naive datetime.now() 는 UTC VM 에서 하루 어긋나
        # publication_date 가 전날로 박혔다 (제목·본문 5/30 회귀의 원인).
        payload: dict = {
            "mode": mode,
            "publication_date": today_kst(),
            "event": {
                "name": context.event_name,
                "category": context.category,
                "date": context.date,
                "summary": context.summary,
                "background": context.background,
                "key_figures": context.key_figures,
                "timeline": context.timeline,
                "sources": context.sources,
            },
        }
        # v5.4.0 — 사진 후보 풀 주입. orchestrator 가 sources URL 에서 추출한
        # og:image / og:title / og:description / publisher. composer 가 본문
        # 흐름에 맞는 것을 골라 hero_image / 섹션 images 로 emit.
        if context.available_images:
            payload["available_images"] = [
                {
                    "source_url": img.source_url,
                    "image_url": img.image_url,
                    "title": img.title,
                    "description": img.description,
                    "publisher": img.publisher,
                }
                for img in context.available_images
            ]
        if parent_context is not None:
            sig = parent_context.triggering_signal
            payload["followup"] = {
                "is_followup_report": True,
                "parent_report_id": parent_context.parent_report_id,
                "parent_report_url": parent_context.parent_report_url,
                "parent_event_description": parent_context.parent_event_description[:500],
                "parent_scenarios": parent_context.parent_scenarios,
                "triggering_signal": {
                    "signal_id": sig.signal_id,
                    "description": sig.description,
                    "measurement": sig.measurement,
                    "direction": sig.direction,
                    "deadline": sig.deadline,
                    "follow_up_action": sig.follow_up_action,
                },
                "chain_depth": parent_context.chain_depth,
                "instruction": (
                    "이 보고서는 위 부모 보고서의 후속이다. 부모 시나리오 중 어느 가지가 "
                    "실현 중인지 판정하고, 그 가지에서 다시 분기를 생성하라. 부모 시나리오와 "
                    "새 시나리오 간 모순이 있으면 봉합하지 말고 contradictions 에 명시. "
                    "새 watch_signals 는 부모와 다른 분기점/시간축을 가리킬 것."
                ),
            }
        return payload

    # ------------------------------------------------------------------
    # V6 Phase V6-3 — 사실 보완 (Codex 지시 → Opus 재작성, AP-V6-1/11)
    # ------------------------------------------------------------------

    REVISE_SYSTEM_PROMPT: str = (
        "너는 이 시장·지정학 보고서를 쓴 편집장(Opus)이다. 외부 팩트체크 데스크(Codex)가\n"
        "사실 결함을 지적했다. 너의 임무는 *지적된 부분만* 근거에 맞게 고치는 것이다.\n\n"
        "★ 독자 우선 (최우선 원칙):\n"
        "이 보고서는 *구독자가 읽을 정보*다. 너는 무엇이 틀렸는지 기록하는 게 아니라,\n"
        "독자에게 정확하고 유용한 정보를 주도록 고친다. 검수 과정은 독자에게 보이지\n"
        "않아야 한다. 다음을 *절대* 본문에 남기지 마라:\n"
        "  - 정정 흔적·메타 코멘트: '신규 공개가 아니다 / 사실과 다르다 / 정정하면 /\n"
        "    출처에 따르면 ~아니다 / 확인 결과 ~' 같은 자기 지시적·해명조 표현.\n"
        "  - 부정문 박제: 틀린 주장을 '~한 것은 아니다' 로 끝내 독자에게 빈손을 주는 것.\n"
        "잘못된 주장은 ① *정확한 사실로 자연스럽게 다시 쓰거나* ② 그 사실이 보고서 핵심과\n"
        "무관하면 *덜어낸다*. 예: '오늘 GR00T 공개'(틀림) → '엔비디아가 3월 GTC에서 선보인\n"
        "GR00T 휴머노이드 모델을 이번 타이베이에서 다시 부각했다'(정확+자연). 독자는 GR00T가\n"
        "뭐고 왜 중요한지를 알아야지, '신규가 아님' 같은 해명을 읽을 이유가 없다.\n\n"
        "절대 규칙:\n"
        "1) 지적되지 않은 문장·구조·논지·문체는 그대로 둔다. 보고서를 새로 쓰지 마라.\n"
        "2) 출처 없는 특정 수치는 삭제하거나, 근거가 뒷받침하는 표현으로만 바꾼다.\n"
        "3) 과장된 인과·단정은 헤지 표현으로 누그러뜨린다('기여했을 수 있다/와 부합한다/\n"
        "   간접 영향'). 한쪽 주장은 '...측은 주장했다' 로 귀속한다.\n"
        "4) scope(단위/범위)를 근거에 맞게 정정한다. 시점·신규성은 발행일 기준으로 맞추되,\n"
        "   '신규 아님' 식 부정이 아니라 *실제 시점을 정보로* 녹인다('3월 GTC에서 선보인').\n"
        "5) 없는 사실을 새로 지어내지 마라. 근거가 부족하면 단정을 빼고 완화한다.\n"
        "6) 마크다운 강조·em/en dash 금지(평문). 일반 독자가 읽는 평이한 우리말.\n"
        "7) ★ 고치면서 *새로운* 주장·프레이밍·수식어를 근거 없이 끌어들이지 마라. 지적된\n"
        "   것만 빼거나 정확히 바꾼다. '복귀/최초/사상 최대/직격탄/사실상' 같은 함의 큰\n"
        "   표현은 evidence 가 직접 뒷받침할 때만. (한 결함을 고치다 새 결함을 심는 것 방지.)\n\n"
        "출력: 아래 JSON *하나만*. 코드펜스·설명 금지. 차트·이미지·신호는 시스템이 보존하니\n"
        "너는 *텍스트만* 낸다.\n"
        '{"headline":"(정정된 제목)","deck":"(정정된 부제)",'
        '"sections":[{"heading":"(섹션 제목)","prose":"(정정된 본문)"}],'
        '"contradictions_heading":"(쟁점 섹션 제목, 있으면)","closing":"(맺음, 없으면 빈 문자열)"}\n'
        "sections 는 원본과 *같은 개수·같은 순서* 로 낸다. 안 고친 섹션도 원문 그대로 포함.\n"
        "★ 제목 중복 지적이 있으면: 같은 제목을 두 곳(섹션 제목 / 쟁점 섹션 제목 "
        "contradictions_heading / 헤드라인)에 쓰지 말고, 각각 그 부분 내용에 맞는 *서로 "
        "다른* 제목으로 반드시 바꾼다."
    )

    async def revise_for_facts(
        self,
        report: "ComposedReport",
        context: ContextAnalysis,
        *,
        fix_instructions: list[str],
        publication_date: str,
    ) -> "ComposedReport":
        """Codex 지적(fix_instructions)을 받아 *지적된 부분만* Opus 가 재작성.

        본문은 Opus 고정 (AP-V6-1/11). 차트·이미지·신호 등 비텍스트 필드는 코드가
        원본에서 보존(merge)하므로 LLM 은 텍스트만 emit. 파싱·호출 실패 시 원본을
        그대로 반환 (graceful — 보완이 원본보다 나빠지지 않게).
        """
        if not fix_instructions:
            return report
        payload = {
            "publication_date": publication_date or today_kst(),
            "event": {"name": context.event_name, "date": context.date},
            "evidence": {
                "summary": context.summary,
                "background": context.background,
                "timeline": context.timeline,
                "key_figures": context.key_figures,
                "sources": context.sources,
                "time_series": context.time_series,
            },
            "fix_instructions": fix_instructions,
            "report_text": {
                "headline": report.headline,
                "deck": report.deck,
                "sections": [
                    {"heading": s.heading, "prose": s.prose} for s in report.sections
                ],
                "contradictions_heading": report.contradictions_heading,
                "closing": report.closing,
            },
        }
        # V7 Track C — 보완 패스에도 동일 계약 주입 (루프 양 패스의 맹점 공유 해소,
        # REFACTOR_V7_PLAN.md §3.5). flag OFF = payload·프롬프트 byte-equal.
        revise_prompt = self.REVISE_SYSTEM_PROMPT
        if getattr(self.config, "enable_ref_frame", False):
            from src.factcheck.reference_frame import build_reference_frame
            frame = build_reference_frame(context)
            if frame.get("instruments"):
                payload["reference_frame"] = frame
            revise_prompt += (
                "\n\n=== 기준시점 정정 (V7) ===\n"
                "시점 지적(wrong_timeframe/stale_anchor)은 evidence.time_series 의 *최신* "
                "일자(reference_frame.last_available_date) 값으로 교체하고 날짜를 명기한다. "
                "해당 일자 데이터가 없으면 그 수치 문장을 완화하거나 덜어낸다 — 옛 날짜 "
                "수치를 무표기로 남기지 마라."
            )
        user_message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(
                    user_message, timeout_s=300.0,
                    system_prompt=revise_prompt,
                )
            else:
                raw = await self._call_api(
                    user_message, mode="standard",
                    system_prompt=revise_prompt,
                )
        except Exception as exc:  # noqa: BLE001 — 보완 실패 → 원본 유지
            logger.warning("[revise_for_facts] LLM call failed: %s", exc)
            return report

        obj = self._loads_first_json_object(raw)
        if obj is None:
            repaired = self._repair_truncated_json(raw)
            obj = self._loads_first_json_object(repaired) if repaired else None
        if not isinstance(obj, dict):
            logger.warning("[revise_for_facts] revision parse failed; keeping original")
            return report
        return self._merge_text_revision(report, obj)

    @staticmethod
    def _merge_text_revision(original: "ComposedReport", revised: dict) -> "ComposedReport":
        """LLM 이 낸 텍스트 필드만 원본 deep-copy 에 병합 (차트/이미지/신호 보존).

        sections 는 *인덱스 매칭* — LLM 이 같은 개수·순서로 내도록 지시받았다. 개수가
        달라도 겹치는 인덱스만 갱신해 본문 손실을 막는다.
        """
        new = original.model_copy(deep=True)
        if isinstance(revised.get("headline"), str) and revised["headline"].strip():
            new.headline = revised["headline"]
        if isinstance(revised.get("deck"), str):
            new.deck = revised["deck"]
        if isinstance(revised.get("closing"), str):
            new.closing = revised["closing"]
        if isinstance(revised.get("contradictions_heading"), str) and revised["contradictions_heading"].strip():
            new.contradictions_heading = revised["contradictions_heading"]
        rsecs = revised.get("sections")
        if isinstance(rsecs, list):
            for i, rs in enumerate(rsecs):
                if i >= len(new.sections) or not isinstance(rs, dict):
                    continue
                if isinstance(rs.get("heading"), str) and rs["heading"].strip():
                    new.sections[i].heading = rs["heading"]
                if isinstance(rs.get("prose"), str) and rs["prose"].strip():
                    new.sections[i].prose = rs["prose"]
        return new

    async def compose(
        self,
        result: FullAnalysisResult,
        chart_catalog: list[dict],
    ) -> ComposedReport | None:
        """[Legacy v3.3.0~v3.5.0] 7개 분석가 결과를 받아 편집만 하는 경로.

        v4.0.0 Tier 4 부터는 ``compose_unified()`` 가 기본 경로. 본 메서드는
        하위 호환을 위해 보존하지만 orchestrator 는 호출하지 않음. 향후 정리 시 제거.
        """
        user_payload = self._build_user_payload(result, chart_catalog)
        # JSON 직렬화 — compact (한국어 nested JSON 토큰 절약, base.py 와 동일).
        user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(user_message)
            else:
                raw = await self._call_api(user_message)
        except Exception as e:
            logger.warning("[narrative_composer] LLM call failed: %s", e)
            return None

        composed = self._parse_response(raw)
        if composed is None:
            return None
        # 출력의 chart_id / block_type 을 catalog 와 대조하여 invalid 항목 제거.
        composed = self._validate_references(composed, chart_catalog)
        logger.info(
            "[narrative_composer] Composed report: %d sections, headline=%r",
            len(composed.sections), composed.headline[:40],
        )
        return composed

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_payload(
        result: FullAnalysisResult, chart_catalog: list[dict]
    ) -> dict:
        """Composer 에 전달할 입력 dict.

        토큰 절약 목적: 빈 필드 생략, glossary 같은 비핵심 필드 제외.
        """
        payload: dict = {}

        if result.context:
            ctx = result.context
            payload["event"] = {
                "name": ctx.event_name,
                "category": ctx.category,
                "date": ctx.date,
                "summary": ctx.summary,
                "background": ctx.background,
                "key_figures": ctx.key_figures,
                "timeline": ctx.timeline,
                "sources": ctx.sources,
            }

        if result.players and result.players.players:
            payload["players"] = {
                "list": result.players.players,
                "alliances": result.players.alliances,
                "power_dynamics": result.players.power_dynamics,
            }

        if result.dynamics:
            d = result.dynamics
            payload["dynamics"] = {
                "framework": d.framework,
                "core_tension": d.core_tension,
                "asymmetries": d.asymmetries,
                "feedback_loops": d.feedback_loops,
                "tipping_points": d.tipping_points,
                "key_insight": d.key_insight,
                "counter_view": d.counter_view,
            }

        if result.chain_reaction and result.chain_reaction.chain:
            cr = result.chain_reaction
            payload["chain_reaction"] = {
                "chain": cr.chain,
                "feedback_loops": cr.feedback_loops,
                "wildcards": cr.wildcards,
                "worst_case": cr.worst_case,
            }

        if result.scenarios:
            sc = result.scenarios
            payload["scenarios"] = {
                "list": sc.scenarios,
                "watch_signals": sc.watch_signals,
                "invalidation_conditions": sc.invalidation_conditions,
                "base_case_summary": sc.base_case_summary,
            }

        # Findings / Claims catalog — composer 가 cite 할 수 있도록 ID + 본문만 노출.
        if result.findings:
            claims_catalog = []
            for f in result.findings:
                claims_catalog.append({
                    "claim_id": f.main_claim.claim_id,
                    "lens": f.lens_id,
                    "type": f.main_claim.claim_type,
                    "statement": f.main_claim.statement,
                    "answers": f.answers_question,
                    "counter_hypothesis": f.counter_hypothesis,
                })
            payload["claims"] = claims_catalog

        if result.judgment:
            j = result.judgment
            payload["judgment"] = {
                "main": j.main_judgment,
                "base_scenario": j.base_scenario,
                "biggest_uncertainty": j.biggest_uncertainty,
                "contradictions": j.contradictions,
                "counter_hypothesis": j.counter_hypothesis,
            }

        # Strategy intent — composer 가 무엇에 답해야 하는지.
        if result.strategy:
            payload["intent"] = {
                "user_intent": result.strategy.user_intent,
                "core_questions": result.strategy.core_questions,
                "event_type": result.strategy.event_type,
            }

        # 차트 catalog — composer 가 referencing 할 수 있는 차트 목록.
        if chart_catalog:
            payload["available_charts"] = chart_catalog

        # v5.2.0 — 시계열 데이터 (orchestrator 가 market_fetcher 로 채움).
        # 각 series 가 chart_type ('line' / 'candle' / 'area') 을 추천 — composer 가
        # 그대로 사용. data 비어있으면 (fetch 실패 / key 없음) 해당 instrument 차트 X.
        ts = getattr(result.context, "time_series", None) or []
        ts_with_data = [s for s in ts if (s.get("data") if isinstance(s, dict) else getattr(s, "data", None))]
        if ts_with_data:
            payload["available_time_series"] = ts_with_data

        return payload

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_cli(
        self, user_message: str, timeout_s: float = 480.0,
        system_prompt: str | None = None,
    ) -> str:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        # system_prompt 미지정 시 compose 용 SYSTEM_PROMPT (기본 경로 byte-equal).
        full_prompt = f"{system_prompt or SYSTEM_PROMPT}\n\n---\n\n{user_message}"
        cmd = [
            claude_bin,
            "-p", full_prompt,
            "--output-format", "text",
            "--model", self.COMPOSER_MODEL,
            "--dangerously-skip-permissions",
        ]
        logger.info(
            "[narrative_composer] Starting CLI call (%s, prompt=%d chars, timeout=%.0fs)",
            self.COMPOSER_MODEL, len(full_prompt), timeout_s,
        )
        start = time.time()
        # v5.6.6 — stdout 을 임시 파일로 받는다. timeout 으로 proc 를 kill 해도 그때까지
        # 스트리밍된 부분 출력이 디스크에 남아 살릴 수 있다. PIPE+communicate() 는 timeout
        # 시 부분 출력을 통째로 버려 0% fallback 회귀의 직접 원인이었다.
        fd, tmp_path = tempfile.mkstemp(prefix="composer_", suffix=".txt")
        try:
            with os.fdopen(fd, "wb") as out_f:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=out_f,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout_s,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    with contextlib.suppress(Exception):
                        await proc.wait()
                    partial = self._read_text(tmp_path)
                    logger.warning(
                        "[narrative_composer] CLI timeout after %.0fs; "
                        "salvaged %d chars partial output",
                        timeout_s, len(partial),
                    )
                    raise _ComposerTimeout(timeout_s, partial)
            elapsed_ms = int((time.time() - start) * 1000)
            if proc.returncode != 0:
                err = stderr.decode().strip() if stderr else "unknown"
                raise RuntimeError(
                    f"narrative_composer CLI exit={proc.returncode}: {err}"
                )
            raw = self._read_text(tmp_path)
            if self.telemetry is not None:
                self.telemetry.record_llm_call(
                    agent_name="narrative_composer",
                    input_chars=len(full_prompt),
                    output_chars=len(raw),
                    elapsed_ms=elapsed_ms,
                )
            logger.info(
                "[narrative_composer] CLI response (%d chars, %dms)",
                len(raw), elapsed_ms,
            )
            return raw
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    @staticmethod
    def _read_text(path: str) -> str:
        """파일을 utf-8 로 읽어 strip. 실패/부재 시 빈 문자열 (부분 출력 살리기용)."""
        try:
            with open(path, "rb") as f:
                return f.read().decode("utf-8", "replace").strip()
        except OSError:
            return ""

    async def _call_api(
        self, user_message: str, mode: str = "standard",
        system_prompt: str | None = None,
    ) -> str:
        assert self._api_client is not None, "API client not initialised"
        start = time.time()
        sys_p = system_prompt or SYSTEM_PROMPT
        max_tokens = self.MAX_TOKENS_BY_MODE.get(mode, self.MAX_TOKENS)
        response = await self._api_client.messages.create(  # type: ignore[union-attr]
            model=self.COMPOSER_MODEL,
            max_tokens=max_tokens,
            system=sys_p,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text  # type: ignore[index]
        elapsed_ms = int((time.time() - start) * 1000)
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name="narrative_composer",
                input_chars=len(sys_p) + len(user_message),
                output_chars=len(raw),
                elapsed_ms=elapsed_ms,
            )
        return raw

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _loads_first_json_object(s: str) -> dict | None:
        """문자열에서 첫 완결 JSON 객체를 추출. 앞 prose / 뒤 extra data 허용.

        v5.5.10 — `json.loads` 는 "Extra data" (객체 뒤 텍스트) 에 죽지만
        `raw_decode` 는 첫 완결 값만 파싱하고 나머지를 무시한다. degraded 응답
        (JSON + 꼬리 텍스트, 또는 prose + JSON) 회귀 대응.
        """
        s = (s or "").strip()
        if not s:
            return None
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
        start = s.find("{")
        if start == -1:
            return None
        try:
            obj, _end = json.JSONDecoder().raw_decode(s, start)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_response(raw: str) -> ComposedReport | None:
        """raw 텍스트에서 ComposedReport JSON 추출 + 검증.

        v5.5.10 — fence split / greedy regex 가 깨진 응답("Extra data" 등) 에
        취약했음. 여러 후보(```json 펜스 / raw 전체 / 일반 펜스)를 raw_decode 로
        시도해 첫 검증 통과 객체를 채택. trailing extra / 앞 prose / 잘못된
        스트레이 펜스에 견고.
        """
        candidates: list[str] = []
        if "```json" in raw:
            candidates.append(raw.split("```json", 1)[1].split("```", 1)[0])
        candidates.append(raw)  # 펜스 없는 본문 / 펜스 추출 실패 / trailing extra 대비
        if "```" in raw:
            candidates.append(raw.split("```", 1)[1].split("```", 1)[0])
        for cand in candidates:
            obj = NarrativeComposer._loads_first_json_object(cand)
            if obj is None:
                continue
            try:
                return ComposedReport.model_validate(obj)
            except Exception:  # noqa: BLE001 — 다음 후보 시도
                continue
        # v5.6.6 — 정상 파싱이 모두 실패하면 *잘린 JSON 복구* 시도. 타임아웃/한도로
        # 중간에 끊긴 응답에서 완성된 섹션까지만 살린다 (0% fallback 회피).
        for cand in candidates:
            repaired = NarrativeComposer._repair_truncated_json(cand)
            if repaired is None:
                continue
            try:
                obj = json.loads(repaired)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            for candidate_obj in (obj, NarrativeComposer._drop_invalid_sections(obj)):
                try:
                    composed = ComposedReport.model_validate(candidate_obj)
                    logger.warning(
                        "[narrative_composer] recovered truncated JSON "
                        "(%d sections)", len(composed.sections),
                    )
                    return composed
                except Exception:  # noqa: BLE001 — 섹션 떨군 뒤 재시도
                    continue
        # v5.6.8 — head-loss 복구. LLM 이 SYSTEM_PROMPT 의 JSON 예시 들여쓰기를
        # 따라가다 응답의 *시작 부분* (``{``, headline, deck, sections 배열 시작) 을
        # 통째로 빠뜨리고 ``      "prose": "..."`` 같은 sections 객체의 *중간 줄* 부터
        # 시작하는 회귀(2026-05-30 발견). 그 경우 부분 객체라도 살려 1-섹션 보고서로.
        recovered = NarrativeComposer._recover_head_loss(raw)
        if recovered is not None:
            logger.warning(
                "[narrative_composer] head-loss 복구: 1-섹션 (prose=%d chars)",
                len(recovered.sections[0].prose) if recovered.sections else 0,
            )
            return recovered
        logger.warning(
            "[narrative_composer] No parseable ComposedReport "
            "(raw=%d chars, head=%r)", len(raw), raw[:200],
        )
        return None

    @staticmethod
    def _recover_head_loss(raw: str) -> ComposedReport | None:
        """LLM 이 응답 시작을 빠뜨려 sections 객체 *중간 줄* 부터 시작했을 때,
        부분 객체에서 prose / heading 등을 추출해 1-섹션 ComposedReport 로 재조립.

        패턴: 코드펜스 또는 응답 시작이 ``{`` 가 아니라 들여쓰기된 ``"key":`` 인 케이스.
        그 부분을 ``{...}`` 로 wrap 해서 한 객체로 만든 뒤, ``heading``/``prose`` 가
        있으면 ComposedSection 으로 변환. headline 은 빈 문자열(orchestrator 가 hook
        으로 context.event_name 으로 덮어쓸 수 있음).
        """
        if not raw:
            return None
        # 코드펜스 안 또는 raw 직접에서 후보 추출
        body = raw
        if "```json" in raw:
            body = raw.split("```json", 1)[1]
            if "```" in body:
                body = body.split("```", 1)[0]
        body = body.strip()
        if not body or body.startswith("{"):
            return None  # 정상 시작이면 본 복구 대상 아님
        # 들여쓰기 키 패턴이 있어야 head-loss 후보
        import re as _re
        if not _re.search(r'^\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:', body):
            return None
        # ``{`` 로 wrap → 파싱 시도 + 잘렸으면 복구
        for wrapped in ("{" + body, "{" + body + "}"):
            obj = NarrativeComposer._loads_first_json_object(wrapped)
            if obj is None:
                repaired = NarrativeComposer._repair_truncated_json(wrapped)
                if repaired is None:
                    continue
                try:
                    obj = json.loads(repaired)
                except json.JSONDecodeError:
                    continue
            if not isinstance(obj, dict):
                continue
            prose = obj.get("prose")
            if not isinstance(prose, str) or not prose.strip():
                continue  # prose 없으면 살릴 가치 없음
            heading = obj.get("heading") if isinstance(obj.get("heading"), str) else "분석"
            section_data = {"heading": heading, "prose": prose}
            for opt in ("kicker", "lede", "pull_quote"):
                v = obj.get(opt)
                if isinstance(v, str) and v.strip():
                    section_data[opt] = v
            try:
                return ComposedReport(
                    headline="",
                    sections=[ComposedSection(**section_data)],
                    confidence_score=0.3,
                    confidence_summary=(
                        "응답 시작 부분이 누락돼 본문 일부만 복구함 (head-loss recovery)."
                    ),
                )
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    def _repair_truncated_json(s: str) -> str | None:
        """절단된 JSON 을 마지막 *완결 경계* 까지 자르고 열린 괄호를 닫는다.

        쉼표 직전(완결 값 뒤)·``}``/``]`` 직후만 안전 경계로 인정해 미완 스칼라/키를
        남기지 않는다. 문자열 내부의 괄호·쉼표는 무시(in_str 추적). 첫 ``{`` 부터 시작.
        """
        if not s:
            return None
        start = s.find("{")
        if start < 0:
            return None
        s = s[start:].rstrip()
        # 앞 펜스 잔재가 있으면 위 find 로 제거됨. 이제 안전 경계 탐색.
        in_str = False
        esc = False
        last_safe: int | None = None
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "}]":
                last_safe = i + 1
            elif ch == ",":
                last_safe = i
        if last_safe is None:
            return None
        head = s[:last_safe]
        # 열린 괄호 추적해 닫기.
        stack: list[str] = []
        in_str = False
        esc = False
        for ch in head:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack:
                    stack.pop()
        head = head.rstrip().rstrip(",").rstrip()
        return head + "".join(reversed(stack))

    @staticmethod
    def _drop_invalid_sections(data: dict) -> dict:
        """sections 배열에서 heading/prose 가 빠진(절단된) 항목 제거한 사본 반환."""
        secs = data.get("sections")
        if not isinstance(secs, list):
            return data
        good = [
            s for s in secs
            if isinstance(s, dict) and s.get("heading") and s.get("prose")
        ]
        if len(good) == len(secs):
            return data
        nd = dict(data)
        nd["sections"] = good
        return nd

    # ------------------------------------------------------------------
    # 기호 정화 (v5.6.7) — AI 가 인지되는 기호 결정적 제거 (사용자 최우선 규칙)
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(s: str) -> str:
        """한 텍스트에서 마크다운 강조 + em/en dash 를 자연스럽게 제거/치환.

        - 마크다운 강조 (``**`` / ``*`` / ``` `` ``` / ``_``) → 제거 (강조 내용은 보존).
        - em dash ``—`` / en dash ``–`` / 수평선 ``―`` → 맥락별 자연 치환:
          · 공백으로 둘러싸인 ` — ` (삽입구/부연) → ', ' (쉼표) — 한국어에서 가장 자연.
          · 숫자 사이 ``3—5`` (범위) → '~'.
          · 그 외 (단어 직접 인접) → 공백 한 칸.
        치환 후 이중 공백/공백+문장부호는 정리.
        """
        if not s:
            return s
        import re as _re
        out = s
        # 1) 마크다운 강조 제거 (내용 보존). ** 먼저, 그 다음 단독 * / ` / _.
        out = out.replace("**", "")
        out = out.replace("*", "")
        out = out.replace("`", "")
        # 밑줄 강조: 단어 경계의 _..._ 만 (스네이크케이스 식별자 훼손 방지 위해 공백 인접만).
        out = _re.sub(r"(?<=\s)_+|_+(?=\s)", "", out)
        out = _re.sub(r"^_+|_+$", "", out)
        # 2) dash 치환. 범위(숫자—숫자) → ~
        out = _re.sub(r"(?<=\d)\s*[—–―]\s*(?=\d)", "~", out)
        # 공백으로 둘러싸인 dash → 쉼표 (삽입구/부연 자르기)
        out = _re.sub(r"\s+[—–―]\s+", ", ", out)
        # 남은 dash (단어 직접 인접) → 공백
        out = _re.sub(r"[—–―]", " ", out)
        # 3) 정리: 쉼표 앞 공백 제거, 이중 쉼표/공백 압축
        out = _re.sub(r"\s+,", ",", out)
        out = _re.sub(r",\s*,", ",", out)
        out = _re.sub(r"[ \t]{2,}", " ", out)
        # 문장부호 앞 잉여 쉼표 ( ", ." → "." )
        out = _re.sub(r",\s*([.!?])", r"\1", out)
        return out.strip()

    @classmethod
    def _clean_value(cls, v):
        """str / list / dict 를 재귀적으로 정화. 그 외 타입은 그대로."""
        if isinstance(v, str):
            return cls._clean_text(v)
        if isinstance(v, list):
            return [cls._clean_value(x) for x in v]
        if isinstance(v, dict):
            return {k: cls._clean_value(x) for k, x in v.items()}
        return v

    @classmethod
    def _sanitize_symbols(cls, composed: "ComposedReport") -> None:
        """ComposedReport 의 *모든 사용자 노출 텍스트* 에서 금지 기호 제거 (in-place).

        사용자 최우선 규칙 (v5.6.7): 보고서·SNS 문구에 ``**`` / ``*`` / em dash 등
        AI 가 인지되는 기호를 절대 쓰지 않는다. 프롬프트 지시 + 본 결정적 후처리
        2중 방어. URL(source_url/image_url) 은 정화 대상에서 제외 (링크 훼손 방지).
        """
        # 보고서 레벨 단문 필드
        for attr in (
            "headline", "deck", "closing", "contradictions_heading",
            "confidence_summary", "broadcast_summary",
        ):
            val = getattr(composed, attr, "")
            if isinstance(val, str) and val:
                setattr(composed, attr, cls._clean_text(val))

        # 리스트[dict] 필드 (watch_signals / contradictions) — 값 전체 재귀 정화
        composed.watch_signals = cls._clean_value(composed.watch_signals)
        composed.contradictions = cls._clean_value(composed.contradictions)
        if composed.timeline_flow:
            composed.timeline_flow = cls._clean_value(composed.timeline_flow)

        # hero_image / embedded_map: URL 제외하고 텍스트 필드만
        cls._clean_media(getattr(composed, "hero_image", None))
        if composed.embedded_map:
            composed.embedded_map = cls._clean_map(composed.embedded_map)

        # 섹션
        for sec in composed.sections:
            for attr in ("heading", "kicker", "prose", "pull_quote", "lede"):
                val = getattr(sec, attr, "")
                if isinstance(val, str) and val:
                    setattr(sec, attr, cls._clean_text(val))
            if sec.analogy:
                sec.analogy = cls._clean_value(sec.analogy)
            sec.fact_grid = cls._clean_value(sec.fact_grid)
            # charts: title/note/data 내 라벨 텍스트 정화 (URL 없음)
            sec.charts = cls._clean_value(sec.charts)
            # images: caption/credit/alt 만 — URL 키는 보존
            for img in (sec.images or []):
                cls._clean_media(img)

    @classmethod
    def _clean_media(cls, media) -> None:
        """이미지 dict 의 텍스트 필드만 정화 (URL 키 보존). in-place. None 안전."""
        if not isinstance(media, dict):
            return
        for k in ("caption", "credit", "alt", "title"):
            if isinstance(media.get(k), str) and media[k]:
                media[k] = cls._clean_text(media[k])

    @classmethod
    def _clean_map(cls, m: dict) -> dict:
        """embedded_map 의 label 텍스트만 정화. 좌표/id/bool 보존."""
        if not isinstance(m, dict):
            return m
        nm = dict(m)
        for coll_key in ("markers", "arcs", "legend"):
            coll = nm.get(coll_key)
            if isinstance(coll, list):
                new_coll = []
                for item in coll:
                    if isinstance(item, dict):
                        it = dict(item)
                        for tk in ("name", "label"):
                            if isinstance(it.get(tk), str) and it[tk]:
                                it[tk] = cls._clean_text(it[tk])
                        new_coll.append(it)
                    else:
                        new_coll.append(item)
                nm[coll_key] = new_coll
        return nm

    @staticmethod
    def _validate_references(
        composed: ComposedReport, chart_catalog: list[dict]
    ) -> ComposedReport:
        """Composer 가 적은 chart_id 와 block_type 중 invalid 한 것을 제거.

        - chart_id 는 catalog 의 id 와 매칭되어야 함.
        - block_type 은 화이트리스트 (BlockType Literal) 내여야 함.
        """
        valid_chart_ids = {c["id"] for c in chart_catalog}
        valid_block_types = {
            "actor_cards", "scenario_table", "timeline", "flow_chain",
            "watchlist", "data_series", "risk_matrix", "decomposition",
            "counter_hypothesis", "callout", "narrative", "matrix",
            "argument_pair", "claim_card", "evidence_table", "qna",
            "decision_matrix",
        }
        for sec in composed.sections:
            sec.embedded_charts = [
                cid for cid in sec.embedded_charts if cid in valid_chart_ids
            ]
            sec.embedded_blocks = [
                bt for bt in sec.embedded_blocks if bt in valid_block_types
            ]
        return composed
