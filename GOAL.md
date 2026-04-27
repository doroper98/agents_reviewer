---
tier: 1
last_synced_with: v2.9.5
ssot_for:
  - "기능 요구사항 ID 체계 (REQ-*)"
  - "비기능 요구사항 (NFR-*)"
  - "성공 기준 (SC-*)"
  - "향후 작업 (FUT-*)"
depends_on: []
last_review: 2026-04-26
---

# Event Analysis Team — Project Goal

## 1. Objective (목적)
텔레그램 메시지로 사건/이벤트 분석을 지시하면, 7개 AI 에이전트 팀이 자동으로
다각도 분석을 수행하고 6막 극장 스타일 HTML 보고서로 결과를 반환하는 시스템.

## 2. Requirements (요구사항)

### 기능 요구사항 (Functional)

| ID | 분류 | 설명 | 우선순위 | 상태 |
|----|------|------|----------|------|
| REQ-TG-001 | Telegram | 텔레그램 봇으로 분석 명령 수신 | P0 | ✅ |
| REQ-TG-002 | Telegram | 분석 진행 상태 실시간 메시지 | P1 | ✅ |
| REQ-TG-003 | Telegram | HTML 파일 + Cloudflare 공유 링크 전송 | P0 | ✅ |
| REQ-TG-004 | Telegram | `?` 접두어 간단 질답 기능 | P1 | ✅ |
| REQ-ORC-001 | Orchestrator | 4단계 파이프라인 순차 실행 | P0 | ✅ |
| REQ-AGT-001 | Agent | 상황인식 분석관 — 팩트, 타임라인, 웹 검색 | P0 | ✅ |
| REQ-AGT-002 | Agent | 이해관계자 분석관 — 행위자, 전략, 위험도 | P0 | ✅ |
| REQ-AGT-003 | Agent | 구조/상호작용 분석관 — 게임이론, 전환점 | P0 | ✅ |
| REQ-AGT-004 | Agent | 연쇄반응 분석관 — 인과 사슬, 도미노 효과 | P0 | ✅ |
| REQ-AGT-005 | Agent | 향후 시나리오 분석관 — 4개 시나리오 + 감시 신호 | P0 | ✅ |
| REQ-AGT-006 | Agent | 시각화 분석관 — SVG 관계도, Leaflet 지도, Canvas 차트 | P0 | ✅ |
| REQ-AGT-007 | Agent | 보고서 합성관 — HTML 생성, Cloudflare 배포 | P0 | ✅ |
| REQ-RPT-001 | Report | 6막 극장 6막 극장 구조 테마 | P0 | ✅ |
| REQ-RPT-002 | Report | SVG/Canvas 시각화 (Plotly 제거) | P0 | ✅ |
| REQ-RPT-003 | Report | Executive Summary 자동 생성 | P0 | ✅ |
| REQ-RPT-004 | Report | 용어 정의(glossary) 포함 | P1 | ✅ |
| REQ-RPT-005 | Report | 모바일 반응형 | P1 | ✅ |
| REQ-V3-001 | Strategy | AnalysisStrategy Pydantic 모델 정식 승격 (dict 폐기, user_intent/core_questions/recommended_lenses 신설) | P0 | ✅ |
| REQ-V3-002 | Archetype | 보고서 아키타입 다중화 (six_act_theater 강등 + financial_transmission, tech_decomposition 추가; registry 패턴) | P0 | ✅ |
| REQ-V3-003 | Block | 보고서 블록 렌더링 시스템 (AnalysisBlock + 17종 BlockType + report_block.html 디스패처; 매크로 1:1 결합 해소) | P0 | ✅ |
| REQ-V3-004 | Quality | Quality Gate 1/2 (Plan Sanity + Coverage Check); 실패 시 최대 2회 재시도 후 부분-분석 알림 | P0 | ✅ |
| REQ-V3-005 | Traceability | Claim-Evidence 추적성 (evidence_ids ≥1 Pydantic 강제) + ConfidenceProfile 3축 분해 + Synthesis Judge 모순 노출 | P0 | ✅ |
| REQ-V3-006 | Lens Pool | LensRunner ABC + 8종 lens (geopolitical / financial_transmission / tech_architecture / policy_implementation / accident_causality / market_structure / red_team / pre_mortem) + 사건당 4개 동시 실행 한도 (Anti-pattern #6) | P0 | ✅ |
| REQ-V3-006a | Archetype Extension | 신규 archetype 3종 (geopolitical_strategic / accident_forensic / policy_implementation) — 사진 매트릭스 6 케이스 모두 라우팅 | P0 | ✅ |
| REQ-V3-007 | Watchlist | WatchSignal Pydantic 모델 + SQLite 영구 저장 + 봇 재시작 복구 + 봇 프로세스 내 asyncio monitor (1시간 주기 deadline 자동 발화) + `/watchlist`·`/fire` 명령 (Anti-pattern #11) | P0 | ✅ |

### 비기능 요구사항 (Non-Functional)

| ID | 설명 | 상태 |
|----|------|------|
| NFR-001 | 전체 분석 완료 (순차 실행 기준) | ✅ |
| NFR-002 | API 키 환경변수 관리 (.env) | ✅ |
| NFR-003 | Max 플랜 CLI 모드 (추가 비용 없음) | ✅ |
| NFR-004 | Oracle Cloud 무료 VM 운영 | ✅ |
| NFR-005 | Cloudflare Pages 무료 호스팅 | ✅ |

## 3. Success Criteria (성공 기준)

| SC | 설명 | 검증 방법 | 상태 |
|----|------|-----------|------|
| SC-01 | 텔레그램 메시지로 분석 시작 가능 | 수동 테스트 | ✅ |
| SC-02 | 7개 에이전트 순차 실행 완료 | 로그 확인 | ✅ |
| SC-03 | 6막 극장 HTML 보고서 정상 생성 | 브라우저 확인 | ✅ |
| SC-04 | 6막 구조 분석 내용 포함 | 내용 확인 | ✅ |
| SC-05 | SVG/Canvas 시각화 정상 렌더링 | 브라우저 확인 | ✅ |
| SC-06 | Cloudflare 배포 + 공유 링크 동작 | URL 접속 확인 | ✅ |
| SC-07 | `?` 간단 질답 동작 | 수동 테스트 | ✅ |

## 4. Completed Phases

### Phase 1: Core Infrastructure ✅
- 프로젝트 구조 수립, Pydantic 모델 정의, 에이전트 기본 클래스

### Phase 2: Pipeline & Integration ✅
- 오케스트레이터 파이프라인, 텔레그램 봇 연동, HTML 템플릿

### Phase 3: Refinement ✅
- 9→7 에이전트 재구성, 6막 극장 스타일, CLI 모드 전환
- SVG 직접 생성, Canvas 차트, Leaflet 지도
- 음슴체 프롬프트, 용어 정의, 모바일 반응형

## 5. Future Improvements (향후 개선)

| ID | 설명 | 우선순위 |
|----|------|----------|
| FUT-001 | Mac Mini 이전 시 병렬 실행 복원 (lens 4개 동시 호출 → 분석 시간 단축) | P2 |
| FUT-002 | 분석 중 사용자 추가 요청 반영 (중간 피드백) | P2 |
| FUT-003 | 분석 대기열 (여러 분석 동시 요청) | P3 |
| FUT-004 | Figma MCP를 활용한 고급 시각화 | P3 |
| FUT-005 | 보고서 에필로그 (예측 검증 스코어카드) | P3 |
