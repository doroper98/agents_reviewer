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
    # v5.6.3 — 관리자 비공개 목록 페이지 토큰. 설정 시 admin-{token}.html 에 전체
    # 보고서 목록(토큰 URL 포함)을 생성 — 관리자만 아는 *고정* unlisted 주소(즐겨찾기용).
    # 미설정 시 미생성 (공개 index 는 목록 없음, /reports 로 대체). 긴 난수 권장.
    admin_index_token: str = ""
    model_name: str = "claude-opus-4-6"
    model_name_light: str = "claude-sonnet-4-6"
    use_cli_mode: bool = True

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
    # 매일 ``market_briefing_time`` (MARKET_BRIEFING_TZ 기준, 디폴트 17:00 KST) 에
    # pykrx 거래일 가드를 거쳐 ``/market_brief_on`` 구독자에게 한국 주식시장
    # 구조 해석 보고서 자동 송신. 페르소나는 ``market_briefing_persona_path`` 의
    # 파일에서 startup 시 1회 로드 + event_description 앞에 prime.
    market_briefing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MARKET_BRIEFING_ENABLED", "market_briefing_enabled",
        ),
    )
    market_briefing_time: str = Field(
        default="17:00",
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
        default="",
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
