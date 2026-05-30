---
tier: 1
last_synced_with: v5.6.9
ssot_for:
  - "VM (Oracle Ubuntu) 표준 재배포 절차 (회귀 가드 포함)"
  - "VM 운영 회귀 (VM-AP-N) 카탈로그 — append-only"
depends_on:
  - "src/orchestrator.py:VERSION (재배포 후 일치 확인 대상)"
  - "requirements.txt (의존성 변경 감지)"
last_review: 2026-05-30
---

# VM Deploy Playbook — 재배포 회귀 방지 SSOT

VM (Oracle Cloud Ubuntu) 에서 봇을 재배포하고 운영할 때 **유일한** 권위 문서.

> **Claude 행동 규칙**: 사용자에게 VM 재배포 명령어를 줄 때, **반드시 본 문서를
> 먼저 읽고 §1 표준 절차의 *모든* 회귀 가드를 포함한 명령어를 제공**한다. 단순
> 4단계 `pkill / nohup` 만 제공하면 §2 의 VM-AP 회귀가 재발한다. CLAUDE.md 의
> VM 배포 SOP 섹션은 본 playbook 의 §1 을 참조한다.

---

## §1 표준 재배포 절차 (회귀 가드 내장)

VM 의 `~/agents_reviewer` 에서 그대로 복붙. **§2 VM-AP-1~6 모든 가드 포함**.
idempotent — 봇이 떠있든 안 떠있든 같은 결과.

```bash
cd ~/agents_reviewer

# ─── Stage 1: pull 전 working tree 정리 (VM-AP-3 가드) ───
# 로컬 잔재 (이전 commit 에서 삭제된 파일이 VM 에 남음) 가 pull 을 막는다.
DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ]; then
  echo "⚠️ 로컬 수정사항 발견:"
  echo "$DIRTY"
  echo "→ 잔재 파일이면 rm, 의도적 수정이면 stash 후 재실행."
  echo "  (자주 발생: 이전에 삭제된 스크립트의 VM 잔재 — rm 안전)"
  exit 1
fi

# ─── Stage 2: pull + 의존성 변경 감지 (VM-AP-6 가드) ───
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  # requirements 변경 감지 → pip install 안내
  if git diff --name-only "$LOCAL..$REMOTE" | grep -qE '^requirements(-.*)?\.txt$'; then
    echo "⚠️ requirements 변경 감지 — pip install 필요"
    NEED_PIP=1
  fi
  git pull
  if [ -n "${NEED_PIP:-}" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
  fi
else
  echo "✓ 이미 최신 ($LOCAL)"
fi

# ─── Stage 3: 코드 버전 확인 (VM-AP-4 가드 — 재기동 누락 차단) ───
echo "코드 버전: $(grep '^VERSION = ' src/orchestrator.py)"

# ─── Stage 4: 옛 봇 graceful + force 종료 (VM-AP-1 가드) ───
# pkill SIGTERM 후 종료를 *기다린다*. graceful shutdown 은 텔레그램 polling
# unwind 때문에 5~15초 걸린다. sleep 2 후 즉시 새 봇 띄우면 두 봇이 동시에
# polling → "Conflict: terminated by other getUpdates request" 에러로 한쪽 죽음.
OLD=$(pgrep -f 'python.*src\.main' || true)
if [ -n "$OLD" ]; then
  echo "기존 봇 PID: $OLD — SIGTERM 송신"
  pkill -f 'python.*src\.main'
  for i in $(seq 1 15); do
    sleep 1
    REM=$(pgrep -f 'python.*src\.main' || true)
    if [ -z "$REM" ]; then
      echo "✓ 옛 봇 정상 종료 (${i}초 소요)"
      break
    fi
  done
  REM=$(pgrep -f 'python.*src\.main' || true)
  if [ -n "$REM" ]; then
    echo "⚠️ graceful shutdown 15초 초과 — SIGKILL (PID: $REM)"
    kill -9 $REM
    sleep 1
  fi
fi

# ─── Stage 5: 옛 bot.log 보존 + 새 봇 시작 (VM-AP-5 가드) ───
# nohup 의 ``> bot.log`` 가 truncate 모드라 두 봇이 동시에 떠있을 때 같은 파일에
# 쓰며 진단을 혼선시킨다. 새 봇 띄우기 전 옛 로그 1건 백업.
if [ -f bot.log ]; then
  mv bot.log "bot.log.$(date +%Y%m%d_%H%M%S)"
fi
source venv/bin/activate
nohup python -m src.main > bot.log 2>&1 &
disown

# ─── Stage 6: 가동 확인 (VM-AP-4 강화 — 버전·인스턴스·에러) ───
sleep 4
N=$(pgrep -f 'python.*src\.main' | wc -l)
if [ "$N" -ne 1 ]; then
  echo "⚠️ 봇 인스턴스 수: $N (1이어야 정상)"
  ps aux | grep 'src.main' | grep -v grep
fi
echo "─── bot.log 가동 신호 ───"
grep -E 'Starting Event Analysis Team bot|Application started|Conflict|ERROR' bot.log | head
echo "─── 확인 포인트 ───"
echo "  ① 'Starting Event Analysis Team bot — vX.Y.Z' 가 코드 버전과 일치"
echo "  ② [DIRTY] 표시 없어야 (working tree clean)"
echo "  ③ 'Conflict' / 'ERROR' 라인 없어야 (옛 봇과 polling 충돌 안 났는지)"
```

복붙 가능한 한 묶음으로 유지. 한 줄씩 끊지 말 것 — 사용자가 5단계만 실행하고
6단계 누락하는 회귀가 VM-AP-4 의 본질.

---

## §2 VM 운영 회귀 카탈로그 (VM-AP-N)

append-only. 새 회귀 발견 시 §4 의 등록 절차로 추가.

### VM-AP-1 — pkill 후 graceful shutdown 대기 부족 (2026-05-30 발생)

**증상**: `pkill -f "src.main"` 보낸 직후 `sleep 2` 만 하고 새 봇을 띄움. 옛 봇이
graceful shutdown (telegram polling unwind) 에 5~15초 걸리므로 새 봇 시작 시점에
*아직 살아있음*. 두 봇이 동시에 같은 토큰으로 `getUpdates` 호출 → 텔레그램이
"Conflict: terminated by other getUpdates request" 에러로 한쪽을 죽임.

**관찰된 흔적**:
- `ps aux | grep "src.main"` 출력에 두 PID 동시에 보임
- `bot.log` 에 옛 봇의 `Application is stopping` + 새 봇의 `Market briefing loop
  starting` 이 1초 차이로 섞임

**Fix**: §1 Stage 4 — `pkill` 후 최대 15초 polling 으로 죽음 대기, 안 죽으면 SIGKILL.

### VM-AP-2 — 새 실행 스크립트가 git 에 100644 (실행 불가) 로 들어감 (2026-05-30)

**증상**: 컨테이너 환경 (Claude Code on Web) 에서 `core.fileMode false` 인 상태로
새 실행 스크립트를 `git add` 하면, 로컬 +x 권한과 무관하게 git index 에 100644
모드로 저장됨. VM 에서 pull 받으면 실행 권한 없어 `./script` 가 "Permission denied".
사용자가 `chmod +x` 하면 이번엔 git 이 modified 로 인식해 후속 pull 충돌(VM-AP-3).

**관찰된 흔적**:
- `git ls-files --stage <script>` 가 `100644` (실행 가능은 `100755`)
- VM 에서 `./script` 실행 시 "Permission denied" 또는 그냥 무반응

**Fix**: **새 실행 스크립트를 만들지 않는다** (이번 사례). 진행 진단/모니터 같은
도구는 명령어 sequence 를 본 playbook §3 에 텍스트로 박아두고 사용자가 복붙.

> ★ 부득이하게 만들어야 하면: `git add <script>` 직후 `git update-index --chmod=+x <script>`
> 실행 + commit 전에 `git ls-files --stage <script>` 가 100755 인지 *반드시* 확인.
> 이 단계는 commit-msg hook 으로 강제하기 어려우니 PR 체크리스트와 본 playbook
> 으로 인지 부담을 진다.

### VM-AP-3 — 삭제된 파일의 VM 잔재로 git pull 충돌 (2026-05-30)

**증상**: 이전 commit 에서 git rm 으로 삭제된 파일이 VM 의 working tree 에 (사용자
의 chmod / 로컬 편집으로) 수정된 채 남아있어, 새 pull 시 "Your local changes to
the following files would be overwritten by merge" 에러로 pull 중단. 봇은 옛 버전
유지 (VM-AP-4 트리거).

**관찰된 흔적**: pull 출력에 "Please commit your changes or stash them" + `Aborting`.

**Fix**: §1 Stage 1 — pull 전 `git status --porcelain` 검사 + 잔재 파일이면 rm,
의도적 수정이면 stash. 잔재 식별 가이드: "git log --all -- <file>" 로 commit 이력
보고, 삭제된 파일(`D <file>`)이면 안전하게 rm.

### VM-AP-4 — 봇 옛 버전 가동 중인데 코드 갱신 후 재기동 누락 / 미확인 (2026-05-30 2회 발생)

**증상**: `git pull` 로 v5.6.8/v5.6.9 코드가 들어왔지만 봇 프로세스는 여전히
v5.6.7 의 이미지로 도는 중. 사용자에게 "재배포 완료" 로 보이지만 실제 동작은 옛
코드 — 픽스가 적용되지 않은 상태로 회귀가 계속 보고됨.

**관찰된 흔적**:
- `bot.log` 의 `Starting Event Analysis Team bot — vX.Y.Z` 가 코드의 VERSION 과 불일치
- `Starting` 라인에 `[DIRTY: uncommitted changes]` 표시 (working tree 가 옛 commit 기준)
- `/status` 텔레그램 응답이 옛 버전

**Fix**: §1 Stage 3 (pull 후 코드 버전 print) + Stage 6 (bot.log 의 Starting 라인이
코드 버전과 일치하는지 명시 확인). Claude 가 사용자에게 답변할 때 "재배포 후 첫
세 줄 결과 (코드 VERSION / 봇 인스턴스 수 / bot.log Starting 라인) 를 붙여달라"
고 *명시적으로* 요청.

### VM-AP-5 — 두 봇이 같은 bot.log 에 동시 출력 → 진단 혼선 (잠재, 2026-05-30 부분 관찰)

**증상**: VM-AP-1 발생 시 옛 봇과 새 봇이 같은 bot.log file descriptor 에 동시
출력. `tail` 해도 어느 봇의 로그인지 구분 안 되고, 옛 봇 종료 메시지와 새 봇 시작
메시지가 1초 단위로 섞임.

**Fix**: §1 Stage 5 — 새 nohup 시작 전 `mv bot.log bot.log.YYYYMMDD_HHMMSS` 로
옛 로그 보존. 새 봇은 새 파일에 깨끗하게 적고, 옛 로그는 진단/포렌식 용으로 남음.

### VM-AP-6 — requirements 변경 후 pip install 누락 → import 에러로 봇 죽음 (잠재)

**증상**: 새 의존성이 requirements.txt 에 추가됐는데 `git pull` 후 `pip install`
안 하고 봇 재기동 → import 에러 → 즉시 죽음. bot.log 첫 줄에 ModuleNotFoundError.

**Fix**: §1 Stage 2 — `git diff --name-only LOCAL..REMOTE` 로 requirements 변경 감지
시 `pip install -r requirements.txt` 자동 실행 (venv 활성화 포함).

---

## §3 진단 명령어

### 봇 현재 상태 한눈에

```bash
# 봇 인스턴스 수 (1이어야 정상, 0=죽음, 2+=VM-AP-1)
pgrep -fc 'python.*src\.main'

# 봇이 어느 버전으로 떠있나
grep -E 'Starting Event Analysis Team bot' bot.log | tail -1

# 코드 버전 (떠있는 봇과 일치해야 — 불일치는 VM-AP-4)
grep '^VERSION = ' src/orchestrator.py
```

### 보고서 생성 진행 여부 (이전 bot-if-working 대체)

```bash
# 마지막 시작 마커 vs 완료 마커
tail -500 bot.log | grep -E '상황 분석관|편집장|Starting CLI|✅ 분석 완료' | tail -5
```

시작 마커가 완료 마커보다 뒤면 진행 중, 그 반대면 유휴.

### composer 회귀 추적 (head-loss / timeout / parse 실패)

```bash
tail -500 bot.log | grep -E '(narrative_composer|unified_composer|composer 호출|orchestrator\] _ensure)'
```

핵심 라인:
- `using salvaged partial (N sections)` — v5.6.6 부분 살림 작동
- `recovered truncated JSON` — 절단 복구 작동
- `head-loss 복구: 1-섹션` — v5.6.8 head-loss 복구 작동
- `composer failed; emitting minimal fallback` — 모든 복구 실패 → 0% fallback

---

## §4 신규 회귀 발견 시 등록 절차

CHART-AP / WRITE-AP 와 동일 패턴 (append-only):

1. **번호 부여**: 다음 VM-AP-N (현재 6 까지 사용). 같은 패턴은 기존 항목에 사례 추가.
2. **§2 에 새 항목 append** — 증상 / 관찰된 흔적 / Fix 3 섹션.
3. **§1 표준 절차에 가드 추가** — Fix 가 명령어 단계인 경우.
4. **CLAUDE.md 의 본 playbook 참조 라인이 있으면** `last_synced_with` 갱신.
5. CHANGELOG 의 해당 ops/버전 entry 에 reference.

기존 항목 *수정 금지*. 정정이 필요하면 새 항목으로 (이력 보존).

---

## §5 본 playbook 갱신 규칙

- **append-only** §2: 발견된 회귀는 새 항목으로. 기존 수정 금지.
- §1 의 표준 절차는 §2 와 *동기화* 유지 — 새 VM-AP 의 Fix 가 명령어이면 §1 에 가드 반영.
- 헤더의 `last_synced_with` 는 §1 갱신 시 함께 올림.
- Claude 가 VM 명령어를 줄 때 본 playbook 의 §1 을 *그대로* 사용. 단축/임의 변형 금지.
