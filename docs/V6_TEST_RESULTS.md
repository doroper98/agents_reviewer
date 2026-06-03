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

1. ☐ codex CLI 설치 + ChatGPT headless 인증 유지 방식 확인 (`codex --version`, 인증 토큰 만료 주기).
2. ☐ `codex exec` 비대화형 JSON 출력 안정성 — 실제 호출 형태 확정 (subcommand/args).
   확정 결과를 `.env` 의 `V6_CODEX_SUBCOMMAND` / `V6_CODEX_EXTRA_ARGS` 에 반영.
3. ☐ Codex 호출 rate-limit 이 일일브리핑 + 온디맨드 빈도를 감당하는지 (한도·지연 측정).
4. ☐ 비전(이미지) 입력 지원 여부 — Phase V6-4(미학 검수) 가부 결정.
5. ☐ 실제 codex 1회 수동 호출 로그 (`logs/codex_calls.jsonl` 1줄 + stdout 샘플) 첨부.

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

## §2. 효과·비용 지표 (T-10, 누적 — Phase 3 루프 가동 후 채움)

| 지표 | 값 | 측정일 |
|------|----|--------|
| fact-error rate (fixture 기준 발행본 잔존위반/보고서) | — (Phase 3 후) | — |
| 루프 평균 횟수 (재작성/확인패스) | — | — |
| Codex 호출수 · 한도소모 · 평균 지연 | — (VM 실연동 후) | — |
| Codex FP율 (근거 없는 지적 비율) | — | — |
| 소프트가드 적중률 (Phase 6) | — | — |
