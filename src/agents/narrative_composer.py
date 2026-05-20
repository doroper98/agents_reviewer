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
import json
import logging
import re
import shutil
import time
from typing import Optional

from src.config import Config
from src.models import (
    ComposedReport,
    ComposedSection,
    ContextAnalysis,
    FullAnalysisResult,
    ParentContext,
)
from src.telemetry import RunTelemetry

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "당신은 사건 분석가이자 편집장. 1차 사실 자료(웹 검색으로 수집된 사실/타임라인/"
    "핵심 수치/출처 URL)를 받아 *단독으로* 분석하고 보고서를 작성한다.\n\n"
    "v4.0.0 Tier 4: 별도의 행위자/구조/시나리오/판단 분석가가 없음. 본 호출 한 번에\n"
    "다음을 모두 수행: ① 핵심 행위자 식별 ② 구조적 동인 분석 ③ 인과 사슬 추적 ④\n"
    "시나리오 설계 ⑤ 모순/반대 가설 표면화 ⑥ 보고서 본문 작성 ⑦ 감시 신호 추출.\n\n"
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
    "- **진부 연결어 금지**: 다양한 측면에서 / 결론적으로 / 주목할 만한 점은 / 다시\n"
    "  말해 / 더 깊은 분석이 필요하다 / 심도 있게 살펴보면. 허용: 사실은 / 단 /\n"
    "  즉 / 그러나 / 반면 (WRITE-AP-4).\n"
    "- **'N번' vs 서수**: 서수는 '첫 / 처음으로 / 첫 번째 / 가운데 첫'. 'N번' 은 식별\n"
    "  번호 뉘앙스 (WRITE-AP-7).\n"
    "- **짧은 문단**: 한 문단 3~5 문장. 단락 사이 ``\\n\\n``.\n"
    "- **모순 봉합 금지**: 관점 충돌은 ``contradictions`` 에 명시 (Anti-pattern #5).\n\n"
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

    "[차트 type 결정 트리 — v5.2.14 신설]\n"
    "캔들/donut/bar 만 반복 emit 회귀 (~70%) 방지의 SSOT. 데이터 형태부터 시작:\n"
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
    "    slope, 분해형이면 waterfall 가 더 적절한 경우가 많음.\n\n"

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
    "- 어느 쪽 손을 들어줬는지, 패배한 입장은 어떤 조건에서 살아나는지 명시.\n\n"
    "=== 감시 신호 (Watchlist 통합) ===\n"
    "- watch_signals 배열 — Watchlist 시스템이 SQLite 에 INSERT.\n"
    "- 형식: [{signal, description, indicates, deadline?, icon?}]\n"
    "  · signal: 짧은 식별자 (예: 'Fed 6월 FOMC 점도표')\n"
    "  · description: 신호 설명 한 문장\n"
    "  · indicates: 이 신호가 어느 시나리오 분기를 가리키는지\n"
    "  · deadline: 'YYYY-MM-DD' 또는 '6월 중' 등 (생략 가능)\n"
    "  · icon: 이모지 1~2자 (생략 가능)\n\n"
    "=== JSON 응답 형식 (반드시 준수) ===\n"
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
    '  "contradictions": [\n'
    "    {\n"
    '      \"side_a\": \"관점 A 한 줄\",\n'
    '      \"side_b\": \"반대 관점 B 한 줄\",\n'
    '      \"evidence\": \"양 관점이 충돌하는 데이터/논거 (생략 가능)\",\n'
    '      \"resolution\": \"현 시점 어느 손 들었는지 + 패배 입장 살아나는 조건\"\n'
    "    }\n"
    "  ],\n"
    '  "confidence_summary": "출처 다양성/신선도/확신도 한 줄 자유 평가",\n'
    '  "confidence_score": 0.0~1.0\n'
    "}\n"
    "```\n"
    "JSON 만 출력. 추가 설명 텍스트 금지.\n"
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
    MAX_TOKENS_BY_MODE: dict[str, int] = {
        "fast": 12000,
        "standard": 20000,
        "deep": 32000,
    }
    MAX_TOKENS: int = 32000  # 기본값 (mode 정보 없을 때)

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
        user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        try:
            if self.config.use_cli_mode:
                raw = await self._call_cli(user_message)
            else:
                raw = await self._call_api(user_message, mode=mode)
        except Exception as e:
            logger.warning("[unified_composer] LLM call failed: %s", e)
            return None

        composed = self._parse_response(raw)
        if composed is None:
            return None
        # v4.0.0: chart_catalog 가 비었으니 embedded_charts 도 빈 list 로 강제 (검증 layer).
        composed = self._validate_references(composed, chart_catalog=[])
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
        payload: dict = {
            "mode": mode,
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

    async def _call_cli(self, user_message: str) -> str:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{user_message}"
        cmd = [
            claude_bin,
            "-p", full_prompt,
            "--output-format", "text",
            "--model", self.COMPOSER_MODEL,
            "--dangerously-skip-permissions",
        ]
        logger.info(
            "[narrative_composer] Starting CLI call (%s, prompt=%d chars)",
            self.COMPOSER_MODEL, len(full_prompt),
        )
        start = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed_ms = int((time.time() - start) * 1000)
        if proc.returncode != 0:
            err = stderr.decode().strip() if stderr else "unknown"
            raise RuntimeError(f"narrative_composer CLI exit={proc.returncode}: {err}")
        raw = stdout.decode().strip()
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name="narrative_composer",
                input_chars=len(full_prompt),
                output_chars=len(raw),
                elapsed_ms=elapsed_ms,
            )
        logger.info(
            "[narrative_composer] CLI response (%d chars, %dms)", len(raw), elapsed_ms,
        )
        return raw

    async def _call_api(self, user_message: str, mode: str = "standard") -> str:
        assert self._api_client is not None, "API client not initialised"
        start = time.time()
        max_tokens = self.MAX_TOKENS_BY_MODE.get(mode, self.MAX_TOKENS)
        response = await self._api_client.messages.create(  # type: ignore[union-attr]
            model=self.COMPOSER_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text  # type: ignore[index]
        elapsed_ms = int((time.time() - start) * 1000)
        if self.telemetry is not None:
            self.telemetry.record_llm_call(
                agent_name="narrative_composer",
                input_chars=len(SYSTEM_PROMPT) + len(user_message),
                output_chars=len(raw),
                elapsed_ms=elapsed_ms,
            )
        return raw

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> ComposedReport | None:
        """Extract JSON from raw text and validate as ComposedReport."""
        if "```json" in raw:
            json_str = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            json_str = raw.split("```", 1)[1].split("```", 1)[0].strip()
        else:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[narrative_composer] No JSON object in response")
                return None
            json_str = match.group()
        try:
            data = json.loads(json_str)
            return ComposedReport.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[narrative_composer] Parse/validation failed: %s", e)
            return None

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
