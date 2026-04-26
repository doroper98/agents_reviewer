---
tier: 2
last_synced_with: v2.4.1
ssot_for:
  - "Pydantic 모델 관계 도식 (필드 정의는 미러 아님)"
depends_on:
  - "src/models.py (필드 정의의 SSOT)"
last_review: 2026-04-26
---

# Data Models — Pydantic Schema Map

> **이 문서는 도식이다. 필드 정의는 `src/models.py` 가 SSOT.**
> 새 필드를 *정의*하지 않는다. 코드에 추가한 후 본 문서의 도식만 갱신한다 (Anti-pattern 9 회피).

---

## 1. 모델 관계도

```
                    AnalysisRequest
                         │
                         ▼
                  Orchestrator pipeline
                         │
        ┌──────┬──────┬──┴───┬───────┬──────────┐
        ▼      ▼      ▼      ▼       ▼          ▼
   Context  Player Dynamics Chain  Scenario  Visual
   Analysis Analysis Analysis Reaction Analysis Analysis
        │      │      │      │       │          │
        └──────┴──────┴──┬───┴───────┴──────────┘
                         ▼
                  FullAnalysisResult
                         │
                         ▼
                ReportSynthesizer (HTML/Markdown)
```

각 분석 모델은 `FullAnalysisResult` 의 optional 필드. `NarrativePlan` 은 보고서 합성 단계에서 동적 생성됨.

---

## 2. 모델 목록 (현재 v2.4.1)

| 모델 | 책무 | 정의 위치 |
|------|------|-----------|
| `AnalysisRequest` | 사용자 요청 (텔레그램 메시지 → 모델) | `src/models.py` |
| `ContextAnalysis` | ACT I 결과 (팩트·타임라인·수치) | `src/models.py` |
| `PlayerAnalysis` | ACT II 결과 (행위자·동맹·power_dynamics) | `src/models.py` |
| `DynamicsAnalysis` | ACT III 결과 (비대칭·전환점·피드백 루프·반대 가설) | `src/models.py` |
| `ChainReactionAnalysis` | ACT IV 결과 (인과 사슬·차단점·와일드카드) | `src/models.py` |
| `ScenarioAnalysis` | ACT V+VI 결과 (시나리오·감시 신호·무효화 조건) | `src/models.py` |
| `VisualAnalysis` | 시각 요소 (SVG·Leaflet·Canvas) | `src/models.py` |
| `NarrativeSection` | 보고서의 단일 섹션 사양 | `src/models.py` |
| `NarrativePlan` | 섹션 순서·테마 (Claude 생성) | `src/models.py` |
| `FullAnalysisResult` | 모든 분석 결과 + 메타데이터 | `src/models.py` |

각 모델의 **현재 필드 목록**은 `src/models.py` 를 직접 읽는다 — 본 문서에 필드 사본을 두면 SSOT 위반이 된다.

---

## 3. 핵심 필드 의미 (분석 산출물 위주)

필드 *정의* 가 아니라, 필드의 *목적*을 사람의 언어로 풀어둔 가이드.

### 3.1 ContextAnalysis
- `timeline`: 날짜/사건/영향 트리오. 보고서 ACT I 의 타임라인 카드로 렌더.
- `key_figures`: label / value / context 트리오. 핵심 수치 카드.
- `background`: 배경 단락 (다단락 가능, `structured` 필터 처리).
- `glossary`: 용어 풀이. 보고서 말미.

### 3.2 PlayerAnalysis
- `players`: 각 항목은 name / role_tag / risk_level / position / strategy / vulnerability / timeline_pressure 키를 가진 dict.
- `alliances`: group(이름 배열) / nature(동맹/대립/협력 등).
- `power_dynamics`: 전체 권력 역학 요약 (서술형).

### 3.3 DynamicsAnalysis
- `framework`: 사용한 분석 시각의 조합 (예: "게임이론 + 경로 의존성 + 행동경제학").
- `asymmetries`: type / description / advantage_to.
- `feedback_loops`: type(강화|균형) / description.
- `tipping_points`: condition / timeline / consequence.
- `counter_view`: 반대 가설 또는 대안 해석.
- `cognitive_biases`: 분석 시 경계할 인지 편향 목록.

### 3.4 ChainReactionAnalysis
- `chain`: step / title / description / affected / time_horizon / effect_type / reversible / severity.
- `feedback_loops`: 사슬 안에서 자기강화·억제 구조.
- `break_points`: at_step / condition (사슬을 끊을 수 있는 지점).
- `wildcards`: 예측 어려운 흑조 사건.

### 3.5 ScenarioAnalysis
- `scenarios`: id / name / tag / probability / description / preconditions / trigger / impact_by_player.
- `watch_signals`: signal / description / indicates / icon.
- `invalidation_conditions`: 분석 자체를 다시 해야 하는 조건.
- `summary`: 균형 분석 본문 (4단락: 핵심 판단 / 상하방 비대칭 / 변수 민감도 / 한계와 유보).

### 3.6 NarrativePlan
- `report_theme`: 핵심 서사 한 문장.
- `sections`: NarrativeSection 배열. 각 섹션은 act_label / title / data_source / narrative_bridge / subsections 보유.

---

## 4. 모델 변경 시 동시 갱신해야 할 곳

[CLAUDE.md](../CLAUDE.md) Change Propagation 매트릭스의 "src/models.py 변경" 행 참조. 핵심:

1. `src/models.py` 정의 갱신 (코드 SSOT)
2. 본 문서 §2 `모델 목록` 표 + §3 의미 가이드 갱신
3. 영향받는 에이전트의 system prompt JSON 스키마 갱신
4. 보고서 템플릿 (`src/templates/report.html`) 의 렌더링 부분 갱신
5. `DEVLOG.md` 에 변경 기록

V3 후에는 추가로:
- `docs/CATALOGS.md` 의 BlockType 표 갱신 (BlockType 변경 시)

---

## 5. Out of scope

- 필드의 정확한 타입·기본값 → `src/models.py` 직접 읽기
- 모델 인스턴스의 직렬화 형식 → Pydantic 의 `model_dump()` / `model_validate_json()` 동작 (코드)
- 에이전트가 어떤 시스템 프롬프트로 어떤 모델을 채우는지 → `src/agents/<name>.py` 의 SYSTEM_PROMPT
