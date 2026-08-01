---
tier: 1
last_synced_with: v7.5.1
ssot_for:
  - "AI 에이전트 행동 규칙 (Execution Rules)"
  - "Change Propagation 매트릭스 (코드 변경 → 갱신할 문서)"
  - "Tier 4 파이프라인 정책 (2-call: context + composer)"
depends_on:
  - "docs/STYLEGUIDE.md (코드 컨벤션 SSOT)"
  - "docs/MONO_THEME_GUIDE.md (테마/패턴 SSOT)"
  - "DOCS_GOVERNANCE_V3.md (문서 거버넌스 SSOT)"
last_review: 2026-05-05
---

# CLAUDE.md — Event Analysis Team Agent System

> **🔴 운영 모드 SSOT — 절대 잊지 말 것.** 이 봇은 **Claude Code CLI 구독 플랜** 으로 돈다. `.env` 의 `ANTHROPIC_API_KEY` 는 *빈 값이 정상*. [src/config.py:131-135](src/config.py) 의 `_select_mode` 가 키가 비어있으면 자동으로 `use_cli_mode=True` 선택. `bot.log` 의 `WARNING: ANTHROPIC_API_KEY is not set` 은 [src/main.py:29](src/main.py) 가 무조건 찍는 노이즈 — 무시. 사용자에게 "API 키 채우라" 같은 조언 절대 금지. 사용자가 명시적으로 "API 로 바꿔달라" 라고 하지 않는 한 키 채우라고 하지 말 것.

> **🔴 봇 재시작·운영 SSOT — systemd 서비스다 (사용자 강력 요청, 2026-07-11 실제 사고).**
> VM 의 봇은 **systemd 서비스 [`agents-reviewer.service`]** 로 돈다 (`enabled` — 부팅
> 시 자동 기동, `/etc/systemd/system/agents-reviewer.service`, 실행 유저 `ubuntu`,
> `.../venv/bin/python -m src.main`). **재시작·재배포 반영은 딱 한 줄:**
> ```
> sudo systemctl restart agents-reviewer.service
> ```
> - 상태 `systemctl status agents-reviewer.service` · 로그 `journalctl -u agents-reviewer.service -f` · 중지 `sudo systemctl stop agents-reviewer.service`.
> - `.env` 변경도 이 restart 한 줄로 반영 (config 는 startup 1회 로드). 재배포 = `git pull` 후 이 한 줄.
> - **🚫 절대 `nohup python -m src.main` 수동 기동 금지.** systemd 인스턴스와 *중복* 으로
>   떠서 텔레그램 `getUpdates` **Conflict** + 메모리 이중 낭비 → 1GB VM 에서 **OOM 프리즈**
>   유발(2026-07-11 실제 사고 — 이 규칙이 없어 nohup 안내 → 봇 2개 → 전면 프리즈). 봇을
>   완전히 죽여야 하면 `pgrep -af 'src\.main'` 로 확인 후 systemd MainPID 외 잔재만 정리.
> - **[VM_DEPLOY_PLAYBOOK.md](docs/VM_DEPLOY_PLAYBOOK.md) §1 의 `pkill`+`nohup` 블록은
>   systemd 도입 전 legacy** — systemd 서비스가 있으면 그 블록 대신 이 한 줄을 쓴다.

> **🔴 제1규칙 — 보고서 핫픽스 시퀀스 (사용자가 발행된 보고서의 결함을 지적하면 *즉시* 이 순서로).**
> 사용자가 발행된 보고서(보통 `analysis-reports.pages.dev/...` 링크 + "이 문구 / 이 차트 / 이 표현 고쳐"
> 형태)의 결함을 지적하면 — 되묻지 말고 — 아래 시퀀스로 이해·진행한다. SSOT 도구는
> [scripts/patch_report.py](scripts/patch_report.py) (LLM 0, ~$0, **URL 보존**, `revision` 증가 — 내용 변경=정수부 +1·소수부 리셋 / `--rerender-only` 표현·레이아웃 변경=소수부 +1, 표기 `Rev major.minor`, v6.0.5).
>
> **① 트리거 인식.** "이거 고쳐 / 패치해 / 무슨 뜻이야 + 보완" + 보고서 링크·문구 인용 = 핫픽스. 즉시 착수.
>
> **② report_id 추출.** URL `…/analysis_<report_id>` 의 `analysis_` 뒤 전체가 `report_id`
> (해시 접미사 포함). 예: `…/analysis_20260530_163305_9a4dd1d5ed` → `20260530_163305_9a4dd1d5ed`.
> 파일은 `reports/analysis_<report_id>.json` ([patch_report.py:549](scripts/patch_report.py)).
>
> **③ 범위 판정** ([docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md) §결정트리):
> 이 보고서 1건만 → ③-A. 모든 보고서에 재발할 시스템 회귀 → ③-A + ③-B *둘 다*.
> - **③-A 발행본 핫픽스** (이미 나간 보고서): `scripts/patch_report.py <report_id>` 로
>   `--replace "OLD=NEW"` (전문 용어 평이화) / `--add-footnote "SEC:용어=설명"` (불가피한 핵심 용어)
>   / `--remove-chart`·`--remove-section`·`--map-*` (차트·지도) / `--recompose` (통째 재작성).
>   **반드시 `--dry-run` 으로 매치 수 먼저 확인 → 그다음 실제 적용.**
>   정정을 텔레그램 구독자에게도 보내려면 `--broadcast` 추가 — 정정된 `broadcast_summary`
>   (이 필드도 `--replace` 치환 대상) + 동일 URL 을 `[정정]` 머리표 붙여 *새 메시지* 로
>   재발송 (원본 메시지 in-place edit 아님; message_id 미저장). 대상은 `--chat-id` 또는
>   `ALLOWED_CHAT_IDS`. 배포된 http URL 있을 때만 동작.
> - **③-B 소스 재발 방지** (시스템 회귀일 때만): composer `SYSTEM_PROMPT` + 해당 SSOT
>   ([REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) §2.1 어휘표 / [REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md) WRITE-AP-N
>   / [CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) CHART-AP-N) 동시 갱신 후 커밋·푸시.
>
> **④ 실행 환경 분기.** **VM(봇 가동기)**: 위 명령 실행 — `reports/*.json` + Cloudflare
> 자격증명이 거기 있음. 단 **반드시 repo 루트에서 venv 활성 후** (`cd ~/agents_reviewer &&
> source venv/bin/activate`). Ubuntu 는 `python` 이 없고 `python3` 만 있으며, 홈(`~`)에서
> 바로 돌리면 `src.*` import·의존성이 안 잡힌다 (실제 재발한 gotcha). **Claude Code on the
> web / 원격 컨테이너**: fresh clone 라 `reports/`
> 없음 + Cloudflare 토큰 없음 → 직접 실행 불가. 이때는 ③-A 명령을 **복사용 한 줄** 로 정확히
> 만들어 주고("VM 에서 실행하세요"), ③-B 소스 패치만 내가 커밋·푸시한다.
>
> **⑤ 평이화 어휘는 SSOT 1곳.** `--replace` 매핑은 [REPORT_STYLE_GUIDE.md §2.1](docs/REPORT_STYLE_GUIDE.md)
> 어휘표 + composer `SYSTEM_PROMPT` 평이화 예시와 *항상 정합*. 새 매핑 쓰면 그 두 곳에도 추가.
>
> **⑥ 🔴 시장 수치 핫픽스 — 외부 1차 출처 검증 불변규칙 (2026-06-19, 실제 사고).**
> 발행본의 시장 수치(지수/환율/종가/등락률)를 정정할 때 **보고서 본문·표가 적어둔 값을
> "정답"으로 신뢰하고 그 값으로 치환하지 말 것.** 보고서가 틀렸으니 고치는 것인데, 그
> 보고서의 다른 필드 값도 똑같이 오염됐을 수 있다 (실제: 본문 7,516 ↔ 표 8,864 둘 다
> 오답, 실제는 9,063.84). **반드시 `WebSearch`/`WebFetch` 또는 KRX 로 그 날짜 실제 종가를
> *먼저* 검증**한 뒤, 단일 출처 요약을 그대로 믿지 말고 **2곳 이상 교차확인 + 산술 정합
> (직전봉×(1+등락률)=종가) 검산** 후에야 `--replace` 값을 확정한다. 추측 숫자 박기 절대 금지.

## 🔴 시장 데이터 무결성 — 날짜·연도·소스 정합 (재발방지 SSOT, v7.9.16)

> 2026-06-19 브리핑 사고: ① 코스피만 6/17 봉(해외 Yahoo `^KS11` EOD 지연)인데 삼성전자·환율은
> 6/18 (cross-source 기준일 불일치), ② 본문은 환각값 7,516(+0.31%), 표 카드는 8,864(6/17),
> 실제는 9,063.84(+2.25%) — codex 가 켜진 채(web_verified=True) 돌았는데도 *틀린 time_series
> 와의 일치만* 봐서 전부 통과. 다층 방어:
> 1. **데이터 소스** — 코스피·코스닥 지수는 KRX(pykrx 1001/2001) primary + Yahoo fallback
>    (`market_fetcher`, v7.9.15). 해외 피드 지연이 근원.
> 2. **결정적 가드** — [deterministic_guards.py:`market_anchor_coherence_guard`](src/factcheck/deterministic_guards.py)
>    (v7.9.16): 같은 한국거래소 지표 기준일 불일치(`stale_market_anchor`) + 최신 봉 연도≠발행연도
>    (`wrong_year_market_anchor`) 를 *데이터 계층* 에서 high 검출. `run_fact_guards` base 합류
>    (log-only, `V6_FACT_GUARDS`). prose 가드 시야 밖인 표 카드·차트와 무관하게 동작.
> 3. **codex 페르소나** — 시장 수치는 time_series 만 믿지 말고 *웹 직접 대조*, 구조화 필드
>    (표/차트) 와 prose 의 intra-report 모순, *연도까지* 확인, 한국 지표 기준일·수급 방향
>    정합을 high 로 검수. SSOT 2파일 + 코드 `_CRITIC_INSTRUCTIONS` 정합
>    ([codex_critic_persona.md](prompts/codex_critic_persona.md) §1 / [market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md) §1-a~d / [codex_critic.py](src/agents/codex_critic.py)).
> 4. **운영** — 이 가드들이 실제로 돌려면 VM `.env` 에 **`V6_FACT_GUARDS=1`** (+ 기준시점
>    가드 원하면 `V7_REF_FRAME=1`) 필요. 꺼져 있으면 검출 0 (가드는 있는데 작동 안 함).

## 🔴 OSINT(osint_generator) 교신 규칙 — 복붙 중계 금지 SSOT

> **🔴🔴 절대 규칙 (사용자 강력 요청, 2026-07-09).** `osint_generator`(영상
> consumer)에게 전달·질문·통지할 게 생기거나 osint 회신을 처리할 때 — **사용자를
> 복붙 중계기로 쓰지 말 것.** 전용 교신 저장소 **[doroper98/reviewer_osint_q_a](https://github.com/doroper98/reviewer_osint_q_a)**
> 에 파일로 직접 주고받는다. 규칙 정본은 그 repo 의 `PROTOCOL.md` (SSOT). 아래는
> 그 요약 — 두 문서는 항상 정합.
>
> **① 트리거.** 계약 변경 통지 / 질문 / 요청 / osint 회신 처리 — 무엇이든 osint 와
> 오가야 하면 이 채널을 쓴다. 답변을 텔레그램·채팅으로 사용자에게 넘겨 "osint 에
> 전달하세요" 라고 시키는 것 금지.
>
> **② 메시지 종류(kind) = 질문(q) / 통지(n).** *상대의 답변·결정이 필요* 하면
> **질문 `q`**(open→answered→closed), *이미 정해진 걸 알리는* 계약 변경·릴리스·결정
> 이면 **통지 `n`**(posted→(acked)→closed). 통지는 답변 강제 X — 상대 동기화가
> 필요하면 `ack_required: yes`.
>
> **③ 한 사안 = 한 스레드 파일.** 새로 전달·질문·통지할 게 생기면 항상 **새 파일**을
> `reviewer_osint_q_a/threads/` 에 만든다. 파일명 코드 체계:
> `yyyy_mm_dd_hhmmss_agent_reviewer_bot_<kind>_nn.md` (`<kind>`=`q`|`n`, `nn`=발신자·
> kind 별 2자리 일련번호, 타임스탬프 KST — `TZ=Asia/Seoul date +%Y_%m_%d_%H%M%S`).
> osint 발신은 `..._osint_generator_<kind>_nn.md`.
>
> **④ 스레드 구조.** 질문(q): `## 질문 / 전달`(발신자) → `## 답변`(수신자) →
> `## 조치 · 종결`(발신자). 통지(n): `## 통지`(발신자) → (ack 필요 시) `## 확인 ·
> 동기화`(수신자) → `## 종결`(발신자). 헤더 `status` 를 kind 흐름대로 갱신. 양식은
> repo 의 `templates/question_template.md` / `notice_template.md`.
>
> **⑤ 종결 의무.** 상대 답변·ack 를 받으면 실제 조치(코드/문서/버전 반영 또는 "조치
> 불요" 판단)를 하고 **종결 섹션을 채운 뒤 `status: closed`**. 답변만 받고 방치 금지
> — "어떻게 조치하고 종결했는지" 를 반드시 남긴다.
>
> **⑥ 답변·확인에 새 요청 금지.** 답변·확인·종결을 쓰다 새로 부탁·질문·통지할 게
> 생기면 거기 끼워넣지 말고 **별도 스레드 파일**(③)을 새로 만든다. 한 스레드는 원 사안만.
>
> **⑦ 실행 환경.** 이 repo 가 세션 scope 에 없으면 `add_repo`(doroper98/
> reviewer_osint_q_a) 로 추가 후 clone. 자기 쪽 변경만 커밋·푸시(상대 섹션 임의
> 수정 금지), 커밋 메시지에 스레드 코드(`<kind>_nn`) 포함. 계약(IMAGE_BUNDLE_CONTRACT
> 등) 실제 반영은 agents_reviewer repo 에서 별도로 하고, 그 사실을 스레드
> `## 조치 · 종결` 에 기록해 교신과 코드 변경을 연결한다.

## Project Overview
텔레그램 메시지 → **2-call Tier 4 파이프라인** (ContextAnalyst Opus 5 + NarrativeComposer Opus 5, v8.5.0) → mono 테마 HTML 보고서 → Cloudflare Pages 배포. 시스템 흐름 SSOT 는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **V5 리팩토링 진행 중.** [REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md) 가 v5.0.0 의 4-Tier 17-Phase 마스터 플랜 SSOT. 현재는 Phase 0 (Baseline + SSOT Repair) 에 진입한 상태이고, v4.5.7 baseline 으로 코드·문서 정합성을 복원하는 작업이 진행된다. 코드는 v4.5.7 그대로 유지된다.

> **V6 트랙 (병행) — "workflow → agent".** [REFACTOR_V6_PLAN.md](REFACTOR_V6_PLAN.md) 가 v6.0.0 의 *사실 grounding + bounded Codex critic loop* 마스터 플랜 SSOT (v2 — Codex 외부 critic 중심 개정, 2026-06-03). 2026-06-01 NVIDIA 보고서 팩트체크 회귀(5종)에서 출발 — 자유 본문(`ComposedSection.prose`)에 evidence-binding 미적용 + fact-critic 루프 부재가 근본 결함. 핵심 결정: 빠진 critic 을 **외부 모델 `codex` CLI(ChatGPT 구독)** 로 내재화 — 교차 모델(GPT)이 Claude(Opus) confabulation 을 검수. 확정 루프 **`Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1)`** (재작성 bounded, 제어=0 LLM 위반카운트 AP-V6-5). Codex 는 사실/문구 + 차트 데이터 + 미학(렌더 PNG) + 자체 웹verify 까지 검수하나 **본문은 직접 쓰지 않음**(보완은 Opus, AP-V6-1/11). 착지=헤지 기본 + `unsourced_number` 만 drop. 자율 보강은 **적립↔적용 분리**(critique_log 자동적립 → 재발 시 log-only 소프트가드 자동 → 정식 프롬프트/가드 편입만 게이트, AP-V6-9). 바이라인("Opus 작성/Codex 검수")은 검수 실제 수행 시에만(AP-V6-10). 외부 의존은 graceful degrade(AP-V6-12). 모든 `V6_*` flag default OFF = v5.8.8 byte-equal (AP-V6-3). Phase V6-0(fixture) 완료, **Phase V6-1(codex spike) 코드 랜딩** — [src/agents/codex_critic.py](src/agents/codex_critic.py) + [src/models.py:FactVerdict](src/models.py)/`CritiqueClaim` + `Config.codex_*`(`V6_CODEX_CRITIC` default OFF) + 회귀 39종(모킹). orchestrator 미연결 = flag OFF byte-equal 자명. **VM 실연동 완료** (2026-06-03 — codex-cli 0.136.0/gpt-5.5 e2e 검수가 scope/unsourced 정확 검출, stdin·`-o`·비전 확정) — 측정 SSOT 는 [docs/V6_TEST_RESULTS.md](docs/V6_TEST_RESULTS.md). **Phase V6-2(사전필터) 가드 랜딩** — [src/factcheck/deterministic_guards.py](src/factcheck/deterministic_guards.py) 5종(unsourced/scope/novelty/market/nan, log-only, `V6_FACT_GUARDS` default OFF) + CodexCritic 검수자 페르소나 훅(`V6_CODEX_PERSONA_PATH`), T-1 결정적 5종 100%/0-FP. 프롬프트 하드닝 완료 — composer `_FACT_DISCIPLINE_BLOCK`(`V6_FACT_PROMPT`) + ContextAnalyst `_RECENCY_BLOCK`(`V6_RECENCY_BOUND`), 둘 다 flag OFF byte-equal(WRITE-AP-11/14~21 작성단계 차단·stale 검색 차단). **Phase V6-3(루프) orchestrator 연결** — [src/factcheck/critic_loop.py](src/factcheck/critic_loop.py) `CriticLoop`(Opus작성→Codex검수→Opus보완≤1→확인패스≤1, 제어 0-LLM, `apply_landing` unsourced drop) + [NarrativeComposer.revise_for_facts](src/agents/narrative_composer.py)(Opus 보완, 텍스트-only merge 로 차트 보존) + orchestrator Phase 2.5 flag-gated(`V6_CODEX_CRITIC`). T-3/T-4 9종+전체 71 pass, flag OFF byte-equal. **VM e2e 수렴** — 실제 codex(gpt-5.5)+Opus 루프가 NVIDIA 4위반을 보완 1회로 위반 0 수렴(scope/unsourced/novelty 교정). Phase V6-1/2/3 완료 + 풀 파이프라인 e2e 통과(실제 토픽 발행). **Phase V6-4(미학 vision, `V6_CODEX_VISUAL`)·V6-5(웹verify, `V6_CODEX_WEBVERIFY`) 완료 + VM 실연동 검증** (codex 비전이 실제 차트 판독·미학 지적, codex 웹검색이 정답+URL 반환; 둘 다 default OFF byte-equal). **Phase V6-6(자율보강 `V6_AUTOLEARN`)·7(바이라인 `V6_BYLINE`)·8(provenance `V6_PROVENANCE`) 완료 — V6 전 Phase(0~8) 랜딩.** 남은 것=7/6/8 재머지·재배포(v6.0.0 코어는 이미 main). V5 와 flag 네임스페이스 분리(`V5_*`/`V6_*`), composer SYSTEM_PROMPT 는 양 트랙이 직교하게 추가. 새 사실오류 회귀는 `tests/regression/fixtures/fact_discipline_scenarios.yaml` 에 append (error_class 1차 5종 + 2026-06-03 일일 브리핑 2차 확장 6종 = market_data_mismatch[최우선]/stale_sourcing/event_conflation/attribution_as_fact/causal_overreach/metric_label_ambiguity, 신규 class 는 사용자 게이트 승격으로만 추가).

## Tech Stack (v4.5.7)
- Language: Python 3.11+
- AI 모델: **claude-opus-5** (composer + context + 르포, v8.5.0 부터 일관 — 구 4.7/4.8. 르포 분기 배선 `NarrativeComposer.COMPOSER_MODEL_REPORTAGE` 은 보존, 값 동일) · claude-sonnet-4-6 (legacy 보존)
- AI 호출: Claude Code CLI (--dangerously-skip-permissions) 또는 Anthropic API
- Messaging: python-telegram-bot
- Data Validation: Pydantic v2
- Report: Jinja2 HTML, freeform_essay.html 단일 템플릿
- Visualization: d3 v7 SVG 차트 (composer-emitted inline data, **27종 type** — v5.3.0 FT/Economist 7종 + sankey + v7.0.0 bump/bullet/connected_scatter 3종 + v7.5.0 combo/diverging_bar/pyramid/dot_matrix 4종. v7.9.17 network 폐기 CHART-AP-36)
- Map: d3 + d3-geo + world-atlas TopoJSON 110m (maplibre-gl 폐기, mono guide §2)
- Theme: **5종 풀 (라이트 1 + 다크 4, v6.2.0)** — editorial_cream(라이트) / burgundy_mono / midnight_indigo / pine_forest(짙은 녹색) / graphite_slate(짙은 회색). v5.0.2 부터 보고서마다 `random.choice` 로 선택 (event_type 무관, 시각 다양성 목적). 모든 테마는 *동일 레이아웃* — bg/card/text/accent 만 다름. SSOT 는 [src/lens_policy.py:ALL_THEMES](src/lens_policy.py) + [src/templates/report.css](src/templates/report.css) 의 `[data-theme="..."]` 블록. v6.2.0 에서 slate_steel / forest_sage / dusk_rose / paper_classic 4종 풀+CSS 삭제 (짙은 계열 중심 재편, 사용자 요청). legacy `light_mono` CSS 는 보존되었으나 풀에서 빠짐 — 직접 지정 시만 사용 가능.
- Font: Newsreader (display serif, 영문/숫자) + IBM Plex Sans KR (본문) + IBM Plex Mono. Noto Serif KR 한국어 폴백.
- Hosting: Cloudflare Pages (wrangler CLI 배포)
- Infra: Oracle Cloud VM (무료 티어)

## Agents (v4.5.7 Tier 4)
실제 호출되는 에이전트는 **2개**:
1. **ContextAnalyst** (Opus 5, 웹 검색) — 사실 / 타임라인 / 핵심 수치 / 출처 수집. mode 별 max_tokens (fast 4K / standard 4K / deep 10K, v4.5.7).
2. **NarrativeComposer** (Opus 5, 단일 호출) — 행위자 / 구조 / 시나리오 / 모순 분석 + 보고서 작성 + 차트 / 지도 데이터 emit. mode 별 max_tokens (fast 12K / standard 20K / deep 32K, v4.5.4 의 `MAX_TOKENS_BY_MODE`).

V5 Phase 1A 부터 추가 가능한 에이전트:

3. **ResearchDirector** (Opus 5, MAX_TOKENS=6000) — `Config.enable_research_director` 가 켜진 환경 (env: `V5_RESEARCH_DIRECTOR=1`) 에서만 호출. 사용자 질의 + EvidencePack 을 받아 AnalysisBrief (분석 설계도 — thesis / selected_methods / report_shape / visual_constraints / strategic_hint) 를 emit. 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에선 `design_via_heuristics` 결정적 fallback 이 LLM 호출 없이 동일 형태로 emit. 9종 method SSOT: [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md).

> legacy 7-agent (PlayerAnalyst, DynamicsAnalyst, ChainReactionAnalyst, ScenarioArchitect, SynthesisJudge, QualityInspector, VisualAnalyst) 는 v4.0.0 부터 호출 안 됐고 **v5.2.9 에서 모듈 자체가 삭제됨**. 11-lens pool + 11-archetype matrix 는 모듈 보존 (lens registry 가 `src/orchestrator.py:get_lens` 에서 import 되지만 호출 경로 없음).

세부 카탈로그는 [docs/CATALOGS.md §1](docs/CATALOGS.md). 이 문서는 카탈로그를 사본으로 갖지 않는다 (SSOT 단일 출처).

## Canonical Documents
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 아키텍처
- [docs/STYLEGUIDE.md](docs/STYLEGUIDE.md) — 코드 컨벤션
- [docs/TESTING.md](docs/TESTING.md) — 테스트 전략
- [docs/REPO_MAP.md](docs/REPO_MAP.md) — 파일/폴더 구조 설명
- [docs/CATALOGS.md](docs/CATALOGS.md) — 에이전트·렌즈·블록 카탈로그
- [docs/DATA_MODELS.md](docs/DATA_MODELS.md) — Pydantic 모델 도식
- [DEVLOG.md](DEVLOG.md) — 전체 개발 로그 (인프라, 트러블슈팅 포함)
- [CHANGELOG.md](CHANGELOG.md) — 사용자 관점 릴리스 노트
- [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) — 문서 거버넌스 (3-tier, SSOT 매트릭스)

## VM 배포 SOP (✱ 기능 개발 완료 후 반드시 사용자에게 안내)

> **SSOT: [docs/VM_DEPLOY_PLAYBOOK.md](docs/VM_DEPLOY_PLAYBOOK.md).** 표준 재배포
> 명령어 + VM-AP-N 회귀 카탈로그 + 진단 명령어가 모두 playbook 에 있다.
>
> **🔴 Claude 행동 규칙 (필수)**: VM 재배포 명령을 사용자에게 줄 때 **반드시 본
> playbook §1 의 모든 가드 (VM-AP-1~6) 를 포함한 명령어를 그대로** 제공한다.
> "간단히 pkill + nohup 4단계" 식 단축 금지 — 이번 세션에서 2회 재발한 VM-AP-1
> (graceful shutdown 부족), VM-AP-3 (잔재 충돌), VM-AP-4 (옛 버전 가동) 의 원인.
> 새 회귀 발견 시 playbook §2 에 VM-AP-N 으로 등록 후 §1 에 가드 추가.
>
> **🔴🔴 절대 규칙 — "명령어 없는 지시 금지" (사용자 강력 요청, 2026-06-17, 2회 catch).**
> VM 에서 *무엇이든 실행해야 하면* — `git pull` / 재배포 / 봇 재시작 / `patch_report`
> 패치 / `pip install` / backfill 등 — **반드시 그 자리에서 복사·붙여넣기로 바로
> 실행되는 완전한 명령어를 함께 준다.** "VM 을 먼저 v7.x.x 로 재배포한 뒤" / "git pull
> 하세요" / "재배포 필요" 같이 *행동만 지시하고 명령은 안 주는 문장 절대 금지*. 새
> 코드(신규 flag·옵션)를 패치 명령에 쓰라고 안내할 땐, **그 코드를 VM 에 올리는
> `git pull`(=재배포 §1 블록)을 같은 답변에 먼저 넣고**, 이어서 패치 명령을 준다
> (순서대로 번호 매겨). 안 그러면 사용자가 옛 버전 VM 에서 `unrecognized arguments`
> 로 막힌다 (실제 재발). 전제조건(특정 버전 필요 등)을 말로만 적고 그 전제를 충족하는
> 명령을 빼면 본 규칙 위반.

**필수 안내 사항 (playbook §1 외 운영 컨텍스트):**
- 처음 clone 후 1회: `git config core.hooksPath .githooks` (commit-msg hook 활성화 — Execution Rule #12). 미설정 시 hook 작동 안 함.
- venv 가 없으면 `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` 후 진행
- `.env` 변경 시 (env flag 추가 등) 재시작 *반드시* 필요. config 는 startup 시점 1회만 로드 → **`sudo systemctl restart agents-reviewer.service`** (상단 '봇 재시작·운영 SSOT' 참조)
- **봇은 systemd 서비스 `agents-reviewer.service` 로 관리된다 (확정).** 재시작·재배포 반영은 `sudo systemctl restart agents-reviewer.service` 한 줄. `nohup` 수동 기동 금지(중복→Conflict/OOM). 정본 규칙은 상단 '🔴 봇 재시작·운영 SSOT' 블록.
- (legacy) `nohup ... & disown` 방식은 systemd 서비스가 *없을 때만*. 현 VM 은 서비스 등록돼 있으므로 쓰지 말 것 — playbook §1 의 nohup 블록도 systemd restart 로 대체.

**보안:**
- 봇 토큰·API 키가 노출된 로그를 사용자가 붙여넣으면 즉시 토큰 회전 안내 (`@BotFather /revoke` → `.env` 갱신 → 재시작)
- `.env` 는 절대 git 에 커밋 금지. `.env.example` 만 커밋

**진단 명령어**: playbook §3 참조 (봇 상태 / 보고서 생성 진행 여부 / composer 회귀 추적).

**새 실행 스크립트 만들 때 (VM-AP-2 가드)**: 컨테이너 환경의 `core.fileMode false`
때문에 새 인터프리터 스크립트(`*.sh`/`*.py` 실행파일/no-ext shebang) 가 git 에 100644
로 들어가 VM 에서 실행 불가. 권장: **새 스크립트를 안 만들고** 명령어 sequence 를
playbook §3 에 텍스트로 박는다. 부득이하면 `git add <file>` 직후 `git update-index
--chmod=+x <file>` + commit 전 `git ls-files --stage <file>` 가 100755 확인.

## Codex 검수자 페르소나 갱신 SOP (사용자가 codex 페르소나 지침을 주면 *즉시* 이 절차로)

> **트리거 인식.** 사용자가 "codex 검수자가 X도 봐야 한다 / 이런 표현(을) 쓰지 마라 /
> 심각도 기준 바꿔 / 도메인 추가 / 이 케이스를 잡아라" 식으로 **codex *검수* 페르소나** 에
> 대한 지침을 주면 — 되묻지 말고 — 아래로 두 파일에 *정합* 반영한다. ⚠️ 이건 *작성*
> 페르소나가 아니라 *검수* 페르소나다 (codex 는 본문을 쓰지 않음, AP-V6-11). "이렇게
> 써라" 류 작성 지시면 composer SYSTEM_PROMPT/STYLE_GUIDE 쪽이지 여기가 아니다.
>
> **두 파일 (SSOT 분리, 항상 정합):**
> - [prompts/market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md) — *전체
>   기준서*(bible). 상세 정의·예시·배경. 길어도 됨. drift 시 **이게 정본**.
> - [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md) — *런타임 단축본*.
>   실제 codex 프롬프트로 주입됨 (`V6_CODEX_PERSONA_PATH` 기본값). 핵심만, 토큰 경제.
>
> **반영 규칙:**
> 1. 새 검수 항목/도메인 → 전체 기준서 §"반드시 검수해야 할 항목"(상세) + 단축본
>    §"검수 포커스"(1~2줄 압축) *둘 다*.
> 2. 심각도·금지 행동·태도 변경 → 두 파일 모두. 심각도는 항상 JSON `severity`(high/
>    medium/low) 매핑 유지 (치명적→high / 중대→medium / 경미·개선→low).
> 3. **출력 형식은 절대 바꾸지 않는다.** codex 출력은 `FactVerdict` JSON 고정(파서·루프
>    계약). 페르소나의 산문형 데스크 보고서 형식을 *런타임 단축본에 넣지 말 것* (파서
>    깨짐, AP-V6-13 인접). 단축본에 "출력은 시스템 지정 JSON 따름" 문구 유지.
> 4. AP-V6-8(모든 지적 근거 인용 필수)·AP-V6-11(본문 작성 금지)은 *항상* 보존. 작성
>    페르소나로 변질 금지.
>
> **적용·운영:**
> - **코드 변경 불요, 봇 재시작 불요.** 파일은 런타임에 읽힌다 (`CodexCritic` 가 보고서
>   마다 재생성되며 persona 재로딩) — 커밋·푸시 후 VM `git pull` 이면 *다음 보고서부터* 적용.
> - 새 검수 항목이 *재발 회귀* 케이스면 `tests/regression/fixtures/fact_discipline_scenarios.yaml`
>   fixture 도 함께 (단 error_class 동결 확장은 사용자 게이트 — AP-V6-9).
> - 회귀 발견 패턴이면 [REFACTOR_V6_PLAN.md §5](REFACTOR_V6_PLAN.md) AP-V6-N append.

## 차트·지도 제작 기준 (v4.5.7)
SSOT 는 [docs/MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md). 핵심:
- **차트**: composer 가 `ComposedSection.charts` 에 직접 emit. type **27종** (v7.9.17 부터 — network 폐기 CHART-AP-36). v7.1.0 — 초기 7종 (bar/donut/stacked/bubble/heatmap/waterfall) 비주얼 격상: 해치=명목 카테고리 전용, 위계=잉크 농도 사다리, 세리프 직접 라벨 (어휘 SSOT: [MONO_THEME_GUIDE §10](docs/MONO_THEME_GUIDE.md)). 기존 12종 (bar/donut/line/gantt/stacked/bubble/heatmap/dual_line/forecast/choropleth/candle/area) + FT/Economist 스타일 7종 (scatter/stacked_area/lollipop/slope/small_multiples/waterfall/range_bar, v5.3.0) + sankey (v5.3.0) + **v7.0.0 신규 3종 (bump 순위경쟁 / bullet 목표대비 / connected_scatter 2변수 궤적)** + **v7.5.0 신규 4종 (combo 이중축 막대+선 / diverging_bar 대립쌍 발산 / pyramid 인구 피라미드 / dot_matrix 100칸 와플 — 이중 축 결합 + 사회 이슈 어휘)**. 카테고리 구분은 hue 가 아닌 45° 패턴 (hatch-tight/hatch-wide/dots/accent-hatch + accent solid). v5.3.0 7종 + v7.0.0 3종 + v7.5.0 4종은 `guarded` tier — chart_critic + Visual Sanity Gate C 통과 필수. v7.0.0 부터 annotation 레이어(vline/hline/band/point, 차트당 ≤3 — AP-V7-6)가 cartesian 전 type 개방 (combo 포함). 전 타입 갤러리 베이스라인: [samples/chart_gallery_v7.html](samples/chart_gallery_v7.html).
- **지도**: composer 가 `ComposedReport.embedded_map` 에 emit. d3 + d3-geo + world-atlas/110m TopoJSON. maplibre-gl / 외부 타일 서비스 사용 금지 (mono guide Anti-pattern §6.6). v7.5.0 부터 `projection: "globe"` (정사영 지구본 — 대권 호, 탄도·위성·극지 토픽) + `rings` (사거리권·작전반경 동심원) additive 지원.
- **폰트**: Noto Serif KR (숫자/타이틀), Noto Sans KR (라벨/본문/지도 라벨)
- **색**: 큰 숫자에 액센트 색 금지 → `--text` 만 (mono guide §3.3)
- **사선**: 45° 한 방향만. cross-hatch / 반대 방향 / 회전 패턴 안에 dash 모두 금지 (mono guide §6.1~6.3).
- **참조 구현**: [samples/chart_map_mono_compare.html](samples/chart_map_mono_compare.html) (라이브: doroper98.github.io/agents_reviewer/samples/chart_map_mono_compare.html)

## Execution Rules
1. 모든 코드 변경 후 `python -m py_compile` 검증
2. Type hints 필수
3. Pydantic 모델 사용 (dict 금지)
4. Agent system prompt 는 한국어 + 영어 혼용 가능
5. 커밋 메시지: `v{VER}: {변경 요약}`
6. CLI 모드: `--dangerously-skip-permissions --allowedTools "WebFetch,WebSearch"`
7. 시스템 프롬프트에 `.format()` 사용 금지 → `.replace()` 사용 (JSON `{}` 충돌 방지)
8. AnalysisStrategy 는 dict 가 아닌 Pydantic 모델로만 다룬다. dict 회귀 금지 ([REFACTOR_V3_PLAN.md §8](REFACTOR_V3_PLAN.md) Anti-pattern #3). per-agent directive 는 transitional `legacy_directives` 필드를 통해서만 접근.
9. claim 에 evidence 1 개 이상 강제 (`Claim.must_have_evidence` Pydantic validator). 빌더가 빈 evidence 로 Claim 생성 시도 금지 — Anti-pattern #4. 데이터가 없으면 finding 자체를 생성하지 말 것.
10. Synthesis Judge 는 모순을 봉합하지 않고 드러낸다. 모순은 `JudgmentVerdict.contradictions` 필드에 명시 — Anti-pattern #5. 어느 쪽 채택했는지 `resolution` 에 적되, 패배한 입장은 `counter_hypothesis` 로 보존.
11. 신규 문서는 [DOCS_GOVERNANCE_V3.md](DOCS_GOVERNANCE_V3.md) 의 YAML 헤더 규약 + SSOT 매트릭스를 따름. 사실은 한 곳에만 적고 다른 곳은 링크.
12. **커밋 메시지의 `vX.Y.Z:` prefix 는 `src/orchestrator.py:VERSION` 상수와 반드시 일치**. 메시지에만 새 버전 박고 상수 안 올리면 배포된 봇이 옛 버전을 계속 표기하는 회귀 (v5.2.5 까지 3회 반복) — `.githooks/commit-msg` 가 mismatch 시 커밋을 reject 한다. 활성화는 clone 직후 1회: `git config core.hooksPath .githooks`. `--no-verify` 우회 금지. 정말 우회해야 하면 `SKIP_VERSION_CHECK=1 git commit ...` (rebase / cherry-pick 같은 ops 한정).

## Change Propagation Matrix
**코드를 변경했다면 같은 커밋에서 아래의 문서도 함께 갱신한다.** SSOT 매트릭스는 [DOCS_GOVERNANCE_V3.md §3](DOCS_GOVERNANCE_V3.md).

| 코드 변경 | 동시 갱신해야 할 문서 |
|-----------|----------------------|
| `src/orchestrator.py:VERSION` 증가 | [README.md](README.md) `Status`, [CHANGELOG.md](CHANGELOG.md) (신규 항목 추가), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `src/models.py` 모델 추가/변경 | [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (도식 + 의미 가이드) |
| `src/handoff/bundle_builder.py` 또는 `src/models.py:ReportBundle` 모델군 (v5.5.0) 변경 | [docs/CONTRACTS/report_bundle_v1.md](docs/CONTRACTS/report_bundle_v1.md) (계약 SSOT — §7: additive=무증분 / breaking=schema_version 증분+양측 동시), `src/visual/schemas.py` (차트 data shape pin, 재정의 금지 §9), [docs/DATA_MODELS.md §5.5](docs/DATA_MODELS.md), `docs/CONTRACTS/report_bundle_v1.example.json` (예시 parity), `tests/test_report_bundle.py`. `ORIGIN_TO_VERIFICATION` / verification enum 변경 시 계약 §1/§2 + 회귀 테스트 동시 갱신 |
| `src/agents/*` 신규 추가/삭제 | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/REPO_MAP.md](docs/REPO_MAP.md) |
| `src/lenses/*` 신규 추가 (V3 Step 5 후) | [docs/CATALOGS.md §2](docs/CATALOGS.md) |
| `src/archetypes/*` 신규 추가 (V3 Step 2 활성) | [docs/CATALOGS.md §3](docs/CATALOGS.md), [docs/ARCHITECTURE.md §5.1](docs/ARCHITECTURE.md) |
| `src/templates/blocks/*` 신규 추가 (V3 Step 3 활성) | [docs/CATALOGS.md §4](docs/CATALOGS.md), `src/models.py:BlockType` Literal 확장, `_BLOCK_BUILDERS` 등록 |
| `src/models.py:BlockType` 변경 | [docs/CATALOGS.md §4](docs/CATALOGS.md), [docs/DATA_MODELS.md §3.7](docs/DATA_MODELS.md), 신규 타입은 `src/templates/blocks/<type>.html` + 빌더 추가 |
| `src/templates/archetypes/*` 신규 추가 | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| `src/token_budget.py` 정책 변경 | [docs/ARCHITECTURE.md §3.1](docs/ARCHITECTURE.md), [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/lens_policy.py` 매핑 변경 | [docs/CATALOGS.md §2.1](docs/CATALOGS.md) |
| `src/templates/static/charts.js` 차트 추가/변경 (v3.2.0) | [CLAUDE.md `Chart System`](CLAUDE.md), `samples/chart_gallery.html`, `src/visual_builder.py:build_chart_payload`, `src/tests/test_chart_builders.py` |
| `src/tools/market_fetcher.py` 변경 (v5.2.0) | `src/config.py` (API key 필드), `src/models.py:ContextAnalysis` (`instruments_mentioned` / `time_series`), `src/agents/context_analyst.py:SYSTEM_PROMPT` (지원 종목 목록), `src/orchestrator.py` (fetch hook + `_select_market_period`), `tests/test_market_fetcher.py`, `.env.example`, [CLAUDE.md `Market Data Fetcher`](CLAUDE.md). 신규 instrument 추가 시 `INSTRUMENT_REGISTRY` + alias + 회귀 테스트 동시 갱신. |
| `src/models.py:ComposedSection._drop_invalid_charts` 변경 (v5.2.0) | `src/visual/schemas.py:_TYPE_TO_GUARD` (타입별 가드 SSOT), `tests/regression/test_composed_section_guard.py` (production wiring 회귀), `docs/CHART_RENDERING_ANTIPATTERNS.md` (AP-N 추가 시 함께). 본 validator 가 chart_gate 의 production 진입점 — 디폴트 ON. 위반 차트 silent drop. |
| `src/agents/narrative_composer.py` 변경 (v3.3.0) | [docs/CATALOGS.md §1](docs/CATALOGS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [src/visual_builder.py:build_chart_catalog](src/visual_builder.py), [src/tests/test_narrative_composer.py](src/tests/test_narrative_composer.py) |
| `src/agents/narrative_composer.py:SYSTEM_PROMPT` 또는 `src/agents/context_analyst.py:SYSTEM_PROMPT` 의 어조·어휘 가이드 변경 (v5.2.9 신설) | [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) (본문 문체 SSOT — 한 곳에만 적기, anti-pattern #1), [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md) (회귀 시 새 WRITE-AP-N append). 두 SYSTEM_PROMPT 와 STYLE_GUIDE 의 어휘 표·ban 리스트·빈도 가이드는 *항상 정합* 해야 — drift 발견 시 STYLE_GUIDE 가 정본 |
| codex *검수자* 페르소나 지침 변경 (사용자 지시, V6) | [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md) (런타임 단축본) + [prompts/market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md) (전체 기준서) *동시* 갱신, 항상 정합. 출력 형식(`FactVerdict` JSON)·AP-V6-8/11 불변. 절차 SSOT: CLAUDE.md `Codex 검수자 페르소나 갱신 SOP` |
| `src/templates/archetypes/freeform_essay.html` 변경 (v3.3.0) | [docs/REPO_MAP.md](docs/REPO_MAP.md), [docs/CATALOGS.md §3](docs/CATALOGS.md) |
| `src/templates/static/charts.css` 차트 디자인 토큰 변경 | [CLAUDE.md `Chart System`](CLAUDE.md) |
| `src/visual_builder.py:build_chart_payload` 차트 매핑 변경 | [CHANGELOG.md `차트 매트릭스`](CHANGELOG.md) |
| [GOAL.md](GOAL.md) `REQ-*` 추가/완료 | [DEVLOG.md](DEVLOG.md) 에 변경 기록 |
| 의존성 추가 (`requirements.txt`) | [DEVLOG.md](DEVLOG.md), [README.md](README.md) Quick Start |
| 워크플로우 변경 | [WORKFLOWS.md](WORKFLOWS.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 인프라 변경 (Cloudflare/VM) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [DEVLOG.md](DEVLOG.md) |
| VM 재배포 회귀 발견 (graceful shutdown / 권한 / 잔재 / 옛 버전 가동 등) | [docs/VM_DEPLOY_PLAYBOOK.md](docs/VM_DEPLOY_PLAYBOOK.md) §2 (VM-AP-N append) + §1 (가드 추가). CLAUDE.md `VM 배포 SOP` 의 playbook 참조 라인은 그대로 유지. CHANGELOG 의 ops 항목에 reference |
| `docs/CHART_RENDERING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (차트 렌더링)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) 의 해당 버전 entry |
| `docs/REPORT_WRITING_ANTIPATTERNS.md` 새 항목 추가 | [CLAUDE.md `Anti-Patterns (보고서 본문 작성)`](CLAUDE.md), [CHANGELOG.md](CHANGELOG.md) |
| V5 Phase 진입/완료 ([REFACTOR_V5_PLAN.md](REFACTOR_V5_PLAN.md)) | [CHANGELOG.md](CHANGELOG.md), 신규 SSOT 문서 (Phase 0B 의 `tests/regression/README.md`, Phase 1A 의 `docs/RESEARCH_DIRECTOR_METHODS.md`, Phase 2B 의 `docs/VISUAL_CAPABILITY_REGISTRY.yaml`, Phase 7 의 `docs/DESK_VISUAL_RUBRIC.md`, Phase 8 의 `docs/STRATEGIC_MODE_PROMPT.md`), 영향받은 모든 문서 헤더의 `last_synced_with` |
| `tests/regression/fixtures/golden_prompts.yaml` 변경 | [tests/regression/README.md](tests/regression/README.md) §2 갱신, `helpers.py` 의 검증 함수가 새 expected 키 처리하는지 점검 (Phase 0B SSOT) |
| `src/state/*.py` 6-tier State 모델 변경 (Phase 0C) | [docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md) (V5 6-tier 도식), [docs/DATA_MODELS.md](docs/DATA_MODELS.md) (V5 State 섹션), [tests/regression/test_state_compaction.py](tests/regression/test_state_compaction.py) (guards + 30% 절감 검증), [REFACTOR_V5_PLAN.md §4](REFACTOR_V5_PLAN.md) (Phase 0C SSOT) — 단계 라벨·method enum·필드 추가 시 모두 갱신 |
| `src/agents/research_director.py` 변경 (Phase 1A) | [docs/RESEARCH_DIRECTOR_METHODS.md](docs/RESEARCH_DIRECTOR_METHODS.md) (9종 method SSOT — 사람-친화 정의), [src/state/models.py:AnalysisMethod.method](src/state/models.py) (Literal 9종 enum — 코드 SSOT), [tests/regression/test_research_director.py](tests/regression/test_research_director.py) (≥80% 일치 검증), [tests/regression/test_method_compliance.py](tests/regression/test_method_compliance.py) (downstream contract — required_exhibits 매핑 + StrategicReport 8 필드 + heuristic 의 method 준수), [tests/regression/fixtures/golden_prompts.yaml](tests/regression/fixtures/golden_prompts.yaml) (각 prompt 의 expected_method), [REFACTOR_V5_PLAN.md §6](REFACTOR_V5_PLAN.md) (Phase 1A SSOT). `_DEFAULT_REQUIRED_EXHIBITS` 9종 매핑 변경 시 `test_method_compliance.py` 의 method-specific 검증 9종 함께 갱신 |
| 운영 의존성 (Plan §22 runtime) 추가 | [requirements-v5.txt](requirements-v5.txt) (Phase 2/2B/6/7 운영 패키지 SSOT), [docs/V5_ACTIVATION.md §1.5](docs/V5_ACTIVATION.md) (graceful degrade 매트릭스), [docs/V5_TEST_RESULTS.md](docs/V5_TEST_RESULTS.md) (effect 측정) — 새 phase 가 runtime 의존성 추가 시 3곳 모두 갱신 |
| V5 phase 활성화 / 회귀 측정 | [docs/V5_TEST_RESULTS.md §3](docs/V5_TEST_RESULTS.md) (append-only entry 추가), [docs/V5_ACTIVATION.md §3](docs/V5_ACTIVATION.md) (단계별 절차) — 새 측정 결과는 *추가만*, 기존 entry 수정 금지. AP-V5-32 강제 |
| `src/visual/evidence_dataset.py` 변경 (Phase 2A) | [src/state/models.py:EvidenceDataset / DatasetField / TransformStep](src/state/models.py) (모델 SSOT), [tests/regression/test_evidence_dataset.py](tests/regression/test_evidence_dataset.py) (AP-V5-24/25/26 검증), [REFACTOR_V5_PLAN.md §8](REFACTOR_V5_PLAN.md) (Phase 2A SSOT) — semantic_type 7종 enum / 3종 금지 행위 변경 시 모두 갱신 |
| `src/visual/v5_theme.py` 변경 (Phase 2) | [REFACTOR_V5_PLAN.md §19](REFACTOR_V5_PLAN.md) (design token 정본), `samples/chart_map_mono_compare.html` (사람-친화 SSOT), `src/templates/themes/{editorial,burgundy}.css` (브라우저 SSOT), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py) (drift 검증) — 4곳이 byte-equal 일치해야 |
| `src/visual/vega_adapter.py` 변경 (Phase 2) | [src/agents/visual_planner.py](src/agents/visual_planner.py) (Vega-Lite spec emit), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py) (어댑터 검증), [REFACTOR_V5_PLAN.md §7](REFACTOR_V5_PLAN.md) (Phase 2 SSOT) — render_vega_lite / validate_vega_spec / chart_dict_to_vega_spec 시그니처 변경 시 |
| `src/agents/visual_planner.py` 변경 (Phase 2) | [src/visual/vega_adapter.py](src/visual/vega_adapter.py) (출력 spec 검증), [src/state/models.py:EvidenceDataset](src/state/models.py) (입력 dataset), [tests/regression/test_phase2_vega.py](tests/regression/test_phase2_vega.py), [REFACTOR_V5_PLAN.md §7.3](REFACTOR_V5_PLAN.md) (Phase 2 agent SSOT) |
| `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 변경 (Phase 2B) | [src/visual/capability_registry.py](src/visual/capability_registry.py) (캐시는 자동 갱신, 단 분포 가드 함수 검증 필요), [tests/regression/test_capability_registry.py](tests/regression/test_capability_registry.py) (분포 + safe/guarded/experimental 매칭), [REFACTOR_V5_PLAN.md §9](REFACTOR_V5_PLAN.md) (Phase 2B SSOT) — 새 chart type 추가는 *반드시* yaml + 회귀 테스트 분포 가드 함께 갱신 (PR 체크리스트, AP-V5-27 강제) |
| `src/visual/schemas.py` (Phase 6 Gate A) 변경 | [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py) (해당 type guard 검증 추가), [docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) (새 antipattern 매핑 시), [REFACTOR_V5_PLAN.md §13.2](REFACTOR_V5_PLAN.md) — 새 chart type 의 Pydantic guard 추가 시 _TYPE_TO_GUARD 매핑 + validate_chart_data 분기도 함께 |
| `src/visual/sanity_check.py` (Phase 6 Gate C) / `src/visual/chart_gate.py` (Gate D) 변경 | [src/agents/chart_critic.py](src/agents/chart_critic.py) (Gate B 정책 정합), [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py), [REFACTOR_V5_PLAN.md §13](REFACTOR_V5_PLAN.md) (Phase 6 SSOT) — threshold (`SanityCheckThresholds`) 변경 시 Plan §13.4 의 임계와 정합 검증 |
| `src/agents/chart_critic.py` (Phase 6 Gate B) 변경 | [REFACTOR_V5_PLAN.md §13.3 / §13.8](REFACTOR_V5_PLAN.md) (7개 질문 + 운영 정책 SSOT), [tests/regression/test_chart_correctness.py](tests/regression/test_chart_correctness.py) (KEEP_SCORE_THRESHOLD 검증), CHANGELOG (운영 정책 변경 기록) |
| `src/state/models.py:Exhibit / RequiredExhibit / ExhibitPriority` (Phase 6A) 변경 | [src/visual/chart_gate.py](src/visual/chart_gate.py) (priority 분기 정합), [src/agents/research_director.py](src/agents/research_director.py) (`_DEFAULT_REQUIRED_EXHIBITS` 9종 매핑), [tests/regression/test_exhibit_priority.py](tests/regression/test_exhibit_priority.py) (AP-V5-28 검증), [REFACTOR_V5_PLAN.md §14](REFACTOR_V5_PLAN.md) (Phase 6A SSOT) — fallback_form enum 또는 priority enum 변경 시 |
| `src/visual/deterministic_gate.py` (Phase 7A) 변경 | [tests/regression/test_deterministic_gate.py](tests/regression/test_deterministic_gate.py) (HARD_FAIL_RULES + SOFT_FAIL_RULES + MODE_LOWER_BOUND + ChartCountLimits SSOT 검증), [REFACTOR_V5_PLAN.md §15](REFACTOR_V5_PLAN.md) (Phase 7A SSOT) — Hard fail 추가 시 plan 의 §15.4 + 회귀 테스트 *동시* 갱신. AP-V5-29 강제 (LLM Desk 우회 금지) |
| `src/agents/desk_editor.py` (Phase 7) 변경 | [docs/DESK_VISUAL_RUBRIC.md](docs/DESK_VISUAL_RUBRIC.md) (Visual 8-rubric SSOT — append-only), [src/visual/capture.py](src/visual/capture.py) (Playwright capture), [tests/regression/test_desk_editor.py](tests/regression/test_desk_editor.py) (KILL_RULES + HOLD_DISPATCH + SYSTEM_PROMPT 정합), [REFACTOR_V5_PLAN.md §16](REFACTOR_V5_PLAN.md) (Phase 7 SSOT) — KILL_RULES 추가는 plan §16.6 + 회귀 테스트 *동시* 갱신. AP-V5-11/12/13/14/15/16 강제 |
| `docs/DESK_VISUAL_RUBRIC.md` 새 (시각-N) 항목 append (AP-V5-16) | YK 가 발견한 결함만 추가 (append-only, 수정 X). 다음 DeskEditor 호출부터 SYSTEM_PROMPT 에 자동 포함. CHANGELOG 의 해당 버전 entry 에 명시 |
| `src/agents/strategic_router.py` (Phase 8) 변경 | [docs/STRATEGIC_MODE_PROMPT.md](docs/STRATEGIC_MODE_PROMPT.md) (3-경로 감지 SSOT), [src/state/models.py:StrategicReport](src/state/models.py) (8 필수 출력), [tests/regression/test_strategic_mode.py](tests/regression/test_strategic_mode.py) (정확도 ≥90% + KILL_RULES + AP-V5-18 갱신), [REFACTOR_V5_PLAN.md §17 + §18](REFACTOR_V5_PLAN.md) — STRATEGIC_PATTERNS 추가는 plan + 회귀 테스트 *동시* 갱신 |
| `src/agents/editor.py` (Phase 1) 변경 | [tests/regression/test_editor.py](tests/regression/test_editor.py) (7-rubric SSOT + 보존 검증), [REFACTOR_V5_PLAN.md §5](REFACTOR_V5_PLAN.md) (Phase 1 SSOT) — SYSTEM_PROMPT 의 7-rubric 변경 시 SECTION_SCORE_RUBRICS list + 회귀 테스트 *동시* 갱신. AP-V5-1 (Editor 우회 금지) 강제 |
| `src/agents/layout_typesetter.py` 또는 `LayoutPrimitive` Literal (Phase 3) 변경 | [src/state/models.py:LayoutPrimitive](src/state/models.py) (Literal SSOT), [tests/regression/test_layout_typesetter.py](tests/regression/test_layout_typesetter.py) (9-vocab AP-V5-3 가드), [REFACTOR_V5_PLAN.md §10](REFACTOR_V5_PLAN.md) (Phase 3 SSOT) — *9종 동결*. 추가/변경 금지 (AP-V5-3). 추가는 RFC + Plan 갱신 + 본 회귀 테스트 *동시* 갱신만 가능 |
| `src/visual/exhibit_numbering.py` (Phase 4) 변경 | [tests/regression/test_exhibit_and_budget.py](tests/regression/test_exhibit_and_budget.py) (정규식 SSOT + AP-V5-6), [REFACTOR_V5_PLAN.md §11](REFACTOR_V5_PLAN.md) — `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` 정규식 변경 시 EXHIBIT_REF_PATTERN / EXHIBIT_REF_RANGE_PATTERN 동시 갱신. AP-V5-6 강제 (composer 임의 번호 부여 금지) |
| `src/visual/word_budget.py` (Phase 5) 변경 | [tests/regression/test_exhibit_and_budget.py](tests/regression/test_exhibit_and_budget.py) (5종 시그널 + gini + budget bands), [REFACTOR_V5_PLAN.md §12](REFACTOR_V5_PLAN.md) — MODE_TARGET_CHARS_LOWER 는 [tests/regression/helpers.py](tests/regression/helpers.py) 와 byte-equal 유지. COMPOSER_MAX_TOKENS_V5 변경 시 Plan §12.6 + 회귀 테스트 동시 갱신 |

## Anti-Patterns (문서)
[DOCS_GOVERNANCE_V3.md §9](DOCS_GOVERNANCE_V3.md) Anti-patterns 1~10 절대 위반 금지. 핵심:
- 사실을 두 곳에 적기 금지 → 한쪽은 링크
- `last_synced_with` 갱신 안 한 채 본문만 수정 금지
- DEVLOG 과거 항목 수정 금지 (append-only). 정정은 새 항목으로
- GOAL 의 REQ-* 삭제 금지. deprecated 마킹만

## Anti-Patterns (차트 렌더링 — v4.4.3 신설, v5.1.2 확장)
**charts.js / maps.js / composer 의 차트 prompt 변경 시 반드시 점검.** SSOT:
[docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md). **43개 패턴 누적** (v5.8.8 — CHART-AP-27 폭포수 부호 / 28 빈 차트 프레임 / 29 NaN 노출, 모두 결정적 가드로 차단. v7.0.1~2 — CHART-AP-30 곡선 보간 왜곡 / 31 시계열 데이터 듬성 emit / v7.5.1 — 32 sankey 라벨 수치 중복 표기 / v7.9.8 — 33 scatter 라벨 충돌 / 34 dot_matrix 좌측 쏠림 / v7.9.14 — 35 composer diverging_bar 지수 등락률 0 누락 / v7.9.17 — 36 network 관계도 포맷 폐기 / v8.0.0 — 37 stakeholder_map force/physics 레이아웃 금지[선제, network 교훈 상속] / v8.2.10 — 38 등록된 dict-데이터 차트 type 의 validate_chart_data 분기 누락→100% silent drop[사용자 catch — 르포 관계도가 v8.0.0 이래 미표시였던 근본 원인] / v8.2.13 — 39 대륙 간 스케일 지도를 평면 메르카토르로 렌더→빈 바다·구석 왜곡[사용자 catch — 경도 span>=100° 평면 지도를 globe 로 결정적 자동 격상] / v8.2.16 — 40 stakeholder_map 엣지 라벨이 가운데 칼럼 카드·다른 라벨 위에 찍혀 가림→카드+라벨 장애물 de-confliction(수직 우선 밀어내기+연결선)+선 스타일 범례[사용자 catch] / v8.2.17 — 41 stakeholder_map 교차 칼럼 엣지 세로 구간이 한 통로에 포개짐→칼럼 사이 gap 에 엣지별 세로 레인(bendX) 균등 분배 라우터+GAP/VSP 확대[사용자 catch] / v8.2.18 — 42 stakeholder_map 노드 자산 어휘 부족(미지원 국기 KR 등 silent 이니셜 강등+로고·인물 실사진 슬롯 부재)→ISO 전 국가 국기(flagcdn+인라인 KR 포함 7종 fallback)+logo(공식 도메인→원형 로고)+photo(흑백 원형 인물 사진), 원격 자산은 프리로드 성공 시에만 오버레이[사용자 catch] / 43 stakeholder_map 엣지가 카드 뒤 관통(교차 엣지 수평 구간·같은 칼럼 skip 수직 구간)+라벨이 타 엣지 선·교차점 위 안착→장애물 인지형 직교 라우터(가운데 칼럼 행 사이 수평 코리더+바깥 세로 레인 우회, 평행 겹침 0)+라벨 장애물에 엣지 세그먼트 포함[사용자 catch], 전부 사용자 catch. CHART-AP-29 는 v7.9.17 에서 소스(market_fetcher)·합류(orchestrator) 2단 NaN 봉 차단 추가):
- CHART-AP-1~10: 기존 (drawNetwork / drawStacked / drawBar / 지도 / annotation 등)
- CHART-AP-11: 차트 카드 배경 하드코딩 fallback (v4.5.3 — `--card-deep` 미정의)
- CHART-AP-12: 버블 차트 스케일 고정 (v4.5.3 — `domain([0,1])` 고정)
- CHART-AP-13: Gantt 차트 시간축 누락 + 행 라벨/note 충돌 (v4.5.4 신설)
- CHART-AP-14: 보고서와 무관한 지리 annotation 무조건 렌더 (v4.5.7 신설 — Somaliland viewport gating)
- CHART-AP-15: gantt zero-duration emit (v5.1.2 신설 — point-in-time 이벤트 모음을 gantt 로, `GanttGuard.validate_durations` 추가)
- CHART-AP-16: donut 2-segment 안티패턴 (v5.1.2 신설 — 정보 손실 + subtitle 잉여 + 렌더러 silent return 빈 카드 회귀, `DonutGuard.validate_segment_count` 추가)
- CHART-AP-17: 차트 type starvation (v5.3.0 신설 — 캔들 회귀 교훈. 새 type 의 production wiring 만으로는 부족 — 5-Layer Usage Guarantee 필요)
- CHART-AP-18: entry 애니메이션 motion 회귀 (v5.3.0 신설 — duration / easing / prefers-reduced-motion / IntersectionObserver unobserve / ambient RAF pause 가드)
- CHART-AP-19: 재무·수익성 보고서에서 sankey/waterfall 분해 차트 누락 (v5.4.3 신설 — 결정 트리 collapse, 시계열 분기로 먼저 매치되어 분해 차트 branch 까지 못 도달. SYSTEM_PROMPT 에 step 0 추가)
- CHART-AP-20: sankey viewBox 과대 프로비저닝으로 "위로 쏠림" (v5.4.6 신설 — H = max(320,...) 클램프 + MAX_NODE_H_RATIO 0.50 의 결합으로 노드 적은 sankey 가 아래쪽 ~40% 휑함. content-fit viewBox 패스로 tight H 재계산 + dy 시프트)
- CHART-AP-21: sankey 좌·우 zones margin 부족으로 라벨 잘림 (v5.4.7 신설 — left=8/right=8 으로 첫 컬럼 "DS 매출" 라벨이 음수 좌표까지 뻗어 잘리고 마지막 컬럼 우측에 ~170px 휑함. left=80/right=120 으로 보정. ★ v6.0.1~6.0.4 에서 4회 재발 — 고정 margin 의 구조적 한계. **최종 해법 = ①렌더 후 getBBox content-fit ②노드 코어 기준 중앙정렬 ③긴 끝-라벨 2줄 wrap 의 3종 결합** (doc 의 "★ 최종 해법 SSOT" 박스). "중앙이 아니다" 회귀 시 margin 숫자 만지지 말고 이 3종이 다 켜졌는지 확인)
- CHART-AP-22: sankey 중간 컬럼 라벨 stacking 충돌 (v5.4.7 신설 — MIN_NODE_PAD=18 이 위 라벨 font11 + 값 라벨 font10 stacking 에 부족, 메모리/파운드리 사이 "65.0" ↔ "파운드리" 라벨 7px overlap. pad 36 으로 16px 여유 확보)
- CHART-AP-23: forecast 차트 y축 도메인이 actual 점을 제외 (v5.4.8 신설 — `?? fallback` 으로 forecast 가 있으면 actual 무시 → actual 의 값이 forecast 범위 밖이면 데이터 점이 차트 영역 밖에 박힘. actual + forecast 모든 값 산입으로 픽스)
- CHART-AP-24: forecast 차트 actual ↔ forecast 선 단절 (v5.4.8 신설 — actual 선과 forecast 선/cone 이 별도 path 로 그려져 boundary 에서 1년치 gap. actual 마지막 점을 forecast bridge 의 첫 점으로 prepend → cone 이 fork 시점에서 한 점, 미래로 fan 형태로 확장)
- CHART-AP-25: 행위자 관계도를 radial network (hairball) 로 렌더 (v5.5.5 신설 — 노드 위치 무의미 → 중심 관통 실타래, 시인성 최악. `drawNetwork` 렌더러를 **인접행렬** 로 교체. 데이터 계약 (nodes/links) · NetworkGuard · registry · usage_log 불변, type 명 `network` 유지. 셀이 관계 type 인코딩 (대립/동맹/영향/연관), getBBox content-fit viewBox 로 자동 중앙정렬. 모크업: `samples/actor_relationship_redesign_compare.html`)
- CHART-AP-31: composer 가 시계열 차트 데이터를 듬성하게 추려 emit (v7.0.2 신설, 사용자 catch — LLM 토큰 절약으로 일별 60거래일을 8~12 포인트로 축약. `orchestrator._densify_ts_charts` 가 차트의 날짜 창 안 실 데이터 행으로 결정적 교체, 확대 창·이벤트 마커 보존, 디폴트 ON)
- CHART-AP-30: 시장 시계열 풀 차트의 곡선 보간 (v7.0.1 신설, 사용자 catch — curveMonotoneX 가 실제 가격 경로를 평탄화. v5.2.9 가 sparkline 만 고치고 풀 카드에 잔재. line/area/dual_line/forecast/stacked_area/small_multiples/connected_scatter 전부 curveLinear 통일, 예외는 bump 순위 축뿐)
- CHART-AP-26: slope 차트 좌·우 라벨 충돌 (v5.5.8 신설 — 동일/근접 값 다수 시 라벨이 같은 y 에 겹쳐 판독 불가. 기준선 정규화(모두 100.0) 차트에서 특히 빈발. `drawSlope` 에 라벨 baseline dodge (minGap 13 + 범위 클램프) + 점→라벨 connector 추가. 점·선은 실제 값 위치 유지)

회귀 발견 시 본 문서에 새 항목 (CHART-AP-N) append. 같은 실수 반복 차단의 SSOT.

## Anti-Patterns (보고서 본문 작성 — v4.4.4 신설, v4.5.4 확장)
**composer SYSTEM_PROMPT / docs/REPORT_STYLE_GUIDE.md / 본문 출력 변경 시 반드시 점검.**
SSOT: [docs/REPORT_WRITING_ANTIPATTERNS.md](docs/REPORT_WRITING_ANTIPATTERNS.md). 26개 패턴 누적 (v5.8.8 — WRITE-AP-15 시장수치 자유서술[최우선] / 16 주장→사실 / 17 인과 과장 / 18 행사 혼동 / 19 일방서사 / 20 제목·본문 무게 / 21 신뢰도% 노출, 2026-06-03 일일 브리핑 회귀. v7.0.0 — WRITE-AP-22 기준시점 오선택. v7.6.4 — WRITE-AP-23 TTS 발음 표기 글 누수[사용자 catch]. v7.9.6 — WRITE-AP-24 고유명사 한글 음차 본문 누수[사용자 catch — 보고서와 영상 음성 내레이션 분리]. v8.2.4 — WRITE-AP-25 편집장 실패 1-섹션 폴백/절단본을 정상 완료로 무경고 발행[사용자 catch — deep 타임아웃→minimal fallback→degraded 플래그+텔레그램 경고+헤더 배너로 차단]. v8.2.9 — WRITE-AP-26 본문이 가리킨 시각물(아래 관계도/지도) 미표시[사용자 catch — 프롬프트 시각물-본문 일치 강제 + _reconcile_visual_references 안전망]):

> **★ 최우선 가치 — 일반 독자 우선 (v5.5.5).** 보고서는 *비전문가* 가 읽는다. ①
> 전문 용어·영어 표현·은어는 평이한 우리말로 바꾼다. ② 못 바꾸는 핵심 용어만 본문에
> 남기고 그 섹션 `ComposedSection.footnotes` 로 *문단 하단 주석* (`{term, explanation}`)
> 을 단다. 이 둘이 다른 모든 문체 규칙에 앞선다. SSOT: [docs/REPORT_STYLE_GUIDE.md §0.1](docs/REPORT_STYLE_GUIDE.md).
> 렌더는 `freeform_essay.html` 의 `.freeform-footnotes`, prompt 는 composer SYSTEM_PROMPT
> 의 "★ 최우선 원칙" 블록.

- WRITE-AP-1~7: 기존 (마크다운 raw / 용어 풀이 / 지도 후행 / 진부 연결어 / 추정 단정 / 모순 봉합 / 서수 모호)
- WRITE-AP-8: max_tokens 한도로 보고서 본문 중간 절단 (v4.5.4 신설 — 단일 8K 한도 회귀)
- WRITE-AP-9: 모순 섹션의 정적 메타-라벨 제목 (v5.5.1 신설 — "봉합하지 않은 충돌" 고정 제목이 결론 회피 인상 + 단조로움. composer 동적 `contradictions_heading` + resolution 단락 착지로 서술형 전환)
- WRITE-AP-10: 전문 용어·영어 표현을 평이화도 주석도 없이 본문에 방치 (v5.5.5 신설 — rate card / rate limit premium 회귀. `ComposedSection.footnotes` 문단 하단 주석 + 평이화 어휘표 신설)
- WRITE-AP-11: 발행일과 사건일이 다른데 본문에 시점 앵커 없음 (v5.6.4 신설 — 5/29 발행 보고서 본문이 "5월 26일 코스피..." 로 시작 + "같은 시각, 환율 7거래일 연속..." 로 지속 상태를 사건일에 고정 → 인지부조화 회귀. `_build_unified_payload` 에 `publication_date` 주입 + SYSTEM_PROMPT 의 `=== 시점 앵커링 ===` 섹션으로 첫 단락 시간 거리 명시 + '같은 시각' 금지 + 지속 상태는 발행일 현재 기준 프레이밍 강제)
- WRITE-AP-12: AI 가 인지되는 기호 (마크다운 강조 `**`/`*`/백틱, em·en dash `—`/`–`) 사용 (v5.6.7 신설, 사용자 최우선 규칙). SYSTEM_PROMPT 의 "★ 기호 금지" 블록 + `NarrativeComposer._sanitize_symbols` 결정적 후처리 (모든 사용자 노출 텍스트 정화, dash 자연 치환: 삽입구→쉼표·숫자범위→`~`·단어인접→공백, URL/좌표 보존) + orchestrator 최종 호출로 모든 경로 보장. `_strip_inline_md` (broadcast 폴백) 동일 규칙
- WRITE-AP-13: LLM 이 SYSTEM_PROMPT 의 JSON 예시 들여쓰기를 따라가다 응답 시작(`{`/headline/deck/sections 배열 시작) 을 통째로 누락하고 `      "prose":` / `      "side_a":` 같은 sections 객체 *중간 줄* 부터 출력 (v5.6.8 신설, Claude Opus 4.7 회귀). SYSTEM_PROMPT 의 ★★★ 강조 instruction (`{` 로 시작 강제) + `NarrativeComposer._recover_head_loss` 결정적 후처리 (body 가 `"key":` 시작이면 `{...}` wrap → 부분 객체에서 prose/heading 추출 → 1-섹션 ComposedReport 재조립, confidence 0.3)
- WRITE-AP-14: 미래 사건 카운트다운(D-N)을 발행일이 아닌 출처 작성일 기준으로 표기 (v5.8.3 신설 — 6/1 발행 보고서가 6/3 지방선거를 "사흘 앞"=5/31 기준으로 베껴 표기, 실제론 이틀 뒤/모레). WRITE-AP-11 의 거울상(과거 거리 누락 ↔ 미래 카운트다운 오기준). composer SYSTEM_PROMPT `=== 시점 앵커링 ===` 블록에 미래 카운트다운 규칙 추가 — D-N·'사흘 앞'·'내일'·'모레' 는 publication_date 와 사건일 실제 차이로 직접 셈, 출처 문구 베끼기 금지, 불확실하면 절대 날짜만)
- WRITE-AP-22: 최신 가용 데이터를 두고 옛 일자의 (정확한) 시장 수치를 무표기 채택 (v7.0.0 신설 — 6/5 발행 보고서가 6/4 종가 가용한데 6/1 종가를 인용, codex 는 '6/1 기준 정확' 으로 통과 → 정확하지만 시점이 틀린 문장으로 루프 수렴. WRITE-AP-11/14 가 시점 *표기* 회귀라면 이건 시점 *선택* 회귀. V7 Track C `V7_REF_FRAME` — `reference_frame` 계약을 composer/codex/reviser 3곳 주입 + 결정적 가드 2종(DateAnchoredMarket/StaleAnchor) + codex error_class `wrong_timeframe` 신설[사용자 게이트 2026-06-11] + 잔존 착지 drop. SSOT: [REFACTOR_V7_PLAN.md §3](REFACTOR_V7_PLAN.md))
- WRITE-AP-23: TTS 발음 표기가 눈으로 읽는 글(broadcast_summary/prose)로 누수 (v7.6.4 신설, 사용자 catch — 텔레그램 요약에 'WTI'가 '더블유티아이', 'D램'이 '디램', '7.86%'가 '7.86퍼센트'로 나옴. v7.4.0~v7.6.3 의 강한 '★ TTS 발화 규칙' 블록이 같은 LLM 호출 안에서 `broadcast_summary` 작성까지 번짐 — TTS 규칙이 `narration_tts` 전용임을 미명시. Fix 2중 — ① 프롬프트 경계(TTS 블록 적용범위 명시 + broadcast_summary 표기 레지스터, SSOT [tts_narration_guide.md §0](docs/tts_narration_guide.md)) ② `narrative_composer._revert_phonetic_in_text` 결정적 복원(broadcast_summary 명확 약어만, 모호어 제외) + prose/headline/deck warn-only. 숫자·%는 프롬프트 전담)

회귀 발견 시 본 문서에 새 항목 (WRITE-AP-N) append. 차트 anti-pattern 과 분리 유지.

## Key Directories (v4.5.7 — 호출되는 것만)
- `src/agents/` — 살아있는 에이전트: `context_analyst.py` (사실 수집) + `narrative_composer.py` (본문 작성) + `report_synthesizer.py` (HTML 렌더) + `research_director.py` (V5 Phase 1A, opt-in). v5.2.9 에서 dead persona 7개 모듈 삭제.
- `src/templates/archetypes/freeform_essay.html` — 유일하게 사용되는 보고서 템플릿
- `src/templates/report.css` — 5테마 풀 (editorial_cream / burgundy_mono / midnight_indigo / pine_forest / graphite_slate, v6.2.0) `[data-theme="..."]` 블록 정의 SSOT. legacy `light_mono` 블록도 보존 (v5.0.2 부터 풀 제외)
- `src/templates/static/` — d3.v7.min.js / charts.js / maps.js / charts.css / maps.css (보고서 dir 로 동기화)
- `src/orchestrator.py` — 4단계 (context → composer → render → watchlist) 진입점, `VERSION` SSOT
- `src/models.py` — Pydantic 데이터 모델 SSOT (`ComposedReport.charts` / `embedded_map` 포함)
- `src/token_budget.py` — mode 별 정책. v4.5.7 에선 모든 모드 동일하게 2 LLM 호출. mode 는 composer prompt 깊이 지시 + composer/context max_tokens 한도 (v4.5.4/v4.5.7) 결정
- `src/lens_policy.py` — `select_theme(event_type)` 가 `ALL_THEMES` 5종 풀(v6.2.0)에서 `random.choice` (v5.0.2). `select_lenses()` 는 호출 안 됨
- `src/telemetry.py` — LLM 호출 / 단계별 elapsed 기록
- `src/watchlist/` — SQLite Watchlist Registry (composed_report.watch_signals 에서 등록)
- `docs/` — 모든 정규 문서. `MONO_THEME_GUIDE.md` 가 차트/지도/테마 SSOT.
- `samples/` — 라이브 샘플 (GitHub Pages 자동 배포 — `chart_map_mono_compare.html`, `v4_2_0_architecture.html` 등)
- `reports/` — 생성된 HTML 보고서 (git ignored)

### Deprecated 모듈 (호출 안 됨, 파일 보존)
- `src/lenses/` (전체 11종) — registry 만 import, 호출 경로 없음
- `src/archetypes/` (freeform_essay 외 11종)
- `src/visual_builder.py` (build_chart_payload / build_map_payload — composer 가 직접 emit 으로 대체)
- `src/templates/{report.html,report_block.html}` (legacy archetype 용)
- `src/templates/blocks/` 17종 — composer 가 `embedded_blocks` 로 명시 시만 사용 (현재 실질 미사용)

### Removed 모듈 (v5.2.9 — 5년 가까이 dead code 정리)
- `src/agents/{player,dynamics,chain_reaction,scenario,visual,quality_inspector,synthesis_judge}_*.py` 7개 파일 삭제
- `src/tests/test_quality_gates.py` 삭제 (QualityInspector / SynthesisJudge 테스트)
- `src/models.py:ContextAnalysis.recommended_persona` 필드 삭제 — persona dict 채널 (v4.3.0) 폐기
- `src/state/models.py:EvidencePack.recommended_persona`, `AnalysisBrief.recommended_persona` 필드 삭제
- `src/token_budget.py` 의 dead flag 6종 (`use_llm_quality_gate / use_llm_narrative_plan / use_llm_executive_summary / use_llm_visuals / use_llm_synthesis / use_legacy_personas`) 삭제. 본문 문체 SSOT 는 [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) 로 통합.

## Chart System (v7.5.0)
- 차트 데이터는 **composer 가 단일 LLM 호출 안에서 직접 emit** (외부 빌더 없음). 빈 데이터면 차트 없음.
- **27종 type** (v7.9.17 — network 폐기 CHART-AP-36):
  - 기존 12종 (v5.2.13 까지): bar / donut / line / gantt / stacked / bubble / heatmap / dual_line / forecast / choropleth / candle / area
  - v5.3.0 신규 7종 (FT/Economist 스타일, **guarded** tier): scatter / stacked_area / lollipop / slope / small_multiples / waterfall / range_bar
  - v5.3.0 sankey (**guarded** tier — 재무 분해 / 자본 배분)
  - v7.0.0 신규 3종 (**guarded** tier, REFACTOR_V7_PLAN.md §1.3): bump (시기별 순위 경쟁) / bullet (목표 대비 실적) / connected_scatter (2변수 시간 경로)
  - v7.5.0 신규 4종 (**guarded** tier — 이중 축 결합 + 사회 이슈 어휘): combo (이중 축 막대+선 — 부피·건수 × 수준) / diverging_bar (대립 쌍 발산 막대 — 찬반·유입유출, 사회 이슈·여론 SSOT) / pyramid (인구 피라미드 — 연령 × 두 집단) / dot_matrix (100칸 와플 — '100명 중 N명' 체감)
- **annotation 레이어 (v7.0.0 개방)**: `{kind: vline|hline|band|point}` 를 cartesian 전 type (기존 bar/line/gantt/bubble/dual_line/forecast + candle/area/scatter/stacked_area/lollipop/range_bar/bullet/connected_scatter + v7.5.0 combo) 이 지원. 차트당 ≤3 (AP-V7-6, `ComposedSection._drop_invalid_charts` 가 정제). 에디토리얼 헤더 `unit_line` (단위·기간 라인) 도 v7.0.0 additive.
- 각 차트는 `ComposedSection.charts: list[dict]` 의 dict 1개 — `{type, title, data, note?}`.
- 렌더링: `freeform_essay.html` 이 chart-card SVG + inline JSON payload emit → `charts.js` 가 스캔/렌더 (mono guide §4 패턴 자동 적용).
- **차트 type 결정 트리** — composer SYSTEM_PROMPT 의 결정 트리 (v5.3.0 신설). LLM 의 line/bar default bias 차단 (negative constraint 패턴).
- **5-Layer Usage Guarantee** (v5.3.0 — 캔들 회귀 차단):
  ① telemetry (`src/visual/usage_log.py`) — type emit JSONL 영구 기록, starvation alarm. **v8.3.0 자기교정 루프**: `composer_rebalance_hint` 가 최근 30건에서 굶주린 *서사* type(주입 전용·르포 전용 제외)을 골라 orchestrator 가 다음 보고서 composer 프롬프트에 우선-고려 힌트로 자동 주입 (0-LLM 제어, 힌트 비면 byte-equal — 관리자 알림 대신 봇 스스로 빈도 회복, 사용자 결정 2026-07-02)
  ② 결정 트리 (SYSTEM_PROMPT)
  ③ method × exhibit 매트릭스 (`research_director.py:_DEFAULT_REQUIRED_EXHIBITS` — fault_tree→waterfall, pre_mortem→scatter)
  ④ 다양성 쿼터 (`deterministic_gate.py:chart_type_monotony` soft fail — standard ≥3 차트에 distinct <2 면 hold). **v8.3.0 — `check_chart_type_monotony` public 진입점으로 V5 게이트와 독립해 production log-only 상시 배선** (발행 불차단, 강제 승격은 관찰 후 사용자 게이트). composer 프롬프트도 v8.3.0 부터 *서사 차트*(시장 가격 차트 제외) 기준 distinct 필수 하한 (standard ≥3 / deep ≥4, '권장' 폐기)
  ⑤ 회귀 fixture (`tests/regression/fixtures/chart_type_scenarios.yaml` — 29 시나리오 SSOT, `KNOWN_CHART_TYPES` 와 1:1)
- 신규 type 추가 절차: ① `charts.js` 의 `RENDERERS` dict 에 함수 추가 ② composer SYSTEM_PROMPT 의 type 별 data 스키마 섹션에 추가 ③ `src/visual/schemas.py` 의 `_TYPE_TO_GUARD` 에 가드 추가 ④ `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 등록 ⑤ `src/visual/usage_log.py:KNOWN_CHART_TYPES` 추가 ⑥ `tests/regression/fixtures/chart_type_scenarios.yaml` 시나리오 추가 ⑦ 회귀 테스트.

## Market Data Fetcher (v5.2.0)
- ContextAnalyst 가 LLM 출력에 `instruments_mentioned: list[str]` emit → orchestrator 가 `src/tools/market_fetcher.py` 의 `fetch_many` 호출 → `ContextAnalysis.time_series` 채움 → composer 가 candle / line / area 차트로 emit.
- 4 source: KRX (한국 개별주 + **한국 지수 코스피/코스닥**, 무인증) / YAHOO (미국 지수·개별주 + DXY + 한국 지수 *폴백*, 무인증) / FRED (미국 매크로 — UST/WTI/금, free key) / ECOS (한국은행 macro, free key). SSOT `src/tools/market_fetcher.py:INSTRUMENT_REGISTRY` (현재 24 종목). **v7.9.15 — 코스피·코스닥 지수는 KRX(pykrx) `get_index_ohlcv`(1001/2001) primary + Yahoo(^KS11/^KQ11) fallback** (kospi-date-mismatch: Yahoo 한국 지수 EOD 게시가 장 마감 다음 날 아침까지 지연돼 직전일 봉이 박히는 회귀 차단. `InstrumentSpec.fallback_source`/`fallback_code` + `fetch_market_series` 의 primary-빈데이터→폴백 2단 라우팅. pykrx index 실패 시 Yahoo 폴백이라 회귀 무). v5.6.9 — 미국 빅테크/반도체 개별주 10종 (NVDA/TSLA/AAPL/MSFT/GOOGL/AMZN/META/AMD/TSM/AVGO, Yahoo candle) + 미국 지수 3종 (S&P500 `^GSPC` / 나스닥 `^IXIC` / 필라델피아 반도체 `^SOX`, Yahoo line) 추가. YahooFetcher 는 범용 — 레지스트리 항목만 추가하면 KOSPI 와 동일 경로로 fetch. `_ensure_time_series_chart` 가 주제(event_name>summary) 등장 종목을 우선 차트화 (`_topic_priority_key`, 'NVIDIA 보고서엔 NVIDIA 차트' 보장). v7.0.2 — `_densify_ts_charts` 가 composer emit 차트의 *일별 밀도* 도 보장 (CHART-AP-31, 듬성 데이터를 실측 행으로 교체. v8.3.0 — 행수 상한 `_DENSIFY_MAX_ROWS=260`(≈1년 거래일), 초과 창은 균등 스트라이드 다운샘플 + 마지막 봉 보존, `_build_ts_chart` 주입분 공통 — 3년 751행 일봉 발행 사례 차단). v5.2.6 — DXY 는 FRED/DTWEXBGS (Fed Broad TWI, 117~125 레인지의 다른 지수) 에서 Yahoo/DX-Y.NYB (진짜 ICE DXY, 99~110 레인지) 로 교체.
- Graceful degradation — API key 누락·HTTP fail 시 빈 series + warning log. 보고서는 정상 진행, 해당 instrument 차트만 emit X.
- 기본 기간 3M (사건 보고서 event-anchored). 사건 일자 = `context.date` 기준. 향후 mode-aware period (daily=1M / historical=3Y) 확장 예정.
- 환경변수 `FRED_API_KEY` / `ECOS_API_KEY` / `KRX_API_KEY`. `.env.example` 참조.

## 장마감 브리핑 시장 내부 데이터 — 선물·옵션 그릭 + 시장 폭 (v7.9.0)
> **장마감 브리핑(`scheduler/market_briefing.py`) *전용*.** orchestrator `run_analysis(fetch_kr_market_internals=True)` 일 때만 작동 — 일반 `/analyze`·일일 브리핑은 default False 라 byte-equal. data.krx.co.kr getJsonData 는 2026-06 부터 **로그인 필수**(무로그인 시 HTTP 400 'LOGOUT') → `src/tools/krx_client.py:ensure_session` 이 `Config.krx_id/krx_pw`(.env: KRX_ID/KRX_PW)로 pykrx 로그인 핸드셰이크 재사용, 인증 쿠키로 직접 POST(`asyncio.to_thread`). 자격증명 없으면 graceful skip(보고서 정상). 무료 data.krx 계정 필요.
- **`src/tools/greeks.py`** — Black-Scholes IV 역산 + 그릭(델타/감마/세타/베가/로) + max pain/풋콜비율. 순수 stdlib(scipy 불요). 옵션 그릭 산출 SSOT. 단위 테스트 `tests/test_greeks.py`.
- **`src/tools/derivatives_fetcher.py`** — KOSPI200 선물(MDCSTAT12501 `KRDRVFUK2I`: 종가·베이시스·미결제)·옵션 체인(`KRDRVOPK2I`: 행사가별 프리미엄·OI·거래량)→ **종가에서 IV·그릭 자체 계산** + 풋콜비율·max pain·관심 콜/풋 행사가. 결과는 `key_figures` 로 출력. `build_snapshot` 은 순수 함수(회귀 `tests/test_derivatives_fetcher.py`). 옵션 IV 무위험금리 `DERIVATIVES_RISK_FREE`(기본 0.03).
- **`iv_skew` 차트 2단 (v8.2.5)** — `charts.js:drawIvSkew` 가 *상단 옵션 가격(프리미엄) + 하단 IV 스큐* 2단 패널(행사가 x축 공유) + 날짜 화살표(◀ ▶, 최근 N영업일 하루씩 전환)로 렌더. 선 위 점 표식·다일자 페이드 오버레이 폐기. 스큐 점에 `premium` 동봉(`build_derivatives_charts`/`_skew_points_for_expiry`/`augment_skew_history`) + 일별 캐시 `premium` 컬럼(`src/tools/skew_cache.py`, 구 캐시 nullable `ALTER TABLE` 마이그레이션). `premium` 없는 구 payload 는 스큐 단일 패널 graceful 호환.
- **`src/tools/breadth_fetcher.py`** — 전종목 시세(MDCSTAT01501 STK/KSQ)로 코스피·코스닥 등락 종목 수·하락비율(당일·5/20일)·지수 상관. 멱등 **SQLite 캐시**(`BREADTH_CACHE_PATH`, 신규 영업일만 append). decline-ratio line 차트 + `key_figures`. 회귀 `tests/test_breadth_fetcher.py`. CLI: `python -m src.tools.breadth_fetcher backfill --days 120`(이력 1회 적재).
- orchestrator 가 두 snapshot 의 `key_figures` 를 `context.key_figures` 에 병합(본문 실수치 노출) + breadth line 차트 결정적 주입. 페르소나 제11 렌즈(파생 데스크 5축)·제4 렌즈(시장 폭)·`market_briefing` 프롬프트가 인용·분석 강제.
- flag: `ENABLE_KR_DERIVATIVES` / `ENABLE_MARKET_BREADTH`(기본 ON). **샌드박스 egress 403 → 실연동은 VM 검증** (`python -m src.tools.derivatives_fetcher` / `... breadth_fetcher`). 계산 로직은 단위 테스트로 검증.
- 신규 chart/agent 아님 — `key_figures` + line 차트 주입이라 차트 매트릭스·DATA_MODELS 무변경(Pydantic 모델 추가 없음, tool 내부 dataclass + dict 채널).

## Report Images (v5.4.0)
- ContextAnalyst 가 수집한 `sources` URL 들에서 og:image / og:title / og:description / publisher 자동 추출 → `ContextAnalysis.available_images` → composer 가 본문 흐름에 맞는 사진만 골라 `ComposedReport.hero_image` (보고서당 0~1장) + `ComposedSection.images` (섹션당 0~1장, 보고서 전체 0~3장) emit.
- SSOT: [src/tools/image_fetcher.py](src/tools/image_fetcher.py) (og 메타 parser + publisher 매핑 16개 매체) + [src/agents/narrative_composer.py](src/agents/narrative_composer.py) `SYSTEM_PROMPT` 의 `=== 사진 (v5.4.0) ===` 섹션 (선택 원칙 / 캡션 작성 가이드 / Anti-pattern).
- 렌더: `freeform_essay.html` 의 `.freeform-figure.hero` (deck 직후) + `.freeform-figure.inline` (섹션 charts 다음, embedded_blocks 앞). 컬러 사진 그대로, mono 필터 X. caption 은 Newsreader italic + credit `© Publisher` 는 sans-serif tone-down. 7개 테마 토큰 (border-soft / fg-3) 자동 적용. 모크업 SSOT: [samples/report_images_theme_compare.html](samples/report_images_theme_compare.html).
- 외부 lib 의존성 0 — aiohttp + stdlib regex 만. HTML 첫 64KB cap (og 태그는 `<head>` 안). 평범한 데스크탑 Chrome UA + Accept 헤더로 위장 (메이저 매체 403 회피). per-URL 5s + total 12s timeout — 보고서 흐름 영향 최소화.
- Graceful degrade — sources 빈 list / 모든 URL 403·timeout / 네트워크 차단된 환경 / composer 가 자신 없어 사진 emit X 모두 보고서 정상 진행. `market_fetcher` 와 동일 패턴.
- **주의**: 사용자에게 노출되는 *유일한 외부 이미지 출처*. 광고·placeholder·매체 보일러플레이트 사진이 박힐 위험 — composer `SYSTEM_PROMPT` 의 *선택 원칙 #3* (title 에 'logo' / 'newsletter' / 'subscribe' 만 있으면 emit X) 으로 차단하지만 100% 아님. 봇 본인 사용 목적이므로 저작권은 출처표기 (© Publisher) 로 갈음.

## Map System (v7.5.0)
- composer 가 `ComposedReport.embedded_map` 에 보고서당 1개 emit (지리적 사건일 때만).
- **v7.2.0 어휘 확장 (additive — 무지정 payload 는 기존 렌더 동일)**: `arcs.kind`(flow 방향 화살촉+weight 1~3 굵기 / alt 우회 점선 / tension 하락색 ✕) + `arcs.label_t`, `markers.kind`(chokepoint ◆ / port ◎ / military ▲) + `value`(보조 수치 행) + `label_side`, `regions`(국가 역할 색조 subject/ally/rival/contested — world-atlas 영문명 매칭), `sea_labels`(세리프 워터마크), graticule·해안 정의선·라벨 pill/헤일로. 비교 목업: [samples/map_redesign_v7_compare.html](samples/map_redesign_v7_compare.html).
- **v7.5.0 투영·어휘 확장 (additive)**: `projection: "globe"` — 정사영(orthographic) 지구본. 대권(great-circle) 경로가 휘지 않는 투영 — 탄도미사일 사거리·위성 통과·극항로·대양 횡단 공급망 등 *대륙 간 스케일* 토픽 전용 (지역 사건은 평면 유지). 드래그=회전·버튼=줌, arcs 는 측지선 렌더, v7.2.0 어휘 전부 동일 계약. + `rings: [{from_id|lng/lat, radius_km, label?, kind?}]` — 사거리권·작전반경·도달권 동심원 (d3.geoCircle, 평면·지구본 공통). kind `range`(위협·사거리, 하락색 점선 — 기본) / `coverage`(도달, 액센트 점선), ≤4개, radius_km 는 본문 근거 수치만 (WRITE-AP-5). 베이스라인: [samples/map_globe_v7_5.html](samples/map_globe_v7_5.html).
- 베이스맵: d3 + d3-geo + world-atlas/110m TopoJSON. maplibre-gl 의존 폐기.
- 렌더링: `maps.js` 가 `#freeform-map` 컨테이너 + `#map-payload` 스크립트 읽어 SVG 그림.
- mono guide §2.2: 외부 타일 서비스 / 글리프 PBF 호출 금지. world-atlas 한 번 fetch (~100KB) 후 캐시.
- v4.5.7 — Somaliland (de facto) 폴리곤·legend 는 `path.bounds()` viewport 교집합 통과 시에만 렌더 (CHART-AP-14). 무관한 지리 annotation 의 무조건 렌더 차단.

## Mode Routing (v4.5.7)
- 사용자 메시지 키워드로 자동 매핑: `짧게/간략히/요약/빠르게` → fast, `심층/자세히/면밀` → deep, **그 외(키워드 없음) → deep** (v5.8.2 기본 변경, 기존 standard). standard 는 이제 호출부가 `mode="standard"` 로 명시할 때만 진입. daily_briefing / 후속 보고서는 `mode="deep"` 명시이므로 resolve_mode 무관.
- Mode 별 정책 SSOT 는 [src/token_budget.py](src/token_budget.py).
- v4.0.0 부터 모든 모드 LLM 호출 **2회** 동일 (context + composer). mode 는 composer prompt 의 분석 깊이 지시 (섹션 수, 모순 명시 강도, 시나리오 개수) + max_tokens 한도 (v4.5.4: composer fast 12K / standard 20K / deep 32K, v4.5.7: context fast/standard 4K / deep 10K) 결정.

## Report Format Routing — 르포(탐사보도) (v8.0.0)
- **mode(분석 깊이)와 직교한 *포맷(장르)* 축.** SSOT 는 [src/token_budget.py](src/token_budget.py) `resolve_report_format` / `strip_reportage_trigger`. 메시지에 **"르포"** 토큰이 있으면 `report_format="reportage"`, 아니면 `"standard"` (기존 기사형). 트리거는 "르포" 1개만 (오탐 최소화 — "탐사/내막" 류 동의어는 일반 보고서를 르포로 오인할 위험이 있어 제외).
- **directive 채널**: 트리거 토큰("르포 형식으로" 등 조사 변형 포함)을 떼어낸 나머지 원문이 `AnalysisRequest.user_directive`. ContextAnalyst 사실 증류로 거세되던 사용자 *앵글*("특히 OOO 의 역할에 집중")을 composer payload(`user_directive`)에 직접 복원하는 채널. 르포의 정체성 = 어느 실타래를 당기나. 주관적 앵글은 fact-critic 검증 면제, 내장된 검증 가능한 사실 주장만 grounding.
- **장르 골격**: composer SYSTEM_PROMPT 에 `_REPORTAGE_BLOCK` 직교 주입(reportage 일 때만, [narrative_composer.py](src/agents/narrative_composer.py)). 발단→이해당사자→내막·동기→전개→전망(서사형) 5막 + 행위자(인물·국가·조직·기관·기업) 중심 관계망/지도/sankey/timeline + **감시신호(watch_signals) epilogue 제거**(프롬프트가 `[]` 지시 + orchestrator 가 reportage 면 Watchlist 등록 스킵). 인물 사진은 기사 og:image 만.
- **byte-equal**: `report_format=standard`(트리거 없음) + directive 없을 때 `_compose_system_prompt` / `_build_unified_payload` 모두 기존과 byte-equal. 회귀 [tests/regression/test_reportage_format.py](tests/regression/test_reportage_format.py).
- **전용 디자인(v8.0.0)**: 일반 보고서와 *완전 분기*. ① 전용 테마 풀 [lens_policy.REPORTAGE_THEMES](src/lens_policy.py) 8종 다크(`reportage_*`, report.css `[data-theme="reportage_*"]`, `select_reportage_theme()` 가 르포일 때만 선택) ② 폰트 G마켓 Sans(디스플레이)+Noto Sans(본문) ③ 플랫 미니멀(둥근모서리/그림자 제거) ④ 현재형·박진감 어투 ⑤ **에필로그 전부 제거**(watch_signals/timeline_flow/closing/confidence — 가벼운 소설처럼 끝) ⑥ 본문·제목에 '르포' 단어 금지(UI 헤더 배지로만) — `[르포]` 배지는 **3곳**: 보고서 전문 헤더(`reportage.html` 의 `.rep-top`, v8.5.2) · Cloudflare Pages 관리자 목록(`report_synthesizer._generate_index`, v8.5.2) · GitHub 미러 README(`build_reports_index`, v8.0.0). **목록 2곳의 판별 SSOT 는 [src/tools/report_kind.py](src/tools/report_kind.py)** (v8.5.3 — 르포 + 브리핑 종류 배지를 한 로직으로 통합. 두 목록이 어긋나지 않게). 텔레그램 작동은 일반 보고서와 동일.
- **전용 템플릿(v8.0.0)**: 르포는 **`src/templates/archetypes/reportage.html`** (freeform_essay 와 완전 분리, report_synthesizer 가 report_format=reportage 시 라우팅). 가드 덧대기 아님 — 전용 깨끗한 렌더 경로. 헤더=버전만 / 제목 / 작성일시(분) / 번호 섹션(소제목+본문) / 용어풀이 / 차트·지도 / 최소 푸터. 목차·kicker·fact_grid·pull_quote·analogy·lede·dropcap·쟁점·감시신호·시간궤적·요약·신뢰도·바이라인 전부 미렌더. 한 문단 ≤5문장. ambient 애니: stakeholder_map(엣지 흐름+hub 펄스, charts.css `.sm-flow/.sm-pulse`)·sankey(중심선 입자)·globe(연속 자전, maps.js, reportage 테마 `--map-*` 색). 모두 reduced-motion 정지.
- **로드맵**: Phase 0~1.5 + 전용 템플릿/애니 **완료**. 남은 것 — **텔레그램 전용 후속 르포 신호**(signals 없이 후속 버튼). Phase 2 — ReportBundle 정합(osint 영상). Phase 3 — VM e2e.
- **v8.2.2 — 르포 작성 모델 Opus 4.8 격상**: 르포는 탐사 페르소나·점잇기·시나리오 추론으로 더 높은 추론을 요구하므로 composer 모델을 4.8 로 (`NarrativeComposer.COMPOSER_MODEL_REPORTAGE`, `_model_for_format`). `compose_unified`(주 작성)+`revise_for_facts`(보완 패스) 둘 다 르포면 4.8, 일반 보고서는 4.7 그대로(byte-equal). `_call_cli`/`_call_api` 의 `model` 파라미터 + critic_loop reviser 의 `report_format` 전달로 배선. context_analyst 는 4.7 유지(사실 수집은 모델 무관).
- **v8.2.8 — 편집장 CLI 출력 head-loss 근본 수정 (json envelope 캡처)**: v8.2.7 직후 VM bot.log 정밀 분석으로 588자 미파싱의 진짜 원인 확정 — 모델 산문 이탈이 아니라 편집장 CLI **`--output-format text` 캡처가 긴 응답에서 stdout *머리*(여는 `{`·headline·앞 섹션)를 잃는 systemic 결함**(꼬리만 생존, 2026-06-02부터 수개월·보고서 종류 무관 누적). v8.2.6 가 출력을 최장으로 늘려 꼬리마저 588자로 짧아져 복구 불능→표면화(WRITE-AP-13 의 진짜 뿌리). **Fix**: 편집장 CLI 캡처를 `--output-format json` 단일 envelope(`{...,"result":"<본문>"}`)로 전환, 텍스트 렌더 우회 + 전체 본문 안전 추출(`_extract_cli_result`, 완결/절단/비-envelope graceful). 킬 스위치 `V8_CLI_JSON_OUTPUT=0`(text 복귀 byte-equal). 회귀 `test_cli_json_capture.py`. VM 재배포 전 `claude -p "ping" --output-format json` 로 envelope 1회 확인.
- **v8.2.7 — 르포 생성 안정화 (모델 안전망 + JSON 계약 스코핑)**: v8.2.6 르포 1건이 편집장(4.8) **raw 588자 미파싱**(타임아웃 아님, 클린 종료)으로 minimal fallback 발행(WRITE-AP-25 계열, 사용자 catch). ① **모델 안전망** — 르포 전용 모델(4.8) 작성·재시도가 *모두* 실패하면 minimal fallback 전에 안정 모델(`COMPOSER_MODEL`=4.7)로 마지막 1회 더 작성(`compose_unified`). 일반 보고서는 분기 미진입 byte-equal. ② **프롬프트 계약 스코핑** — `_REPORTAGE_BLOCK` 분량 강령에 "분량은 JSON `sections` 배열 *안* 에서만, 산문을 계약 밖으로 빼지 말고 응답은 `{` 로 여는 단일 JSON" 명문화(강한 길이 압박의 JSON drift 차단). 회귀 `test_reportage_model_fallback.py`.
- **v8.2.6 — 르포 분량 ~2배 확장 (_REPORTAGE_BLOCK 분량/깊이 강령)**: 사용자 요청 — 르포가 너무 짧다, 두 배로. 원인은 페르소나의 '담백하게' 가 *짧게* 로 오독돼 5막을 각 1섹션·단문단으로 압축하던 것 (deep 48K 한도는 이미 충분). `_REPORTAGE_BLOCK` 에 [분량과 깊이 강령] 신설 — ① 5막 각 2섹션 이상으로 펼쳐 *8~12 섹션* ② 섹션당 *3~6 문단* ③ 탐사 3도구 각 섹션마다 가동 ④ '담백 = 무장식이지 짧음 아님' 명문화 ⑤ 물타기 금지("길되 밀도 있게"). standard byte-equal. 회귀 `test_reportage_block_has_length_depth_mandate`.
- **v8.2.0 — 탐사 기자 페르소나 (르포 전용, _REPORTAGE_BLOCK 강화)**: 단순 기사 나열을 명시적으로 금지하고, 르포의 가치를 *한 발 더 들어가는 곳*에서 찾는다. 세 가지 도구 — ① 묻힌 디테일 들춰내기(헤드라인 밖 각주·곁가지) ② connecting dots(흩어진 사실 2~5개를 묶어 패턴) ③ 시나리오 추론(약간 무리한 추측도 *명시 가설 라벨* 안에서 허용). 표현은 **사실(단정형) / 추론(헤지형) / 가설(명시 라벨)** 3등급으로 *반드시* 구분 — 라벨 없이 가설을 단정 부사("분명히/명백히")로 흘리면 사실 규율 위반. 안전선: 무근거 fabrication·입력 사실과 충돌하는 추론·시점/수치를 추론 톤으로 흐림 모두 금지. codex 검수자도 reportage 인지(payload `report_format`)로 표현 등급 정합 검수 — 라벨된 추측은 허용·통과, 라벨 없는 단정 추측은 `speculation_as_fact`(high). SSOT 3중: [src/agents/narrative_composer.py:_REPORTAGE_BLOCK](src/agents/narrative_composer.py) (작성 페르소나) + [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md) §"포맷 적응" (런타임 검수 단축본) + [prompts/market_factcheck_desk_v6.md §14](prompts/market_factcheck_desk_v6.md) (검수 전체 기준서) + [docs/REPORT_STYLE_GUIDE.md §9](docs/REPORT_STYLE_GUIDE.md) 변경 이력. standard 모드는 byte-equal(르포 트리거 없는 보고서엔 영향 0). 회귀 `tests/regression/test_reportage_format.py` 가 탐사 페르소나 marker 가드.
