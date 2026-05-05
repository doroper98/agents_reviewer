---
tier: 3
last_synced_with: v4.5.7
ssot_for:
  - "분석 실행 워크플로우 (텔레그램 명령 → 보고서)"
  - "개발 워크플로우"
  - "배포 워크플로우"
depends_on:
  - "src/orchestrator.py (파이프라인 단계)"
  - "docs/ARCHITECTURE.md"
last_review: 2026-05-05
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

## 보고서 부분 수정 워크플로우 (v4.4.1+)

이미 생성된 보고서를 LLM 호출 *없이* 부분 수정·재렌더·재배포. 차트 1개가
깨졌다거나 빈 차트가 박혔을 때 전체 재분석 (Opus 4.7 호출 ~$2-3) 대신 사용.

전제: v4.4.1 이후 생성된 보고서. ReportSynthesizer 가 HTML + ComposedReport
JSON 을 함께 저장 (`reports/analysis_<timestamp>.json`).

### 사용 예

```bash
cd ~/agents_reviewer
source venv/bin/activate

# 1) 빈 bubble 차트 제거 (3번째 섹션의 1번째 차트, 0-based)
python scripts/patch_report.py 20260502_154823 --remove-chart 2:0

# 2) 섹션 통째 제거 (5번째 섹션, 0-based)
python scripts/patch_report.py 20260502_154823 --remove-section 4

# 3) JSON 직접 편집 (vim 으로 본문/차트 데이터 수정)
EDITOR=vim python scripts/patch_report.py 20260502_154823 --edit

# 4) 수정 없이 재렌더만 (charts.js 갱신 후 정적 자산 동기화)
python scripts/patch_report.py 20260502_154823 --rerender-only

# 5) 로컬만 갱신 (Cloudflare 배포 X)
python scripts/patch_report.py 20260502_154823 --remove-chart 0:0 --no-deploy
```

### 효과

| | 전체 재분석 | patch_report.py |
|---|---|---|
| LLM 호출 | Opus 4.7 × 2 | 0 |
| 비용 | ~$2-3 | 0 |
| 시간 | ~1분 | ~5초 |
| URL | *새* timestamp 로 변경 | 그대로 (사용자 받은 링크 유효) |

### 주의

- v4.4.1 이전 보고서는 JSON 저장 없음 → patch 불가. 재분석 필요.
- `--edit` 시 JSON schema 깨면 검증 실패 (`FullAnalysisResult.model_validate`) — 백업 후 편집 권장.
- Cloudflare 배포는 wrangler 가 reports/ 통째 업로드 — 다른 보고서들도 함께 갱신됨 (정적 자산 새 charts.js / charts.css 동기화).
