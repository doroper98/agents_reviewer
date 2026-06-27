"""Configuration for the Event Analysis Team system using Pydantic BaseSettings."""

from __future__ import annotations

import os

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_project_name: str = "analysis-reports"
    report_output_dir: str = "reports"
    # v5.6.3 — 관리자 비공개 목록 페이지 토큰. 설정 시 {token}.html 에 전체 보고서
    # 목록(토큰 URL 포함)을 생성 — 접속 주소는 /{token} (Pages 가 .html 숨김 서빙,
    # v7.6.1 admin- 접두사 제거). 관리자만 아는 *고정* unlisted 주소(즐겨찾기용).
    # 미설정 시 미생성 (공개 index 는 목록 없음, /reports 로 대체). URL-safe 영숫자
    # 난수 권장 (파일명으로 그대로 쓰임).
    admin_index_token: str = ""
    model_name: str = "claude-opus-4-6"
    model_name_light: str = "claude-sonnet-4-6"
    use_cli_mode: bool = True

    # v6.1.0 — GitHub raw mirror (src/tools/github_mirror.py).
    # 보고서 산출물(.html/.md/.json/.bundle.json)을 Cloudflare Pages 외에 공개
    # GitHub repo 에도 미러해, ``*.pages.dev`` 를 egress 허용목록에서 막는 샌드박스
    # 환경(Claude Code on the web 등)의 다른 AI 가 ``raw.githubusercontent.com``
    # 링크로 보고서를 직접 열람할 수 있게 한다. 토큰/repo 미설정 시 graceful skip
    # — Cloudflare 흐름 byte-equal 보존. PAT 는 단일 공개 repo Contents read/write
    # 권한이면 충분 (.env 에만 보관, git 커밋 금지).
    github_mirror_token: str = Field(
        default="",
        validation_alias=AliasChoices("GITHUB_MIRROR_TOKEN", "github_mirror_token"),
    )
    github_mirror_repo: str = Field(  # "owner/repo" 형식
        default="",
        validation_alias=AliasChoices("GITHUB_MIRROR_REPO", "github_mirror_repo"),
    )
    github_mirror_branch: str = Field(
        default="main",
        validation_alias=AliasChoices("GITHUB_MIRROR_BRANCH", "github_mirror_branch"),
    )
    github_mirror_path: str = Field(  # repo 안 보고서 경로 prefix (빈 값=루트)
        default="reports",
        validation_alias=AliasChoices("GITHUB_MIRROR_PATH", "github_mirror_path"),
    )

    # v5.2.0 — Market data fetcher API keys (src/tools/market_fetcher.py).
    # 셋 다 비어있어도 보고서 정상 진행 — 차트만 빈 series 로 emit. 각 키는
    # 무료 발급:
    #   FRED: https://fred.stlouisfed.org/docs/api/api_key.html (DXY/UST/WTI/금)
    #   ECOS: https://ecos.bok.or.kr/api/ (국고채/환율 한국 macro)
    #   KRX:  현재 미사용 (data.krx.co.kr public endpoint 무인증)
    fred_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FRED_API_KEY", "fred_api_key"),
    )
    ecos_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ECOS_API_KEY", "ecos_api_key"),
    )
    krx_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("KRX_API_KEY", "krx_api_key"),
    )
    # v7.9.2 — data.krx.co.kr getJsonData 가 로그인 필수로 바뀜(응답 'LOGOUT', HTTP 400).
    # 무료 data.krx.co.kr 계정. pykrx 의 로그인 핸드셰이크 재사용(krx_client.ensure_session).
    # 미설정 시 선물·옵션·breadth fetch 만 graceful skip — 보고서는 정상 진행.
    krx_id: str = Field(
        default="",
        validation_alias=AliasChoices("KRX_ID", "krx_id"),
    )
    krx_pw: str = Field(
        default="",
        validation_alias=AliasChoices("KRX_PW", "krx_pw"),
    )

    # v7.9.0 — 한국 장마감 브리핑 시장 내부 데이터(선물·옵션 그릭 + 시장 폭).
    # market_briefing 스케줄러가 fetch_kr_market_internals=True 로 호출할 때만 작동.
    # 일반 보고서엔 무영향. 무로그인 data.krx.co.kr 공개 엔드포인트 사용 → 키 불요.
    enable_kr_derivatives: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_KR_DERIVATIVES", "enable_kr_derivatives"),
    )
    derivatives_risk_free: float = Field(
        default=0.03,
        validation_alias=AliasChoices("DERIVATIVES_RISK_FREE", "derivatives_risk_free"),
    )
    enable_market_breadth: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_MARKET_BREADTH", "enable_market_breadth"),
    )
    breadth_cache_path: str = Field(
        default="data/market_internals.sqlite",
        validation_alias=AliasChoices("BREADTH_CACHE_PATH", "breadth_cache_path"),
    )
    skew_cache_path: str = Field(
        default="data/iv_skew.sqlite",
        validation_alias=AliasChoices("SKEW_CACHE_PATH", "skew_cache_path"),
    )

    # v8.2.8 — 편집장(NarrativeComposer) CLI 출력 캡처를 구조화 JSON envelope 로.
    # `--output-format text` 가 긴 응답에서 stdout 머리(앞부분)를 잃어 보고서가
    # head-loss → 파싱 불가 → minimal fallback 으로 떨어지던 회귀(2026-06-27 르포
    # 588자 미파싱; bot.log 상 수개월 누적된 systemic 결함) 대응. json 모드는 단일
    # envelope `{...,"result":"<본문>"}` 로 와 전체 텍스트를 안전 추출(머리 손실 없음).
    # 기본 ON. 구버전 CLI 등으로 문제가 생기면 `V8_CLI_JSON_OUTPUT=0` 로 즉시 끈다
    # (그러면 기존 text 캡처 경로로 byte-equal 복귀).
    cli_json_output: bool = Field(
        default=True,
        validation_alias=AliasChoices("V8_CLI_JSON_OUTPUT", "cli_json_output"),
    )

    # V5 Phase 1A — ResearchDirector opt-in.
    # 켜져 있으면 orchestrator 가 Phase 1 (ContextAnalyst) 직후에 ResearchDirector
    # 를 호출해 AnalysisBrief 를 emit. 꺼져 있으면 design_via_heuristics 의
    # 결정적 fallback 만 사용 (LLM 0). v4.5.7 호출 경로의 byte-equal 보존을 위해
    # 디폴트 OFF. env: V5_RESEARCH_DIRECTOR=1 또는 .env 의 enable_research_director=true.
    enable_research_director: bool = Field(
        default=False,
        validation_alias=AliasChoices("V5_RESEARCH_DIRECTOR", "ENABLE_RESEARCH_DIRECTOR", "enable_research_director"),
    )

    # V5 Phase 2 — VisualPlanner opt-in.
    # 켜져 있으면 Editor (Phase 1) 또는 composer 직후에 VisualPlanner 를 호출해
    # Vega-Lite spec 으로 exhibit list 를 emit. 꺼져 있으면 plan_via_heuristics
    # 가 v4.5.7 의 ComposedSection.charts 를 그대로 통과 (단 EvidenceDataset
    # Guard 는 적용 — Phase 2A). 디폴트 OFF — v4.5.7 byte-equal 보존.
    # env: V5_VISUAL_PLANNER=1.
    enable_visual_planner: bool = Field(
        default=False,
        validation_alias=AliasChoices("V5_VISUAL_PLANNER", "ENABLE_VISUAL_PLANNER", "enable_visual_planner"),
    )

    # V5 Phase 7 — DeskEditor opt-in.
    # 켜져 있으면 Phase 7A (Deterministic Gate) 통과 후 DeskEditor (Opus 4.7
    # vision) 가 publish/hold/KILL 판정. 꺼져 있으면 v4.5.7 의 minimal fallback
    # 정책 그대로 ("어떻게든 발행"). 디폴트 OFF.
    # env: V5_DESK_EDITOR=1.
    enable_desk_editor: bool = Field(
        default=False,
        validation_alias=AliasChoices("V5_DESK_EDITOR", "ENABLE_DESK_EDITOR", "enable_desk_editor"),
    )

    # V5 Phase 1 — Editor Pass opt-in.
    # 켜져 있으면 Composer (drafting) 직후 Editor (Opus 4.7) 가 7-rubric 으로
    # 비평·재집필. 꺼져 있으면 composer DraftReport 그대로 사용 (v4.5.7 byte-
    # equal). 디폴트 OFF. env: V5_EDITOR_PASS=1.
    enable_editor_pass: bool = Field(
        default=False,
        validation_alias=AliasChoices("V5_EDITOR_PASS", "V5_EDITOR", "ENABLE_EDITOR_PASS", "enable_editor_pass"),
    )

    # V5 Phase 3 — Layout Typesetter opt-in.
    # 켜져 있으면 Editor 후 단계로 LayoutTypesetter (Sonnet 4.6) 가 9종 layout
    # primitive 중 섹션별로 결정. 꺼져 있으면 모든 섹션 'standard' (v4.5.7
    # byte-equal). 디폴트 OFF. env: V5_LAYOUT_TYPESETTER=1.
    enable_layout_typesetter: bool = Field(
        default=False,
        validation_alias=AliasChoices("V5_LAYOUT_TYPESETTER", "ENABLE_LAYOUT_TYPESETTER", "enable_layout_typesetter"),
    )

    # v5.5.0 — ReportBundle 핸드오프 (osint_generator 연동, 계약 v1) kill-switch.
    # 실제 트리거는 per-request ``AnalysisRequest.emit_bundle`` (/analyze --bundle).
    # 본 플래그는 전역 비활성화용 — 디폴트 ON (트리거가 없으면 어차피 emit 안 함).
    # env: V5_REPORT_BUNDLE=0 으로 끄기.
    enable_report_bundle: bool = Field(
        default=True,
        validation_alias=AliasChoices("V5_REPORT_BUNDLE", "ENABLE_REPORT_BUNDLE", "enable_report_bundle"),
    )

    # v5.5.6 — ReportBundle B안 폴백 SVG prerender (계약 §5). 복잡 4종
    # (map/choropleth/network/sankey) 만 Playwright 로 정적 SVG 렌더해
    # prerendered_svg 에 담음. 디폴트 ON — Playwright/chromium 미설치 시 graceful
    # None (기존 동작 = 계약 §5). 끄려면 V5_BUNDLE_PRERENDER_SVG=0.
    enable_bundle_prerender: bool = Field(
        default=True,
        validation_alias=AliasChoices("V5_BUNDLE_PRERENDER_SVG", "ENABLE_BUNDLE_PRERENDER", "enable_bundle_prerender"),
    )

    # v5.1.0 — Daily Briefing Scheduler.
    # 매일 ``daily_briefing_time`` (DAILY_BRIEFING_TZ 기준) 에 깨어나
    # ``/briefing_on`` 으로 구독한 모든 텔레그램 채팅에 "간밤 산업·지정학·정치·전쟁"
    # 심층 보고서를 자동 송신. 스케줄러 task 는 봇 프로세스 안 asyncio loop 에서
    # 항상 기동되지만, 트리거 시각에 실제 분석 실행 여부는 ``daily_briefing_enabled``
    # 가 게이트. enabled=false 시 구독은 받지만 분석은 스킵.
    daily_briefing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DAILY_BRIEFING_ENABLED", "daily_briefing_enabled",
        ),
    )
    daily_briefing_time: str = Field(
        default="06:00",
        validation_alias=AliasChoices(
            "DAILY_BRIEFING_TIME", "daily_briefing_time",
        ),
    )
    daily_briefing_tz: str = Field(
        default="Asia/Seoul",
        validation_alias=AliasChoices(
            "DAILY_BRIEFING_TZ", "daily_briefing_tz",
        ),
    )

    # v5.5.9 — Market Close Briefing Scheduler (한국 장마감 자동 브리핑).
    # 매일 ``market_briefing_time`` (MARKET_BRIEFING_TZ 기준, 디폴트 18:30 KST) 에
    # pykrx 거래일 가드를 거쳐 ``/market_brief_on`` 구독자에게 한국 주식시장
    # 구조 해석 보고서 자동 송신. 페르소나는 ``market_briefing_persona_path`` 의
    # 파일에서 startup 시 1회 로드 + event_description 앞에 prime.
    # v7.9.5 — 17:00 → 18:30 (데이터 정합성): KRX 일별 통계·외국인/기관 확정 수급·
    # 파생 미결제약정이 18:00~18:30 에 안정화되므로(잠정치 출렁임 회피), 선물·옵션
    # 그릭·시장 폭 실데이터가 종가 확정치로 들어오도록 트리거를 늦춤.
    market_briefing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MARKET_BRIEFING_ENABLED", "market_briefing_enabled",
        ),
    )
    market_briefing_time: str = Field(
        default="18:30",
        validation_alias=AliasChoices(
            "MARKET_BRIEFING_TIME", "market_briefing_time",
        ),
    )
    market_briefing_tz: str = Field(
        default="Asia/Seoul",
        validation_alias=AliasChoices(
            "MARKET_BRIEFING_TZ", "market_briefing_tz",
        ),
    )
    market_briefing_persona_path: str = Field(
        default="prompts/market_briefing_persona.md",
        validation_alias=AliasChoices(
            "MARKET_BRIEFING_PERSONA_PATH", "market_briefing_persona_path",
        ),
    )

    # === V6 Phase V6-1 — Codex 외부 critic CLI 통합 (Tier 0 spike) ===
    # REFACTOR_V6_PLAN.md §3 Phase V6-1. codex CLI (ChatGPT 구독) 를 headless 로
    # 호출해 ComposedReport 를 사실 검수하고 FactVerdict 를 받는 경로의 마스터 스위치.
    # 디폴트 OFF — 꺼지면 src/agents/codex_critic.py 의 critique() 가 즉시 skip
    # verdict 를 반환해 v5.8.8 단일패스 byte-equal (AP-V6-3/12). Phase 1 단계에선
    # orchestrator 가 본 모듈을 호출하지 않으므로 호출 경로 자체가 불변.
    # env: V6_CODEX_CRITIC=1.
    enable_codex_critic: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_CODEX_CRITIC", "ENABLE_CODEX_CRITIC", "enable_codex_critic"),
    )
    # codex CLI 실행 파라미터 (VM spike 가 실제 호출 형태를 확정 — 전부 override 가능).
    # 기본 호출: ``codex exec`` 에 프롬프트를 stdin 으로 전달, stdout=verdict JSON.
    codex_bin: str = Field(
        default="codex",
        validation_alias=AliasChoices("V6_CODEX_BIN", "codex_bin"),
    )
    codex_subcommand: str = Field(
        default="exec",
        validation_alias=AliasChoices("V6_CODEX_SUBCOMMAND", "codex_subcommand"),
    )
    codex_extra_args: str = Field(
        default="--skip-git-repo-check --sandbox read-only",
        validation_alias=AliasChoices("V6_CODEX_EXTRA_ARGS", "codex_extra_args"),
    )
    codex_model: str = Field(
        default="",
        validation_alias=AliasChoices("V6_CODEX_MODEL", "codex_model"),
    )
    codex_timeout_s: int = Field(
        default=180,
        validation_alias=AliasChoices("V6_CODEX_TIMEOUT_S", "codex_timeout_s"),
    )
    # Codex critic 페르소나 — *검수자* 관점(도메인 인식 팩트체크 데스크)을 prompt 에
    # 주입. 빈 값이면 기본 critic 지침만 (byte-equal). 파일 경로 (market_briefing_persona
    # 패턴). 작성 페르소나가 아님 — codex 는 본문을 쓰지 않는다 (AP-V6-11).
    # env: V6_CODEX_PERSONA_PATH.
    codex_critic_persona_path: str = Field(
        default="prompts/codex_critic_persona.md",
        validation_alias=AliasChoices("V6_CODEX_PERSONA_PATH", "codex_critic_persona_path"),
    )

    # === V6 Phase V6-2 — 결정적 사실 사전필터 가드 (LLM 0) ===
    # 본문의 명백한 사실 위반(출처 없는 수치 / scope 모호 / 시장 수치 불일치 / NaN)을
    # codex 호출(=ChatGPT 한도) 전에 0-LLM 으로 검출. 초기 log-only — drop/enforce 안
    # 하고 GuardFlag 적립·경고만 (REFACTOR_V6_PLAN.md §4.5 측정우선). 디폴트 OFF —
    # orchestrator 미연결로 byte-equal. env: V6_FACT_GUARDS=1.
    enable_fact_guards: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_FACT_GUARDS", "ENABLE_FACT_GUARDS", "enable_fact_guards"),
    )
    # composer SYSTEM_PROMPT 에 `=== 사실 규율 (V6) ===` 블록 주입 (scope 명시 / 출처없는
    # 특정수치 금지 / 신규성 구분 / 시장 시점 라벨·단일소스 / 주장 귀속 / 인과 헤지 등,
    # WRITE-AP-11/14~21). 디폴트 OFF — 꺼지면 compose 프롬프트 byte-equal. V5 어조와 직교.
    # env: V6_FACT_PROMPT=1.
    enable_fact_prompt: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_FACT_PROMPT", "ENABLE_FACT_PROMPT", "enable_fact_prompt"),
    )
    # ContextAnalyst 웹검색 최신성 제한 — 당일/최근 브리핑은 최근 24~48h 출처 우선 +
    # 상대 시점("이틀 전")을 발행일 기준으로 환산 (stale_sourcing 차단). 디폴트 OFF —
    # 꺼지면 context_analyst 프롬프트 byte-equal. env: V6_RECENCY_BOUND=1.
    enable_recency_bound: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_RECENCY_BOUND", "ENABLE_RECENCY_BOUND", "enable_recency_bound"),
    )

    # === V6 Phase V6-4 — Codex 미학 검수 (vision, 렌더 PNG) ===
    # 발행 후 차트 PNG 를 codex 비전(`codex exec -i`)에 넣어 미학·데이터 정합을 교차검수.
    # V5 deterministic_gate / chart_critic 와 병행(교차검증). 현재 log-only(측정) — 차트
    # 자동수정 안 함. 디폴트 OFF, Playwright/codex 비전 미가용 시 graceful skip.
    # env: V6_CODEX_VISUAL=1.
    enable_codex_visual: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_CODEX_VISUAL", "ENABLE_CODEX_VISUAL", "enable_codex_visual"),
    )

    # === V6 Phase V6-5 — Codex 웹 verify (bounded) ===
    # 켜지면 codex 가 검수 시 *자체 웹검색* 으로 우리 근거에 없는 사실까지 ground truth
    # 대조 + 사용 URL 을 cited_urls/source_urls 에 명시. 웹은 변동 → ON 만 비결정,
    # OFF 는 byte-equal. 검색 횟수는 codex_websearch_cap 으로 프롬프트 bound (AP-V6-2).
    # env: V6_CODEX_WEBVERIFY=1.
    enable_codex_webverify: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_CODEX_WEBVERIFY", "ENABLE_CODEX_WEBVERIFY", "enable_codex_webverify"),
    )
    # codex 웹검색 인자 (보통 비워둠). codex 0.136.0 은 웹검색이 *기본 ON* 이라
    # 별도 플래그 불요 — webverify 는 프롬프트 블록으로 구동(VM 확정 2026-06-03).
    # 특정 환경에서 명시 제어 필요 시만 채움 (예: `-c web_search="live"`).
    codex_websearch_args: str = Field(
        default="",
        validation_alias=AliasChoices("V6_CODEX_WEBSEARCH_ARGS", "codex_websearch_args"),
    )
    codex_websearch_cap: int = Field(
        default=3,
        validation_alias=AliasChoices("V6_CODEX_WEBSEARCH_CAP", "codex_websearch_cap"),
    )

    # === V6 Phase V6-7 — 바이라인 신뢰장치 ===
    # 발행물 말미에 "Claude Opus 4.7 작성 / OpenAI Codex (GPT-5.5) 검수" 도장.
    # 검수 *실제 수행* 시에만 렌더(degrade/skip 시 검수 줄 생략 — 거짓 신뢰 금지 AP-V6-10).
    # 버전은 config(작성=COMPOSER_MODEL) + codex 배너 실측(검수). 디폴트 OFF.
    # env: V6_BYLINE=1.
    enable_byline: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_BYLINE", "ENABLE_BYLINE", "enable_byline"),
    )

    # === V6 Phase V6-6 — 자율 보강 (critique 적립 → 소프트가드 → 승격 후보) ===
    # 켜지면 codex 지적을 critique_log.jsonl 에 영구 적립 + 재발 시그니처를 soft_guards.yaml
    # 에 자동 등재(log-only) + 정식 승격 후보 로그 표면화. 적립↔적용 분리(AP-V6-9) —
    # 정규 가드/프롬프트/fixture 편입은 *사람 게이트*. 코드/프롬프트 무변경이라 byte-equal.
    # env: V6_AUTOLEARN=1.
    enable_autolearn: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_AUTOLEARN", "ENABLE_AUTOLEARN", "enable_autolearn"),
    )

    # === V6 Phase V6-8 — per-fact provenance ===
    # 켜지면 ContextAnalyst 가 각 사실에 source_date/scope_note/source_url 을 구조화 emit
    # (`ContextAnalysis.provenance`). 이 데이터로 NoveltyDelta/Scope 가드가 *프롬프트 없이
    # 데이터로* 판정 (지금은 production 에서 미공급이라 inert). additive·Optional — 구
    # 데이터 호환, flag OFF byte-equal. env: V6_PROVENANCE=1.
    enable_provenance: bool = Field(
        default=False,
        validation_alias=AliasChoices("V6_PROVENANCE", "ENABLE_PROVENANCE", "enable_provenance"),
    )

    # === V7 Track C — 기준시점 계약 (REFACTOR_V7_PLAN.md §3) ===
    # "사실은 맞지만 보고서가 필요로 하는 시점과 다른" 팩트(6/1↔6/5 회귀) 차단.
    # 켜지면 ① 결정적 가드 2종(DateAnchoredMarket/StaleAnchor)이 critic 사전필터에 합류,
    # ② composer/codex/reviser 3곳에 reference_frame(종목별 최신 가용 일자) 블록 주입,
    # ③ codex error_class 에 wrong_timeframe 추가 + 잔존 시 착지 drop.
    # 디폴트 OFF — 프롬프트·가드 모두 미주입 = v6.2.0 byte-equal. env: V7_REF_FRAME=1.
    enable_ref_frame: bool = Field(
        default=False,
        validation_alias=AliasChoices("V7_REF_FRAME", "ENABLE_REF_FRAME", "enable_ref_frame"),
    )

    # === V7 Track B — 스크롤 내러티브 아크 (REFACTOR_V7_PLAN.md §2) ===
    # 켜지면 freeform_essay 보고서에 기승전결(起承轉結) 한자 배경 워터마크 + 스크롤
    # 연동 전환 엔진(템플릿 인라인)이 렌더된다. 발행본 소급 영향 없음(템플릿/CSS 는
    # 보고서 HTML 에 인라인). 디폴트 OFF = v6.2.0 byte-equal. env: V7_SCROLL_ARC=1.
    enable_scroll_arc: bool = Field(
        default=False,
        validation_alias=AliasChoices("V7_SCROLL_ARC", "ENABLE_SCROLL_ARC", "enable_scroll_arc"),
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def codex_cmd_args(self) -> list[str]:
        """codex CLI 의 subcommand + extra args 를 토큰 리스트로 (bin 제외)."""
        args = [self.codex_subcommand] if self.codex_subcommand else []
        if self.codex_extra_args.strip():
            args.extend(self.codex_extra_args.split())
        return args

    @property
    def allowed_chat_ids(self) -> list[int]:
        """Parse allowed chat IDs from ALLOWED_CHAT_IDS env var."""
        raw = os.getenv("ALLOWED_CHAT_IDS", "")
        if raw.strip():
            return [int(x.strip()) for x in raw.split(",") if x.strip()]
        return []

    @model_validator(mode="after")
    def _select_mode(self) -> "Config":
        """Auto-select API mode when an API key is provided."""
        if self.anthropic_api_key:
            self.use_cli_mode = False
        return self


def get_config() -> Config:
    """Create and return a Config instance."""
    return Config()
