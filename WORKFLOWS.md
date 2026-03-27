# WORKFLOWS — Event Analysis Team

## 분석 실행 워크플로우

```
[사용자] 텔레그램으로 분석 명령
    ↓
[Orchestrator] 명령 파싱 → 분석 유형 결정 → 태스크 분해
    ↓
[Event Identifier] 사건 정의 → 5W1H → 소스 검증
    ↓
[병렬 실행] Macro + Geopolitical + Micro + Investment + History/Ethics
    ↓
[Devil's Advocate] 전체 분석 감사 → PASS/REVISE/REJECT
    ↓  (REVISE → 해당 에이전트 재분석)
[Report Synthesizer] HTML 보고서 생성
    ↓
[사용자] 텔레그램으로 보고서 수신
```

## 개발 워크플로우

```
1. 요구사항 확인 (GOAL.md)
2. 코드 구현
3. CLI Gate: python -m py_compile src/*.py
4. 수동 검증
5. DEVLOG 기록
6. 커밋 + 푸시
```
