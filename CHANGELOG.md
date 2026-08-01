---
tier: 3
last_synced_with: v8.5.2
ssot_for:
  - "사용자 관점 릴리스 노트 (versioned changes)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "DEVLOG.md (개발 상세 로그)"
last_review: 2026-05-26
---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom `vMAJOR.MINOR.PATCH` scheme tracked in `src/orchestrator.py:VERSION`.

상세한 개발 로그·트러블슈팅·인프라 메모는 [DEVLOG.md](DEVLOG.md) 참조.

---

## v8.5.2 — 르포 목록 등록 확인 + [르포] 배지 표기 (Pages 목록 · 전문 헤더)

사용자 확인 요청 — "르포도 보고서 저장되는 웹사이트에 등록되나? 등록될 때 [르포] 헤더를 달고 등록되게 해달라."

**확인 결과 — 저장·등록 자체는 이미 정상.** 르포도 일반 보고서와 *같은* 경로로 `analysis_<id>.html` 로 저장되어 Cloudflare Pages 에 배포되고, 관리자 목록(`_generate_index`)이 `analysis_*.html` 를 glob 하므로 목록에도 이미 올라가 있었다. GitHub raw 미러도 포맷 필터 없이 전 보고서를 push 한다. 빠져 있던 것은 **표기**였고, 이는 CLAUDE.md v8.0.0 이 "보고서 전문 헤더 + 리스트에 [르포] 배지" 라고 적어둔 설계가 코드에 구현돼 있지 않던 문서-코드 drift 였다.

| 표기 위치 | v8.5.1 까지 | v8.5.2 |
|---|---|---|
| GitHub 미러 README (`build_reports_index`) | `[르포]` 있음 (v8.0.0) | 유지 |
| Cloudflare Pages 관리자 목록 (`_generate_index`) | **없음** | `[르포]` 배지 추가 |
| 르포 보고서 전문 헤더 (`.rep-top`) | **없음** | `[르포]` 배지 추가 |

- **판별 근거 2단** — 목록은 HTML 머리 3000자만 읽어 판별한다(제목 추출 read 재사용, 추가 파일 IO 0). ① `<meta name="report-format" content="reportage">` — `reportage.html` 에 신설, v8.5.2~ 신규 발행분. ② `data-theme="reportage_*"` 폴백 — v8.0.0~v8.5.1 사이 이미 발행돼 meta 가 없는 르포도 **재렌더 없이** 배지가 붙는다.
- **전문 헤더** — `.rep-top` 을 `flex-end` → `space-between` 으로 바꿔 좌측 `[르포]` 배지 / 우측 버전·Rev. 본문·제목엔 여전히 '르포' 단어를 넣지 않는다(v8.0.0 원칙 유지 — UI 배지로만).
- **검증** — 실제 `_generate_index` 를 임시 디렉토리에서 돌려 신규 르포(meta)·구 발행 르포(폴백)·일반 보고서 3종 혼재 목록을 생성, 르포 2건에만 배지가 붙는 것을 스크린샷·문자열 양쪽으로 확인. 르포 템플릿도 렌더해 헤더 배지 확인.
- **회귀** `tests/regression/test_reportage_index_badge.py` 6종 — 등록 자체 가드(목록에 르포 행 존재) · meta/폴백 배지 · 일반 보고서 오부착 방지 · 일반 템플릿의 르포 마커 오염 방지 · GitHub 미러 배지 유지. 변이 주입(폴백 제거)으로 non-vacuous 확인.

## v8.5.1 — 일반 보고서 줄글 양끝 정렬 (오른쪽 끝단 정돈)

사용자 요청 — 일반 보고서 본문의 오른쪽 끝이 들쭉날쭉해 "뒤죽박죽" 하니 르포처럼 오른쪽도 꽉 차게. 르포(`reportage.html`)는 v8.2.15 부터 `.rep-prose` 에 양끝 정렬이 걸려 있었는데 일반 보고서(`freeform_essay.html`)만 왼쪽 정렬로 남아 있던 비대칭을 해소.

- **줄글 6종에 양끝 정렬 3종 조합 적용** — `.freeform-prose`(본문, p/li 포함) · `.contradiction-prose`(모순 산문) · `.freeform-lede`(머리글) · `.freeform-analogy-body`(비유) · `.freeform-closing-body`(맺음말) · `.epilogue-watch-desc`(감시신호 설명). 조합은 르포와 동일: ① `text-align:justify` 양끝 정렬 ② `text-align-last:left` 로 문단 *마지막 줄은 늘리지 않음*(끝 줄이 억지로 벌어지는 전형적 justify 결함 차단) ③ `word-break:keep-all` 로 한글은 어절 단위로만 줄바꿈(단어 중간 절단 금지, 한글 조판 관례) + `overflow-wrap:break-word` 로 긴 URL·영문 토큰 넘침 방지.
- **비-줄글은 제외** — 제목·라벨·사진 캡션(`figcaption`, v5.5.11 의 명시적 left 유지)·인용 디스플레이(`pull_quote`)·수치 타일은 정렬 대상 아님.
- **검증** — Playwright/Chromium 으로 실제 템플릿을 렌더해 데스크탑(900px)·모바일(420px) 스크린샷 대조. 데스크탑에서 우측 끝단 완전 정렬 확인, 문단 마지막 줄은 왼쪽 유지. 모바일 좁은 폭의 어절 간격은 르포 본문과 픽셀 단위로 동일(같은 규칙) — 어절 유지를 포기하면 간격은 촘촘해지나 한글 단어가 잘려, 조판 관례상 어절 유지를 택함.
- **회귀** `tests/regression/test_prose_justify.py` 4종 — 줄글 6종의 3종 조합 + p/li 자식 규칙 + 르포 정합 + figcaption left 고정. 변이 주입으로 non-vacuous 확인.
- **문서 정합** — v8.5.0 에서 누락됐던 `docs/CATALOGS.md` 의 composer 모델 표기(Opus 4.7 → Opus 5) 동반 정정.
- **발행본 소급** — CSS 는 보고서 HTML 에 인라인되므로 *이미 발행된 보고서는 자동 반영되지 않는다*. 소급하려면 VM 에서 `scripts/patch_report.py <report_id> --rerender-only`(내용 무변경·URL 보존·revision 소수부 +1).

## v8.5.0 — 보고서 파이프라인 모델 Opus 5 격상

보고서 생성이 실패하는 문제 대응 + 사용자 요청으로 파이프라인 전 Opus 계열 모델을 **`claude-opus-5`** 로 격상. Opus 5 는 Opus 4.8 과 동일 가격의 상위 모델(1M context / 128K output)이라 드롭인 교체.

- **모델 통일** — ContextAnalyst(`context_analyst.py`) + NarrativeComposer(`COMPOSER_MODEL`/`COMPOSER_MODEL_REPORTAGE` 둘 다, 일반·르포 동일) + V5 opt-in 4종(Editor/ResearchDirector/VisualPlanner/DeskEditor)을 `claude-opus-4-7`/`claude-opus-4-8` → `claude-opus-5`. 르포 분기 배선(`_model_for_format`)은 향후 상위 모델 재분리 대비로 보존(값 동일). chart_critic 등 light 경로(sonnet-4-6)는 불변.
- **모델 안전망 전 포맷 확장 (`COMPOSER_MODEL_STABLE`)** — v8.2.7 안전망(주 모델 전부 미파싱/실패 시 안정 모델 최후 1회)의 폴백 모델을 `COMPOSER_MODEL` 에서 별도 상수 `COMPOSER_MODEL_STABLE=claude-opus-4-7`(오래 검증된 구세대)로 분리. 주 모델이 신모델 Opus 5 로 통일되면서 (구현상 자연히) 일반 보고서도 안전망 대상에 포함 — 신모델 초기 불안정 대비. 회귀 `test_reportage_model_fallback.py` 2종 갱신.
- **바이라인·라벨 정합** — `critic_loop._pretty_writer` 에 단일 메이저 버전 ID 매핑 추가(`claude-opus-5` → 'Claude Opus 5'; 기존 `X-Y` 매핑은 그대로). orchestrator 텔레그램 진행 알림 라벨을 'Opus 5' 단일 값으로 (구 4.8/4.7 ternary 제거).
- **회귀 테스트 갱신** — `test_reportage_format.py`(모델 상수·라벨 marker) / `test_codex_loop.py`(_pretty_writer opus-5) / `test_editor.py`(EDITOR_MODEL).
- **문서** — CLAUDE.md Tech Stack·Agents, docs/ARCHITECTURE.md §3.1/§3.2·다이어그램, README. 과거 버전 항목(v8.2.x 등)의 4.7/4.8 표기는 이력이므로 불변.
- **운영 노트** — VM 반영은 `git pull` + `sudo systemctl restart agents-reviewer.service`. 재배포 전 CLI 에서 `claude -p "ping" --model claude-opus-5 --output-format json` 1회 확인 권장.

## v8.4.0 — osint_generator 저장소로 번들 직접 미러 (`json/` 폴더)

보고서마다 생성되는 `.bundle.json`(텔레그램에 `📦 영상 제작용 번들`로 첨부되는 것과 동일 파일)을 영상 파이프라인 repo(`doroper98/osint_generator`)의 `json/` 폴더로 자동 push 하는 두 번째 미러 타깃 신설. 지금까지 osint 쪽은 텔레그램 첨부로만 번들을 받았는데, 이제 자기 repo 에서 보고서 생성 시마다 바로 집어갈 수 있다. `GitHubMirror.for_osint(config)` — 기존 raw 미러(`GITHUB_MIRROR_*`)와 독립된 `GITHUB_OSINT_*` config 4종(token/repo/branch/path, path 기본 `json`). 대상 repo 가 *private* 이라 별도 PAT 필요(`GITHUB_OSINT_TOKEN`, 비면 `GITHUB_MIRROR_TOKEN` 폴백 — 같은 PAT 가 양쪽 권한 시). **`degraded`(생성 실패/열화) 보고서·르포는 push 하지 않는다** — 편집장 타임아웃/파싱불가/CLI오류로 minimal fallback 된 것은 `composed_report.degraded==True` 게이트로 제외(사용자 요청). 토큰/repo 미설정 시 `enabled` False → graceful skip(Cloudflare/raw 미러 흐름 byte-equal). `report_synthesizer` 가 raw 미러 직후 호출. 회귀 `tests/test_github_mirror.py` 6종(osint config 읽기·mirror 토큰 폴백·osint 토큰 우선·`push_files` 성공 카운트·disabled 0). `.env.example` + 문서 갱신. (기존 v8.x 정상 번들 63건은 별도 백필로 osint repo 에 적재.)

## v8.3.6 — 보도 사진 cleared ⇒ credit 필수 불변식 (consumer v0.42.2 정합)

osint_generator v0.42.2 회신 — 소비측에 credit gate 추가(credit 빈 `cleared` 사진 거부·스킵)로 "credit 없는 cleared 는 없다"는 producer 보증을 이중화. 그런데 producer 의 `_image_rights` 가 **공식배포 도메인 경로에서 credit 을 확인하지 않아**, 공식 도메인인데 credit 이 빈 사진이 `cleared`+빈 credit 으로 나갈 수 있었다(→ 소비측이 스킵해 낭비 + 보증 위반). Fix — `_image_rights` 를 **credit 없으면 무조건 `needs_review`** 로 강제(공식 도메인이라도). 이제 불변식 `cleared ⇒ credit 비어있지 않음` 이 코드로 보장된다. 회귀 `test_image_rights_credit_required_for_cleared` + 빌드 번들의 모든 cleared 이미지 credit 비어있지 않음 assert. 계약 [IMAGE_BUNDLE_CONTRACT.md §3.1-a](docs/CONTRACTS/IMAGE_BUNDLE_CONTRACT.md) 에 불변식 명문화. 순수 강화 — credit 있는 사진(대다수)의 동작 불변.

## v8.3.5 — report_bundle 에 보도 사진 필드 추가 (IMAGE_BUNDLE_CONTRACT v1)

osint_generator(영상 파이프라인)가 보고서 사진을 영상 photo 씬(풀블리드 + Ken Burns + 캡션/크레딧)으로 소비하는 계약(consumer v0.42.0)에 맞춰 producer emit 을 추가. 전부 **additive** — `schema_version` **1 유지**, 기존 번들(image_refs 빈 배열) 전부 유효.

- **`ReportBundle.images: list[BundleImage]` 신설** ([src/models.py](src/models.py)) — `{image_id, url, caption(≤60), credit, rights_status(cleared|needs_review|blocked), license, source_id, focus}`. `sections[].image_refs`(기존 필드)로 섹션↔사진 연결. 참조 무결성 가드(`_validate_refs_and_ids`)에 image_id unique + image_ref resolve 추가.
- **빌더 배선** ([src/handoff/bundle_builder.py](src/handoff/bundle_builder.py) `_build_images`) — `ComposedReport.hero_image` + `ComposedSection.images`(og:image 후보 중 composer 선택분) → `BundleImage[]`. url dedup(hero==섹션 사진 중복 방지), hero→첫 섹션 오프닝(발단) 삽입, caption ≤60 말줄임, `source_url`→`source_id` 역추적.
- **rights_status/license 판단** (`_image_rights`, 계약 §3.1-a) — 본 시스템은 봇 자체 사용 목적이라 출처표기(credit)로 저작권을 갈음한다(CLAUDE.md 'Report Images' 방침, 사용자 결정 2026-07-08). 정부 공식 배포(`*.go.kr`/`*.gov`/`korea.kr`)·보도자료 와이어 도메인 → `cleared`(license '공식 배포'), **credit 있는 사진 → `cleared`**(license '출처표기'), 둘 다 없으면 `needs_review`. 이때 cleared 는 "검증된 재사용 라이선스" 가 아니라 "출처표기 갈음 자체 사용" 을 뜻하며, 원 계약 §3.1 엄격 정의를 osint_generator 와 **양쪽 repo 동기화로 개정**.
- **계약 문서** — 신규 [docs/CONTRACTS/IMAGE_BUNDLE_CONTRACT.md](docs/CONTRACTS/IMAGE_BUNDLE_CONTRACT.md)(양쪽 repo 동기화 SSOT) + [report_bundle_v1.md §14](docs/CONTRACTS/report_bundle_v1.md) 참조 + 스키마 블록 + 예시(`report_bundle_v1.example.json`) images[] parity + [DATA_MODELS.md §5.5](docs/DATA_MODELS.md). 회귀 `tests/test_report_bundle.py` 3종(emit·dedup·권리·caption / 부재 byte-equal / 미해결 image_ref 거부).

## v8.3.4 — 보고서 완료 메시지에서 본문 .md 링크 제거 (HTML + 번들만 유지)

사용자 요청 — 보고서 발행 시 두 종류의 링크 묶음이 나가는데, 하나는 보고서 본문을 마크다운으로 변환한 `.md` 링크(`🤖 AI 전달용 (Markdown)` + `🤝 AI 직접 열람용 (GitHub raw): …md`), 다른 하나는 영상 제작용 `.bundle.json` 번들 링크(`📦 영상 제작용 번들` + `🔗 …bundle.json` + `🤝 …bundle.json`)다. 본문 `.md` 링크 묶음을 없애고 HTML 보고서 링크(`🔗 보고서 링크`)와 `.bundle.json` 번들만 남긴다. 대상은 자동 보고서 출력 3경로 — 대화형 `/analyze` ([src/telegram_bot.py](src/telegram_bot.py)) + 일일 브리핑 ([src/scheduler/daily_briefing.py](src/scheduler/daily_briefing.py)) + 장마감 브리핑 ([src/scheduler/market_briefing.py](src/scheduler/market_briefing.py)). 각 완료 메시지에서 `🤖 AI 전달용 (Markdown)` 줄과 `.md` GitHub raw 미러 줄(`_mirror_line`/`mirror_line`)을 제거, 미사용이 된 `md_url` 지역변수도 삭제. HTML 보고서 링크·검수 바이라인·`.bundle.json` 번들 메시지(파일 첨부 포함)는 불변. 수동 `/bundle` 명령도 불변.

## v8.3.3 — 르포 관계도 로고 직접 이미지 URL 지원 (CHART-AP-42 후속)

사용자 요청 — 삼성전자·SK하이닉스도 제대로 된 기업 로고를. 파비콘 폴백의 한계(탭 아이콘 ≠ 브랜드 로고)를 도메인 체인 강화로는 못 넘으므로, `logo` 필드가 https:// *직접 이미지 URL* 이면 파비콘 체인을 건너뛰고 그 이미지를 원형 코인으로 렌더 (위키미디어 공식 로고 파일 등 — 프리로드 성공 시에만, 실패 시 기존 fallback 불변). 삼성 워드마크처럼 가로로 긴 로고가 원형 crop 으로 글자 중간만 잘리지 않도록 로고는 contain(meet) fit, 사진·국기는 cover(slice) 유지. composer 프롬프트에 직접 URL 허용(실존 확인 시) 명시. 발행본은 VM 에서 위키피디아 API 로 공식 로고 URL 을 조회·검증해 소급 주입.

## v8.3.2 — 르포 관계도 정부 노드 로고 규칙 (CHART-AP-42 후속, 사용자 결정)

사용자 catch 2건 — ① 이재명 정부 노드에 korea.kr 로고(빨간 태극 정부상징)를 달았더니 "이게 뭐지?"(일반 독자 인지 불가), 청와대 상징이 맞다는 사용자 결정. ② 삼성전자·SK하이닉스 로고가 파비콘(탭 아이콘) 품질로 렌더돼 애매 — Clearbit 1차 소스 무응답 시 구글 파비콘 폴백의 한계. 대응: composer 프롬프트에 정부 노드 로고 규칙 신설 — 정부·행정부 노드는 최고 행정기관 도메인 (한국 정부·대통령실→president.go.kr 청와대 상징, 미국 행정부→whitehouse.gov), korea.kr 류 포털 도메인 금지, 국가 그 자체 노드는 logo 생략·flag 메인. 발행본은 payload 소급 패치(gov→president.go.kr, 파비콘 품질이 확인 안 되는 samsung/sk 는 logo 제거→태극기 메인 복귀) 후 재발행.

## v8.3.1 — 르포 관계도 결합 노드 금지 (CHART-AP-42 후속)

사용자 catch — "구글과 MS 도 동일해". "구글·MS" 처럼 두 주체를 한 노드로 묶으면 어느 쪽 로고도 달 수 없어 v8.2.19 의 로고 상시화가 구조적으로 막힌다. composer SYSTEM_PROMPT(스키마 라인) + `_REPORTAGE_BLOCK` 에 결합 노드 금지 규칙 추가 — 각각 노드로 분리하고 같은 role·진영(col)을 부여, 노드 2~12 한도가 차면 덜 중요한 쪽 제외. 발행본 2건은 payload 소급 패치(hyperscaler → google/msft 분리 + logo 주입) 후 `--rerender-only` 재발행.

## v8.3.0 — 일반 보고서 차트 다양성 회복 4종 세트

사용자 catch — "일반 보고서 차트 유형이 점점 제한적으로 변한다". 실발행 243건 분석으로 정량 확인: event 보고서 line 비중 5월 35.4% → 6월 53.2%(그중 81%가 30행+ 시장 일봉), 보고서당 distinct type 2.9 정체, 6월에 heatmap/range_bar/lollipop/area/forecast/stacked/dual_line/choropleth 8종 0회. 구조 원인 = ⓐ 자동 주입 시장 가격 차트가 다양성 쿼터 선점 ⓑ 강제 장치 전무(V5 게이트 flag OFF·starvation 경보 bot.log 사장·프롬프트 "권장 강제X") ⓒ 조건 엄격 type 의 리스크 회피 후퇴. 대응 4종:

1. **서사/시장 분리 + 필수 하한** — composer SYSTEM_PROMPT 반-편향 가드 격상: 시장 가격 차트(available_time_series 기반)는 다양성 계산에서 제외, *서사 차트* 기준 서로 다른 type standard ≥3 / deep ≥4 필수(권장 문구 폐기), line 은 1번 분기 마지막 수단 명시, forecast/heatmap 트리거 어휘 보강.
2. **자기교정 루프** (사용자 결정 — 관리자 알림 대신 봇이 스스로 빈도 회복) — `usage_log.composer_rebalance_hint` 신설: 최근 30건에서 0회(starved)+희귀(rare) *서사* type(주입 전용 candle/combo_candle/iv_skew/indicator·르포 전용 stakeholder_map·map 채널 제외)을 최대 6개 반환, orchestrator 가 composer 프롬프트에 `_CHART_REBALANCE_BLOCK`(조건 맞을 때만 우선 채택, 억지 사용 금지) 주입. 표본 <10건·힌트 0개면 프롬프트 byte-equal, 르포 미주입.
3. **다양성 쿼터 게이트 production 배선** — `deterministic_gate.check_chart_type_monotony` public 진입점 신설(sections-shape 평탄화 포함 — 기존 private 는 빈 top-level charts 에서 sections 폴백 불달 결함), orchestrator 가 V5 게이트와 독립적으로 매 보고서 log-only 호출. 발행 불차단, 강제 승격은 관찰 후 사용자 게이트.
4. **시계열 행수 상한** — `_DENSIFY_MAX_ROWS=260`(≈1년 거래일) + `_downsample_rows`(균등 스트라이드, 마지막 봉 보존)를 `_densify_ts_charts` 치환분과 `_build_ts_chart` 주입분에 공통 적용. 3년 751행 일봉이 통째로 실리던 발행 사례 4건 차단.

회귀 `tests/regression/test_chart_diversity.py` 12종 (하한 문구/힌트 산출·주입·byte-equal/게이트 public/다운샘플·densify 상한).

ops — VM-AP-11 등록: VM 이 feature 브랜치에 checkout 된 채 §1 재배포 시 pull 이 no-op 되어 옛 버전 재기동 (2026-07-02 실제 발생). §1 Stage 2 에 main 브랜치 가드 추가. SSOT [docs/VM_DEPLOY_PLAYBOOK.md §2](docs/VM_DEPLOY_PLAYBOOK.md).

## v8.2.19 — 르포 관계도 기업 로고 상시화 (CHART-AP-42 후속)

사용자 지적 — "기업 로고도 다 보이게 해야 하는 거 아니야?". v8.2.18 은 logo 를 "확실할 때만" 선택 사항으로 뒀고, 단일 소스(Google favicon)는 미등록 도메인에도 200 + 16px 기본 지구본을 반환해 가짜 아이콘이 박힐 위험이 있었다. Fix ① composer 프롬프트(스키마 라인 + `_REPORTAGE_BLOCK`) — 기업·정부기관·국제기구·언론사 노드는 공식 도메인이 잘 알려져 있으면 logo 를 *반드시* 채우도록 격상 (도메인 창작은 여전히 금지 — fallback 안전망 전제). ② 렌더러 로고 소스 2단 체인 — Clearbit 브랜드 로고(고품질, 미등록 404→onerror 체인 진행) → Google favicon (커버리지 최광, `naturalWidth < minPx(24)` 로 기본 지구본 판별·거부). 프리로드 성공분만 오버레이하는 v8.2.18 fallback 구조 불변. Playwright 라우트 인터셉션으로 4경로(클리어빗 성공/favicon 수락/기본 지구본 거부/전부 실패) 검증.

## v8.2.18 — 르포 관계도 완성도 격상: 노드 자산 + 장애물 인지형 라우팅 (CHART-AP-42/43)

사용자 catch — 르포 관계도의 완성도 종합 지적: 로고를 붙일 수 있는 주체(정부기관·국가·기업)엔 대표 로고, 인물엔 흑백 사진을 넣고, 엣지가 노드에 가려지거나 서로 겹치지 않아야 하며, 엣지 라벨 플레이트가 노드를 가리거나 선 교차점에 앉지 않아야 한다.

**노드 자산 (CHART-AP-42)** — 실발행 payload 가 `flag:"KR"` 을 emit 했는데 인라인 국기 6종(US/TW/CN/JP/UA/RU) 화이트리스트 밖이라 태극기가 이니셜로 silent 강등되던 결함 포함. Fix: ① `flag` ISO alpha-2 전 국가 지원 — 인라인 sprite 에 KR 태극기 추가(7종), 그 외 코드는 flagcdn CDN 을 `Image()` 프리로드해 성공 시에만 둥근 국기 오버레이. ② 신규 `logo`(기관·기업 공식 도메인, 예 "samsung.com") → favicon 서비스 원형 로고 코인. ③ 신규 `photo`(인물 사진 URL) → `sm-gray`(saturate 0) 흑백 원형 렌더. 우선순위 photo→logo→flag, 실패·오프라인이면 국기/실루엣/이니셜 base 유지(빈 슬롯 없음). 사진·로고 노드의 flag 는 국적 배지로 자동 강등. composer SYSTEM_PROMPT + `_REPORTAGE_BLOCK` 에 "공식 도메인·실존 확인 URL 만, 추측 금지" 지시, `StakeholderNode` 에 logo/photo 필드(관용).

**엣지 라우팅·라벨 (CHART-AP-43)** — v8.2.17 레인 라우터 이후에도 ① 교차(좌↔우) 엣지의 수평 구간이 가운데 칼럼 카드 밴드를 관통(엣지가 카드 아래 레이어라 가려짐) ② 같은 칼럼 skip 엣지가 사이 카드를 수직 관통 ③ 라벨이 다른 엣지 선·교차점 위에 안착. Fix: 장애물 인지형 직교 라우터 — 교차 엣지는 가운데 칼럼 행 사이 빈 수평 코리더(밴드 내 14px 분산 + 타 엣지 스텁 y ±8px 회피)로 우회, 같은 칼럼 skip 은 바깥 세로 레인으로 우회, 세로 구간은 채널 4개(바깥-좌/gapA/gapB/바깥-우)에 레인 분배 — 평행(공선) 겹침 0, 남는 교차는 직각 crossing 뿐. 라벨 장애물에 카드·기존 라벨 + 다른 엣지 전 세그먼트 포함, 앵커는 자기 선의 가장 긴 구간(교차 엣지는 코리더) 중점 + 자기 선 방향 슬라이드 우선. `smRoute` 폐기, `smRouteLane` 을 waypoint 폴리라인 + 라운딩으로 일반화. 데이터 계약·가드·registry 불변. 발행본은 재배포 후 `patch_report.py <id> --rerender-only` 로 URL 동일 적용. SSOT: CHART-AP-42/43.

## v8.2.17 — 르포 관계도 교차 엣지 세로 레인 분리 (CHART-AP-41)

사용자 catch(CHART-AP-40 라벨 픽스 후 후속) — 라벨 겹침은 사라졌으나 **선 자체가 뭉쳐**, 특히 가운데 칼럼(`이재명 정부`/`김용범`/`국민성장펀드`) → 오른쪽 칼럼(`삼성전자`/`SK하이닉스`) 교차 엣지의 **세로 구간이 같은 x 에 포개져** 어느 선이 어디로 가는지 구분 불가. 근원은 `smRoute` 가 모든 교차 엣지를 수평 중점(`mx`) 한 곳에서 꺾던 것. Fix — `drawStakeholderMap` 에 결정적 레인 라우터 추가: 칼럼 사이 gap 을 통로로 보고 교차 엣지를 대상 칼럼 왼쪽 gap 에 배정(col0→col2 는 오른쪽 gap 에서 하강해 카드 통로 회피), 같은 gap 의 엣지를 y 순 정렬 후 gap 폭 안에서 균등 분배한 레인 x(`bendX`)로 꺾어 세로 구간을 서로 벌린다. 같은 칼럼 수직 체인은 직선 유지. 칼럼 간격 `GAP 128→152`·세로 간격 `VSP 120→140` 확대 + 교차 엣지 라벨을 레인 위에 올려 선과 정렬. 데이터 계약·가드·registry 불변, 순수 렌더. 발행본은 재배포 후 `--rerender-only` 로 URL 동일 적용. SSOT: CHART-AP-41.

## v8.2.16 — 르포 관계도 엣지 라벨 겹침 차단 + 선 스타일 범례 (CHART-AP-40)

사용자 catch — 르포 행위자 관계도(`stakeholder_map`)에서 관계 라벨 배지(`○ 설계` / `90만장` / `● 인프라` 등)가 가운데 칼럼 카드(`이재명 정부` / `김O씨`) 위에 찍혀 그 카드의 역할 텍스트(`자금·입법 설계` / `금○○○ 현직`)를 가리고, cross 엣지 라벨끼리도 같은 중앙 지점에 몰려 글자가 뭉개졌다. 근원은 `drawStakeholderMap` 이 엣지 라벨을 양 끝 부착점의 기하학적 중점에 그대로 찍는데, col0↔col2 를 가로지르는 엣지의 중점이 정확히 가운데 칼럼 카드에 떨어지고 카드 충돌 회피가 전무했던 것. Fix — 라벨 배치에 결정적 de-confliction 패스 추가(카드 + 이미 배치한 라벨을 AABB 장애물로 보고 중점에서 수직 우선·이어 수평으로 빈 자리로 밀어내고, 8px 이상 밀리면 중점→라벨 연결선을 남겨 association 보존 — slope CHART-AP-26 dodge 패턴 상속) + 선 스타일 범례(실제 등장한 유형만, 2종 이상일 때 — `→ 영향·주도` / `● 협력·자금` / `✕ 대립` / `○ 연관`) 자동 표기로 두 시각 언어(자본 흐름 vs 영향·공급 관계) 해독 단서 제공. 데이터 계약(nodes/edges)·가드·registry 불변, 순수 렌더 변경(일반 보고서 무영향). 발행본은 `git pull`+재배포 후 `patch_report.py <id> --rerender-only` 로 URL 동일 적용. SSOT: [docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) CHART-AP-40.

## v8.2.15 — 르포 데스크탑 우측 끝단 정렬 (본문 ↔ 차트·지도·용어풀이)

사용자 catch — 르포를 데스크탑으로 보면 차트·지도·용어풀이는 콘텐츠 열(`.rep-wrap`, ~768px)을 꽉 채우는데 본문(`.rep-prose`)만 `max-width:66ch`(~580px)로 좁아, 우측 끝단이 시각물보다 안쪽에서 줄바뀜 → 오른쪽 가장자리 어긋남. 모바일은 뷰포트가 더 좁아 둘 다 가용폭을 채우므로 무증상. 본문의 66ch 캡을 제거해 모든 블록을 동일한 한 열 폭으로 통일(좌·우 끝단 일치, 시각물은 full-size 유지). 일반 보고서(`freeform_essay.html`)·기존 테마 무영향.

## v8.2.14 — 지구본 초기 확대 기본 +1.5스텝 (전역)

사용자 요청 — 자동 격상된 지구본이 반구 전체(k=1)로 시작해 너무 멀어 보임. `maps.js:renderGlobe` 의 초기 스케일 `k0` 에 기본 부스트를 적용: 확대 버튼 1스텝=×1.4 이므로 1.5스텝=×1.4^1.5≈×1.66 만큼 더 당겨서 시작(`GLOBE_INITIAL_ZOOM_BOOST`). 대륙 간 무대가 화면을 더 채운다. 드래그 회전·휠 확대·reset 동작 불변(reset 은 부스트된 초기 뷰로 복귀). maps.js 는 보고서 HTML 에 인라인되므로 재렌더(`--rerender-only`)·신규 보고서부터 반영.

## v8.2.13 — 대륙 간 지도 지구본 자동 격상 (CHART-AP-39) + patch `--map-projection`

사용자 catch — 환태평양 메모리 공급망(한국·미국·중국·대만) 보고서의 첫 장면 지도가 이상하게 나옴: composer 가 대륙 간 스케일(경도 span 154°) 토픽에 평면 메르카토르를 emit → 태평양 한가운데 중심으로 빈 검은 바다 + 우측 구석에 북미만 걸리고 아시아 마커가 화면 밖으로 밀림.

- **결정적 안전망 — `_promote_intercontinental_globe` (orchestrator, 디폴트 ON)**: composer 가 projection 을 지정 안 한 평면 지도에서 마커 경도 span(자오선 wrap 보정)을 계산해 대륙 간 임계(≥100°)면 `projection="globe"` 로 자동 격상. 정사영 지구본은 드래그 회전·휠 확대되는 '움직이는' 지도이고 arcs 가 대권 최단경로로 그려져 대륙 간 흐름이 직관적. 좁은 권역(지역 사건)·composer 가 projection 명시한 경우는 no-op(평면 유지, byte-equal).
- **발행본 핫픽스 — `patch_report.py --map-projection {globe,flat}`**: 평면으로 이상하게 나온 발행본을 LLM 0·URL 동일로 지구본 전환(또는 평면 복귀). center/zoom/markers/arcs 등 나머지 어휘는 그대로 유지(renderGlobe 가 평면과 동일 계약 소비).
- 회귀 SSOT: [docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) CHART-AP-39.

## v8.2.12 — 관계도 완성도 개선 (텍스트 잘림 말줄임 + role 길이 가이드)

사용자 catch — 주입된 관계도의 완성도가 떨어짐: ① node role 텍스트가 카드 폭(22자)에서 *말줄임 없이 뚝 잘림*("100만→7", "스파이더웹·4"), ② 긴 role + 좌우 cross 엣지가 가운데 노드를 관통해 겹침.

- **렌더러(`drawStakeholderMap`)**: label/role 클립에 말줄임표(`smClip`) — 단어가 끊긴 듯 보이는 저하 방지(텍스트만, 레이아웃 무변).
- **composer 프롬프트(`_REPORTAGE_BLOCK`)**: node `role` ≤16자·edge `label` ≤6자, 긴 설명·수치는 본문에, 좌우 cross 엣지는 핵심 1~2개만(가운데 관통 겹침 방지) 명문화.
- 발행본은 `--remove-chart` + `--add-stakeholder-map` 로 짧은 role·최소 cross 엣지 데이터로 재주입해 즉시 개선(렌더러 무관).

## v8.2.11 — patch_report `--add-stakeholder-map` (발행본 관계도 수술적 보완)

CHART-AP-38(v8.2.10)로 누락됐던 관계도를 *전체 재작성 없이* 발행본에 주입하는 patch_report 옵션. 사용자 요청 — 본문엔 '(아래 관계도)' 가 있는데 관계도가 빠진 발행본을 보완.

- `scripts/patch_report.py --add-stakeholder-map 'IDX:{차트 JSON}'` — 지정 섹션(0-based) charts 에 stakeholder_map 1개 주입. data 가 `validate_chart_data` 가드를 통과해야만 주입(통과 못하면 렌더 단계서 또 drop 되므로 거부). JSON 안의 ':' 때문에 첫 ':' 로만 split. LLM 0, URL 보존, revision +1.
- `--recompose`(전체 LLM 재작성) 대비 기존 본문·차트를 보존하는 surgical 경로.

## v8.2.10 — 르포 관계도 100% silent drop 근본 수정 (validate_chart_data 분기 누락, CHART-AP-38)

사용자 "왜 관계도가 제대로 안 나오지" 점검 요청 → **진짜 근본 원인 발견.** v8.2.9 의 프롬프트 강제·dangling 제거는 *증상* 대응이었고, 관계도(stakeholder_map)가 v8.0.0 이래 *한 번도 안 떴던* 진짜 이유는 따로 있었다: `validate_chart_data` 의 디스패치 사슬에 **stakeholder_map 분기가 누락**돼, dict `{nodes, edges}` 데이터가 맨 끝 list[dict] `else` 로 떨어져 `(False, "stakeholder_map 는 list[dict] 형식 필요")` → composer 가 정상 emit 해도 `_drop_invalid_charts` 가 **100% silent drop**. 가드·렌더러·레지스트리는 다 있었는데 *디스패치 한 줄*이 빠져 도달 불가였다.

- **Fix** — `validate_chart_data` 에 `elif chart_type == "stakeholder_map":` 분기 추가(sankey 동형, dict→`guard(**data)`). 이제 유효 관계도가 검증 통과 → `drawStakeholderMap` 으로 렌더된다.
- **일반화 회귀** — `_TYPE_TO_GUARD` 의 dict-데이터 type 들이 유효 최소 데이터로 validate_chart_data 를 통과하는지 강제(`test_every_dict_guard_type_has_dispatch_branch`). 같은 부류(분기 누락→조용한 100% drop)의 재발 차단. CHART-AP-38 신설.
- 효과: v8.2.9 의 dangling 안전망은 *그물*로 남되, 정상 경로에서 관계도가 실제로 떠 안전망이 발동할 일이 거의 없어진다.

## v8.2.9 — 깨진 시각물 약속 차단 (본문이 가리킨 관계도/지도 미표시, WRITE-AP-26)

사용자 catch — v8.2.8 르포(`analysis_20260627_151401`)에서 본문이 "(아래 관계도)" / "(아래 지도)"로 시각물을 가리키는데 그 자리에 아무것도 안 보임. 원인: ① composer 가 '아래 관계도'를 쓰면서 그 섹션에 stakeholder_map 을 emit 안 함(2막 일곱 행위자), ② 지도(embedded_map)는 보고서 상단 1회 렌더인데 본문이 '아래'로 가리켜 위치 불일치. (마지막 "첫째/둘째" 종결은 정상 결론 — 에필로그 제거 설계, 미완성 아님.)

- **프롬프트 강제** — `_REPORTAGE_BLOCK` 에 *시각물-본문 일치 규칙*: '아래 관계도/그래프/도표' 를 쓰면 그 시각물을 같은 섹션 charts(지도는 embedded_map)에 반드시 emit, 안 할 거면 가리키지 말 것(깨진 약속 금지). 2막 stakeholder_map 필수. 지도는 상단 1회 렌더이므로 위치-비의존 표현('지도에서 보듯') 사용.
- **결정적 안전망** — orchestrator `_reconcile_visual_references`(르포 전용): 충족 안 된 괄호 지시어를 본문에서 제거(관계도→stakeholder_map/network, 그래프/도표→차트, 지도→embedded_map 존재 여부로 판정). 시각물을 지어내진 않음. 일반 보고서는 미적용 byte-equal.
- 회귀 `tests/regression/test_visual_reference_reconcile.py` 6종. WRITE-AP-26 신설.

## v8.2.8 — 편집장 CLI 출력 head-loss 근본 수정 (json envelope 캡처, WRITE-AP-25)

v8.2.7 직후 VM bot.log 정밀 분석으로 **진짜 근본 원인** 확인 — v8.2.6 르포 588자 미파싱은 모델 산문 이탈이 아니라, 편집장 CLI `--output-format text` 캡처가 *긴 응답에서 stdout 머리(앞부분 — 여는 `{`·headline·앞 섹션)를 잃는* systemic 결함이었다. 캡처된 raw 가 본문 *중간*부터 시작(`니다.\n\n호황의 끝엔…` + 꼬리의 `"video"` 객체)해 파싱·절단복구·head-loss 복구가 전부 실패 → minimal fallback. bot.log 상 2026-06-02부터 수개월 누적(3,860 / 6,022 / 15,459자 등 다양한 길이의 꼬리만 생존), 보고서 종류 무관. v8.2.6 가 르포 출력을 최장으로 늘리며 *꼬리마저 588자로 짧아져* 복구 불능이 되어 표면화.

- **근본 수정** — 편집장 CLI 캡처를 `--output-format json` 단일 envelope(`{...,"result":"<본문>"}`)로 전환. 텍스트 렌더링 경로를 우회해 전체 본문을 머리 손실 없이 추출(`narrative_composer._extract_cli_result`). 완결 envelope→`result` 추출 / 절단 envelope(타임아웃)→정규식+best-effort 언이스케이프로 부분 살리기 보존 / envelope 아니면 raw 그대로(graceful).
- **킬 스위치** — `Config.cli_json_output` (env `V8_CLI_JSON_OUTPUT`) 기본 ON. 구버전 CLI 등 문제 시 `V8_CLI_JSON_OUTPUT=0` 로 즉시 text 캡처 복귀(byte-equal).
- 적용 범위는 편집장(가장 긴 출력 → 유일하게 head-loss 관측)으로 한정. context_analyst/report_synthesizer 는 추후 필요 시 확장.
- 회귀 `tests/regression/test_cli_json_capture.py` (envelope 추출 / escape·unicode / 절단 부분복구 / 비-envelope passthrough / 플래그 기본 ON).
- 운영: VM 재배포 전 `claude -p "ping" --output-format json` 으로 envelope 형식 1회 확인 권장. WRITE-AP-25 추가 회귀로 등재.

## v8.2.7 — 르포 생성 안정화 (모델 안전망 + JSON 계약 스코핑, WRITE-AP-25 계열)

사용자 catch — v8.2.6 르포 1건(`analysis_20260627_123516`)이 "생성되다 멈춤" 증상으로 1-섹션 열화본 발행. 원인은 타임아웃이 아니라, 편집장(Opus 4.8)이 **클린 종료인데 raw 588자짜리 미파싱 응답**만 내놓아 절단·head-loss 복구가 모두 실패 → `compose_unified` None → minimal fallback. v8.2.6 이 르포 분량을 강하게 밀어붙인 직후라, '길어야 한다' 압박이 모델을 JSON 계약 밖으로 흘렸을 개연성이 1차 용의.

- **모델 안전망** — 르포 전용 모델(4.8)로 작성·재시도가 *모두* 파싱 불가/실패면, minimal fallback 으로 떨어지기 전에 검증된 안정 모델(`COMPOSER_MODEL`=4.7)로 *마지막 한 번* 더 작성한다 (`narrative_composer.compose_unified`). 일반 보고서(`use_model==COMPOSER_MODEL`)는 분기 미진입 = byte-equal.
- **프롬프트 계약 스코핑** — `_REPORTAGE_BLOCK` 분량 강령에 "모든 분량은 *JSON `sections` 배열 안* 에서 늘린다 · 산문을 JSON 밖으로 꺼내거나 응답을 설명·서론·메타 코멘트로 시작 금지 · 응답은 여전히 `{` 로 여는 단일 JSON 객체" 명문화. 강한 길이 압박이 출력 계약을 잊게 하는 drift 차단.
- 회귀 `tests/regression/test_reportage_model_fallback.py` (3종 — 4.7 폴백 성공 / 일반 보고서 폴백 미진입 byte-equal / JSON 계약 스코핑 marker). WRITE-AP-25 문서에 추가 회귀로 등재.
- 운영 진단: 4.8 미파싱 반복 시 bot.log `parse returned None ... head=` 로 실제 응답 머리 확인 (모델 산문 이탈 vs CLI 단문 에러 구분).

## v8.2.6 — 르포 분량 ~2배 확장 (탐사 페르소나 분량/깊이 강령)

사용자 요청 — 르포(reportage) 형식 보고서가 너무 짧다, 지금보다 두 배 정도로 늘려 달라. 원인은 코드가 아니라 *프롬프트 페르소나* 였다. composer `_REPORTAGE_BLOCK` 의 '담백하게' 지시가 *짧게* 로 오독돼, 5막을 각 1섹션·단문단으로 압축한 채 끝나던 것. deep 모드 출력 한도(48K)는 이미 충분해 모델에 *더 깊이 파라* 고 지시하는 것만으로 분량이 따라온다.

- composer `_REPORTAGE_BLOCK` 에 **[분량과 깊이 강령]** 신설: ① 5막을 각 2섹션 이상으로 펼쳐 *8~12 섹션* 목표 ② 섹션당 *3~6 문단* 으로 전개 ③ 탐사 3도구(묻힌 디테일·점 잇기·시나리오 추론)를 *각 섹션마다* 가동.
- '담백함 = *무장식*(거창한 수사·장식 컴포넌트 없음)이지 *짧음*이 아님' 을 명문화. 짧은 문단 규칙(≤5문장)은 유지하되 문단 *수* 는 넉넉히.
- 분량은 *새 정보·새 연결·새 통찰* 에서만 — 동어반복·공허한 수사로 채우는 *물타기* 금지("길되 밀도 있게").
- standard(일반 보고서)는 byte-equal 무변경. 르포 트리거 없는 보고서엔 영향 0.
- 회귀 `tests/regression/test_reportage_format.py::test_reportage_block_has_length_depth_mandate`.

## v8.2.5 — 옵션 스큐 차트 2단 개편 (가격 패널 + 날짜 화살표, 점 표식 제거)

사용자 요청 — 장마감 브리핑의 옵션 스큐 차트 위에 *같은 유형의 옵션 가격 차트* 를 얹고, 차트에 날짜 화살표를 두어 날짜별 스큐·가격을 쉽게 보게 하고, 선 위의 동그란 점 표식을 없애 달라. 기존 다일자 페이드 오버레이가 곡선 수십 개로 겹쳐 보이던 문제도 함께 해소.

- **2단 패널** (`src/templates/static/charts.js` `drawIvSkew`) — 하나의 `iv_skew` 카드가 **상단 = 행사가별 옵션 가격(프리미엄)**, **하단 = 같은 행사가의 IV 스큐** 두 패널로 분리. 두 패널은 행사가 x축을 공유한다(가격↔변동성 정렬 비교).
- **날짜 화살표(◀ ▶)** — 우상단 컨트롤로 최근 N영업일을 *하루씩* 전환(`날짜 (i/N)` 표기). 기존의 "오늘 진하게·과거 옅게" 다일자 동시 오버레이(스파게티)를 폐기 — 한 번에 한 날짜만 또렷하게. 날짜가 1개면 화살표 없이 정적.
- **점 표식 제거** — 선 위 per-point 동그라미 삭제, 선만. 범례 점(풋/콜) 2개만 유지.
- **옵션 가격 데이터 배선** — 스큐 점에 `premium` 동봉(`src/tools/derivatives_fetcher.py` `build_derivatives_charts` / `_skew_points_for_expiry` / `augment_skew_history`) + 일별 캐시 `premium` 컬럼 추가(`src/tools/skew_cache.py`, 구 캐시는 `ALTER TABLE` 으로 nullable 추가 — 마이그레이션 전 적재분은 가격 패널 graceful skip).
- **하위 호환** — `premium` 없는 구 `iv_skew` payload 는 스큐 단일 패널로 그대로 렌더(byte-equal 의도). 회귀 `tests/test_skew_cache.py`(premium roundtrip + legacy NULL) / `tests/test_derivatives_fetcher.py`(skew 점 premium 동봉). 샘플 `samples/market_briefing_charts_v7_9_9.html` 갱신.

---

## v8.2.4 — 보고서 "생성되다 만" 채로 무경고 발행 차단 (WRITE-AP-25)

사용자 보고 — 보고서들이 "자꾸 생성되다 만다". 2026-06-25 마이크론 deep 보고서 2건(`analysis_20260625_081213` / `…_061939`)이 같은 주제로 2시간 간격 두 번 모두, 본문 `요약` 섹션 1개뿐인 **minimal fallback** 으로 발행됐는데 텔레그램엔 "✅ 분석 완료" + 정상 URL 이 가서 열어봐야만 미완성을 알았다.

- **근본 원인**: 두 보고서 total 1666s/1517s — 편집장(NarrativeComposer)이 deep CLI 타임아웃(900s)에 걸려 죽었고, `claude -p --output-format text` 는 완료 전까지 stdout 에 스트리밍하지 않아 kill 시점 임시파일이 비어 **살릴 부분 출력이 없음** → `compose_unified` 가 `None` 반환 → orchestrator 가 `context.summary` 기반 1-섹션 폴백을 *그대로* 렌더·배포. 실패임을 알리는 신호가 본문 깊숙한 `confidence_summary` 한 줄뿐이라 텔레그램·헤더 어디에도 표시 없음. deep 가 v5.8.2 부터 기본 모드라 무겁고 긴 주제는 매번 이 경로로 떨어짐.
- **구조적 열화 플래그** (`src/models.py`) — `ComposedReport.degraded: bool` + `degradation_reason: str`. minimal fallback / 타임아웃 부분 살림 / 절단 JSON 복구 / head-loss 복구 *모든* 경로가 `degraded=True` + 사람-읽기 사유 세팅. default False 라 정상 보고서엔 영향 0.
- **실패 원인 표면화** (`src/agents/narrative_composer.py`) — `_last_failure_reason` 가 타임아웃/파싱불가/예외 사유를 한 줄로 적립 → orchestrator 가 폴백의 `degradation_reason` 으로 노출. critic 루프가 보고서를 교체해도 플래그 보존(`src/orchestrator.py`).
- **텔레그램 무경고 금지** (`src/telegram_bot.py`) — 열화면 "✅ 분석 완료" 대신 **"⚠️ 보고서가 끝까지 생성되지 못했습니다 — <사유>. 다시 요청하거나 '짧게' 로 재시도"** + 링크 머리표 `⚠️ 미완성`.
- **보고서 헤더 배너** — `freeform_essay.html` / `reportage.html` 가 `composed.degraded` 면 붉은 경고 배너 렌더. URL 을 여는 누구나 미완성 인지.
- **원인 완화** — deep CLI 타임아웃 900→1500s 상향. 무겁고 긴 deep 보고서가 한도 안에 완결되도록. (스트리밍 살림 `--output-format stream-json` 전환은 후속 검토.)
- 회귀 `tests/regression/test_degraded_report.py` (절단 복구·head-loss·정상 응답의 degraded 플래그 고정). 정상 보고서·르포 byte-equal 보존(`test_reportage_format.py` 19/19).

> ⚠️ 운영 — VM `git pull` + 재배포 후 적용. ⚠️ 가 또 뜨면 주제가 너무 무거운 것 — '짧게' 를 붙이거나 분할 요청. 1500s 로도 부족하면 timeout 상향 또는 stream-json 살림 도입 검토.

## v8.2.3 — 르포 표시 라벨 일치 (Opus 4.8 정상 호출 + 텔레그램·바이라인도 4.8)

v8.2.2 직후 사용자 보고 — 르포 보고서 실제 호출은 `claude-opus-4-8` 로 정상 동작 (`bot.log` 의 `Starting CLI call (claude-opus-4-8, …)` 확인) 인데, 텔레그램 진행 메시지엔 **`편집장 (Opus 4.7): …`** 이 박혀 사용자가 4.7 으로 돌아간 줄 오인. 표시 회귀 — 두 곳에 모델 라벨이 하드코딩.

- `src/orchestrator.py:1817` — 진행 알림 문자열이 `"편집장 (Opus 4.7): …"` 하드코딩. 르포여도 4.7 라벨. 동적 분기로 교체: `report_format == "reportage" → "Opus 4.8"`, 그 외 `"Opus 4.7"`.
- `src/orchestrator.py:2011` — `build_verification_byline` 호출에 `self.narrative_composer.COMPOSER_MODEL` (4.7 고정) 을 넘기던 것을 `_model_for_format(request.report_format)` 로 교체. 르포 발행 푸터 바이라인이 `Claude Opus 4.8 작성` 으로 정확히 표기됨. `_pretty_writer` 정규식은 `opus-4-8` → `Claude Opus 4.8` 매핑 OK (변경 불요).
- 회귀 `test_reportage_format.py` +2: `_pretty_writer` 4.8 매핑 + source 가드(`'편집장 (Opus 4.7):'` 하드코딩 잔재 없음 + 동적 분기 + byline `_model_for_format` 사용).
- byte-equal: `report_format != "reportage"` 인 모든 보고서는 라벨/바이라인 모두 v8.2.2 와 동일(4.7). 르포 트리거 없는 경로에 영향 0.

## v8.2.2 — 르포 작성 모델 Opus 4.8 격상 (일반 보고서는 4.7 유지)

르포(`report_format=reportage`)는 탐사 기자 페르소나·점잇기·시나리오 추론 등 *더 높은 추론*을 요구하므로 작성 모델을 한 단계 위(Opus 4.8)로 올림. 사용자 요청.

- **format 별 composer 모델** (`src/agents/narrative_composer.py`) — `COMPOSER_MODEL_REPORTAGE = "claude-opus-4-8"` 신설 + `_model_for_format(report_format)` 헬퍼. 르포 → 4.8, 그 외 → 기존 `COMPOSER_MODEL`(4.7). `compose_unified` (주 작성) + `revise_for_facts` (팩트 보완 패스) 둘 다 르포면 4.8 사용 — 페르소나·품질 일관.
- **모델 채널** — `_call_cli`/`_call_api` 에 `model: str | None = None` 파라미터 추가(미지정 시 4.7 → 기존 경로 byte-equal). `critic_loop` 의 Reviser Protocol + `NarrativeComposerReviser` + `CriticLoop.run` 이 `report_format` 을 reviser 까지 전달(르포 보완도 4.8).
- **byte-equal 보존** — `report_format != "reportage"` 인 모든 보고서는 모델·payload·프롬프트 전부 v8.2.1 과 동일(4.7). 르포 트리거 없는 경로에 영향 0.
- 회귀 `test_reportage_format.py` +3 (르포→4.8 / 일반→4.7 / reviser report_format 전달), `test_codex_loop.py` StubReviser 시그니처 갱신.

> ⚠️ 운영 — 4.8 모델 가용성은 구독 플랜·CLI 버전에 따름. 배포 후 르포 한 건 e2e 로 `--model claude-opus-4-8` 정상 응답 확인 권장(미지원 시 graceful 하지 않을 수 있음 — 그 경우 `COMPOSER_MODEL_REPORTAGE` 를 가용 ID 로 조정).

## v8.2.1 — CLI 호출 복원력 — 일시적 과부하(529)에 보고서가 죽지 않게

2026-06-24 실연동 사고 수정. context_analyst 가 Anthropic 서버 과부하(HTTP 529 Overloaded) 한 번에 보고서 전체가 `❌ 분석 실패: unknown error` 로 떨어짐. 코드·인증·설정·v8.2.0 무관한 *일시적 서버측* 장애였는데 봇이 복구 없이 전체 실패로 처리한 게 결함.

- **일시 에러 재시도** (`src/agents/base.py`) — `_analyze_cli` 를 재시도 루프로. 529/429/5xx/timeout/connection-reset 등 일시 마커는 최대 3회(backoff 0/4/8s) 재시도, 비일시(인증·인자 오류)는 즉시 fast-fail. NarrativeComposer 는 이미 자체 재시도가 있었고(별도 경로), 이번에 context_analyst(및 BaseAgent CLI 전 경로)에 동급 복원력 부여.
- **stdout 에러 감지** — CLI v2(2.1.85)는 API 에러를 *stdout* 에 (`API Error: 529 …`) 내보내고 종종 exit 0 으로 끝낸다. 봇은 stderr 만 읽어 `unknown error` 로 새 버렸음 — 이제 stdout 의 에러 마커도 함께 판정해 *진짜* 메시지를 로그·예외에 남긴다.
- **중립 cwd 로 CLAUDE.md 자동로드 차단** — CLI v2 는 `-p` 모드에서도 cwd 의 `CLAUDE.md` 를 컨텍스트에 자동 적재한다. 봇 repo 의 54KB 운영문서(`claude doctor` 가 "Large CLAUDE.md > 40,000" 경고)는 뉴스 분석과 무관한데 매 호출 ~45K 토큰을 먹고 과부하 노출만 키웠다. subprocess 를 빈 임시 디렉터리에서 실행해 자동로드를 끊음(WebFetch/WebSearch 만 쓰므로 cwd 무관·안전).
- **타임아웃 가드** — 단일 CLI 호출 300s 상한(`asyncio.wait_for`). 초과 시 hang 대신 transient 로 분류해 재시도.
- 회귀 `tests/regression/test_cli_resilience.py` (8): 재시도/fast-fail/한도소진-진짜에러/stdout-529-감지/clean-경로/중립-cwd. context_analyst 본문·프롬프트·출력 무변경 — *호출 복원력만* 추가.

## v8.2.0 — 르포 탐사 기자 페르소나 — 단순 사실 나열 금지, connecting dots + 시나리오 추론 허용

르포(`report_format=reportage`)의 본문 페르소나를 *탐사 기자(investigative reporter)* 로 강화한 릴리스. 사용자 요청 — \"기사 나열이라면 일반 보고서와 다를 게 없다. 좀 더 깊은 정보를 탐구하고, 거짓말은 아니되 약간 무리한 추측 기반의 시나리오까지 언급할 수 있는 페르소나.\"

- **세 가지 도구 (composer `_REPORTAGE_BLOCK` 강화)** — ① **묻힌 디테일 들춰내기**: 출처들 안에 있지만 메인 헤드라인엔 안 잡힌 작은 사실(각주·인터뷰 곁가지·수치 단위·시점 일치)을 끌어올린다. ② **Connecting dots(점 잇기)**: 여러 출처에 흩어진 사실 2~5개를 *묶어* 전체 그림을 그린다 (\"A 와 B 와 C 를 이으면 D 가 보인다\" 식). 각 점은 입력 사실, 묶음은 일반 보도엔 없는 통찰. ③ **시나리오 추론**: 표면 사실에서 한 발 더 들어간 *그럴법한 가설*. \"한 가지 가설은 — …\" 식 명시 라벨 안에서, 약간 무리한 추측도 허용.
- **표현 3등급 강제** — 사실/추론/가설을 *반드시* 어조로 구분한다. **사실(단정형)** \"X 다 / 9,063 이다\"는 출처·시점·수치가 입력으로 명시된 경우만. **추론(헤지형)** \"…로 읽힐 여지가 크다 / …와 부합한다\"는 정황 기반 통찰 등급. **가설(명시 라벨)** \"한 가지 가설은 — / 무리한 추측을 보태자면\"은 약간 무리한 시나리오 추측 전용. 라벨 없이 가설을 단정 부사(\"분명히/명백히\")로 흘리면 사실 규율 위반.
- **근거의 짜임 가시화** — 추론/가설을 던질 때 *짜임의 재료* 를 한두 마디로 보여라(\"A 의 침묵 + B 의 사임 + C 의 자금 이동 시점을 겹쳐 보면\"). 재료 없는 가설은 공허한 음모론 — 금지.
- **안전선 (탐사 페르소나가 무너지는 곳)** — 무근거 fabrication(허구 인용·존재하지 않는 문서·없었던 발언) 금지. 가설 라벨로도 면책 안 됨. 인물·기관에 입력에 없는 동기·발언을 *단정* 으로 귀속 금지(헤지·가설 라벨 안에서만). 시점·날짜·시장 수치는 *언제나* 단정형 등급(추론·가설 톤으로 흐리지 말 것).
- **codex 검수자 reportage 인지** — payload `report_format` 을 보고 표현 등급 정합 검수로 전환. 명시 헤지·가설 라벨 안의 추측은 *허용·통과*(false-positive 회피, 르포 페르소나의 의도된 기능). 라벨 없는 단정 추측·짜임의 재료 부재·입력 사실 충돌은 여전히 high (`speculation_as_fact` / `unsupported_inference`). SSOT 정합 갱신 — 단축본 [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md) §\"포맷 적응\" + 전체 기준서 [prompts/market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md) §14 (CLAUDE.md `Codex 검수자 페르소나 갱신 SOP` 준수).
- **byte-equal 보존** — `report_format=standard`(트리거 \"르포\" 없는 모든 보고서)는 v8.1.0 과 byte-equal. 일반 보고서 톤은 [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md) 그대로 — 탐사 페르소나는 르포 모드에서만 *덧대진다*. 회귀 `test_reportage_format.py` 에 marker 가드 3개 추가(탐사 페르소나 marker · 3등급 표기 어휘 · codex 르포 적응).

## v8.1.0 — 르포(탐사보도) 포맷 — 전용 디자인 + stakeholder_map + 살아있는 애니메이션 완성

르포를 기존 보고서와 *완전 분리*하고 디자인·차트·애니메이션을 마감한 릴리스.

- **전용 깨끗한 템플릿** `src/templates/archetypes/reportage.html` — freeform_essay 가드 덧대기 폐기, 완전 분리. 헤더=버전만 / 제목 / 작성일시(분) / 번호 섹션(소제목+본문) / 용어풀이만. 목차·kicker·fact_grid·pull_quote·analogy·lede·쟁점·감시신호·시간궤적·요약·신뢰도·바이라인 전부 미렌더. report_synthesizer 가 `report_format=reportage` 시 라우팅.
- **전용 디자인** — 8종 다크 테마(`reportage_*`, report.css `[data-theme]` 블록 + `select_reportage_theme()`), G마켓 Sans(디스플레이)+Noto Sans(본문), 플랫 미니멀(둥근모서리/그림자 제거). 본문·제목에 '르포' 단어 금지 — UI 헤더·리스트(`build_reports_index`) `[르포]` 배지로만.
- **신규 차트 `stakeholder_map`** — 행위자 관계도. 국기·기업/단체 로고 둥근 SVG, 결정적 컬럼 레이아웃(force/hairball 금지 = CHART-AP-36). 7단계 정식 등록(RENDERERS / schemas `_TYPE_TO_GUARD` / usage_log KNOWN_CHART_TYPES / VISUAL_CAPABILITY_REGISTRY / fixture / 회귀).
- **살아있는 애니메이션 (르포 한정, prefers-reduced-motion 정지)** — stakeholder_map 엣지 흐름(`.sm-flow`)+허브 펄스(`.sm-pulse`), globe 지구본 테마색+연속 자전. sankey 는 **원본 렌더 유지(애니 제외)** — 흐름 입자 오버레이가 어색하다는 피드백 반영.
- **차트 최소화** — 르포는 시장 strip / 시계열 차트 자동 주입을 스킵(`report_format != reportage` 가드). 본문 흐름에 필요한 시각물만.
- **byte-equal 보존** — 트리거 "르포" 없는 모든 경로(템플릿·payload·system_prompt·테마·차트)는 v8.0.0 과 byte-equal. 회귀 `test_reportage_format.py`(12) + `test_stakeholder_map.py`(10).

## v8.0.0 — 르포(탐사보도) 포맷 트랙 Phase 0 — 트리거 + directive 채널 + 5막 골격

> **포팅됨 (main v7.9.17 핫픽스 → v8 반영, CHART-AP-29/37):**
> - **NaN 차트 회귀 차단 (CHART-AP-29).** Yahoo `^KS11` 미완성 마지막 봉이 `close=NaN` 으로
>   흘러들어 코스피 line/candle 차트가 빈 프레임, 감시 스트립 `코스피 nan%`, 종합지수 카드
>   `7815.59 → nan` 노출(본문 takeaway 는 9,064 인데 차트만 nan). 다층 차단 — ①
>   `market_fetcher._df_to_ohlc`/`_to_float` 가 `math.isfinite()` 로 비유한 봉을 생성 단계 skip
>   (`nan<=0` 이 False 라 기존 `c<=0` 가드를 빠져나가던 허점), ② `orchestrator._sanitize_market_nan`
>   가 fetch 직후 전 소스 합류 지점에서 비유한 봉 결정적 제거 + compact strip 빌더 방어.
> - **발행본 복구 도구** `scripts/patch_report.py --sanitize-ts-nan` (LLM 0, URL 보존).
> - **구 network(행위자 관계도) 포맷 폐기 (CHART-AP-37).** composer 미emit + `validate_chart_data`
>   drop 가드 + 레지스트리/렌더러/시나리오 정리(guarded 18→17, total 31→30). 르포 행위자
>   관계 시각화는 v8 신규 `stakeholder_map` 사용.

기사형 정보 전달 보고서와 별개로, **하나의 사건을 행위자 중심으로 낱낱이 해부하는 르포
(탐사보도) 포맷**을 신설하는 v8 트랙의 첫 단계(Phase 0).

- **트리거**: 텔레그램 메시지에 "르포" 가 있으면 `report_format="reportage"` 로 전환
  (`token_budget.resolve_report_format`). 트리거 토큰("르포 형식으로" 등 조사 변형 포함)을
  떼어낸 나머지 문장이 *이번 르포의 앵글*. mode(fast/standard/deep)와 **직교** — "르포"가
  없는 모든 메시지는 standard 라 기존 경로와 동일.
- **directive 채널 복원 (핵심)**: 사용자의 구체적 강조("특히 OOO 기관의 역할에 집중",
  "이 자금 흐름의 내막을 파줘")는 그동안 ContextAnalyst 의 사실 증류 과정에서 거세돼
  composer 에 닿지 못했다. v8.0.0 은 트리거를 떼어낸 원문을 `AnalysisRequest.user_directive`
  로 보존해 composer payload 에 직접 주입한다. 르포는 *어느 실타래를 당기느냐* 가 정체성이라
  이 앵글이 필수. 주관적 앵글(무엇에 집중할지)은 fact-critic 검증 면제, 그 안에 끼어든
  *검증 가능한 사실 주장*만 V6 사실 규율의 grounding 대상.
- **5막 골격**: composer SYSTEM_PROMPT 에 `_REPORTAGE_BLOCK` 직교 주입 (reportage 일 때만).
  발단 → 이해당사자 → 내막·동기 → 전개 → 전망(서사형) 5막. 행위자 관계는 network(인접행렬)·
  지도(국가 역할)·sankey(이해/자금 흐름)·timeline 으로 시각화. 인물 사진은 기사 og:image 만.
- **감시신호 제거**: 르포는 말미 watch_signals epilogue 를 두지 않는다 — 프롬프트가
  `watch_signals=[]` 를 지시 + orchestrator 가 reportage 일 때 Watchlist 등록을 스킵.
  contradictions(쟁점/반대 관점)는 유지.
- **byte-equal 보장**: `report_format=standard` + directive 없을 때 `_compose_system_prompt`
  와 `_build_unified_payload` 모두 기존 출력과 byte-equal (AP-V6-3 상속). 회귀
  `tests/regression/test_reportage_format.py` 11종.
- **Phase 1 (랜딩)**: 신규 차트 타입 `stakeholder_map` — 르포 전용 행위자 관계도.
  charts.js `drawStakeholderMap`(진영 칼럼 결정적 배치 + 직각·라운딩 엣지 + 다중 연결
  분산 + content-fit) + `StakeholderMapGuard`(노드 2~12·엣지 참조 검증) + KNOWN_CHART_TYPES /
  VISUAL_CAPABILITY_REGISTRY(guarded 18) / chart_type_scenarios 등록 + composer SYSTEM_PROMPT
  스키마·결정트리·`_REPORTAGE_BLOCK` 반영. 자산(국기/인물)은 `#sm-*` sprite 로 분리 —
  osint_generator 자산으로 교체 가능(로고/사진 미제공 시 이니셜 모노그램). **force/physics
  금지**(CHART-AP-36, network hairball 교훈 상속). 모크업 SSOT
  `samples/stakeholder_map_gallery.html`(6 경우의 수) + `..._themes.html`(5 테마). 회귀
  `tests/regression/test_stakeholder_map.py` + chart_type_diversity 1:1 정합 복원
  (combo_candle/iv_skew/indicator 누락분 동시 보강).
- **다음**: Phase 2 — ReportBundle 정합(osint 영상 관계망 피드). 자산 교체는 osint_generator
  세션 스코프 접근 확보 시.
## v7.9.17 — 시장 시계열 NaN 봉 결정적 차단(CHART-AP-29 소스 가드) + 행위자 관계도(network) 포맷 폐기(CHART-AP-36)

코스피 보고서 사용자 catch 3종 핫픽스.
- **NaN 차트 회귀 차단 (CHART-AP-29).** Yahoo `^KS11` 미완성 마지막 봉이 `close=NaN` 으로
  흘러들어 코스피 line/candle 차트가 빈 프레임, 감시 스트립이 `코스피 nan%`, 종합지수 카드가
  `7815.59 → nan` 으로 노출됐다(본문 takeaway 는 9,064 인데 차트만 nan). 다층 차단 — ①
  `market_fetcher._df_to_ohlc`/`_to_float` 가 `math.isfinite()` 로 비유한 봉을 생성 단계에서
  skip(`nan<=0` 이 False 라 기존 `c<=0` 가드를 빠져나가던 허점), ② `orchestrator._sanitize_market_nan`
  가 fetch 직후 모든 소스 합류 지점에서 비유한 봉 결정적 제거 + compact strip 빌더 방어.
- **발행본 복구 도구.** `scripts/patch_report.py --sanitize-ts-nan` — 이미 나간 보고서의 NaN 봉
  제거 + 영향 차트(line/area/candle)·감시 스트립의 subtitle·등락률·takeaway 재계산. LLM 0, URL 보존.
- **network(행위자 관계도) 포맷 폐기 (CHART-AP-36).** "큰 의미 없고 공간만 차지" 사용자 판단으로
  `network` 차트 type 영구 제거 — composer 미emit + `validate_chart_data` drop 가드 + 레지스트리/
  렌더러/시나리오 정리(guarded 17→16, total 30→29). 발행본은 `--remove-chart` 로 제거.

v7.9.15 가 데이터 소스를 고쳤다면, 본 버전은 *검수가 왜 못 잡았나* 를 메운다. 사고 보고서는
codex 가 켜진 채(web_verified=True, 6건 수정) 돌았는데도 코스피 날짜 불일치(6/17 vs 6/18)·
본문↔표 값 모순(7,516 vs 8,864)·실제값(9,063.84) 괴리를 전부 통과 — codex 가 *틀린
time_series 와의 일치만* 봤고, 표 카드는 prose 가드/검수 시야 밖이었기 때문.
- **결정적 가드 신설** — `deterministic_guards.py:market_anchor_coherence_guard`: ① 같은
  한국거래소 지표(코스피·코스닥·삼성·하이닉스) 최신 기준일 불일치 → `stale_market_anchor`(high)
  ② 최신 봉 연도 ≠ 발행연도(다른 해 같은 날짜) → `wrong_year_market_anchor`(high). `run_fact_guards`
  base 합류(log-only, `V6_FACT_GUARDS`). prose 파싱·LLM 0 — time_series 만 본다. 단위 테스트 4종.
- **codex 페르소나 강화**(2 SSOT + 코드 `_CRITIC_INSTRUCTIONS` 정합) — 시장 수치는 time_series
  만 믿지 말고 *웹 직접 대조*, 표 카드·차트 등 구조화 필드와 prose 의 intra-report 모순, *연도까지*
  확인, 한국 지표 기준일·수급 방향 정합을 high 로 검수.
- **CLAUDE.md** — 시장 수치 핫픽스 외부 1차 출처 검증 불변규칙(⑥) + 시장 데이터 무결성 다층
  방어 SSOT 섹션. 가드 작동에 VM `.env` `V6_FACT_GUARDS=1` 필요 명시.

## v7.9.15 — 코스피·코스닥 지수 KRX(pykrx) 우선 + Yahoo 폴백 (kospi-date-mismatch, 사용자 catch)

6/19 아침 일일 브리핑(analysis_20260619_061515)에서 코스피 표 카드가 `(6/17 종가) 8864.24
(+1.58%)` 로 박혀, 같은 보고서의 KRX 개별주(삼성·하이닉스)·ECOS 환율이 모두 6/18 종가인데
코스피만 하루 뒤처지는 불일치. 근본 원인은 한국 지수만 Yahoo(`^KS11`)에서 받는데, 장 마감
다음 날 아침 fetch 시점(06:15 KST)에 Yahoo 의 `^KS11` 6/18 일봉이 아직 게시되지 않아
직전일(6/17) 봉이 마지막이었던 것 — 게다가 Yahoo `^KS11` 값(8864)이 실제 코스피(7516)와도
괴리. 본문 prose 는 웹검색으로 6/18 7516.04 를 맞게 적어 보고서 내부 모순까지 발생.
- **Fix (A)**: `INSTRUMENT_REGISTRY` 의 코스피/코스닥을 KRX(pykrx) `get_index_ohlcv`
  (코드 1001/2001) primary 로 전환, Yahoo(^KS11/^KQ11)는 `fallback_source`/`fallback_code`
  로 강등. `fetch_market_series` 가 primary 빈 데이터일 때만 폴백 — pykrx index 가 환경에서
  실패해도 최악의 경우 v7.9.14 동작(=Yahoo)과 동일, 회귀 무.
- `InstrumentSpec` 에 `fallback_source`/`fallback_code` 필드 + `_build_fetcher` 헬퍼 추가.
  회귀 테스트 3종(KRX 우선 / 빈 데이터 폴백 / 라우팅 메타) 추가.
- 발행본 061515 는 표 카드·본문 3문장·차트의 8864.24(6/17) → 실측 6/18 종가(7516.04, +0.31%)로
  patch_report 핫픽스.

## v7.9.14 — 지수 등락률 vs 하락비율 diverging_bar 의 KOSPI 등락률 0 누락 방어 (CHART-AP-35, 사용자 catch)

장마감 브리핑(analysis_20260618_184833)의 composer 생성 '지수 등락률 vs 종목 하락비율'
diverging_bar 에서 KOSPI 의 `neg`(지수 등락률)이 **0** 으로 emit 돼 막대·값이 누락(KOSDAQ
3.01 은 정상, 부제엔 '지수는 +2.25%' 라 적고 데이터엔 0 — composer 자체 모순). orchestrator
가 장마감 브리핑 한정 결정적 가드 추가 — diverging_bar 행 라벨이 KOSPI/KOSDAQ 인데 neg 가
0/누락이면 `time_series` 실측 등락률(절댓값)로 채운다(행사가 라벨 OI diverging_bar 는 비대상).
CHART-AP-35 등재. 발행본 184833 은 KOSPI neg 0→2.25 직접 보정 후 재렌더.

## v7.9.13 — 차월물 스큐 선(先)캐시(롤오버 무단절) + 차트에 월물 명시 (사용자 제안)

롤 직후 며칠만 보이던 한계를 해소. ① **차월물 선캐시** — KRX 옵션 체인 응답엔 front 외
다음 월물도 들어오므로, `build_snapshot` 이 `_skew_points_for_expiry` 로 **차월물 IV 까지
미리 계산**(`snap.next_expiry`/`next_skew`) → `augment_skew_history` 가 매일 front+차월물을
둘 다 캐시 저장. 만기가 지나 새 front 가 되면 **이미 N일치 오버레이가 준비**돼 즉시 한 달
곡선이 보인다(롤오버 무단절). ② **월물 명시** — 차트 제목/부제에 `_fmt_expiry` 로
'2026년 7월물' 표기(다른 월물 IV 는 비교 불가하므로 어떤 월물인지 분명히). 회귀 테스트
`test_next_expiry_skew_precached`(차월물 식별·선계산·제목 월물) + 목업 제목 갱신.

## v7.9.12 — 스큐 오버레이 기본 20영업일(≈한 달) + 월물 롤오버 동작 명시 (사용자 요청)

스큐 오버레이/백필 기본을 **10→20영업일(≈한 달)** 로 확대. `backfill_skew` 는 캘린더가
아닌 *영업일* 기준으로 데이터 있는 날을 20개 채울 때까지 반복(휴일 자동 skip, 안전 캡
내). `augment_skew_history` 기본 n_days 20. **월물 롤오버 동작 명문화**: 캐시는 `expiry`
별 저장이고 오버레이는 *오늘 front 월물과 같은 expiry* 만 겹친다 — 다른 월물 IV 는 잔존
만기가 달라 비교 불가하므로, front 가 롤오버되면 새 월물 스큐로 자동 전환되고 그 시점부터
누적(롤 직후엔 며칠만 표시, 의도된 동작). backfill 이 롤 구간을 가로지르면 받은 날 수보다
적게 표시될 수 있음. CLI 기본 `--days 20`.

## v7.9.11 — IV 스큐 곡선 보강: 행사가 라벨 + 범위 확대 + 지난 N영업일 페이드 오버레이 (사용자 피드백)

v7.9.10 IV 스큐에 대한 사용자 피드백 3종. ① **각 행사가 라벨** — x축에 distinct 행사가
눈금+회전 라벨(>16개면 솎음). ② **범위 확대** — 스큐 꼬리가 안 보이던 ±18% 밴드를
**±28%** 로 + 비현실 IV(3~200% 밖, 역산 실패 꼬리) 제외. ③ **지난 N영업일 스큐 오버레이**
— 일별 IV 를 멱등 SQLite 캐시(`src/tools/skew_cache.py`, `SKEW_CACHE_PATH`)에 누적 →
`augment_skew_history` 가 차트 데이터를 다일자 점(각 점 `date`)으로 교체 → `drawIvSkew`
가 오늘=진하게·과거=옅게 페이드 그림. 즉시 10일 확보용 backfill CLI
(`python -m src.tools.derivatives_fetcher skew-backfill --days 14`). 캐시 없으면 오늘 단일
곡선(graceful). 회귀 테스트 — `tests/test_skew_cache.py` 5종 + 스큐 점 date/IV 범위 검증.
목업 갱신(4영업일 페이드 시연). `Config.skew_cache_path` + `.env.example` 추가.

## v7.9.10 — IV 스큐 곡선 재설계 + 베이시스 한 줄 지표 + 회귀 테스트 (v7.9.9 사용자 피드백)

v7.9.9 옵션 차트에 대한 사용자 피드백 반영. ① **IV 스큐를 scatter → 곡선으로 재설계**
(신규 `iv_skew` 렌더러) — 풋(파랑)·콜(빨강)을 행사가 순으로 *선 연결*해 스큐 트렌드가
보이게, 행사가 수를 관심 6개 → *전체 체인*(현물 ±18% 밴드)으로 확대, ATM IV 가로
기준선 라벨을 plot 안 좌상단에 둬 **우측 잘림 제거**. ② **선물 베이시스 한 줄 지표**
(신규 `indicator` 렌더러, 0 중심 ± 막대 — 콘탱고=accent/백워데이션=down) 추가 —
v7.9.9 에서 빠졌던 item4 세 번째 비주얼 완성. ③ `derivatives_fetcher.build_derivatives_charts`
가 iv_skew(전 체인)+indicator(베이시스) 생성, `tests/test_derivatives_fetcher.py` 에
**회귀 테스트 2종 추가**(차트 4종 shape·graceful). `iv_skew`/`indicator` KNOWN_CHART_TYPES
등록. 목업 갱신 `samples/market_briefing_charts_v7_9_9.html`. (전부 결정적 주입 →
다음 브리핑부터 자동.)

## v7.9.9 — 장마감 브리핑 차트 직관화: 코스피 캔들+이평선·하락비율 이중축·옵션 데스크 비주얼 (사용자 요청)

장마감 브리핑(analysis_20260617_184440) 차트 개선 4종을 *소스에 결정적으로* 박아
모든 향후 브리핑에 자동 반영(composer 비의존). ① **코스피 종합지수 candle + 20일
이동평균선** — 카드만 3개월 따로 fetch(20일선이 의미 있도록), `drawCandle` 에 SMA
오버레이 추가(`moving_average` 필드). ② **하락 종목 비율 + 지수 캔들 이중축** — 신규
`combo_candle` 렌더러(좌축 비율 line + 우축 지수 candle, 50% 기준선), orchestrator 가
breadth line 을 지수 OHLC 와 결합해 주입. ③ **옵션 데스크 직관 비주얼 3종** —
`derivatives_fetcher.build_derivatives_charts` 가 IV 스큐 scatter(+ATM 기준선 hline +
하단 설명)·풋콜비율 bullet(중립 1.0 대비)·행사가별 미결제 diverging_bar 를 결정적 생성,
orchestrator 가 옵션 섹션에 주입(서술 위주이던 섹션에 시인성). ④ **'최대고통' → 'max
pain'** — 아무도 안 쓰는 직역어 제거(WRITE-AP-24, derivatives_fetcher/prompt/persona).
미리보기 목업 `samples/market_briefing_charts_v7_9_9.html`. 발행본 184440 은 max pain
텍스트(--replace)+렌더러 fix(charts.js)만 소급 적용 가능 — 캔들·combo·옵션 차트는
데이터 구조 변경이라 *다음 브리핑부터* 반영. (v7.9.8 의 scatter 라벨 dodge·dot_matrix
중앙정렬은 이미 적용.)

## v7.9.8 — scatter 라벨 충돌 + dot_matrix 좌측 쏠림 fix (CHART-AP-33/34, 사용자 catch)

장마감 브리핑(analysis_20260617_184440) 차트 결함 2종. ① IV 스큐 scatter 의 우측
군집 라벨('풋 1,525'/'콜 1,527.5')이 겹쳐 판독 불가 → `drawScatter` 에 라벨 충돌
회피(우측 끝 점은 라벨 좌측 배치 + 같은 쪽 `dodgeYs` 세로 분산 + connector, 점·축
위치 불변). ② dot_matrix('코스피 100종목 등락 분포')가 좌측 쏠림 → grid+범례를 그룹에
담아 `getBBox` 가로 중앙정렬(sankey content-fit 패턴). 둘 다 charts.js 렌더러만 변경 —
발행본은 `patch_report <id> --rerender-only` 로 동일 URL 재렌더 시 적용. CHART-AP-33/34
등재. (같은 보고서의 코스피 캔들+이평선·하락비율 이중축 캔들·옵션 섹션 비주얼·IV 기준선
은 데이터·구조 변경이라 후속 작업으로 분리.)

## v7.9.7 — 발행본 한정 기승전결 스크롤 아크 워터마크 제거 옵션 (patch_report --strip-arc, 사용자 요청)

특정 발행본 마지막 섹션의 기승전결(起承轉結) 배경 워터마크 "結" 이 어색하다는 지적
(이 보고서 한정). `V7_SCROLL_ARC` 기능 자체는 유지한 채 *발행본 한 건만* 워터마크를
빼도록 `FullAnalysisResult.disable_scroll_arc`(default False, byte-equal) 추가 +
`report_synthesizer` 가 이 플래그를 존중해 scroll_arc 미빌드 + `patch_report.py --strip-arc`
가 플래그 세팅 후 재렌더(표현 변경 → render_revision 소수부 +1, 동일 URL). 구 보고서
JSON 은 기본 False(하위호환). DATA_MODELS §3.C 갱신.

## v7.9.6 — 보고서 고유명사 원어 표기 보존, 음성 내레이션과 분리 (WRITE-AP-24, 사용자 catch)

영상용 음성 대본(`narration_tts`)에서나 쓰는 *한글 음차* 가 보고서 본문으로 번져,
`DeepSeek`이 "딥시크", `Copilot Cowork`가 "코파일럿 코워크", `OpenAI`가 "오픈AI",
`Anthropic`이 "앤트로픽", `Azure`가 "애저", 일반 용어 `opt-in`이 "옵트인" 으로 나오던
회귀. WRITE-AP-23(TTS 발음 표기 누수)의 자매 케이스다 — 음성 전용 표기가 *눈으로 읽는
글* 로 새어 든 것. composer SYSTEM_PROMPT §0.1 에 **`(1-예외)` 고유명사 보존 블록**
신설: 회사·제품·서비스·모델·브랜드·기관명은 평이화·음차 대상이 아니며 통용 로마자명은
영문(DeepSeek/Copilot Cowork/OpenAI/Anthropic/Azure/Fable 5/GitHub Copilot/Meta/Mistral),
한국 언론에서 굳어진 이름(마이크로소프트·나스닥·로이터·트럼프)만 한글. 한글 음차는
`narration_tts` 전용이고 prose·headline·deck·heading·각주·`broadcast_summary`·자막
(`narration`)에는 원어 표기 — 보고서와 영상 음성 내레이션을 명확히 분리. `broadcast_summary`
표기 레지스터·TTS 발화 규칙 ⚠️ 경계에도 고유명사 음차 예시 추가. SSOT: REPORT_STYLE_GUIDE
§0.1 (1-예외) + tts_narration_guide §0/§3. 발행본은 `scripts/patch_report.py --replace`
(LLM 0, narration_tts 미변경 — 음성 발음 그대로) + `--add-footnote` 로 opt-in 용어 풀이.

## v7.9.5 — 장마감 브리핑 트리거 17:00 → 18:30 (데이터 정합성, 사용자 결정)

선물·옵션 그릭·시장 폭 실데이터를 붙이면서 *언제 받느냐*가 정합성에 직결. 17:00 은
외국인/기관 수급이 잠정치로 출렁이고 KRX 일별 통계가 막 게시되는 구간이라(장중 14:57
테스트에서 breadth 가 장중 스냅샷으로 잡힌 게 그 증거), 종가 확정치가 아닌 값이 섞일
위험이 있었다. KRX 일별 통계·확정 수급·파생 미결제약정이 18:00~18:30 에 안정화되므로
(breadth 통합 지시서도 18:30 권고) 기본 트리거를 **18:30 KST** 로 변경. `Config.
market_briefing_time` 기본값 + 스케줄러 docstring/loop 기본 + telegram 안내 + .env.example
동기화. env `MARKET_BRIEFING_TIME` 으로 언제든 override 가능(코드 변경 불요). 발행 ~18:55.

## v7.9.4 — 관심 행사가를 현물 ±15% 밴드로 (딥OTM 꼬리 제외)

VM 실측에서 그릭은 정상 산출됐으나 '관심 풋옵션'이 현물 1406 대비 545/800/1000 같은
딥OTM 꼬리(미결제만 큰 복권, 델타 ≈0)로 잡혀 의사결정 가치가 낮았다. `build_snapshot`
의 관심 콜/풋 선정을 **현물 ±15%(`notable_band`) 밴드 안**에서 OI·거래량 상위로 제한 —
지지·저항·매물벽으로 실제 의미 있는 행사가를 노출. 딥꼬리는 스큐·풋콜비율·max pain 엔
계속 반영(제외 아님). 밴드 안 후보 부족 시 전체로 완화. 회귀 30종 통과.

## v7.9.3 — 옵션 그릭 산출 fix + CLI 로그인 (VM 실측 후속)

VM 로그인 성공 후 실데이터로 확인된 두 결함 수정. ① **옵션 그릭 전무** — KRX 옵션 시세
행에 현물가(SPOT_PRC)가 없어(선물 행에만 존재) IV 역산이 전 행 스킵 → ATM IV·델타·감마
등이 안 나옴. `build_snapshot` 이 선물 현물가(또는 체인 내 첫 유효 현물가)를 **기초자산
폴백**으로 사용하도록 수정 → 관심 콜/풋 행사가의 IV·그릭이 채워짐. 회귀 테스트 추가
(옵션 행 SPOT_PRC 제거 시나리오). ② **CLI 로그인** — `python -m src.tools.{derivatives,
breadth}_fetcher` 가 config 없이 호출돼 KRX 미로그인이던 것을, CLI 가 `Config()` 를 구성해
KRX_ID/KRX_PW 를 전달하도록 수정(backfill 포함). VKOSPI 는 여전히 best-effort(지수 엔드포인트
미확정 — 웹검색 보완). 순수 계산 로직 회귀 30종.

## v7.9.2 — KRX 로그인 필수화 대응 (data.krx 'LOGOUT', VM 실측)

v7.9.1(웜업+풀 UA)에도 VM 에서 여전히 HTTP 400. 응답 본문이 **`LOGOUT`** — 즉
data.krx.co.kr 의 getJsonData 가 2026-06 부터 **로그인 필수**로 바뀌었다(무로그인 스크레이핑
종료). pykrx 1.2.8 이 `KRX_ID`/`KRX_PW` 를 요구하게 된 것도 같은 이유였다(VM 에서 pykrx
get_market_ohlcv 도 동일 실패 확인). krx_client 를 **pykrx 인증 세션 재사용**으로 전환 —
`ensure_session(config)` 가 `Config.krx_id/krx_pw`(.env: KRX_ID/KRX_PW)로 pykrx 의 로그인
핸드셰이크(`build_krx_session`)를 수행하고, 그 인증 세션 쿠키로 우리 bld/params 를 직접 POST
(`asyncio.to_thread` 로 오프로드). aiohttp/웜업 경로 제거. 자격증명 미설정·로그인 실패는 빈
snapshot + 안내 warning(보고서 정상 진행). **사용자 액션 필요**: 무료 data.krx.co.kr 계정
가입 후 `.env` 에 KRX_ID/KRX_PW 설정. 순수 계산·집계(테스트 29종) 불변.

## v7.9.1 — KRX getJsonData 400 회귀 fix (세션 웜업 + 풀 UA, VM 실측)

v7.9.0 의 KRX fetch 가 VM 에서 **HTTP 400** 으로 전부 실패(선물·옵션·breadth 모두
'확인되지 않음'). 원인은 KRX WAF 가 *콜드* POST(쿠키 없이 바로 getJsonData)를 400 으로
막는 것 — pykrx 가 되는 이유는 ① 풀 Chrome User-Agent ② 데이터 요청 전 페이지 GET 으로
`JSESSIONID`/`WMONID` 쿠키를 받는 *웜업* 때문이었다(내 코드는 `Mozilla/5.0` 단독 + 웜업
없음). 공유 SSOT `src/tools/krx_client.py` 신설 — 풀 UA + `Accept`/`Accept-Language` 헤더 +
`warmup()`(데이터 메뉴 로더·루트 GET 으로 쿠키 적재, aiohttp cookie_jar 자동 첨부) +
`post_json_rows()`. derivatives_fetcher·breadth_fetcher 가 이 클라이언트를 통해 요청하고
세션 시작 시 `await warmup(session)` 1회. 순수 계산·집계 로직(테스트 29종) 불변 — 네트워크
계층만 교체. 실연동 재검증: `python -m src.tools.derivatives_fetcher` / `... breadth_fetcher`.

## v7.9.0 — 장마감 브리핑 실데이터 파이프라인: 선물·옵션 그릭 + 시장 폭 (사용자 요청)

v7.7/v7.8 로 프롬프트·페르소나를 아무리 강화해도 실제 장마감 보고서엔 선물·옵션 수치가
**'확인되지 않음'** 으로만 떴다. 진단 결과 근본 원인은 *데이터 접근* — 웹 검색이 외국인
선물 순매수·미결제약정·행사가별 IV 같은 granular 수치를 신뢰성 있게 못 가져오고, 그릭은
애초에 어디에도 공표되지 않아 *계산* 해야 했다. 그래서 KRX 정보데이터시스템
(data.krx.co.kr)의 무로그인 공개 엔드포인트에서 직접 받아 결정적으로 산출하는 파이프라인을
신설했다. (사용자가 추가로 요청한 **미결제약정**·**시장 폭(등락 종목 수)** 도 함께 흡수.)

**신규 모듈 3종 (모두 graceful degrade — 실패해도 보고서 흐름 무영향):**

- **`src/tools/greeks.py`** — Black-Scholes 옵션 가격·내재변동성(IV) 역산·그릭(델타/감마/
  세타/베가/로). 순수 stdlib(`math.erf`, scipy 불요), 데스크 관용 단위 환산(베가=1%p, 세타=
  1일, 로=1%p). max pain·풋콜비율 계산도 포함. 단위 테스트 11종(교과서 값·풋콜 패리티·IV
  왕복).
- **`src/tools/derivatives_fetcher.py`** — KOSPI200 선물(전종목 시세 MDCSTAT12501,
  `KRDRVFUK2I`)에서 최근월물 종가·등락·**미결제약정**·현물 대비 **베이시스**, 옵션 체인
  (`KRDRVOPK2I`)에서 행사가별 프리미엄·OI·거래량을 받아 **종가에서 IV 역산 → 그릭 계산**.
  활성 만기 풋/콜 비율(거래량·OI)·**최대고통(max pain)**·ATM IV·**관심 콜·풋 행사가**(OI 상위)
  선정. 결과를 composer 가 소비하는 key_figures({label,value,context})로 출력. 조립 로직은
  순수 함수라 합성 rows 로 회귀 7종.
- **`src/tools/breadth_fetcher.py`** — 전종목 시세(MDCSTAT01501, mktId=STK/KSQ)에서
  코스피·코스닥 **상승/하락/보합 종목 수**를 등락률 부호로 집계 → **하락비율(당일·5일·20일
  평균)·추세·하락비율↔향후 지수 상관**. 멱등 **SQLite 캐시**(과거 영업일 재수집 안 함, 신규일만
  append — 첨부 지시서의 '수집/표현 분리·멱등' 원칙), 1회 실행 inline 백필 상한으로 레이턴시
  보호. 순수 집계·요약 함수 회귀 11종.

**통합:** `orchestrator.run_analysis(fetch_kr_market_internals=True)` (market_briefing 스케줄러만
전달)일 때 ContextAnalyst 직후 두 fetch 를 돌려 실측 수치를 `key_figures` 로 병합(본문에 실수치
노출) + breadth decline-ratio **line 차트**를 compose 후 결정적 주입(d3 네이티브). breadth↔지수
상관은 이미 fetch 된 `context.time_series`(코스피/코스닥 종가) 재사용 — 추가 호출 0. 페르소나
제11 렌즈(파생 데스크 5축)·제4 렌즈(시장 폭)와 프롬프트가 이 데이터를 *반드시 인용·분석*
하도록 강제. config 플래그 `ENABLE_KR_DERIVATIVES`/`DERIVATIVES_RISK_FREE`/
`ENABLE_MARKET_BREADTH`/`BREADTH_CACHE_PATH` 추가(기본 ON, 장마감 브리핑 한정).

**아키텍처 적합화:** 첨부된 breadth 통합 지시서는 matplotlib PNG + 별도 venv + cron +
markdown 병합을 제안했으나, agents_reviewer 는 d3 인터랙티브 HTML 보고서라 *분석 내용*
(등락 종목 수·하락비율·5/20일 추세·지수 상관·선행성 한계 caveat·음슴체 요약)만 네이티브
(무로그인 KRX fetch + d3 차트 + key_figures)로 흡수했다. pykrx 의 KRX_ID/PW 로그인도 불요
(derivatives 와 동일 무로그인 POST).

**범위·검증:** 전부 장마감 브리핑 전용 — 일반 `/analyze`·일일 브리핑은 default False 게이트라
byte-equal. 신규 의존성 0(stdlib + 기존 aiohttp). data.krx.co.kr 은 개발 샌드박스에서 egress
403 이라 실연동 정확성은 **VM 검증** 필요: `python -m src.tools.derivatives_fetcher` /
`python -m src.tools.breadth_fetcher` / `... breadth_fetcher backfill --days 120`(이력 적재).
그릭·집계 *계산 로직* 은 단위 테스트 29종으로 검증 완료.

## v7.8.0 — 장마감 브리핑 선물·옵션 섹션을 파생 데스크 전문가 수준으로 (사용자 요청)

v7.7.0 으로 선물·옵션 렌즈를 넣었지만 실제 장마감 보고서에 **선물·옵션 내용이 전혀
나오지 않았다**(사용자 보고). 진단 결과 근본 원인은 두 가지였다 — (a) ContextAnalyst 가
파생 데이터를 *적극적으로 수집* 하도록 강제하지 않았고(웹 검색이 종가·수급 합계에 그침),
(b) composer 가 *전용 섹션을 반드시 만들도록* 강제하지 않아 파생 내용이 본문에 흩어지거나
누락됐다. 6/15 마감 브리핑 실물에서도 분석관 스스로 "선물 포지션 미확인", "기관 세부 주체
미분리" 라고 적은 게 증거. 두 갈래로 강화했다(전부 장마감 브리핑 전용 — 다른 보고서 무영향).

**① 데이터 수집 강제 (ContextAnalyst 도달).** `market_briefing._build_market_briefing_prompt`
요구사항 #2 를 `[필수]` 로 올리고, 증권사 데일리 파생 리포트·연합인포맥스/이데일리/한국경제/
파이낸셜뉴스의 '선물·옵션 동향' 기사·KRX 정보데이터시스템을 *적극 검색* 하도록 명시. 수집
대상을 **주체별·행사가별** 로 구체화 — 선물 순매수를 외국인/금융투자/투신/연기금/은행/보험/
개인으로 *분해*, 미결제약정 증감, 프로그램 차익/비차익, VKOSPI·풋콜비율·변동성 스큐, 그리고
*거래량·미결제·내재변동성(IV)이 두드러진 주요 콜·풋 행사가*, 옵션 만기·동시만기·롤오버·
맥스페인/매물벽. 확보 못 한 항목은 '확인되지 않음' 표기(추정 금지).

**② 전용 전문 섹션 강제 (composer 도달).** 페르소나(`prompts/market_briefing_persona.md`)의
제11 렌즈를 *파생 데스크 전문가 5축* 으로 확장하고, 요구사항 #4 에서 **선물·옵션만 다루는
독립 H2 섹션 1개를 반드시 포함** 하도록 강제:

- **1축 선물 가격·베이시스** — 베이시스 → 차익 프로그램 → 현물 압력의 인과 사슬.
- **2축 선물 수급 주체별 분해** — 외국인/금융투자(증권사 자기매매·델타헤지)/투신/연기금/
  은행·보험/개인을 쪼개 *누가 방향을 걸었나* + 현·선 정합성으로 확신 강도 판별.
- **3축 미결제약정 × 가격 조합** — 신규 매수/숏커버/신규 매도/롱청산 판별 + 프로그램
  차익/비차익.
- **4축 관심 콜·풋 행사가** — IV·거래량·미결제가 두드러진 콜/풋 행사가, 상단 콜 매물벽·
  하단 풋 헤지, 변동성 스큐·기간구조, VKOSPI·풋콜비율, 만기·맥스페인 자석.
- **5축 그리스(델타/감마/세타/베가/로)** — 옵션 포지션이 시장에 가하는 압력 해석(만기 임박
  감마 증폭, 베가=변동성 노출, 세타=시간가치 소멸). **그릭 수치는 지어내지 않고** 관측
  조건(잔존 만기·IV·행사가 분포·외국인 선물 방향)으로부터 시사점을 읽되, 보도가 구체 수치를
  제시하면 출처와 함께 인용.

데이터 미확인 항목도 *개념·관전 포인트* 는 설명해 섹션을 비우지 않도록 명시(빈 섹션 금지).
파생 데이터는 web 검색(ContextAnalyst) 기반이라 `market_fetcher` 레지스트리·`.env` 변경은
없다. 코드는 `market_briefing.py` 프롬프트 한 곳 + 페르소나, 봇 재시작 필요.

## v7.7.0 — 한국 장마감 브리핑에 텔레그램 요약 + 지수 선물·옵션 상세 섹션 (사용자 요청)

매일 17:00 KST 한국 장마감 브리핑(`src/scheduler/market_briefing.py`)에 두 가지를
추가했다.

**1) 텔레그램 요약(`broadcast_summary`) 송신 — 누락 수정.** 일반 `/analyze` 와 일일
브리핑(06:00)은 보고서 생성 후 composer 가 emit 한 `broadcast_summary`(라벨 없는 평문
요약)를 텔레그램으로 보내는데, 장마감 브리핑만 이 단계가 빠져 있었다(URL + 번들만 전송).
`daily_briefing` 의 "2.5) broadcast 요약" 과 동일 패턴으로 `_market_brief_for_chat` 에
추가 — 보고서 URL 메시지 *앞*에, 라벨 없이 본문만, best-effort(실패해도 보고서 흐름
영향 없음). 이제 장마감 브리핑도 다른 보고서와 동일하게 요약이 먼저 도착한다.

**2) 지수 선물·옵션 상세 브리핑 — 제11 렌즈 신설.** 기존 페르소나(시장 구조 해석가)는
현물 가격·거래대금·수급 중심 10 렌즈였고 선물은 제3 렌즈에서 스치듯 언급될 뿐, 옵션은
거의 다루지 않았다. `prompts/market_briefing_persona.md` 에 **제11 렌즈 — 선물·옵션은
현물의 결과가 아니라 배경이자 선행 신호다** 를 추가하고, 매 보고서에 *독립된 상세 섹션*을
강제했다. 4축 구조:

- **1축 선물 가격·베이시스**: KOSPI200 선물 종가·등락 + 베이시스(선물−현물), 콘탱고/
  백워데이션, 베이시스 → 차익 프로그램 매매 → 현물 압력의 인과 사슬.
- **2축 외국인 선물 포지션**: 외국인 선물 순매수·누적 포지션 + 현물·선물 정합성(매수/매수
  = 강한 위험선호, 매수/매도 = 헤지·확신 약화 등)으로 상승의 신뢰도를 가름(제3 렌즈와 연결).
- **3축 미결제약정·프로그램 매매**: 미결제약정(OI) 증감 × 가격 방향 조합으로 신규 매수/
  숏커버/신규 매도/롱청산 판별 + 차익(베이시스 연동)·비차익(방향성) 분리.
- **4축 옵션 심리·만기 자석**: VKOSPI(한국판 공포지수)·풋콜 비율·행사가별 미결제 집중
  (콜·풋 매물벽, 맥스페인 자석 효과)·동시만기/롤오버 부담.

해석 원칙(둘 이상 같은 방향일 때만 강한 결론, 현물·파생 괴리는 봉합 금지, 미확인 수치는
추정 금지, 용어는 일반 독자용으로 풀거나 주석)도 명문화. ContextAnalyst 수집 단계의
단계 분리 지시에 파생 데이터 수집 항목(선물 종가·베이시스·외국인 선물·OI·프로그램·
VKOSPI·풋콜·행사가·만기)을 추가하고, `market_briefing._build_market_briefing_prompt` 의
요구사항에 파생 데이터 확인 + 독립 상세 섹션 강제(제11 렌즈)를 넣었다. 페르소나 렌즈 수
표기 10 → 11 정합. 파생 데이터는 web 검색(ContextAnalyst) 기반이라 `market_fetcher`
레지스트리 변경은 없다. 코드 변경은 스케줄러 모듈 한 곳 + 프롬프트/페르소나, 봇 재시작
필요(persona 는 런타임 재로딩이지만 prompt builder·VERSION 은 코드).

## v7.6.4 — TTS 발음 표기가 텔레그램 요약·본문으로 누수 차단 (WRITE-AP-23, 사용자 catch)

텔레그램 요약(`broadcast_summary`)에 "WTI"가 "더블유티아이", "D램"이 "디램",
"7.86%"가 "7.86퍼센트"로 나오던 회귀. v7.4.0~v7.6.3 에서 추가된 강한 영상 TTS
발음 규칙(narration_tts 전용)이 같은 LLM 호출 안에서 글 작성까지 번진 게 원인.

- **프롬프트 경계 (1차 방어)**: composer SYSTEM_PROMPT "★ TTS 발화 규칙" 블록 머리에
  적용범위 명시 — 발음 변환은 *오직 `narration_tts`/`*_narration_tts`*, `broadcast_summary`·
  `prose`·`headline`·`deck`·`narration`(자막)·`highlights`·timeline·contradictions 같은
  *눈으로 읽는 글* 엔 금지(원래 표기 WTI·D램·7.86%·8,000). `broadcast_summary` 블록에
  표기 레지스터 규칙 추가. SSOT `prompts/tts_narration_guide.md §0` 경계 박스.
- **결정적 후처리 (2차 방어, 재발방지)**: `narrative_composer._revert_phonetic_in_text`
  (`_sanitize_symbols` 끝에서 호출 → orchestrator 최종 패스로 전 경로 보장) 가
  `broadcast_summary` 의 *명확한* 약어 누수를 결정적 복원(더블유티아이→WTI / 디램→D램 /
  에이치비엠 포→HBM4 등, `_PHONETIC_TO_TEXT` 역매핑). 'S-1=에스원'(보안회사 명)·'에이아이'
  같은 모호어는 오역 위험이라 복원 제외. `headline`/`deck`/`prose` 누수는 복원 안 하고
  warn-only(편집체 보존). 숫자·%(8천→8,000, 퍼센트→%)는 결정적 변환이 오역 위험이라
  프롬프트 전담.
- **재발방지 문서화**: WRITE-AP-23 신설 (`docs/REPORT_WRITING_ANTIPATTERNS.md`),
  `tts_narration_guide.md §0` 적용범위 경계, CLAUDE.md anti-pattern 목록 23개로.
  회귀: `src/tests/test_narrative_composer.py` 에 복원/모호어 제외/idempotent 3종 추가.
- **발행본 정정(소급)**: 이미 나간 보고서는 VM 에서 `scripts/patch_report.py <id>
  --replace "더블유티아이=WTI" ... --broadcast` 로 개별 정정(URL 보존).

## v7.6.3 — narration 비문·누락 보정 (3차 음성 검수)

3차 음성 영상 검수의 문법·완결성 보정. 새 필드 없이 작성 규칙 + producer 결정론 warn.

- **부정·불가능 의존명사 "수 없는" 누락 금지 (이번 핵심)**: "절대로/결코" 가 앞에
  오면 거의 항상 "~할 수 없는" 이 필요하다 — 빠지면 의미가 뒤집힌다. 사고
  "절대로 물러설 한계선이라고 못박았습니다." → "절대로 물러설 *수 없는* 한계선…".
- **각 narration 문장은 문법적으로 완결**: 비교·인용·접속 어미("…보다", "…때문에")
  도중 절단 금지. 화면 자막 한 cue = 한 완결 문장.
- **종결어미는 다큐 경어체로 통일**: 논설체·반말("~이다/~한다/~했다") 금지,
  "~입니다/합니다/됩니다". 특히 contradictions 의 side/resolution 을 narration·line
  으로 옮길 때 원문(논설체)을 *경어체로 다시 쓴다*.
- **항목 나열 가운뎃점(·) → 조사 (2차 ⓕ 강화)**: 출처 나열(NPR·CBS) 관용만 · 허용.
- **표기 (재확인)**: 무기 체계명 영문("장보고 N"), 영문 약어 발음은 narration_tts
  한글("NCG"→"엔씨지"), 숫자+단위 한글("32개월"→"삼십이 개월"), 날짜 "M월 D일".
- **producer 결정론 warn**: `bundle_builder._warn_narration_quality` 가 sections/
  report/timeline/contradictions 의 모든 narration·line 채널에서 3종 사고를 warn —
  ① '절대로/결코' 인데 부정어(없/않/못) 없음(못박다의 '못' 은 오인 제외) ② 비교·접속
  어미 절단 ③ 평서형 '~다' 종결. drop·재작성 안 함(휴리스틱이라 보수적, 1차 방어는
  composer SYSTEM_PROMPT "★ 3차 검수" 블록). contradictions[].video 신설(v7.6.2)은
  재확인 — 이미 main 에 있음.
- SSOT `prompts/tts_narration_guide.md` §1/§7 + composer 단축본 + 계약 §13/DATA_MODELS
  동시 갱신. 회귀: `tests/test_report_bundle.py` 에 narration 품질 warn 2종 추가 (25 pass).

## v7.6.2 — video 쟁점 카드 대본 + 표기 보정 (2차 음성 검수)

2차 음성 영상 검수의 대본 측 보정. 스키마 구조는 그대로, "쓰는 법" + 신규 채널 1종.

- **(신규) `contradictions[].video` — 쟁점 카드 대본 (계약 §13 additive,
  schema_version 1 유지)**: 영상이 `side_a`/`side_b` *논설체 원문* ("…정책
  전환이다") 을 카드·자막에 그대로 노출하던 것을 다큐 경어체 대본으로 대체.
  `{label_a, label_b}` (진영 이름 ≤8자) + `{line_a, line_b}` (한 줄 경어체 ≤40자,
  스테이트먼트 씬) + `{narration, narration_tts}` (쟁점 씬 자막). composer 가
  `contradictions[].video` emit → `bundle_builder._contradiction_video` 결정론
  가드(label ≤8 / line ≤40 / narration ≤4 캡·길이 warn) → `BundleContradictionVideo`.
  `side_a`/`side_b` 원문은 보존하고 video 만 더한다(additive). 부재 시 null.
- **표기 — 무기 체계명 음차 → 영문**: "장보고-엔"·"장보고 엔" → "장보고 N"
  (headline/heading/highlights/prose 전반). narration_tts 발음은 "장보고 엔".
- **highlights 가 heading 을 그대로 반복 금지**: 화면에 같은 말 두 번 — heading 이
  안 보여준 구체 수치·고유명사를 담는다. producer `_section_video` 가 정확 일치
  시 warn (heading 을 매핑부에서 전달, 2차 검수 회귀 표면화).
- **가운뎃점(·)으로 항목 두 개 붙이기 금지**: "김여정 담화·김정은 핵물질 공장" →
  조사로 풀거나 " · "(앞뒤 공백). narration·highlights·prose 공통.
- **narration 각 항목은 완결된 한 문장**: "…침묵보다" 처럼 비교·연결 도중 절단 금지.
- **불변**: 사실 근거 검증, highlights ≤40자, emphasis 정확한 부분 문자열 규칙
  그대로. SSOT `prompts/tts_narration_guide.md` §0-2-3/§1 + composer 단축본 정합 +
  계약 §13/예시 JSON/DATA_MODELS 동시 갱신. 회귀: `tests/test_report_bundle.py`
  에 쟁점 video 매핑/캡/heading-echo/예시 4종 추가 (23 pass).

## v7.6.1 — 비공개 전체 보고서 목록을 /{token} 클린 경로로 (사용자 요청)

- **`ADMIN_INDEX_TOKEN` 목록 페이지 경로 개정**: 기존 `admin-{token}.html` →
  **`{token}.html`** 생성. Cloudflare Pages 가 `.html` 을 숨겨 서빙하므로 접속
  주소는 `https://analysis-reports.pages.dev/{token}` (난수 20자리 고정 주소,
  즐겨찾기용). 공개 랜딩(`/`)은 v5.6.2 그대로 목록 비공개 유지.
- 옛 `admin-*.html` 잔재는 `_generate_index` 가 자동 삭제 — stale 목록이 옛
  주소로 계속 노출되는 누수 차단 (다음 deploy 에서 Pages 에서도 사라짐).
- 텔레그램 안내 URL 2곳(`/reports` 명령, 분석 완료 메시지) + `.env.example` /
  `config.py` 주석 동기화. env 변수명(`ADMIN_INDEX_TOKEN`)·생성 트리거(보고서
  발행 시 재생성)는 불변.

## v7.6.0 — video 대본 작성 규칙 개정 + timeline.video (1차 음성 영상 검수 반영)

첫 음성 합성 영상 (analysis_20260606_114653) 사람 검수 결과를 narration 생성
규칙에 반영. 스키마 구조는 그대로, "쓰는 법" 이 바뀜 — 영상 쪽도 같은 검수로
템플릿 문장·발음 사전·자막 폭을 수정한다.

- **문체 — 축약 금지, 말하듯 풀어쓰기 (검수 최우선 지적: "너무 축약해서 대본이
  써졌고 그걸 읽음")**: narration 은 자막용 요약문이 아니라 *성우가 읽는 구어체
  대본*. 한 문장 한 정보, 명사 나열 대신 주어-동사 문장. **문장 한도 58→75자
  완화** (풀어쓰기용, 자막 줄바꿈은 영상 쪽 처리 — 양측 합의값). 짧게 줄이려고
  조사·서술어 삭제 금지. composer SYSTEM_PROMPT "★ 1차 음성 영상 검수 반영" 블록
  + `bundle_builder._NARRATION_MAX_CHARS = 75`.
- **날짜·시간 표현 — 콤마 나열 금지, 조사로 연결**: "{날짜}, {문장}" 금지 →
  "{날짜}에는/{날짜}에 ~했습니다" ("실제로 1월에는 최대 100만 위성 규모를
  신청했습니다").
- **제목·라벨 낭독 금지**: 섹션·차트 제목, 타임라인 분기점 라벨은 화면이 이미
  보여줌 — 내레이션은 그 내용을 *이야기* 로 푼다.
- **(신규) `timeline.video` — 타임라인 씬 내레이션 (계약 §13 additive,
  schema_version 1 유지)**: timeline 에 video 가 없어 영상 쪽이 기계 문장으로
  메우던 것을 producer 대본으로 대체. composer 가 `timeline_flow.video`
  (`{narration, narration_tts}`, 분기점들을 이야기로 잇는 3~4문장) emit →
  `src/timeline_flow.py` 패스스루 → `bundle_builder._timeline_video` 결정론 가드
  (≤4 캡 + 길이·TTS gap warn) → `BundleTimeline.video: BundleTimelineVideo`.
- **narration_tts 발음 표기 강화 (검수 실사고 기준)**: ① 숫자는 *전부 한글로* +
  자연 발음 단위 띄어쓰기 — "32개월"→"삼십이 개월" (붙이면 '개'에 강세), "7개"→
  "일곱 개". ② 경음화 표기 — "해지권"→"해지꿘", "조건"→"조껀". ③ 영문 약어 한글
  표기는 유지 (에스원·에프씨씨 — 잘 되고 있음). 대원칙: narration_tts 는 *한글로
  받아쓴 발음 그대로*. SSOT `prompts/tts_narration_guide.md` §1/§2/§6 개정
  (자가 체크리스트 §7 로 재번호) + composer 단축본 정합.
- **불변**: 사실 근거 검증 (수치는 번들에 실재), highlights ≤40자, emphasis 정확한
  부분 문자열 규칙 그대로. 회귀: `tests/test_report_bundle.py` 에 timeline.video
  매핑/캡/warn + 75자 경계 3종 추가 (19 pass).

## v7.5.1 — 실데이터 목업 + CHART-AP-32 (sankey 라벨 수치 중복, 사용자 catch)

- **실데이터 목업** — [samples/v7_5_realdata_mockup.html](samples/v7_5_realdata_mockup.html):
  v7.5.0 신규 어휘 + sankey 를 전부 실제 공표치 (2026-06-12 수집) 로 채운 베이스라인.
  combo=삼성전자 5개 분기 매출×영업이익률 (1Q25 79.1조/8.5% → 1Q26 133.9조/42.7%),
  sankey=1Q26 부문 매출→비용/영업이익 (DS 81.7·DX 52.7·SDC 6.7·하만 3.8 → 영업이익
  57.2), pyramid=한국갤럽 6월 2주 연령대별 직무 긍정/부정 (N=1,002), diverging_bar=
  2022 국방백서 남북 상비병력 (128만 vs 50만), dot_matrix=통계청 2025.8 비정규직
  38.2%, 지구본=평양 중심 노동 1,300km·화성-12 4,500km 사거리권 + 괌·앵커리지 위협축.
  카드별 출처 라인 + 하단 출처 목록. 헤드리스 렌더 검증.
- **CHART-AP-32 (사용자 보고 "실보고서 sankey 가 마음에 안 듦" → 목업 제작 중 재현)** —
  sankey 노드 라벨에 수치를 박으면 렌더러 자동 합계와 *이중 표기* ('하만 3.8'+'3.8').
  원인은 composer SYSTEM_PROMPT 의 구체 예 ('총매출 133.9조' 식) 가 가르친 라벨 문법.
  픽스 이중화: ① `drawSankey` 결정적 dedup (라벨에 같은 수치 있으면 자동 값 생략,
  value_label 은 존중) ② SYSTEM_PROMPT 예시를 '라벨은 이름만' 으로 교정. 갤러리
  fixture 도 클린 문법으로. SSOT: [docs/CHART_RENDERING_ANTIPATTERNS.md](docs/CHART_RENDERING_ANTIPATTERNS.md) CHART-AP-32.

## v7.5.0 — 시각화 어휘 확장: 차트 4종 + 지구본 투영 + 사거리권 (사용자 요청, 식별→반영)

- **배경 (사용자 요청)** — "차트 유형에 더해 지도 유형·시각화 유형을 더 늘리자. 지구본
  지도 (탄도미사일·위성 토픽), 사회 이슈 차트, 이중 축 차트 등 상황별 시각화 기법을
  더 흡수. 식별 먼저, 그다음 반영."
- **식별 카탈로그 (선정 7 + 보류)**:
  - 선정 — 차트 4종 (guarded): `combo` (이중 축 막대+선 — 부피·건수 × 수준, dual_line
    의 자매), `diverging_bar` (대립 쌍 발산 막대 — 찬반·동의/비동의·유입/유출, 사회
    이슈·여론 기본 어휘), `pyramid` (인구 피라미드 — 연령 × 두 집단, 고령화·병력 구조),
    `dot_matrix` (100칸 와플/아이소타입 — '100명 중 N명' 사회 통계 체감).
  - 선정 — 지도 2종 (additive): `projection: "globe"` (정사영 지구본 — 대권 호가 직선,
    탄도 궤적·위성 통과·극항로·대양 횡단 토픽. 드래그=회전, 버튼=줌), `rings`
    (사거리권·작전반경·도달권 측지 동심원 — kind range/coverage, 평면·지구본 공통).
  - 보류 (후속 게이트) — radar (다축 왜곡 논란), histogram/beeswarm (원시 관측치
    파이프라인 부재), calendar heatmap, marimekko, ridgeline; chord/treemap 은 기존
    experimental 등재 유지 (렌더러 없는 orphan — 도입 시 5-Layer 절차로); 지도는
    azimuthal equidistant, proportional symbol (markers.value 로 부분 커버), hexbin.
- **차트 wiring (7-step 전체)** — `charts.js` 렌더러 4종 (combo 는 annotation 레이어
  지원, dot_matrix 는 largest-remainder 정확 100칸, pyramid 는 아래→위 적층 + 최대
  행만 세리프 라벨, diverging_bar 는 waterfall 의 pos=액센트/neg=하락색 계약) +
  composer SYSTEM_PROMPT (스키마 4종·emit 금지 규칙·결정 트리 분기 4개·사회 이슈
  anti-bias 가드) + `schemas.py` 가드 4종 (`_TYPE_TO_GUARD` / combo dict 분기) +
  `VISUAL_CAPABILITY_REGISTRY.yaml` (guarded 13→17, 총 26→30) +
  `usage_log.py:KNOWN_CHART_TYPES` + `chart_type_scenarios.yaml` 시나리오 4종
  (메타 25→29) + 회귀 테스트 11종 신규. 갤러리 베이스라인 4 fixture 추가.
- **지도 wiring** — `maps.js` 에 `renderGlobe` (orthographic, land merge 2-path 라
  드래그 재투영 저비용, 뒷면 마커/라벨 culling, 측지 arcs + 기존 kind 어휘 전부) +
  `drawRings` / `renderLegend` (range/coverage 글리프) 공용화 + 평면 renderMap 에도
  rings 연결. composer 지도 스키마에 projection/rings 추가 (radius_km 본문 근거
  강제 — WRITE-AP-5). 무지정 payload 는 기존 렌더와 byte-equal (구 발행본 소급 안전).
  베이스라인: `samples/map_globe_v7_5.html` (가상 사거리 시나리오).
- 헤드리스 렌더 검증 — 신규 4종 차트 + 지구본 (회전·줌·사거리권) 스크린샷 확인.
  전체 회귀 실패 목록은 변경 전후 동일 (환경 의존 기존 실패 67건, 신규 0).

## v7.4.1 — report.video 에도 TTS 발화 채널 (사용자 확정)

- **계약 §13 additive** — `report.video.intro_narration_tts` / `outro_narration_tts`
  추가 (schema_version 1 유지). v7.4.0 이 섹션 narration 에만 표기/발화 분리를 적용해
  타이틀/클로징 씬의 "SpaceX" 류 표기가 음성에서 영어로 읽히던 갭 해소. 섹션
  `narration_tts` 와 같은 규칙 (같은 순서·개수, 위험 표기 없으면 생략).
- `BundleReportVideo` 필드 2종 + `ComposedReport.video` 정규화 키 + `_report_video`
  매핑·`_warn_tts_gap` 적용 + composer SYSTEM_PROMPT 규칙 6/JSON 예시 +
  가이드 §0 규칙 2-1. 검수 샘플 3건의 report.video 에 tts 채움.

## v7.4.0 — TTS 내레이션 발화 규칙 체계 (사용자 제공 가이드 반영)

- **문제 (사용자 지적)** — narration 을 JSON 에 채우게 되는데, 내레이션이 이상하게
  생성되면 TTS 발화가 매우 어색해지고 "AI가 만들었다"는 걸 듣는 즉시 알아챈다. AI 음성
  티는 기계음이 아니라 *사람이라면 절대 그렇게 안 읽는 표기 해석* 에서 난다 (16시를
  '열여섯 시', 2차전지를 '두 차 전지', 6월을 '육월', 7.68%를 '칠 점 육팔'…).
- **신규 SSOT 가이드** — [prompts/tts_narration_guide.md](prompts/tts_narration_guide.md):
  사용자가 작성한 53항목 TTS 오류 리스트를 Opus 작성 에이전트가 지킬 수 있는 규칙으로
  distill. 핵심 = ① 표기용(narration)/발화용(narration_tts) 분리 ② 숫자 이중 체계
  (개수·살·번=고유어, 차수·연도·금액·비율=한자어, 월 예외 6월→유월/10월→시월)
  ③ 영문 약어 한글 음·영상 내 통일 ④ 기호 의미 변환 ⑤ URL·파일명 미낭독 + 문장
  구어체·연쇄·강조 위치.
- **체계화 (3중)** — ① composer SYSTEM_PROMPT 에 "★ TTS 발화 규칙" 런타임 단축본
  주입(가이드와 정합) + narration_tts 를 "위험 표기 있으면 필수"로 격상 ② JSON 예시에
  narration_tts 추가 ③ `bundle_builder._warn_tts_gap` 결정적 탐지 — narration 에 TTS
  위험 표기가 있는데 narration_tts 누락/개수불일치면 warn (자동 재작성 X — 한자어/고유어
  문맥 의존이라 결정적 변환이 오히려 오독을 만든다, 가이드 원칙).
- **계약 §13 명문화** — 표기/발화 분리 + 가이드 SSOT 참조 (consumer 의미론·schema_version
  무변경, additive). 샘플 번들 2건(20260606 SpaceX / 20260611 삼성·SK)의 narration_tts
  를 가이드대로 채워 재생성.

## v7.3.1 — video narration 내레이터 페르소나 (사용자 지시)

- **composer SYSTEM_PROMPT "★ 내레이터 페르소나" 블록 신설** — narration 을
  *시사 교양 다큐 내레이션 작가 20년차* 가 되어 쓴다: ① 귀로 듣는 말 (한 번 듣고
  그림이 그려져야) ② 짧은 문장의 연쇄 — 앞 문장이 던진 것을 다음 문장이 받아 잇기
  (무관한 사실 나열 금지 = 기계 템플릿과의 차별점) ③ 한 문장 한 정보, 주어·서술어
  근접, 관형절 중첩 금지 ④ 명사 쌓기 대신 동사로 말하기 ('통항 정상화 가능성 대두'
  X → '뱃길이 다시 열릴 수 있습니다' O) ⑤ 쉽되 가볍지 않게 — 차분한 경어체, 감탄·
  유행어·수사적 질문 금지, 무게는 사실에서 ⑥ 숫자 최소화·전문 용어 평이화 (본문
  평이화 원칙과 동일, 단 §13 사실 근거 한계 안에서).
- 검수용 샘플 번들(`analysis_20260612_061311_2c19018118.bundle.json`) narration
  전체 + 계약 example 을 페르소나 문체로 재작성 (최장 48자, emphasis 부분 문자열
  관계·§8 검증 유지). 계약 §13 에 작성 페르소나 항목 추가 (consumer 의미론 무변경).

## v7.3.0 — report_bundle §13 video 내레이션 (osint_generator 계약, 사용자 확정)

- **계약 §13 (additive, schema_version 1 유지)** — 영상 파이프라인(osint_generator)의
  자막·내레이션이 고정 템플릿이라 기계적 + 차트 없는 서술 섹션이 영상에서 통째로
  누락되던 두 문제를, *내용을 가장 잘 아는 보고서 생성 시점* 에 producer 가 대본을
  emit 하는 것으로 해소. 계약 SSOT: [docs/CONTRACTS/report_bundle_v1.md §13](docs/CONTRACTS/report_bundle_v1.md).
- **`sections[].video`** — `{narration(2~4문장, 문장 ≤58자), highlights(1~3개, ≤40자),
  emphasis(정확한 부분 문자열만), narration_tts?(발음용)}`. **`report.video`** —
  `{intro_narration, outro_narration}` (타이틀/클로징 씬, 각 1~2문장).
- **emit 경로** — composer SYSTEM_PROMPT `=== 영상 내레이션 (video) ===` 신설
  (사실 근거: 같은 섹션 prose·구조화 데이터에 실재하는 수치·날짜·고유명사만 — 영상 쪽
  검증기가 불일치 문장 폐기·템플릿 폴백 / 다큐 브리핑체 / `<미검증>` 표기) →
  `ComposedSection.video` / `ComposedReport.video` (정규화 validator) →
  `bundle_builder._section_video` / `_report_video` 결정적 가드 (emphasis 부분 문자열
  불일치 drop + warn, narration ≤4 / highlights ≤3 / intro·outro ≤2 캡, 58/40자
  한도는 warn-only — consumer 의 … 절단이 정보 파괴보다 낫다).
- **WRITE-AP-12 정합** — `_sanitize_symbols` 가 video 텍스트도 정화 (narration 과
  emphasis 가 같은 변환을 거쳐 부분 문자열 관계 보존). V6 critic 루프의
  `_merge_text_revision` 은 원본 video 보존 (보완 응답이 video 를 내면 수용).
- **검증 플로우** — 최근 발행본 `reports/analysis_20260612_061311_2c19018118.bundle.json`
  에 video 필드를 채워 push (osint_generator 검수용 샘플). 계약 확정 기록은 양측 검수
  통과 후.

## v7.2.0 — 지도 어휘 격상 (사용자 승인, 발행본 소급)

- **ops** — VM-AP-9 등재 ([docs/VM_DEPLOY_PLAYBOOK.md](docs/VM_DEPLOY_PLAYBOOK.md) §2):
  봇 미러 산출물 `reports/README.md` 가 pull 을 상습 차단 (하루 3회 재발). §1 Stage 1
  에 자동 폐기 가드 추가 — 해당 파일 단독 잔재면 자동 `git checkout --` 후 진행.

- **동기(사용자 지적)** — 지도의 선·관계가 단조로움. 현행 어휘가 마커 2종(강조/일반 점)
  + 호 2종(실선/점선)뿐이라 봉쇄·회랑·대립·우회가 전부 같은 그림.
- **변경 (maps.js — 전부 additive, 무지정 payload 는 기존 렌더와 byte-동일 로직)** —
  - `arcs.kind`: **flow**(물색 헤일로+실선+방향 화살촉) / **alt**(우회 점선) /
    **tension**(하락색+중간 ✕) + `weight` 1~3 굵기 사다리 + `label_t`(경로상 라벨 위치).
  - arc 라벨 → 물색 pill (줌 시 마커처럼 카운터-스케일).
  - `markers.kind`: **chokepoint**(◆+이중 링) / **port**(이중 원) / **military**(▲) +
    `value`(세리프 보조 수치 행) + `label_side`(밀집 권역 라벨 힌트 — 기존 occupancy
    충돌 회피의 1순위 후보로 합류).
  - `regions`: 국가 역할 색조 — subject(액센트)/ally(잉크)/rival(하락색)/contested(45° 해치).
    world-atlas 영문 국가명 매칭, composer 명시 emit 만 (CHART-AP-14/15 유지).
  - `sea_labels`: 바다·해역 세리프 이탤릭 워터마크 (FT 지도 문법).
  - graticule 텍스처 + 해안 정의선 + 마커 라벨 paint-order 물색 헤일로.
  - 범례 kind 확장 (flow/alt/tension/chokepoint/military).
- **composer** — SYSTEM_PROMPT 지도 섹션에 신규 어휘 스키마·사용 원칙 (regions ≤4 /
  sea_labels ≤3 / markers·arcs ≤8, 본문 언급 근거 필수). `_clean_map` 이 regions/
  sea_labels/value 텍스트도 정화.
- **검증** — [samples/map_redesign_v7_compare.html](samples/map_redesign_v7_compare.html)
  좌측을 production+신규 스키마로 교체, headless 렌더로 목업과 동등 확인.
  베이스맵 로컬 사본 (samples/vendor/) 으로 차단망에서도 목업 동작.

## v7.1.0 — 초기 7종 차트 비주얼 격상 (사용자 승인, 과거 발행본 소급)

- **범위** — bar / donut / stacked / bubble / heatmap / network / waterfall. 목업
  ([samples/chart_redesign_v7_compare.html](samples/chart_redesign_v7_compare.html))
  승인 후 production charts.js 직접 이식 — **사용자 결정으로 발행본 소급 적용**
  (Cloudflare 재업로드 시 과거 보고서도 신 디자인).
- **공통 어휘** ([docs/MONO_THEME_GUIDE.md §10](docs/MONO_THEME_GUIDE.md) 신설) —
  해치 = 명목 카테고리 전용으로 환원, 순위·서수·구성 위계 = 단일 잉크 농도 사다리
  (≤4단) + 핵심 1개 액센트, 값 = Newsreader 세리프 직접 라벨, 그리드 최소·0-기준선 crisp.
- **타입별** — bar: 풀폭 트랙 + note 보조 행 + annotations 유지 / donut: 핵심 점유율
  중앙 큰 숫자 + 값 정렬 범례 (arc sweep 애니메이션·CHART-AP-16 유지) / stacked:
  **bar 문법으로 병합** (가로 세그먼트 막대 + 상단 범례, label→농도 일관 매핑 유지) /
  bubble: 중앙값 십자선 + 강조 1개 + 크기 범례 (CHART-AP-12 스케일 가드·annotations
  유지) / heatmap: 5칸 강도 트랙 + 등급 태그 / network: 갭 그리드 + 글리프 4종 +
  진영 색띠 + **영향 방향(▸) 보존** (기존 대칭 인코딩은 방향 소실; v5.5.5 골격·
  content-fit·CHART-AP-25 유지) / waterfall: 3색 의미론 + 부호 라벨 + 수평 라벨 —
  **neg row 가 magnitude 든 음수든 동일 동작** (CHART-AP-27 의 잔존 렌더 경로까지 봉합).
- entry 애니메이션 계약 (bar-grow / donut-arc / static 태그) 전부 보존. headless
  Chromium 으로 7종 전 타입 렌더·시각 검수.

## v7.0.2 — CHART-AP-31: 시계열 차트의 일별 밀도 보장 (사용자 catch)

- **동기(사용자 지적)** — "지수 차트는 캔들이든 라인이든 일별 종가가 기준이어야 —
  저렇게는 너무 정보가 없다." market_fetcher 는 일별 3M(~60거래일)을 공급하는데,
  차트 데이터를 composer LLM 이 손으로 emit 하는 구조라 토큰 절약으로 8~12 포인트로
  추려 쓰는 회귀 경로가 열려 있었다 (지시 준수 의존 — 보장 없음).
- **변경** — `orchestrator._densify_ts_charts` 신설 (결정적 0-LLM, 디폴트 ON):
  composer emit line/candle/area 차트를 title 의 instrument 로 실 series 와 매칭,
  차트 *자신의 날짜 창* 안 실 데이터 행이 더 많으면 전체 일별 행으로 교체.
  의도적 확대 창(사건 주간) 보존 / 단축 날짜 표기는 전체 series 폴백 / 이벤트 마커
  날짜·suffix 매칭 보존. type·제목·해석은 composer 권한 그대로.
- 갤러리(chart_gallery_v7.html) line/candle fixture 도 일별 밀도(62/40거래일)로 교체 —
  베이스라인이 실보고서 질감을 반영. 회귀 6케이스 (`test_ts_densify.py`).

## v7.0.1 — CHART-AP-30: 시장 시계열의 곡선 보간 왜곡 교정 (사용자 catch)

- **동기(사용자 지적)** — 지수/가격 line 차트가 부드러운 곡선으로 그려져 실제 가격
  움직임이 안 보임. `curveMonotoneX` 는 데이터에 없는 중간 경로를 그려넣는 왜곡.
- **변경** — line/area/dual_line/forecast(실측·cone·mid)/stacked_area/small_multiples
  `curveLinear` 통일 + connected_scatter 의 CatmullRom (점 사이 부풀음) 도 직선 연결.
  v5.2.9 sparkline 교정의 풀 카드 완성판. 예외 = bump (순위 축의 관례적 전환 연출).
- 개별 종목은 기존대로 candle (OHLC). CHART-AP-30 등재 — 신규 시계열 렌더러의 곡선
  보간은 기본 금지, 예외는 사유와 함께 등재.

## v7.0.0 — V7 Track C: 기준시점 계약 (정확하지만 시점이 틀린 시장 수치 차단)

- **동기(사용자 보고 회귀)** — 6/5 발행 보고서에 6/4 종가가 가용한데 본문이 6/1 종가를 인용.
  수치는 6/1 기준으로 *정확* 해서 codex 사실 검수가 통과시키고, 보완 패스(Opus)도 같은
  맹점을 공유해 루프가 "정확하지만 시점이 틀린" 문장으로 수렴 (WRITE-AP-22 신설).
- **근본 원인** — ① 작성·검수·보완 어디에도 "이 보고서가 어느 시점의 값을 필요로 하는가"
  계약이 없음. ② `MarketDataSourceGuard` 가 날짜 비앵커 — 본문 수치가 시계열의 *어느*
  종가와든 일치하면 통과 (AP-V7-5).
- **변경 (`V7_REF_FRAME`, default OFF = v6.2.0 byte-equal)** —
  - 결정적 가드 2종 신설 ([src/factcheck/deterministic_guards.py](src/factcheck/deterministic_guards.py)):
    `DateAnchoredMarketGuard` (날짜 명시 수치를 *그 날짜의* bar OHLC 와 대조 — 다른 날짜
    값 귀속 시그니처만 flag, low-FP) + `StaleAnchorGuard` (종목별 최신 인용 시점이 가용
    시계열보다 1거래일 초과 뒤처지면 flag — 직전 거래일 lag 허용, 종목별 최신 인용 기준).
  - `reference_frame` 계약 ([src/factcheck/reference_frame.py](src/factcheck/reference_frame.py)
    신설 — 종목별 최신 가용 일자·종가·전일대비, 0-LLM) 을 composer 작성 payload +
    codex 검수 프롬프트 + Opus 보완 payload **3곳에 동일 주입** (루프 양 패스의 맹점
    공유 해소).
  - codex error_class **`wrong_timeframe`** 신설 (사용자 게이트 승인 2026-06-11) —
    "사실로서 정확하지만 보고서 기준 시점과 다른 날짜의 값". recency_violation(출처
    신선도)과 구분. 잔존 시 `apply_landing` 결정적 drop (unsourced/market 과 동급).
  - 시점 지적엔 `timeframe_correction_hint` — time_series *최신* bar 의 종가·전일대비를
    역산해 Opus 보완 지시에 덧댐 (drop 전에 교체 우선, market hint 의 거울상).
  - 페르소나 동시 갱신 (SOP 준수): [prompts/codex_critic_persona.md](prompts/codex_critic_persona.md)
    ★기준시점 정합 포커스 + [prompts/market_factcheck_desk_v6.md](prompts/market_factcheck_desk_v6.md)
    §13 신설 + 치명적 등급에 wrong_timeframe 등재.
- **회귀** — `fact_discipline_scenarios.yaml` 에 `wrong_timeframe_01` (6/1↔6/5 케이스 박제),
  V7 가드 8케이스 + 루프 5케이스 + 프롬프트 게이트 4케이스 신규. flag OFF inert 검증 포함.
- **Track A — 차트 에디토리얼 확장 (additive — 발행본 소급 영향 0)** —
  - **신규 3종 (guarded tier, 7단 절차 완주)**: `bump` (시기별 순위 경쟁 — slope/line 이
    못 덮는 순위 축), `bullet` (실적 vs 목표/컨센서스 — target 양수 강제),
    `connected_scatter` (2변수 시간 궤적 — dual_line 과 구분, 진행 방향 화살촉).
    RENDERERS + SYSTEM_PROMPT 스키마·결정트리 + `_TYPE_TO_GUARD` 3종 + registry
    (guarded 10→13, 총 23→26) + `KNOWN_CHART_TYPES` + fixture 시나리오 + 회귀 테스트.
  - **annotation 레이어 개방**: 기존 bar/line/gantt/bubble/dual_line/forecast 에 더해
    candle/area/scatter/stacked_area/lollipop/range_bar (+신규 2종) wiring — 사건
    vline·임계 hline·국면 band·강조 point 를 어느 cartesian 차트에나. 기존 payload 에
    annotations 없으면 렌더 불변 (additive-by-construction). 차트당 ≤3 정제 (AP-V7-6,
    `_drop_invalid_charts` 합류). top 마진이 좁은 type 은 vline 잘림 회피 (필터/마진 확장).
  - **에디토리얼 헤더**: `unit_line` (단위·기간 라인) optional 필드 + `.chart-card-unitline`
    (additive CSS — 구 보고서 불변).
  - **A-0 갤러리 베이스라인**: `samples/chart_gallery_v7.html` — 전 23종 × 5테마 fixture
    갤러리 (Track A 후속 리디자인의 전·후 비교 기준). headless Chromium 으로 전 타입
    렌더 검증 (마크 0 차트 없음) + 신규 3종·annotation 데모 스크린샷 검수 완료.
  - 기존 20종 렌더러의 *비-additive* 비주얼 리디자인 (§1.2 의 축 경제·직접 라벨링
    일괄 격상) 은 A-0 갤러리 기준의 시각 리뷰 게이트 뒤로 — 그때 자산 버저닝
    (charts.v7.js, AP-V7-1) 발동. 본 릴리스의 charts.js 변경은 전부 additive 라
    발행본 렌더 불변.
- **Track B — 기승전결(起承轉結) 스크롤 아크 (`V7_SCROLL_ARC`, default OFF)** —
  freeform_essay 배경에 블러된 한자 워터마크 1자가 화면 중앙 고정, 스크롤 진행에 따라
  다음 단계 한자가 이전 한자를 *연속 보간* 으로 밀어올림 (역방향 동일 — 인터랙티브).
  - 매핑: `ComposedSection.narrative_phase` (composer emit, additive·Optional) +
    **위치 기반 결정적 폴백** ([src/visual/scroll_arc.py](src/visual/scroll_arc.py) —
    첫 섹션=기 / 중간=승 / 마지막 본문=전 / 쟁점=전 / 감시신호·타임라인·맺음=결, AP-V7-4).
    구 JSON·recompose·LLM 누락 전부 회복.
  - 렌더: freeform_essay.html **인라인** CSS/JS 만 — charts.js 등 공유 자산 불변이라
    발행본 소급 영향 0 (REFACTOR_V7_PLAN.md §2.5). 블러는 요소 1회 래스터 + transform
    보간만 (AP-V7-2), 색은 --fg-1 저알파 워터마크 (라이트 테마 알파 하향), 차트·본문
    정보는 불변·영구 (AP-V7-3, CHART-AP-18 상속).
  - prefers-reduced-motion / print → 백드롭 전체 숨김 (사용자 결정). flag OFF 렌더는
    v6.2.0 템플릿과 **byte-equal 검증 통과** (Jinja whitespace control).
- **마스터 플랜** — [REFACTOR_V7_PLAN.md](REFACTOR_V7_PLAN.md) (3-트랙: A 차트 에디토리얼
  리디자인 / B 스크롤 내러티브 아크 / C 기준시점 계약). 본 릴리스 = Track C (V7-C1~C3) + Track B (V7-B1) + Track A (V7-A0/A2 + annotation 개방).

## v6.2.0 — 테마 풀을 짙은(다크) 계열 중심 5종으로 재편

- **동기(사용자 요청)** — 라이트 톤 테마들을 빼고 짙은 계열 중심으로.
- **변경** — `ALL_THEMES` 풀을 7종 → **5종**:
  - 유지: `editorial_cream`(유일 라이트) · `burgundy_mono` · `midnight_indigo`
  - 삭제(풀+CSS 블록): `slate_steel` · `forest_sage` · `dusk_rose` · `paper_classic`
  - 신설(다크): `pine_forest`(짙은 녹색 + jade 액센트) · `graphite_slate`(짙은 회색 + copper 액센트)
  - 결과: 라이트 1 + 다크 4. 보고서마다 `random.choice` 는 동일.
- **신규 테마 토큰** — `midnight_indigo` 구조를 그대로 따라 전체 CSS 변수 세트
  정의 (bg/card/border/text/muted/accent/up/down/map-*/alias/bg-3/border-soft).
  다크 3종 액센트 구분: indigo=skyblue / pine=jade / graphite=copper.
- **동시 갱신** — `src/lens_policy.py:ALL_THEMES` · `src/templates/report.css`
  (4종 블록 삭제 + 2종 추가) · `samples/v5_themes_showcase.html`(5종 쇼케이스
  재작성) · `docs/CONTRACTS/report_bundle_v1.md`(theme id enum) · CLAUDE.md(3곳).
- **하위호환** — 이미 배포된 보고서는 정적 스냅샷이라 영향 없음. 삭제된 테마로
  생성된 옛 보고서를 *재렌더*하면 해당 CSS 블록이 없어 기본(editorial_cream)
  토큰으로 폴백 (깨지지 않음). `light_mono` 와 동일하게 풀에서만 빠지는 게 아니라
  CSS 까지 삭제한 점이 차이 — 4종은 완전 제거.
- **쇼케이스**: https://doroper98.github.io/agents_reviewer/samples/v5_themes_showcase.html

## v6.1.2 — GitHub 미러에 보고서 목록 README 자동 생성 (제목·날짜·링크)

- **동기(사용자 보고)** — 미러된 `reports/` 폴더가 `analysis_<timestamp>_<hash>`
  파일명만 나열돼 무슨 보고서인지 알 수 없었다.
- **변경** — `src/tools/github_mirror.py:build_reports_index()` 신설 — `reports/`
  의 `analysis_*.md` 헤더(첫 `# 제목` + `**Category:**`)를 싸게 읽어 **제목·날짜·
  분류·md/json/bundle 상대링크 표**를 `reports/README.md` 로 생성(최신순). GitHub 이
  폴더 화면 아래에 자동 렌더. `report_synthesizer.synthesize` 가 보고서 미러와 함께
  매번 갱신.
  - 파일명(`analysis_<id>`)은 system-wide `report_id` 참조라 **그대로 유지**(rename
    금지 — 텔레그램 링크·patch_report 계약 보존). 제목은 *별도 인덱스* 로만 노출.
  - `GitHubMirror.path_prefix` 프로퍼티 추가 — prefix 가 비면(루트 미러) 루트 README
    덮어쓰기 방지 위해 인덱스 스킵.
- **테스트** — `tests/test_github_mirror.py` 인덱스 빌더 2종(최신순/제목·링크/limit).
- **graceful** — 인덱스 빌드 실패해도 보고서 미러는 정상 진행.

## v6.1.1 — 번들 차트에 display(strip/full) 플래그 (영상 파이프라인이 스트립 vs 본문차트 구분)

- **동기(사용자 보고)** — 영상 제작 AI(osint_generator)가 보고서의 *작게 묶여
  나오는 보조 지표 스트립*(여러 종목 sparkline 한 줄)과 *본문에 크게 박히는 단일
  차트*(sankey/waterfall/gantt 등)를 구분 못 해 비주얼 배치가 어려웠다. 렌더러는
  `freeform_essay.html` 의 `ch.role == 'compact'` 로 이미 둘을 가르지만, 영상이
  읽는 `.bundle.json` 의 `BundleChart` 엔 그 신호가 없었다.
- **변경** — `BundleChart.display: str`("strip" | "full", default "full") 추가
  (계약 §12, **additive** → schema_version 불변). `bundle_builder` 가 렌더러와
  동일 규칙으로 매핑 — composed chart 의 `role == "compact"` → `"strip"`, 그 외
  → `"full"`.
  - `composed_report` JSON 은 이미 차트별 `role` 필드로 구분됨 (변경 불요).
- **동시 갱신** — `docs/CONTRACTS/report_bundle_v1.md`(§12 신설 + 스키마),
  `docs/CONTRACTS/report_bundle_v1.example.json`(parity), `docs/DATA_MODELS.md §5.5`,
  `tests/test_report_bundle.py`(display 매핑 회귀).
- **하위호환** — 구 consumer 는 필드 무시해도 무해. 구 번들 JSON 엔 없음 → 기본 "full".

## v6.1.0 — GitHub raw 미러 (pages.dev 를 막는 샌드박스 AI 도 보고서 직접 열람)

- **동기(사용자 보고)** — 텔레그램으로 받은 보고서 링크(`analysis-reports.pages.dev/
  …​.html` / `.md` / `.bundle.json`)를 다른 Claude(특히 Claude Code on the web 같은
  *샌드박스 컨테이너*)가 열지 못했다. 원인은 봇 차단도 파일 형식도 아니라, 받는 쪽
  AI 의 **egress 허용목록(network policy)** 에 `*.pages.dev` 가 없어 프록시가
  `403 host_not_allowed` 로 막은 것. 반면 `github.com` / `raw.githubusercontent.com`
  은 대부분의 샌드박스 허용목록에 포함된다.
- **변경** — 보고서 산출물(`.html`/`.md`/`.json`/`.bundle.json`)을 Cloudflare Pages
  배포와 *함께* 공개 GitHub repo 에도 미러하고, 텔레그램 메시지에
  `raw.githubusercontent.com/...` 링크(🤝 AI 직접 열람용)를 함께 싣는다. 받는 쪽 AI 는
  설정 변경 없이 보고서를 바로 읽는다.
  - 신규 [src/tools/github_mirror.py](src/tools/github_mirror.py) `GitHubMirror`
    (Contents API PUT, 파일 단위 업로드, 기존 파일은 sha update).
  - `Config.github_mirror_{token,repo,branch,path}` (env `GITHUB_MIRROR_*`).
  - `FullAnalysisResult.mirror_url` (raw HTML URL) — 메시지 사이트가 여기서
    `.md`/`.bundle.json` 파생.
  - 메시지 사이트 3곳 연결: `/analyze` (telegram_bot) + 일일 브리핑 + 장마감 브리핑.
- **Graceful degrade** — 토큰/repo 미설정 또는 네트워크 차단·HTTP fail 시 미러를
  건너뛰고 빈 `mirror_url`. Cloudflare 흐름·기존 메시지는 **byte-equal 불변**
  (`market_fetcher`/`image_fetcher` 와 동일 패턴).
- **설정** — `.env` 에 `GITHUB_MIRROR_TOKEN`(공개 repo Contents read/write PAT) +
  `GITHUB_MIRROR_REPO`(`owner/repo`) 추가 후 재시작. 미설정 시 기존 동작 그대로.

## v6.0.5 — 발행본 revision 을 major.minor 로 분리 (내용=정수부 / 표현=소수부)

- **동기(사용자 제안)** — `--rerender-only` 가 revision 을 아예 안 올려서, 차트
  레이아웃·정적 자산만 바꿔 재배포했을 때 "바뀐 게 맞나" 추적이 안 됐다.
- **변경** — revision 을 **major.minor** 로 분리:
  - `revision`(정수부) = **내용/데이터 수정** (`--replace`/`--add-footnote`/`--edit`/
    `--recompose`). 데이터 변경 시 소수부는 0 으로 리셋(새 내용 baseline).
  - `render_revision`(소수부, 신규) = **표현/레이아웃 수정** (`--rerender-only` —
    새 charts.js/CSS, 차트 정렬 등). 내용 그대로면 소수부만 +1.
  - 표기는 `FullAnalysisResult.revision_label` → `Rev 1.2` 처럼 한 덩어리(major.minor).
    진짜 소수가 아니라 `1.10 > 1.9`. hero eyebrow 가 `Rev {revision_label}` 렌더.
- **하위호환** — 구 보고서 JSON 엔 `render_revision` 없음 → Pydantic 기본 0 (`Rev N.0`).
- 동시 갱신: `src/models.py`(필드+property), `scripts/patch_report.py`(증가 로직),
  `freeform_essay.html`(표기), `docs/DATA_MODELS.md`, CLAUDE.md 핫픽스 시퀀스 SSOT.

## v6.0.4 — sankey 끝-컬럼 라벨 2줄 줄바꿈 (CHART-AP-21 재발 4, 비대칭 overhang 해소)

- **증상(사용자 재보고, IMG_2642)** — v6.0.3 코어 중앙정렬 후에도 우측에 큰 빈
  여백 → 여전히 좌측 치우침으로 보임.
- **근본 원인** — 끝-컬럼 라벨이 길면("Colossus 2 (블랙웰 GPU 55.5만 발주)" ~28자)
  그쪽 overhang 이 커진다. 코어를 중앙에 둬도 좌·우 margin 을 `max(overhang)` 로
  동일하게 잡으니 짧은 라벨 측에 `overhangL − overhangR` 만큼 빈 여백이 남아,
  코어는 수학적으로 중앙이어도 시각적 "치우침" 인상.
- **Fix** — 첫·마지막 컬럼의 긴 라벨을 **2줄로 줄바꿈**(`wrapEndLabel` — " (" 또는
  공백에서 접기, max ~14자/줄) + 노드에 세로 중앙정렬(`drawEndLabel`). overhang 이
  ~40% 줄고 좌·우 대칭에 가까워져, 코어 중앙정렬(v6.0.3)과 결합 시 빈 여백 최소화
  (≈pad) → 흐름이 빈 공간 없이 중앙. 중간 컬럼 라벨/수직 정렬은 불변.
- charts.js 만 변경. 발행본은 `patch_report.py <id> --rerender-only` 로 동일 URL
  재렌더 시 적용. CHART-AP-21 "재발 4" 항목 추가.
- **재발방지 SSOT 확정** — 4회 재발(v6.0.1~6.0.4)을 거쳐 끝-라벨 차트 중앙정렬의
  최종 해법을 `docs/CHART_RENDERING_ANTIPATTERNS.md` CHART-AP-21 "★ 최종 해법 (SSOT)"
  박스로 압축: **①렌더 후 getBBox content-fit ②노드 코어 기준 중앙정렬 ③긴 끝-라벨
  2줄 wrap 의 3종 결합** (하나라도 빠지면 재발). CLAUDE.md CHART-AP-21 한 줄도 정합
  갱신 — "중앙이 아니다" 회귀 시 margin 숫자 만지지 말고 3종 점검. (코드는 이미 main)

## v6.0.3 — sankey 흐름 코어 중앙 정렬 (CHART-AP-21 재발 3, bbox → 코어 기준)

- **증상(사용자 재보고, IMG_2641)** — v6.0.2 tight-fit 후에도 "중앙이 아니다".
- **근본 원인** — v6.0.2 는 **라벨 포함 bbox** 를 중앙에 뒀다. 좌·우 라벨 폭이
  비대칭(좌측 "Colossus 2 (블랙웰 GPU 55.5만 발주)" ≫ 우측)이면 bbox 중심은 맞아도
  *흐름 코어(노드/리본)가 넓은 라벨 반대쪽으로 쏠린다*. 사람 눈은 라벨이 아니라
  흐름 다이어그램의 중앙을 본다.
- **Fix** — 정렬 기준을 라벨 포함 bbox → **노드 코어**(첫 컬럼 `x0` ~ 마지막 컬럼
  `x1`)로 변경. 좌·우 여백 `m = max(overhangL, overhangR) + pad(14)` 로 동일하게
  잡아 ① 코어 중심 = viewBox 중심 ② `m ≥ 각 overhang` 으로 무클립. 짧은 라벨 쪽에
  여분 여백이 생기나 흐름은 정중앙. 수직 content-fit(CHART-AP-20)은 vy/vh 보존.
- charts.js 만 변경. 발행본은 `patch_report.py <id> --rerender-only` 로 동일 URL
  재렌더 시 적용. CHART-AP-21 "재발 3" 항목 추가.

## v6.0.2 — sankey 중앙 정렬 fix (CHART-AP-21 재발 2, expand-only → tight-fit)

- **증상(사용자 재보고, IMG_2629)** — v6.0.1 로 라벨 잘림은 사라졌으나 차트가
  *왼쪽으로 쏠리고* 오른쪽에 ~150px 빈 여백이 남음.
- **근본 원인** — v6.0.1 의 content-fit 이 **확장만(expand-only)**: `maxX =
  max(vx+vw, …)` 로 원본 우측 경계(W=760)를 유지. 컨텐츠 우측 끝(~608)과 760 사이
  ~150px 가 빈 채로 viewBox 에 들어가, `xMidYMid` 가 빈 공간 포함 전체를 중앙에
  놓으며 컨텐츠는 좌측 쏠림.
- **Fix** — `drawSankey` 수평 content-fit 을 **양쪽 tight-fit** 으로: viewBox x/width
  를 원본 프레임과 무관하게 content bbox + 동일 pad(14)로 설정(`x = bb.x - pad`,
  `w = bb.width + 2*pad`). 빈 여백 제거 → `xMidYMid` 가 컨텐츠를 폭에 맞춰 정확히
  중앙 배치. 수직 content-fit(CHART-AP-20)은 vy/vh 보존.
- charts.js 만 변경. 발행본은 `patch_report.py <id> --rerender-only` 로 동일 URL
  재렌더 시 적용. CHART-AP-21 "재발 2" 항목 추가.

## v6.0.1 — sankey 첫 컬럼 라벨 잘림 fix (CHART-AP-21 재발, 수평 content-fit)

- **증상(사용자 스크린샷, analysis_20260606_114653)** — Colossus sankey 의 첫 컬럼
  라벨이 "(Col 1, … MW, GPU 22만+)" / "(Col 2, … GPU 55.5만 발주)" 처럼 18~25자로
  길어지자, `text-anchor:end at x0-6 (≈82px)` 라벨이 음수 좌표로 빠져 앞부분
  "(Col 1, …" 가 viewBox 왼쪽 밖에서 잘리고 화면엔 "MW, GPU 22만+)" 만 남음.
- **근본 원인** — v5.4.7 의 `{left:80, right:120}` 고정 margin 은 ≤8자/≤15자 한국어
  라벨 가정. **고정 margin 은 라벨 길이가 가변인 한 항상 어떤 입력에서 깨진다.**
- **Fix** — `src/templates/static/charts.js:drawSankey` 끝에 **수평 content-fit
  viewBox** 추가: 모든 라벨이 렌더된 뒤 `svg.node().getBBox()` 로 실제 content extent
  를 측정해 viewBox 를 가로로 확장(라벨 overflow 포함). `preserveAspectRatio=xMidYMid`
  가 자동 중앙 정렬 → 차트가 살짝 축소되며 중앙으로 모이고 좌·우 어느 라벨도 안 잘림.
  수직 content-fit(CHART-AP-20)은 vy/vh 그대로 보존. getBBox 실패 시 try/catch 로
  기존 viewBox 유지(graceful). 교훈: 가변 라벨 SVG 는 고정 margin 이 아닌 렌더 후
  bbox content-fit 으로 프레이밍(network 재설계 CHART-AP-25 동일 원칙).
- charts.js 만 변경(Pydantic/코드/계약 무변경). 발행본은 `patch_report.py <id>
  --rerender-only` 로 동일 URL 재렌더 시 적용(인라인 charts.js 갱신).
- 문서 동시 갱신: CHART_RENDERING_ANTIPATTERNS.md CHART-AP-21 재발 항목 추가.

## v6.0.0 — 검수 강도 ↑: 실시간성 엄격 + 반복 섹션 제목 강제교정 (사용자 지시)

- **#1 실시간성(엄격)** — codex 검수 페르소나·지침에 *실시간성 최우선* 추가. 발행일
  (publication_date) 기준 데이터·시점·'오늘/현재/최근' 신선도를 매 보고서 가장 깐깐하게
  검수, 어긋나면 `recency_violation`(high) + 웹 최신값 확인. `_CRITIC_INSTRUCTIONS` +
  `codex_critic_persona.md` + `market_factcheck_desk_v6.md §2` 정합(SOP).
- **#2 반복 섹션 제목** — 동일 제목이 여러 섹션에 나란히 붙는 회귀를 *매 보고서 결정적*
  으로 잡음. `DuplicateHeadingGuard`(정규화 동일 제목 검출, low-FP) + **loop HARD 트리거**:
  codex 가 clean 이어도 제목 중복이면 revision 강제 → Opus 에 "각 섹션을 서로 다른 제목으로"
  강한 지시. codex 측도 `duplicate_heading`(high)로 병행 검수(페르소나 §12). nan 노출도 HARD.
  **실제 회귀 반영(사용자 스크린샷)** — 일반 섹션 제목 + **쟁점(모순) 섹션 제목
  (`contradictions_heading`)** + 헤드라인까지 비교(섹션-쟁점 제목 동일이 잦음). `contradictions_heading`
  을 `revise_for_facts` payload/merge 에 추가해 Opus 가 *교정 가능* (이전엔 넘기지 않아 못 고쳤음).
- 회귀 127 pass (dup guard 검출 / HARD 트리거 / 정상시 무트리거 유지). flag OFF byte-equal.

## v6.0.0 — 시장 수치 역산 교체 + 맥락·서사 검수 (R1·R2, 사용자 지시)

- **R1. 시장 수치 *교체*(drop 아님)** — `market_correction_hint`: 틀린 시장 수치의 *올바른
  값* 을 `time_series` 에서 역산(종목+날짜 → 종가·전일대비%)해 Opus 의 fix_instruction 에
  덧댐 → Opus 가 *정확값으로 교체*. 실측: "삼성 5/29 +10.1%" → "318,500, +7.78%"(차트와 일치).
  매치 실패 시 착지 drop 으로 폴백.
- **R2. 맥락·서사 정합 검수** — codex 검수자가 *문장 간 맥락* 도 본다. error_class
  `coherence_break`(비유·프레임 붕괴 — "세 채널"인데 "유가 채널" 등장) / `undefined_reference`
  (서두 정의 없이 'A/B'·약어 사용). 어디서 끊기는지 evidence_conflict + *어떻게 이으면 되는지*
  Opus 가이드를 fix_instruction 에. 페르소나 SOP 정합 — `codex_critic_persona.md`(런타임) +
  `market_factcheck_desk_v6.md`(전체 §11) + `_CRITIC_INSTRUCTIONS` 동시 갱신, 본문 작성 금지 보존(AP-V6-11).
- 회귀 124 pass.

## v6.0.0 — 시장 수치 잔존 처리 강화 (착지 drop + time_series 가드)

첫 실전에서 codex 가 "삼성전자 5/29 +10.1%"(실제 +7.78%)를 잡고도 *발행은 됐던* 문제
(market_data_mismatch 가 unsourced 가 아니라 착지 drop 대상이 아니었음) 해결. 사용자 선택 C.

- **A. 착지 확장** — `apply_landing` 이 잔존 `unsourced_number` + **`market_data_mismatch`**
  를 본문에서 drop. 시장 수치는 최우선(WRITE-AP-15) — 틀린 채 발행하느니 제거.
- **B. time_series 가드 공급** — `market_series_from_context` 가 `context.time_series` →
  {종목:[종가들]} 추출, `run_fact_guards` 가 자동 공급(이전엔 미공급으로 inert). 가드 v2:
  종목명 직후 *가격* 숫자만(날짜·% 제외, `_PRICE_RE`) + 시계열 *어느 종가와도* 불일치
  시만 flag(날짜 모호성 강건·low-FP).
- codex 프롬프트에 "시장 수치는 time_series 와 반드시 대조" 강조 → 1차 검수서 포착.
- 회귀 122 pass (market: level 불일치 검출 / 과거일 매치 FP 없음 / % skip / 착지 drop).

## v6.0.0 — V6 검수 가시성 개선 (status 문구·텔레그램 바이라인·로그 diff/태깅)

첫 실전 e2e 에서 드러난 가시성 결함 4종 일괄 보강 (사용자 피드백).

- **(a) status 문구** — "지적 N건 중 0건 정정"(=drop 0, Opus 보완을 0처럼 오인)을 "지적
  N건 **보완 반영**, K건 미해결"로. Opus 가 실제 고친 것을 정확히 표기.
- **(b) 텔레그램 바이라인** — `/analyze`·일일브리핑 완료 메시지에 `🔎 Opus 작성·Codex
  검수 — 지적 N건 보완 반영…` 첨부 (검수 수행 시만, `verification.text`).
- **(c) 로그 report_id 태깅** — 발행 후 `V6 [analysis_…id] 검수 요약: 식별·변경·잔존`
  한 줄 → `grep analysis_…id` 로 보고서별 검수 내역 추적 가능(이전엔 매칭 불가).
- **(d) diff 개선** — `_diff_span`: `V6 변경` 이 섹션 앞 140자 클립이라 변경이 뒤쪽이면
  "위아래 동일"로 보이던 회귀 → 공통 prefix/suffix 제거 후 *바뀐 부분만* + 문맥.
- 회귀 117 pass. 코드만(flag OFF byte-equal 유지).

## v6.0.0 (Phase V6-8) — per-fact provenance (가드를 데이터로 판정)

GAP-7. ContextAnalyst 가 각 사실에 출처일·단위·URL 을 구조화 emit → NoveltyDelta/Scope
가드가 *프롬프트 없이 데이터로* 판정. (지금까진 production 에서 source_dates/scope_notes 가
미공급이라 두 가드가 사실상 inert 였음 — provenance 가 이 데이터를 채워 가드를 실작동시킴.)
flag `V6_PROVENANCE` default OFF. **V6 전 Phase(0~8) 완료.**

- `ContextAnalysis.provenance: list[dict]` (additive·Optional, 구 데이터 호환). 각 항목
  {fact, source_date?, scope_note?, source_url?} — fixture evidence 와 동형.
- context_analyst `_PROVENANCE_BLOCK` (`_build_system_prompt` flag-gating, recency 와 직교).
- `run_fact_guards` 가 명시 인자 없으면 `source_dates_from_context`/`scope_notes_from_context`
  로 provenance 에서 데이터 공급 (provenance 비면 [] → inert = 기존 동작, byte-equal).
- codex 비전/critic evidence digest 에 provenance 추가.
- 회귀 `test_provenance.py` 7종(프롬프트 flag-gating/derive/scope·novelty 데이터 발화/inert). V6 116 pass.

## v6.0.0 (Phase V6-6) — 자율 보강 (critique 적립 → 소프트가드 → 승격 후보)

"Codex 가 매번 잡는 패턴이 시스템에 누적돼 스스로 강해진다" — 단 **적립↔적용 분리**
(AP-V6-9). flag `V6_AUTOLEARN` default OFF.

- **A. 적립(자동·안전)** — `src/factcheck/critique_log.py:append_critique` 가 모든 verdict
  지적을 `logs/critique_log.jsonl` 에 {error_class, signature, location, report_id, 날짜}로
  영구 적립. 코드/프롬프트 무변경.
- **B-1. 소프트가드 자동등재(log-only)** — `auto_register_soft_guards`: 동일 시그니처 재발
  ≥3 → `logs/soft_guards.yaml` 에 `mode: log_only` 로 자동 등재 + 로그. 정규 가드/프롬프트
  불변 (오판이어도 피해 0).
- **B-2. 정식 승격(사람 게이트)** — `promotion_candidates`: 재발 ≥8 시그니처를 *로그로 표면화만*.
  정규 가드/`SYSTEM_PROMPT`/fixture/AP-N 편입은 사람 확인 후에만 (자동 편입 금지, AP-V6-9).
- orchestrator 가 루프 후 flag-gated 로 적립+자동등재+후보 표면화. `CriticLoopResult.claim_records`.
- 회귀 `test_critique_log.py` 7종(적립/재발 임계/idempotent 등재/승격 임계/graceful). V6 109 pass.

## v6.0.0 (Phase V6-7) — 검수 바이라인 (버전 명시 신뢰 도장)

발행물 말미에 "Claude Opus 4.7 작성 · OpenAI Codex (gpt-5.5) 사실 검수 — 지적 N건 반영"
도장. 독자에게 보이는 신뢰 surface (생성 중 라이브 status 의 발행 후 짝). flag `V6_BYLINE`.

- **버전 명시** — 작성 모델은 config SSOT(`NarrativeComposer.COMPOSER_MODEL` → "Claude Opus
  4.7"), 검수 모델은 **codex 배너 실측**("model: gpt-5.5" 파싱, 하드코딩 금지). `_pretty_writer`.
- **조건부 렌더 (AP-V6-10)** — critic 이 *실제 수행* 됐을 때만. degrade/skip/flag OFF 시
  `ComposedReport.verification=None` → 바이라인 생략(거짓 신뢰 금지). `critic_label` 빈값으로 가드.
- `build_verification_byline` (위반 수·미해결·웹대조 반영) → `composed.verification.text` →
  `freeform_essay.html` footer `.footer-byline`(accent 색).
- 회귀 `test_codex_loop.py` 바이라인 6종(버전/clean/미해결/label 전파/skip 무바이라인). V6 102 pass.

## v6.0.0 — V6 사실 거버넌스 (Codex 외부 critic 루프) 정식 릴리스

2026-06-01 일일 브리핑 팩트체크 회귀(자유 본문에 evidence-binding 부재 + fact-critic 루프
부재)에서 출발한 V6 트랙의 코어가 라이브. 외부 모델 `codex`(ChatGPT 구독)가 Claude(Opus)
본문의 사실 결함을 *교차 검수* 하는 bounded 루프를 orchestrator 에 연결.

**4층 사실 거버넌스 (전부 opt-in flag, default OFF = v5.8.8 byte-equal):**
1. **검색** — ContextAnalyst 최신성 제한 (`V6_RECENCY_BOUND`): 당일/최근 브리핑 24~48h 출처.
2. **작성** — composer 사실규율 프롬프트 (`V6_FACT_PROMPT`): 시장 단일소스·시점 라벨·scope·
   신규성·귀속·인과 헤지 (WRITE-AP-11/14~21 작성단계 차단).
3. **가드** — 결정적 사전필터 5종 (`V6_FACT_GUARDS`): unsourced/scope/novelty/market/nan, 0-LLM.
4. **루프** — Codex critic (`V6_CODEX_CRITIC`): `Opus 작성 → Codex 검수 → Opus 보완(≤1) →
   Codex 확인패스(≤1)` (제어 0-LLM). + 차트 미학 비전 검수 (`V6_CODEX_VISUAL`) + 웹 verify
   (`V6_CODEX_WEBVERIFY`).

**불변식**: 본문은 Opus 고정(Codex 는 지시만, 본문 안 씀 — AP-V6-11) / 모든 지적 근거 인용
강제(AP-V6-8) / 외부 실패 graceful degrade → 단일패스(AP-V6-12) / 재작성·확인패스 각 ≤1 bound
(AP-V6-2). 생성 중 라이브 status + 잔존 정직 착지(미해결 시 신뢰도 하향, 검수 안 했으면 "건너뜀"
표시 AP-V6-10). 검수 페르소나 SSOT `prompts/market_factcheck_desk_v6.md` + 런타임 단축본.

**검증**: 회귀 97종(모킹) + VM e2e — NVIDIA 표본 위반 4→0 수렴(scope/unsourced/novelty 교정),
실토픽(예측) 풀 파이프라인 발행 구독자 품질, codex 비전(차트 판독+미학 지적)·웹검색(정답+URL)
실연동. 측정 SSOT `docs/V6_TEST_RESULTS.md`. 마스터 플랜 `REFACTOR_V6_PLAN.md`.

**남은 것 (post-v6.0.0)**: Phase 6(자율보강 critique_log)·7(발행물 바이라인)·8(per-fact provenance).

## v5.8.8 (V6 Phase V6-5) — Codex 웹 verify (bounded)

GAP-2/9 — 우리 근거에 *없는* 사실까지 codex 가 자체 웹검색으로 ground truth 대조.
오늘 e2e 캐비엇("블랙웰 300" 류 내부정합은 맞지만 외부 미검증)을 닫는 단계. 웹은 변동 →
`V6_CODEX_WEBVERIFY` ON 만 비결정, OFF byte-equal.

- `critique()` webverify-aware (config flag) — cmd 에 웹검색 인자(`codex_websearch_args`,
  기본 `--enable web_search`) + 프롬프트에 `=== 웹 verify (bounded ≤N) ===` 블록(근거 없는
  사실만 ≤N 검색·URL 인용 강제·URL 못 대면 지적 안 함, AP-V6-8).
- `_build_cmd`/`_call_codex_cli` 에 `webverify` 파라미터. `codex_websearch_cap`(기본 3) bound.
- `_coerce_verdict` — claim 의 `source_urls` 를 `cited_urls` 로 집계(웹verify URL 추적).
- 회귀 `test_codex_webverify.py` 6종(웹검색 인자/프롬프트 블록/cap/flag OFF 불변/cited_urls 집계). V6 96 pass.
- **남은 것(VM)**: codex `exec` 가 실제 웹검색을 하는지 + `--enable web_search` 정확한 형태 실연동.

## v5.8.8 (V6 Phase V6-4) — Codex 미학 검수 (vision, 렌더 PNG)

GAP-8 — 차트 데이터뿐 아니라 *미학* 까지 교차모델(codex 비전)이 검수. Phase 1 에서
`codex exec -i` 이미지 입력 지원 확인됨. 현재 발행 후 log-only(측정) — 차트 자동수정은
안 함(V5 deterministic_gate / chart_critic 와 병행). flag `V6_CODEX_VISUAL` default OFF.

- **`CodexCritic.critique_visual(report, image_paths)`** — 차트 PNG 를 codex 비전(`-i`)에
  넣어 미학·데이터 정합 검수. `_VISUAL_INSTRUCTIONS`(가독성/잘림/패턴충돌/축누락/데이터
  불일치/빈프레임) + chart data digest(숫자 대조). FactVerdict 계약 재사용(model_label
  "OpenAI Codex (vision)").
- **`critique_report_visuals(report, html_path)`** — `src/visual/capture.py:capture_proofs`
  로 차트 PNG 캡처 → critique_visual. Playwright/codex 비전 미가용 시 graceful skip.
- `_call_codex_cli` / `_build_cmd` 에 `image_paths`(→ `-i`) 지원.
- orchestrator 발행 후 flag-gated 훅(log-only): 미학 지적을 `V6 미학 지적:` 로 로그.
- **budget telemetry V6-aware** — critic 루프의 Opus 보완 1콜을 cap 에 반영(헛경고 제거).
- 회귀 `test_codex_visual.py` 6종(이미지 -i 전달/verdict 파싱/flag·이미지 degrade). V6 91 pass.
- **남은 것(VM)**: codex 비전이 실제 차트 PNG 를 검수하는지 실연동 1회 + 자동수정 통합 여부 측정.

## v5.8.8 (V6) — Codex 검수 루프 라이브 status (텔레그램/CLI 진행 표시)

루프가 logger 만 찍고 `status_callback` 미연결이라 사용자가 검수 단계를 못 보던 것
보강. 검수+보완이 ~35s+ 지연을 더하는데 표시가 없으면 "왜 멈췄지" → 라이브 진행 +
신뢰 신호(생성 중 버전). Phase 7 바이라인(발행 후 도장)의 *생성 중* 대응물.

- `CriticLoop.run(..., on_progress=콜백)` — 단계별 status emit. orchestrator 가
  `self._notify` 래퍼를 주입(텔레그램/CLI 양쪽).
- 흐름: "🔎 외부 팩트체크 데스크(Codex) 교차검증 중…" → 위반 0 "✅ 사실 검수 통과" /
  위반 N "✍️ 편집장(Opus) 지적 N건 반영 중…" → "✅ 사실 검수 완료(잔존/미해결 정직 표시)".
- **degrade 시 "건너뜀" 으로 정직 표시**(검수 안 했는데 "통과" 거짓말 안 함, AP-V6-10).
- flag OFF 면 루프 미동작 → status 0 (byte-equal). emit 실패가 검수를 막지 않음.
- 회귀 `test_codex_loop.py` progress 4종(clean/violation/skipped 정직/None 안전). V6 83 pass.

## v5.8.8 (V6) — 루프 완결성 보강 (예방·가시성·정직한 착지)

e2e 에서 보완이 새 프레이밍("PC 칩 복귀")을 끌어들여 residual 이 생긴 것을 발견 →
완결성을 "0 보장"이 아니라 *예방+가시성+정직 착지+bounded* 로 확보. (사용자 방향 (a).)

- **① 예방**: `REVISE_SYSTEM_PROMPT` 규칙 7 — 고치면서 근거 없는 *새* 주장·프레이밍
  ('복귀/최초/사상 최대/직격탄/사실상') 도입 금지. 한 결함 고치다 새 결함 심는 것 차단.
- **② 가시성**: `CriticLoopResult.residual_summary`(잔존 claim 사람-읽기 요약) +
  `unresolved_count` + orchestrator 로그 노출. 잔존이 *뭔지* 보임(기존 카운트만).
- **③ 정직한 착지**: drop 으로 해소 안 된 잔존이 남으면 "깨끗한 척" 발행 안 하고
  `confidence_score` 정직 하향(−0.1/건, 0.3 floor). 비-unsourced 잔존은 prose surgery
  대신 신호로만(AP-V6-10 사상). bounded(재작성≤1) 유지 — 무한 루프 금지(AP-V6-2).
- 회귀 `test_codex_loop.py` 보강(미해결 카운트/신뢰도 하향/잔존 요약/예방 프롬프트). 73 pass.

## v5.8.8 (V6 Phase V6-3) — Bounded Codex critic 루프 (orchestrator 연결)

V6 의 심장 — `Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1)` 루프를
orchestrator 에 연결. `V6_CODEX_CRITIC` OFF 면 블록 통째 스킵 = v5.8.8 byte-equal.
플랜: REFACTOR_V6_PLAN.md §3 Phase V6-3.

- **`src/factcheck/critic_loop.py`** — `CriticLoop`(루프 제어 0-LLM, 위반 카운트로 결정),
  `CriticLoopResult`, `apply_landing`(잔존 `unsourced_number` 만 결정적 drop),
  `NarrativeComposerReviser` 어댑터. 재작성 ≤1·확인패스 ≤1·결정적 종료. degrade/보완
  실패 시 원본 보존 (AP-V6-12).
- **`NarrativeComposer.revise_for_facts`** — Codex `fix_instruction` 을 받아 *지적된
  부분만* Opus 가 재작성 (AP-V6-1/11, 본문은 Opus 고정). `REVISE_SYSTEM_PROMPT` +
  텍스트-only 출력 → 코드가 원본에 merge (차트/이미지/신호 보존). 파싱·호출 실패 시 원본
  반환. `_call_cli`/`_call_api` 에 `system_prompt` override 추가 (기본 None=compose 경로 byte-equal).
- **orchestrator Phase 2.5** — composer + ensure-hooks 후, `_sanitize_symbols` 전에
  flag-gated 삽입. 사전필터(Phase 2) 신호를 Codex pre_flags 로 합류 (단 재작성 트리거는
  Codex 위반에만 — 가드 FP 가 본문 안 망침).
- **회귀 T-3/T-4** (`test_codex_loop.py`, 9종) — flag OFF passthrough(critic 0콜)/degrade/
  clean 무보완/위반→보완→확인 수렴/unsourced 착지 drop/bound(재작성·확인 각 1회 강제)/
  보완실패 원본보존/사전필터 합류. 전체 66 pass.
- **VM e2e 수렴 (완료, 2026-06-03)**: 실제 codex(gpt-5.5)+Opus 루프가 NVIDIA 표본 4위반
  (scope/unsourced/novelty)을 보완 1회·확인패스 1회로 **위반 0 수렴**. 130만→"랙 전체",
  "27년 만" 제거, GR00T "오늘 공개"→"3월 GTC, 신규 아님" 정확 교정. Phase V6-3 DoD 충족.

## v5.8.8 (V6 Phase V6-2) — 결정적 사실 사전필터 가드 + 프롬프트 하드닝 + 검수자 페르소나

codex 호출(=ChatGPT 한도) 전에 *명백한* 사실 위반을 0-LLM 으로 거르는 결정적 가드.
전부 flag OFF default + orchestrator 미연결 = byte-equal. 플랜: REFACTOR_V6_PLAN.md §3 Phase V6-2.

- **`src/factcheck/deterministic_guards.py`** — 5종 가드 (log-only, drop 안 함):
  `UnsourcedNumberGuard`(근거에 없는 정량 주장) / `ScopeBarewordGuard`(근거가
  "X 단위 아님" 경고한 X 에 대형 수치 귀속) / `NoveltyDeltaGuard`(출처일↔발행일 차 +
  신규성·상대시점 단어) / `MarketDataSourceGuard`(시장 수치 ±tolerance 불일치) /
  `NaNExposureGuard`(본문·차트 nan 노출). `run_fact_guards()` 집계 → `GuardFlag` 목록,
  Phase 3 에서 `CodexCritic.critique(pre_flags=...)` 로 합류.
- **검수자 페르소나 훅 + 실제 페르소나** — `CodexCritic(config, persona=...)` +
  `V6_CODEX_PERSONA_PATH`(기본 `prompts/codex_critic_persona.md`). GPT 협업 산출물
  "시장 브리핑 팩트체크 데스크" 채택: 전체 기준서 `prompts/market_factcheck_desk_v6.md` +
  런타임 단축본 `prompts/codex_critic_persona.md`(10개 검수 포커스·회의적 기본·심각도
  매핑·금지사항). **출력 형식만 우리 `FactVerdict` JSON 계약으로 오버라이드**(페르소나의
  산문형 데스크 보고서 형식은 파서와 충돌 → 미채택). *검증 기준*이지 작성 페르소나 아님
  (codex 는 본문 안 씀, AP-V6-11). 파일 없으면 graceful 빈값 = byte-equal.
- **flag**: `V6_FACT_GUARDS`(default OFF). `.env.example` 갱신.
- **회귀 T-1** (`test_fact_discipline.py`) — 결정적 타깃 5종 100% 검출 + good_prose 0-FP +
  NaN/clean/pre_flag seam. 의미 판단 케이스(threshold/event/attribution/causal/metric/
  timepoint 앵커/list/FX sub-tolerance)는 Codex(Phase 3)로 명시 라우팅.
- **프롬프트 하드닝 (완료)**: composer `_FACT_DISCIPLINE_BLOCK`(`V6_FACT_PROMPT`) —
  SYSTEM_PROMPT 에 직교 추가, 시장 단일소스·시점 라벨·scope·신규성·귀속·인과 헤지 등
  WRITE-AP-11/14~21 를 작성 단계에서 선제 차단. `_compose_system_prompt()` 로 flag-gating
  (OFF=byte-equal). ContextAnalyst `_RECENCY_BLOCK`(`V6_RECENCY_BOUND`) — 당일/최근
  브리핑 최근 24~48h 출처 우선 + 상대 시점 발행일 환산(`stale_sourcing` 차단),
  `_build_system_prompt()` flag-gating. 회귀 `test_fact_prompt.py` 6종(OFF byte-equal +
  ON 주입). **Phase V6-2 완료.**

## v5.8.8 (V6 Phase V6-1) — Codex CLI 통합 spike + FactVerdict 계약

V6 트랙(사실 grounding + 외부 Codex critic 루프)의 Tier 0 진입점. 전 V6 루프가
의존하는 *외부 codex CLI 경로* 를 먼저 증명하는 spike. 모든 신규 행동은 flag OFF
default 라 v5.8.8 byte-equal — orchestrator 에 연결하지 않았다(계약·degrade 검증만).
VERSION 미증가(릴리스 아님). 마스터 플랜: [REFACTOR_V6_PLAN.md](REFACTOR_V6_PLAN.md) §3 Phase V6-1.

- **`src/models.py:FactVerdict` / `CritiqueClaim`** — Codex verdict 계약. per-claim
  지적(location/error_class/quote/evidence_conflict/source_urls/fix_instruction/
  severity). 근거(evidence_conflict) 없는 지적은 모델 validation 이 거부 (AP-V6-8).
  보완은 Opus 가 수행 — Codex 는 본문을 쓰지 않는다 (AP-V6-1/11).
- **`src/agents/codex_critic.py:CodexCritic`** — codex CLI 를 headless 호출(프롬프트
  stdin → verdict JSON stdout). JSON 파싱 + 코드펜스 제거 + 절단복구
  (`_repair_truncated_json`, composer 대응물) + ungrounded claim 드롭. 외부 실패는
  **graceful degrade** (`FactVerdict.skip`): flag_off / codex_not_found / auth_failed /
  rate_limited / timeout / codex_error / parse_failed → 단일패스 발행 (AP-V6-12).
  호출 텔레메트리 JSONL 적립 (`logs/codex_calls.jsonl`, T-C3).
- **`src/config.py`** — `V6_CODEX_CRITIC`(마스터, default OFF) + `V6_CODEX_BIN` /
  `_SUBCOMMAND` / `_EXTRA_ARGS` / `_MODEL` / `_TIMEOUT_S` (VM spike 가 실제 호출 형태 확정).
  `.env.example` 갱신.
- **회귀 39종** — `tests/regression/test_codex_contract.py`(T-V1, 17) +
  `test_codex_critic.py`(T-C1/C2/C3, 22). codex 는 *모킹*(CI 결정적), 실연동은 VM 수동 1회.
- **문서**: DATA_MODELS §3.15 / CATALOGS §1 / REPO_MAP / 신규 [docs/V6_TEST_RESULTS.md](docs/V6_TEST_RESULTS.md)(append-only 측정 SSOT) 갱신.
- **VM 실연동 완료** (2026-06-03): codex-cli 0.136.0(gpt-5.5) e2e 검수가 NVIDIA 표본의
  scope_misattribution(130만=랙) + unsourced_number(27년)를 정확 검출(35.1s). stdin 입력·
  `-o` 클린 캡처(배너/echo/푸터 제거)·`-i` 비전 입력 지원 확정 → Phase V6-4 가능.
  DoD 전부 충족. 다음 = Phase 2(사전필터)·3(루프).

## v5.8.8 — fact-grid 가로 오버플로/비대칭 폭 fix

5·6개짜리 팩트 그리드가 한 셀만 가로로 길어지고 마지막 카드가 화면 밖으로 잘리던
회귀 수정 (사용자 보고). 원인은 `grid-template-columns:repeat(N,1fr)` 의 `1fr` 이
실제로는 `minmax(min-content,1fr)` 이라, `$4.99~5.50/hr` 처럼 끊기지 않는 넓은 값
셀의 min-content 가 균등분할을 깨고 그리드 전체를 컨테이너(780px) 밖으로 밀어낸 것.

- **모든 트랙을 `minmax(0,1fr)` 로** — 셀이 콘텐츠보다 좁아지는 것을 허용해 N개가
  항상 균등 폭으로 컨테이너 안에 들어옴 (오버플로/비대칭 근본 차단).
- **5·6개는 데스크탑에서 3-wide 로 줄바꿈** (6→3+3, 5→3+2) — 한 줄에 욱여넣어
  셀이 좁아 값이 잘리던 문제 해소. 7개 이상은 base(4-wide) 로 자동 wrap.
- **모바일(≤640px) 5·6개는 2-wide** (6→2+2+2, 5→2+2+1).
- 값/서브라벨에 `overflow-wrap:break-word;word-break:keep-all` 안전망 — 한글은
  단어 단위 유지, 긴 라틴 토큰만 필요 시 줄바꿈(인접 셀 침범 방지).
- 코드 경로/Pydantic 무변경. `freeform_essay.html` CSS 만. 이미 발행된 보고서는
  `patch_report.py <id> --rerender-only` 로 동일 URL 재렌더 시 적용. v5.8.1/v5.8.4
  의 세로 baseline 정렬(label `min-height:2.6em`)은 보존.

## v5.8.7 (plan) — V6 마스터 플랜 신설 + Fact-discipline 골든 fixture (Phase V6-0)

2026-06-01 NVIDIA GTC 보고서가 외부 팩트체크에서 받은 5종 사실오류(보드 130만
scope 오귀속 / "27년" 출처없는수치 / GR00T "오늘" 신규성 혼동 / 211.14 시점
과근접 / OEM 목록 축소)를 구조적 결함으로 진단. 근본 원인은 ① 자유 본문에
evidence-binding 미적용 ② fact-critic/검증 루프 부재(단일 패스).

- **[REFACTOR_V6_PLAN.md](REFACTOR_V6_PLAN.md) 신설** — "workflow → agent" 트랙.
  bounded FactCritic 루프 + 결정적 사실 가드 + per-fact provenance + 역할별 모델
  티어링(본문=Opus 고정, critic/plan=저가, control=0 LLM). 11 GAP / 11 REQ / 8
  Phase(3-Tier) / 테스트 플랜 T-0~8 / AP-V6-1~7. 모든 `V6_*` flag default OFF =
  v5.8.7 byte-equal.
- **Phase V6-0 착수**: `tests/regression/fixtures/fact_discipline_scenarios.yaml`
  (NVIDIA 5종 회귀 영구 보존, error_class 5종 동결) + `test_fact_discipline.py`
  (스키마·enum·분포 회귀 6종 통과). 코드 경로 무변경 (fixture+테스트만).
- 다음: Phase V6-1 (결정적 가드 + composer SYSTEM_PROMPT 사실 규율 블록 +
  WRITE-AP-15/16) — composer 프롬프트 변경이라 착수 전 체크인.

---

## v5.8.7 — 보고서 완료 알림의 "전체 보고서 목록" 링크 정정

보고서 완료 시 텔레그램이 보내던 `📁 전체 보고서 목록: …/` 링크가 **공개
인덱스(`/`)** 를 가리켰는데, 이 페이지는 v5.6.2 부터 목록을 노출하지 않는 빈
랜딩("보고서 목록은 공개되지 않습니다")이다. 라벨과 목적지가 모순돼, 눌러도
목록이 안 보이던 회귀.

- **Fix** (`telegram_bot.py`): 실제 목록 경로로 정정.
  - `ADMIN_INDEX_TOKEN` 설정 시 → `…/admin-{token}.html` (전체 목록 웹 페이지).
  - 미설정 시 → "전체 보고서 목록은 `/reports` 명령으로" 안내 (빈 랜딩 링크 제거).
- `.env.example` 에 `ADMIN_INDEX_TOKEN` 항목 추가 (그간 누락 — 발견성 개선).
- 참고: `/reports` 텔레그램 명령(관리자 전용)은 기존대로 전체 목록을 즉시 회수.

---

## v5.8.6 — 메타 없는 신호엔 [▶ 후속 보고 생성] 버튼 숨김 (죽은 버튼 제거)

v5.5.7 이전 생성 + JSON 백필 불가인 보고서(예: 5/2)는 후속 분석에 필요한
`report_meta` 가 없어, [▶ 후속 보고 생성] 버튼을 눌러도 "후속 분석 불가 —
부모 컨텍스트가 registry 에 없음" 으로 매번 막혔다. 누르면 죽는 버튼이 계속
노출되던 UX 문제.

- **Fix**: `_notify_signal_fired` 가 버튼을 붙이기 전에 `get_report_meta` 로
  부모 메타 존재를 확인 — `_activate_followup` 의 가드와 동일 조건
  (meta + event_description). 메타가 있으면 버튼 부착(기존 동작), 없으면 버튼
  대신 "구버전 생성이라 후속 제공 안 함 + `/analyze` 로 직접 지시" 안내 한 줄.
- 죽은 버튼이 사라지고, 작동 가능한 신호에만 버튼이 뜬다. v5.5.7 이후 보고서는
  영향 없음(메타 있음 → 버튼 그대로). 코드 1곳(telegram_bot.py).

---

## v5.8.5 — 옛 보고서 report_meta 백필 스크립트 (후속 버튼 복구)

v5.5.7 미만(특히 v5.4.9~v5.5.6 의 `MAX_CHAIN_DEPTH=0` 가드 +
`result.composed_report.scenarios` AttributeError 사이드이펙트)에 생성된
보고서는 `report_meta` 등록이 누락돼, 감시 신호의 [▶ 후속 보고 생성] 버튼을
누르면 "후속 분석 불가 — 부모 컨텍스트가 registry 에 없음" 으로 막혔다.

- `scripts/backfill_report_meta.py` 신설 — `reports/analysis_*.json`
  (FullAnalysisResult.model_dump) 에 *이미 저장된* 필드만 꺼내 백필. **LLM 0,
  재분석 없음** (orchestrator.py:1716 과 동일 추출 경로: event_description ←
  request, report_title ← composed_report.headline, scenarios ←
  scenarios.scenarios).
- **dry-run 기본** — `--apply` 없이는 DB 무변경. **메타 없는 것만** 등록
  (idempotent, v5.5.7+ 정상 메타 보존). JSON 없는(v4.4.0 미만) 보고서는 skip.
- 사용: `python scripts/backfill_report_meta.py` (목록 확인) →
  `--apply` (실제 백필). 코드 경로 무변경 — 운영 보조 스크립트만 추가.

---

## v5.8.4 — fact-grid 숫자 정렬 버그 fix (v5.8.1 margin-top:auto 제거)

v5.8.1 의 fact-grid 정렬이 sublabel(부가 설명) 줄 수가 카드마다 다르면 다시
어긋나던 버그 수정. `.freeform-fact-value` 의 `margin-top:auto` 가 큰 숫자를 카드
*바닥* 으로 밀어붙였기 때문에, sublabel 이 1줄인 카드(23.51% "역대 최고")와 2줄인
카드(D-2 "2026년 6월 3일 수요일")의 숫자 baseline 이 어긋났다.

- **Fix**: `margin-top:auto` 제거. label 의 `min-height:2.6em`(2줄 예약)은 유지 —
  큰 숫자가 *고정 높이 label 바로 아래* 에서 시작(위에서 정렬)하므로 sublabel 줄
  수와 무관하게 모든 카드의 숫자 세로 시작선이 일치.
- 모크업 `samples/factgrid_pullquote_redesign_compare.html` A안도 동일 수정.
- 데이터 계약 무변경, 7테마 자동 적용. 배포된 봇은 VM 재배포 시 반영.

---

## v5.8.3 — 미래 사건 카운트다운 발행일 기준 재계산 (WRITE-AP-14)

6/1 발행 보고서가 6/3 지방선거를 "사흘 앞으로 다가온" 으로 표기하던 회귀 수정.
6/1 → 6/3 은 이틀 뒤(모레)인데 "사흘"로 셌다 — "사흘"은 5/31 기준이며, 출처
기사(5/31 작성)의 카운트다운을 그대로 베낀 것.

- **원인**: v5.6.4 시점 앵커링 블록이 *과거* 방향("사흘 전")만 다루고 *미래*
  방향 카운트다운(D-N, "사흘 앞" / "내일" / "모레")은 언급이 없었다. composer 가
  웹 검색 출처의 상대 표현을 발행일 기준 재계산 없이 옮겼다. WRITE-AP-11 의 거울상.
- **Fix**: composer SYSTEM_PROMPT `=== 시점 앵커링 ===` 블록에 미래 카운트다운
  규칙 추가 — D-N·상대 표현은 publication_date 와 사건일의 실제 차이로 직접 셈하고,
  출처 문구를 그대로 옮기지 않으며, 불확실하면 'M월 D일' 절대 날짜만 쓴다.
- WRITE-AP-14 등록 (REPORT_WRITING_ANTIPATTERNS.md). 코드 변경은 prompt 1곳.

이미 발행된 보고서(analysis_20260601_060645…)는 VM 에서 `patch_report.py --replace`
로 핫픽스. 배포된 봇은 prompt fix 가 없어 VM 재배포 시 다음 보고서부터 반영.

---

## v5.8.2 — 기본 분석 모드 standard → deep

사용자가 "빠르게/짧게/요약" 등 fast 키워드를 *명시하지 않는 한* 모든 보고서를
deep 으로 생성. `token_budget.resolve_mode` 의 폴백을 standard → deep 으로 변경.

- 우선순위는 그대로: deep 키워드 우선(fast·deep 함께 오면 deep), fast 키워드만
  있으면 fast, 둘 다 없으면 deep(← 변경점, 기존 standard).
- 영향 범위: 일반 `/analyze` 에서 mode 미지정(None) 일 때만. daily_briefing /
  후속 보고서는 이미 `mode="deep"` 명시라 무영향. standard 는 호출부가 직접
  지정할 때만 진입.
- 동반 갱신: `resolve_mode_fallback`(regression helper 미러), golden_prompts.yaml
  의 expected_mode standard 7건 → deep, test_resolve_mode_keywords, CLAUDE.md
  Mode Routing.

배포된 봇 반영은 VM 재배포 필요. (mode 는 startup 무관 — 코드만 갱신되면 즉시 적용.)

---

## v5.8.1 — fact-grid 숫자 세로 정렬 + pull_quote 박스 재설계

보고서의 두 시각 요소를 다듬었다.

- **가로 카드(fact-grid) 숫자 정렬**: label 이 1줄/2줄로 섞이면 그 아래 큰 숫자의
  세로 시작선이 카드마다 어긋나 보기 불편하던 문제. `.freeform-fact-tile` 을 flex
  column 으로 바꾸고 `.freeform-fact-label` 에 `min-height:2.6em` (2줄 예약) +
  `.freeform-fact-value` 에 `margin-top:auto` → 큰 숫자 baseline 이 모든 카드에서 일치.
- **키 메시지(pull_quote) 박스 재설계**: 기존 `background + border-radius +
  border-left 4px` 의 전형적인 "AI 인용 박스" 룩 폐기. 배경·둥근모서리 제거 +
  좌·우 양쪽 가는 룰(accent 2px) + 이탤릭 세리프로 편집 디자인 인용 톤. 메시지는
  그대로, 감싸는 형상만 절제.
- 모바일 오버라이드 동반 갱신 (pullquote padding, fact-label min-height).
- 모크업: `samples/factgrid_pullquote_redesign_compare.html` (Before/After 비교).

7개 테마 모두 토큰(accent/fg/border-soft) 자동 적용. 데이터 계약 무변경.

---

## ops/2026-05-31 — VM 재배포 paste-safe + bot.log 백업 가드 오발 fix (VM-AP-7)

이번 세션 재배포에서 두 번 막혔다. 둘 다 §1 표준 절차의 구조적 결함이었고
VM-AP-7 로 등록 + 영구 차단.

- **SSH 세션 종료**: §1 블록을 raw 명령으로 SSH 에 붙여넣으면 Stage 1 의 `exit 1`
  이 *로그인 셸(=SSH 세션)* 을 종료해 접속이 끊김. → §1 전체를 `redeploy()` 함수로
  래핑 + `exit 1` → `return 1`. 붙여넣기 안전 (paste-safe).
- **bot.log 백업 dirty 오발**: Stage 5 가 만든 `bot.log.<ts>` 백업이 untracked 라
  다음 Stage 1 `git status` 가 "로컬 수정사항" 으로 오인해 매번 멈춤 (악순환).
  → Stage 1 을 `--untracked-files=no` 로 변경 + `.gitignore` 에 `bot.log.*` 추가.
- `docs/VM_DEPLOY_PLAYBOOK.md` §1 표준 절차 교체 + §2 VM-AP-7 append.

코드 변경 없음 (ops/문서) — VERSION 무증분.

---

## v5.8.0 — 후속 보고서에 '이 분석의 출발점' (원 보고서 제목 + 링크) 노출

후속(follow-up) 보고서를 읽는 사람이 원 보고서의 사건·가정을 함께 보며 입체적으로
이해하도록, 원 보고서로의 연결 고리를 후속 보고서 본문 **서두 + 매리말 양쪽**에 넣었다.

- **용어**: 본문에 "부모 보고서" 같은 내부 용어 대신 **'이 분석의 출발점'** (매리말은
  '이어서 읽기 — 이 분석의 출발점') 으로 노출. 일반 독자 우선 원칙.
- **데이터**: 원 보고서 헤드라인을 `report_meta.report_title` 에 신규 저장
  (`ComposedReport.headline` 출처). `ParentContext.parent_report_title` 필드 추가.
  제목 없으면 `parent_report_id` 폴백.
- **렌더**: `freeform_essay.html` 에 `.freeform-origin` 박스 — 서두(헤드라인·덱 아래,
  본문 읽기 전 맥락) + 매리말(closing 뒤, 다 읽고 원본으로 회귀). accent border-left,
  제목은 Newsreader serif + 클릭 링크. 후속 보고서일 때만 (`result.parent_context`).
  일반 보고서엔 미노출.
- **DB**: `report_meta` 에 `report_title` 컬럼 추가. 기존 DB 는
  `registry._initialize` 의 idempotent 마이그레이션 (PRAGMA 체크 → ALTER TABLE).
  구 행은 빈 title 로 안전 조회.
- 회귀 테스트: `TestReportMeta` 4종 (왕복 / 폴백 / no-op / 구 DB 마이그레이션).

배포된 봇은 이 기능이 없으므로 VM 재배포 필요. 마이그레이션은 봇 재시작 시 자동.

---

## v5.7.0 — 일일 브리핑 날짜가 하루 어긋나던 회귀 fix (KST timezone SSOT)

**증상**: 5/31 06:00 KST 에 트리거된 일일 브리핑이 제목·본문 전체에 "5/30" 을
박았다. 스케줄러가 만든 안내 메시지("2026-05-31 일일 브리핑 시작")와 분석 스코프
문구("Asia/Seoul 기준 2026-05-30 자정 이후 ~ 오늘 06:00")는 5/31 로 맞았는데,
완성된 보고서 제목("2026-05-30 아침 종합 브리핑")과 본문("오늘(5/30) 아침
풍경...")만 하루 전이라 인지부조화. WRITE-AP-11(시점 앵커링)의 더 깊은 원인.

**원인**: 봇이 도는 VM/컨테이너가 **UTC** 인데, 사용자에게 노출되는 '오늘'
날짜를 만드는 4곳이 timezone 없는 `datetime.now()` 를 썼다. 06:00 KST = 전날
21:00 UTC 이므로 naive `now()` 는 *전날* 을 돌려준다. 스케줄러만
`ZoneInfo("Asia/Seoul")` 로 올바르게 계산했고, ContextAnalyst 의 `current_date`
(composer 가 보는 '오늘' 의 진짜 출처) / NarrativeComposer 의 `publication_date`
/ bundle_builder 의 `fetched_at`·`generated_at` / models 의 `analysis_timestamp`
는 모두 UTC 기준 전날로 셌다.

**Fix**:
- `src/timeutil.py` 신설 — `KST` / `now_kst()` / `today_kst()` SSOT (stdlib 고정
  +09:00, tzdata 미설치 환경도 안전). 사용자 노출 날짜는 *항상* 이 모듈을 경유.
- 위 4곳을 KST-aware 로 교체. `report_synthesizer.py` 의 중복 `KST` 정의도 본
  모듈로 통합 (이미 `datetime.now(KST)` 로 올바르게 동작 중이었음).
- 부수 효과 — ReportBundle 의 `generated_at` 이 계약서(`docs/CONTRACTS/
  report_bundle_v1.md`)가 요구하는 `+09:00` offset 으로 정렬됨 (기존
  `.astimezone()` 는 VM 의 UTC offset 을 냄).
- `docs/REPORT_WRITING_ANTIPATTERNS.md` WRITE-AP-11 에 근본 원인(timezone) 보강.

배포된 봇은 이 fix 가 없으므로 VM 재배포 필요 (다음 일일 브리핑부터 날짜 정합).

---

## ops/2026-05-30 — VM 재배포 회귀 방지 체계 (VM_DEPLOY_PLAYBOOK)

이번 세션에서 VM 재배포가 두 번 막혔다. 모두 사전 예방 가능했던 회귀였고,
체계가 없어 같은 일이 반복됐다. SSOT 신설 + Claude 행동 규칙으로 차단.

### 신설: `docs/VM_DEPLOY_PLAYBOOK.md`

- **§1 표준 재배포 절차** — VM-AP-1~6 모든 가드 내장 idempotent 명령어 블록.
  사용자가 그대로 복붙. CLAUDE.md 의 SOP 가 본 §1 을 참조.
- **§2 VM-AP-N 카탈로그** (append-only):
  - VM-AP-1: pkill 후 graceful shutdown 대기 부족 → 두 봇 동시 가동 → 텔레그램
    Conflict (2026-05-30 발생, 15초 polling + SIGKILL fallback 으로 차단)
  - VM-AP-2: 새 실행 스크립트 git 100644 (실행 불가) — `bot-if-working` 사례.
    원칙: 새 실행 스크립트 안 만들기, 부득이하면 `git update-index --chmod=+x`
  - VM-AP-3: 삭제된 파일의 VM 잔재로 pull 충돌 (2026-05-30 발생, pull 전 git
    status 검사 가드)
  - VM-AP-4: 봇 옛 버전 가동 + 코드 갱신 후 버전 확인 누락 (2회 발생, Stage 3
    + Stage 6 의 명시적 버전·Starting 라인 확인)
  - VM-AP-5: 두 봇이 같은 bot.log 출력 → 진단 혼선 (잠재, mv 백업으로 차단)
  - VM-AP-6: requirements 변경 후 pip install 누락 (잠재, diff 감지 자동화)
- **§3 진단 명령어** — 봇 상태 / 보고서 진행 / composer 회귀 추적.
- **§4 새 회귀 등록 절차** — CHART-AP / WRITE-AP 와 동일 패턴.

### Claude 행동 규칙 추가 (`CLAUDE.md`)

- VM 배포 SOP 섹션을 playbook §1 참조로 교체. "🔴 Claude 행동 규칙: VM 명령을
  줄 때 반드시 playbook 의 모든 가드를 포함한 명령어를 그대로 제공" 명시.
- 단축 4단계 (`pkill / sleep 2 / nohup / tail`) 금지 — 이번 회귀의 원인.
- Change Propagation Matrix 에 "VM 재배포 회귀 발견 시 playbook §2 append + §1
  가드 추가" 행 추가.

> 이번 세션의 VM 재배포 회귀 4건 (VM-AP-1/2/3/4) 모두 사후 등록. 향후 동일
> 회귀는 §1 의 가드가 차단하고, 새 회귀는 §4 절차로 누적.

## [v5.6.9] — 2026-05-30

### 미국 빅테크/반도체 개별주 + 미국 지수 차트 지원 + 주제 우선 차트화

사용자 보고: NVIDIA 주제 보고서인데 차트에 삼성·하이닉스·KOSPI 만 뜸. 원인 —
`INSTRUMENT_REGISTRY` 에 미국 개별주가 아예 없어서(한국 개별주 삼성·하이닉스 2개뿐),
ContextAnalyst 가 'NVIDIA' 를 emit 해도 `resolve_instrument` 가 None → 데이터 못
가져옴 → 매치되는 삼성·하이닉스·KOSPI 만 차트화.

#### 추가 (`src/tools/market_fetcher.py:INSTRUMENT_REGISTRY` 11→24 종목)

- **미국 개별주 10종** (Yahoo, candle): NVDA(엔비디아)·TSLA(테슬라)·AAPL(애플)·
  MSFT(마이크로소프트)·GOOGL(알파벳/구글)·AMZN(아마존)·META(메타/페이스북)·AMD·
  TSM(TSMC)·AVGO(브로드컴).
- **미국 지수 3종** (Yahoo, line): S&P 500(`^GSPC`)·나스닥(`^IXIC`)·필라델피아
  반도체(`^SOX`).
- YahooFetcher 는 이미 범용 구현(임의 ticker OHLC) — 레지스트리 항목만 추가하면
  KOSPI/DXY 와 동일 경로로 fetch. 코드 변경은 레지스트리 + 프롬프트 + hook 뿐.
- 모두 무인증(yfinance) — API 키 불필요.

#### 주제 우선 차트화 (`orchestrator.py:_topic_priority_key`)

- 기존 `_ensure_time_series_chart` 는 'data 많은 순' 으로만 정렬 → 주제 주인공이
  아닌 종목이 먼저 뜰 수 있었음. v5.6.9 부터 3단계 우선순위: 제목(event_name)
  등장 > 요약(summary) 등장 > 그 외, 같은 그룹 안에선 data 많은 순. 'NVIDIA
  보고서엔 NVIDIA 차트' 보장 (제목 주인공은 data 적어도 primary).
- ContextAnalyst SYSTEM_PROMPT 에 "주제 주인공 종목을 instruments_mentioned 의
  *첫 번째* 로" 규칙 추가.

#### 동시 갱신 (Change Propagation Matrix)

`context_analyst.py:SYSTEM_PROMPT`(지원 종목 목록) · `orchestrator.py`(hook) ·
`tests/test_market_fetcher.py`(미국 종목 22 매치 + 오탐 회귀) · `.env.example` ·
CLAUDE.md · market_fetcher.py 헤더 표(KOSPI/KOSDAQ Source 드리프트 KRX→YAHOO 정정).

> 검증: resolve_instrument 정상매치 22/22 + 오탐 점검 + 주제우선 3단계 정렬 통과,
> 전체 compile OK. ⚠️ VM 재배포 필수 (+ yfinance 설치 확인 — 이미 requirements.txt).

## [v5.6.8] — 2026-05-30

### composer head-loss 회귀 픽스 — JSON 응답 시작이 빠지던 새 패턴 (WRITE-AP-13)

사용자 보고 (`analysis_20260530_130528`, Duration 1397s, "composer 호출 실패. 사실
자료만 표시."): v5.6.7 부분 살림(timeout 복구)에도 불구하고 또 minimal fallback.
로그 분석 결과 **timeout 안 났고 정상 종료**, raw 응답이 ``` ```json``` 직후 ``{``
가 아니라 ``      "prose": ...`` 처럼 sections 객체의 *중간 줄* 부터 시작 — 즉
LLM 이 SYSTEM_PROMPT 의 JSON 예시 들여쓰기(6 spaces)를 따라가다 응답의 시작 부분
(``{``, headline, deck, sections 배열 시작) 을 통째로 빠뜨림 (head-loss). 두 번
다 같은 회귀 → 재시도 무용.

#### 수정 (2중 방어)

- **근본 (`narrative_composer.py:SYSTEM_PROMPT`)**: JSON 예시 직전에 ★★★ 강조 박스
  추가 — "응답은 반드시 ``{`` 한 글자로 시작. 코드펜스 ``` ```json``` 직후 첫
  비공백 글자가 ``{`` 가 아니면 응답 *전부 무효*. 예시의 중간 줄(``      "prose":``
  / ``      "side_a":``) 부터 시작 금지" 명시. LLM 이 깊은 줄부터 출력하지 않도록 유도.
- **단기 (`NarrativeComposer._recover_head_loss`)**: 정상 파싱 + 절단 복구 모두
  실패하고, 응답 body 가 ``{`` 가 아니라 ``"key":`` 패턴으로 시작하면, ``{...}`` 로
  wrap 해서 부분 객체에서 ``prose``/``heading``/``kicker``/``lede``/``pull_quote``
  추출 → 1-섹션 ComposedReport 재조립 (confidence_score 0.3, summary "응답 시작
  부분이 누락돼 본문 일부만 복구함"). 0% fallback 대신 일부라도 살림.

#### WRITE-AP-13 신규 항목

LLM 이 SYSTEM_PROMPT 의 JSON 예시 들여쓰기를 따라가다 응답 시작을 누락하는 회귀.
JSON 예시가 들여쓰기된 예시를 포함할 때 빈발. 예시 들여쓰기 자체는 유지(가독성)
하되 명시적 instruction + 결정적 후처리 복구로 차단.

> 검증: 사용자 회귀 case1 (165자 prose 살림) + case2 (prose 없음 → 정상 None) +
> 정상 응답 + 빈 응답 + heading 포함 케이스 6/6 통과. ⚠️ VM 재배포 필수.

## [v5.6.7] — 2026-05-30

### AI 가 인지되는 기호 박멸 (마크다운 강조 + em/en dash) — 사용자 최우선 규칙 (WRITE-AP-12)

보고서·SNS 문구 등 봇이 생성하는 *모든* 사용자 노출 텍스트에서 `**`/`*`/백틱
(마크다운 강조) 와 긴 줄표 em dash `—` / en dash `–` 를 절대 쓰지 않는다. 사람은
잘 안 쓰는 기호라 "AI 가 썼다" 는 인상을 즉시 주기 때문. 사용자 최우선 규칙.

#### 2중 방어

- **프롬프트** (`narrative_composer.py:SYSTEM_PROMPT`): "★ 기호 금지 (최우선,
  WRITE-AP-12)" 블록 추가. 강조 기호 + dash 금지, 부연은 쉼표·마침표, 숫자 범위는
  `~`, 제목 부제 구분은 쉼표·줄바꿈.
- **결정적 후처리** (`NarrativeComposer._sanitize_symbols`): 파싱된 ComposedReport
  의 모든 사용자 노출 텍스트(headline/deck/heading/prose/pull_quote/lede/캡션/
  chart 라벨·note/watch_signals/contradictions/timeline_flow/map 라벨/
  broadcast_summary)에서 강조 기호 제거 + dash 자연 치환(삽입구 → 쉼표, 숫자 범위
  → `~`, 단어 인접 → 공백). URL·좌표·bool 보존.
- **모든 경로 보장**: orchestrator 가 `_ensure_broadcast_summary` 직후
  `_sanitize_symbols` 를 한 번 더 호출 — composer 정상 경로뿐 아니라 minimal
  fallback / hook 추가 텍스트 / context 기반 합성본까지 정화. broadcast 폴백의
  `_strip_inline_md` 도 동일 dash 규칙으로 확장.

> 검증: `_clean_text` 13케이스 + `_sanitize_symbols` e2e(중첩 구조 + URL/좌표 보존
> 23검사) 오프라인 통과, 전체 compile OK. ⚠️ VM 재배포 필수.

## [v5.6.6] — 2026-05-30

### composer 짤림(truncation) 근본 수정 + SNS 문구 강건화

사용자 보고 (`analysis_20260530_105701`): deep 보고서가 또 "사실 자료만 표시"
0% fallback 으로 짤림. Duration 1306초 = deep timeout 540s × 2회(재시도) + 컨텍스트
분석. 즉 composer 가 540초 안에 큰 deep 보고서를 못 끝내 **두 번 다 timeout →
부분 출력 통째 폐기 → 0% fallback** 회귀. v5.5.9 의 timeout 은 "무한 hang" 만 막고
(a) 큰 보고서엔 한도 부족 (b) 부분 출력 폐기 (c) 재시도가 같은 timeout 한 번 더
낭비 — 3중 문제를 남겼다.

#### 수정 (4중 방어, `src/agents/narrative_composer.py`)

- **부분 출력 살리기**: `_call_cli` 가 stdout 을 임시 파일로 받는다. timeout 으로
  proc 를 kill 해도 디스크에 남은 부분 출력을 `_ComposerTimeout.partial` 로 운반.
- **잘린 JSON 복구**: `_repair_truncated_json` 이 마지막 *완결 경계* (쉼표 직전 /
  `}`·`]` 직후) 까지 자르고 열린 괄호를 닫아 파싱. `_drop_invalid_sections` 가
  heading/prose 빠진 절단 섹션 제거. 완성된 섹션까지는 실제 내용으로 렌더.
- **timeout 후 재시도 안 함**: 또 timeout 날 뿐 — 살린 부분으로 끝내거나 중단.
- **timeout 상향**: deep 540→900s, standard 360→480s, fast 240→300s. 부분 살림이
  있으므로 한도 초과해도 완성 섹션은 건진다.

#### SNS broadcast 문구 결정적 폴백 (`src/orchestrator.py`)

- `_ensure_broadcast_summary` 추가. composer 가 `broadcast_summary` 를 비워 emit
  하거나(LLM 누락) timeout 부분 살림본이라 비어 있을 때, deck + 앞 섹션 prose 로
  친절한 평문을 합성 (최후 폴백 context.summary). 결정적 hook — LLM 미호출.
  composer 가 채웠으면 존중. 이제 텔레그램/일일브리핑이 SNS 문구를 *항상* 확보.
- 합성 텍스트는 평문화 (`_strip_inline_md` 로 `**`/`*`/`` ` ``/`_` 제거).

> 검증: JSON 복구 8케이스 + broadcast 폴백 7케이스 오프라인 통과, 전체 compile OK.
> ⚠️ VM 재배포 필수 (composer 안정화는 봇 재기동 후 적용).

## [v5.6.5] — 2026-05-30

### 두 버전 계보 통합 (lineage reconciliation)

`v5.5.5` 이후 배포 라인(main)과 기능 라인(v5.6.x)이 **두 갈래로 분기**해
`v5.5.6`~`v5.5.10` 버전 번호가 양쪽에서 중복 사용되는 회귀가 발생했다 (Execution
Rule #12 위반). 배포된 봇은 main 계보(`v5.5.11`)였고, X 공유 요약·composer
타임아웃/재시도·파싱 강건화 등은 v5.6.x 계보에만 있어 운영에 반영되지 않았다.

본 릴리스는 **v5.6.x 계보를 정본으로 확정**하고, main 계보(`v5.5.6`~`v5.5.11`)가
독자적으로 추가한 기능을 빠짐없이 cherry-pick 으로 이식해 단일 라인으로 합쳤다.

#### main 계보에서 이식된 기능

- **감시 신호 후속 보고 수동 활성화 버튼** (main v5.5.6): 신호 발화 알림에
  `[▶ 후속 보고 생성]` `InlineKeyboardButton` 동봉 + `CallbackQueryHandler`.
- **후속 보고 deep 모드 고정 + chain depth 제한 폐지 + 부모 메타 누락 가드**
  (main v5.5.7): `MAX_CHAIN_DEPTH` 상수 제거, 자동 폭주는 수동 버튼 모델로 차단.
- **silent except 가 묻고 있던 attribute access 3건 fix** (main v5.5.8):
  `result.composed_report.sections` / `.embedded_map`, `result.scenarios` 정정 —
  차트 type 기록·부모 report_meta 등록 실패 회귀 해소.
- **한국 장마감 자동 브리핑 + 시장 구조 해석가 페르소나** (main v5.5.9):
  `/market_brief_on|off|status` 명령 + `MarketBriefSubscriberRegistry` +
  `run_market_briefing_loop` + `prompts/market_briefing_persona.md` +
  `MARKET_BRIEFING_*` config 4종 (디폴트 17:00 KST, 기본 OFF).
- **`/status` 에 market brief 정보 추가 + `/watchlist` 4096자 한도 fix**
  (main v5.5.10).
- **composer `max_tokens` 1.5배 + headline/deck 평이화 + figcaption 정렬 fix**
  (main v5.5.11): `MAX_TOKENS_BY_MODE` fast 18K / standard 30K / deep 48K.
- **patch_report `--recompose`** (main, v5.5.5 후속): 저장된 사실 기반 보고서
  통째 재작성.

#### v5.6.x 계보가 이미 보유 (보존됨)

- composer 타임아웃 + 재시도 + "Extra data" 파싱 강건화 (v5.6.x 계보의 v5.5.9/
  v5.5.10 — "사실 자료만 표시" 중단 회귀 차단). main v5.5.11 의 max_tokens 증량과
  **공존** — 보고서 중단을 타임아웃·재시도·토큰증량 3중으로 방어.
- X 구독자용 broadcast 요약 + 보고서 URL 난수 토큰 (v5.6.1).
- 공개 인덱스 비공개 + `/reports` 관리자 토큰 URL (v5.6.2~v5.6.3).
- 발행일·사건일 시점 앵커링 WRITE-AP-11 (v5.6.4).

> ⚠️ **VM 재배포 필수.** 배포된 봇은 두 기능(X 공유 요약·composer 안정화)을
> 갖지 못한 main `v5.5.11` 이다. 본 통합본으로 재배포해야 두 문제가 동시에 해소된다.

## [v5.6.4] — 2026-05-29

### Fixed — 발행일과 사건일이 다를 때 시점 앵커 누락 (WRITE-AP-11)

5/29 발행 데일리 브리핑이 본문 첫 줄부터 "5월 26일 코스피 8,047 신고가..." 로
시작하고 "같은 시각, 환율 7거래일 연속..." 로 지속 상태를 사건일에 고정 → 독자에
게 "오늘 보고서인데 갑자기 사흘 전?" 인지부조화 회귀.

원인: composer SYSTEM_PROMPT 에 "오늘=발행일" anchor 가 없었고 payload 에도
`publication_date` 가 없어 composer 가 today 를 모름. context.date 는 사건일이
박혀와 본문 시제가 그날에 고정됐다. 데일리 브리핑 prompt 가 ContextAnalyst 에는
today 를 줬지만 composer 단까지 전달이 끊겨 있었다.

- `_build_unified_payload` 에 `publication_date` (datetime.now %Y-%m-%d) 주입.
- SYSTEM_PROMPT 에 **=== 시점 앵커링 ===** 신설:
  · 첫 단락에 시간 거리를 발행일 시점 표현으로 명시 ('지난 26일' / '사흘 전').
  · '같은 시각' / '같은 날' 표현 주의 — 시점을 사건일에 고정시킴.
  · 지속 상태(누적/연속)는 *발행일 현재* 기준으로 프레이밍.
  · publication_date == event.date 면 적용 불필요.
  · broadcast_summary 에도 동일 적용.

docs: WRITE-AP-11 등록(REPORT_WRITING_ANTIPATTERNS.md) + CLAUDE.md 카운트 11.

---

## [v5.6.3] — 2026-05-26

### Added — 관리자 비공개 목록 페이지 (즐겨찾기용 고정 unlisted 주소)

v5.6.2 에서 공개 목록을 없앤 뒤, 관리자가 웹에서 전체 목록을 *즐겨찾기* 로 보고
싶다는 요청. 비번 없이 일관되게 — *고정 난수* 주소의 비공개 페이지로 해결.

- `config.admin_index_token` (env `ADMIN_INDEX_TOKEN`) 설정 시 `_generate_index` 가
  공개 `index.html`(목록 없음) **외에** `admin-{token}.html` 도 생성 — 전체 보고서
  목록 + 토큰 URL 테이블. 토큰이 고정이라 한 번 북마크하면 주소 불변.
- 미설정 시 admin 페이지 미생성 (기존 동작). 두 페이지 모두 `noindex,nofollow`.
- `/reports` 가 admin 페이지 URL 을 상단에 함께 안내 (토큰 설정 시).

> 설정: `.env` 에 `ADMIN_INDEX_TOKEN=<긴 난수>` (예: `openssl rand -hex 8`).
> 북마크 주소 = `https://<project>.pages.dev/admin-<token>.html`. 토큰을 모르면
> 접근 불가 (unlisted). 진짜 인증이 필요하면 Cloudflare Access 권장.

---

## [v5.6.2] — 2026-05-26

### Changed — 공개 인덱스 목록 비공개 + /reports (관리자) 전체 목록 회수

v5.6.1 의 난수 URL 가드를 완성. 공개 `index.html` 이 전체 보고서를 나열하면 토큰
링크가 다 노출돼 가드가 무력화되던 구멍을 막음.

- **공개 `index.html`**: 보고서 목록·건수 제거 → "구독자 전용, 발급 링크로만 열람"
  안내만. `_generate_index` 가 더 이상 reports/ 를 glob 하지 않음.
- **`/reports` (텔레그램, 관리자 전용)**: 기존엔 공개 인덱스 링크만 던졌으나 이제
  최근 30건의 제목 + 생성일시 + **토큰 URL** 을 직접 회수. 모든 unlisted 링크를
  노출하므로 `_is_authorized` 게이팅 추가 (기존엔 무방비였음).

> 운영 필수: 구독자 서비스라면 `.env` 의 `ALLOWED_CHAT_IDS` 에 본인 chat_id 를
> 설정해야 `/reports`(및 다른 명령)가 외부에 열리지 않는다. 미설정 = 전체 허용.

---

## [v5.6.1] — 2026-05-26

### Added — X(트위터) 구독자용 broadcast 요약 + 보고서 URL 난수 토큰

- **broadcast_summary**: composer 가 보고서마다 `ComposedReport.broadcast_summary`
  로 친절한 평문 요약을 emit (해요/습니다 혼합, 문단당 2문장, 5~6 짧은 문단,
  라벨·이모지·불릿·AI 상투어 금지). 마지막 문장은 전체 보고서로 안내하되 *매번 다른
  표현* 으로 변주 (고정 문구 = AI 티). 텔레그램 완료 메시지에 **라벨 없이** 링크 앞에
  첨부 — 보고서를 안 봐도 맥락·핵심·시사점을 얻게. 비면 첨부 안 함(graceful).
  일일 브리핑 전송 경로에도 동일 적용. SSOT: narrative_composer SYSTEM_PROMPT
  `=== broadcast_summary ===` 블록.
- **보고서 URL 난수 토큰**: 신규 보고서 파일명을 `analysis_{YYYYMMDD_HHMMSS}_{10hex}`
  로 — 날짜·시각은 유지하되 `secrets.token_hex(5)` 난수를 덧붙여 추측 불가능한
  unlisted URL 생성 (구독자 전용 컨텐츠 가드). 재렌더(patch_report)는 토큰 보존.
  bundle/md/json 도 같은 stem 공유. 인덱스 날짜 파싱·patch 조회 호환.

> 주의: 난수 URL 은 "추측 불가(unlisted)" 가드일 뿐 인증이 아니다. 공개 인덱스
> 페이지가 모든 보고서를 나열하면 가드가 무력화됨 — 인덱스 비공개/게이팅은 별도 결정.

---

## [v5.6.0] — 2026-05-26

### Integrated — feature 브랜치 통합 (인접행렬 + prerender + slope fix + composer 복원력)

별도 feature 브랜치(`claude/ecstatic-newton-1OmQA`)에서 진행된 작업을 main 의
v5.5.5(평이화/각주)와 통합. 병렬 작업으로 양쪽이 v5.5.5 를 동시 사용 + patch_report
를 양쪽이 수정 → 본 통합에서 조율. **코드 충돌은 없었음**(main 의 평이화/footnotes 는
`ComposedSection.footnotes` 필드 + SYSTEM_PROMPT 추가로 additive — 본 작업의 차트
렌더러·prerender·composer 호출부와 무관). 단계별 상세는 DEVLOG 의 v5.5.6~v5.5.10 항목.

- **행위자 관계도 → 인접행렬 (CHART-AP-25)**: radial hairball 폐기, `drawNetwork`
  렌더러만 교체(데이터 계약 nodes/links 불변). 셀이 관계 type 인코딩 + 진영 정렬 +
  getBBox content-fit 중앙정렬.
- **ReportBundle B안 폴백 SVG prerender (계약 §5)**: 복잡 4종(map/choropleth/
  network/sankey)만 Playwright 격리 렌더로 `prerendered_svg` 채움. `asyncio.to_thread`
  로 이벤트 루프 밖 실행. graceful null. schema_version 무증분.
- **slope 차트 라벨 충돌 fix (CHART-AP-26)**: 동일/근접 값 다수 시 라벨 dodge + connector.
- **composer 복원력 ("보고서 중간 끊김 / 사실 자료만 표시" 회귀 fix)**: CLI 응답이
  degraded(10분+ 소요·짧음·JSON 뒤 잡설) → 파싱 None → confidence-0 fallback 되던
  문제. `_call_cli` mode 별 타임아웃(deep 540s) + `compose_unified` 1회 재시도 +
  `_parse_response` 를 `raw_decode` 기반으로 강건화("Extra data" 무시) + raw head 로깅.

### Coordination — patch_report 도구 일원화

main 의 `--replace`/`--add-footnote`/`--dry-run`(v5.5.5) 을 정본으로 채택. feature
브랜치가 별도로 추가했던 `--replace-text "OLD=>NEW"` 는 폐기(기능 중복). 보고서 용어
정정은 `python scripts/patch_report.py <id> --replace "OLD=NEW"` 사용.

---

## [v5.5.5] — 2026-05-26

### Added — 일반 독자 우선: 전문 용어 평이화 + 문단 하단 주석 (WRITE-AP-10)

**배경**: 사용자 — 보고서에 `rate card` / `rate limit premium` 같은 영어 표현·전문
용어가 풀이 없이 그대로 노출됨. "일반인이 이해할 수 있는 평이한 용어 + 어려운
전문용어는 문단 하단 주석" 을 본 시스템의 *최우선 가치* 로 요청.

**변경**:
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` — 본문 최상단에 "★ 최우선 원칙 —
  일반 독자 우선" 블록 신설. (1) 전문 용어·영어 표현·은어를 평이한 우리말로 바꾸고
  (2) 못 바꾸는 핵심 용어만 그 섹션 `footnotes` 로 문단 하단 주석. 다른 모든 문체
  지시에 우선. JSON 스키마에 `footnotes` 추가.
- `src/models.py:ComposedSection.footnotes` — `list[{term, explanation}]` 신규 필드.
  None / 비정형 항목 정규화 validator (빈 각주 카드 회귀 차단).
- `src/templates/archetypes/freeform_essay.html` — prose 직후 `.freeform-footnotes`
  "용어 풀이" 블록 (term + explanation) 렌더 + 7테마 토큰 CSS. 비면 안 그림.
- `docs/REPORT_STYLE_GUIDE.md` — §0.1 (최우선 가치 명문화) + §2.1 어휘표 확장
  (rate card / rate limit premium / 익스포저 / 가이던스 / 헤지 등) + §2.2 를 3단
  사다리 (평이화 → 괄호 풀이 → 문단 하단 주석) 로 재구성.
- `docs/REPORT_WRITING_ANTIPATTERNS.md` — WRITE-AP-10 신설 (append-only).
- `CLAUDE.md` / `docs/DATA_MODELS.md` — 최우선 가치 + 신규 필드 반영.

**범위**: ReportBundle (`BundleSection`) 은 footnotes 를 싣지 않음 — 계약 무변경
(additive). 기존 보고서 데이터는 footnotes 빈 list 로 호환.

## [v5.5.4] — 2026-05-25

### Fixed — `/bundle` 명령 `name 'json' is not defined` 크래시

`src/telegram_bot.py:_bundle_command` (v5.5.0 신설) 이 `json.load`/`json.dump` 를
쓰는데 모듈 상단에 `import json` 누락 → 첫 실행 시 `번들 생성 실패: name 'json'
is not defined`. `import json` 추가로 해결. (auto-attach 경로는 binary open 이라
무관, /bundle 재emit 경로만 영향.)

## [v5.5.3] — 2026-05-25

### Changed — ReportBundle 항상 emit + 텔레그램 자동 전송

**배경**: 사용자 — osint_generator 영상 제작에 `analysis_{ts}.bundle.json` 이 필요. 보고서+md 와 함께 번들도 텔레그램으로 받고 싶다.

**변경**:
- `src/agents/report_synthesizer.py` — 번들 emit 게이트를 `config.enable_report_bundle` *단독* 으로(항상 emit). `--bundle` 플래그(`request.emit_bundle`) 의존 제거 — 이제 모든 보고서에 동반. 번들 빌드는 결정론·LLM 0 이라 비용 무시 가능.
- `src/telegram_bot.py` — 분석 완료 시 `analysis_{ts}.bundle.json` 을 **문서로 자동 첨부** + pages.dev URL 안내. `/bundle <report_id>` 도 재생성한 파일을 첨부(기존 보고서 회수 경로). `/start` 도움말 갱신.
- `--bundle` 플래그는 no-op 으로 호환 유지 (orchestrator strip 보존).

**Change Propagation Matrix**: `src/orchestrator.py:VERSION` v5.5.2 → v5.5.3, `docs/CONTRACTS/report_bundle_v1.md` (트리거: 항상 emit), README/DEVLOG/본 CHANGELOG.

## [v5.5.2] — 2026-05-25

### Added — 시간 흐름도 (감시 신호 직후 capstone, 과거→현재→미래)

**배경**: 사용자 — "감시 신호 이후에 보고서 전체 흐름 맥락을 이해하도록 과거→현재, 가능한 주제는 향후까지 시계열 흐름도를 넣자."

**설계 (하이브리드)**: 재료가 이미 있음 — 과거는 `context.timeline`, 현재는 `context.date`, 미래는 바로 위 `watch_signals` 의 `deadline`. 감시 신호 직후 배치 = 방금 나열한 신호를 시간축 미래 마커로 흡수하는 synthesis (중복 아님).
- `src/timeline_flow.py` (신규) — `build_timeline_flow(context, composed)`: 결정론 backbone (timeline + watch_signals) + composer 선택적 윤색 병합. render(report_synthesizer) 와 emit(bundle_builder) 가 공유.
- `src/models.py:ComposedReport.timeline_flow: dict | None` — composer 가 milestone 라벨 + 시나리오 미래 분기 선택 emit. 비면 backbone 자동 조립.
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` — timeline_flow 선택 emit 가이드. **미래는 토픽이 받쳐줄 때만** (과신 금지).
- `src/templates/archetypes/freeform_essay.html` — 감시 신호 직후 수직 타임라인. **과거=실선/채운 점, 현재=accent 앵커, 미래=점선/빈 점/'예상·감시' 태그** (투사 ≠ 사실 시각 구분). 데이터 없으면 섹션 생략 (graceful).
- `src/models.py:BundleTimeline` + `ReportBundle.timeline` (additive, 계약 §7 무증분) — OSINT 영상 타임라인 세그먼트용. `phase` 가 confirmed-past vs projected-future 구분.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.5.1 → v5.5.2
- `src/models.py` (ComposedReport.timeline_flow, BundleTimeline/Point, ReportBundle.timeline) → `docs/DATA_MODELS.md`
- `src/timeline_flow.py` 신규 → `docs/REPO_MAP.md`
- `docs/CONTRACTS/report_bundle_v1.md` (timeline additive)
- `tests/test_report_bundle.py` (+3), `README.md`, `DEVLOG.md`, 본 CHANGELOG entry

## [v5.5.1] — 2026-05-25

### Changed — 모순 섹션 서술형 전환 + 동적 제목 (WRITE-AP-9)

**배경**: 사용자 — "'봉합하지 않은 충돌'이라는 명칭 자체가 결론을 안 낸 느낌, 앞 내용 읽은 독자에게 시간낭비 인상. 모든 보고서에 동일 문구라 단조롭다. 서술형으로 바꿔줘."

**문제**: `freeform_essay.html` 의 고정 `<h2>봉합하지 않은 충돌</h2>` 가 *내용이 아니라 보고서 인식론* 을 말해 "결론 회피" 로 읽힘. 정작 판단인 `resolution` 은 "분석가의 정리 —" 각주형 border-left 박스로 뒤에 붙어 독자가 의심으로 끝남.

**해결**:
- `src/models.py:ComposedReport.contradictions_heading: str = ""` 추가 — composer 가 내용 기반 판단형 제목 emit (예: '정전이냐 잠복이냐'). 비면 reframe fallback '쟁점과 판단'.
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` — contradictions_heading 동적 작성 + resolution 결론적 문장(착지) 지시, 정적 메타-라벨 금지.
- `src/templates/archetypes/freeform_essay.html` — 서술형 prose 전환: side_a → '그러나'(accent) → side_b → resolution(fg-1 bold, 단락 착지). 각주형 라벨("근거 충돌:" / "분석가의 정리 —") + border-left 박스 폐기. kicker '쟁점'.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.5.0 → v5.5.1
- `src/models.py:ComposedReport` (contradictions_heading) → `docs/DATA_MODELS.md`
- composer SYSTEM_PROMPT → `docs/REPORT_WRITING_ANTIPATTERNS.md` (WRITE-AP-9), `docs/REPORT_STYLE_GUIDE.md`
- `CLAUDE.md` Anti-Patterns (9개 누적), `README.md`, `DEVLOG.md`, 본 CHANGELOG entry

## [v5.5.0] — 2026-05-25

### Added — ReportBundle 핸드오프 (osint_generator 영상 파이프라인 연동, 계약 v1)

**배경**: osint_generator (한국어 OSINT 영상 자동제작) 와의 연동. 우리 보고서의 차트/지도/signals/섹션 + 출처·검증 메타를 최종 HTML 과 별개로 *기계 판독용 단일 산출물* `analysis_{ts}.bundle.json` 으로 내보낸다. 계약 SSOT: [docs/CONTRACTS/report_bundle_v1.md](docs/CONTRACTS/report_bundle_v1.md).

**구현**:
- `src/models.py` — `ReportBundle` + 하위 모델 (BundleReport/Section/Chart/Map/Provenance/Source/Claim/Signal/Contradiction/Theme/Confidence). 계약 §8 참조 무결성 (`*_refs` resolve + id unique) `model_validator` 강제. enum: VerificationStatus 5값 / ConfidenceLevel 3값 / ProvenanceOrigin 3값 / EvidenceStance 3값. `ORIGIN_TO_VERIFICATION` 매핑 SSOT (계약 §2).
- `src/handoff/bundle_builder.py` (신규) — `FullAnalysisResult → ReportBundle`. **Q5 verification 배선 = 결정론**: market_fetcher 출처 차트 (context.time_series instrument 매칭) → measured/confirmed + source 자동주입, forecast → model_forecast/inferred, 그 외 composer 차트 → narrative_inference/inferred. composer SYSTEM_PROMPT 무변경. 테마 토큰은 `report.css [data-theme]` 블록 파싱 (단일 SSOT 유지).
- `src/agents/report_synthesizer.py` — synthesize() 가 deploy 전 `.bundle.json` emit (request.emit_bundle + config.enable_report_bundle 둘 다 ON 시). 실패해도 보고서 정상 진행 (graceful).
- `src/orchestrator.py` — `/analyze --bundle` 플래그 감지 → `AnalysisRequest.emit_bundle` (토픽 문자열에서 strip).
- `src/telegram_bot.py` — `/bundle <report_id>` (기존 보고서 JSON 에서 재emit + 재배포) + `/analyze --bundle`.
- `src/config.py` — `enable_report_bundle` kill-switch (디폴트 ON, env `V5_REPORT_BUNDLE=0`).

**v5.5.0 한계 (계약 명시)**: `claims[]=[]` (라이브 2-call 경로는 Claim/Evidence 그래프 미생성 — 라벨 척추는 charts/map provenance 가 짐), `prerendered_svg=null` (SVG passthrough 하네스 fast-follow), `section.map_ref=null` (composer 섹션↔지도 바인딩 전, 계약 §10).

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.9 → v5.5.0
- `src/models.py` (ReportBundle 모델군 + AnalysisRequest.emit_bundle) → `docs/DATA_MODELS.md`
- `src/handoff/` 신규 → `docs/REPO_MAP.md`
- `docs/CONTRACTS/report_bundle_v1.md` status draft → active
- `README.md` Status, 본 CHANGELOG entry, `DEVLOG.md`

## [v5.4.9] — 2026-05-22

### Changed — 자동 후속 보고서 생성 기능 비활성화 (사용자 요청)

**배경**: 사용자 — "후속 보고서 만드는건 기능을 멈춰줘." v5.1.1 부터 도입된 watch signal 발화 → 자동 child 보고서 생성 체인을 끄고 싶다는 요청.

**해결** — `src/models.py:MAX_CHAIN_DEPTH`:
- `2` → `0`
- 부수 효과 (의도):
  - `src/telegram_bot.py:_maybe_enqueue_followup` — 모든 신호 발화가 `next_depth >= MAX_CHAIN_DEPTH` 조건에 걸려 후속 분석 enqueue 스킵. 사용자에게 "자동 후속 분석 기능이 비활성화되어 있습니다" 안내 송신
  - `src/orchestrator.py:Phase 4` — `child_chain_depth >= MAX_CHAIN_DEPTH` (depth=0 이어도 통과) → 부모 보고서의 watch_signals 가 SQLite Watchlist Registry 에 *등록되지 않음*. HTML 보고서의 "감시 신호" 섹션은 composed_report.watch_signals 에서 직접 렌더하므로 시각 영향 X
  - `/fire` 명령 — 등록된 신호 없음 → 발화 대상 없음 (수동 발화 경로도 사실상 정지)

**메시지 단순화**: `_maybe_enqueue_followup` 에서 `MAX_CHAIN_DEPTH == 0` 분기 추가 — "체인 상한(depth=0) 도달" 같은 어색한 표기 대신 "자동 후속 분석 기능이 비활성화되어 있습니다" 로 명확화. 재활성화 (`MAX_CHAIN_DEPTH = 2`) 시 기존 메시지 자동 복원.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.8 → v5.4.9
- `src/models.py:MAX_CHAIN_DEPTH` 2 → 0 (+ 주석 갱신)
- `src/telegram_bot.py:_maybe_enqueue_followup` 메시지 단순화
- `README.md` Status
- 본 CHANGELOG entry

**재활성화 방법**: `src/models.py:MAX_CHAIN_DEPTH = 2` 로 복원 + 재배포. 메시지 분기는 자동 복원 (== 0 조건이 거짓).

**검증**: 다음 보고서 작성 → watch signals 섹션은 HTML 에 정상 표시, SQLite Registry 는 비어있음 (`/watchlist` 명령으로 확인). 임의로 `/fire signal_id` 시 — registry 가 비어 "신호 없음" 응답 + 자동 후속 미생성.

---

## [v5.4.8] — 2026-05-21

### Fixed — forecast 차트 y축 도메인 + 실측 ↔ 예측 선 단절 (CHART-AP-23, CHART-AP-24)

**증상**: 사용자 피드백 — "차트 이렇게 중간에 선이 끊기게 나오는게 맞아?" 같은 보고서 (`analysis_20260521_122324`) 의 HBM 시장 규모 추정 forecast 차트에서 두 회귀 동시 발견.

**원인 — CHART-AP-23 (y축 도메인)**:
- `drawForecast` 의 `yMin = d3.min(forecast, d => +d.low) ?? d3.min(actual, ...)` — `??` 연산자는 *좌측이 nullish 일 때만* 우측으로 fallback. `d3.min(forecast)` 는 forecast 가 있으면 항상 숫자 반환 → **actual 무시**.
- HBM 케이스: actual 2023=4, 2024=14, 2025=25 / forecast 2026.low=30, 2028.high=78
- yMin = 30, yMax = 78 → 패딩 후 y축 범위 22~85 → actual 4 와 14 가 22 미만으로 떨어져 **차트 영역 밖**. 2025=25 도 30 미만이라 grid 아래 박힘.

**원인 — CHART-AP-24 (선 단절)**:
- actual lineA path 와 forecast lineF path 가 *완전히 별도* 로 렌더 — boundary 에서 연결 segment 없음.
- HBM 케이스: 검정 solid 선이 (2025, 25) 에서 끝, 빨강 dashed 선이 (2026, 35) 에서 시작 → 1년치 X 간격으로 시각 단절.
- cone (low~high shaded) 도 2026 부터 시작 → actual 끝점에서 fan 형태로 펼쳐지지 않음 (표준 fan chart 컨벤션 미적용).

**해결** — `src/templates/static/charts.js:drawForecast`:

1. y 도메인 산정 변경:
   ```js
   const yValues = actual.map(d => +d.y)
     .concat(forecast.flatMap(d => [+d.low, +d.mid, +d.high]));
   const yMin = d3.min(yValues);
   const yMax = d3.max(yValues);
   ```
   - actual.y + forecast.low/mid/high 4종 모두 산입 → 모든 데이터 점이 y 범위 안.

2. Forecast bridge 추가 (시각 연결):
   ```js
   let forecastBridge = forecast;
   if (forecast.length && actual.length) {
     const lastA = actual[actual.length - 1];
     forecastBridge = [
       { x: lastA.x, low: +lastA.y, mid: +lastA.y, high: +lastA.y },
       ...forecast,
     ];
   }
   ```
   - bridge 의 첫 점 = actual 의 마지막 점 (low=mid=high=actual.y).
   - cone area: 그 점에서 한 점으로 시작 → 미래로 low~high 폭 확장 (fan 형태)
   - mid dashed 선: actual 끝점에서 시작 → forecast 의 마지막 mid 까지 연속
   - actual line / 끝점 dots / fork_at 마커는 `forecast` 원본 그대로 (bridge 는 cone+mid 렌더 전용)

**결과**:
- HBM 케이스 시각: y축 0~85 로 actual 모든 점 visible. solid 선 2023→2025 끝점이 dashed 선 시작점과 정확히 일치. cone 이 (2025, 25) 에서 한 점으로 narrow → (2028, 50~78) 까지 fan 으로 확장.
- 표준 fan chart 컨벤션 (Bloomberg / FT / Economist 의 forecast 차트와 동일) 적용.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.7 → v5.4.8
- `src/templates/static/charts.js:drawForecast` (y 도메인 + forecast bridge)
- `docs/CHART_RENDERING_ANTIPATTERNS.md` (CHART-AP-23, CHART-AP-24 append + last_synced_with v5.4.7 → v5.4.8)
- `CLAUDE.md` Anti-Patterns 차트 렌더링 (22 → 24, CHART-AP-23/24 lines)
- `README.md` Status
- `samples/forecast_continuity_fix_v5_4_8.png` (Before/After 비교)
- 본 CHANGELOG entry

**검증**: actual 의 모든 점이 y축 grid 안 visible, solid 선 끝점과 dashed 선 시작점 일치, cone 이 fork 에서 한 점으로 narrow.

---

## [v5.4.7] — 2026-05-21

### Fixed — sankey 좌·우 라벨 잘림 + 중간 컬럼 라벨 stacking 충돌 (CHART-AP-21, CHART-AP-22)

**증상**: v5.4.6 의 content-fit viewBox 픽스로 위·아래 쏠림은 해소됐으나 사용자 피드백으로 두 별개 회귀 추가 발견 — (1) "여전히 왼쪽으로 치우쳐져 있어서 맨 왼쪽 글씨가 짤려있고, 오른쪽에는 여백이 과도하게 남아있는 느낌." (2) "중간에 메모리, 파운드리, 시스템LSI 글씨가 있는 곳에 수치가 겹쳐있어서 시인성이 박살나있네."

**원인 — CHART-AP-21 (좌·우 margin)**:
- `computeZones(W, H, { left: 8, right: 8, ... })` — 좌·우 margin 각 8px
- 첫 컬럼 라벨 위치: `x = x0 - 6 = 10`, text-anchor: `end`
- 한국어 라벨 ("DS 매출" 등 5~8자) 텍스트 폭 ~50~80px → 음수 좌표까지 뻗어 viewBox 밖으로 잘림
- 마지막 컬럼 라벨 끝 (x≈625) 에서 viewBox 오른쪽 경계 (760) 까지 135px 휑함 (18% wasted)

**원인 — CHART-AP-22 (라벨 stacking)**:
- `MIN_NODE_PAD = 18` 이 인접 노드의 위쪽 라벨 (font 11, y0-6) 과 상위 노드의 값 라벨 (font 10, y1+14) stacking 에 부족
- 사용 가능 영역 = pad - 20 = -2px → 반드시 overlap
- 메모리/파운드리 케이스: "65.0" baseline y=178.1 vs "파운드리" baseline y=176.1 (역전, 7px overlap)

**해결** — `src/templates/static/charts.js:drawSankey`:

1. `computeZones` margin: `{ left: 8, right: 8, ... }` → `{ left: 80, right: 120, ... }`
   - left=80: 첫 컬럼 한국어 ≤8자 라벨이 x≈22 부터 렌더 — viewBox 안 fits
   - right=120: 마지막 컬럼 ≤15자 라벨 (예: "캡티브 (사내 SoC·SSD)") 이 x≈490~615 — viewBox 안 fits
   - 좌·우 비대칭 — 한국어 sankey 의 last col 라벨이 first col 대비 1.5~2× 긴 휴리스틱 반영

2. `MIN_NODE_PAD`: `18` → `36`
   - 산식: 위 라벨 height (8) + 값 라벨 height (7) + 텍스트 여백 (5) ×2 = 30 최소, 36 으로 4px buffer
   - 결과: "65.0" baseline y=178.1, "파운드리" baseline y=200.1 → 22px 차이, 텍스트 영역 5~6px 여유 gap

**부수 효과**: 컬럼 stack 이 (n-1)×18 → (n-1)×36 만큼 늘어나 차트 vertical 로 약간 길어짐. 8-노드 DS 케이스 tightH 238 → 308 (여전히 원래 H=320 보다 작음, content-fit pass 작동). 다크 스테이지 263px → ~340px — 위·아래 쏠림 해소 상태에서 라벨도 깨끗.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.6 → v5.4.7
- `src/templates/static/charts.js:drawSankey` (zones margin + MIN_NODE_PAD)
- `docs/CHART_RENDERING_ANTIPATTERNS.md` (CHART-AP-21, CHART-AP-22 append + last_synced_with v5.4.6 → v5.4.7)
- `CLAUDE.md` Anti-Patterns 차트 렌더링 (20 → 22, CHART-AP-21/22 lines)
- `README.md` Status
- `samples/sankey_lean_fix_v5_4_6.png` → `sankey_lean_fix_v5_4_7.png` (v5.4.7 결과로 업데이트)
- 본 CHANGELOG entry

**검증**: 첫 컬럼 "DS 매출"/"100.0" 라벨 완전 visible, 중간 컬럼 라벨/값 간 5~6px 여유 gap, 마지막 컬럼 라벨 viewBox 안 fits.

---

## [v5.4.6] — 2026-05-21

### Fixed — sankey 차트 "위로 쏠림" (CHART-AP-20)

**증상**: 사용자 피드백 — 삼성전자 DS 매출 흐름 sankey (analysis_20260521_122324) 가 다크 스테이지 위쪽 60% 만 채우고 아래쪽 ~40% 가 휑함. "한쪽으로 쏠려있다" 는 시각 인상.

**원인**: `drawSankey` 의 viewBox 공식 `H = max(320, min(560, 60 + n*28))` 이 노드 적은 sankey (≤9 노드) 에 320px 를 강제 → 자연 사이즈 284 보다 36px 과대. 추가로 `MAX_NODE_H_RATIO = 0.50` 이라 가장 두꺼운 컬럼도 zones.data 의 50% 만 사용 → 8-노드 케이스에선 컨텐츠가 zones 의 ~68% 차지하고 위·아래 각 16% 가 여백. 가중치 큰 노드 (메모리 65) 가 첫 컬럼 위쪽에 자연 배치되면서 시각 무게중심이 위로 시프트 → 다크 스테이지 아래쪽 60px 가 눈에 띄게 휑함.

**해결** — `src/templates/static/charts.js:drawSankey` 의 colKeys forEach 직후, link slice 할당 *전에* content-fit viewBox 패스 신설:

1. 노드 positioning 끝난 뒤 `nodes` 의 vertical extent 측정 — 중간 컬럼 노드는 라벨 padding (위 18px / 아래 22px) 함께 산입
2. `tightH = (contentBot - contentTop) + 14 + 14` 으로 viewBox H 재계산
3. tightH < 원래 H 일 때만 `dy = 14 - contentTop` 만큼 모든 노드 y 시프트 + svg viewBox 재설정
4. 시프트는 link slice 계산 전에 수행 (slice 는 `n.y0` 직접 참조)

**결과**:
- 8-노드 DS 매출 케이스: viewBox 320 → 238 (26% 축소), 위 7.86px / 아래 9.88px 로 균형. 다크 스테이지 361px → 263px (98px 축소)
- 12-노드 회귀 케이스 (chart_catalog 의 매출 → 사업부 → 비용/이익): viewBox 396 → 256, 마찬가지 균형
- v5.3.0 의 sankey 4원칙 (anchor 압축 / source-weighted ordering / 분기 V 분산 / column y-centering) 은 *보존*. 결과 viewBox 만 압축

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.5 → v5.4.6
- `src/templates/static/charts.js:drawSankey` (content-fit viewBox 패스 추가)
- `docs/CHART_RENDERING_ANTIPATTERNS.md` (CHART-AP-20 append + last_synced_with v5.4.3 → v5.4.6)
- `CLAUDE.md` Anti-Patterns 차트 렌더링 (19 → 20, CHART-AP-20 line)
- `README.md` Status
- 본 CHANGELOG entry

**검증**: `sankey_compare.png` (좌 v5.4.5 / 우 v5.4.6) — 아래쪽 dead space 가 사라지고 위·아래 여백이 8~10px 으로 대칭.

---

## [v5.4.5] — 2026-05-20

### Fixed — hero 사진 figure 위·아래 여백 비대칭

**증상**: 사용자 피드백 — "사진은 잘 들어갔는데, 사진 위아래 여백이 너무 큰 거 같아. 특히 아래쪽이 더 커." 첫 사진 박힌 보고서 (삼성전자 2026 1Q, v5.4.2 시점) 의 hero 사진 영역에서 caption 아래 ~ 다음 섹션 (목차) 사이 공백이 사진 위쪽 (meta 아래) 보다 눈에 띄게 큼.

**원인**: hero figure 가 `.freeform-hero` header 안에 있고, header 의 `padding: 48px 0 32px` 의 bottom 32px 가 figcaption 직후에 그대로 적용. figure 자체의 margin-bottom 은 0 이지만 header padding 이 누적되어 사용자 인지로는 ~46px (figcaption padding-top 10 + header padding-bottom 32 + 다음 섹션 시작 여백) 공백.

**해결** — `src/templates/archetypes/freeform_essay.html` CSS 3곳:

1. `.freeform-figure.hero` margin `18px 0 0` → `12px 0 0` (사진 위 여백 살짝 좁힘 — meta 와의 호흡 유지)
2. `.freeform-hero:has(.freeform-figure.hero) {padding-bottom: 14px}` 신규 — `:has()` 셀렉터로 *사진 있을 때만* 적용. 사진 없는 보고서는 기존 32px 유지 (의도된 호흡)
3. `.freeform-figure figcaption` padding-top `10px` → `8px` — 사진과 caption 사이도 살짝 좁힘 (전 figure 공통, hero/inline 모두)
4. 모바일 (≤640px) `.freeform-hero:has(.freeform-figure.hero) {padding-bottom: 12px}` 추가 — 24→12

**Graceful degrade**: `:has()` 미지원 구형 브라우저 (Safari 15.3 이하 / Firefox 120 이하) 는 기존 padding-bottom 32px 그대로 — 시각만 조금 헐렁할 뿐 기능 영향 X.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.4 → v5.4.5
- `src/templates/archetypes/freeform_essay.html` (3 CSS 라인 + 모바일 break)
- README.md Status + last_synced_with
- 본 CHANGELOG entry

**검증**: 다음 사진 박힌 보고서 (예: 다음 재무·기업 분석 보고서) 에서 caption 직후 본문까지의 공백이 사진 위 (meta→사진) 와 시각적으로 대칭이어야 정상.

---

## [v5.4.4] — 2026-05-20

### Changed — `analysis-reports.pages.dev` 인덱스 editorial_cream 톤으로 전환

**배경**: 보고서 목록 페이지 (Cloudflare Pages 루트, `_generate_index` 생성) 가 다크 버건디 (#2B1A1A bg / #C9A84C gold / Noto Sans KR) 톤으로 남아있어 *7테마 풀의 어느 보고서를 열어도* 인덱스 → 보고서 간 색·폰트 단절. 사용자가 이걸 editorial_cream 으로 통일 요청.

**변경**: `src/agents/report_synthesizer.py:_generate_index` 의 인라인 CSS 와 마크업을 전면 교체.

- 팔레트: `--bg #F2EBDB / --card #ECE3D0 / --card-hover #E5DBC4 / --border #D4C8B0 / --text #1F1814 / --muted #6B5C4A / --accent #B05A38` (samples 다이어그램 페이지와 동일 토큰, mono guide §3.1)
- 폰트: Newsreader (제목 800 + 보고서 링크 700) + IBM Plex Sans KR (본문) + IBM Plex Mono (eyebrow / 날짜 / footer). Noto Sans/Serif KR 한국어 폴백
- 구조: eyebrow ("Event Analysis Team") + h1 ("Analysis Reports") + sub (총 N건 mono) + table (Newsreader 제목 링크, hover accent underline) + footer ("editorial_cream · samples · github" 링크)
- 모바일 (≤640px): wrap padding 축소, h1 30px, cell-date 11px / 패딩 축소
- `data-theme="editorial_cream"` html 속성으로 보고서 본문 (random 7테마) 와 인덱스 (고정 cream) 의 시각 정체성 분리

**무영향 (데이터 계약)**:
- `glob('analysis_*.html')` → 50건 정렬, title 추출 로직 변경 없음
- 인덱스 파일 경로 (`reports/index.html`) + 배포 절차 변경 없음
- Pydantic / orchestrator 호출 경로 무영향 — 템플릿 인라인 HTML 만 교체

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.3 → v5.4.4
- `src/agents/report_synthesizer.py:_generate_index` 인라인 HTML/CSS 전면 교체
- README.md Status + last_synced_with
- 본 CHANGELOG entry

**검증**: 코드 컴파일 통과. 다음 보고서 발행 시 자동으로 새 인덱스 생성 — 별도 마이그레이션 불요. 봇 재배포 (VM SOP 4단계) 후 첫 보고서부터 적용.

---

## [v5.4.3] — 2026-05-20

### Fixed — 재무·수익성 보고서에서 sankey/waterfall 누락 회귀 (CHART-AP-19)

**증상**: 사용자가 "재무분석 요청인데 sankey 가 안 들어갔다" — 삼성전자 2026
1Q 보고서 (analysis_20260520_134233). event_category = '기업 재무 / 반도체
산업', 본문 narrative 가 명백한 *재무 분해* (매출 333.6조 → DS/모바일/디스
플레이/가전 → 비용 → 영업이익 57.2조, DS 영업이익률 37.3% → 66%). 그런데
composer 가 emit 한 차트: line ×4 + slope + bar + range_bar + forecast. **분해
차트 (sankey / waterfall) 0개**.

**원인 — 결정 트리 collapse**: 기존 SYSTEM_PROMPT 의 [차트 type 결정 트리]
는 step 1 이 "시간축 있음?" 이고 sankey/waterfall 은 step 3 (카테고리 비교)
의 마지막 두 branch. 본문에 시계열 데이터 (삼성·SK하이닉스·코스피 추이) 가
풍부하면 composer 가 step 1 에서 시계열 분기로 먼저 collapse → step 3 의 분해
차트 branch 까지 못 도달. 5-Layer Guarantee 의 Layer 4 (다양성 쿼터) 도
distinct type 5개라 monotony 검사 통과 — 단조 X, sankey 없음에도 silent.

**해결 — 결정 트리 step 0 추가**:
`src/agents/narrative_composer.py:SYSTEM_PROMPT` 의 [차트 type 결정 트리] 에
*step 0 "사건 카테고리가 재무·수익성·기업 분석인가?"* 분기 신설. 매치되면
**sankey 또는 waterfall 중 최소 1개 emit 강제** (시계열·추이는 *함께* OK,
단 분해가 함께 있어야). step 1 보다 *먼저* 평가됨을 명시.

추가:
- 사례 구체화 — sankey type 별 가이드에 삼성전자 1Q 보고서 nodes/links 예시
  (총매출 → 사업부 → 영업이익, negative=true 는 적자 사업부 흐름).
- anti-bias 가드에 "재무·수익성 보고서인데 시계열 + bar 만 박지 말 것" 추가
  (회귀 사례 라벨링).

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.2 → v5.4.3
- `src/agents/narrative_composer.py:SYSTEM_PROMPT`: [차트 type 결정 트리] +
  anti-bias + sankey 가이드 (3곳)

**검증**: 본 fix 의 효과는 다음 재무 보고서 emit 시 확인. SYSTEM_PROMPT 변경
이라 단위 테스트 X — composer LLM 출력의 sankey 빈도 (v5.4.3 이후 재무
카테고리 보고서) 를 운영 telemetry 로 추적.

---

## [v5.4.2] — 2026-05-20

### Changed — /status 메시지에서 에이전트 구성 블록 제거

운영자에게 *반복 노이즈* 인 "📋 에이전트 구성 — Tier 4 ..." 블록 (① 상황
분석관 ② 편집장 + ※ 4 줄 설명) 을 텔레그램 `/status` 출력에서 제거. 메시지가
짧아짐 — 봇 상태 / 가동시간 / 보고서 수 / 메모리 / 큐 / 일일 브리핑 만 표시.

에이전트 구성은 변경 시점에만 의미 있는 정보 (이미 [docs/CATALOGS.md §1](docs/CATALOGS.md)
에 SSOT) — 매 status 호출마다 표시할 필요 없음. v4.0.0 이래 Tier 4 가 안
바뀌었고 사용자가 이미 알고 있는 정보의 반복.

`src/telegram_bot.py` 만 변경, 다른 경로 영향 없음.

---

## [v5.4.1] — 2026-05-20

### Fixed — 보고서 사진 broken image 회귀 (외부 hotlink 차단)

**증상**: v5.4.0 첫 배포 후 사용자 피드백 — "본문에는 있는데 (figure / 캡션 /
credit 은 보이는데) 이미지가 안 보여, 마치 다운로드가 안 된 것처럼." 즉
composer 가 og:image URL 을 정상 emit + 템플릿이 `<img src>` 박았는데 브라우저
에서 broken image 자리.

**원인**: 메이저 매체 (FT / Reuters / Bloomberg / 한국 매체 다수) 의 이미지 CDN
이 *외부 도메인의 hotlink 검증* — referrer / origin 헤더로 자기 사이트 외부에서
`<img>` 로 박는 걸 403 으로 차단. og:image URL 자체는 valid 하고 브라우저로 직접
열면 보이지만, *다른 도메인 (Cloudflare Pages) 에 박힌 `<img src>`* 로는 못
가져옴. v5.4.0 의 설계가 외부 URL 그대로 참조하는 방식이라 정통으로 회귀.

**해결 — 봇이 직접 다운로드 + 동일 출처 serve**:
1. `src/tools/image_fetcher.py` 에 `download_image_to_dir(url, dst_dir)` +
   `localize_image_urls(urls, dst_dir)` 추가. 이미지 fetch 시엔 매체 자기
   도메인을 Referer 로 보냄 (CDN 일부는 referrer 있어야 200) + Accept 헤더를
   image/* 로 설정. 파일명 = SHA256(URL)[:16] + Content-Type 기반 확장자
   (같은 URL 두 번 등장 시 자동 dedup, 12MB cap, 1KB 미만 placeholder 제거).
2. `src/agents/report_synthesizer.py` 의 `synthesize()` 가 template.render 직전
   에 `_localize_report_images(result, output_dir)` 호출 — composed_report 의
   hero_image + 각 sec.images 의 image_url 을 *전부 다운로드 후 상대 경로
   ('img/<hash>.jpg') 로 swap*. Cloudflare Pages 가 reports/ 전체를 업로드하므로
   이미지와 HTML 이 *동일 출처* → hotlink 검사 무관.
3. 추가 안전망 — `freeform_essay.html` 의 `<img>` 에 `referrerpolicy="no-referrer"`
   + `crossorigin="anonymous"` 속성. 다운로드 실패해 원본 URL 유지된 케이스
   에서 referrer 기반 차단을 가볍게 우회. 로컬 상대경로일 땐 브라우저가 무시.

**Graceful degrade**: 다운로드 실패한 URL 은 *원본 URL 유지* (위 referrer 속성
도움받아 부분적으로라도 보일 가능성 있어 broken 보다 낫다는 판단). 모든 URL
실패해도 보고서 렌더 정상 진행, warning log 만 남김. composer 가 사진 emit X
한 보고서는 hook 자체 no-op.

**검증**: aiohttp mock 기반 단위 테스트 — 3 URL 다운로드 → reports/img/ 에
실제 파일 저장 → composed_report 의 image_url 이 'img/<hash>.jpg' 상대경로로
swap → 같은 URL 두 번 등장 시 동일 로컬 파일 가리키는 dedup 까지 정상 동작.

**Change Propagation Matrix**:
- `src/orchestrator.py:VERSION` v5.4.0 → v5.4.1
- `src/tools/image_fetcher.py`: download_image_to_dir / localize_image_urls 신규,
  `__all__` export 갱신
- `src/agents/report_synthesizer.py:synthesize()`: localize hook 추가 (await),
  `_localize_report_images()` async @staticmethod 신규
- `src/templates/archetypes/freeform_essay.html`: hero + inline `<img>` 에
  referrerpolicy + crossorigin 속성 추가

---

## [v5.4.0] — 2026-05-20

### Added — 보고서 본문에 출처 기사의 사진 자동 삽입

**배경**: 보고서가 본문 + 차트 + 지도 일색이라 *지금 누가 / 무엇이 / 어디서*
의 시각 정보가 비어 있었다. 사용자 피드백 — "맥락에 닿아있는 필요한 사진을
넣자". FT 의 헤드라인 직후 hero 사진 + 캡션 + 출처 (© Getty Images) 형태를
참조 SSOT 로 채택.

**파이프라인**:
1. ContextAnalyst 가 평소대로 sources URL 수집.
2. orchestrator 가 market_fetcher 후속으로 `src/tools/image_fetcher.py` 호출
   — 각 source URL 의 og:image / og:title / og:description / publisher 를
   추출해 `ContextAnalysis.available_images` 채움. 5장 cap, per-URL 5s
   timeout, total 12s timeout. 실패해도 보고서 진행 (graceful degrade).
3. NarrativeComposer 가 payload 에 available_images 를 받아 본문 흐름과
   *직접 맥락이 닿는* 사진만 신중하게 선택. hero_image (보고서 1장) + 섹션
   inline images (보고서 전체 0~3장) emit. 캡션은 한국어 editorial 톤, credit
   은 `© Publisher` 형식.
4. `freeform_essay.html` 이 hero figure (deck 직후) + 섹션 inline figure 를
   FT 스타일로 렌더 — Newsreader italic 캡션 + sans-serif credit, 컬러 사진
   그대로 (mono 필터 X), 7개 테마 토큰 (border/figcaption color) 자동 적용.

**SSOT 매트릭스**:
- `src/models.py`: `AvailableImage` 신규 + `ContextAnalysis.available_images` +
  `ComposedReport.hero_image` + `ComposedSection.images`. forward-ref 해결
  `ContextAnalysis.model_rebuild()`.
- `src/tools/image_fetcher.py`: aiohttp + regex 기반 (외부 lib 의존성 0).
  HTML 첫 64KB 만 읽음 (og 태그는 <head> 안). 평범한 데스크탑 Chrome UA +
  Accept 헤더로 위장 (403 회피). twitter:image / property/name 순서 반전 /
  HTML entity unescape / 상대 URL → 절대 URL 자동 처리.
- `src/agents/narrative_composer.py`: SYSTEM_PROMPT 에 `=== 사진 (v5.4.0) ===`
  섹션 추가 — 후보 풀 형식, 선택 원칙 (맥락 직결만 / 추정 금지 / 광고
  placeholder 차단), 배치 (hero 0~1 + inline 0~3), 캡션·credit 작성 가이드,
  Anti-pattern (URL 환각 / 중복 / 보일러플레이트). JSON schema 에 `images` /
  `hero_image` 필드 명시.
- `src/orchestrator.py`: market_fetcher hook 직후에 image_fetch hook 추가.
- `src/templates/archetypes/freeform_essay.html`: `.freeform-figure.hero` +
  `.freeform-figure.inline` CSS + hero figure (deck 직후) + 섹션 inline
  figure (charts 다음, embedded_blocks 앞) 렌더 블록.

**테스트 / 검증**:
- 단위: `_parse_og_meta` — FT (standard og), BBC (twitter:image only), 한겨레
  (content 속성 반전), 상대 URL, HTML entity, empty case 모두 정확.
- publisher 매핑: ft.com → FT, biz.chosun.com → 조선비즈, bbc.co.uk → BBC 등
  16개 매체 사람-친화 이름.
- 통합: composer payload 에 `available_images` key 주입 확인. ComposedReport
  / ComposedSection Pydantic round-trip 정상.
- 렌더링: 가짜 데이터로 freeform_essay.html 풀 렌더 — hero <figure> 1개 +
  inline <figure> 1개 + © Reuters / © Bloomberg credit 모두 정상 출력.

**Graceful degrade 표**:

| 시나리오 | 동작 |
|---|---|
| sources 비어있음 | image_fetch hook skip, 사진 emit X |
| 모든 URL 403 / timeout | available_images 빈 list, composer 가 사진 emit X |
| 일부만 og:image 보유 | 그것만 후보로, composer 가 선별 |
| 네트워크 정책으로 외부 차단된 환경 | warning log + 보고서 정상 진행 |
| composer 가 사진 emit 안 함 (자신 없을 때) | hero_image=null / images=[] — 차트만 박힌 보고서 |

**모크업**: [`samples/report_images_theme_compare.html`](samples/report_images_theme_compare.html)
— 7개 테마 (editorial_cream / burgundy_mono / slate_steel / forest_sage /
midnight_indigo / dusk_rose / paper_classic) 별 hero+inline figure 시각 비교.

---

## [v5.3.2] — 2026-05-19

### Changed — 감시 신호 섹션 editorial epilogue 화

**배경**: 보고서 말미의 "감시 신호" 카드가 essay 의 완결성을 해친다는 피드백.
v5.2.12 의 chart-card 화 (border + shadow + accent "시사" takeaway 박스) 가
본문 prose 와 시각적으로 단절되어, 산문 → 모순 → 분석가의 한계 로 흘러야 할
마지막 호흡 직전에 "표" 처럼 끼어드는 회귀가 있었음. kicker "앞으로 무엇을
볼까" + H2 "감시 신호" 라벨도 사무적·시스템 출력 어조라 editorial 톤과 불일치.

**변경**:
- 별개 H2 폐기 (kicker + heading 모두). 모순 섹션 마지막 호흡의 연장선으로
  자연스럽게 흘러가도록 (단, watch_signals 가 contradictions 없이도 단독으로
  올 수 있으니 conditional section block 자체는 유지)
- chart-card / takeaway 박스 폐기. 대신 lede 한 문단 + row 기반 list:
  - **lede** (italic serif, accent strong) — "본 분석의 가정이 다음 N개
    지점에서 시험된다. 한 곳이라도 반대 방향으로 움직이면 결론은 다시
    작성되어야 한다." — 신호 개수는 `composed.watch_signals | length` 로 동적
  - **deadline** (좌측 108px 고정, mono italic, accent) | **body** (우측 1fr)
  - **signal** (Newsreader serif, fg-1) → **desc** (sans, fg-2) →
    **시사 —** (italic + accent 2px border-left + uppercase mono prefix) —
    contradiction-prose 의 `.ct-resolve` 와 같은 시각 어휘로 본문 통일
  - row 사이 `border-soft` 가로 divider (chart-card 의 box 반복 회피)
- 모바일 (≤640px): deadline 을 본문 위로 올려 한 컬럼 (`no-deadline` row 와
  같은 grid-template-columns:1fr). signal 15px / lede 15.5px 로 축소
- `.signal-grid / .signal-card / .signal-card-head / .signal-card-title /
  .signal-card-deadline / .signal-card-desc / .signal-card-takeaway /
  .signal-card-takeaway-label` 클래스 전체 폐기 → `.epilogue-watch-lede /
  .epilogue-watch-list / .epilogue-watch-row / .epilogue-watch-deadline /
  .epilogue-watch-signal / .epilogue-watch-desc / .epilogue-watch-indicates`

**무영향 (데이터 계약)**:
- `composed.watch_signals: list[dict]` (ScenarioAnalysis.watch_signals → ComposedReport.watch_signals → 모델 SSOT) Pydantic 변경 없음
- `convert_watch_signals()` → `WatchlistRegistry` SQLite INSERT 경로 변경 없음 — 후속 보고서 자동 트리거 (v5.1.1) 그대로 작동
- composer SYSTEM_PROMPT 의 watch_signals emit 지시 변경 없음 — 같은 데이터를 다른 렌더링으로만 보여줌

**모크업**: `samples/watch_signals_redesign_compare.html` (editorial_cream 테마,
같은 watch_signals 3개 데이터로 좌측 v5.3.1 production / 우측 본 안 비교).

**파일**:
- `src/templates/archetypes/freeform_essay.html` — line 78-87 (signal CSS) →
  epilogue-watch CSS, line 331-355 (signal section) → epilogue 섹션. 모바일
  media query 에 epilogue 규칙 추가.

---

## [v5.3.1] — 2026-05-19

### Fixed — entry 애니메이션 커버리지 (option C — bar grow + donut sweep + fill-path fade)

**배경**: v5.3.0 의 `_applyEntryAnimation` 은 *type-무관 post-process* 로
설계됐다. renderer 코드를 손대지 않고 SVG DOM 만 스캔해 path/rect/circle
3종에 generic 애니메이션을 거는 방식. 하지만 두 가지 사각이 있었음:

1. **fill 있는 path 는 전부 skip** (line/area 의 stroke-only 만 그리기).
   결과: donut arc / choropleth 국경 / sankey flow / stacked_area 레이어 /
   forecast cone / area gradient 가 모두 무애니메이션. 보고서에서 가장
   자주 등장하는 *donut* 이 거의 정적으로 보이던 원인.

2. **rect 는 opacity fade 만** (width/height 변형 X). 가로 bar 의 막대가
   "좌→우 성장" 이 아닌 "그 자리에서 어슴푸레 진해짐" 으로만 등장.

옵션 A (fill-fade 만 추가, 최소 패치) 와 B (전 renderer 모크업 이식) 중,
사용 빈도 상위 2 type 만 renderer-level 로 가져오고 나머지는 generic
확장으로 메우는 **옵션 C** 채택.

**변경**:

- `drawBar` (`src/templates/static/charts.js:318`) — 막대 rect 에 두 가지
  data 속성 부여:
  - `data-anim="bar-grow"` (대상 식별)
  - `data-final-w={barW}` (목표 폭)

- `drawDonut` (`src/templates/static/charts.js:374`) — arc path 에:
  - `data-anim="donut-arc"` + `data-start={startAngle}` + `data-end={endAngle}`
  - SVG 루트엔 `data-donut-cx/cy/ir/r` (arcGen 재구성용 geometry)

- `_animateBars(svg)` — `rect[data-anim="bar-grow"]` 의 width 를 0 으로
  되감았다가 stagger 40ms / duration 380ms 으로 final width 까지 트랜지션.

- `_animateDonut(svg)` — SVG 의 geometry 메타로 `d3.arc()` 재구성,
  `attrTween('d')` 로 각 arc 를 startAngle 위치의 zero-arc 에서 (startAngle,
  endAngle) 로 펼침. duration 680ms. 시작 프레임 깜빡임 방지를 위해
  transition 직전 d 를 zero-arc 로 동기 세팅.

- `_applyEntryAnimation` 의 path 분기 재설계 — *fill 있는* path 면 opacity
  fade-in (360ms), *stroke only* 면 기존 stroke-dashoffset 그리기. 위
  type-specific 핸들러가 처리한 tagged 요소는 skip.

- **silent 회귀 fix** — `data-orig-dasharray` 가 어디서도 set 되지 않아
  dual_line / forecast 의 점선이 애니메이션 종료 후 솔리드로 둔갑하던
  버그 해소. dashoffset 트릭 시작 전에 기존 `stroke-dasharray` 를
  `data-orig-dasharray` 에 저장해 두고 on('end') 에서 복원.

**보존**:
- CHART-AP-18 가드 (≤700ms 단일 duration, prefers-reduced-motion 즉시 정적
  폴백, IntersectionObserver 1회 재생 후 unobserve, fallback 즉시 렌더).
- 나머지 17 종 차트의 generic post-process — rect fade / circle pop /
  stroke draw 동작 무변경.

**파일**:
- `src/templates/static/charts.js` — drawBar + drawDonut 태깅, _applyEntryAnimation
  재설계 (≈+70 lines, -10 lines)
- `src/orchestrator.py:VERSION` — `v5.3.0` → `v5.3.1`
- `README.md` Status 갱신
- `CHANGELOG.md` 본 entry

---

## [v5.3.0] — 2026-05-18

### Added — FT/Economist 스타일 신규 7종 차트 + 5-Layer Usage Guarantee

**개요**: 캔들 회귀 (v5.2.0 에 추가했으나 production 13종 중 약 70% 가
bar/line/donut 으로 collapse) 의 교훈으로 두 가지를 동시 도입.

#### Part 1 — 신규 7종 차트 (FT/Economist 스타일)

기존 13종에 7종 추가. 모두 `guarded` tier 로 시작 (chart_critic 통과율 측정
후 `safe` 승격 검토).

- **scatter** — 라벨 산점도 (FT 좌측 스타일). bubble 과 구분 — size 인코딩 X.
- **stacked_area** — 시계열 누적 영역 (FT 우측 스타일). 점유율 연속 변화.
- **lollipop** — bar 의 우아한 대안. 8-15 항목.
- **slope** — 2 시점 비교, 순위 역전. 3-10 항목.
- **small_multiples** — 4-9 패널 그리드 비교.
- **waterfall** — 증감 누적 분해 (P&L brücke). 첫·끝 row `type='total'` 강제.
- **range_bar** — Dumbbell. 두 값 사이 갭 (남녀 임금격차 등).

#### Part 2 — 5-Layer Usage Guarantee (회귀 방지 안전망)

- **Layer 1** — `src/visual/usage_log.py` (신규). 보고서당 emit chart type 을
  JSONL 영구 기록. 누적 ≥10 보고서에서 0회 emit type 을 WARNING 으로 표면화.
  CLI: `python -m src.visual.usage_log analyze`.
- **Layer 2** — `narrative_composer.py:SYSTEM_PROMPT` 에 차트 type 결정 트리
  + 반-편향 가드 추가. "시계열 + OHLC → candle (LINE 금지)" 같은 negative
  constraint 로 LLM 의 line/bar default bias 차단.
- **Layer 3** — `research_director.py:_DEFAULT_REQUIRED_EXHIBITS` 의 빈 method
  채움: `fault_tree → waterfall`, `pre_mortem → scatter`. 신규 type 에 자동
  수요 부여.
- **Layer 4** — `deterministic_gate.py` 에 `chart_type_monotony` soft fail
  추가 (SOFT_FAIL_RULES 5 → 6). standard ≥3 차트 + distinct <2, deep ≥5 차트
  + distinct <3 면 DeskEditor 가 hold 받아 type 다양화 지시.
- **Layer 5** — `tests/regression/fixtures/chart_type_scenarios.yaml` (신규).
  21 시나리오 (20 차트 type + map) SSOT. `KNOWN_CHART_TYPES` 와 1:1 매칭.

#### Part 3 — Pydantic 가드 보강

`src/visual/schemas.py:_TYPE_TO_GUARD` 11 → 21 entries. 신규 7종 +
production 가드 없던 3종 (`dual_line/forecast/choropleth`) 추가.

#### Part 4 — Capability Registry 갱신

`docs/VISUAL_CAPABILITY_REGISTRY.yaml` 분포: safe 11 / guarded 10 (3→10) /
experimental 2 / 총 23 (was 16). 신규 7종 모두 `d3_custom` + `guarded`.

#### 모크업 (검토용)

`samples/chart_animation_mockup.html` — 21종 entry 애니메이션 모크업.
IntersectionObserver 트리거, motion off / ambient drift 토글. production
이식은 본 PR *제외* — 모크업으로 검토 후 별도 PR 권장.

---

## [v5.2.13] — 2026-05-18

### Fixed — 컴팩트 스트립만 나오고 풀 차트가 누락되던 회귀 (사용자 catch)

**증상**: 시계열 데이터가 충분히 fetch 된 보고서에서 *compact strip 차트만*
계속 보이고, 캔들·라인·area 같은 정식 풀 카드 차트는 누락. 사용자 노출 결함.

**근본 원인** (v5.2.5 회귀): `src/orchestrator.py:_composer_instruments` 가
strip row (role='compact') 를 *composer 가 박은 instrument 집합* 으로 인정하도록
변경됐는데 (instrument 중복 emit 회피 목적), 부작용으로:
1. composer 가 SYSTEM_PROMPT 의 "시계열 차트 1개 이상 emit 강제 규칙" 을 어기고
   풀 카드를 0 개 emit
2. `_ensure_market_strip` 이 3+ instrument 를 compact row 로 박음
3. `_composer_instruments` 가 *모든* instrument 를 covered 로 반환
4. `_ensure_time_series_chart` fallback 의 dedupe 가 모든 instrument 잘라 no-op
5. 결과: 사용자가 strip 만 봄 (풀 카드 0)

`_drop_invalid_charts` validator 가 composer 의 candle/line/area 를 silent drop 한
케이스도 동일 결과 (drop 후 풀 카드 0 → strip 만 남음 → fallback 막힘).

**Fix**:
- `_count_existing_ts_charts` (`orchestrator.py:100-117`) 가 strip row
  (role='compact') 를 제외하도록 수정. strip 의 type 도 ``line`` 이지만 sparkline
  용 다른 시각 역할 — 풀 카드 보장 판정의 분자에 포함하면 회귀가 영구화.
- `_ensure_time_series_chart` (`orchestrator.py:500-573`) 에 *풀 카드 ≥1 보장*
  안전망 추가. composer 의 유효 풀 카드가 0 이면 data 가 가장 풍부한 series 1개를
  strip dedupe 우회로 풀 카드 강제 추가. 1개만 강제 — 모든 instrument 풀 카드는
  strip 의 at-a-glance 역할과 중복돼 시각 혼잡 (v5.2.5 의 origin).

**회귀 가드** (`tests/regression/test_compact_strip.py`):
- `test_count_existing_ts_charts_excludes_compact_strip` — strip row 가 풀 카드
  카운트에서 빠지는지 lock
- `test_ensure_time_series_chart_guarantees_full_card_when_composer_emits_zero` —
  사용자 사례 재현 + 풀 카드 ≥1 보장 lock
- `test_ensure_time_series_chart_preserves_composer_full_card` — composer 가
  풀 카드 emit 했으면 fallback 이 추가 풀 카드 안 박는지 lock (시각 혼잡 방지)
- `test_ensure_time_series_chart_force_picks_data_richest` — 강제 emit 시 data 가
  가장 풍부한 instrument 선택 규칙 lock

기존 `test_composer_instruments_picks_up_compact_role` 은 그대로 유지 — strip 도
dedupe 집합에 포함하는 것 *자체는* 정합 (instrument 중복 emit 회피 의도). 이번
fix 는 그 결과로 fallback 이 막히는 *별개의* 안전망 누락만 메움.

비-시계열 차트 (donut/bar/gantt/network/bubble/heatmap/stacked/dual_line/forecast/
choropleth) 는 composer 가 직접 결정 — fallback 없음 (의도된 동작). 시계열만
fetch 된 데이터를 자동으로 다루는 v5.2.0 약속 영역.

---

## [v5.2.12] — 2026-05-17

### Changed — 모순·신호 섹션 재디자인 (`freeform_essay.html`)

보고서 말미의 두 섹션이 본문과 톤이 따로 놀던 문제 정리. 모델 (`ComposedReport.contradictions`,
`watch_signals`) 은 변경 없음 — 템플릿 레이어 단독 변경.

**모순 (`composed.contradictions`)**: 카드 + "관점 A:/B:" 라벨 + 좌측 점선 보더로
정형 박스화돼 있던 렌더 → 본문 prose 와 동일한 톤의 서술형 단락으로 변환. composer
의 4-필드 (`side_a / side_b / evidence / resolution`) 는 그대로 받되 "한쪽은 X.
반면 다른 쪽은 Y." 패턴으로 한 단락에 결합. 강조 위계 3단:
- base: `--fg-2`
- claim (충돌하는 단언): `--fg-1` + bold (`.ct-claim`)
- accent (핵심 수치): `--accent` + bold (`.ct-accent`) — 본문 `<em>` 톤과 일치
- resolution: 단락 끝에 가는 accent 좌측 보더 + Newsreader italic, "분석가의
  정리" uppercase 라벨이 자동 prefix (`.ct-resolve`)

**신호 (`composed.watch_signals`)**: 어두운 카드 (`rgba(0,0,0,0.18)` 배경 + 좌측
accent 보더) → `chart-card` 와 동일 토큰 (`--card` / `--border-light` / 10px
round / `--shadow`). 내부 구조도 차트 카드 톤:
- 제목: Noto Serif KR 14.5px (`.chart-card-title` 톤)
- `deadline`: 우측 mono accent 칩
- `indicates`: `chart-card-takeaway` 클론 — 옅은 accent 배경 + accent 좌측 보더 +
  "시사" uppercase 라벨

WRITE-AP / CHART-AP 신규 항목 없음 (회귀가 아닌 의도적 디자인 개선).

---

## [v5.2.11] — 2026-05-17

### Fixed — 가로 막대 + 간트 차트 가독성/직관성 회귀

**문제 1 — 간트 풀폭 회귀**: 같은 월(예: `2026-05-09`, `2026-05-15`, `2026-05-21`)
안의 모든 이벤트가 day-precision 무시로 동일 시점으로 collapse 되고, 그 결과
zero-duration 폴백 `+0.4` (≈5개월) 가 일제히 발동해 *모든 막대가 데이터 영역
풀폭*으로 렌더되던 회귀. composer 가 day-precision ISO 로 emit 해도 JS 가
month 단위로만 파싱하던 게 근본 원인. CHART-AP-15 가드는 모든-행 zero-duration
케이스만 잡았기에 (3 point + 1 range 같은) mixed 케이스는 통과해 회귀가 잔존.

**Fix**:
- `drawGantt.parseTime` 에 day-precision 분기 추가: `YYYY-MM-DD` 도 파싱.
  encoding `y + ((m-1)*31 + (day-1)) / 372` — month-only 입력과 호환.
- zero-duration 폴백 `+0.4` 제거. 막대 시각적 minimum 은 기존 `Math.max(6, …)`
  pixel floor 가 보장.
- axis tick 단위/포맷 자동: span ≥ 4 yr → 연도 / 0.4 ≤ span < 4 → `YYYY-MM` /
  span < 0.4 → `MM-DD`. 이전엔 `2026.4` 같은 분수 연도 라벨이라 5월/4월 직관 X.
- annotation `vline.x`/`band.x_*` 도 `parseTime` 통과시켜 day-precision 지원.

**문제 2 — 가로 막대 라벨 포맷 불일치 + 시인성**: 값 라벨이 `String(d.value)`
raw 라 `13567` 그대로 찍히는 반면 x축 tick 은 `d3.format(',')` → `13,567`.
같은 차트 안에서 *포맷 불일치*. 또 22자 이상 라벨은 무음 truncate (잘림 인지
불가) + 값 0/극소이면 막대가 0px 로 사라져 빈 행처럼 보임.

**Fix**:
- 값 포맷 통일 헬퍼 `fmt(v)` 도입 — 천 단위 separator + |v| 규모별 소수점 자동
  (≥100 정수 / ≥10 `.1f` / 그 외 `.2f`). 부호 보존. 막대 라벨 + 축 tick 양쪽에
  동일 적용.
- 라벨 22자 초과 시 ellipsis `…` 부착.
- 막대 최소 너비 `Math.max(2, x1 - x0)` floor — 0/극소값도 시각적 흔적 보장.

**Files**:
- `src/templates/static/charts.js` — `drawBar` / `drawGantt` (`parseTime` 포함)
- `src/orchestrator.py:VERSION` → v5.2.11

### Known limitations (다음 회차)
- 가로 막대 음수는 여전히 magnitude 기반 (label 에 부호만 표시). 진짜 diverging
  bar (0 기준 좌·우 양방향) 는 미지원 — `BarChartGuard` 에서 reject 하거나
  렌더 분기 추가는 별도 작업.
- 간트 `BarRow.group` 필드는 schema 에만 있고 렌더 미사용 (dead field) — 그룹별
  색 구분 미구현. 본 회차 범위 밖.

---

## [v5.2.10] — 2026-05-17

### Fixed — compact strip sparkline 가격 흐름 가독성 + sparkline 기간 라벨 노출

**문제 1 — 너무 부드러운 곡선**: compact strip 의 sparkline 이
`d3.curveMonotoneX` 베지에 보간을 써서 일간 종가 변동을 *평탄화*. 실제
가격 흐름의 jaggedness 가 시각적으로 사라져 "그냥 우상향/우하향 곡선" 으로
밖에 안 보임. 사용자 catch: "가격 흐름이 너무 부드러운 곡선으로만 보이는걸
실제 가격 흐름을 알 수 있는 라인 형태로 보완".

**문제 2 — 기간 부재**: sparkline 옆에 라벨/축이 없어 표시된 기간이
지난 24h 인지, 1W 인지, 3M 인지 알 수 없음. 사용자 catch: "조그맣게 기간을
표현해주고".

**Fix**:
- `src/templates/static/charts.js` `drawSparkline`:
  - `d3.curveMonotoneX` → `d3.curveLinear` — 일간 종가 사이를 직선 segment
    로 연결. 베지에 평탄화 제거 → 실제 가격 흐름 (변동성·반전점·급등락)
    그대로 표시. `stroke-linejoin: miter` 로 꺾임도 sharp.
  - **baseline (시작 종가) dashed line** — 옅은 0.6px dashed, opacity 0.35.
    가격이 시작 대비 어디까지 움직였는지 한눈에 보이는 zero-line. mono
    가이드 위반 없음 (line color 와 동일, 액센트 색 X).
  - **min/max 극값 dot** — 기간 내 최고/최저 close 에 1.1px dot (opacity
    0.55). 변동의 진폭을 즉시 인지.
- `src/orchestrator.py:_compact_period_label` (신규) — start/end_date 일수
  차이로 짧은 라벨 (`24H` / `1W` / `2W` / `1M` / `3M` / `6M` / `1Y` / `2Y`
  / `{n}Y`) 분류. start/end 파싱 실패 시 data 포인트 수로 fallback.
- `src/orchestrator.py:_build_compact_strip_row` — payload 에
  `period_label` 필드 추가.
- `src/templates/archetypes/freeform_essay.html` — compact-row 안에
  `<span class="compact-period">` 삽입 (change 와 spark 사이).
- `src/templates/static/charts.css` — `.compact-row .compact-period` 규칙
  (9.5px / muted / monospace / uppercase / letter-spacing 0.4). 모바일
  ≤600px 분기에서 9px 로 축소.
- `tests/regression/test_compact_strip.py` — 6 신규 회귀: 버킷 정확도 +
  fallback + payload field + template span + CSS 규칙 + curveLinear lock.

**영향**: 시계열 instrument 3개↑ 보고서 (자동 trigger) 의 strip sparkline
시각이 즉시 변경. 풀 차트 / 본문 문체 / VM 운영 절차 무영향.

---

## [v5.2.9] — 2026-05-17

### Refactored — 본문 문체 SSOT 통합 + persona 채널 폐기 + dead persona 7개 모듈 청소

**문제**: composer (`src/agents/narrative_composer.py:SYSTEM_PROMPT`) 와
context (`src/agents/context_analyst.py:SYSTEM_PROMPT`) 사이에 문체·어휘
규칙이 *3중 중복* 되어 있었음. 또한 v4.3.0 의 `recommended_persona` dict
채널은 context 가 "디폴트 그대로 권장" 으로 emit 하고 composer 가 "느슨하게
적용 / 영감용" 으로 받아 *사실상 dead channel*. 더해서 음슴체 (context) vs
평어체 (composer) 의 어조 충돌 위험. 마지막으로 v4.0.0 부터 호출되지 않던
dead persona 7개 agent 모듈이 5년 가까이 보존되어 있었음.

**변경**:
- **본문 문체 SSOT 신설** — [docs/REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md)
  를 v5.2.9 부터 *보고서 본문 문체 SSOT* 로 재포지셔닝 (이전엔 abhinavbwj
  기반 색·타이포·레이아웃 가이드, v4.5.0 부터 stale). 색·타이포는
  [MONO_THEME_GUIDE.md](docs/MONO_THEME_GUIDE.md) 로 위임.
- **persona dict 채널 폐기**:
  - `src/models.py:ContextAnalysis.recommended_persona` 필드 삭제
  - `src/state/models.py` 의 `EvidencePack.recommended_persona`,
    `AnalysisBrief.recommended_persona` 필드 삭제
  - `src/state/compaction.py`, `src/agents/research_director.py` 의 persona
    복사·기본값 라인 삭제
  - `src/agents/context_analyst.py:SYSTEM_PROMPT` 의 "페르소나 권장" 섹션
    + JSON 출력 스키마 안의 `recommended_persona` 필드 삭제. "출력의 위치"
    섹션 신설 — "당신 출력은 내부 분석 메모. composer 가 평어체 본문으로
    재작성한다" 명시 (음슴 vs 평어 충돌 해소).
  - `src/agents/narrative_composer.py:SYSTEM_PROMPT` 의 "페르소나 적용"
    섹션 + `_build_payload` 의 `payload["persona"]` 주입 삭제
- **본문 문체 톤 온건화** (사용자 요청 — "지금보다 평이/친절/덜 극적"):
  - 수사적 질문 *1 섹션당 1~2회* → *보고서당 0~1회*
  - lede 예시 교체: "35년의 봉인이 한 번에 풀렸다 / 무대 위에 올랐다" 같은
    극적 톤 → "9월 27일, 미국은 베르베라항 사용권 확보를 공식 발표했다.
    35년 만의 외교 신호다." 같은 평이한 톤
  - 신문 표제어 ban 리스트 신설 (봉인 / 무대 위에 / 변곡점 / 거대한 파장 /
    격동의 / 운명의 / 칼끝 / 풍전등화 / 백척간두 / 일촉즉발)
  - 보수 표현 의무화 — 추정·예측 영역에서 "~로 보인다 / ~할 가능성"
  - editorial 컴포넌트 빈도 (lede / analogy / fact_grid / dropcap /
    pull_quote / kicker) 전부 절제 방향으로 가이드 통합
- **dead persona 7개 모듈 + 그 테스트 삭제**:
  - `src/agents/{player,dynamics,chain_reaction,scenario,visual,
    quality_inspector,synthesis_judge}_analyst.py` 또는 `_judge.py` 7개 파일
  - `src/tests/test_quality_gates.py` (QualityInspector/SynthesisJudge 테스트)
  - `src/orchestrator.py` 의 7개 import + 인스턴스화 + `_wire_telemetry`
    의 list iteration 정리
  - `src/agents/__init__.py` 의 deprecated 7종 + lens 별칭 3종 export 정리
- **dead flag 6종 삭제** — `src/token_budget.py` 의
  `use_llm_quality_gate / use_llm_narrative_plan / use_llm_executive_summary /
  use_llm_visuals / use_llm_synthesis / use_legacy_personas`. v4.0.0 부터 모든
  mode 에서 False 였고 호출하던 agent 가 삭제됨. `allow_meta_lenses` 는
  `lens_policy` 가 검사하므로 보존. `src/tests/test_token_optimization.py`
  의 dead flag assertion / `TestDeprecatedPersonasGated` /
  `TestSynthesisJudgeGating` 블록 삭제.
- **사용자 노출 문구 일반화** — `src/telegram_bot.py:286` 의 "ScenarioArchitect 의
  watch_signals" → "보고서의 watch_signals" (dead agent 이름 사용자 노출 제거).

**영향**:
- 보고서 본문 톤이 신문 칼럼 흉내에서 *친절한 편집자의 차분한 설명* 으로
  shift. 극적 형용사·수사적 질문·editorial 컴포넌트 빈도 모두 절제됨.
- 어휘·어조 규칙이 한 곳 ([REPORT_STYLE_GUIDE.md](docs/REPORT_STYLE_GUIDE.md))
  에 모임. 향후 문체 변경은 SSOT 한 곳만 손대면 됨 (anti-pattern #1 해소).
- 코드베이스 ~2000 줄 감소 (dead agent + dead test + dead flag).
- 호출 경로 변경 없음 — composer 와 context 의 입력/출력 형태는 그대로,
  단지 persona 필드 하나가 사라짐 (downstream 코드 미사용).

---

## [v5.2.8] — 2026-05-17

### Fixed — compact-strip 이 데스크탑/태블릿에서 본문 좌우를 넘어가던 회귀

사용자 보고: 콤팩트 스트립 차트가 데스크탑·태블릿 뷰포트에서 보고서 본문
(`.container` max 960px) 의 좌우 폭을 **넘어서서** 렌더링.

- **원인**: v5.2.5~v5.2.7 의 `.compact-strip` 이 의도적으로 break-out —
  `width: min(1100px, calc(100vw - 48px))` + `position: relative; left: 50%;
  transform: translateX(-50%)` 로 본문 폭을 escape 해 viewport 폭까지 확장.
  당시엔 모크업(1200px wrap)의 시각 정합 우선이었으나 사용자 시점에선
  본문과 분리된 폭이 부자연스러움.
- **수정**: break-out 제거 → `width: 100%; max-width: 100%;
  box-sizing: border-box` 로 본문 폭에 conform. grid `repeat(3, ...)` →
  `repeat(2, ...)` 으로 desktop/tablet 공통 2-col. 920px 미디어쿼리 분기
  삭제 (base 가 이미 2-col). 모바일(≤600px) 1-col stack 은 유지.
- **차트 수 가변 처리**: 2-col grid 의 자연 wrap — 3개 → 2x2 (마지막 1셀),
  5개 → 2x3 (마지막 1셀), 7개 → 2x4 (마지막 1셀) 등. odd N 의 마지막 왼쪽
  셀은 `:last-child` 로 separator 자동 제외.
- **세로 구분선**: nth-child(3n) → nth-child(2n) 기준으로 재배치.
- **회귀 가드**: `tests/regression/test_compact_strip.py` 의
  `test_compact_strip_css_breaks_out_of_narrow_container` 를
  `test_compact_strip_css_stays_within_container_width` 로 반전 + 신규
  `test_compact_strip_css_two_column_grid_on_desktop_tablet` 추가.
  16/16 통과.

---

## [v5.2.7] — 2026-05-16

### Fixed — 시계열 차트 takeaway 가 모든 차트에서 동일 + 소수점에서 절단되던 회귀

사용자 보고 (`analysis_20260516_230827`): DXY 차트의 takeaway 가
`"미국 10년물 국채 금리가 5월 15일 4"` 로 표시 — ① DXY 차트인데 미국채
얘기 (모든 시계열 차트가 같은 takeaway), ② 중간에서 끊김.

- **원인**: `src/orchestrator.py:_format_ts_takeaway` 가
  `context.summary.split(".")[0]` 을 1순위로 반환. 두 회귀 동시 유발:
  ① `context.summary` 는 보고서 전역 1개라 모든 차트가 같은 문장,
  ② `"4.52%"` 의 `.` 에서 split 되어 `"4"` 까지만 추출.
- **수정**: 전역 summary 경로 *제거*. 데이터 기반 결정적 takeaway 로 단일화 —
  `{instrument} 기간 중 {lo}~{hi} 사이 {상승/하락/횡보} — 마지막 {last}
  ({±N.NN}%), 변동폭 {N.N}%`. 차트마다 instrument + data 다르므로 자연히
  per-chart 차별화. 소수점 split 같은 절단 경로 없음.
- **기존 보고서 retro-fix**: `scripts/patch_report.py` 에
  `--regenerate-ts-takeaways` 플래그 추가. 시계열 차트 (line/area/candle) 의
  takeaway 만 새 로직으로 재계산 (LLM 호출 X). composer-emitted 비-시계열
  (network/donut/gantt) 은 건드리지 않음.
- **회귀 가드**: `tests/regression/test_ts_takeaway.py` 신규 — 소수점 절단 /
  차트별 차별화 / direction & range 키워드 / candle close 필드 / summary
  독립성 6종 검증.

### 사용법 (배포된 보고서 retro-fix)

```bash
# 예: analysis_20260516_230827 의 takeaway 재생성 + 재배포
python scripts/patch_report.py 20260516_230827 --regenerate-ts-takeaways
```

---

## [v5.2.6] — 2026-05-16

### Fixed — 달러인덱스(DXY) 가 ICE 가 아닌 Fed Broad TWI 를 가져오던 회귀

사용자 보고 (`analysis_20260516_230827`): 달러인덱스 차트가 `117.54 → 118.04`
로 표시 — 시장 통념의 DXY (최근 99~110) 와 ~15~20pt 어긋남.

- **원인**: `src/tools/market_fetcher.py:INSTRUMENT_REGISTRY["DXY"]` 가
  FRED 시리즈 `DTWEXBGS` (Nominal Broad U.S. Dollar Index, 2006-01=100,
  26개국 가중 — CNY·MXN 비중 큼, 최근 117~125 레인지) 를 가져와 "달러인덱스"
  로 라벨링. 시장에서 통용되는 DXY 는 **ICE U.S. Dollar Index**
  (1973-03=100, EUR 57.6 / JPY 13.6 / GBP 11.9 / CAD 9.1 / SEK 4.2 /
  CHF 3.6 6-통화 고정 바스켓, 최근 99~110 레인지) 로 완전히 다른 지수.
  FRED 무료 API 엔 ICE DXY 가 없음 (ICE 독점) — 가장 가까웠던 `DTWEXM`
  (Major TWI) 도 2019-12 단종.
- **수정**: DXY 라우팅을 Yahoo Finance 의 `DX-Y.NYB` 티커 (ICE U.S. Dollar
  Index 의 표준 Yahoo 심볼) 로 교체. `_TYPE_TO_GUARD` / chart_type 변경 없음
  (계속 line). Yahoo 인프라는 이미 v5.2.1 부터 코스피 (`^KS11`) / 코스닥
  (`^KQ11`) 용으로 가동 중이라 추가 의존성 없음.
- **회귀 가드**: `tests/test_market_fetcher.py:test_dxy_routed_to_yahoo_ice_ticker`
  추가 — `DTWEXBGS` 회귀 차단 + `DX-Y.NYB` 명시.
- **기존 보고서 영향**: `analysis_20260516_230827` 의 117.54 → 118.04 수치는
  DTWEXBGS 입장에선 올바른 값이지만 "달러인덱스" 라벨이 잘못됐던 것. 신규
  보고서부터 진짜 ICE DXY 값으로 표기. 기존 배포된 HTML 은 retroactive 패치
  불가 — 사용자가 동일 사건을 재분석하면 갱신됨.

---

## [v5.2.3] — 2026-05-15

### Fixed — KOSPI 보고서 (analysis_20260515_230117) 차트 렌더링 4건 결함

사용자 보고: 코스피 line 차트의 영역(area) fill 그라데이션 누락 / 차트가 좌측
치우침 / 우측 끝 값 라벨이 부동소수점 그대로 노출 ("7493.180175125") /
3개 차트(코스피·삼성전자·SK하이닉스) 가 동일한 1-5 번호 마커와 동일한 풋노트.

- **`src/templates/static/charts.js` `drawLine`** — area fill 을 단색
  (`fill: t.accent, fill-opacity: 0.10`) 에서 `linearGradient` (상단 alpha 0.28
  → 하단 0.02) 로 교체. `drawArea` 의 그라데이션 정의와 동일 패턴 — 두 함수
  시각 언어 일관성 회복. (결함 #1)
- **`src/templates/static/charts.js` `drawLine`** — `computeZones` 의
  `right: 110 → 70`, `scalePoint` 의 `padding: 0.1 → 0.04`. 우측 110px 가
  빈 채로 남아 차트가 왼쪽 치우치는 인상을 주던 현상 해소. `placeEndLabel`
  후보 위치들이 좌측으로도 떨어질 수 있어 110 은 과도. (결함 #2)
- **`src/templates/static/charts.js` `drawLine`** — `placeEndLabel(...
  String(last.y) ...)` 의 raw float 전달 → `Math.abs(lastY) >= 1000` 이면
  `d3.format(',.0f')` 로 정수 천단위, 그 외엔 `d3.format(',.2f')` 로 소수
  2자리. Y 라벨 포맷 규칙과 일치. (결함 #3)
- **`src/orchestrator.py` `_attach_event_markers`** — `instrument` 매개변수
  추가. `context.timeline` 전체를 모든 차트에 균등 부착하던 v5.2.2 회귀
  수정. 차트별 필터링 규칙:
  - 지수/벤치마크 차트 (코스피·코스닥 등) → 모든 이벤트 흡수
  - 자기 instrument 이름 명시된 이벤트 → 부착
  - 어떤 instrument 도 명시 안 된 일반 시장 이벤트 → 개별 자산 차트도 흡수
  - 그 외 (다른 instrument 가 명시된 이벤트) → 스킵
  - `instrument=""` 면 종전 동작 (모든 이벤트 통과) — backward-compat.
- **`src/orchestrator.py:VERSION`** `v5.2.2 → v5.2.3`.

### Added — 기존 보고서 소급 패치 스크립트 (`scripts/patch_existing_reports.py`)

v5.2.2 에서 이미 생성·배포된 보고서를 LLM 재호출 없이 v5.2.3 결함 해소 상태로
끌어올리는 일회용 도구. 두 단계 동시 처리:

1. `reports/charts.js` 를 v5.2.3 의 `src/templates/static/charts.js` 로 덮어쓰기
   → 결함 #1/#2/#3 (drawLine 로직) 즉시 해소.
2. `reports/analysis_*.html` 안의 `<script class="chart-payload-inline">`
   inline JSON 의 `data[].event` 필드를 instrument-aware filter 로 재계산
   → 결함 #4 (모든 차트 동일 1-5 사건) 해소.

원본은 `*.bak` 로 idempotent 백업. 운영자가 결과 확인 후 `wrangler pages deploy`
로 재배포. 사용법은 docstring 또는 DEVLOG v5.2.3 §"기존 보고서 소급 패치" 참조.

### Notes

- chart_gate / chart_critic / market_fetcher 미변경.
- 데이터 모델 변경 없음.
- charts.js 의 `drawArea` 는 이미 linearGradient 사용 중이라 변경 불필요 —
  이번 회귀는 `drawLine` 단독.
- 별도 스크립트 `scripts/patch_report.py` (ComposedReport JSON → ReportSynthesizer
  재렌더) 와 `scripts/patch_existing_reports.py` (HTML inline JSON 직접 패치)
  는 다른 용도로 공존. 후자가 더 가벼움 — composer JSON 보존 안 된 보고서에도
  적용 가능.

---

## [v5.2.2] — 2026-05-15

### Enhanced — `_ensure_time_series_chart` hook 을 mockup 수준 quality 로 보강

사용자 피드백: "차트는 적극적으로 박혀도 되지만, *mockup 수준의 정합성과 시인성*
은 필수." 이전 v5.2.1 hook 은 단순한 fallback 형태 (제목 "코스피 시계열", 이벤트
마커 없음, takeaway 없음) — 보고서 quality 가 mockup 보다 낮음. 이번 강화로 hook
이 생성하는 차트도 mockup 과 동일 시각화 정합성 확보.

**시그니처 변경**: `_ensure_time_series_chart(composed, time_series: list)`
→ `_ensure_time_series_chart(composed, context: ContextAnalysis)` —
timeline / summary 접근 위해 context 전체 받음. `patch_report.py
--ensure-time-series` 호출처도 갱신.

**적극 모드** (사용자 요청): composer 가 일부 instrument 만 emit 하고 나머지
빠뜨린 경우, hook 이 *모든 누락 instrument 를* 차트로 추가. composer 가 박은
instrument 는 제목 매칭으로 detect → skip (중복 회피).

### 차트 quality enhancement (5종)

1. **이벤트 마커 자동 부착** — `_attach_event_markers` 신규. context.timeline
   의 각 event 의 date 와 series.data row 의 date 매칭 → row 에 `event`
   필드 부착. charts.js 가 *자동으로* 번호 배지(❶❷❸) + 하단 footnote 렌더.
   mockup 의 핵심 시각 정합성.
2. **사용자 친화 title** — `_format_ts_title`:
   · Yahoo 지수 → "코스피 종합지수" / "코스닥 종합지수"
   · KRX 개별주 → "삼성전자 (005930)" / "SK하이닉스 (000660)"
   · 그 외 → instrument 이름 그대로
3. **변화율 명시 subtitle** — `_format_ts_subtitle`:
   "2026-04-15 ~ 2026-05-15 · -4.75% (284,000 → 270,500)" 형태. 사용자가
   차트 보지 않고도 *수치적 narrative* 파악.
4. **자동 takeaway** — `_format_ts_takeaway`:
   · 1순위: `context.summary` 첫 문장 (≤100자)
   · 2순위 (summary 없으면): 변동성 기반 — "기간 중 최고 X · 최저 Y — 변동폭 Z%"
5. **출처 표기** — `_format_ts_source`:
   "Yahoo Finance / 2026-04-15 ~ 2026-05-15 · 일간" — source / period / frequency
   3중 명시.

### 회귀 테스트 14건 추가 (기존 8건 갱신 + 6건 신규)

- mockup 품질 검증 — title / subtitle / source / takeaway / event markers
- 적극 모드 검증 — composer 가 일부 instrument 만 emit 했을 때 누락분 보충
- composer 가 같은 instrument 박았으면 중복 회피
- 후보 우선순위 (data 많은 순)
- 모든 no-op edge case (timeline 없음 / data 없음 / sections 없음)

전체 **119/119 통과** (test_market_fetcher 29 + test_chart_correctness 54 +
test_composed_section_guard 36).

### Notes

기존 보고서 `20260515_230117` 복구: `patch_report.py --ensure-time-series`
호출 시 새 quality 적용 (이벤트 마커 + 한국어 title + subtitle 변화율 등).

---

## [v5.2.1] — 2026-05-15

### Fixed — composer 가 available_time_series 무시하는 case C 회귀

20260515_230117 보고서 ("삼성전자·SK하이닉스 동반 급락 — 코스피 8000 사상 첫
돌파 직후 6% 폭락") 진단 결과:
- ContextAnalyst: `['코스피', '삼성전자', 'SK하이닉스']` 정상 emit
- orchestrator: 3 종목 모두 61 bars 실 OHLC fetch
- **composer LLM**: `available_time_series` payload 받았지만 *시계열 차트 0개* —
  대신 bar / donut / bubble (사건성 차트) 만 emit. 변동성 narrative 인데 핵심
  시각화 누락.

원인: v5.2.0 의 composer SYSTEM_PROMPT 가 "데이터 있다고 무조건 차트 만들지
말 것" 룰로 너무 보수적. LLM 이 차트 안 만들어도 되는 신호로 해석.

### Added — orchestrator 결정적 안전망 + composer prompt 강화

- **`src/orchestrator.py:_ensure_time_series_chart`** 신규 — composer 호출 직후
  실행. composer 가 시계열 차트 0개 emit 했고 `time_series` 데이터는 있을 때,
  가장 data 많은 series 를 그 series 의 `chart_type` 으로 변환해 sections[0].
  charts[0] 에 자동 삽입. composer 가 1개 이상 박았으면 no-op.
- **`src/agents/narrative_composer.py:SYSTEM_PROMPT`** 시계열 차트 섹션 강화:
  · "★ 강제 규칙 (v5.2.0+, 예외 없음)" 표기로 명시성↑
  · "available_time_series 가 비어있지 않으면 *반드시 최소 1개* 시계열 차트
    emit. 0개 emit 절대 금지" 룰 도입
  · 사건성 보고서 (변동·급등·급락·폭락 narrative) 는 관련 instrument *전부*
    차트로 (한 종목만 emit 하고 나머지 빠뜨리는 것 금지)
  · 차트 type 매핑 (지수=line / 개별주=candle / 원자재=area) 명시
  · "데이터 있다고 무조건 차트 만들지 말 것" 룰은 v5.2.0 이전 거로 명시 정정
- **`scripts/patch_report.py:--ensure-time-series`** 옵션 신규 — 기존 보고서를
  사후 복구. orchestrator 의 `_ensure_time_series_chart` 헬퍼 재사용. 회귀
  보고서 (20260515_230117 같은) 복구용.

### Added — 회귀 테스트 8건 (tests/regression/test_composed_section_guard.py)

- `test_ensure_ts_chart_adds_when_composer_skipped` — case C 회귀 가드
- `test_ensure_ts_chart_noop_when_composer_already_emitted` — 1개 이상이면 no-op
- `test_ensure_ts_chart_noop_when_no_time_series` — 데이터 없으면 no-op
- `test_ensure_ts_chart_noop_when_time_series_data_empty` — 빈 data 만이면 no-op
- `test_ensure_ts_chart_noop_when_no_sections` — sections 없으면 no-op
- `test_ensure_ts_chart_respects_chart_type_for_candle` — OHLC shape 보존
- `test_ensure_ts_chart_maps_xy_for_line` — line/area 는 {x,y} 형태로 변환
- `test_ensure_ts_chart_picks_most_data_rich_series` — 후보 다중일 때 우선순위

전체 109/109 통과.

---

## [v5.2.0] — 2026-05-15

Market Data Fetcher + 시계열 차트 (candle/area) + chart_gate production wiring +
mode-aware period + drawLine 이벤트 마커 통일. 본 릴리스로 CHART-AP-15/16 의
근본 원인 (시계열 데이터 부재 + 가드 비활성) 둘 다 해소. composer 가 같은 실수
해도 가드 자동 차단, 진짜 OHLC 로 차트 emit.

운영자 단계: VM 에 `pip install pykrx yfinance` + `.env` 에 `FRED_API_KEY` /
`ECOS_API_KEY` 추가 + 봇 재시작. 다음 보고서부터 코스피·삼성전자·DXY·국고 10Y·
미국채 1Y·WTI 등 실 OHLC 자동 차트 emit. `python scripts/verify_market_fetcher.py`
로 봇 재시작 전 안전망 검증.

### Fixed — chart_gate production wiring (CRITICAL)

이전엔 `run_chart_gate` / `validate_chart_data` 가 정의만 있고 production
경로에서 *호출 안 됨* (V5 Phase 6 flag 디폴트 OFF 때문). CHART-AP-15/16 가드
모두 dormant 상태였음 — composer 가 위반 차트 emit 해도 그대로 통과.

- **`src/models.py:ComposedSection._drop_invalid_charts`** — Pydantic
  `@model_validator(mode="after")` 신설. composer JSON 파싱 직후 *디폴트 ON* 으로
  각 차트 dict 에 `validate_chart_data` 호출. 위반 차트만 silent drop + warning
  log. 합법 차트는 절대 안 건드림. validator 자체 raise 도 차트 보존 (composer
  토큰 12~32K 비용 회피).
- **`tests/regression/test_composed_section_guard.py`** — 신규 17건 회귀 테스트.
  AP-15/16 의 실제 회귀 케이스 + 합법 차트 보존 + edge cases.

### Added — drawLine 의 이벤트 마커 통일 (Bloomberg/FT 스타일)

기존 `drawLine` 의 inline event 는 *점선만* 그리고 라벨 X — 어떤 이벤트인지 알
수 없었음. v5.2.0 에서 candle/area 에 도입한 번호 배지 + footnote 패턴을 line
에도 적용 (3 type 일관 스타일).

- **`src/templates/static/charts.js:drawLine`** — `data.filter(d=>d.event)`
  의 legacy dotted-line 만 그리던 블록을 `_renderEventBadgesAndFootnote`
  호출로 교체.

### Added — Mode-aware period 선택

market_fetcher 가 받는 fetch 기간을 사건/리포트 성격으로 분기:

- **`src/orchestrator.py:_select_market_period`** — 헬퍼 신설.
  daily briefing 키워드 (간밤/어제/오늘 등) → "1M",
  historical 키워드 (IMF/외환위기/10년 만에 등) → "3Y",
  기본 → "3M" (사건 보고서 event-anchored ±30일).

### Added — KRX ISIN 동적 lookup

기존 `_ISIN_MAP` 은 삼성전자/SK하이닉스 2개만 하드코딩. 사용자가 다른 종목
mention 하면 fetcher 가 빈 결과 반환했음. KRX search endpoint 로 동적 조회.

- **`src/tools/market_fetcher.py:_lookup_isin`** — KRX `finder_stkisu` POST 로
  6자리 코드 → ISIN 동적 조회. 결과는 `_ISIN_MAP` cache 에 자동 저장.
  하드코딩 seed 도 NAVER/카카오/현대차/LG화학/삼성SDI/삼성바이오 추가 (8 종목).

### Added — 운영 검증 스크립트

- **`scripts/verify_market_fetcher.py`** — `.env` 의 키로 6 종목 1M fetch 시도.
  ✅/❌ 표시 + 빈 응답 사유. 봇 재시작 *전* 키 검증용. pykrx/yfinance 설치 상태도 표시.

### Fixed — KRX 우회 (pykrx + Yahoo Finance 하이브리드)

운영 환경 verify 에서 두 차례 KRX 이슈 발견 → 단계적 해결.

- 1차: `src/tools/market_fetcher.py:KRXFetcher` 가 aiohttp 직접 POST → 모든
  KRX 종목이 `HTTP 400 LOGOUT` 으로 실패. warm-up GET 추가해도 미해결.
- 2차: **pykrx 로 전환** — 한국 거래소 scraping 표준 라이브러리. 개별주
  (삼성전자/SK하이닉스) 정상 fetch. requirements.txt 에 `pykrx>=1.0` 추가.
- 3차: pykrx 의 *지수* endpoint (`get_index_ohlcv`) 가 OTP 인증 우회 실패 →
  KOSPI/KOSDAQ 만 **Yahoo Finance** (`yfinance`) 로 우회 (`^KS11` / `^KQ11`
  ticker 무인증 안정). 개별주는 pykrx 그대로. requirements.txt 에 `yfinance>=0.2.40`
  추가. `INSTRUMENT_REGISTRY` 의 KOSPI/KOSDAQ source `'KRX'` → `'YAHOO'`.
- 데이터 정합 검증 — pykrx ↔ Yahoo cross-check 로 OHLC/거래량 byte-equal 확인
  (운영자 매뉴얼 검증).

---

### Added — 시계열 데이터 파이프라인 (B 안)

ContextAnalyst LLM 이 본문에서 다루는 금융 instrument 를 ``instruments_mentioned``
로 emit → orchestrator 가 KRX / FRED / ECOS 에서 실 OHLC fetch →
``ContextAnalysis.time_series`` 에 저장 → composer 가 line / candle / area
차트로 emit. 가짜 데이터 / 추정값 차트 회귀 (CHART-AP-15/16 의 근본 원인) 해소.

- **`src/tools/market_fetcher.py`** (신규) — FRED / ECOS / KRX 3 fetcher 통합.
  `INSTRUMENT_REGISTRY` 11 종목 (코스피·코스닥·삼성전자·SK하이닉스·DXY·UST 1Y/10Y·
  WTI·금·국고 10Y·원/달러). `resolve_instrument(query)` 한국어 alias 매칭.
  `fetch_market_series` / `fetch_many` async API. graceful degradation —
  API key 없으면 빈 series + warning log (보고서 진행).
- **`src/models.py`** — `ContextAnalysis.instruments_mentioned`, `time_series`
  필드 신설.
- **`src/agents/context_analyst.py`** — SYSTEM_PROMPT 에 `instruments_mentioned`
  emit 가이드 추가 (지원 종목 + 규칙 명시).
- **`src/orchestrator.py`** — Phase 1 직후 market_fetch hook. 사건 일자 anchor +
  3M 기본 기간 + 병렬 fetch. fetch 실패해도 보고서 흐름 영향 X.
- **`src/agents/narrative_composer.py`** — composer payload 에 `available_time_series`
  포함 + SYSTEM_PROMPT 에 "시계열 차트 데이터는 반드시 fetched series 만" 규칙.
- **`src/config.py`** — `FRED_API_KEY` / `ECOS_API_KEY` / `KRX_API_KEY` 환경변수.
- **`.env.example`** — 3 키 자리 + 발급 링크.

### Added — Candle / Area 차트 type

`charts.js` 의 11 type 에서 13 type 으로. 두 신규 type 은 시계열 OHLC 차트
전용이며 *반드시 market_fetcher 데이터로만 emit* (composer 가 추정 금지).

- **`src/templates/static/charts.js`** — `drawCandle` (OHLC body + wick, accent=bull
  outline / down=bear fill) + `drawArea` (line + gradient) 신규. 공통 헬퍼
  `_renderEventBadgesAndFootnote` — Bloomberg/FT 풍 번호 배지 (상단 same-Y +
  가로 cascade + leader line) + HTML footnote (`.chart-card-footnote` 안).
- **`src/templates/static/charts.css`** — `.chart-card-footnote` / `.chart-note-row`
  / `.chart-note-num` / `.chart-note-date` / `.chart-note-text` 토큰.
- **`src/visual/schemas.py`** — `CandleChartGuard` (data ≥2 + OHLC 순서 일관성
  low≤open≤high / low≤close≤high) + `AreaChartGuard` (line 과 동일 + finite).
  `_TYPE_TO_GUARD` 에 등록.
- **`tests/regression/test_chart_correctness.py`** — Candle / Area 가드 회귀 9건.
- **`tests/test_market_fetcher.py`** — 파서·라우팅·graceful degradation 25건 (모킹 only).

### Notes

- `enable_visual_planner` 등 V5 flag 와 *독립적* — 디폴트 ON. fetcher 는 API key
  유무로만 분기. 봇 운영자가 `.env` 에 키 추가 → 다음 보고서부터 자동 작동.
- 이번 commit 으로 CHART-AP-15 (gantt zero-duration) / CHART-AP-16 (donut 2-segment)
  의 *근본 원인* (= 시계열 데이터 부재로 composer 가 부적합 차트 선택) 해소.

---

### Fixed — donut 2-segment 빈 카드 + gantt zero-duration 빈 차트 회귀

20260515_125106 보고서 ("코스피 8000 돌파") 에서 2건의 차트 type 선택 회귀
사용자 보고. 둘 다 *데이터 결함이 아니라 type 선택 결함* — composer 가
부적합한 type 을 골랐고 가드 인프라가 못 잡음.

- **CHART-AP-15** (gantt zero-duration emit): "2026년 5월 코스피 8000 돌파
  타임라인" gantt — 7개 row 중 6개가 `start == end` (point-in-time 이벤트 모음).
  본질이 *event sequence* 이지 *duration timeline* 이 아니어서 gantt 부적합.
  `GanttGuard.validate_durations` 신규 — zero-duration ratio > 70% 면 reject.
- **CHART-AP-16** (donut 2-segment 안티패턴): "외국인 5월 누적 순매도 구성"
  donut — `[{반도체:16.8}, {비반도체:3.4}]` 2 segment. "비반도체" 잡탕 segment
  로 정보 손실 + subtitle 이 같은 비율(83%) 이미 전달 + 렌더러 (`drawDonut`)
  가 `< 3` 이면 silent return 해서 *제목·부제만 보이는 빈 카드*로 회귀.
  `DonutGuard.validate_segment_count` 신규 — segment < 3 이면 reject.

**수정**:
- `src/visual/schemas.py` — `DonutGuard` `min_length=2 → 1` + `validate_segment_count`,
  `GanttGuard` + `validate_durations`.
- `src/agents/narrative_composer.py:SYSTEM_PROMPT` donut / gantt spec 행에
  AP-15 / AP-16 명시.
- `docs/CHART_RENDERING_ANTIPATTERNS.md` AP-15, AP-16 append + `last_synced_with`
  → v5.1.2 + "누적 16개" 갱신.
- `CLAUDE.md` Anti-Patterns (차트 렌더링) 섹션 16개 패턴 / AP-15, AP-16 라인 추가.
- `tests/regression/test_chart_correctness.py` 회귀 테스트 4건 추가.
- 기존 보고서는 `scripts/patch_report.py 20260515_125106 --remove-chart 2:0
  --remove-chart 4:0` 로 일회성 정리 (LLM 호출 0).

---

## [v5.1.2] — 2026-05-14

### Changed — Daily Briefing 기본 트리거 시각 07:30 → 06:00 KST

`DAILY_BRIEFING_TIME` 디폴트를 `"07:30"` 에서 `"06:00"` 으로 조정. 시장 개장
(09:00 KST) · 외교 일정 시작 전에 더 일찍 노출하기 위함. 운영 중인 환경에서
`.env` 의 `DAILY_BRIEFING_TIME` 으로 override 한 경우 영향 없음 (env 우선).

**수정**:
- `src/config.py` `daily_briefing_time` Field default `"07:30" → "06:00"`.
- `src/scheduler/daily_briefing.py` `run_daily_briefing_loop(time_str=...)`
  default `"07:30" → "06:00"` + `_build_briefing_prompt` 안내 docstring 동기화.
- `.env.example` `DAILY_BRIEFING_TIME=07:30 → 06:00`.
- 문서 (`README`, `WORKFLOWS`, `GOAL`, `docs/ARCHITECTURE`, `docs/REPO_MAP`) 의
  "기본 07:30 KST" 표기 동시 갱신. v5.1.0~v5.1.1 의 출시 디폴트는 GOAL 의
  REQ-V5-101 노트에 명시 (히스토리 보존).
- `src/orchestrator.py:VERSION` `v5.1.1 → v5.1.2`.

### Notes

- 기능·구조 변경 없음 — 단일 디폴트 상수 조정. 스케줄러 task / DB 스키마 /
  텔레그램 명령 / 프롬프트 본문은 모두 그대로.
- 실행 중인 봇은 재기동 후 다음 트리거가 06:00 으로 잡힘. `/briefing_status`
  로 시각 확인 가능.

---

## [v5.1.0] — 2026-05-13

### Added — 자동 일일 브리핑 시스템

매일 지정 시각 (기본 07:30 KST) 에 "간밤 산업·지정학·정치·전쟁 이슈" 심층 보고서를
자동 생성·배포·텔레그램 송신. 별도 cron / systemd timer 없이 봇 프로세스 안 asyncio
task 로 동작 (watchlist monitor 와 동일 패턴).

**신규 모듈** `src/scheduler/`:
- `subscriptions.py` — `BriefingSubscriberRegistry` (SQLite CRUD; 구독 + 실행 이력)
- `daily_briefing.py` — `run_daily_briefing_loop()` background task + `_next_trigger()`
  / `_build_briefing_prompt()` 순수 함수
- `db_schema.sql` — `briefing_subscribers` + `briefing_runs` 두 테이블
  (`run_date` PRIMARY KEY 로 같은 날 중복 트리거 방지)

**신규 텔레그램 명령**:
- `/briefing_on` — 이 채팅을 일일 브리핑 수신처로 등록 (mode='deep' 고정)
- `/briefing_off` — 구독 해제
- `/briefing_status` — 구독 상태 + 스케줄러 활성 여부 + 시각/타임존 표시

**신규 환경변수** (`Config` 에 `AliasChoices` 패턴으로 추가):
- `DAILY_BRIEFING_ENABLED` — 디폴트 `false`. task 는 항상 살아 있고 구독은 받지만,
  트리거 시각에 실제 분석 실행 여부를 게이트. `false` 시 스킵 + 로그만.
- `DAILY_BRIEFING_TIME` — 디폴트 `07:30`. HH:MM (24h), `DAILY_BRIEFING_TZ` 기준.
- `DAILY_BRIEFING_TZ` — 디폴트 `Asia/Seoul`. IANA tz (예: `UTC`, `Asia/Tokyo`).

### Notes

- 일일 브리핑은 기존 v4.0.0 Tier 4 2-call 파이프라인 (`ContextAnalyst` + `NarrativeComposer`) 을 `mode='deep'` 으로 호출 — composer 프롬프트가 5~7 섹션 + 모순 명시.
- 브리핑 프롬프트는 ContextAnalyst 가 웹 검색으로 간밤 보도를 직접 확인하도록 명시 (학습 데이터 의존 금지). `mode='deep'` 강제 + 프롬프트에 "심층" 키워드 자연 포함.
- 봇 재시작 시 별도 복구 호출 불필요 — `BriefingSubscriberRegistry` SQLite 영속성으로 구독자 자연 복구.
- 같은 날 봇 재시작 + 트리거 시각 통과 케이스에서도 `briefing_runs.run_date` PK 가 중복 분석을 막음.
- `/status` 응답에 일일 브리핑 활성 여부 + 구독자 수 표시.

### Changed

- `src/orchestrator.py:VERSION` `v5.0.0 → v5.1.0`.

---

## [v5.0.0] — 2026-05-05

REFACTOR_V5_PLAN.md 17-Phase 마스터 플랜 완료. v4.5.7 호출 경로 byte-equal 보존 — V5 신규 모듈은 모두 opt-in (`V5_*` env flag, 디폴트 OFF).

**Tier 1 (Phase 0/0B/0C)** — Baseline + Golden Evaluation Harness (20 prompt + 회귀 17종) + 6-tier State 모델 (RawContext → EvidencePack → AnalysisBrief → DraftReport → ExhibitPack → PublishManifest).

**Tier 2 (Phase 1A/2/2A/2B)** — ResearchDirector (9-method 라우팅) + VisualPlanner (Vega-Lite spec) + EvidenceDataset Contract (AP-V5-24/25/26) + Capability Registry (16 chart type, AP-V5-27).

**Tier 3 (Phase 6/6A/7A/7/8/8A)** — Chart Gate (Schema/Critic/Sanity/Fallback) + Exhibit Priority + Deterministic Gate (11 Hard + 5 Soft) + DeskEditor (Logical 7 + Visual 8 rubric) + Strategic Mode (7 prefix + 8 패턴 + 8 필수 출력).

**Tier 4 (Phase 1/3/4/5)** — Editor Pass (7-rubric copy editing) + Layout Primitives (9-vocab AP-V5-3) + Exhibit 번호제 (`[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]`, AP-V5-6) + Word Budget (5종 truncation signal + adaptive max_tokens, deep 64K, WRITE-AP-8 해소).

**활성화:** `docs/V5_ACTIVATION.md` 5-step 절차. `V5_RESEARCH_DIRECTOR=1` / `V5_VISUAL_PLANNER=1` / `V5_EDITOR_PASS=1` / `V5_LAYOUT_TYPESETTER=1` / `V5_DESK_EDITOR=1` 환경변수로 단계적 활성화.

**회귀 baseline:** v4.5.7 124 pass / 52 fail / 1 skip. V5 진보 측정은 후속 phase 별 baseline 재측정.

**Anti-pattern:** AP-V5-1 ~ AP-V5-32 누적, 회귀 테스트로 강제.

**진단 도구:** `scripts/retrofit_v5.py` — 기존 v4.5.7 보고서를 V5 게이트로 read-only dry-run 진단.

---

## [Unreleased]

V5 활성화 후속 작업 (각 phase 별 회귀 테스트 통과율 baseline 재측정).

---

## [v5.2.5] — 2026-05-16

### compact-strip (key_figures inline) 회생 + overflow root-fix + 모크업 양식 정렬

사용자 catch 3건 (overflow → 모크업 정합 → 시각 분리·모바일) 을 한 번에 정리.
이전 보고서 HTML (사용자 사전 push) 에는 있었으나 repo 에 미커밋 상태였던
`.compact-strip` 구현체를 회생시키며 v5.2.4 P0-Patch7 의 grid overflow 회귀를
근본 차원에서 fix.

**근본 원인 (회귀 1):** v5.2.4 의 `grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))`
+ flex children 의 고정 min-width 합 (name 64 + value 70 + change 50 + spark 60 +
gap 30 = 274px). flex 컨테이너의 default `min-width: auto` 가 grid track 의
220px 제약을 깨고 자식 합산 min-content 로 셀을 강제 확장 → 3 셀이 .freeform-section
.container (max 780px) 의 752px 를 넘쳐 옆 셀 콘텐츠를 침범. 라벨이 옆 sparkline
위에 겹쳐 보임.

**3-단 fix:**
1. `width: min(1100px, calc(100vw - 48px))` + `left: 50%` + `transform: translateX(-50%)`
   — strip 만 .container 의 780px 를 escape, 모크업 (`samples/market_charts_mockup.html`
   §2) 의 1200px wider context 재현. 모크업 CSS 값 (name 64fixed / value min 70 /
   change min 50 / spark flex 1 min 60) 글자 그대로 보존.
2. `.compact-row { min-width: 0 }` + `grid-template-columns: repeat(3, minmax(0, 1fr))`
   — break-out 동작 안 하는 edge case 의 safety net.
3. responsive (≤920 → 2 cols, ≤600 → 1 col stack) — 모크업 wrap 미만 viewport
   에서 overflow 보다 stack 이 항상 더 가독성 좋음.

**시각 분리 강화 (사용자 catch 3):**
- col gap 10 → 24px + 셀 사이 세로 separator (`::after` pseudo, 1px line)
- 행 내부 gap 10 → 8px (라벨+수치 그룹 더 묶음) + `.compact-spark margin-left: 6px`
  ([라벨+수치] 그룹 ↔ sparkline 시각 분리)

**모바일 명시 설계 (≤600px):**
- 1-col stack + 각 row 가 padding 10 + border-bottom 으로 독립 ticker 단위
- `:first-child` / `:last-child` padding·border reset
- name/value/change 폭 축소 (64/70/50 → 56/60/44) — 좁은 viewport fit

### 회생된 구현체 (repo 누락분)

- `charts.css` — `.compact-strip` / `.compact-row` 전체 CSS + 반응형
- `charts.js` — `drawSparkline` + `renderSparklines` (rAF×2 + ResizeObserver
  로 layout settle 후 그림) + `init()` 의 `renderSparklines()` 호출
- `freeform_essay.html` — `sec.charts` 를 `role='compact'` / 일반으로 namespace
  분기. compact 는 strip 으로 모아 prose 직후 1회만 emit
- `orchestrator.py` — `_format_compact_value` (rate/통화/일반 분기) +
  `_build_compact_strip_row` + `_ensure_market_strip` (instrument 3개↑ 면
  sections[0] 앞에 strip 자동 emit, idempotent) + `_composer_instruments` 가
  role='compact' 도 dedupe 집합에 포함

### 회귀 가드 (`tests/regression/test_compact_strip.py` — 15 tests)

- break-out width/left/translateX 동시 lock
- 모크업 §2 의 4 값 (name 64 / value 70 / change 50 / spark 60 + flex:1 +
  overflow:hidden) 글자 그대로 lock
- `.compact-row { min-width: 0 }` safety lock
- 920/600 breakpoint lock
- 세로 separator (`::after` selector + content/background) lock
- `.compact-spark margin-left` (그룹 분리) lock
- mobile 1-col stack 에서 `border-bottom` + `:last-child` reset 동시 lock
- `_ensure_market_strip` threshold-3 + idempotency + `_composer_instruments`
  role='compact' dedupe

---

## [v5.2.4] — 2026-05-15

### Standalone HTML 모드 — report_synthesizer 정적 자산 인라이닝

`<link href="charts.css">` / `<script src="charts.js">` 를 빌드 시점에 inline
`<style>` / `<script>` 로 치환. Cloudflare Pages 외 환경 (이메일 첨부, 로컬
열기) 에서도 차트가 정상 렌더.

---

## [v4.5.7 이전 — V5 리팩토링 진행 중 단계]

V5 리팩토링 (REFACTOR_V5_PLAN.md) Tier 1 (토대) 진행:

- **Phase 0 (Baseline + SSOT Repair) — 완료.** v4.5.7 baseline 으로 문서·메타데이터 정합성 회복. 코드 변경 0 (orchestrator VERSION 은 이미 v4.5.7).
- **Phase 0B (Golden Evaluation Harness) — framework 완료, baseline 녹화 대기.** 20건 Golden Prompt fixture (8개 카테고리 정합) + 5종 회귀 테스트 (Golden / Visual / Semantic / Cost / Completeness) framework + CLI runner + record_baseline.py. py_compile 통과. 사용자가 `.env` 환경에서 `python scripts/record_baseline.py` 1회 실행 시 baseline 녹화 완료. SSOT: `tests/regression/README.md`.
- **Phase 0C (Pipeline State Compaction) — framework 완료, 후속 Phase 결합 대기.** `src/state/` 모듈 신설 — 6-tier State 모델 (RawContext / EvidencePack / AnalysisBrief / DraftReport / ExhibitPack / PublishManifest), RawContext → EvidencePack 변환 (`compact_to_evidence_pack`, `evidence_pack_from_context_analysis`), 8단계 입력 제한 강제 (`assert_input_is`, `forbid_raw_context_in`, AP-V5-30). orchestrator 에 EvidencePack adapter *telemetry 전용* 삽입 — v4.5.7 호출 경로 byte-equal 보존. 회귀 테스트 `tests/regression/test_state_compaction.py` 신설 (16건 케이스, Plan §4.5 인수 기준 #1~#3 검증). py_compile + AST + Plan §4.4 / §6.3 정적 일치 검증 통과.
- **Phase 1A (Research Director / Method Router) — framework 완료, opt-in 활성 대기.** `src/agents/research_director.py` 신설 — Plan §6.4 의 SYSTEM_PROMPT 그대로 + 9종 method enum (ACH / scenario_tree / transmission_channel / stakeholder_matrix / fault_tree / decision_matrix / pre_mortem / transmission_timeline / comparative) + 결정적 fallback `design_via_heuristics` (LLM 0) + DEFAULT_BRIEF (Plan §20.3 fallback). orchestrator 에 *opt-in flag* (`Config.enable_research_director`, env `V5_RESEARCH_DIRECTOR=1`) 로 통합 — 디폴트 OFF, v4.5.7 호출 경로 byte-equal 보존. 꺼진 환경에서도 `design_via_heuristics` 가 모든 prompt 에 AnalysisBrief 를 emit (Plan §6.6 인수 기준 #1 충족). SSOT: `docs/RESEARCH_DIRECTOR_METHODS.md` (9종 method 의 적용 사건·입력·출력·권장 시각화). 회귀 테스트 `tests/regression/test_research_director.py` 신설 — Golden Prompt 20건 expected_method 일치률 90% (Plan §6.6 인수 기준 #4 임계 80% 통과). `run_regression.py` 가 lazy import 로 sandbox graceful degrade.
- **Phase 4 (Exhibit 번호제) + Phase 5 (Word Budget + 절단 회복) — framework 완료. Tier 4 종료.** Plan §11 + §12 — V5 의 마지막 Phase 들. *V5 의 보고서 본문 품질* 의 마지막 layer.
  - `src/visual/exhibit_numbering.py` 신설 (Phase 4) — Plan §11.3 의 `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` 정규식 SSOT (`EXHIBIT_REF_PATTERN` + `EXHIBIT_REF_RANGE_PATTERN`). `assign_exhibit_ids` 자동 1부터 부여 + composer 가 박은 임의 ID 덮어씀 (AP-V5-6 강제). `resolve_exhibit_refs` (plain text) + `resolve_exhibit_refs_html` (anchor 점프) 양쪽. `validate_exhibit_refs` 가 Phase 7A 의 exhibit_ref_broken hard fail 의 사전 가드. `count_exhibit_refs` 통계 (Plan §11.5 인수 기준 — 보고서당 1~3회 권장).
  - `src/visual/word_budget.py` 신설 (Phase 5) — Plan §12 의 두 작업 통합. `MODE_TARGET_CHARS_LOWER` (Plan §6.4 byte-equal — fast 1500 / std 3500 / deep 6000) + `MODE_BUDGET_BANDS` (Plan §12.3 — peak_target / asymmetry 정도) + `COMPOSER_MAX_TOKENS_V5` (Plan §12.6 — fast 16K~24K / std 28K~40K / deep 48K~64K, **v4.5.7 의 deep 32K 한계 해소**). `detect_truncation` 5종 시그널 (production SSOT, helpers 와 byte-equal). `adaptive_max_tokens(mode, complexity)` + `complexity_score_from_context` (Plan §12.6 가중합). `compute_word_budgets` 가 mode 별 peak/support/watch 역할 분배. `gini_coefficient` + `section_length_distribution` (Plan §12.7 인수 기준 #1 측정). `stitch_continuation` 연속 호출 결합 (Plan §12.5 — 마지막 미완성 잘라내고 이어 작성).
  - 회귀 테스트 `tests/regression/test_exhibit_and_budget.py` 신설 — 32건 케이스. Phase 4 부분 (15건): assign_exhibit_ids AP-V5-6 강제 + 단일/괄호/범위/phantom resolve + HTML anchor + validate + count + 정규식 SSOT. Phase 5 부분 (17건): SSOT byte-equal + detect_truncation 4 시그널 + adaptive_max_tokens 보간 + complexity_score 가중합 + compute_word_budgets peak/role + gini 균등/집중 + stitch_continuation.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 4/5 모두 *데이터 + 함수* 형태. Renderer 결합 (Phase 4 의 anchor HTML 출력) 및 composer 호출 후 처리 (Phase 5 의 절단 검출 → 연속 호출) 는 별도 통합 작업.
  - **Tier 4 (미적 개선) 4/4 ✅ 종료. V5 17 Phase 모두 완료.**

- **Phase 3 (Layout Primitives) — framework 완료.** Plan §10 — 섹션마다 동일 구조 → *섹션별 layout 변주*. 9종 layout vocab 정본 동결 (AP-V5-3).
  - `src/state/models.py` — `LayoutPrimitive` Literal 9종 (standard / hero_map / hero_chart / split_2col / sidebar_callout / qna_panel / timeline_strip / signature_summary / exhibit_grid) + `LayoutAssignment` 모델 (section_idx + layout + why + assigned_by 3-tier).
  - `src/agents/layout_typesetter.py` 신설 — `LayoutTypesetter(BaseAgent)` (Sonnet 4.6, MAX_TOKENS=2048, 빠른 분류 작업). SYSTEM_PROMPT 가 Plan §10.3 의 결정 원칙 (60~70% standard / hero_* ≤ 1~2개 / 연속 배치 차단 / 지리 사건 hero_map 권장 등) 명시.
  - `plan_layouts_via_heuristics(sections, has_map, is_strategic, section_count)` — LLM 0 결정적 fallback. 9-vocab 모두 트리거 (지리/결론/차트≥3/Q&A 패턴/타임라인/비교/단일 결정적 차트/analogy 동반/그 외 standard) + 연속 배치 차단 + hero count ≤ 2 강제.
  - `fallback_all_standard(n)` — Plan §10.5 의 LayoutTypesetter 호출 실패 시 모든 섹션 standard fallback.
  - `Config.enable_layout_typesetter` opt-in flag (env `V5_LAYOUT_TYPESETTER=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_layout_typesetter.py` 신설 — 23건 케이스. 9-vocab SSOT (AP-V5-3 강제 가드) + LayoutPrimitive Literal 정합 + heuristic 8종 트리거 검증 + 연속 배치 차단 + hero ≤ 2 cap + fallback_all_standard + agent 모델·예산 (Sonnet 4.6, 2048).
  - HTML 템플릿 (templates/layouts/) 은 *별도 작업* — 본 commit 은 결정 로직만. 템플릿이 박힐 때까지 LayoutAssignment 는 *meta 정보* 로 telemetry / 후속 분기.

- **Phase 1 (Editor Pass) — framework 완료. Tier 4 (미적 개선) 의 첫 Phase.** Plan §5 — V5 의 *보고서 글쓰기 품질* 개선 시작점. Drafting + Editing 2 호출 — 같은 Opus 4.7 이 *editor 페르소나* 로 자기 글을 비평·재집필.
  - `src/agents/editor.py` 신설 — `Editor(BaseAgent)` (Opus 4.7, MAX_TOKENS=16000). SYSTEM_PROMPT 가 Plan §5.4 의 7-rubric (군더더기 / 결론의 칼날 / 모순 봉합 / 차트-본문 결합 / 분량 비대칭 / 신선함 / 외래어 풀이) 그대로. JSON 응답 스키마 (critique / revisions / final) 강제.
  - `EditedReport` 모델 — ComposedReport 와 호환 구조 + `editor_critique` + `editor_pass_applied` flag.
  - `SectionScore` (7-rubric 0~10 점) + `SectionRevision` (rewrite/cut/keep) + `EditorCritique` 모델.
  - `assert_signal_count_preserved(draft, edited)` — Plan §5.6 인수 기준 #3 강제. Editor 가 watch_signals / contradictions 개수를 *축소* 하면 fail → graceful fallback (draft 그대로). Anti-pattern #5 (모순 봉합) 회귀 차단.
  - `detect_cliches(text)` — Plan §5.4 Q1 (padding) 의 결정적 보조. 7종 진부어 (`주목할 만한 점은`, `결론적으로`, `대체로` 등) 매칭.
  - `Config.enable_editor_pass` opt-in flag (env `V5_EDITOR_PASS=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_editor.py` 신설 — 22건 케이스. SECTION_SCORE_RUBRICS 7종 SSOT + SYSTEM_PROMPT 7-rubric 정합 + 보존 검증 (4건) + 진부어 매칭 + EditedReport / EditorCritique 모델 + Editor 인스턴스 smoke.
  - v4.5.7 호출 경로 byte-equal 보존 — Composer DraftReport 가 Editor 통과 후 EditedReport 로 emit 되는 결합은 opt-in 시점에 활성.

- **Phase 8 + 8A (Strategic Mode + Contract) — framework 완료.** Plan §17 + §18 — 의사결정 보조 모드. *처방적* 보고서 (옵션 + 권고 + ActionPlan). 분석 모드와 *근본적으로 다른* 보고서 종류.
  - `docs/STRATEGIC_MODE_PROMPT.md` 신설 (Plan §25.1 사전 작업 #2 완료) — composer system prompt 확장 SSOT (전략 모드 7개 디폴트 섹션 + 핵심 어법 규칙) + 3-경로 감지 (prefix / 패턴 / LLM) + 한계 (LLM 의 utility function 모름) 명시.
  - `src/agents/strategic_router.py` 신설 — `EXPLICIT_PREFIXES` 7종 (`?전략` / `?분석` / `?예측` / `?비교` / `?지도` / `?짧게` / `?심층` + `/strategy` alias) + `STRATEGIC_PATTERNS` 8종 정규식 (Plan §17.2 byte-equal). `route_query(user_request, llm_user_intent)` 통합 router → `ModeRouting` (mode + detection_source + matched_prefix/patterns + cleaned_query). AP-V5-23 (모호 시 analytical 기본값) 강제.
  - `src/state/models.py` 강화 — Phase 8A 의 8개 필수 출력 모델: `StrategicReport` (decision_statement / options / criteria / constraints / decision_matrix / recommendation / kill_switch_conditions / action_plan_30_60_90) + leaf 모델 8종 (`StrategicOption` + `Criterion` + `Constraints` + `DecisionMatrix` + `Recommendation` + `ActionItem` + `ActionPlan` + `FailureMode`).
  - `KILL_RULES_STRATEGIC` (`run_strategic_kill_rules`) — Plan §17.6 + §18.4 의 9종: options_too_many (≥6) / no_decision_matrix / matrix_score_uniform / recommendation_absent (rationale<50자) / premortem_missing_deep / criteria_not_user_aligned / decision_statement_missing / action_plan_missing / kill_switch_missing. **AP-V5-18 갱신** (Plan §18.4) — 옵션 0개 → hold (KILL 아님), 1~2개 허용, 6+ KILL.
  - `evaluate_strategic_mode(report, mode)` 통합 평가 → `StrategicEvaluation` (decision: publish/hold/kill). 0 옵션 시 hold + 사용자 안내 ("?분석 prefix 로 재시도").
  - 회귀 테스트 `tests/regression/test_strategic_mode.py` 신설 — 39건 케이스. **Plan §17.7 인수 기준 #1 정확도 검증** — 30건 라벨된 query 의 routing 정확도 100% (≥90% 임계 통과). prefix 7종 + pattern 8종 + 모델 enum + 9종 KILL_RULES + AP-V5-18 갱신 정책 (0/1/2/6 옵션) + 통합 evaluate.
  - v4.5.7 호출 경로 byte-equal 보존 — 텔레그램 봇의 `_classify_input` 또는 orchestrator 의 mode 결정 시점에 결합 가능 (현재 코드만 박힘).

- **Phase 7 (Desk Editor — Logical + Visual Proof) — framework 완료. Tier 3 의 첫 Phase.** Plan §16 — V5 의 *가장 큰 사용자 체감 변화 시작점*. 신문사 데스크 등급의 시스템 QA + publish/hold/**KILL** 권한.
  - `docs/DESK_VISUAL_RUBRIC.md` 신설 (Plan §25.1 사전 작업 #4 완료) — Visual 8-rubric SSOT (시각-1~8) + append-only 누적 정책 (AP-V5-16) + 자동 KILL 신호 매트릭스. YK catch 결함이 다음 DeskEditor 호출에서 자동 catch 되도록 self-improving (Plan §16.12).
  - `src/visual/capture.py` 신설 — Plan §16.5 의 Playwright capture pipeline. `capture_proofs(html_path, exhibit_count, timeout_ms)` 가 desktop_full (1280×scrollHeight) + mobile_full (375×scrollHeight) + chart_closeup (≤3개) 캡쳐. Playwright 미설치 시 graceful 빈 list (Visual rubric skip). `save_captures_to_disk` 디버그용.
  - `src/agents/desk_editor.py` 신설 — Plan §16.2 의 DeskEditor (Opus 4.7 vision, MAX_TOKENS=8000). SYSTEM_PROMPT 가 Plan §16.3 의 Logical 7-rubric (headline_body / deck_conclusion / section_flow / chart_redundancy / watch_signal_predictivity / source_claim_ratio / smell_test) + DESK_VISUAL_RUBRIC.md §1 의 Visual 8-rubric 자동 포함 (self-improving).
  - `DeskVerdict` (decision: publish/hold/kill + logical_rubric_scores + visual_rubric_scores + issues + kill_reason + auto_kill_rules_triggered) + `DeskIssue` (severity / domain / rubric / suggested_action / target_module / visual_evidence_idx).
  - `run_logical_kill_rules` + `run_visual_kill_rules` + `evaluate_auto_kill` — Plan §16.6 의 결정적 KILL_RULES (Logical 5종 + Visual 3종, *둘 이상* 발화 시 자동 KILL). LLM 호출과 *별개* 로 작동 (AP-V5-14 강제).
  - `HOLD_DISPATCH` 매트릭스 17종 + `dispatch_hold_action` — Plan §16.8 의 lower editor 재호출 분기 (composer/editor/chart_critic/renderer/visual_planner/layout).
  - `Config.enable_desk_editor` opt-in flag (env `V5_DESK_EDITOR=1`) — 디폴트 OFF.
  - 회귀 테스트 `tests/regression/test_desk_editor.py` 신설 — 27건 케이스. DeskVerdict/DeskIssue enum 정합 + Logical 5-KILL + Visual 3-KILL + 자동 KILL 통합 (둘 이상 / 1종 / Logical+Visual 조합) + HOLD_DISPATCH 17종 매핑 + Playwright graceful skip + SYSTEM_PROMPT 의 7+8 rubric 정합 + DESK_VISUAL_RUBRIC.md SSOT 형식.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 7 전 단계 (Phase 7A Deterministic Gate) 통과 후에만 호출 가능.

- **Phase 7A (Deterministic Publish Gate) — framework 완료. Tier 2 의 마지막 Phase.** Plan §15 — DeskEditor (LLM Vision, Phase 7) 호출 *전* 결정적 (rule-based) 검사. 기계적으로 잡을 수 있는 결함은 LLM 비용 0 으로 차단. AP-V5-29 강제.
  - `src/visual/deterministic_gate.py` 신설:
    · **Hard fail 11종** (Plan §15.4): html_render_failed / html_unparseable / required_section_missing / exhibit_ref_broken / chart_without_source (AP-V5-26) / chart_container_empty / report_too_short (mode lower bound) / closing_missing / asset_404 (정적 자산 디스크 verify) / mobile_horizontal_overflow (inline width >400px 검출) / playwright_timeout. 1개라도 발생 시 decision='kill' → LLM 호출 0.
    · **Soft fail 5종** (Plan §15.5): asymmetry_gini (>0.6) / chart_count_exceeded (mode 별 fast 2 / std 4 / deep 5) / heading_pattern_repetitive (어두 동일 + 길이 ±2자) / watch_signal_all_ambiguous / stale_source_ratio (>70% 90일+). DeskEditor system prompt 에 hold 신호로 전달.
    · `MODE_LOWER_BOUND` (Plan §6.3 의 fast 1500 / std 3500 / deep 6000) + `ChartCountLimits` (Plan §13.8) SSOT.
    · `[[ex:N]]` / `[[exr:N]]` / `[[exs:N-M]]` exhibit ref 정규식 파싱 — Phase 4 신설 형식 사전 가드.
    · `_gini_coefficient` / `_heading_repetitive` / `_stale_source_ratio` 헬퍼.
    · `run_deterministic_gate(composed, rendered_html_path, mode, must_have_sections, playwright_timed_out)` 통합 진입점 → `DeterministicGateResult` (decision: publish/soft_fail/kill + hard_failures + soft_failures + metrics).
  - 회귀 테스트 `tests/regression/test_deterministic_gate.py` 신설 — Plan §15.6 인수 기준 #1 (11 hard fail 모두) + #2 (Hard fail → decision='kill' → LLM 호출 0) 결정적 검증. 22건 케이스 — clean publish + 11종 Hard fail 개별 + 4종 Soft fail + 다중 Hard 모두 보고 + Result 형식.
  - v4.5.7 호출 경로 byte-equal 보존 — Phase 7 (DeskEditor) 활성 시점에 결합. AP-V5-29 가 *Phase 7 가 박힐 때* 본격 활성.

- **Phase 6A (Exhibit Priority Policy) — framework 완료.** Plan §14 — Phase 6 의 보수적 drop 정책이 *핵심 논거 차트까지 조용히 사라지게* 만드는 부작용을 차단. AP-V5-28 (Required Exhibit 의 silent drop 금지) 강제.
  - `src/state/models.py` 강화 — `ExhibitPriority` Literal 3종 enum (required / supporting / decorative) + `Exhibit` 모델 신설 (priority + priority_assigned_by + fallback_form 필드) + `RequiredExhibit` 모델 신설 (Plan §14.4 — description / visual_type_hint / why_required / fallback_form) + `AnalysisMethod.required_exhibits` 가 `list[str]` → `list[RequiredExhibit]` 로 강화 (legacy `list[str]` 자동 변환 — model_validator before).
  - `src/visual/chart_gate.py` 강화 — `run_chart_gate(...)` 가 `priority` 와 `required_fallback_form` 인자 추가. priority 별 분기:
    · `required` → AP-V5-28 강제 격하 (fact_grid / table / text 순). 데이터 결손 시에도 *최소한 placeholder text emit* — drop 절대 금지. `ChartGateResult.required_fallback_used=True` 로 DeskEditor 가 hold 사유로 인지.
    · `supporting` (기본) → 기존 3단계 ladder (fact_grid → text → drop).
    · `decorative` → 1단계만 (fact_grid 안 되면 즉시 drop, 조용히).
  - `FallbackLadder.to_table()` 신설 — 행 다수 (>6) 데이터를 표 형식으로 격하. RequiredExhibit.fallback_form='table' 분기.
  - `ChartGateResult` 에 `priority` + `required_fallback_used` 추적 필드 추가.
  - `src/agents/research_director.py` SYSTEM_PROMPT 에 Plan §14 의 required_exhibits 정책 안내 추가 (각 method 마다 1~2개 핵심 차트 명시 + fallback_form 지정). `_DEFAULT_REQUIRED_EXHIBITS` heuristic 매핑 갱신 — 9종 method 모두 매핑 (fault_tree / pre_mortem 은 빈 list 허용). RequiredExhibit dict 형식으로 전환.
  - 회귀 테스트 `tests/regression/test_exhibit_priority.py` 신설 — Plan §14.5 인수 기준 #1~#3 모두 검증. 22건 케이스 — Exhibit default priority + 3-tier enum + RequiredExhibit 모델 + legacy list[str] 자동 변환 + AP-V5-28 강제 (required + Gate fail → drop 금지) + table fallback (row 다수) + text fallback (data 결손 placeholder) + decorative silent drop + supporting 3-step + ChartGateResult priority 추적 + ResearchDirector heuristic.
  - v4.5.7 호출 경로 byte-equal 보존 (legacy list[str] 자동 변환).

- **Phase 6 (Chart Correctness Gate — 4중 게이트) — framework 완료.** Tier 2 의 핵심. Plan §13 의 4중 게이트:
  - **Gate A (Schema Validation)** — `src/visual/schemas.py` 신설. 9개 type 별 Pydantic 가드 (`BubbleChartGuard`/`GanttGuard`/`NetworkGuard`/`BarChartGuard`/`LineChartGuard`/`HeatmapGuard`/`StackedBarGuard`/`DonutGuard`). NaN/inf 거절 (CHART-AP-3), 빈 data 거절 (CHART-AP-7), bubble size>0 (CHART-AP-12), gantt 시간 파싱 + 중복 라벨 (CHART-AP-13), network link 참조 + 노드 ≥ 2 (CHART-AP-1), donut 음수/0 합계, stacked categories ↔ values 정합. `parse_time` 이 ISO/날짜/연도 4종 형식 지원.
  - **Gate B (ChartCritic LLM)** — `src/agents/chart_critic.py` 신설 (Sonnet 4.6, 1024 tokens). Plan §13.3 의 7개 질문 SYSTEM_PROMPT — Q1 차트 빠지면 논거 약해지나 / Q2 takeaway repeat / Q3 type 적합 / Q4 prose 인용 (AP-V5-7) / Q5 중복 / Q6 지도 무관 (AP-14) / Q7 공허. `ChartVerdict` (score 1~5, keep/replace/drop). Plan §13.8 운영 정책 — score ≥ 4 만 keep (3 ambiguous → drop), 호출 실패 시 보수적 drop fallback. `critique_via_heuristics` 가 LLM 0 결정적 휴리스틱 (Q4 + Q7 평가).
  - **Gate C (Visual Sanity)** — `src/visual/sanity_check.py` 신설. lxml 기반 SVG 정적 검증 (미설치 시 정규식 fallback). `visual_sanity_check_svg(svg, viewbox)` 가 4개 항목 검증 — 마크 카운트 (AP-12), 라벨 bbox 충돌 ≤ 20% (AP-5/6/10), viewBox 점유율 ≥ 5% (빈 frame), 라벨 viewBox 밖 잘림 (AP-5).
  - **Gate D (Fallback Ladder)** — `src/visual/chart_gate.py` 신설. Plan §13.5 의 3단계 격하: ① fact_grid 변환 (≤ 6 행 시) → ② 자연어 1문장 요약 → ③ 차트 자체 drop. *깨진 차트 보고서 노출 0건* 정책.
  - **`run_chart_gate(chart, ...)`** 통합 진입점 — Gate A → B → (B-extra: EvidenceDataset) → C → D 순. 어느 게이트든 fail 시 즉시 Fallback Ladder. `ChartGateResult` 가 final_verdict (keep / fallback_fact_grid / fallback_text / fallback_drop) + gate_results + fallback_payload 반환.
  - 회귀 테스트 `tests/regression/test_chart_correctness.py` 신설 — Plan §13.7 인수 기준 #1 (14개 antipattern 시나리오). 38건 케이스 — Gate A 8개 type guard + Gate B 4건 (Q4/Q7/threshold 4) + Gate C 5건 (SVG 결함) + Gate D 4건 (fallback ladder) + 통합 5건 (run_chart_gate end-to-end).
  - v4.5.7 호출 경로 byte-equal 보존 — 본 게이트는 VisualPlanner / 미래 Phase 7 DeskEditor 의 emit 경로에 결합 (현재 코드만 박힘).

- **Phase 2B (Visualization Capability Registry) — framework 완료.** Plan §9 — 차트 type 의 *capability bound* 명시. `docs/VISUAL_CAPABILITY_REGISTRY.yaml` 신설 (16종 type — safe 11 / guarded 3 / experimental 2 정확 분포). `src/visual/capability_registry.py` 신설 — yaml 로더 (캐시) + `is_chart_type_allowed` (3-tier 정책: safe 자유 / guarded Phase 6 Gate C 필수 / experimental forbidden 디폴트, must_have 명시 시만) + `check_required_fields` (필드 정합) + `assert_chart_in_registry` (AP-V5-27 강제). VisualPlanner 의 `_parse_exhibits` + `plan_via_heuristics` 양쪽에 Registry 가드 통합 — emit 전 Registry 미등재/forbidden 즉시 drop. 회귀 테스트 `tests/regression/test_capability_registry.py` 신설 — Plan §9.3 의 11/3/2 분포 검증 + experimental forbidden 강제 + must_have 우회 + required_fields 정합 + renderer enum 4종 검증. 24건 케이스. v4.5.7 호출 경로 byte-equal 보존 (VisualPlanner opt-in flag 그대로).

- **Phase 2 (Visualization Decoupling + Open-Ended Charts) — framework 완료, opt-in 활성 대기.** Tier 2 의 첫 Phase. Plan §7 + §19 에 따라:
  - `src/visual/v5_theme.py` 신설 — Plan §19 의 design token SSOT (Editorial Cream + Burgundy Mono 2종 + 폰트 트리플렛). `get_theme_config(theme)` 가 Vega-Lite config 로 변환, `apply_theme_to_spec(spec, theme)` 가 LLM 이 박은 색을 *덮어씀* (AP-V5-2 강제).
  - `src/visual/vega_adapter.py` 신설 — `render_vega_lite(spec, theme, output)` 단일 어댑터 (Plan §7.4). `vl-convert-python` 미설치 환경에서 themed spec dict 로 graceful fallback (브라우저 vega-embed 호환). `validate_vega_spec` 이 Phase 6 Gate A 의 사전 가드 (CHART-AP-7 빈 data / 비-Vega-Lite schema 거절). `chart_dict_to_vega_spec` 이 v4.5.7 의 ComposedSection.charts 형식을 Vega-Lite 로 마이그레이션 보조.
  - `src/agents/visual_planner.py` 신설 — Plan §7.3 의 VisualPlanner (Opus 4.7, MAX_TOKENS 12000) + SYSTEM_PROMPT (Plan §7.3 그대로). `plan_via_heuristics` 가 LLM 호출 없이 v4.5.7 chart spec 을 EvidenceDataset Guard 통과 기준으로만 필터. `Config.enable_visual_planner` opt-in flag (env `V5_VISUAL_PLANNER=1`) 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존.
  - 회귀 테스트 `tests/regression/test_phase2_vega.py` 신설 — Plan §19 design token 정합성 + apply_theme 강제 + validate_vega_spec + Plan §7.7 antipattern 자동 해결 매핑 (AP-1 / AP-11 / AP-12) 검증. 25건 케이스.
  - Plan §7.8 인수 기준: #4 (모든 차트가 V5 design token 강제) ✅, #5 (자동 해결 8개 항목 검증) ✅. #1 (visual_builder 11개 함수 폐기) 은 Phase 2 본격 활성 시점에 — v4.5.7 charts.js 의존이라 *현재 보존*. #2 (새 chart type demo) / #3 (Editor → Visual 호출 순서) 는 Phase 1 (Editor Pass) 결합 후.

- **Tier 1 baseline 측정 (2026-05-05).** VM 에서 v4.5.7 환경 그대로 20건 Golden Prompt 실측 녹화 (139분, errors 0). 회귀 테스트 7종 통과율 **70.1% (124 pass / 52 fail / 1 skip / 177 total)** 박힘. 52 fail 은 *Plan §22 #2 의 의도대로* V5 후속 Phase 가 개선해야 할 항목들의 baseline (watch_signal direction 미발화 / 분량 부족 / 부적합 차트 / deck-결론 정합 등). AP-V5-32 활성 — V5 후속이 fail count 를 늘리면 회귀. helper 버그 1건 (`extract_chart_numbers` 의 1자리 숫자 거름 누락) 수정.

- **Phase 2A (EvidenceDataset Contract) — framework 완료, Phase 6 ChartCritic 결합 대기.** `src/state/models.py` 의 `EvidenceDataset` 강화 — `DatasetField` (semantic_type 7종 enum) + `TransformStep` (raw → 차트 데이터 변환 추적) BaseModel 화. `src/visual/evidence_dataset.py` 신설 — `EvidenceDatasetGuard` + 검증 함수 (`validate_evidence_dataset`, `ensure_chart_has_source_ids`, `ensure_chart_data_cited_in_prose`, `extract_chart_numbers`). Plan §8.5 의 3개 금지 행위 (AP-V5-24 prose 발 차트 데이터 / AP-V5-25 출처 없는 synthetic / AP-V5-26 source_id 없는 chart) 결정적 강제. Plan §8.6 의 ChartCritic 질문 8 (prose 인용 가드) 사전 구현 — 차트 data 의 *고유 숫자 ≥20% 가 prose 에 인용* 되어야 keep, 미만 시 drop 권고. 회귀 테스트 `tests/regression/test_evidence_dataset.py` 신설 — Plan §8.7 인수 기준 #1~#4 모두 결정적 검증 (24건 케이스). v4.5.7 호출 경로 byte-equal 보존 — Phase 6 ChartCritic 진입 시 본격 활성.

---

### v4.5.7 — ContextAnalyst max_tokens deep 모드 4K → 10K + Somaliland viewport gating

#### Changed
- `src/agents/base.py` — `BaseAgent._max_tokens_override` 지원. subclass 가 mode 별로 override 가능.
- `src/agents/context_analyst.py` — `request.mode` 별 max_tokens 분기. fast / standard 4096 유지, deep 4096 → 10000. deep 사건의 사실/타임라인/출처 다수 시 4K 부족 회귀 차단.

#### Fixed
- `src/templates/static/maps.js` — Somaliland (de facto) 해칭 폴리곤과 'de facto' legend 항목이 모든 보고서에 무조건 렌더되던 회귀. `path.bounds(SOMALILAND_GEOJSON)` 로 projection 적용 후 viewport 와 교집합 검사. 호르무즈·동북아 같은 무관 보고서에서 polygon + legend 모두 skip.
- 사용자 회귀 (호르무즈 / 위안화 통행세 보고서에 'Somaliland (de facto)' legend 노출) 차단.

#### Added
- **CHART-AP-14** — "보고서와 무관한 지리 annotation 무조건 렌더" anti-pattern 신설 (CHART_RENDERING_ANTIPATTERNS.md). `path.bounds()` 로 viewport 교집합 검사 후 render gating 의무화.

> 주의: 24ba563 commit 메시지는 이 항목을 'CHART-AP-13' 으로 표기했지만, v4.5.4 에서 이미 CHART-AP-13 (Gantt 시간축) 이 부여되어 번호 충돌. REFACTOR_V5_PLAN.md §3.7 의 정본에 맞춰 CHART-AP-14 로 정정한다.

---

### v4.5.6 — 'Analysis Team' 접두 + Rev 0 항상 표기

#### Changed
- `src/templates/archetypes/freeform_essay.html` hero eyebrow — `v4.5.5` → `Analysis Team v4.5.5 · Rev 0`. `Rev 0` 도 항상 표기 (이전엔 0 숨김). 사용자 요구 "애너리시스 팀 v4.5.5" 식 명시적 레이블.

---

### v4.5.5 — system_version + revision 추적성 (보고서 상단 노출)

#### Added
- `FullAnalysisResult.system_version: str` — 생성 시점 `src/orchestrator.py:VERSION` 기록. 재렌더 시엔 *재렌더 시점* 버전으로 갱신 (CSS/JS 가 그 버전 따름).
- `FullAnalysisResult.revision: int = 0` — 최초 생성 0, `patch_report.py` 수정 시 +1.
- `freeform_essay.html` hero eyebrow — `EVENT ANALYSIS · COMPOSED · v4.5.5 · Rev 2` 형식. revision 0 면 'Rev 0' 안 표시 (v4.5.6 에서 정책 변경 — 항상 표시).
- `.freeform-version` 토큰 — IBM Plex Mono, muted 색.

#### Changed
- `src/agents/report_synthesizer.py:synthesize()` — 매 렌더 (신규/재렌더 모두) 시 `result.system_version` 갱신. 재렌더만 한 경우엔 system_version 만 바뀌고 revision 그대로 (데이터 변경 X).
- `scripts/patch_report.py` — mutated 또는 `--edit` 인 경우 `result.revision += 1` 후 저장. `--rerender-only` 는 데이터 변경 없으니 revision 안 올림.

#### 배경
사용자 피드백 (20260503_164450) — 보고서가 477초 걸린 후 'composer 호출 실패. 사실 자료만 표시' 폴백으로 종료. 어떤 코드 버전에서 만들어졌는지, 이후 패치됐는지가 보고서 자체에 안 보여 진단·재발 추적 어려움.

---

### v4.5.4 — drawGantt 시간축 + note placement fix + composer max_tokens mode 별 분기

#### Added
- `narrative_composer.MAX_TOKENS_BY_MODE` — fast 12K / standard 20K / deep 32K. `_call_api(user_message, mode)` 에 mode 인자 추가.
- **CHART-AP-13** — "Gantt 차트 시간축 누락 + 행 라벨/note 충돌" anti-pattern 신설.
- **WRITE-AP-8** — "max_tokens 한도로 보고서 본문 중간 절단" anti-pattern 신설.

#### Changed
- `charts.js:drawGantt` 전면 보강 — `d3.axisBottom` 풍 시간축 자동 추가 (tick + label + grid). `parseTime()` 입력 정규화 (numeric / 'YYYY' / 'YYYY-MM' 모두 지원). `start === end` 면 0.4 단위 폭 부여. 막대 최소 폭 2 → 6px. note placement 분기 — 막대 폭 ≥ 60px 면 *내부* 흰글자, 아니면 *외부 우측*. 행 라벨 truncate 22 → 25자.
- `narrative_composer` 단일 `MAX_TOKENS = 8192` → `MAX_TOKENS_BY_MODE` (default fallback 32000).

#### Fixed
- WRITE-AP-8 회귀 — composer 의 단일 MAX_TOKENS=8192 가 deep 모드 (5~7 섹션 + 시나리오 + 모순 + 차트/지도 emit) 에서 부족해 응답 *중간 절단*. mode 별 분기로 차단.
- 자율주행 일정 비교 gantt 차트의 의미 불명 회귀 (사용자 피드백 20260503_142254).

---

### v4.5.3 — chart-card 테마 귀속 + bubble 스케일 자동 감지 (CHART-AP-11/12)

#### Added
- 각 테마 블록에 `--card-deep` CSS 변수 정의 — editorial_cream `#E5DBC4`, burgundy_mono `#1A0810`, light_mono `#dccea8`.
- **CHART-AP-11** — "차트 카드 배경이 하드코딩 fallback (테마 미반영)" anti-pattern 신설.
- **CHART-AP-12** — "버블 차트 스케일 고정 — 데이터가 frame 밖으로" anti-pattern 신설.

#### Changed
- `src/templates/archetypes/freeform_essay.html` `.freeform-chart-wrap .chart-card` 배경 — `rgba(0,0,0,0.18)` → `var(--card, var(--bg-2))`. 테마 따라감.
- `charts.js:drawBubble` — `d3.scaleLinear().domain([0,1])` 고정 → `d3.extent` 자동 감지. 0 포함 + 5% padding + size 정규화 (sMax 기반). composer 가 0~1 / 0~5 / 0~100 어느 범위로 emit 해도 정상 표시.

#### Fixed
- editorial_cream 디폴트 (v4.5.0) 채택 후 즉시 노출된 회귀 — 모든 차트 카드가 dark wine 박스로 표시되어 글자 가독성 0. `--card-deep` 변수 미정의로 CSS variable resolution fallback `#321F1F` 가 항상 적용된 결함.
- 시나리오 확률×영향 버블 차트의 빈 frame 회귀 — composer 가 0~5 또는 0~100 범위로 emit 시 모든 bubble 이 frame 밖으로 나가 안 보이던 문제.

---

### v4.5.2 — fact-grid 항상 한 줄 (data-cols 강제) + VERSION bump 동기화

#### Changed
- `src/templates/archetypes/freeform_essay.html` fact-grid CSS — 미디어 쿼리 폐기. `data-cols` 값 그대로 cols 적용. 2/3/4/5/6 모두 한 줄에 강제. wrap 가능성 자체 제거.
- 좁은 폭 (≤ 640px) 가독성 — tile padding 14px/16px → 10px/8px, label font 10.5px → 9px, value font 22px → 15px (`word-break: keep-all`), sublabel font 11px → 10px. 5/6 cols 추가 축소.
- `src/orchestrator.py:VERSION` — v4.5.0 → v4.5.2 (v4.5.1 / v4.5.2 commit 시 VERSION bump 누락분 동기화).

#### 사용자 피드백
v4.5.1 의 mobile 1-col stack 이 사용자 의도와 반대 ("한 줄에 보이는 게 더 좋아"). 정책 반전.

---

### v4.5.1 — fact-grid 모바일 1 col stack — 홀수 타일 어색 wrap 차단

#### Changed
- `src/templates/archetypes/freeform_essay.html` fact-grid — mobile (< 720px) 모든 count 1 col stack. desktop (≥ 720px) count 별 분기 유지 (2/3/4/5/6 한 줄). `data-cols="2"` 추가.

#### 비고
v4.5.2 에서 정책 반전됨 (사용자 피드백 따라 모바일도 한 줄 강제). v4.5.1 은 short-lived intermediate state.

---

### v4.5.0 — Editorial Interaction Patterns + Newsreader/IBM Plex Fonts (LG 벤치마크 차용)

LG AI Seminar 보고서를 인터랙션 패턴 벤치마크로 채택. 기술 스택 (d3 차트/지도, mono 테마 시스템, Tier 4 아키텍처) 은 그대로 유지하고 *말하는 방식 + 페이지 위 텍스트 구조* 만 차용. 음슴체 → 평어체, 신규 editorial 컴포넌트 4종, 폰트 시스템 교체.

#### Added
- 신규 테마 `editorial_cream` — cream (`#F2EBDB`) + terracotta accent (`#B05A38`). 디폴트로 채택. `burgundy_mono` 는 위기·분쟁 (`geopolitical`/`accident`) 한정.
- `ComposedSection.lede` — 긴 도입 1~3문장 (italic, prose 위 큰 글씨).
- `ComposedSection.analogy` — `{title, body}` 비유 박스. 어려운 개념을 일상 비유로.
- `ComposedSection.fact_grid` — `[{label, value, sublabel?}]` 핵심 수치 격자.
- `ComposedSection.dropcap` — bool, prose 첫 글자 dropcap 렌더 (보고서당 1~2 섹션 권장).
- 자동 TOC — 섹션 ≥ 2개일 때 hero 직후 자동 생성. 섹션 anchor (`#sec-N`) 자동 부여.
- 폰트: Newsreader (display serif, 영문/숫자) + IBM Plex Sans KR (본문) + IBM Plex Mono. 한국어는 Noto Serif KR 폴백.
- WRITE-AP-7 — 서수 / 기수 혼용 ("N번" 의 두 얼굴) anti-pattern 신설.

#### Changed
- composer SYSTEM_PROMPT v4.5.0 — 음슴체 (~함) 폐기 → 평어체 (~다). 질문 던지기 가이드. WRITE-AP-7 prevention 명시.
- `burgundy_mono` 톤 어둡게 보정 — bg `#3D1820` → `#2A0F18`, water `#2A0E16` → `#1A0810`. 사용자 피드백 "맑은 와인" → "dried-blood" 톤.
- `lens_policy._THEME_BY_CATEGORY` — 디폴트 `editorial_cream`, `geopolitical`/`accident` 만 `burgundy_mono`.
- `freeform_essay.html` — 모든 raw text 출력에 `| strip_md` 적용 (v4.4.7 정책 일관).

#### Fixed
- WRITE-AP-1 회귀 (v4.4.7) — markdown asterisk 가 `contradictions` / `watch_signals` / `deck` / `headline` 등 dict 필드에서 raw 노출. lightweight `_strip_markdown` 신규 + jinja2 `strip_md` filter + 모든 raw text 필드에 일괄 적용.

---

### v4.4.7 — Patch tool 텍스트 필드 옵션 + WRITE-AP-7 + WRITE-AP-1 확장

`patch_report.py` 에 `--deck` / `--headline` / `--closing` / `--confidence-summary` 추가. composed_report 텍스트 필드를 LLM 호출 없이 즉시 수정.

### v4.4.6 — 지도 상단 배치 + d3.zoom + 소말릴란드 해칭 폴리곤

WRITE-AP-3 (지도 후행 배치) 회귀 fix — 지도 섹션을 hero 직후로 이동. d3.zoom() pan/zoom + 컨트롤 버튼. 소말릴란드 (de facto) 45° 해칭 폴리곤 (Natural Earth 1:50m 단순화).

### v4.4.5 — patch_report.py 지도/마커 옵션 + 다중 차트 제거

`--show` / `--map-zoom` / `--map-center` / `--remove-marker` 추가. `--remove-chart` 다중 가능 (인덱스 shift 자동 처리).

---

### v4.2.0 — Composer-emitted Charts + Maps

Composer 가 차트/지도 데이터를 단일 LLM 호출에서 *직접 emit*. 옛 결정적 빌더 (`visual_builder.build_chart_payload`) + `auto-init by element id` 패턴 + `maplibre-gl` 의존 모두 폐기. mono guide §2 (d3 + d3-geo + TopoJSON) + §4 (45° 패턴 시스템) 정합.

#### Added
- `ComposedSection.charts: list[dict]` — 차트 데이터 inline. `{type, title, data, note?}`. 8종 type: `bar / donut / line / gantt / network / stacked / bubble / heatmap`.
- `ComposedReport.embedded_map: dict | None` — 보고서 레벨 단일 지도. `{center, zoom, markers, arcs, legend?}`.
- `charts.js` 전면 재작성 — 섹션마다 `<script class="chart-payload-inline">` 스캔, mono guide §4 패턴 (hatch-tight / hatch-wide / dots / accent-hatch) 자동 적용.
- `maps.js` 전면 재작성 — `d3.geoMercator` + `topojson.feature(world-atlas/110m)` 베이스맵, 외부 타일 서비스 의존 0.
- `freeform_essay.html` 의 closing 앞에 `#freeform-map` 영역 + `#map-payload` 스크립트 (composer 가 emit 했을 때만).

#### Changed
- composer SYSTEM_PROMPT — 차트 type 8종 별 data 스키마 명시. "수치 비교가 본문 이해에 결정적일 때만" 보수적 게이팅.
- `freeform_essay.html` — 옛 chart-id 기반 9개 if/elif 분기 (chart-scenarios / chart-figures / chart-severity / ...) 통째 폐기. 섹션마다 `sec.charts` 순회로 변경.
- `maps.css` — 옛 maplibre 용 `.block-map.theme-{light_mono,burgundy_mono}` 트리 통째 폐기. mono 토큰만으로 동적 적용하는 `.map-card / .map-stage` 만 남김.

#### Deprecated (호출 안 됨)
- `src/visual_builder.py:build_chart_payload()` — composer 가 직접 emit 으로 대체.
- `src/visual_builder.py:build_map_payload()` — 동일.
- `src/templates/blocks/map.html` (v3.4.0 추가분) — composer.embedded_map 으로 대체.

---

### v4.1.0 — ContextAnalyst → Opus 4.7

Tier 4 의 2-call 파이프라인에서 context 가 composer (Opus 4.7) 가 보는 *유일한* 사실 입력. 사실 추출 품질이 보고서 전체 품질의 상한선이라 모델을 한 세대 위로 통일.

#### Changed
- `src/agents/context_analyst.py` — `use_light_model=True → False` + `self.model_name = "claude-opus-4-7"` 직접 지정. config.model_name (Opus 4.6) 보다 한 세대 위.
- `src/orchestrator.py` — fast 모드의 context 다운그레이드 로직 + 모델 복원 코드 제거.
- `src/telegram_bot.py` — `/status` 의 ① 상황 분석관 모델 표시 갱신.

#### Effects
- 사실 추출 품질 상한 ↑ — 출처 1차/2차 구분 / 단위 보존 / 인과 순서 정확도.
- 비용: ~1.6~1.8× (vs v4.0.0). v3.5.0 deep (13-call) 대비 30~40% 수준.
- 지연: context 단계 ~10초 → ~25초 (총 ~30초 추가 추정).

---

### v4.0.0 — Tier 4 Unified Pipeline (MAJOR)

7개 분석 에이전트 + 11종 lens + 11종 archetype + 5단계 게이트 다중 파이프라인을 폐기하고 ContextAnalyst + UnifiedComposer 2회 LLM 호출로 압축. 보고서 자유도 최대화 + LLM 호출 ~85% 감소 + 지연 시간 ~60% 감소.

#### Pipeline change
- BEFORE (v3.5.0): context → strategy → gate1 → [players → dynamics → chain (deep만)] → scenarios → lens_pool 1~4종 → judgment → gate2 → visuals → composer → render. **LLM 호출 fast 5 / standard 8 / deep 13**.
- AFTER (v4.0.0): context → unified_composer → render. **LLM 호출 모든 모드 2회**.

#### Added
- `NarrativeComposer.compose_unified(context, mode)` — Opus 4.7 단일 호출에서 행위자 / 구조 / 시나리오 / 모순 분석 + 본문 작성.
- `ComposedReport.watch_signals: list[dict]` — Watchlist Registry 통합용. 기존 `ScenarioArchitect` 출력 대체.
- `ComposedReport.contradictions: list[dict]` — Anti-pattern #5 (모순 봉합 금지) 보존.
- `ComposedReport.confidence_summary: str` + `confidence_score: float` — composer 자체 신뢰도 평가.
- `freeform_essay.html` 에 contradictions / watch_signals / confidence 노출 섹션 추가.

#### Removed (호출 안 됨, 파일 보존)
- `_generate_analysis_strategy` LLM 호출 (event_type / intent / lenses / archetype 결정).
- Quality Gate 1 (계획 sanity) + Gate 2 (커버리지) LLM 검증.
- `PlayerAnalyst / DynamicsAnalyst / ChainReactionAnalyst / ScenarioArchitect` 호출.
- `SynthesisJudge.judge()` (모순/판단 LLM 검사).
- `_run_lenses()` (lens pool 1~4 LLM 호출).
- `VisualAnalyst.analyze()` (LLM 시각화 + 결정적 빌더 양쪽 모두).
- `select_archetype()` matrix 라우팅 — 항상 `freeform_essay`.

#### Changed
- `token_budget.py` — 모든 모드 `max_llm_calls=2`, `max_lenses=0`. mode 는 composer prompt 깊이 지시만 결정.
- orchestrator `run_analysis()` — ~370줄 → ~120줄.

---

### v3.5.0 — Composer to All Modes + Mono Theme Standard

`narrative_composer` (Opus 4.7) 를 fast/standard 에도 활성화 + 멀티컬러 6테마 폐기 + DATA DASHBOARD 9개 차트 무지성 박힘 차단.

#### Added
- `token_budget.for_mode("fast"|"standard")` 에 `use_llm_narrative_composer=True`. cap 상향 (fast 4→5, standard 7→8).
- `report.css` 의 `burgundy_mono` + `light_mono` 정의 (mono guide §3 팔레트).
- `freeform_essay.html` 에 contradictions / watch_signals / confidence 노출 섹션 (v4.0.0 으로 이어짐).

#### Removed
- `report.css` 의 6 멀티컬러 테마 (burgundy / geopolitical / financial / tech / nature / liquidglass) 통째 삭제.
- `report_block.html` 의 "DATA DASHBOARD / 한눈에 보기" 섹션 (9개 차트 슬롯) — composer-referenced 만 freeform_essay.html 이 렌더하는 정책으로 통일.

#### Changed
- `lens_policy.select_theme()` — multi-color 6테마 매핑 → mono 2종만. policy → light_mono, 그 외 → burgundy_mono.
- 모든 템플릿 (report_block / freeform_essay / financial_transmission / tech_decomposition) 디폴트 `data-theme` → `burgundy_mono`.
- `AnalysisStrategy.theme` 디폴트 + `_empty_strategy_fallback` + orchestrator fallback 모두 `burgundy_mono`.

---

### v3.4.7 — AMC 전체 archetype 적용 + required_inputs 검증 (PR4)

PR3 후속. PR3 에서 5개 archetype 만 contract() 선언 → PR4 에서 **나머지 7개까지 전체 12개 archetype 에 적용** + required_inputs 런타임 검증 추가.

#### Added — 7개 archetype 에 contract() + narrative_stage 태깅
- `geopolitical_strategic`: mandatory `[fact, mechanism, divergence, trigger]`, forbidden `[decision_matrix]`
- `industry_value_chain`: mandatory `[fact, mechanism, divergence, trigger]`
- `policy_implementation`: mandatory `[fact, mechanism, divergence, decision]`
- `tech_decomposition`: mandatory `[fact, mechanism, divergence, decision]`, forbidden `[scenario_table]`
- `timeline_first`: mandatory `[fact, divergence]`, forbidden `[decision_matrix, scenario_table]` (what_happened 전용 — 사실 정리가 본분)
- `freeform_essay`: 느슨한 contract (composer 가 stage 자율 결정 — mandatory_stages 비어있음)
- `six_act_theater`: mandatory `[fact, mechanism, divergence, trigger]` (legacy 라 enforcement 트리거 안 됨, 일관성/디버깅용)

→ **이제 12개 archetype 전체가 narrative_stage 태깅 + contract() 선언**. 모든 archetype 에서 stage 배지가 시각화되고 mandatory stage 미달 시 경고 가시화.

#### Added — required_inputs 런타임 검증
- `ReportSynthesizer._check_required_inputs()` 신설: contract.required_inputs 가 result 에 실제로 채워졌는지 검증.
  - `FullAnalysisResult.<field>` 가 None → missing
  - Pydantic 모델 인스턴스이지만 모든 list/dict/str 필드 비어있음 → missing
- `_build_blocks` 가 시작 시 검증, 누락 시 WARNING 로그.
- 첫 블록 `__amc__` 메타에 `required_inputs` + `missing_inputs` 기록.
- `report_block.html` 의 AMC 경고 배너가 누락된 입력도 표시 ("누락된 필수 입력: context, players").

#### Tests
- `test_amc_narrative_dsl.py` 확장:
  - **`TestArchetypeStageCoverage`**: 5개 individual test → `parametrize` 로 11개 strict archetype 전체 검증 (freeform_essay 는 별도)
  - **`TestArchetypeNoSelfViolation`**: 동일하게 11개 전체 자가 모순 검증
  - **`TestAllArchetypesHaveContract`** (신설): 12개 archetype 모두 callable contract() 노출 + AnalysisMethodContract 인스턴스 반환
  - **`TestRequiredInputsCheck`** (신설): _check_required_inputs 4개 테스트 (None / 빈 모델 / 데이터 있음 / 부분 누락)
- 결과: `pytest src/tests/` **202 passed, 4 skipped** (PR3 175 + PR4 27 신설). skip 4개는 mandatory_stages 또는 forbidden_blocks 가 비어있는 archetype 의 parametrize 항목.

#### Code quality
- Pydantic V2.11 deprecation 경고 해소: `obj.model_fields` → `type(obj).model_fields` (V3.0 에서 제거 예정).

---

### v3.4.6 — AMC + Narrative DSL (PR3) — 단조로움의 구조적 처방

PR1'/PR2 후속. 사용자 지적 *"기법 다양성을 주문했는데 형식이 늘 비슷함"* (REFACTOR_V3_PLAN §6) 의 **구조적** 처방.

문제의 본질은 LLM 능력 부족이 아니라 *아키텍처가 다양성을 보존·증폭하지 못하고 기본형으로 수렴*시키는 것. archetype 들은 표면상 다른 `block_types` 를 선언하지만 빌더가 archetype-blind 라 결국 같은 모양으로 평탄화됨. PR3 는 두 메커니즘으로 해결:

#### Added — Narrative DSL (5단계)
- **`NarrativeStage` Literal** (`src/models.py`): `fact / mechanism / divergence / decision / trigger` — 보고서 흐름의 5단 분석 단계.
- **`ReportSectionPlan.narrative_stage`** (optional): archetype 작성자가 각 섹션이 어느 단계인지 선언. backward-compat (None 허용).
- **시각 차별화** (`report.css`):
  - 섹션 헤더에 stage 배지 (색상이 단계별 — fact=blue / mechanism=gold / divergence=orange / decision=green / trigger=red)
  - 섹션 자체에 좌측 컬러 액센트 (스크롤하면서 단계 흐름이 한눈에 보임)
- 결과: 같은 archetype 의 섹션도 단계별로 시각적으로 분리되어 *단조로움 직접 해소*.

#### Added — AMC (Analysis Method Contract)
- **`AnalysisMethodContract` Pydantic model**: `method_id`, `required_inputs`, `mandatory_stages`, `forbidden_blocks`, `rationale` 필드.
- **archetype 별 `contract()` 메서드** (5개 구현):
  - `scenario_first`: mandatory `[fact, divergence, trigger]`, forbidden `[decision_matrix]`
  - `decision_brief`: mandatory `[fact, divergence, decision, trigger]`
  - `mechanism_decomp`: mandatory `[fact, mechanism, divergence]`, forbidden `[scenario_table, decision_matrix]`
  - `accident_forensic`: mandatory `[fact, mechanism, decision]`, forbidden `[scenario_table]`
  - `financial_transmission`: mandatory `[fact, mechanism, divergence, trigger]`, forbidden `[decision_matrix]`
- **default_contract()** helper: contract() 미선언 archetype 은 빈 contract → backward-compat.
- **synthesizer enforcement** (`_build_blocks`):
  - `forbidden_blocks` 등재된 block_type 은 빌더 실행 전 reject + INFO 로그
  - 빌드 후 mandatory stage 미달 시 WARNING 로그
  - 첫 블록 payload 에 `__amc__` 메타 부착 (covered/missing stages 기록)
- **템플릿 가시화** (`report_block.html`): AMC 미달 시 보고서 상단에 ⚠ 경고 배너 — 어떤 분석 단계가 빠졌는지 사용자에게 직접 노출.

#### Why this fixes monotony
이전: 5개 archetype 모두 `narrative` + `decomposition` + `matrix` + ...를 비슷한 순서로 호출 → *결과물이 비슷해 보임*. <br>
이후: 같은 `narrative` block 도 한 섹션은 `stage="fact"` (파란 배지), 다른 섹션은 `stage="divergence"` (주황 배지) → *시각·의미적으로 분리*. archetype 간 차별화는 mandatory_stages 차이 (decision_brief 만 `decision` 강제, accident_forensic 만 `decision`+`mechanism` 강제 등) 로 *구조적으로* 보장.

#### Tests
- `test_amc_narrative_dsl.py` 신설 — 19개 테스트:
  - `TestNarrativeStageField` (4): NarrativeStage Literal 동작 + ReportSectionPlan 확장
  - `TestAnalysisMethodContract` (3): AMC 모델 동작 + default_contract helper
  - `TestArchetypeContracts` (5): 5개 archetype 모두 contract() 선언 검증
  - `TestArchetypeStageCoverage` (5): 각 archetype 의 section_plan 이 자기 mandatory_stages 를 모두 커버 (자가 정합성)
  - `TestArchetypeNoSelfViolation` (2): forbidden_blocks 가 자기 section_plan 안에 없음 (자가 모순 방지)
- 결과: `pytest src/tests/` **175 passed** (PR2 156 + PR3 19).

#### Roadmap (남은 작업)
- 6개 archetype (geopolitical_strategic / industry_value_chain / policy_implementation / tech_decomposition / timeline_first / freeform_essay) 에 contract() + stage 태깅 → backward-compat 라 점진 가능.
- lens 단위 contract (현재는 archetype 단위만). lens 가 fact/mechanism 출력을 강제하는 형태로 확장 가능.
- AMC `required_inputs` 가 *충족 안 되면* archetype 자체 라우팅 거부 (현재는 경고만).

---

### v3.4.5 — Scenario data enrichment (PR2)

PR1' 후속. 사용자 진단 #2 (시나리오 시인성)의 *완성판* — 확률 bar 외에 **신뢰도** 와 **선행 신호** 를 시각화.

#### Added
- **`ScenarioAnalysis.scenarios[*].confidence`** (0.0~1.0 또는 0~100) — 이 시나리오 판단의 신뢰도. `scenario_architect` SYSTEM_PROMPT 가 LLM 에 요청. `visual_builder.build_scenario_table` 이 dict (`{raw, label}`) 로 정규화 (raw는 0~100 정수, label은 "높음/중간/낮음/매우 낮음").
- **`ScenarioAnalysis.scenarios[*].driver_signals`** (list[str] 또는 list[dict]) — 이 시나리오로의 분기를 *현재 관측 가능한* 형태로 식별하는 선행 지표 (최대 4개). visual_builder 가 dict/string 양쪽 입력 받아 정규화.
- **scenario_table.html 렌더 보강**:
  - 카드 헤더에 **신뢰도 배지** (`scenario-card-confidence`) — 색상이 신뢰도에 따라 변화 (높음=녹색, 중간=골드, 낮음=주황, 매우낮음=빨강).
  - **"선행 신호" 섹션** (`scenario-card-signals`) — 칩 형태 list, 각 칩 앞에 ► 마커.
- **scenario_architect prompt** 가 impact_by_player 의 impact 텍스트에 정량 강도 단어("극심한 타격", "높은 충격", "중간 영향", "낮은 파급") 포함을 권장. PR1'의 `_impact_magnitude` 가 추출하여 stacked chart 의 segment 가중치로 사용.

#### Backward compatibility
- 모든 신규 필드는 *optional*. `ScenarioAnalysis.scenarios` 는 여전히 `list[dict]` (loose). LLM 출력에 confidence/driver_signals 없으면 `confidence=None`, `driver_signals=[]` → 템플릿이 조건부 렌더 (`{% if sc.confidence %}` / `{% if sc.driver_signals %}`).
- 기존 시나리오 데이터(probability/description/impact_by_player만 있음)는 그대로 동작.

#### Tests
- `TestScenarioTable` 클래스 신설 — 6개 테스트:
  - `test_passes_confidence_as_float` (0~1 입력)
  - `test_passes_confidence_as_percent` (0~100 입력)
  - `test_omits_confidence_when_missing`
  - `test_extracts_driver_signals_from_string_list`
  - `test_extracts_driver_signals_from_dict_list`
  - `test_summarizes_impact_by_player`
- 결과: `pytest src/tests/` **156 passed** (PR1' 150 + PR2 6).

#### Roadmap
- **PR3** (별도 세션): AMC (Analysis Method Contract) + Narrative DSL — 단조로움의 *구조적* 처방.

---

### v3.4.4 — Quality fixes (PR1')

샘플 보고서(`analysis_20260501_165647`)에서 관찰된 6가지 품질 문제 중 v3.4.3 이후에도 *여전히 미해결인 4개*만 처리. 시나리오 모델 강화(PR2)와 AMC + Narrative DSL(PR3)은 후속.

#### Fixed
- **차트 테마 미동기 (#1)** — `src/templates/static/charts.js` 의 `TOKENS` 상수가 burgundy hex(`#321F1F`, `#C9A84C` 등) 하드코딩 → `getComputedStyle` 로 `:root` 의 `--card / --gold / --green / --orange / --red / --blue / --text-*` CSS 변수 읽기. 페이지 `data-theme` (geopolitical/financial/tech/nature/liquidglass) 와 차트 팔레트 자동 동기화. fallback 으로 burgundy 유지.
- **무지성 차트 (#3)** — `src/visual_builder.py`:
  - `build_key_figures_chart_data`: 숫자 추출 실패 시 `1.0` 폴백 제거 (균등 도넛 안티패턴 차단). 항목 < 3 이거나 모든 값 동일이면 빈 list → 도넛 미생성.
  - `build_stacked_chart_data`: 모든 segment `value=1` 하드코딩 제거. `_impact_magnitude()` 가 (a) 명시적 `impact_score/magnitude/weight` 필드, (b) impact 텍스트의 키워드("극심"/"높음"/"중간"/"낮음" 등) 우선순위로 정량값 추출. 추출 실패 segment skip, ≥4 segment + variance>0 일 때만 차트 생성.
- **빈 placeholder 블록 (#5 부분)** — `_payload_claim_card / _payload_evidence_table / _payload_qna` 가 빈 dict 대신 `None` 반환. 기존엔 빈 카드/표가 매 보고서에 렌더되어 단조로움의 직접 원인.
- **모바일 cram (#6 부분)** — `src/templates/report.css` 에 `@media (max-width:540px)` 추가:
  - `block-timeline-item` 세로 스택 (이전: `display:flex` + `min-width:110px` 날짜 → 좁은 폭에서 셀 안 텍스트가 한두 글자씩 흘러내림).
  - `evidence_table / risk_matrix` 테이블 → 카드 스택 변환 (`<thead>` 숨김, `<tr>`→카드, `<td>`→라벨된 행). `<td>` 에 `data-label` 속성 추가하여 카드 모드에서 라벨 표시.

#### Already-fixed-on-main (verified, no work needed)
- **#2 시나리오 시인성** — `scenario_table.html` 이 이미 `scenario-grid` + 확률 bar (v3.2.0). 단 `confidence`/`driver_signals` 필드는 **PR2 범위**.
- **#4 차트 빈 공간** — `charts.js` 가 이미 dynamic SVG sizing + `aspect-ratio` + 모바일 breakpoint (v3.2.0).
- **#5 단조로움 (부분)** — Narrative Composer (v3.3.0) 가 deep mode 에서 freeform 에디토리얼. AMC 등 구조적 처방은 **PR3 범위**.

#### Tests
- `test_chart_builders.py` 중 4개 테스트가 *이전의 잘못된 동작*(value=1 fallback, `1.0` default)을 검증하고 있어 **새 (올바른) 동작**에 맞게 갱신:
  - `test_extracts_numeric_value`: 3+ figures 로 변경 (Insight Gate 충족)
  - `test_falls_back_to_one_when_no_number` → `test_skips_when_no_number` (정정된 동작 검증)
  - `test_skips_when_uniform_values` 신설
  - `test_builds_segments_per_scenario` → `test_builds_segments_with_varied_magnitudes` (variance>0 검증)
  - `test_returns_none_when_uniform_magnitudes` 신설
  - `test_omits_empty_chart_types`: 1개 figure → key_figures omit (Insight Gate 동작 명시)
  - `test_full_payload_with_all_data`: 3+ figures + 변동성 있는 stacked
- 결과: `pytest src/tests/` **150 passed** (이전 144 + 신설 6).

#### Roadmap
- **PR2** (다음): `ScenarioAnalysis` 모델에 `confidence` + `driver_signals` 필드 추가. `visual_builder.build_scenario_table` 추출 + `scenario_table.html` 배지 렌더.
- **PR3** (별도 세션): AMC (Analysis Method Contract) — 기법별 `required_inputs / output_schema / mandatory_sections / forbidden_fallbacks` 선언. + Narrative DSL (fact→mechanism→divergence→decision→trigger). 사용자 지적 "기법 다양성을 주문했는데 형식이 늘 같음"의 *구조적* 처방.

---

## [3.4.3] — 2026-05-01

> **핫픽스 — v3.4.0 회귀 수정.** `_payload_map()` 이 `result.report_theme` 을 읽어 light/burgundy 분기를 시도하지만, `FullAnalysisResult` 모델에 해당 필드가 없어 `synthesize()` 초입의 `result.report_theme = theme` 할당이 Pydantic ValidationError 를 던졌다. 결과: 모든 보고서 생성이 `❌ 분석 실패: "FullAnalysisResult" object has no field "report_theme"` 로 실패. **한 줄 패치 — 모델에 필드 추가.**

### Changed
- **`src/models.py:FullAnalysisResult`** — `report_theme: str = ""` 필드 추가. SSOT (`NarrativePlan.report_theme`) 과 별개로 block builder 가 읽는 채널.
- **`src/orchestrator.py:VERSION`** `v3.4.2 → v3.4.3`

### Migration
- **VM 재기동 필요**.
- 분석 흐름은 그대로. Block builder 의 theme 분기가 이제 정상 작동.

---

## [3.4.2] — 2026-05-01

> **`/stop` `/stopall` — 진행 중 분석 텔레그램에서 직접 중단.** `_run_analysis` 시작 시점에 `asyncio.current_task()` 를 보관해 두고, `/stop` 핸들러가 `cancel()` 호출 → `CancelledError` 가 위로 전파되며 LLM 호출 / 서브프로세스 / await 체인 모두 정상 종료. `/stop` 은 현재 1건만, `/stopall` 은 큐까지 전부 비움. 인가 체크는 `/analyze` 와 동일 (`_is_authorized`).

### Added
- **`src/telegram_bot.py:_stop_command()`** — 진행 중 분석만 cancel. 큐는 보존. 메시지: `🛑 분석 중단 요청 보냄: <topic>\n정리 후 곧 종료됩니다.\n📋 대기열 N건 은 그대로 유지.`
- **`src/telegram_bot.py:_stopall_command()`** — 진행 중 분석 cancel + `self._queue.clear()`. 메시지: `🛑 전체 중단: 진행 중 분석 (<topic>) 취소 + 대기열 N건 비움.`
- **`src/telegram_bot.py:TelegramBot.__init__`** — `self._current_task: asyncio.Task | None = None` 인스턴스 변수.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.4.1 → v3.4.2`
- **`src/telegram_bot.py:_run_analysis()`** — 시작 시점에 `self._current_task = asyncio.current_task()` 캡처. `except asyncio.CancelledError` 블록 추가 (사용자에게 "🛑 분석 중단됨" 알림 후 re-raise). `finally` 에서 `self._current_task = None`. `await self._process_queue()` 는 finally 에서 그대로 — `/stop` 후에도 큐 진행 (스킵하려면 `/stopall` 사용).
- **`src/telegram_bot.py:create_app()`** — `CommandHandler("stop", ...)` + `CommandHandler("stopall", ...)` 등록.
- **`src/telegram_bot.py:_start_command()`** — 도움말에 `/stop`, `/stopall` 두 줄 추가.

### Migration
- **VM 재기동 필요** — 코드 변경.
- 기존 동작 변경 없음. 새 명령만 추가.

### 동작 노트
- `CancelledError` 는 Python 3.8+ 부터 `BaseException` 상속이라 `except Exception:` 에 안 잡힘 — orchestrator/agent 의 일반 except 블록을 통과해 위로 전파.
- subprocess 기반 Claude CLI 호출 (`asyncio.create_subprocess_*`) 도 cancel 시 SIGTERM 전파됨.
- 부분적으로 생성된 `reports/` 임시 파일은 그대로 남을 수 있음 — 다음 분석에 영향 없음, 추후 cleanup 필요시 별도 작업.

---

## [3.4.1] — 2026-05-01

> **`/status` build info — 운영 디버깅 가속.** 봇 프로세스가 시작될 때 git 상태 (branch / short commit / commit date / dirty) 를 한 번 캡처해 `src/orchestrator.py:BUILD_INFO` 에 보관. 시작 로그 (`Starting Event Analysis Team bot — v3.4.1 · branch=main · commit=af9443d (...)`) 와 텔레그램 `/status` 응답 모두에 노출. *실행 중인 코드*의 커밋을 가리키므로 (pull 후 재기동을 안 한 케이스 포함) 운영자가 버전 미스매치를 즉시 알 수 있다.

### Added
- **`src/orchestrator.py:_capture_build_info()` + `BUILD_INFO`** — `git rev-parse --abbrev-ref HEAD` / `--short=7 HEAD` / `git log -1 --format=%cd --date=format:...` / `git status --porcelain` 4개 호출 (각 timeout 2s, stderr 무음). 실패 시 `"?"` 로 graceful degrade. import 시점에 1회만 실행 — 이후 disk 변경은 반영되지 않으며 이게 *목적*이다.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.4.0 → v3.4.1`
- **`src/main.py:main()`** — `app.run_polling()` 직전 `logger.info("Starting Event Analysis Team bot — %s · branch=%s · commit=%s (%s)%s", ...)` 추가. 운영자가 tmux 첫 줄에서 즉시 확인.
- **`src/telegram_bot.py:_status_command()`** — `브랜치` / `커밋` 두 줄 추가 (`✅ 봇 실행 중` 직후, `가동시간` 위). dirty 일 때 `⚠️ uncommitted` 표기.

### Migration
- **VM 재기동 필요** — 코드 변경. 재기동 후 시작 로그와 `/status` 출력에 새 줄이 보여야 정상.
- 비-git 환경 / repo 외부에서 실행 시 `BUILD_INFO` 가 모두 `"?"` 로 표시됨 — 의도된 동작.

---

## [3.4.0] — 2026-05-01

> **`map` BlockType — MapLibre + d3-geo 지도 블록 통합.** 보고서 파이프라인에 maplibre-gl 4.7 + d3-geo v7 기반 지도 블록을 정식 추가. `BlockType` Literal 18번째로 `"map"` 등록. light_mono / burgundy_mono 두 테마와 골드(#C9A84C) 단일 하이라이트 원칙은 `samples/theme_mono_map_chart.html` 의 검증된 디자인을 그대로 옮긴다. 데이터 소스는 기존 `visual_analyst` 의 `leaflet_config` 를 재사용해 분석 흐름 변경 없이 시각화만 교체. 데이터 없으면 빌더가 None 반환 → 자동 스킵.

### Added
- **`src/templates/blocks/map.html`** — 새 블록 템플릿. `data-block-id` + `theme-light_mono`/`theme-burgundy_mono` 클래스 + `<script type="application/json">` 페이로드. 초기화는 `maps.js` 가 `DOMContentLoaded` 에 일괄 처리.
- **`src/templates/static/maps.js`** — `window.MapBlocks.initAll()` 진입점. maplibre-gl 인스턴스 생성, `d3.geoTransform` 으로 maplibre `map.project()` 를 d3-geo path projection 에 위임, `d3.geoInterpolate` 로 great-circle arc 64분할. `move`/`resize` 이벤트마다 SVG 오버레이 재투영. 244 lines, no deps beyond global `maplibregl` + `d3`.
- **`src/templates/static/maps.css`** — 블록 컨테이너·헤드·스테이지·범례·캡션 + 두 테마 CSS variables. 버건디는 `voyager_nolabels` 베이스 + `grayscale → sepia → hue-rotate(-22deg) → brightness(0.78)` 필터로 마룬 합성, 라이트는 `light_nolabels` + `grayscale → contrast(0.96) → brightness(1.04)`.
- **`src/visual_builder.py:build_map_payload()`** — leaflet_config (legacy `[lat,lng]`) → MAP block payload (`[lng,lat]`) 변환기. marker color/emoji 로 highlight 결정, line color 명시 시 highlight, 매칭 안 되는 line endpoint 는 placeholder 노드로 합성. legend 도 자동 생성.
- **`src/agents/report_synthesizer.py:_payload_map()`** — `result.visuals.leaflet_config` 가 enabled 일 때만 payload 빌드. theme 은 `result.report_theme` 을 따라 burgundy/light 분기. `_BLOCK_BUILDERS["map"]` 에 등록.
- **`src/tests/test_map_block.py`** — 13 케이스 (BlockType 검증, leaflet → maplibre 좌표 변환, highlight 룰, theme 분기, legend 자동 생성, placeholder 노드 합성, 빌더 등록).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.3.1 → v3.4.0`
- **`src/models.py:BlockType`** Literal 에 `"map"` 추가 (17 → 18종).
- **`src/agents/report_synthesizer.py:STATIC_ASSETS`** `+ "maps.js", "maps.css"` (보고서 디렉토리 동기화 대상).
- **`src/agents/report_synthesizer.py:synthesize()`** `result.report_theme = theme` 를 초입에 기록 → block builder 가 light/burgundy 분기 가능.
- **`src/templates/report_block.html`** + **`src/templates/archetypes/freeform_essay.html`** — `has_map_block` 분기로 maplibre-gl CSS/JS + `maps.css`/`maps.js` + `d3.v7.min.js` 조건부 로드. 차트 블록과 d3 공유.
- **`src/archetypes/geopolitical_strategic.py`** — "전장·행위자" 섹션의 `block_types` 에 `"map"` 선두 추가. 데이터 없으면 자동 스킵.

### LLM 호출 수 변화
- 없음. 결정적 빌더만 추가.

### 보고서 디자인 변화
- `geopolitical_strategic` archetype 으로 라우팅된 보고서 + visual_analyst 가 `leaflet_config` 를 enabled 로 산출한 경우 → "전장·행위자" 섹션 상단에 maplibre+d3-geo 지도 블록이 등장. 기존 Leaflet 시각화 (`report.html` six_act_theater 경로) 는 그대로 유지.
- freeform_essay (deep 모드) 도 `_build_all_available_blocks` 에서 자동으로 map 블록 빌드 → composer 가 `embedded_blocks` 에 `"map"` 을 referencing 하면 본문에 박힘.

### Migration
- 기존 보고서 URL 계속 동작.
- visual_analyst 프롬프트 / 산출물 스키마 변경 없음 — `leaflet_config` 를 그대로 사용.
- **VM 재기동 필요** (코드 변경, 정적 자산 추가).
- 보고서 디렉토리에 `maps.js` / `maps.css` 가 처음 보고서 생성 시 자동 동기화됨.

---

## [3.3.1] — 2026-05-01

> **Sample 추가 (showcase only).** 보고서 파이프라인에는 변화 없음 — 디자인/톤앤매너 검증용 독립 HTML 페이지 1개 추가.

### Added
- **`samples/theme_mono_map_chart.html`** — maplibre-gl 4.7 + d3-geo v7 단일 페이지 샘플. 라이트 모노 (#FAFAF7 크림) / 버건디 모노 (#2B1A1A 마룬) 두 팔레트에 동일 데이터셋 (동북아·동남아 항만 네트워크 + 16주 컨테이너 처리량) 을 입혀 비교. 두 테마 공통 하이라이트 `#C9A84C` (골드) 로 부산↔싱가포르 회랑·관측 노드·14주차 피크 막대만 강조. 베이스 타일은 CartoDB `light_nolabels` / `dark_nolabels` + CSS 필터(`grayscale` / `sepia + hue-rotate`) 합성. d3.geoTransform 으로 maplibre `map.project()` 를 d3-geo path 에 위임, `d3.geoInterpolate` 로 great-circle arc 64분할.

### Changed
- **`src/orchestrator.py:VERSION`** `v3.3.0 → v3.3.1`
- **`README.md`** Status / Recent Changes / `last_synced_with` 갱신

### Not Changed (중요)
- **보고서 생성 파이프라인은 v3.3.0 과 동일.** 이 샘플은 `src/templates/`, `src/visual_builder.py`, `src/agents/visual_analyst.py`, `src/models.py:BlockType` 어디에도 연결되지 않은 **독립 쇼케이스**. 텔레그램 보고서가 maplibre 지도를 포함하려면 별도 통합 작업 (BlockType 추가, 블록 빌더, 템플릿 임베드, archetype 라우팅) 이 필요하며 이는 v3.4.0 이상에서 다룬다.
- VM 재기동 불필요 (런타임 동작 변화 없음).

---

## [3.3.0] — 2026-04-30

> **Narrative Composer (Opus 4.7) — Freeform Editorial Pass.** 보고서가 17 BlockType 슬롯에 데이터를 부어넣는 정형 구조에서 벗어나, deep 모드에서 Opus 4.7 단일 콜이 *편집장* 역할로 사건 성격에 맞춰 섹션 수/길이/순서/톤을 자유 결정. 차트는 composer 가 본문에 박는 자리만 결정하고 (auto-dashboard 폐지), 데이터 빌드는 그대로 결정적. fast/standard 모드는 영향 없음.

### Added
- **`src/agents/narrative_composer.py`** `NarrativeComposer` — Opus 4.7 (`claude-opus-4-7`) 단일 콜로 `ComposedReport` 산출. 전체 분석 결과 + claim 카탈로그 + 차트 catalog 를 입력으로 받음. CLI/API 모드 모두 지원, max_tokens=8192. 실패 시 `None` 반환하여 호출자가 폴백.
- **`src/models.py:ComposedReport`** + **`ComposedSection`** — composer 산출물 Pydantic 모델. `embedded_charts: list[chart_id]` + `embedded_blocks: list[block_type]` + `cited_claim_ids` 로 evidence 추적성 보존 (Anti-pattern #4 우회 금지).
- **`src/models.py:FullAnalysisResult.composed_report`** — composer 출력 보유 필드. None 이면 폴백 archetype 으로 라우팅.
- **`src/archetypes/freeform_essay.py`** + **`src/templates/archetypes/freeform_essay.html`** — composer 출력 전용 archetype + 템플릿. 산문 우위 디자인 (max-width 780px, Noto Serif KR 헤드라인, 최소한의 chrome). select_archetype matrix 가 아니라 orchestrator 가 deep + 성공 시 *명시* 라우팅.
- **`src/visual_builder.py:build_chart_catalog()`** + **`chart_id_to_payload_key()`** — 데이터 가용한 차트만 `[{id,title,hint}]` 로 노출. composer prompt 입력에 포함되어 invalid chart_id reference 방지.
- **`src/agents/report_synthesizer.py:_build_all_available_blocks()`** — freeform_essay 용 블록 빌더. section_plan 무관하게 가용한 BlockType 마다 1개씩 빌드 → composer 가 type 으로 referencing.
- **`src/tests/test_narrative_composer.py`** — 16 pytest 케이스 (chart catalog 필터링, ComposedReport/Section 모델, parser, reference validator, archetype 등록, token budget gating, payload builder).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.2.0 → v3.3.0`
- **`src/orchestrator.py:run_analysis`** — judgment + visuals 직후 `narrative_composer.compose()` 호출 (deep 모드만). 성공 시 archetype 을 `freeform_essay` 로 *명시* 라우팅 (matrix 우선순위 무시). 실패 시 `select_archetype()` 폴백.
- **`src/orchestrator.py:Orchestrator.__init__`** + **`_wire_telemetry`** — `narrative_composer` 인스턴스 등록 + telemetry 와이어링.
- **`src/token_budget.py:TokenBudget`** — `use_llm_narrative_composer: bool` 필드 신규. deep=True, 그 외 False. deep 의 `max_llm_calls` `12 → 13` (composer +1).
- **`src/archetypes/registry.py`** — `freeform_essay` 추가 (총 12종).

### LLM 호출 수 변화
- fast/standard: 변화 없음 (composer 비활성).
- deep: `+1 Opus 4.7 콜` (max_tokens 8K, 입력 ~30~50K). 총 12 → 13. 기존 `_generate_executive_summary` / `_generate_narrative_plan` 보조 콜은 그대로 유지 (composer 출력이 메인 본문, deterministic summary 는 hero 영역).

### 보고서 디자인 변화
- deep 모드 보고서: 정형 17 슬롯 매핑이 아닌 **3~7개 자유 섹션** + 사건 성격에 맞춘 헤드라인/부제. Auto-dashboard 폐지 — 차트는 본문 흐름에 따라 composer 가 적재적소에 embed.
- Evidence 추적성: 본문에 등장하는 핵심 주장 옆에 `cited_claim_ids` (claim_id 목록) 인용 표기.
- fast/standard: v3.2.0 과 동일 (auto-dashboard + 정형 archetype).

### Migration
- 기존 보고서 URL 계속 동작.
- `FullAnalysisResult.composed_report` 필드는 optional — 기존 코드 영향 없음.
- 새 archetype `freeform_essay` 는 select_archetype() matrix 에 포함되지 않음 (orchestrator 만 라우팅).

---

## [3.2.0] — 2026-04-30

> **d3 Chart Dashboard + Mobile-first Scenario Cards.** 보고서 시각화 품질을 대폭 강화하는 minor 릴리스. d3 v7 라이브러리 인라인 임베드 (정적 자산) + 9종 차트 라이브러리 + 모바일 우선 시나리오 카드. 보고서가 데이터 가용성에 따라 자동으로 적절한 차트들을 모두 생성. v3.1.0 의 token budget 정책은 그대로.

### Added
- **`src/templates/static/d3.v7.min.js`** — d3 v7.9.0 minified (~274KB). Cloudflare Pages 에 정적 자산으로 배포되어 외부 CDN 의존 없음.
- **`src/templates/static/charts.js`** — 9종 d3 SVG 차트 라이브러리 (~700 lines). 모두 hover 인터랙션 + 진입 애니메이션 + 자체 디자인 토큰.
  1. `drawScenarioBar` — 시나리오 확률 가로 막대 (gradient + tag 색띠)
  2. `drawKeyFiguresDonut` — 핵심 수치 도넛
  3. `drawSeverityHeatmap` — 인과 사슬 위험도 히트맵 (CSS 기반, PDF 안전)
  4. `drawConfidenceTriple` — 신뢰도 3축 막대
  5. `drawTimeseriesLine` — 시계열 라인 (area gradient + animated path)
  6. `drawStackedBar` — 시나리오 × 행위자 누적 막대
  7. `drawBubble` — 리스크 매트릭스 (확률 × 영향, 4사분면)
  8. `drawGantt` — 타임라인 간트 차트
  9. `drawNetwork` — 행위자 force-directed 네트워크 그래프
- **`src/templates/static/charts.css`** — 차트 + 시나리오 카드 + hero dashboard 디자인 토큰 (~250 lines). burgundy 테마 변수 상속.
- **`src/visual_builder.py`** 차트 데이터 빌더 8종 — `build_scenario_chart_data`, `build_key_figures_chart_data`, `build_severity_chart_data`, `build_confidence_chart_data`, `build_stacked_chart_data`, `build_bubble_chart_data`, `build_gantt_chart_data`, `build_network_chart_data`, `build_chart_payload` (모두 결정적, LLM 호출 0).
- **`src/agents/report_synthesizer.py:_sync_static_assets`** — 보고서 디렉토리에 d3/charts.js/charts.css 자동 복사 (size+mtime 기반 idempotent).
- **`samples/chart_gallery.html`** — 9종 차트 모두 한 페이지에 보여주는 샘플 갤러리.
- **`src/tests/test_chart_builders.py`** — 24 pytest 케이스 (각 차트 데이터 빌더, 통합, 정적 자산 존재, 시나리오 카드 템플릿 검증).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.1.0 → v3.2.0`
- **`src/templates/blocks/scenario_table.html`** — 4컬럼 `<table>` 폐기 → 모바일 우선 카드 그리드 (`scenario-grid` + `scenario-card`). 모바일에서 1열, 720px+ 에서 2열. tag 별 색띠 (`최선`/`기본`/`악화`/`최악`), 확률 큰 숫자 + gradient bar, 영향을 sentiment 색 칩으로 표시.
- **`src/templates/report.html:render_scenarios`** — 동일하게 카드 그리드로 통일. 표 마크업 완전 폐기.
- **`src/templates/report.html`** — 보고서 상단에 "한눈에 보기" (DATA DASHBOARD) 섹션 추가. 데이터 가용성에 따라 최대 8개 d3 차트 자동 렌더. 보고서 끝에 `<script type="application/json" id="chart-payload">` + d3.js + charts.js 로드.
- **`src/templates/report_block.html`** — 동일한 차트 대시보드 섹션 추가 (block dispatcher 경로 archetype 도 차트 동일하게 표시).
- **`src/agents/visual_analyst.py:VisualAnalyst.analyze(judgment=...)`** — 새 인자. deterministic 경로에서 신뢰도 차트 데이터 빌더 호출용.
- **`src/orchestrator.py:run_analysis`** — 시각화 단계를 SynthesisJudge 이후로 이동 (judgment.confidence 를 차트 데이터로 전달하기 위함).
- **`src/visual_builder.py:build_visuals(judgment=...)`** — 새 인자. `chart_config.payload` 에 8종 차트 데이터 dict 자동 채움.

### LLM 호출 수 변화
없음. 모든 차트는 결정적 빌더로 생성 (LLM 호출 0). v3.1.0 의 mode 정책 그대로 유지 — fast 4회, standard 7회, deep 12회.

### 보고서 크기 변화
- 보고서 HTML 자체: +2~5KB (chart payload + chart card markup)
- 정적 자산 (한 번만 다운로드 + 캐시): d3.v7.min.js 274KB + charts.js ~26KB + charts.css ~6KB = **306KB 추가** (Cloudflare 캐시 후 재방문 시 0KB)
- 첫 방문 시 Cloudflare CDN 에서 모든 자산 한 번에 다운로드 → 후속 보고서 방문은 캐시 사용

### 보고서 자동 차트 매트릭스
| 데이터 가용성 | 자동 생성되는 차트 |
|-----|-----|
| `scenarios` | 시나리오 막대 + (impact_by_player 있으면) 누적 막대 |
| `key_figures` | 도넛 |
| `chain.chain` | severity 히트맵 |
| `judgment.confidence` | 3축 신뢰도 막대 |
| `chain.wildcards` | 리스크 매트릭스 (버블) |
| `context.timeline ≥ 2건` | Gantt 타임라인 |
| `players.players + alliances` | force-directed 네트워크 그래프 |

데이터 없으면 해당 차트는 안 그림 (현재 정책 그대로).

### Migration
- 기존 보고서 URL 계속 동작 (마크업 변경만, 데이터 모델 변경 없음).
- `result.visuals.chart_config` dict 의 구조에 `payload` 키 추가됨 — 기존 `enabled`/`charts` 키는 그대로 유지 (LLM VisualAnalyst 산출물 호환).
- 봇 재시작 시 자동으로 d3/charts.js/charts.css 가 첫 보고서 생성 시 reports/ 로 복사되어 Cloudflare 에 배포됨.

---

## [3.1.0] — 2026-04-27

> **Token Budget + Mode Routing.** 보고서 품질을 유지하면서 입력 토큰·LLM 호출 수를 약 절반으로 줄이는 minor 릴리스. 한 사건에 모든 에이전트를 무조건 실행하던 기존 정책을 폐기하고, fast/standard/deep 3모드로 분기. v3.0.0 의 분석 모델·블록 시스템·archetype 11종은 그대로 유지.

### Added
- **`src/token_budget.py`** — `AnalysisMode` Literal (fast/standard/deep) + `TokenBudget` dataclass.
  - fast: 최대 LLM 호출 4회, lens 1개. quality gate / narrative plan / visual / synthesis LLM 모두 비활성. 페르소나 비활성. 메타 lens 비활성.
  - standard: 최대 LLM 호출 7회, lens 2개. 메타 lens 허용. synthesis LLM 은 contradictions / 저신뢰 / 미답변 risk 시에만 발화.
  - deep: 최대 LLM 호출 12회, lens 4개. 모든 LLM augmentation 활성 + 페르소나 호출.
  - `resolve_mode(event_description)` — 사용자 메시지의 키워드 (`짧게`/`간략히` → fast, `심층`/`자세히` → deep) 로 mode 결정. default `standard`.
- **`src/lens_policy.py`** — `select_lenses(event_type, user_intent, mode)` 코드 규칙 기반 lens 결정자.
  - 분야별 lens 우선순위 (tech_architecture / financial_transmission / accident_causality / policy_implementation / market_structure / geopolitical / stakeholder / structural / cascade).
  - 메타 lens (red_team / pre_mortem) 는 의사결정 / 취약점 / 전망 의도에서만 자동 추가.
  - `select_theme(event_type)` 코드 규칙 — Strategy Planner 프롬프트에서 분리.
- **`src/brief_builder.py`** + `src/models.py:AnalysisBrief`** — 후속 에이전트/렌즈에 전달할 *압축* 컨텍스트.
  - 모든 list 필드 길이 cap (BRIEF_MAX_FACTS=8, BRIEF_MAX_TIMELINE=6, BRIEF_MAX_ACTORS=5, BRIEF_MAX_CAUSAL=6, BRIEF_MAX_SCENARIOS=4, BRIEF_MAX_UNCERTAINTIES=4, BRIEF_MAX_SOURCES=8).
  - `compact()` — 빈 필드 자동 생략 dict 반환.
- **`src/visual_builder.py`** — 결정적 SVG 빌더 (`build_actor_relationship_svg`, `build_flow_chain_svg`, `build_scenario_table`, `build_visuals`). LLM 없이 SVG 생성. fast/standard 의 default. `needs_advanced_visuals()` 키워드 (지도/차트/시계열) 매칭.
- **`src/telemetry.py`** — `RunTelemetry` (사건당 인스턴스). 각 LLM 호출의 input/output char, elapsed ms, 단계별 timing, 선택된 lens / 스킵된 에이전트 / 스킵된 LLM 단계 기록. 보고서 완료 후 `log_summary()` 자동 호출.
- **`src/tests/test_token_optimization.py`** — 24 pytest 케이스 (TokenBudget 모드별 cap, resolve_mode 키워드, lens_policy 매핑, compact JSON serialization, AnalysisBrief 길이 제한, deterministic summary, persona gating, narrative plan gating, SynthesisJudge gating, visual builder).

### Changed
- **`src/orchestrator.py:VERSION`** `v3.0.0 → v3.1.0`
- **Strategy Planner 프롬프트 대폭 축소** — 약 4,200자 → 약 800자 (5배 축소).
  - 출력 항목: `event_type` / `user_intent` / `intent_confidence` / `core_questions` 만 LLM 이 산출.
  - archetype 선택은 `select_archetype()` matrix 단독 결정자 (LLM 후보 폐기).
  - theme 는 `lens_policy.select_theme()` 코드 규칙.
  - recommended_lenses 는 `lens_policy.select_lenses()` 가 mode 기반 결정.
  - per-agent directive (`legacy_directives`) 는 더 이상 LLM 으로 생성하지 않음 (transitional shim 은 보존, v4.0.0 제거 예정).
  - 모델: `model_name` (Opus) → `model_name_light` (Sonnet).
- **`src/agents/base.py:_serialize_context`** — `json.dumps(..., indent=2)` → `separators=(",", ":")` (한국어 JSON 토큰 ~30~50% 절감). `context.pop` 부작용 제거 — 호출자 dict 변형 금지.
- **`src/agents/base.py:BaseAgent.telemetry`** — 새 필드. orchestrator 가 사건당 `RunTelemetry` 인스턴스 주입 → 각 LLM 호출 자동 기록.
- **`src/orchestrator.py:run_analysis(mode=...)`** — mode 인자 추가 (None 이면 키워드 자동 매핑). 페르소나 (PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst) 호출은 `budget.use_legacy_personas=True` 일 때만 (deep 모드 전용).
- **`src/agents/quality_inspector.py:QualityInspector.use_llm_judge`** — 새 플래그. default False. fast/standard 는 heuristic 만, deep 또는 환경변수 `QUALITY_LLM_JUDGE=true` 일 때만 LLM judge.
- **`src/agents/synthesis_judge.py:SynthesisJudge`** — heuristic-first 전환. `use_llm_synthesis` (deep), `allow_llm_on_low_confidence` (standard, contradictions/저신뢰 시에만), `core_questions_at_risk` 플래그 추가. fast 는 heuristic 만.
- **`src/agents/visual_analyst.py:VisualAnalyst.analyze(use_llm=...)`** — 새 인자. False 면 `visual_builder` 결정적 빌더만 사용. fast/standard default.
- **`src/agents/report_synthesizer.py:ReportSynthesizer`** — `use_llm_narrative_plan` / `use_llm_executive_summary` 플래그. fast/standard 는 default narrative plan + deterministic executive summary 사용. deep 만 LLM 호출.
- **`src/agents/report_synthesizer.py:_build_deterministic_summary()`** — 새 staticmethod. `judgment.main_judgment` + `biggest_uncertainty` + `counter_hypothesis` + top finding 으로 governance + key items 결정적 생성.
- **`src/models.py:AnalysisRequest.mode`** — Literal[fast/standard/deep] 필드 추가. default `standard`.
- **`src/agents/scenario_architect.py`** — persona None 입력 가드 — fast/standard 에서 player/dynamics/chain_reaction None 으로 들어오는 케이스 안전 처리.

### Deprecated (호환 유지)
- `PlayerAnalyst` / `DynamicsAnalyst` / `ChainReactionAnalyst` 페르소나 — fast/standard 에서는 호출 안 함. deep 모드에서만 호출 (6막 보고서 풍부 데이터 보존).
  - v3.0.0 부터 이미 `DeprecationWarning` 발화 중. v4.0.0 에서 6막 템플릿 재작업과 함께 정식 제거 예정 (FUT-LEGACY-001).

### LLM 호출 수 변화 (분석 1건당, 추정)
| Mode | v3.0.0 (이전) | v3.1.0 (이후) | 변화 |
|------|------------|------------|------|
| fast (구 quick_mode) | ~9 | **3~4** | -55% |
| standard (default) | 13~15 | **5~7** | -55% |
| deep | 13~15 | **9~12** | -20% (품질 보존) |

추가로 Strategy Planner 프롬프트 5배 축소 + `indent=2` 폐기로 input 토큰도 ~30% 추가 절감.

### Migration Notes
- 기존 `quick_mode` 키워드는 자동으로 `fast` mode 로 매핑됨 — 사용자 메시지 변경 불필요.
- `Orchestrator.run_analysis(event_description, chat_id)` API 변경 없음 (mode 인자는 optional).
- legacy 페르소나가 호출되지 않는 fast/standard 모드는 6막 (`six_act_theater`) 보고서를 받았을 때 일부 섹션 (이해관계자/구조/연쇄반응) 이 빈 상태가 될 수 있음. archetype matrix 가 적절한 block-based archetype 으로 라우팅하도록 강화됨.

---

## [3.0.0] — 2026-04-27

### Added
- **V3 Step 5-C — archetype 11종 완성 + 페르소나 → lens 이전. V3 리팩토링 최종.**
  - 신규 archetype 5종:
    - `decision_brief` — `what_to_do` 의도 전용 (옵션 비교 → 옵션별 리스크 → 권고 → Pre-mortem → 감시 신호)
    - `timeline_first` — `what_happened` 의도 전용 (핵심 요약 → 사실 타임라인 → 핵심 수치 → 출처 평가 → 미확인 사항)
    - `scenario_first` — `what_next` 의도 전용 (기준 시나리오 → 분기 시나리오 → 베이지안 업데이트 가이드 → 감시 신호)
    - `mechanism_decomp` — `why_happened` 의도 전용 (표층 현상 → 직접 원인 → 구조적 원인 → 제1원리 → 흔한 오해)
    - `industry_value_chain` — 산업·가치사슬 사건 (산업 구조 → 가치사슬 → 경쟁 구도 → 수익성 압력 → 전략 옵션 → 의사결정 포인트)
  - `src/archetypes/registry.select_archetype()` — 4-tier 우선순위 매트릭스 (분야+의도 → 의도 전용 → geopolitical → fallback)
  - `src/orchestrator.py` 하이브리드 라우팅 — LLM 1순위 후보 + matrix 최종 결정 (mismatch 시 INFO 로그로 추적)
  - 페르소나 → lens 이전 3종:
    - `src/lenses/stakeholder_lens.py` — `PlayerAnalyst` 대체 (행위자 식별, 전략, 위험도)
    - `src/lenses/structural_lens.py` — `DynamicsAnalyst` 대체 (게임이론, 비대칭, 전환점, 피드백 루프)
    - `src/lenses/cascade_lens.py` — `ChainReactionAnalyst` 대체 (인과 사슬, 도미노, 와일드카드)
  - `src/tests/test_archetype_selection.py` — 23 pytest 케이스 (Registry / 신규 5종 section_plan / 10-case 회귀 매트릭스 / tech 의도 차등화 / fallback warning)
  - `GOAL.md` REQ-V3-008 (archetype 11종 완성), REQ-V3-009 (페르소나 → lens 이전), `FUT-LEGACY-001` (v4.0.0에서 legacy alias 제거)

### Changed
- `src/orchestrator.py:VERSION` `v2.9.5 → v3.0.0`
- `six_act_theater.suitable_intents` 7종(default) → 2종(`who_benefits`, `what_happened`) — 인물극형 specialty 로 좁힘 (Anti-pattern #2 위반 아님: 코드/템플릿 그대로, 적용 범위만 좁힘)
- `src/lenses/registry.py` — 8종 → 11종 (분야 6 + 메타 2 + 페르소나 이전 3)
- `src/archetypes/registry.py` — 6종 → 11종, `select_archetype()` 매트릭스 4-tier 재설계
- Strategy Planner 가이드: archetype 후보 11종 + 4-tier 결정 규칙 (matrix 최종 결정)

### Deprecated
- `src.agents.PlayerAnalyst` → `src.lenses.stakeholder_lens.StakeholderLens` 사용 권장
- `src.agents.DynamicsAnalyst` → `src.lenses.structural_lens.StructuralLens` 사용 권장
- `src.agents.ChainReactionAnalyst` → `src.lenses.cascade_lens.CascadeLens` 사용 권장
- 위 3종 모듈 import 시 `DeprecationWarning` 발생 — v4.0.0 에서 모듈 제거 예정 (`FUT-LEGACY-001`)

### Removed
- 없음. V3 는 하위호환 유지. legacy alias 제거는 v4.0.0 (`FUT-LEGACY-001`) 별도 트랙.

### Security
- 변경 없음.

### Migration notes
- 페르소나 import 경로(`src.agents.player_analyst` 등) 는 v3.x 동안 동작 보장. 단, import 시점에 `DeprecationWarning` 출력 → `python -W error::DeprecationWarning` 으로 CI 게이트 가능.
- 신규 코드는 `src.lenses.*Lens` 사용. lens 는 `LensRunner.run()` 인터페이스 (페르소나 `.analyze()` 와 시그니처 다름) — alias 경로는 *동시 지원*, 호출 측 코드 변경 불필요.
- six_act_theater 가 더 이상 default 가 아님 — fallback 은 `select_archetype()` 매트릭스 끝의 명시적 fallback 분기 + warning 로그. 분류 매트릭스에서 매칭되지 않은 의도는 의도 전용 archetype 으로 라우팅.
- Watchlist DB 스키마 변경 없음 (v2.9.5 와 호환).

---

## [2.9.5] — 2026-04-26

### Added
- **V3 Step 5-B — Watchlist Registry**
  - `WatchSignal` Pydantic 모델 + `WatchDirection` Literal 3종 (confirms_base / rejects_base / ambiguous)
  - `src/watchlist/` 신설:
    - `registry.py` — `WatchlistRegistry` SQLite CRUD (`register`, `list_active`, `list_active_for_chat`, `mark_fired`, `get`, `count_active`, `count_total`)
    - `db_schema.sql` — `watchsignals` 테이블 + 3 인덱스 (active/chat/deadline). WAL 모드.
    - `converter.py` — `ScenarioAnalysis.watch_signals` (dict[]) → `list[WatchSignal]`. direction 휴리스틱 추정, deterministic signal_id, default deadline = today+30일
    - `monitor.py` — `run_monitor_loop` (봇 프로세스 내 asyncio task, 1시간 주기), `tick_once` (테스트 mock 가능), `format_telegram_alert` (spec 템플릿 정확)
  - 텔레그램 명령: `/watchlist` (이 채팅의 active 신호), `/fire <signal_id> [direction]` (수동 발화)
  - 봇 lifecycle hooks: `_on_app_post_init` (monitor task 기동) / `_on_app_post_shutdown` (정리)
  - Orchestrator: 분석 종료 후 `result.scenarios.watch_signals` 자동 변환 + DB 등록 (Anti-pattern #11 회피)
  - `src/tests/test_watchlist.py` — 19 pytest 케이스 (모델 / Registry CRUD / converter / monitor auto-fire (mocked clock) / 봇 재시작 시뮬레이션 / 알림 포맷)

### Changed
- `src/orchestrator.py:VERSION` `v2.9.0 → v2.9.5`
- `Orchestrator.__init__` 에 `watchlist_registry` optional 인자 추가 (None 시 등록 스킵 — 단위 테스트 안전)
- `TelegramBot.__init__` 가 `WatchlistRegistry(reports/watchlist.db)` 생성 후 orchestrator 에 주입 + Application.builder 에 post_init/post_shutdown 훅 등록
- 봇 시작 메시지 (`/start`) 에 `/watchlist`, `/fire` 도움말 추가

### Migration notes
- DB 파일 자동 생성 (`reports/watchlist.db`). 기존 보고서 파일들과 같은 디렉토리 — `.gitignore` 의 `reports/` 패턴에 자연스럽게 포함되어 git 추적 안 됨.
- 외부 시장 데이터 자동 폴링은 본 마일스톤 *밖* (FUT 트랙). 발화 트리거는 deadline 자동 + `/fire` 수동 둘만.
- 봇 재시작 시 별도 복구 호출 불필요 — SQLite 영구 저장이라 인스턴스화만으로 active 신호 복구.

---

## [2.9.0] — 2026-04-26

### Added
- **V3 Step 5-A — Lens Pool 도입**
  - `src/lenses/` 디렉토리 + `LensRunner` ABC + `registry.py` (8종 lens registry, 미등록 폴백)
  - 8종 lens 신설: `geopolitical`, `financial_transmission`, `tech_architecture`, `policy_implementation`, `accident_causality`, `market_structure`, `red_team`, `pre_mortem`
  - 사건당 동시 실행 한도 = 4 (Pydantic `max_length=4` + orchestrator `LENS_CAP_PER_EVENT=4` 이중 가드, Anti-pattern #6)
  - 신규 archetype 3종: `geopolitical_strategic`, `accident_forensic`, `policy_implementation` (총 6 archetypes)
  - `src/tests/test_lens_pool.py` — 11 pytest 케이스
  - `result.findings = wrapped + lens_findings` (Step 4 wrap + Step 5 lens 동시 운용)

### Changed
- `src/orchestrator.py:VERSION` `v2.8.0 → v2.9.0`
- Strategy Planner 프롬프트에 archetype 6종 + lens 8종 매트릭스 + 선택 규칙 + 4-cap 명시
- 텔레그램 진행 메시지에 "🔬 Lens 풀 실행: [...] (N/4 cap)" 추가

### Migration notes
- 기존 페르소나 (Player/Dynamics/ChainReaction) 는 *그대로 유지*. lens 는 *추가* 호출이라 v2 회귀 0건. 페르소나 → lens 이전은 v3.0.0 (Step 5-C) 에서.
- Watchlist 자동화 (5-B) 는 v2.9.5 마일스톤 — 별도 PR.
- six_act_theater 보고서 출력 byte-equal 보장 유지 (legacy 분기 무수정).

---

## [2.8.0] — 2026-04-26

### Added
- **V3 Step 4 — Quality Gate 1/2 + Claim-Evidence 추적성 + Synthesis Judge**
  - 모델: `Claim` (evidence_ids ≥1 Pydantic 강제, Anti-pattern #4), `Evidence`, `ConfidenceProfile` (3축, Anti-pattern #10), `AnalyticalFinding`, `JudgmentVerdict` (contradictions 노출, 봉합 X — Anti-pattern #5)
  - `FullAnalysisResult.findings`, `FullAnalysisResult.judgment` 신규 필드
  - `src/agents/quality_inspector.py` — `gate_1_plan_sanity` + `gate_2_coverage_check` (heuristic-first, LLM-as-judge 보강)
  - `src/agents/synthesis_judge.py` — findings → JudgmentVerdict, 어휘+counter_hypothesis 기반 모순 검출, 3축 신뢰도 합성
  - `orchestrator._wrap_findings()` — v2 분석 결과를 AnalyticalFinding 리스트로 래핑 (sources → Evidence 풀)
  - 게이트 wiring: gate 1 (strategy 직후, max 2 retry), gate 2 (보고서 합성 직전, max 2 retry), 실패 시 "⚠️ 부분 분석 완료. {gate} 실패 ({reason})" 텔레그램 알림 — 우회 금지 (Anti-pattern #7)
  - 게이트 통과율·재시도율 통계 INFO 로그
  - `src/tests/test_quality_gates.py` — 18 케이스 pytest 단위 테스트

### Changed
- `src/orchestrator.py:VERSION` `v2.7.0 → v2.8.0`
- 텔레그램 진행 메시지에 "🧮 종합 판단관" 단계 추가 (모순 건수 노출)

### Deprecated
- 기존 `confidence_score: float` 필드들 (`ContextAnalysis`, `PlayerAnalysis` 등) — 호환 목적 보존, 신규 코드는 `ConfidenceProfile` 사용 (Anti-pattern #10 회피)

### Migration notes
- six_act_theater 보고서 출력은 기능적으로 v2.7.0 과 동일. 진행 메시지에 게이트/판단관 단계만 추가.
- 게이트 실패가 분석 *중단* 을 뜻하지 않음 — 부분-분석 알림 후 보고서 생성 계속.

---

## [2.7.0] — 2026-04-26

### Added
- **V3 Step 3 — 보고서 블록 렌더링 시스템**
  - `BlockType` Literal 17종 + `AnalysisBlock` Pydantic 모델 (`src/models.py`)
  - `FullAnalysisResult.blocks: list[AnalysisBlock]` 필드
  - `src/templates/blocks/` — 17개 단일-책임 템플릿 (각 ≤50 줄, payload-only access)
  - `src/templates/report_block.html` — 디스패처 (section_plan iterate + section_id 매치)
  - `src/agents/report_synthesizer.py` — `_BLOCK_BUILDERS` 레지스트리 + 17개 `_payload_*` 빌더
  - `report.css` — block-* 클래스 append (기존 클래스 무수정, 디자인 토큰 재사용)

### Changed
- `src/orchestrator.py:VERSION` `v2.6.0 → v2.7.0`
- 신규 archetype (`financial_transmission`, `tech_decomposition`) 의 `template_path()` 가 `report_block.html` 반환 — Step 2 placeholder HTML 은 디스크에 보존되지만 사용 안 됨 (Anti-pattern #2)
- `ReportSynthesizer.synthesize()` 가 archetype 별 분기: legacy six_act_theater 는 기존 흐름 (byte-equal 보장), 그 외는 블록 빌더 + 디스패처

### Migration notes
- six_act_theater 보고서 출력은 v2.6.0 과 byte 단위 동일 (sha256 검증 통과).
- 신규 BlockType 추가 절차: ① `src/models.py:BlockType` Literal 확장 → ② `src/templates/blocks/<type>.html` 신설 (≤50 줄, payload-only) → ③ `_BLOCK_BUILDERS` 등록 → ④ `docs/CATALOGS.md §4` 갱신 (Anti-pattern #15).

---

## [2.6.0] — 2026-04-26

### Added
- **V3 Step 2 — 보고서 아키타입 다중화**
  - `src/archetypes/` 디렉토리 신설 (Protocol-based registry pattern)
    - `base.py` (`ReportArchetype` Protocol, `runtime_checkable`)
    - `six_act_theater.py` (default; 기존 `report.html` 그대로 가리킴)
    - `financial_transmission.py` (시장·거시 사건용 archetype)
    - `tech_decomposition.py` (기술·AI·IT 사건용 archetype)
    - `registry.py` (`get_archetype()`, `list_archetypes()`)
  - `src/templates/archetypes/{financial_transmission,tech_decomposition}.html` (Step 2 placeholder; Step 3 에서 본격 블록 렌더링)
  - Strategy Planner 프롬프트에 archetype 자동 선택 매트릭스 추가 (user_intent + event_type → archetype_id)
  - `ReportSynthesizer.synthesize()` 에 `archetype` 인자 추가, `archetype.template_path()` 로 분기

### Changed
- `src/orchestrator.py:VERSION` `v2.5.0 → v2.6.0`
- `AnalysisStrategy.report_archetype` 가 본격 활용됨 (Step 1 에서는 placeholder default 만 보유)
- 기존 6막 극장은 `archetype="six_act_theater"` 로 강등 — 분류 애매 시 default fallback (Anti-pattern #2: 즉시 제거 금지)

### Migration notes
- `archetype="six_act_theater"` 경로의 렌더 출력은 이전과 byte 단위 동일 (sha256 검증 통과).
- LLM 이 미등록 archetype_id 를 출력하면 `get_archetype()` 가 `six_act_theater` 로 폴백하며 warning 로그 기록.

---

## [2.4.1] — 2026-04-26

### Added
- 문서 거버넌스 V3 적용 (3-tier 계층, SSOT 매트릭스, YAML 헤더 규약)
- `docs/CATALOGS.md` (에이전트·블록 카탈로그)
- `docs/DATA_MODELS.md` (Pydantic 모델 도식)
- `CHANGELOG.md` (본 파일, Keep a Changelog 형식)
- `CLAUDE.md` 에 Change Propagation 매트릭스

### Changed
- `docs_canonical/` → `docs/` 이름 단순화
- `overall_structure.md` 내용을 `docs/ARCHITECTURE.md` 에 흡수
- `prototype_*.html` 두 개를 `docs/references/` 로 이동
- `src/style_guide/REPORT_STYLE_GUIDE.md` → `docs/REPORT_STYLE_GUIDE.md` 이전
- `README.md` 60줄 이내로 슬림화 (진입점·링크 위주)

### Removed
- `overall_structure.md` (루트)
- `prototype_d3_map.html`, `prototype_gold_chart.html` (루트)

---

## [2.5.0] — 2026-04-26

### Added
- **V3 Step 1 — AnalysisStrategy Pydantic 모델 정식 승격**
  - `AnalysisStrategy`, `EvidenceNeed`, `ReportSectionPlan`, `VisualizationSpec`, `UserIntent` (Literal 7종) 신규
  - `user_intent` / `core_questions` / `recommended_lenses` 필드 도입 → 사용자 질문 의도별 분석 분기 기반 마련
  - `FullAnalysisResult.strategy: AnalysisStrategy | None` Optional 필드 추가
  - `model_validator` 로 lens-question 정합성 강제, `core_questions min_length=1` 보장
- `dynamics_analyst` 신규 필드: `feedback_loops`, `counter_view`, `cognitive_biases`
- `chain_reaction_analyst` 신규 필드: `feedback_loops`, `wildcards`, `time_horizon`, `effect_type`, `reversible`
- `scenario_architect` 신규 필드: `preconditions`, `invalidation_conditions`
- 보고서 균형 분석 4단락 구조 강제 (핵심 판단 / 상하방 비대칭 / 변수 민감도 / 한계)
- `.balance-analysis` CSS 컴포넌트 (시인성 강화)

### Changed
- `src/orchestrator.py:_generate_analysis_strategy()` 가 dict 대신 `AnalysisStrategy` 반환. 호출 측은 객체 속성 (`strategy.skip_agents`, `strategy.theme`) 으로 접근 (Anti-pattern #3 dict 회귀 방지).
- `src/orchestrator.py:VERSION` `v2.4.0 → v2.5.0`.
- 모든 에이전트 시스템 프롬프트의 용어 난이도를 학부생 수준으로 낮춤.
- 분석 시각 풀 확장: 게임이론·시스템 사고·경로 의존성·신호 이론·네트워크·행동경제학 등 14가지.

### Deprecated
- `AnalysisStrategy.legacy_directives` — Step 1 한정 transitional shim. Step 5 lens pool 도입 시 제거 예정. 신규 코드는 `recommended_lenses` 사용.

---

## [2.4.0] — 2026-XX-XX

### Added
- AI 소비용 Markdown 보고서 export

---

## [2.4.1-pre] (사전 v2.4.1) — 2026-XX-XX

### Changed
- 모든 테마의 텍스트 대비 개선

---

## [1.x] — 2026-03-27 ~ 2026-03-29

자세한 1.x 릴리스 흐름은 [DEVLOG.md §9 버전 히스토리](DEVLOG.md) 참조.
