---
tier: 1
last_synced_with: v2.4.1
ssot_for:
  - "문서 거버넌스 규칙 (3-Tier, SSOT 매트릭스, 헤더 규약, Change Propagation)"
depends_on: []
last_review: 2026-04-26
---

# Agents Reviewer — Document Governance V3

> **Target:** `doroper98/agents_reviewer`
> **Companion document:** `REFACTOR_V3_PLAN.md`
> **Purpose:** 저장소 문서 체계 정비. 파편화·버전 불일치·SSOT 부재를 해소하여 V3 리팩토링 이후에도 문서가 코드와 동기화되게 함.
> **When to apply:** **V3 리팩토링 Step 1 이전**에 먼저 적용한다 (Step 0).

---

## 0. Why This Governance Exists

### 0.1 진단된 파편화 패턴

| # | 패턴 | 구체적 사례 |
|---|------|------------|
| 1 | SSOT 부재 | "7개 에이전트 표"가 README.md와 CLAUDE.md 양쪽에 중복 |
| 2 | 버전 단일점 없음 | `orchestrator.py:24` `VERSION="v2.4.0"`이 박혀있으나 어떤 문서에도 버전 명시 없음 |
| 3 | 문서 성격 분류 부재 | GOAL.md(frozen)·DEVLOG.md(living)·CLAUDE.md(중간)이 구분 표시 없이 같은 폴더 |
| 4 | 변경 전파 메커니즘 없음 | 코드 X 변경 시 갱신해야 할 문서 목록이 어디에도 없음 |
| 5 | 미분류 문서 | `overall_structure.md`(루트), `prototype_*.html`(루트) — 책무·위치 불명 |

### 0.2 결과

- 문서가 stale해지는 속도가 코드보다 빠르다
- "이 문서를 믿어야 하는가" 판단이 매번 필요하다
- 새 기여자(또는 코딩 에이전트)가 진입할 때 어느 문서부터 읽어야 할지 모른다
- V3 리팩토링이 끝나도 동일 패턴으로 또 파편이 생긴다

### 0.3 핵심 원칙

**한 사실은 한 곳에만 적는다. 다른 곳은 링크만 한다.**
이 단순한 규칙이 깨지지 않으면 파편화는 발생하지 않는다.

---

## 1. Three-Tier Document Hierarchy

### 1.1 계층 정의

| Tier | 성격 | 변경 빈도 | 갱신 트리거 |
|------|------|-----------|-------------|
| **Tier 1 — Constitution** | 거의 안 바뀜. 바뀌면 시스템 정체성이 바뀌는 결정 | 분기당 0~1회 | 메이저 방향 전환 시 |
| **Tier 2 — Architecture** | 릴리스마다 한 번 갱신. 코드 구조의 도식 | 릴리스당 1회 | 마이너 버전 릴리스 (vX.Y.0) |
| **Tier 3 — Operational** | 자주 변함. 일상 운영 기록 | 커밋마다 또는 사건마다 | 커밋·트러블슈팅·신규 기능 |

### 1.2 문서 배치 (V3 적용 후)

```
agents_reviewer/
├── README.md                      # Tier 1 — 진입점만, 슬림
├── GOAL.md                        # Tier 1 — 요구사항·성공 기준
├── CLAUDE.md                      # Tier 1 — AI 에이전트 행동 규칙
├── CHANGELOG.md                   # Tier 3 — 사용자 관점 릴리스 노트 (신규)
├── DEVLOG.md                      # Tier 3 — 개발자 관점 상세 로그
├── WORKFLOWS.md                   # Tier 3 — 실행 절차
├── REFACTOR_V3_PLAN.md            # Tier 2 — V3 리팩토링 명세 (한시적)
├── DOCS_GOVERNANCE_V3.md          # Tier 1 — 본 문서
│
├── docs/                          # docs_canonical에서 이름 단순화
│   ├── ARCHITECTURE.md            # Tier 2 — 시스템 구조 (overall_structure.md 흡수)
│   ├── DATA_MODELS.md             # Tier 2 — Pydantic 모델 도식 (신규)
│   ├── CATALOGS.md                # Tier 2 — archetype·lens·block 카탈로그 (신규)
│   ├── REPO_MAP.md                # Tier 3 — 파일·디렉토리 설명
│   ├── STYLEGUIDE.md              # Tier 1 — 코드 컨벤션
│   ├── TESTING.md                 # Tier 2 — 테스트 전략
│   └── references/                # 참조 자료 (prototype 파일 등)
│       ├── prototype_d3_map.html
│       └── prototype_gold_chart.html
│
├── samples/                       # 기존 유지
├── scripts/                       # 기존 유지
└── src/                           # 기존 유지
```

### 1.3 폐기·통합 대상

| 기존 위치 | 처리 | Step |
|-----------|------|------|
| `overall_structure.md` (루트) | `docs/ARCHITECTURE.md`로 흡수 후 삭제 | Step 0 |
| `prototype_d3_map.html` (루트) | `docs/references/`로 이동 | Step 0 |
| `prototype_gold_chart.html` (루트) | `docs/references/`로 이동 | Step 0 |
| `docs_canonical/` | `docs/`로 이름 변경 (canonical 표시는 헤더로 대체) | Step 0 |

---

## 2. Document Header Convention

모든 문서 최상단에 다음 YAML 헤더를 박는다.

```markdown
---
tier: 1                                       # 1·2·3
last_synced_with: v2.4.0                      # 코드 버전
ssot_for:                                     # 이 문서가 정본인 항목
  - "기능 요구사항 ID 체계"
  - "성공 기준"
depends_on:                                   # 갱신 시 참조해야 할 다른 문서
  - "src/orchestrator.py:VERSION"
last_review: 2026-04-26                       # 최종 검토 일자
---
```

**규칙:**
- `tier`는 필수.
- `last_synced_with`는 필수. 코드 버전을 따라간다.
- `ssot_for`는 이 문서가 SSOT인 항목 목록. 비어있어도 됨 (Tier 3 운영 문서).
- `depends_on`은 이 문서를 갱신할 때 참조해야 할 SSOT 위치.
- `last_review`는 최소 분기당 1회 갱신.

---

## 3. SSOT Matrix

각 사실 항목마다 **단 한 곳**만 정본이다. 다른 곳은 *링크 또는 참조*만 한다.

| 사실 항목 | SSOT 위치 | 동기화 대상 (Read-only Mirror) |
|-----------|-----------|--------------------------------|
| 버전 번호 | `src/orchestrator.py:VERSION` | README.md 헤더, CHANGELOG.md, 모든 문서의 `last_synced_with` |
| 에이전트·렌즈 카탈로그 | `src/lenses/registry.py` (V3 후) | `docs/CATALOGS.md` |
| Archetype 카탈로그 | `src/archetypes/registry.py` (V3 후) | `docs/CATALOGS.md` |
| 블록 타입 카탈로그 | `src/models.py:BlockType` | `docs/CATALOGS.md` |
| 데이터 모델 정의 | `src/models.py` | `docs/DATA_MODELS.md` (도식·관계만) |
| 기능 요구사항 (REQ-*) | `GOAL.md` | 다른 곳에서 ID로 참조만 (예: "REQ-AGT-001") |
| 비기능 요구사항 (NFR-*) | `GOAL.md` | 동일 |
| 향후 작업 (FUT-*) | `GOAL.md` | 동일 |
| 코드 컨벤션 | `docs/STYLEGUIDE.md` | CLAUDE.md에서 링크만 |
| AI 에이전트 행동 규칙 | `CLAUDE.md` | 다른 곳에서 링크만 |
| 분석 워크플로우 | `WORKFLOWS.md` | README에서 링크만 |
| 시스템 아키텍처 다이어그램 | `docs/ARCHITECTURE.md` | README에서 링크만 |
| 환경 변수 목록 | `.env.example` | README에서 링크만 |
| 테스트 케이스 | `docs/TESTING.md` + 코드 | DEVLOG에서 결과만 기록 |
| 릴리스 변경 사항 (사용자 관점) | `CHANGELOG.md` | README 최근 릴리스 섹션에서 요약 |
| 개발 상세 로그 | `DEVLOG.md` | 다른 곳에서 참조 안 함 |

### 3.1 SSOT 위반 사례 — 절대 금지

- ❌ README.md에 "에이전트 7개"의 표를 적고, CLAUDE.md에도 같은 표를 적기
- ❌ GOAL.md의 REQ-AGT-001 내용을 README.md에 풀어 쓰기
- ❌ 데이터 모델 필드를 docs/DATA_MODELS.md에서 *정의*하기 (정의는 src/models.py에서만)
- ❌ 버전 번호를 README.md 본문에 하드코딩

### 3.2 올바른 참조 패턴

```markdown
# 올바름
이해관계자 분석은 [REQ-AGT-002](GOAL.md#기능-요구사항)를 따른다.

# 올바름
현재 시스템 버전은 v3.0.0이다 (SSOT: `src/orchestrator.py:VERSION`).

# 올바름
사용 가능한 분석 렌즈 목록은 [docs/CATALOGS.md#analysis-lenses](docs/CATALOGS.md#analysis-lenses) 참조.

# 잘못됨 — 사실 중복
사용 가능한 분석 렌즈는 다음 6개다: geopolitical, financial_transmission, ...
```

---

## 4. Change Propagation Checklist

코드 변경 시 갱신해야 할 문서 매핑. CLAUDE.md에 박아 코딩 에이전트가 매번 확인하게 한다.

| 코드 변경 | 동시 갱신해야 할 문서 |
|-----------|----------------------|
| `src/orchestrator.py:VERSION` 증가 | README 헤더, CHANGELOG.md (신규 항목 추가), 영향받은 모든 문서의 `last_synced_with` |
| `src/models.py` 모델 추가/변경 | `docs/DATA_MODELS.md` 도식 갱신 |
| `src/agents/*` 신규 추가 | `docs/CATALOGS.md`, REPO_MAP.md |
| `src/lenses/*` 신규 추가 (V3 후) | `docs/CATALOGS.md` (lens 섹션) |
| `src/archetypes/*` 신규 추가 (V3 후) | `docs/CATALOGS.md` (archetype 섹션) |
| `src/templates/blocks/*` 신규 추가 (V3 후) | `docs/CATALOGS.md` (block 섹션) |
| `GOAL.md` REQ-* 추가/완료 | DEVLOG.md에 변경 기록 |
| 의존성 추가 (`requirements.txt`) | DEVLOG.md, README.md 환경 섹션 |
| 워크플로우 변경 | `WORKFLOWS.md`, `docs/ARCHITECTURE.md` |
| 인프라 변경 (Cloudflare/VM) | `docs/ARCHITECTURE.md`, DEVLOG.md |

### 4.1 자동화 권장 (V3 이후)

다음 자동화를 둔다.

- **Pre-commit hook**: `last_synced_with`가 현재 VERSION보다 낮으면 경고
- **CI 체크**: SSOT가 아닌 문서에 사실을 직접 기재한 경우 탐지 (정규식 기반)
- **자동 카탈로그 생성**: `src/lenses/registry.py` → `docs/CATALOGS.md`의 lens 섹션 자동 갱신

---

## 5. Document Lifecycle Rules

### 5.1 Tier 1 (Constitution) 변경 규칙

- 변경 시 반드시 DEVLOG.md에 *왜* 바꾸는지 명시
- GOAL.md의 REQ-* 삭제 금지. *deprecated 마킹*만 허용
- CLAUDE.md의 Execution Rules는 추가만 가능. 삭제는 메이저 버전 릴리스 시에만

### 5.2 Tier 2 (Architecture) 변경 규칙

- 매 릴리스(vX.Y.0)마다 검토 + `last_synced_with` 갱신
- 검토 시 SSOT와의 정합성 자동 검사
- 도식·다이어그램 변경 시 mermaid/draw.io 소스 동시 커밋

### 5.3 Tier 3 (Operational) 변경 규칙

- DEVLOG.md: append-only. 과거 항목 수정 금지. 정정은 새 항목 추가로
- CHANGELOG.md: 릴리스마다 추가. Keep a Changelog 형식 따름 (Added/Changed/Deprecated/Removed/Fixed/Security)
- WORKFLOWS.md: 신규 흐름 추가 또는 기존 흐름 수정. 삭제는 deprecated 마킹 후 1릴리스 보존

### 5.4 폐기 규칙

- 어떤 문서도 *바로 삭제*하지 않는다
- 폐기 단계: `[DEPRECATED]` 마킹 → 1릴리스 보존 → 삭제
- 삭제 시 git history에서 추적 가능하게 마지막 커밋 메시지에 명시: `docs: remove deprecated overall_structure.md (merged into docs/ARCHITECTURE.md at v2.6.0)`

---

## 6. README.md Slim-Down

현재 README.md는 진입점이면서 동시에 아키텍처 설명, 에이전트 카탈로그, 토큰 추정까지 담고 있다. **진입점 역할로만 슬림화**한다.

### 6.1 신규 README.md 구조 (목표)

```markdown
# Event Analysis Team — AI Agent System

[1줄 시스템 설명]

## Status
- Version: v3.0.0
- Tier 1 docs: [GOAL](GOAL.md) · [CLAUDE](CLAUDE.md) · [STYLEGUIDE](docs/STYLEGUIDE.md)
- Tier 2 docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_MODELS](docs/DATA_MODELS.md) · [CATALOGS](docs/CATALOGS.md)
- Tier 3 docs: [WORKFLOWS](WORKFLOWS.md) · [DEVLOG](DEVLOG.md) · [CHANGELOG](CHANGELOG.md)

## Quick Start
[3~5줄 명령어]

## What This Does
[2문단 이내 — 시스템 핵심]

## Architecture
[다이어그램 1개 + ARCHITECTURE.md 링크]

## Recent Changes
[CHANGELOG.md 최신 항목 5개 발췌 + 전체 링크]

## License
```

### 6.2 README에서 *제거*할 내용

다음은 SSOT가 아닌 곳에 있던 정보들이다. 제거하고 링크로 대체한다.

- 7개 에이전트 표 → CATALOGS.md로 이전
- 토큰 추정 표 → DEVLOG.md 또는 ARCHITECTURE.md
- 6막 극장 보고서 디자인 설명 → ARCHITECTURE.md
- 텔레그램 사용법 상세 → WORKFLOWS.md
- 프로젝트 구조 트리 → docs/REPO_MAP.md

---

## 7. CHANGELOG.md Introduction

신규 도입한다. DEVLOG.md와 책무가 다르다.

| 항목 | DEVLOG.md | CHANGELOG.md |
|------|-----------|--------------|
| 청자 | 개발자(자기 자신) | 사용자·통합자·미래의 자기 |
| 단위 | 커밋·세션·트러블슈팅 | 릴리스 (vX.Y.Z) |
| 톤 | 시간순 상세 로그 | 항목별 요약 |
| 형식 | 자유 | Keep a Changelog (Added/Changed/Deprecated/Removed/Fixed/Security) |
| 갱신 시점 | 매 커밋·세션 | 릴리스 직전 |

### 7.1 CHANGELOG.md 템플릿

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- ...

### Changed
- ...

### Deprecated
- ...

## [3.0.0] - 2026-XX-XX

### Added
- AnalysisStrategy Pydantic 모델 정식 승격
- 보고서 아키타입 11종 (six_act_theater, financial_transmission, ...)
- 분석 렌즈 풀 (LensRunner ABC + 6개 기본 렌즈)
- 블록 렌더링 시스템 (17종 블록 타입)
- Quality Gate 1/2 (Plan Sanity, Coverage Check)
- Synthesis Judge (모순 매트릭스, 반대 가설)
- Watchlist Registry (자동 신호 모니터링)
- Claim-Evidence 추적성 강제

### Changed
- 기존 Player/Dynamics/Chain/Scenario 에이전트 → 기본 렌즈로 재구성
- 6막 극장 보고서 → archetype="six_act_theater" 옵션으로 강등
- confidence_score(스칼라) → ConfidenceProfile(3축)

### Deprecated
- `_generate_analysis_strategy()`의 dict 반환 (AnalysisStrategy 객체로 대체)

### Removed
- (없음 — V3는 하위호환 유지)
```

---

## 8. Migration Steps (Step 0 — V3 리팩토링 이전)

본 거버넌스를 적용하는 작업 자체를 **Step 0**으로 둔다. V3 리팩토링 Step 1 이전에 완료한다.

### Step 0.1: 디렉토리·파일 정리

| 작업 | 명령 |
|------|------|
| `docs_canonical/` → `docs/` 이름 변경 | `git mv docs_canonical docs` |
| `overall_structure.md` 내용을 `docs/ARCHITECTURE.md`에 흡수 | 수동 머지 후 `git rm overall_structure.md` |
| `prototype_d3_map.html`, `prototype_gold_chart.html` → `docs/references/` 이동 | `mkdir -p docs/references && git mv prototype_*.html docs/references/` |

### Step 0.2: 거버넌스 헤더 추가

모든 마크다운 문서 상단에 YAML 헤더 추가. 우선순위:
1. README.md
2. GOAL.md
3. CLAUDE.md
4. WORKFLOWS.md
5. DEVLOG.md
6. docs/*.md

### Step 0.3: 신규 문서 생성

| 파일 | 내용 |
|------|------|
| `CHANGELOG.md` | Keep a Changelog 형식. v2.0.0~v2.4.0 과거 릴리스 정리 |
| `docs/CATALOGS.md` | 현재 시점의 7개 에이전트 + 보고서 디자인 (V3 후 archetype/lens/block 추가) |
| `docs/DATA_MODELS.md` | `src/models.py`의 모델 관계 도식 (mermaid) |

### Step 0.4: README.md 슬림화

Section 6.1 구조로 재작성. 제거된 정보는 적절한 SSOT로 이동.

### Step 0.5: SSOT 위반 정리

`grep`으로 사실 중복 탐지. 한 곳만 남기고 다른 곳은 링크로 대체.

```bash
# 예시: "7개 에이전트"가 여러 파일에 적힌 경우 탐지
grep -rn "7개 에이전트\|7 agents" --include="*.md"
```

### Step 0.6: CLAUDE.md에 Change Propagation 규칙 추가

Section 4의 매핑 표를 CLAUDE.md의 Execution Rules에 추가한다.

### Step 0 Acceptance Criteria

- [ ] 모든 마크다운 문서에 YAML 거버넌스 헤더 존재
- [ ] `overall_structure.md`, `prototype_*.html` 루트에서 제거
- [ ] `docs_canonical/` → `docs/` 이름 변경 완료
- [ ] CHANGELOG.md 생성 + 과거 릴리스 정리
- [ ] README.md가 60줄 이내로 슬림화 (현재 ~120줄)
- [ ] `grep`으로 SSOT 위반 (사실 중복) 5건 미만
- [ ] CLAUDE.md에 Change Propagation 매트릭스 추가
- [ ] DEVLOG.md에 Step 0 완료 기록

**커밋:** `v2.4.1: 문서 거버넌스 V3 적용 (3-tier 계층, SSOT 매트릭스, README 슬림화)`

---

## 9. Anti-Patterns (절대 하지 말 것)

1. ❌ **사실을 두 곳에 적기.** 정 두 곳에 있어야 한다면 한쪽은 링크로 대체.
2. ❌ **버전 번호 하드코딩.** 항상 SSOT 참조.
3. ❌ **거버넌스 헤더 없는 신규 문서 작성.**
4. ❌ **DEVLOG.md 과거 항목 수정.** Append-only.
5. ❌ **GOAL.md REQ-* 삭제.** Deprecated 마킹만.
6. ❌ **`docs/` 외 위치에 신규 마크다운 추가.** 루트 마크다운은 Tier 1·Tier 3만.
7. ❌ **Tier 1 문서를 코딩 에이전트가 임의 변경.** Tier 1은 사람이 결정.
8. ❌ **CHANGELOG.md를 자유 양식으로 작성.** Keep a Changelog 엄격 준수.
9. ❌ **`docs/CATALOGS.md`에 카탈로그를 *정의*하기.** 정의는 코드 registry에만, 문서는 미러.
10. ❌ **거버넌스 헤더의 `last_synced_with`를 갱신하지 않은 채 본문만 수정.**

---

## 10. Validation

Step 0 완료 후 다음 검증 통과해야 한다.

```bash
# 1. 모든 마크다운 헤더 존재
for f in $(find . -name "*.md" -not -path "./node_modules/*" -not -path "./.git/*"); do
  if ! head -10 "$f" | grep -q "^tier:"; then
    echo "MISSING HEADER: $f"
  fi
done

# 2. 폐기 대상 파일 부재
test ! -f overall_structure.md
test ! -f prototype_d3_map.html
test ! -f prototype_gold_chart.html
test -d docs/references

# 3. CHANGELOG.md 존재
test -f CHANGELOG.md

# 4. README 슬림 확인
test $(wc -l < README.md) -lt 80
```

---

## 11. Relationship to V3 Refactor Plan

본 거버넌스와 `REFACTOR_V3_PLAN.md`의 관계:

```
[Step 0] DOCS_GOVERNANCE_V3 적용  ← 본 문서
   │
   ▼
[Step 1] AnalysisStrategy 모델 승격
   │
   ▼
[Step 2] 보고서 아키타입 다중화
   │   └─ 신규 archetype 추가 시 docs/CATALOGS.md 갱신 (Section 4 규칙)
   ▼
[Step 3] 블록 렌더링 시스템
   │   └─ 신규 block 추가 시 docs/CATALOGS.md 갱신
   ▼
[Step 4] Quality Gate + Claim-Evidence
   │   └─ 신규 모델 추가 시 docs/DATA_MODELS.md 갱신
   ▼
[Step 5] Lens Pool + Watchlist
       └─ 신규 lens 추가 시 docs/CATALOGS.md 갱신
       └─ 모든 문서 헤더 last_synced_with: v3.0.0으로 갱신
       └─ CHANGELOG.md v3.0.0 항목 작성
```

V3 리팩토링은 본 거버넌스 위에서 동작한다. Step 0를 건너뛰고 Step 1부터 진행하면 V3 종료 시점에 문서 파편이 더 심해진다.

---

## 12. Long-Term Discipline

V3 종료 후에도 거버넌스를 유지하기 위해.

### 12.1 분기 검토 (Quarterly Review)

- 모든 Tier 1 문서의 `last_review` 갱신
- SSOT 위반 자동 탐지 결과 검토
- Stale 문서 식별 (`last_synced_with` < 현재 버전 - 2)

### 12.2 신규 기여자(또는 신규 코딩 에이전트 세션) 온보딩 순서

1. README.md 읽기 (5분)
2. CLAUDE.md 읽기 (5분)
3. DOCS_GOVERNANCE_V3.md 읽기 (본 문서, 10분)
4. GOAL.md의 현재 REQ-* 검토 (10분)
5. docs/ARCHITECTURE.md (15분)
6. 작업 시작

총 45분 안에 진입할 수 있어야 한다. 그 이상 걸리면 진입점 문서(README, CLAUDE)가 비대하다는 신호.

### 12.3 거버넌스 자체의 SSOT

본 문서(`DOCS_GOVERNANCE_V3.md`)가 거버넌스의 SSOT다. 거버넌스 변경은 메이저 버전 릴리스(vX.0.0)에서만 가능하다.

---

**End of Document Governance V3**

이 문서는 `agents_reviewer` 저장소 루트에 `DOCS_GOVERNANCE_V3.md`로 커밋되어야 하며,
`REFACTOR_V3_PLAN.md`보다 먼저 적용되어야 한다.
