---
tier: 3
last_synced_with: v2.9.0
ssot_for:
  - "사용자 관점 릴리스 노트 (versioned changes)"
depends_on:
  - "src/orchestrator.py:VERSION"
  - "DEVLOG.md (개발 상세 로그)"
last_review: 2026-04-26
---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom `vMAJOR.MINOR.PATCH` scheme tracked in `src/orchestrator.py:VERSION`.

상세한 개발 로그·트러블슈팅·인프라 메모는 [DEVLOG.md](DEVLOG.md) 참조.

---

## [Unreleased]

(다음 릴리스 항목 대기 중 — v2.9.5 Watchlist + v3.0.0 페르소나 deprecation.)

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
