---
tier: 2
last_synced_with: v2.4.1
ssot_for:
  - "현재 에이전트 카탈로그 (mirror of src/agents/*)"
  - "보고서 블록 타입 카탈로그 (V3 후 src/models.py:BlockType 미러)"
  - "분석 렌즈 카탈로그 (V3 후 src/lenses/registry.py 미러)"
  - "보고서 archetype 카탈로그 (V3 후 src/archetypes/registry.py 미러)"
depends_on:
  - "src/agents/* (현재 SSOT)"
  - "src/models.py (V3 후 BlockType SSOT)"
  - "src/lenses/registry.py (V3 후 lens SSOT)"
  - "src/archetypes/registry.py (V3 후 archetype SSOT)"
last_review: 2026-04-26
---

# Catalogs — Agents · Lenses · Archetypes · Blocks

> 본 문서는 **카탈로그 미러**다. 정의는 코드에서만, 문서는 사람이 읽기 쉬운 형태로 동기화한 사본일 뿐이다.
> 카탈로그를 *정의*하지 않는다. 카탈로그는 코드 registry 가 SSOT.

---

## 1. Agents — 현재 (v2.4.x, V3 이전)

각 에이전트의 정의는 `src/agents/<name>.py` 에 있다. 본 표는 미러.

| # | 에이전트 | 파일 | 역할 (요약) |
|---|---------|------|-------------|
| 1 | 상황인식 분석관 | `src/agents/context_analyst.py` | ACT I: 팩트, 타임라인, 핵심 수치, 웹 검색 |
| 2 | 이해관계자 분석관 | `src/agents/player_analyst.py` | ACT II: 행위자 식별, 전략, 위험도 |
| 3 | 구조 및 상호작용 분석관 | `src/agents/dynamics_analyst.py` | ACT III: 게임이론, 비대칭, 전환점, 피드백 루프 |
| 4 | 연쇄반응 분석관 | `src/agents/chain_reaction_analyst.py` | ACT IV: 인과 사슬, 도미노, 와일드카드 |
| 5 | 향후 시나리오 분석관 | `src/agents/scenario_architect.py` | ACT V+VI: 시나리오, 감시 신호, 균형 분석 |
| 6 | 시각화 분석관 | `src/agents/visual_analyst.py` | SVG 관계도, Leaflet 지도, Canvas 차트 |
| 7 | 보고서 합성관 | `src/agents/report_synthesizer.py` | HTML/Markdown 생성, Cloudflare 업로드 |

기능 요구사항 매핑은 [GOAL.md](../GOAL.md) 의 REQ-AGT-001~007 참조.

---

## 2. Analysis Lenses — V3 후 도입 예정

V3 Step 5 에서 `src/lenses/` 디렉토리에 LensRunner ABC 와 6개 기본 렌즈가 추가된다. 도입 후 등록될 렌즈 풀:

| Lens ID | 의미 | 출처 모듈 |
|---------|------|-----------|
| (V3 Step 5 후 작성) | — | `src/lenses/registry.py` |

V3 적용 전까지 본 섹션은 비어 있다. 빈 섹션을 *임의로 채우지 않는다* (Anti-pattern 9).

---

## 3. Report Archetypes — V3 후 도입 예정

V3 Step 2 에서 보고서 archetype 다중화가 도입된다. 첫 archetype:

| Archetype ID | 설명 | 대상 사건 유형 |
|--------------|------|----------------|
| `six_act_theater` | 현재의 6막 극장 구조 (보존) | 인물극 중심 사건 |
| (추가 archetype은 V3 Step 2 후 등록) | — | — |

archetype registry 의 SSOT 는 `src/archetypes/registry.py` (V3 도입 후).

---

## 4. Block Types — V3 후 도입 예정

V3 Step 3 에서 17종 블록 타입이 도입된다. 등록 SSOT 는 `src/models.py:BlockType` (V3 후).

| Block ID | 카테고리 | 용도 |
|----------|----------|------|
| (V3 Step 3 후 작성) | — | — |

---

## 5. 카탈로그 갱신 절차

신규 항목을 코드 registry 에 추가했다면 본 문서도 동시에 갱신한다 ([CLAUDE.md](../CLAUDE.md) Change Propagation 매트릭스 참조).

- 신규 에이전트 → `src/agents/` 추가 시 §1 표 갱신
- 신규 lens → `src/lenses/registry.py` 등록 시 §2 표 갱신
- 신규 archetype → `src/archetypes/registry.py` 등록 시 §3 표 갱신
- 신규 block → `src/models.py:BlockType` 추가 시 §4 표 갱신

자동화 권장은 [DOCS_GOVERNANCE_V3.md §4.1](../DOCS_GOVERNANCE_V3.md) 참조.
