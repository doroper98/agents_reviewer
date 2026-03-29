# WORKFLOWS — Event Analysis Team

## 분석 실행 워크플로우

```
[사용자] 텔레그램으로 분석 명령 (일반 메시지)
    ↓
[Orchestrator] 명령 수신 → 파이프라인 시작
    ↓
Phase 1: [상황인식 분석관] 팩트 수집, 타임라인, 핵심 수치 (웹 검색)
    ↓
Phase 2: [이해관계자 분석관] 행위자, 전략, 위험도
         → [구조/상호작용 분석관] 게임이론, 비대칭, 전환점
    ↓
Phase 3: [연쇄반응 분석관] 인과 사슬, 도미노 효과
         → [향후 시나리오 분석관] 4개 시나리오 + 감시 신호
    ↓
Phase 3.5: [시각화 분석관] SVG 관계도, Leaflet 지도, Canvas 차트
    ↓
Phase 4: [보고서 합성관] Executive Summary 생성
         → Jinja2 HTML 렌더링 (valentino-boop 6막 구조)
         → Cloudflare Pages 배포 (wrangler CLI)
    ↓
[사용자] 텔레그램 수신:
         - 에이전트별 실시간 상태 메시지
         - 코드블록 텍스트 보고서
         - HTML 파일 + Cloudflare 공유 링크
```

## 간단 질답 워크플로우

```
[사용자] 텔레그램으로 "? 질문 내용"
    ↓
[Orchestrator] ? 접두어 감지 → 단일 Claude 호출
    ↓
[사용자] 텔레그램으로 간단 답변 수신
```

## 개발 워크플로우

```
1. 요구사항 확인 (GOAL.md)
2. 아키텍처 참조 (docs_canonical/ARCHITECTURE.md)
3. 코드 구현 (type hints 필수, Pydantic 모델 사용)
4. 컴파일 검증: python -m py_compile src/*.py
5. 수동 테스트 (텔레그램 분석 요청)
6. DEVLOG.md 기록
7. 커밋 (v{VER}: {변경 요약}) + 푸시
```

## 배포 워크플로우

```
1. Oracle Cloud VM SSH 접속
2. git pull origin main
3. source venv/bin/activate
4. pip install -r requirements.txt (의존성 변경 시)
5. python -m src.main (봇 재시작)
```
