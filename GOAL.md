# Event Analysis Team — Project Goal

## 1. Objective (목적)
텔레그램 메시지로 사건/이벤트 분석을 지시하면, AI 에이전트 팀이 자동으로
다각도 분석을 수행하고 비주얼 보고서로 결과를 반환하는 시스템 구축.

## 2. Requirements (요구사항)

### 기능 요구사항 (Functional)

| ID | 분류 | 설명 | 우선순위 |
|----|------|------|----------|
| REQ-TG-001 | Telegram | 텔레그램 봇으로 분석 명령 수신 | P0 |
| REQ-TG-002 | Telegram | 분석 진행 상태 실시간 알림 | P1 |
| REQ-TG-003 | Telegram | 최종 보고서 HTML 링크 전송 | P0 |
| REQ-ORC-001 | Orchestrator | 명령 파싱 및 분석 유형 자동 결정 | P0 |
| REQ-ORC-002 | Orchestrator | 5단계 파이프라인 순차/병렬 실행 | P0 |
| REQ-AGT-001 | Agent | Event Identifier — 사건 5W1H 프로필 생성 | P0 |
| REQ-AGT-002 | Agent | Macro Analyst — 거시경제 파급력 분석 | P0 |
| REQ-AGT-003 | Agent | Geopolitical Analyst — 지정학 파급력 분석 | P0 |
| REQ-AGT-004 | Agent | Micro Analyst — 미시경제 파급력 분석 | P0 |
| REQ-AGT-005 | Agent | Investment Analyst — 투자 영향 분석 | P0 |
| REQ-AGT-006 | Agent | Historian & Ethics — 역사/윤리 맥락 분석 | P0 |
| REQ-AGT-007 | Agent | Devil's Advocate — 비판적 검증/감사 | P0 |
| REQ-AGT-008 | Agent | Report Synthesizer — HTML 보고서 생성 | P0 |
| REQ-RPT-001 | Report | YK_ soft-brutalism 테마 적용 | P0 |
| REQ-RPT-002 | Report | 4-Quadrant 영향도 시각화 | P1 |
| REQ-RPT-003 | Report | Executive Summary 자동 생성 | P0 |

### 비기능 요구사항 (Non-Functional)

| ID | 설명 |
|----|------|
| NFR-001 | 전체 분석 완료 ≤ 3분 |
| NFR-002 | 병렬 분석으로 처리 시간 최적화 |
| NFR-003 | API 키 환경변수 관리 (.env) |

## 3. Success Criteria (성공 기준)

| SC | 설명 | 검증 방법 | REQ |
|----|------|-----------|-----|
| SC-01 | 텔레그램 메시지로 분석 시작 가능 | 수동 테스트 | REQ-TG-001 |
| SC-02 | 9개 에이전트 순차/병렬 실행 완료 | 로그 확인 | REQ-ORC-002 |
| SC-03 | HTML 보고서 정상 생성 | 브라우저 확인 | REQ-RPT-001 |
| SC-04 | 보고서에 4대 분석 + 역사/윤리 포함 | 내용 확인 | REQ-AGT-002~006 |
| SC-05 | Devil's Advocate 감사 결과 포함 | 내용 확인 | REQ-AGT-007 |

## 4. Phases

### Phase 1: Core Infrastructure
- S1.1: 프로젝트 구조 수립 → SC-01
- S1.2: 데이터 모델 정의 → SC-02
- S1.3: 에이전트 기본 클래스 + 9개 에이전트 정의 → SC-04, SC-05

### Phase 2: Pipeline & Integration
- S2.1: 오케스트레이터 파이프라인 구현 → SC-02
- S2.2: 텔레그램 봇 연동 → SC-01
- S2.3: HTML 보고서 템플릿 → SC-03
