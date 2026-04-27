---
tier: 3
last_synced_with: v3.0.0
ssot_for:
  - "분석 실행 워크플로우 (텔레그램 명령 → 보고서)"
  - "개발 워크플로우"
  - "배포 워크플로우"
depends_on:
  - "src/orchestrator.py (파이프라인 단계)"
  - "docs/ARCHITECTURE.md"
last_review: 2026-04-26
---

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
         → Jinja2 HTML 렌더링 (6막 극장 6막 구조)
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
2. 아키텍처 참조 (docs/ARCHITECTURE.md)
3. 코드 구현 (type hints 필수, Pydantic 모델 사용)
4. 컴파일 검증: python -m py_compile src/*.py
5. 수동 테스트 (텔레그램 분석 요청)
6. DEVLOG.md 기록
7. 커밋 (v{VER}: {변경 요약}) + 푸시
```

## 감시 신호 (Watchlist) 워크플로우 — V3 Step 5-B (v2.9.5)

```
[ScenarioArchitect] 분석 종료 시 watch_signals (dict[]) 산출
    ↓
[Orchestrator] convert_watch_signals() → list[WatchSignal] (Pydantic)
    ↓
[WatchlistRegistry] SQLite (reports/watchlist.db) 영구 저장 (Anti-pattern #11)
    ↓
─── 봇 프로세스 안에서 1시간 주기로 ───
[run_monitor_loop] tick_once() → list_active() 순회
    ↓
   deadline 도래 시 → mark_fired(direction='ambiguous')
    ↓
[notify_signal_fired] → app.bot.send_message(chat_id=parent_chat_id, ...)
    ↓
🔔 텔레그램 알림 (spec template):
   사건: {parent_report_title}
   신호: {description} → {direction}
   원 보고서: {parent_report_url}
   권장 후속: {follow_up_action}
```

### 수동 발화 (사용자 트리거)

```
[사용자] /fire <signal_id> [direction]
    ↓
[telegram_bot] 권한 검증 (parent_chat_id 일치)
    ↓
[WatchlistRegistry.mark_fired()] direction 갱신 + fired_at 기록
    ↓
[notify_signal_fired] 본 채팅에 발화 알림 송신
```

### 감시 신호 목록 조회

```
[사용자] /watchlist
    ↓
[telegram_bot] WatchlistRegistry.list_active_for_chat(chat_id) → 목록 응답
```

봇 재시작 시 별도 복구 호출 불필요 — SQLite 영속성 덕분에 새 `WatchlistRegistry(db_path)` 인스턴스가 active 신호 상태 자연 복구.

## 배포 워크플로우

```
1. Oracle Cloud VM SSH 접속
2. git pull origin main
3. source venv/bin/activate
4. pip install -r requirements.txt (의존성 변경 시)
5. python -m src.main (봇 재시작)
```
