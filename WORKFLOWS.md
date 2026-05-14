---
tier: 3
last_synced_with: v5.1.2
ssot_for:
  - "분석 실행 워크플로우 (텔레그램 명령 → 보고서)"
  - "개발 워크플로우"
  - "배포 워크플로우"
  - "일일 자동 브리핑 워크플로우 (v5.1.0)"
depends_on:
  - "src/orchestrator.py (파이프라인 단계)"
  - "src/scheduler/* (v5.1.0)"
  - "docs/ARCHITECTURE.md"
last_review: 2026-05-14
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

## 일일 자동 브리핑 워크플로우 — v5.1.0

별도 cron 없이, 봇 프로세스 안 asyncio task 가 매일 지정 시각 (기본 06:00 KST) 에
깨어나 구독한 모든 텔레그램 채팅에 "간밤 산업·지정학·정치·전쟁" 심층 보고서를 자동 송신.

### 사용자 사이드 (1회 셋업)

```
[사용자] 텔레그램에서 /briefing_on
    ↓
[telegram_bot] BriefingSubscriberRegistry.subscribe(chat_id, mode='deep')
    ↓
[봇] "✅ 일일 브리핑 구독 완료 — 매일 06:00 (Asia/Seoul)" 응답
    ↓ (이후 자동)
[매일 06:00 KST] 보고서 자동 수신
```

### 시스템 사이드 (자동 트리거)

```
[봇 시작] _on_app_post_init
    ↓
asyncio.create_task(run_daily_briefing_loop)
    ↓
─── loop ───
[scheduler] _next_trigger() 로 다음 06:00 KST 계산 → asyncio.sleep
    ↓
[scheduler] briefing_runs 테이블에 run_date PK insert (같은 일자 중복 시 skip)
    ↓
[scheduler] BriefingSubscriberRegistry.list_all() 순회
    ↓
   for chat_id, mode in subscribers:
       ├── send_text_fn(chat_id, "🌅 일일 브리핑 시작...")
       ├── Orchestrator.run_analysis(briefing_prompt, chat_id,
       │                              status_callback, mode='deep')
       │      ├── ContextAnalyst (Opus 4.7, 웹 검색) → 간밤 보도 수집
       │      └── NarrativeComposer (Opus 4.7, deep → 5~7 섹션 + 모순 명시)
       │            └── Cloudflare Pages 배포 (wrangler)
       ├── 텍스트 보고서 (chunked) → chat_id 송신
       ├── 용어 정의 (chunked) → chat_id 송신
       └── 보고서 URL + Markdown URL → chat_id 송신
    ↓
[scheduler] briefing_runs.finish_run(run_date, succeeded, failed)
    ↓
─── 다음 루프 (다음 06:00 KST 까지 sleep) ───
```

### 환경변수 게이트

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `DAILY_BRIEFING_ENABLED` | `false` | task 는 항상 살아 있고 구독은 받지만, 트리거 시각에 실제 분석 실행 여부 게이트. false 시 스킵 + 로그만. |
| `DAILY_BRIEFING_TIME` | `06:00` | 24h "HH:MM", `DAILY_BRIEFING_TZ` 기준 |
| `DAILY_BRIEFING_TZ` | `Asia/Seoul` | IANA tz (예: `UTC`, `America/New_York`, `Asia/Tokyo`) |

### 텔레그램 명령

| 명령 | 동작 |
|------|------|
| `/briefing_on` | 이 채팅을 일일 브리핑 수신처로 등록 (deep mode 고정) |
| `/briefing_off` | 구독 해제 |
| `/briefing_status` | 구독 상태 + 스케줄러 활성 여부 + 시각/타임존 표시 |

봇 재시작 시 별도 복구 호출 불필요 — `BriefingSubscriberRegistry` SQLite 영속성으로
구독자 자연 복구. 같은 날 봇 재시작 후 트리거 시각이 이미 지난 경우, `briefing_runs.run_date`
PRIMARY KEY 가 중복 트리거를 막음.

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
