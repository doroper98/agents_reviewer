"""Context Analyst Agent -- situation and fact analysis."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import Config
from src.models import AnalysisRequest, ContextAnalysis
from src.timeutil import today_kst

SYSTEM_PROMPT = (
    "당신은 상황 분석관. 사건의 팩트, 타임라인, 핵심 수치를 정리함.\n\n"
    "중요: 오늘 날짜는 {current_date}.\n"
    "반드시 최신 정보를 기반으로 분석할 것.\n"
    "웹 검색을 통해 최신 뉴스, 데이터, 현황을 확인한 후 분석.\n"
    "학습 데이터에만 의존하지 말 것.\n"
    "과거 정보를 현재로 혼동하지 말 것 (예: 이전 정부를 현 정부로 착각 금지).\n\n"
    "=== 출력의 위치 (v5.2.9 명시) ===\n"
    "당신의 출력 (summary / background / key_figures.context / timeline 등) 은\n"
    "*내부 분석 메모* 다. 그 자체가 보고서 본문이 되지 않는다. 후속의 NarrativeComposer\n"
    "가 본 출력을 입력으로 받아 *평어체 한국어 본문* 으로 재작성한다. 따라서:\n"
    "- 본 출력은 음슴체 (~함 / ~임) 사용 OK — 압축된 분석 메모 톤.\n"
    "- 미사여구·극적 형용사·수사적 질문 금지. 사실과 수치 위주.\n"
    "- 보고서 본문의 평어체·친절한 어조는 composer 가 책임진다.\n\n"
    "=== 규칙 ===\n"
    "- 용어 난이도: 대학교 학부생 수준. 신문 사회면을 읽는 일반인도 이해 가능해야 함\n"
    "- 한자어/외래어 남용 금지 (예: '회임 / 제고 / 함의 / 귀결 / 부합 / 결부 / 소지'\n"
    "  → '맡김 / 높임 / 뜻하는 바 / 결과 / 맞음 / 엮임 / 가능성'). 자세한 어휘 표는\n"
    "  docs/REPORT_STYLE_GUIDE.md §2.1 참조 — SSOT 단일 출처.\n"
    "- 영어 약어/전문용어는 첫 등장 시 괄호로 풀어쓸 것 (예: GDP (국내총생산))\n"
    "- 검증된 팩트만. 추측 시 명시 (~로 보임 / ~할 가능성)\n"
    "- 타임라인은 날짜+사건 형태\n"
    "- 핵심 수치는 구체적 숫자로 + 비교 기준 함께 (예: '전년 대비', '평균 대비')\n"
    "- 다양한 분석 시각 활용: 사건의 직접 원인뿐 아니라 구조적 배경, 비교 사례,\n"
    "  역사적 평행 사례, 통계적 추세, 관련 법/제도까지 폭넓게 검토\n"
    "- 출처 필수\n\n"
    "JSON 응답 형식:\n"
    "```json\n"
    "{\n"
    '  "event_name": "사건명",\n'
    '  "event_name_en": "English name for report title",\n'
    '  "date": "YYYY-MM-DD",\n'
    '  "category": "분류",\n'
    '  "summary": "3줄 이내 핵심 요약",\n'
    '  "timeline": [{"date": "날짜", "event": "사건", "impact": "영향"}],\n'
    '  "key_figures": [{"label": "지표명", "value": "수치", "context": "맥락"}],\n'
    '  "background": "배경 설명 (5줄 이내)",\n'
    '  "sources": ["출처1", "출처2"],\n'
    '  "glossary": [{"term": "용어", "definition": "정의"}],\n'
    '  "confidence_score": 0.0,\n'
    '  "instruments_mentioned": ["코스피", "삼성전자", "WTI"]\n'
    "}\n"
    "```\n\n"
    "=== instruments_mentioned (v5.2.0 신설) ===\n"
    "사건이 *금융 시장* 과 직간접 관계가 있을 때, 본문에서 참조될 가능성이 높은\n"
    "instrument 의 한글 명을 list 로 emit. orchestrator 가 이 list 를 받아 실데이터\n"
    "(KRX / FRED / ECOS) 를 fetch 해서 composer 가 *진짜 차트* 를 그릴 수 있게 함.\n\n"
    "지원 instrument (한글로 적을 것):\n"
    "  - 한국 지수:   '코스피', '코스닥'\n"
    "  - 미국 지수:   'S&P 500', '나스닥', '필라델피아 반도체'\n"
    "  - 한국 개별주: '삼성전자', 'SK하이닉스'\n"
    "  - 미국 개별주: '엔비디아', '테슬라', '애플', '마이크로소프트', '알파벳'(구글),\n"
    "                 '아마존', '메타'(페이스북), 'AMD', 'TSMC', '브로드컴'\n"
    "  - 미국 매크로: '달러인덱스', '미국채 1Y', '미국채 10Y', 'WTI', '금'\n"
    "  - 한국 매크로: '국고채 10Y', '원/달러 환율'\n\n"
    "규칙:\n"
    "  - 본문이 *실제로 다루는* instrument 만 추가. '주변 언급' 까지 포함 X.\n"
    "  - **★ 주제(사건)의 주인공 종목을 *반드시 첫 번째* 로 둔다.** 예: 엔비디아 실적\n"
    "    발표 사건이면 ['엔비디아', ...]. 테슬라 리콜 사건이면 ['테슬라', ...]. 주제\n"
    "    종목을 빠뜨리고 지수/매크로만 넣지 말 것 — 보고서 주인공의 차트가 떠야 한다.\n"
    "  - 코스피 8000 돌파 같은 사건이면 ['코스피', '삼성전자'] 정도. 무리해서 6개 채우지 말 것.\n"
    "  - 사건이 금융과 무관하면 (예: 자연재해 / 외교 회담) 빈 list [].\n"
    "  - 미등록 종목은 무시됨 (warning log). 추가 종목 필요하면 src/tools/market_fetcher.py 의\n"
    "    INSTRUMENT_REGISTRY 확장 후 사용."
)


class ContextAnalyst(BaseAgent):
    """Establishes facts, timeline, and key data points."""

    def __init__(self, config: Config) -> None:
        super().__init__(
            name="context_analyst",
            role="Context Analyst (상황 분석관)",
            system_prompt=SYSTEM_PROMPT,
            config=config,
            use_light_model=False,
        )
        # v4.1.0 — Tier 4 의 2-call 파이프라인에서는 context 가 편집장(Opus 4.7)이
        # 보는 *유일한* 사실 입력. 사실/숫자/타임라인 추출 품질이 보고서 전체 품질의
        # 상한선이 되므로 Opus 4.7 일관 적용 (composer 와 같은 모델).
        # config.model_name (Opus 4.6) 보다 한 세대 위 모델을 쓰기 위해 직접 지정.
        self.model_name = "claude-opus-4-7"

    async def analyze(self, request: AnalysisRequest) -> ContextAnalysis:
        """Analyze event and return context / situation board."""
        # v4.5.7 — mode 별 max_tokens 분기. deep 사건은 사실/타임라인/출처가 많아
        # 4K 부족 가능. fast/standard 는 4K 충분.
        MAX_TOKENS_BY_MODE = {"fast": 4096, "standard": 4096, "deep": 10000}
        self._max_tokens_override = MAX_TOKENS_BY_MODE.get(request.mode, 4096)
        context = {
            "event_description": request.event_description,
            "request_type": request.request_type,
        }
        # v5.7.0 — KST 기준 '오늘'. naive datetime.now() 는 UTC VM 에서 하루 어긋남
        # (일일 브리핑 06:00 KST = 전날 21:00 UTC). WRITE-AP-11 의 진짜 원인.
        context["current_date"] = today_kst()
        context["instruction"] = f"오늘은 {context['current_date']}. 최신 정보 기준으로 분석할 것."
        self.system_prompt = SYSTEM_PROMPT.replace("{current_date}", context["current_date"])
        raw_text = await super().analyze(context)
        return self._parse_json_response(raw_text, ContextAnalysis)
