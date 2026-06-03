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

### Phase V6-2 — 결정적 사실 사전필터 가드 ◐ (가드 랜딩, 프롬프트 하드닝 대기)

**일자**: 2026-06-03
**flag**: `V6_FACT_GUARDS` (default OFF), `V6_CODEX_PERSONA_PATH` (페르소나 훅)

**랜딩 산출물**
- `src/factcheck/deterministic_guards.py` — 5종 가드 + `run_fact_guards` 집계 (log-only).
- `CodexCritic` 검수자 페르소나 훅 (`persona=` / `V6_CODEX_PERSONA_PATH`, default 빈값=byte-equal).

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

**남은 것**: composer `SYSTEM_PROMPT` `=== 사실 규율 (V6) ===` 블록(byte-equal 위해 flag-gating
필요) + ContextAnalyst 일일브리핑 최신성 제한(24~48h, `stale_sourcing` 근본 차단).

---

## §2. 효과·비용 지표 (T-10, 누적 — Phase 3 루프 가동 후 채움)

| 지표 | 값 | 측정일 |
|------|----|--------|
| fact-error rate (fixture 기준 발행본 잔존위반/보고서) | — (Phase 3 후) | — |
| 루프 평균 횟수 (재작성/확인패스) | — | — |
| Codex 호출수 · 한도소모 · 평균 지연 | 단건 검수 35.1s (gpt-5.5, e2e 1회) — 볼륨 한도 Phase 3 후 | 2026-06-03 |
| Codex FP율 (근거 없는 지적 비율) | — | — |
| 소프트가드 적중률 (Phase 6) | — | — |
