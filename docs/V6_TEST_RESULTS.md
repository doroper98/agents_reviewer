---
tier: 2
status: v6_measurement_ssot
last_synced_with: v5.8.8
ssot_for:
  - "V6 효과·비용 측정 (append-only) — fact-error rate / 루프 횟수 / 호출수·한도·지연 / Codex FP율 / 소프트가드 적중률"
  - "V6 Phase 별 DoD 통과 기록 (모킹 테스트 + VM 실연동 로그)"
depends_on:
  - "REFACTOR_V6_PLAN.md §4 (테스트 플랜 T-0~T-10)"
  - "tests/regression/test_codex_*.py (모킹 회귀)"
  - "docs/V5_TEST_RESULTS.md (append-only 패턴 선례, AP-V5-32)"
last_review: 2026-06-03
---

# V6 테스트·효과 측정 결과 (append-only)

> **원칙 (AP-V6-6, AP-V5-32 계승).** 본 문서는 *추가만* 한다. 기존 entry 수정 금지.
> 측정은 첫 도입 시 **log-only → 측정 → enforce 승격** 순서 (REFACTOR_V6_PLAN.md §4.5).
> 외부(codex/웹) 의존 테스트는 *모킹 기본*(CI 결정적) + 실연동은 VM 수동 1회.

---

## §1. Phase 별 DoD 통과 기록

### Phase V6-1 — Codex CLI 통합 Spike + Verdict 계약 ◐ (코드 랜딩, VM 대기)

**일자**: 2026-06-03
**flag**: `V6_CODEX_CRITIC` (default OFF)

**랜딩 산출물**
- `src/models.py:FactVerdict` / `CritiqueClaim` — Codex verdict 계약 (REQ-V6-6/7/8).
- `src/agents/codex_critic.py:CodexCritic` — codex CLI headless 호출 + JSON 파싱
  + 절단복구(`_repair_truncated_json`) + 5경로 graceful degrade + 텔레메트리 적립.
- `src/config.py` — `codex_*` 필드 6종 (bin/subcommand/extra_args/model/timeout + 마스터 flag).

**모킹 회귀 (CI 결정적) — 통과**

| 테스트 | 대상 | 결과 |
|--------|------|------|
| T-V1 (`test_codex_contract.py`) | per-claim 필수필드 6종 누락/빈값 거부 + severity enum + status 정합 + degrade | ✅ 17 pass |
| T-C1 (`test_codex_critic.py`) | headless 호출(모킹)·JSON 파싱·코드펜스·절단복구·ungrounded claim drop | ✅ |
| T-C2 (`test_codex_critic.py`) | degrade 6경로 (flag_off/not_found/auth/rate_limit/generic/timeout) → skip → 발행 | ✅ |
| T-C3 (`test_codex_critic.py`) | 텔레메트리 JSONL 적립 (latency·skip_reason·violations) | ✅ |
| — | `test_codex_critic.py` 합계 | ✅ 22 pass |
| T-0 (byte-equal) | orchestrator 미연결 → flag OFF 호출 경로 불변 (자명) | ✅ (grep 검증) |

**합계: 39 tests pass (0.36s), `python -m py_compile` 통과.**

**남은 것 — VM 실연동 검증 (REFACTOR_V6_PLAN.md §3 Phase V6-1 "VM 검증 항목")**

> 아래는 *코드가 아니라 환경* 검증이라 fresh 컨테이너에선 불가 (codex·인증·reports 없음).
> VM(Oracle Ubuntu, 봇 가동기)에서 수동 1회 수행 후 결과를 본 §1 에 *추가* 기록.

1. ☑ codex CLI 설치 + ChatGPT headless 인증 — **완료 (2026-06-03)**. 아래 §VM 참조.
2. ☑ `codex exec` 호출 형태 확정 — **완료**. `exec` 가 stdin 프롬프트 수신, `-o <FILE>` 로
   최종 메시지만 수신. `.env` 기본값 = `V6_CODEX_SUBCOMMAND=exec` +
   `V6_CODEX_EXTRA_ARGS="--skip-git-repo-check --sandbox read-only"`.
3. ◐ Codex 호출 rate-limit/지연 — **단건 측정 완료** (e2e 검수 1회 = 35.1s, gpt-5.5).
   볼륨 한도(일일브리핑+온디맨드 빈도)는 Phase 3 루프 가동 후 누적 측정.
4. ☑ 비전(이미지) 입력 지원 — **YES** (`codex exec -i, --image <FILE>...`). Phase V6-4 가능.
5. ☑ 실제 봇 e2e 1회 — **완료 (2026-06-03)**. 아래 §봇 e2e 참조.

#### VM 실연동 로그 (2026-06-03, analysisbot)

- **환경**: Oracle Cloud Ubuntu (봇 가동기), Node v20.20.0 / npm 10.8.2.
- **설치**: `sudo npm install -g @openai/codex` (전역 prefix `/usr/lib/node_modules` 라 sudo
  필요). → **codex-cli 0.136.0**. 시스템 Node 미변경(봇의 claude CLI 보존).
- **인증**: `ssh -L 1455:localhost:1455` 포워딩 세션에서 `codex login` → ChatGPT 계정 OAuth
  (로컬 브라우저 콜백) → `~/.codex/auth.json` (0600) 생성. 토큰 자동 갱신.
- **모델**: 기본 `gpt-5.5` (provider openai). approval=never, sandbox=read-only 로 비대화 동작.
- **스모크**: `printf '... {"ok":true,"msg":"hi"}' | codex exec --skip-git-repo-check
  --sandbox read-only -C /tmp` → 정답 `{"ok":true,"msg":"hi"}` 반환 (1,592 tokens).
- **관측된 gotcha**: codex stdout 은 *배너(workdir/model/session) + 프롬프트 echo +
  `tokens used` 푸터* 로 오염됨 → 첫 `{` 스크랩이 echo 된 프롬프트의 `{` 를 잡을 위험.
  **대응**: `_call_codex_cli` 가 `-o <tmpfile>` 로 *최종 메시지만* 수신하도록 코드 보강
  (배너/echo/푸터 제거). 파일 비면 raw stdout 폴백 + 절단복구.
- **bubblewrap 미설치 경고**: codex 가 번들 bubblewrap 으로 폴백 — 동작엔 무해
  (읽기전용 검수라 샌드박스 거의 미사용). `sudo apt-get install -y bubblewrap` 로 제거함.

#### 봇 e2e 실연동 (2026-06-03, /tmp/v6spike 워크트리, `V6_CODEX_CRITIC=1`)

`CodexCritic.critique()` 에 NVIDIA 회귀 표본(본문에 scope/unsourced 오류 + evidence 에
정답 provenance) 투입. **실제 codex(gpt-5.5) 검수 결과:**

```
status=violations  violations=3  skipped=False  reason=  latency_ms=35101
 - unsourced_number   | headline  | '27년 만' 삭제/근거범위 수정
 - scope_misattribution | 발표 요지 | 130만 부품 → 보드 아니라 NVL72 랙 전체로 수정
 - unsourced_number   | 발표 요지 | '27년 만'·'PC 칩' 단정을 입증 가능 표현으로
```

- **핵심 검증**: 교차모델(GPT)이 Claude 본문의 scope_misattribution + unsourced_number 를
  *근거 대조*로 정확히 검출 (fact_discipline fixture 의 scope_misattribution_01 /
  unsourced_number_01 과 동형). V6 핵심 가설(외부 critic 으로 confabulation 검수) 실증.
- **파싱**: `-o` 클린 캡처로 parse_failed 0. 3 claims 모두 계약 통과 = codex 가
  evidence_conflict/quote/severity 까지 채움 (AP-V6-8 충족, ungrounded drop 0).
- **지연**: 35.1s (단건, 첫 호출 워밍업 포함). 일일브리핑(비동기)엔 무영향, 온디맨드
  보고서엔 루프당 codex 2회 ≈ +70s 예상 → Phase 3 에서 측정·튜닝.
- **텔레메트리 (T-C3 실측, `logs/codex_calls.jsonl`)**:
  ```
  {"ts":1780468194,"verdict_status":"violations","skipped":false,"skip_reason":"",
   "violations":3,"latency_ms":35101,"truncation_repaired":false,"prompt_chars":2253,"model":"(default)"}
  ```
  `truncation_repaired:false` = `-o` 클린 캡처로 복구 폴백 미발동 (codex 출력이 파서에
  그대로 진입). prompt_chars=2253 (report digest + evidence digest).

**→ Phase V6-1 DoD 전부 충족** (모킹 39종 + 실제 codex 1회 + flag OFF byte-equal).

**VM 수동 호출 (복사용) — codex 설치·인증 후 repo 루트 venv 활성 상태에서:**

```
cd ~/agents_reviewer && source venv/bin/activate && \
V6_CODEX_CRITIC=1 V6_CODEX_LOG_PATH=logs/codex_calls.jsonl python3 -c "
import asyncio
from src.config import Config
from src.agents.codex_critic import CodexCritic
from src.models import ComposedReport, ComposedSection, ContextAnalysis
cfg = Config()
report = ComposedReport(headline='27년 만의 PC 칩 RTX 스파크', deck='엔비디아 타이베이 공개',
  sections=[ComposedSection(heading='발표 요지', prose='베라 루빈 보드 한 장에 부품 130만 개가 들어간다')])
ctx = ContextAnalysis(event_name='NVIDIA GTC Taipei', date='2026-06-01',
  summary='젠슨 황 키노트', sources=['https://nvidianews.nvidia.com/'])
v = asyncio.run(CodexCritic(cfg).critique(report, ctx, publication_date='2026-06-01'))
print('status=', v.verdict_status, 'violations=', v.violation_count,
      'skipped=', v.skipped, 'reason=', v.skip_reason, 'latency_ms=', v.latency_ms)
for c in v.claims: print(' -', c.error_class, '|', c.location, '|', c.fix_instruction)
"
```

> 기대: codex 설치·인증 OK 면 `status=violations` + scope_misattribution(130만=랙) /
> unsourced_number(27년) 류 claim. 미설치·인증실패면 `skipped=True reason=codex_not_found`
> 등으로 *정상 degrade* (둘 다 spike 성공 — 경로가 작동함을 증명).

---

### Phase V6-2 — 결정적 사실 사전필터 가드 + 프롬프트 하드닝 ✅ (완료, 2026-06-03)

**일자**: 2026-06-03
**flag**: `V6_FACT_GUARDS` (default OFF), `V6_CODEX_PERSONA_PATH` (페르소나 훅)

**랜딩 산출물**
- `src/factcheck/deterministic_guards.py` — 5종 가드 + `run_fact_guards` 집계 (log-only).
- `CodexCritic` 검수자 페르소나 훅 (`persona=` / `V6_CODEX_PERSONA_PATH`).
- **검수자 페르소나 (GPT 협업 채택)**: `prompts/market_factcheck_desk_v6.md`(전체 기준서) +
  `prompts/codex_critic_persona.md`(런타임 단축본, config 기본값). 10개 검수 포커스 +
  회의적 기본 + 심각도 4단계→JSON severity 매핑. **출력 형식은 우리 `FactVerdict` JSON
  으로 오버라이드** (페르소나 원안의 산문형 데스크 보고서는 파서와 충돌해 미채택).
  파일 부재 시 graceful 빈값. 회귀: `test_codex_critic.py` 페르소나 4종(기본 로드/본문작성
  금지 정합/missing graceful/명시 빈값) 통과.

**T-1 검출 (`test_fact_discipline.py`) — 통과**

| 시나리오 | 가드 | bad 검출 | good 0-FP |
|----------|------|:--------:|:---------:|
| scope_misattribution_01 | ScopeBarewordGuard | ✅ | ✅ |
| unsourced_number_01 | UnsourcedNumberGuard | ✅ | ✅ |
| novelty_conflation_01 | NoveltyDeltaGuard (novelty_delta) | ✅ | ✅ |
| stale_sourcing_01 | NoveltyDeltaGuard (stale_relative_timepoint) | ✅ | ✅ |
| market_data_mismatch_01 | MarketDataSourceGuard | ✅ | ✅ |

- **결정적 검출률 5/5 = 100%** (DoD ≥90% 충족), good_prose FP 0.
- **Codex 라우팅 (결정적 비대상)**: unsourced_number_02(근거 산출 임계) / market_data_mismatch_02
  (원/달러 0.29% sub-tolerance) / event_conflation / attribution_as_fact / causal_overreach /
  metric_label_ambiguity / timepoint_overclaim(앵커 정확성) / list_truncation — 의미 판단
  영역이라 Phase 3 Codex critic 담당. 가드는 *명백한* 위반만 0-LLM 으로 거른다.
- `test_fact_discipline.py` 합계 통과 (스키마 6 + T-1 14 = 20).

**프롬프트 하드닝 (완료)**: composer `_FACT_DISCIPLINE_BLOCK`(`V6_FACT_PROMPT`,
`_compose_system_prompt()` flag-gating) + ContextAnalyst `_RECENCY_BLOCK`(`V6_RECENCY_BOUND`,
`_build_system_prompt()`). 회귀 `test_fact_prompt.py` 6종 — 둘 다 **flag OFF byte-equal**
(== v5.8.8 프롬프트) + ON 직교 주입(WRITE-AP-11/14~21 / 최신성 24~48h). 전체 V6 회귀 71 pass.

### Phase V6-3 — Bounded Codex critic 루프 ✅ (완료, VM e2e 수렴 2026-06-03)

**일자**: 2026-06-03
**flag**: `V6_CODEX_CRITIC` (default OFF — 루프 마스터)

**랜딩 산출물**
- `src/factcheck/critic_loop.py` — `CriticLoop`/`CriticLoopResult`/`apply_landing`/
  `NarrativeComposerReviser`. 루프 제어 0-LLM (위반 카운트), 재작성≤1·확인패스≤1.
- `NarrativeComposer.revise_for_facts` + `REVISE_SYSTEM_PROMPT` (텍스트-only → merge).
  `_call_cli`/`_call_api` `system_prompt` override (기본 None=byte-equal).
- orchestrator Phase 2.5 flag-gated 연결 (composer→ensure-hooks→**루프**→sanitize→render).

**T-3/T-4 (`test_codex_loop.py`, 모킹 critic+reviser) — 9종 통과**

| 테스트 | 검증 |
|--------|------|
| flag OFF passthrough | 원본 동일 객체 + critic 0콜 (byte-equal) |
| degrade(skipped) | 원본 보존 + 보완·확인 안 함 |
| clean 1차 | 무보완·무확인 (위반 0 결정적 종료) |
| 위반→보완→clean 확인 | revised=True, critic 2콜, 잔존 0 |
| unsourced 착지 | 확인패스 잔존 unsourced 인용구 결정적 drop |
| **bound** | 확인패스에 위반 남아도 재작성 1회·검수 2회 고정 |
| 보완 실패 | 원본 보존 + 확인패스는 진행 |
| 사전필터 합류 | guards on → pre_flags 가 codex 1차에 전달 |
| 사전필터 단독 | codex clean 이면 가드 신호만으론 재작성 안 함 |

전체 V6 회귀 **66 pass**. flag OFF byte-equal (orchestrator 블록 조건부 + call 시그니처 하위호환).

#### VM e2e — 실제 codex + Opus 루프 (2026-06-03, /tmp/v6spike, `V6_CODEX_CRITIC=1 V6_FACT_GUARDS=1`)

NVIDIA 표본(본문에 scope/unsourced/novelty 오류 + evidence 에 정답 provenance) 투입.
**실측 결과 — 위반 0 으로 수렴:**

```
skipped=False  revised=True  confirm=True
init_viol=4  residual=0  dropped=[]  pre_flags=2
[보완본] headline: "PC 칩 RTX 스파크 공개"  (← "27년 만의 PC 칩" 에서 27년 만 제거)
 발표 요지: "베라 루빈 NVL72 랙 전체에 약 130만 개 …  PC용 칩 RTX 스파크를 새로 내놨다.
            GR00T N1.7/N2 는 3월 GTC에서 공개된 내용으로 이번 타이베이 신규 공개 아님."
```

- **수렴 검증**: 결정적 가드 2건 선검출(pre_flags) + Codex 4건 검출(init_viol) →
  Opus 보완 1회 → Codex 확인패스 잔존 0 → drop 불필요. **재작성 1회·확인패스 1회 bound 준수.**
- **교정 정확도**: scope(보드→NVL72 랙 전체) / unsourced("27년 만" 제거) / novelty(GR00T
  "오늘 공개"→"3월 GTC, 신규 아님") 3종 모두 evidence 에 맞게 교정 (fact_discipline
  scope_misattribution_01 / unsourced_number_01 / novelty_conflation_01 과 동형).
- **V6 핵심 가설 실증**: 교차모델(GPT)이 Claude confabulation 검출 → Opus 보완 →
  bounded 루프 수렴. 전 과정 실제 모델.

> **후속 재실행 (AP-V6-13 반영, 2026-06-03)**: 1차 보완본이 "신규 공개 아님" 식 *정정
> 흔적/부정 박제* 를 남긴 것을 발견(독자 무가치) → `REVISE_SYSTEM_PROMPT` "★ 독자 우선"
> 블록 추가. 재실행 결과 GR00T 문장이 **"3월 GTC에서 선보인 GR00T를 이번 타이베이에서
> 다시 부각했다"** 로 *독자용 정보* 화 (해명조 제거). 단 `residual=1` — 보완이 헤드라인에
> "PC 칩 복귀" 라는 근거 없는 프레이밍을 새로 끌어들였고 **확인패스가 이를 검출**(확인패스
> 설계의 정당성 입증). bounded(재작성≤1) 라 잔존 1건은 2차 재작성 없이 발행. → 후속 개선
> 후보: ① 보완 시 *새 주장·프레이밍 도입 금지* 프롬프트 강화(예방) ② residual claim 텍스트
> 로깅(현재 카운트만) ③ 비-unsourced 잔존의 착지 정책(헤지 vs 발행).
>
> **완결성 보강 ①②③ 반영 (2026-06-03).** ① `REVISE_SYSTEM_PROMPT` 규칙 7 — 고치면서
> 새 주장·프레이밍('복귀/최초/직격탄/사실상') 도입 금지(예방). ② `CriticLoopResult.residual_summary`
> (잔존 claim 사람-읽기 요약) + orchestrator 로그 노출(가시성). ③ 정직한 착지 — drop 으로
> 해소 안 된 잔존(`unresolved_count`)이 남으면 "깨끗한 척" 발행 안 하고 `confidence_score`
> 를 정직 하향(−0.1/건, 0.3 floor). surgery 위험한 비-unsourced 잔존은 신호로만 남김.
> **완결성 = 0 보장이 아니라 예방+가시성+정직 착지+bounded.** 회귀 73 pass.
> **재실행 검증 (2026-06-03)**: 동일 표본 e2e 재실행 → `residual=0`(① 예방으로 "복귀"
> 미발생), `unresolved=0`, `conf=0.7` 유지(③ 깨끗한 케이스 무페널티). 보완본 헤드라인도
> "엔비디아 타이베이 공개, 베라 루빈과 RTX 스파크" 로 담백·정확. 설계가 깨끗(이번)/잔존(지난) 둘 다 처리 확인.

**→ Phase V6-3 DoD 충족** (NVIDIA 표본 위반 0 수렴 + 재작성≤1 + 확인패스≤1 + 모킹 9종).

**남은 것 (선택, 배포 단계)**: 전체 4층(검색·작성·가드·루프) + 실제 웹검색 + 발행까지의
풀 파이프라인 e2e — 봇으로 실제 보고서 1건 (프로덕션 영향) + degrade 경로(codex 미인증)
단일패스 확인. codex 2콜 + Opus 보완 1콜의 총 지연(온디맨드 UX) 측정.

#### 풀 파이프라인 e2e — 4층 + 실제 웹검색 (2026-06-03, 발행만 제외)

토픽 `엔비디아 FY2027 Q1 실적` 으로 ContextAnalyst(웹검색) → composer(`V6_FACT_PROMPT`)
→ guards → 루프 전 층 가동 (`V6_CODEX_CRITIC=1 V6_FACT_GUARDS=1 V6_FACT_PROMPT=1
V6_RECENCY_BOUND=1`):

```
[1] context: 8 sources (실제 웹검색)   [2] composer: 6 sections
[3] init_viol=0  residual=0  unresolved=0  dropped=[]  conf=0.72
```

- **핵심 — `init_viol=0`**: 작성단계 사실규율(②)이 제대로 먹어 codex 가 고칠 위반 0.
  "앞단이 잘 막으면 루프 할 일이 적다" 가설 실증 (합성 루프-only 테스트 init_viol=4 와 대비).
- **본문 내부정합 완벽**(검산): 752/816=92% / 컴퓨팅604+네트워킹148=752 / 74+18+8=100 /
  순이익583억→"87조(한국 매체 환산치)" *귀속* / 910억 가이던스 +12%. 모순 노출·헤지·
  전문용어 풀이 살아있음 = 구독자 품질.
- **회의적 캐비엇(중요)**: `init_viol=0`≠완벽. ① 헤드라인 "122조"(원) ↔ 본문 "816억 달러"
  통화 혼재를 codex 가 통과(페르소나 '혼재 통화' 체크 미작동). ② "블랙웰 300" 등 구체
  제품·수치는 *외부 교차검증 안 됨* — **Phase V6-5(codex 웹 verify) 필요성 입증**. ③ 실적
  발표는 숫자 명확한 *쉬운* 토픽 — 출처 충돌 속보에서 루프가 진짜 일하는 검증은 별도.

**→ V6 핵심 4층(검색·작성·가드·루프) 풀 파이프라인 실제 토픽 e2e 통과. 구독자 품질 보고서
생성 확인.** 남은 것: 발행(렌더+Cloudflare) 포함 봇 e2e + degrade 경로 + Phase 4/5/6/7/8.

---

### Phase V6-4 — Codex 미학 검수 (vision) ◐ (코드 랜딩, VM 비전 실연동 대기)

**일자**: 2026-06-03 · **flag**: `V6_CODEX_VISUAL` (default OFF)

**랜딩**: `CodexCritic.critique_visual`(차트 PNG `-i` → 미학 verdict) + `critique_report_visuals`
(capture_proofs 캡처 → 검수) + `_call_codex_cli`/`_build_cmd` 이미지 지원 + `_VISUAL_INSTRUCTIONS`
(가독성/잘림/패턴/축/데이터불일치/빈프레임) + orchestrator 발행 후 flag-gated 훅(log-only).
budget telemetry V6-aware(Opus 보완 1콜 cap 반영). T-5 모킹 6종(`test_codex_visual.py`) 통과,
전체 V6 91 pass. flag OFF byte-equal.

**남은 것 (VM)**: codex 비전이 *실제* 차트 PNG 를 검수하는지 실연동 1회(Phase 1 의 `-i` 플래그
존재 확인 → 실제 이미지 처리 검증). 미작동 시 미학은 V5(chart_critic/desk_editor) 유지. 자동수정
통합 여부는 측정 후(현재 log-only).

---

### Phase V6-5 — Codex 웹 verify (bounded) ◐ (코드 랜딩, VM 웹검색 실연동 대기)

**일자**: 2026-06-03 · **flag**: `V6_CODEX_WEBVERIFY` (default OFF)

**랜딩**: `critique()` webverify-aware — cmd 에 웹검색 인자(`codex_websearch_args`,
기본 `--enable web_search`) + 프롬프트 `=== 웹 verify (bounded ≤N) ===` 블록(근거 없는
사실만 ≤N 검색·URL 인용 강제·URL 못 대면 무시) + `_build_cmd`/`_call_codex_cli` webverify
파라미터 + `_coerce_verdict` cited_urls 집계. T-6 모킹 6종(`test_codex_webverify.py`),
전체 V6 96 pass. flag OFF byte-equal (ON 만 비결정 — 웹 변동).

**남은 것 (VM)**: codex `exec` 가 *실제* 웹검색을 수행하는지 + `--enable web_search` 정확한
형태(샌드박스/네트워크 정책 포함) 실연동 1회. 미작동 시 `codex_websearch_args` override 로
조정 or webverify 보류(graceful — flag OFF 면 무영향).

---

## §2. 효과·비용 지표 (T-10, 누적 — Phase 3 루프 가동 후 채움)

| 지표 | 값 | 측정일 |
|------|----|--------|
| fact-error rate (fixture 기준 발행본 잔존위반/보고서) | — (Phase 3 후) | — |
| 루프 평균 횟수 (재작성/확인패스) | — | — |
| Codex 호출수 · 한도소모 · 평균 지연 | 단건 검수 35.1s (gpt-5.5, e2e 1회) — 볼륨 한도 Phase 3 후 | 2026-06-03 |
| Codex FP율 (근거 없는 지적 비율) | — | — |
| 소프트가드 적중률 (Phase 6) | — | — |
