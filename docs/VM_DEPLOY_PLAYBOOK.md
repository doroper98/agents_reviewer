---
tier: 1
last_synced_with: v8.7.6
ssot_for:
  - "VM (Oracle Ubuntu) 표준 재배포 절차 (회귀 가드 포함)"
  - "VM 운영 회귀 (VM-AP-N) 카탈로그 — append-only"
depends_on:
  - "src/orchestrator.py:VERSION (재배포 후 일치 확인 대상)"
  - "requirements.txt (의존성 변경 감지)"
last_review: 2026-06-01
---

# VM Deploy Playbook — 재배포 회귀 방지 SSOT

VM (Oracle Cloud Ubuntu) 에서 봇을 재배포하고 운영할 때 **유일한** 권위 문서.

> **Claude 행동 규칙**: 사용자에게 VM 재배포 명령어를 줄 때, **반드시 본 문서를
> 먼저 읽고 §1 표준 절차의 *모든* 회귀 가드를 포함한 명령어를 제공**한다. 단순
> 4단계 `pkill / nohup` 만 제공하면 §2 의 VM-AP 회귀가 재발한다. CLAUDE.md 의
> VM 배포 SOP 섹션은 본 playbook 의 §1 을 참조한다.

---

## §1 표준 재배포 절차 (회귀 가드 내장)

> **🔴 현 VM 은 봇을 systemd 서비스 `agents-reviewer.service` 로 관리한다 (2026-07-11
> 확정).** 그래서 아래 `pkill`+`nohup` 블록은 **legacy** 다 — 쓰면 systemd 인스턴스와
> *중복* 으로 떠서 텔레그램 Conflict + OOM 프리즈를 유발한다(VM-AP-12, 실제 사고). **표준
> 재배포는:**
> ```bash
> cd ~/agents_reviewer && git checkout main && git pull
> sudo systemctl restart agents-reviewer.service
> systemctl status agents-reviewer.service --no-pager | head -5
> journalctl -u agents-reviewer.service -n 20 --no-pager | grep -E 'Starting|Conflict|ERROR'
> ```
> requirements 변경 시엔 pull 후 `source venv/bin/activate && pip install -r requirements.txt`
> 를 restart 앞에 넣는다. 아래 nohup 블록은 **systemd 서비스가 없는 환경에서만**.
> 정본 규칙: CLAUDE.md '🔴 봇 재시작·운영 SSOT'.

### §1.0 systemd 표준 재배포 — 가드 내장 완전본 (현 VM 은 이걸 쓴다)

> v8.5.13 신설. 상단 4줄 systemd 블록은 *최소본* 이라 VM-AP-3/9/10(reports 잔재)·
> VM-AP-11(feature 브랜치 잔류)·VM-AP-4(옛 버전 가동) 가드가 빠져 있었고, 아래 긴
> 블록은 systemd 이전 nohup legacy 다. 둘 사이가 비어 있어 매번 손으로 조립하던 것을
> 정식 블록으로 고정한다. **여는 `(` 부터 닫는 `)` 까지 통째로** 붙여넣으면 1회 실행.

```bash
(
  cd ~/agents_reviewer || exit 1

  # ─── Stage 1: reports/ 미러 산출물 잔재 자동 폐기 (VM-AP-9 / VM-AP-10) ───
  if git status --porcelain --untracked-files=no | grep -q '^ M reports/'; then
    echo "ⓘ reports/ 로컬 수정 폐기 (origin+Cloudflare 가 정본)"
    git checkout -- reports/
  fi
  DIRTY=$(git status --porcelain --untracked-files=no)
  if [ -n "$DIRTY" ]; then
    echo "⚠️ 로컬 tracked 수정사항 — pull 차단 위험:"; echo "$DIRTY"
    echo "→ 잔재면 git checkout -- <file>, 의도적이면 stash 후 재실행."; exit 1
  fi

  # ─── Stage 2: main 확인 + pull + 의존성 감지 (VM-AP-11 / VM-AP-6) ───
  BR=$(git rev-parse --abbrev-ref HEAD)
  if [ "$BR" != "main" ]; then
    echo "⚠️ 현재 브랜치 $BR ≠ main — 전환 (VM-AP-11)"; git checkout main || exit 1
  fi
  git fetch origin main
  LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse origin/main)
  if [ "$LOCAL" != "$REMOTE" ]; then
    if git diff --name-only "$LOCAL..$REMOTE" | grep -qE '^requirements(-.*)?\.txt$'; then
      NEED_PIP=1; echo "⚠️ requirements 변경 감지"
    fi
    git pull || exit 1
    if [ -n "${NEED_PIP:-}" ]; then source venv/bin/activate && pip install -r requirements.txt; fi
  else
    echo "✓ 이미 최신 ($LOCAL)"
  fi

  # ─── Stage 3: 코드 버전 확인 (VM-AP-4) ───
  echo "코드 버전: $(grep '^VERSION = ' src/orchestrator.py)"

  # ─── Stage 3.5: config 로드 프리플라이트 (VM-AP-13) ───
  # .env 의 미지원 키·형식 오류는 재시작 후에야 status=1 무한 루프로 드러난다.
  # 살아있는 봇을 내리기 *전에* 새 코드 + 현재 .env 조합이 뜨는지 먼저 확인한다.
  if ! venv/bin/python -c 'from src.config import Config; Config()' 2>/tmp/cfgcheck.err; then
    echo "❌ config 로드 실패 — 재시작 중단 (봇은 옛 버전으로 계속 가동 중, VM-AP-13)"
    cat /tmp/cfgcheck.err; exit 1
  fi
  echo "✓ config 로드 OK"

  # ─── Stage 3.6: Claude CLI 로그인·모델 프리플라이트 (v8.7.3, VM-AP-14) ───
  # 구독 로그인이 만료됐거나 새 모델이 계정에서 안 열리면, 재시작해도 보고서가 전부
  # 실패한다. 내리기 전에 편집장 모델로 ping 1회. 저장소 CLAUDE.md 를 읽지 않게 /tmp 에서.
  MODEL=$(venv/bin/python -c 'from src.agents.narrative_composer import NarrativeComposer as N; print(N.COMPOSER_MODEL)')
  PING=$(cd /tmp && timeout 120 claude -p "ping" --model "$MODEL" --output-format json 2>&1)
  if ! echo "$PING" | grep -qE '"is_error": ?false'; then
    echo "❌ Claude CLI 점검 실패 ($MODEL) — 재시작 중단 (봇은 옛 버전으로 계속 가동 중)"
    echo "$PING" | head -c 600; echo
    echo "→ 'OAuth'·'401' 이면 claude 실행 후 /login. 모델 오류면 위 출력을 확인."; exit 1
  fi
  echo "✓ Claude CLI OK ($MODEL)"
  # Codex 는 없어도 보고서가 나간다(검수만 건너뜀) — 중단하지 않고 상태만 보여 준다.
  # 'Logged in' 표시만으론 부족하다(VM-AP-16) — 봇이 쓸 모델로 실제로 한 번 물어본다.
  CXM=$(venv/bin/python -c 'from src.config import Config; print(Config().codex_model)')
  CX=$(cd /tmp && echo "Reply with the single word pong." | timeout 90 codex exec --skip-git-repo-check --sandbox read-only -m "$CXM" 2>&1)
  if echo "$CX" | grep -qiE '^pong[.!]?$'; then
    echo "✓ codex OK ($CXM · $(codex --version 2>&1))"
  else
    CXE=$(echo "$CX" | grep '^ERROR' | tail -1); [ -z "$CXE" ] && CXE=$(echo "$CX" | tail -1)
    echo "⚠️ codex 검수 불가 (보고서는 나가고 검수만 건너뜀): $(echo "$CXE" | head -c 300)"
    echo "   → §3 'Codex 검수 점검' 표 참고"
  fi

  # ─── Stage 4: systemd 재시작 (nohup 금지 — VM-AP-12 중복 기동 OOM) ───
  sudo systemctl restart agents-reviewer.service
  sleep 5

  # ─── Stage 5: 가동 확인 (VM-AP-4 강화 — 버전·인스턴스·충돌) ───
  systemctl status agents-reviewer.service --no-pager | head -5
  N=$(pgrep -f 'python.*src\.main' | wc -l)
  [ "$N" -ne 1 ] && { echo "⚠️ 봇 인스턴스 $N 개 (1이어야 정상)"; pgrep -af 'python.*src\.main'; }
  journalctl -u agents-reviewer.service -n 40 --no-pager \
    | grep -E 'Starting Event Analysis Team bot|Conflict|ERROR' | head
  echo "─── 확인 포인트 ───"
  echo "  ① 'Starting Event Analysis Team bot — vX.Y.Z' 가 위 코드 버전과 일치"
  echo "  ② 'Conflict' / 'ERROR' 없음"
)
```

---

VM 의 `~/agents_reviewer` 에서 그대로 복붙. **§2 VM-AP-1~8 모든 가드 포함**.
idempotent — 봇이 떠있든 안 떠있든 같은 결과.
**(systemd 환경에서는 위 systemctl 블록을 쓰고 아래는 참고용으로만 둔다.)**

> **★ paste-safe 설계 (VM-AP-8, VM-AP-7 개정).** 전체를 **즉시 실행 서브셸
> `( … )`** 로 감싼다. **별도 호출 명령(`redeploy`) 이 없다** — 닫는 `)` 까지
> 붙여넣는 순간 1회 실행된다.
>
> 왜 함수(`redeploy() { … }` + 끝줄 `redeploy`) 가 아니라 서브셸인가: 함수 방식은
> *정의* 와 *호출* 이 분리돼 있어, 긴 함수 본문이 SSH 붙여넣기 중 한 줄이라도
> 씹히면 함수가 끝내 정의되지 않고, 그 상태로 마지막 `redeploy` 만 실행돼
> **"redeploy: command not found"** 가 난다 (VM-AP-8 실제 회귀). 서브셸은 정의·호출이
> 한 몸이라 이 분리 실패가 원천적으로 없다.
>
> 서브셸도 VM-AP-7 의 SSH-종료 안전성을 그대로 만족한다: `( … )` 안의 `exit 1` 은
> *서브셸만* 빠져나오고 부모 로그인 셸(=SSH 세션) 은 유지된다. 가드에 걸려 멈췄으면
> 원인 고친 뒤 **블록 전체를 다시 붙여넣으면** 된다 (재정의/재호출 구분 없음).
>
> ⚠️ 마지막 줄이 닫는 괄호 `)` 다. 붙여넣을 때 **`)` 까지 포함**됐는지 확인.

```bash
(
  cd ~/agents_reviewer || exit 1

  # ─── Stage 1: pull 전 working tree 정리 (VM-AP-3 / VM-AP-9 / VM-AP-10 가드) ───
  # untracked(-uno) 제외 — bot.log 백업 등은 pull 을 막지 않는다 (VM-AP-7).
  # reports/ 하위는 전부 봇·mirror·patch_report 가 재생성하는 산출물 — origin/main
  # (mirror API push) + Cloudflare(live) 가 정본이라 로컬 수정본은 pull 을 막는
  # 단골 잔재다. VM-AP-9(README.md, 2026-06-11) → VM-AP-10(analysis_* 패치 산출물,
  # 2026-06-17 — patch_report 가 reports/*.json/html/md/bundle 를 로컬 write 하나
  # 커밋은 mirror API 가 origin 에 직접 푸시해 로컬 working tree 만 diverge)으로
  # 일반화: reports/ 의 tracked 수정은 자동 폐기 후 진행 (pull 이 origin 의 정본 회복).
  if git status --porcelain --untracked-files=no | grep -q '^ M reports/'; then
    echo "ⓘ reports/ 미러 산출물 로컬 수정 자동 폐기 (VM-AP-9/10 — origin+Cloudflare 가 정본):"
    git status --porcelain --untracked-files=no | grep '^ M reports/' | sed 's/^ M //'
    git checkout -- reports/
  fi
  DIRTY=$(git status --porcelain --untracked-files=no)
  if [ -n "$DIRTY" ]; then
    echo "⚠️ 로컬 tracked 수정사항 발견 (pull 차단 위험):"
    echo "$DIRTY"
    echo "→ 잔재면 git checkout -- <file>, 의도적 수정이면 stash 후 재실행."
    exit 1
  fi

  # ─── Stage 2: main 확인 + pull + 의존성 변경 감지 (VM-AP-6 / VM-AP-11 가드) ───
  # VM 이 과거 세션에서 feature 브랜치에 checkout 된 채 남아있으면 git pull 이
  # 그 브랜치 기준 no-op ("Already up to date") 되고 옛 버전이 재기동된다
  # (VM-AP-11, 2026-07-02 실제 발생 — v8.3.0 배포가 v8.2.17 재기동으로 끝남).
  BR=$(git rev-parse --abbrev-ref HEAD)
  if [ "$BR" != "main" ]; then
    echo "⚠️ 현재 브랜치 $BR ≠ main — main 으로 전환 (VM-AP-11)"
    git checkout main || exit 1
  fi
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
  # (백업 bot.log.* 는 .gitignore + Stage 1 -uno 로 git status 에 안 잡힘 — VM-AP-7.)
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
  echo "  ② 'Conflict' / 'ERROR' 라인 없어야 (옛 봇과 polling 충돌 안 났는지)"
)
```

복붙 가능한 한 묶음으로 유지. **여는 `(` 부터 닫는 `)` 까지 통째로** 붙여넣을 것 —
서브셸은 `)` 가 들어오는 순간 1회 자동 실행된다. 별도 `redeploy` 호출 없음 (VM-AP-8).
5단계만 실행하고 6단계 누락하는 회귀가 VM-AP-4 의 본질이므로 블록을 자르지 말 것.

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

### VM-AP-7 — 재배포 블록을 SSH 에 붙여넣으면 세션이 끊기고, bot.log 백업이 가드를 오발 (2026-05-31 발생)

**증상 (2가지가 겹쳐 발현)**:

1. **SSH 세션 종료**: §1 블록을 함수로 안 감싸고 raw 명령 나열로 SSH 셸에 붙여넣으면,
   명령이 *현재 로그인 셸* 에서 실행된다. Stage 1 가드가 `exit 1` 이면 그게
   스크립트 종료가 아니라 *로그인 셸(=SSH 세션) 종료* → 접속이 뚝 끊긴다. 사용자
   화면에선 "VM 이 꺼진 것처럼" 보이지만 실제 VM·봇은 멀쩡.
2. **bot.log 백업이 dirty 오발**: Stage 5 가 만든 `bot.log.<timestamp>` 백업이
   untracked 라, 다음 실행의 Stage 1 `git status --porcelain` 에 `??` 로 잡힌다.
   가드가 자기가 만든 로그 백업을 "로컬 수정사항" 으로 오인해 매번 멈춘다 (악순환).
   `.gitignore` 에 `bot.log` 만 있고 `bot.log.*` 가 없어 백업은 무시 안 됐음.

**관찰된 흔적**:
- 붙여넣기 직후 프롬프트가 로그아웃돼 `ubuntu@host:~$` 로 떨어짐 (세션 종료)
- 재접속 후 `git status` 에 `?? bot.log.20260531_113123` 만 단독으로 잡힘
- Stage 1 가드 메시지("로컬 수정사항 발견") + 백업 파일명만 출력하고 중단

**Fix (3중)**:
1. **§1 전체를 `redeploy()` 함수로 래핑** + `exit 1` → `return 1`. 함수 안의 return
   은 함수만 빠져나오므로 SSH 세션 유지. 블록 끝 `redeploy` 로 1회 실행.
2. **Stage 1 을 `git status --porcelain --untracked-files=no`** 로 변경 — untracked
   (bot.log 백업 등) 은 pull 을 막지 않으므로 제외. tracked 수정만 차단 위험으로 검사.
3. **`.gitignore` 에 `bot.log.*` 추가** — 백업이 애초에 git status 에 안 잡히게 근본 차단.

### VM-AP-8 — `redeploy` 함수가 정의 안 돼 "command not found" (2026-06-01 발생)

**증상**: VM-AP-7 의 Fix 로 §1 을 `redeploy() { … }` 함수 + 끝줄 `redeploy` 호출
형태로 바꿨더니, 사용자가 SSH 에 붙여넣고 마지막에 `redeploy` 를 쳤을 때
**`redeploy: command not found`** 가 났다. 함수 *정의* 와 *호출* 이 분리돼 있어,
긴 함수 본문(80여 줄) 이 SSH 붙여넣기 중 한 줄이라도 씹히거나 중간에 끊기면
함수가 끝까지 정의되지 않는다. 그 상태에서 마지막 `redeploy` 만 셸에 들어가면
정의되지 않은 명령을 부르는 꼴 → command not found. 사용자는 "명령어가 틀렸다"
고 인지하지만 실제론 *정의가 누락* 된 것.

**관찰된 흔적**:
- `redeploy` 입력 시 `redeploy: command not found` (또는 `bash: redeploy: …`)
- `type redeploy` 가 `not found` — 함수가 셸에 등록 안 됨
- 붙여넣기 로그를 보면 함수 본문 중간 줄부터 프롬프트가 섞여 있음 (paste 분절)

**Fix**: §1 을 **즉시 실행 서브셸 `( … )`** 로 재설계. 정의·호출이 한 몸이라
별도 `redeploy` 호출 자체가 없어진다 — 닫는 `)` 가 들어오는 순간 1회 실행. paste
가 중간에 끊겨도 셸 문법 에러로 *즉시* 드러나지(불완전 `(`) 조용히 "정의 누락"
으로 빠지지 않는다. VM-AP-7 의 SSH-종료 안전성은 서브셸의 `exit 1`(부모 셸 미종료)
으로 동일하게 보존. 함수 안의 `return 1` → 서브셸의 `exit 1` 로 일괄 치환.

### VM-AP-9 — 봇의 미러 산출물(reports/README.md)이 pull 을 상습 차단 (2026-06-11, 하루 3회 발생)

**증상**: `git pull origin main` 이 "Your local changes to reports/README.md would be
overwritten" 로 중단 → 사용자에겐 "pull 했는데 버전이 안 올라간다" 로 보임 (VM-AP-4 와
결합해 옛 버전 봇 재기동까지 이어짐). v7.0.2→v7.1.0→v7.2.0 배포에서 연속 3회 재발.

**원인**: 봇이 보고서를 발행할 때마다 `github_mirror.build_reports_index()` 가
`reports/README.md` 를 로컬에서 재생성 — 이 파일은 tracked 라 다음 pull 의 충돌
대상이 된다. 운영 중인 봇이 있는 한 거의 항상 dirty 상태.

**관찰된 흔적**: `git status --porcelain --untracked-files=no` 에 ` M reports/README.md`
단독으로 잡힘. pull 출력에 "Please commit your changes or stash them" + Aborting.

**Fix**: §1 Stage 1 에 자동 가드 — 잔재가 정확히 `reports/README.md` 면 자동
`git checkout --` 후 진행 (자동 재생성 파일이라 폐기 안전). 그 외 파일이 함께 dirty
면 기존대로 멈추고 사람이 판단. **(v7.9.8 — VM-AP-10 으로 일반화: reports/ 전체로 확대.)**

---

### VM-AP-10 — patch_report 가 남긴 reports/analysis_* 산출물이 pull 을 차단 (2026-06-17 발생)

**증상**: `patch_report.py`(--replace / --strip-arc / --rerender-only) 를 VM 에서 돌린 뒤
재배포하면 Stage 1 가드가 ` M reports/analysis_20260617_*.{json,html,md,bundle.json}`
8개를 잡고 멈춤 → 사용자에겐 "pull 이 또 막힌다" 로 보임. VM-AP-9 의 형제 회귀
(README.md → 패치된 보고서 산출물로 확대).

**원인**: `patch_report` 가 `reports/<id>.{json,html,md,bundle.json}` 를 **로컬 working
tree 에 write** 하지만, 그 변경의 git 커밋은 `github_mirror`(GitHub Contents API)가
**origin/main 에 직접 푸시**한다 (로컬 `git commit` 경유 X). 결과로 로컬 HEAD 는 그대로인데
working tree 만 patched 버전으로 diverge → 다음 pull 이 "local changes would be overwritten"
로 차단. origin/main(mirror push) + Cloudflare(live) 가 이미 정본이라 로컬본은 잉여.

**Fix (v7.9.8)**: §1 Stage 1 가드를 `reports/README.md` 단독 → **`^ M reports/` 전체**로
일반화. reports/ 하위 tracked 수정은 전부 자동 `git checkout -- reports/` 후 진행 (pull 이
origin 의 정본 회복, Cloudflare live 는 git 과 무관하게 보존). 폐기 전 목록을 echo 로 표시.
reports/ 밖 파일이 dirty 면 기존대로 멈추고 사람 판단.

### VM-AP-11 — VM 이 feature 브랜치에 checkout 된 채 재배포 → 옛 버전 재기동 (2026-07-02 발생)

**증상**: §1 블록이 끝까지 정상 실행됐는데 `코드 버전: VERSION = "v8.2.17"` 처럼
*옛 버전* 이 찍히고, bot.log 시작 라인도 옛 버전 + `branch=claude/...` 를 표기.
`git fetch origin main` 은 origin/main 을 새 커밋으로 갱신했지만 `git pull` 은
"Already up to date".

**원인**: 과거 세션에서 feature 브랜치(예: `claude/youthful-galileo-01gjgh`)를 VM 에
직접 checkout 해 배포한 잔재. §1 Stage 2 의 `git pull` 은 *현재 브랜치의 upstream*
을 당기므로, main 이 아닌 브랜치에 서 있으면 main 의 새 커밋은 영원히 반영되지 않고
Stage 4~6 이 옛 코드를 충실히 재기동한다. `LOCAL != REMOTE` 비교도 HEAD(feature) vs
origin/main 비교라 pull 을 트리거하지만 결과가 no-op ("Already up to date").

**Fix (2026-07-02)**: §1 Stage 2 맨 앞에 브랜치 가드 추가 — `git rev-parse
--abbrev-ref HEAD` 가 main 이 아니면 echo 후 `git checkout main` (실패 시 exit).
Stage 1 이 working tree 를 이미 깨끗하게 만든 뒤라 checkout 은 안전. 재발 진단
단서 = Stage 3 의 `코드 버전` echo 와 bot.log 시작 라인의 `branch=` 표기.

---

### VM-AP-12 — systemd 서비스 봇에 `nohup` 수동 기동 → 중복 인스턴스 → Conflict/OOM (2026-07-11 발생)

**증상**: 봇 재시작/재배포 후 텔레그램 `getUpdates` **Conflict** 가 간헐 발생하거나,
1GB VM(E2.1.Micro)이 무거운 보고서 중 **전면 OOM 프리즈**(SSH·모든 서비스 동시 사망).
`pgrep -af 'src\.main'` 에 **2개 이상** 인스턴스가 뜬다(systemd MainPID + 수동 nohup PID).

**원인**: 이 VM 의 봇은 이미 systemd 서비스 `agents-reviewer.service`(enabled)로 관리되는데,
재시작을 `nohup python -m src.main` 로 안내·실행하면 **systemd 인스턴스에 더해 수동
인스턴스가 중복**으로 뜬다. 두 봇이 같은 토큰으로 polling → Conflict. 메모리도 이중
점유(수동 인스턴스가 보고서 돌며 100MB+ 로 비대) → 스왑 없는 1GB 에서 OOM 프리즈.
근본은 §1 의 legacy `pkill`+`nohup` 블록이 systemd 도입 사실을 반영 못 한 것 +
CLAUDE.md 에 재시작 규칙이 확정형으로 없어 매 세션 nohup 을 재발명한 것.

**Fix (2026-07-11)**: ① 재배포·재시작 표준을 **`sudo systemctl restart agents-reviewer.service`**
한 줄로 확정(§1 상단 박스). ② CLAUDE.md 최상단에 '🔴 봇 재시작·운영 SSOT' 블록 신설
(nohup 금지 명문화). ③ 스왑 4G 추가(OOM 프리즈 완충, E2.1.Micro 필수). 중복 정리는
`SYSPID=$(systemctl show -p MainPID --value agents-reviewer.service)` 후 그 외 `src.main`
PID 만 `kill`.

### VM-AP-13 — `.env` 의 미지원 키 하나가 봇 기동을 통째로 막음 (2026-08-30 발생)

**증상**: `systemctl restart` 후 서비스가 `activating (auto-restart)` 와
`code=exited, status=1/FAILURE` 를 무한 반복. `pgrep` 인스턴스 **0개**(봇 전면 정지).
`journalctl` 에 `pydantic_core._pydantic_core.ValidationError: N validation errors for Config`
+ `Extra inputs are not permitted [type=extra_forbidden]`. `scripts/patch_report.py` 등
`Config()` 를 지나는 **모든 CLI 도 같은 지점에서 동시에 전멸** 한다.

**원인**: `pydantic-settings` BaseSettings 의 기본값이 `extra="forbid"` 인데
`src/config.py:Config.model_config` 가 이를 재정의하지 않았다. 그래서 `.env` 에
`Config` 가 모르는 키가 **하나라도** 있으면 설정 객체 생성 자체가 실패한다. 실사고에서는
운영자가 앞으로 쓸 증권사 API 키(`KIS_APP_KEY` / `KIS_APP_SECRET`)를 `.env` 에 미리
적어둔 것이 방아쇠였다. 코드는 그 키를 아직 안 쓰므로 *아무 기능도 요구하지 않는 문자열
두 줄이 서비스를 죽인 것*. 실행 중인 봇은 config 를 startup 1회만 읽으므로 키를 적은
시점엔 멀쩡했고, **다음 재시작(=재배포)에서야 터진다** — 원인과 증상의 시간이 벌어져
"이번 배포가 봇을 깼다" 로 오진하기 쉽다.

**Fix (2026-08-30, v8.5.15)**: `Config.model_config` 에 **`"extra": "ignore"`**. 앞으로 쓸
키를 `.env` 에 미리 적어두는 것은 정상 운영 행위이고, 그 대가가 서비스 전면 정지여선
안 된다. 미지원 키는 무시하고 뜬다 — 실제로 읽히려면 어차피 필드 선언이 필요하므로
"조용히 무시돼 설정이 안 먹는" 위험은 원래부터 필드 선언 여부로 결정된다. 회귀
`tests/regression/test_config_env_tolerance.py` (실사고 `.env` 모양 + 임의 미래 키 +
선언된 필드 정상 로딩 3종). §1.0 Stage 3.5 에 **재시작 전 config 로드 프리플라이트**
추가 — 죽은 뒤 로그를 뒤지지 말고, 재시작 전에 막는다.

---

### VM-AP-14 — CLI 구독 인증 만료로 한 달간 보고서 전면 실패, 아무도 모름 (2026-09-27 ~ 10-27 발생)

**증상**: 봇 서비스는 `active (running)`, 인스턴스 1개, 메모리 여유 — 겉으로는 정상.
그런데 9/28 아침 브리핑부터 **모든 보고서가 0건**. GitHub `reports/` 미러도 9/27 이
마지막. `journalctl` 에 매일 `claude CLI failed after 1 attempt(s): exit=1: Failed to
authenticate. API Error: 401 … "OAuth access token has expired. Re-authenticate to
continue."`. 7/31 에 이은 **두 번째 같은 사고**.

**원인**: 원인 자체는 §3 'CLI 구독 인증 만료 점검' 의 그것(구독 OAuth 만료)이다.
문제는 *감지* 였다. 봇은 실패할 때마다 텔레그램에 `❌ 일일 브리핑 생성 실패:
{str(e)[:200]}` 를 보냈지만, 내용이 200자에서 잘린 오류 원문(JSON)이라 *무엇을 해야
하는지* 읽히지 않았다. 사전 점검도 없어 브리핑 시각이 되어서야 실패했다.

**Fix (v8.7.1)**:
- `src/tools/cli_auth.py:failure_message` — 실패 원인이 인증 만료면 원문 대신 **복구
  명령**(`claude` → `/login` → `/exit`, 확인 `claude -p "ping"`)을 보낸다. 일일·장마감
  브리핑, `/analyze`, 질문 답변, 장마감 소급 발행 5경로 공통. 다른 실패는 기존 문구 그대로.
- `src/scheduler/cli_auth_watch.py` — 켜진 브리핑마다 **브리핑 60분 전**
  (`CLI_AUTH_WATCH_LEAD_MIN`)에 `claude -p ping` 으로 점검, 만료면 구독자에게 먼저
  경고. 다른 실패(타임아웃 등)는 오경보를 피해 로그만. 끄려면 `CLI_AUTH_WATCH=0`.
- 회귀 `tests/test_cli_auth.py` (실로그 문자열 판별·문구 byte-equal·ping 파싱·점검 시각·
  만료 시에만 경고·브리핑 실패 경로 배선).

같은 날 함께 드러난 결함 — **osint 번들 전송 0건 (v8.4.0 이후 석 달)**. 같은 업로드
코드가 agents_reviewer 쪽으로는 동작했으므로 코드가 아니라 토큰 권한 문제다.
`GITHUB_OSINT_TOKEN` 미설정 → `GITHUB_MIRROR_TOKEN`(agents_reviewer 전용 fine-grained
PAT) 대체 → osint 쓰기 `HTTP 403 Resource not accessible by personal access token`
(2026-10-27 소급 발행 로그로 확정). 진단 중 GET 200 을 "읽기 권한 있음"으로 오독했는데,
osint_generator 는 **공개 저장소** 라 GET 200 은 권한과 무관하다 — 쓰기 권한은 쓰기로만
확인한다 (아래 §3 의 blob 시험). **해결**: 기존 미러 PAT 의 저장소 목록에 osint_generator
를 추가(토큰 값 불변 → `.env`·재시작 불요) → 같은 날 재전송으로 첫 성공 (osint `4f8a749`).
실패가 로그 한 줄로만 남아 무감지였다. v8.7.1 부터 실패 사유(`HTTP 403 …`)와 조치가
번들 메시지(일일 브리핑은 링크 메시지)에 한 줄로 붙는다 (`FullAnalysisResult.osint_mirror_error`).
진단 명령은 §3 'osint 번들 전송 점검'.

**교훈**: graceful degrade 는 *보고서를 살리는* 장치이지 *실패를 숨기는* 장치가 아니다.
실패 알림은 원문이 아니라 **조치** 를 담아야 하고, 반복되는 외부 의존(구독 인증)은
실패 전에 점검한다.

---

### VM-AP-15 — KRX 비밀번호 만료(CD010)를 "자격증명 확인"으로 오인, 시장 내부 데이터 무경고 누락 (2026-10-27 발견)

**증상**: 장마감 브리핑이 정상 발행되는데 선물·옵션 그릭과 시장 폭이 비어 있다
(`브리핑 차트 주입: breadth=0 deriv=0`). 실행 화면에 pykrx 의 `⚠️ KRX 비밀번호 변경이
필요합니다. 오류 메시지: 패스워드 변경 필요` 가 여러 번 찍히고, 봇 로그에는
`[krx] 로그인 실패 — 자격증명 확인(KRX_ID/KRX_PW).` 만 남는다.

**원인**: KRX 계정의 비밀번호 변경 주기가 지나 로그인 API 가 `CD010` 을 돌려준다.
pykrx 1.2.x 는 이 원인을 **print 로만** 알리고 `None` 을 돌려주므로, 봇은 원인을 모른 채
"자격증명 확인" 이라는 틀린 문구를 남겼다. 보고서는 그 섹션만 빈 채로 나가 무감지였다.
또 한 보고서 안의 여러 fetch 스레드가 각자 로그인을 시도해, 같은 실패 로그인이 동시에
여러 번 나갔다 — 틀린 비밀번호 반복 로그인은 계정 잠금 위험이다.

**Fix (v8.7.1)**: `src/tools/krx_client.py` — pykrx 출력을 잡아 원인 분류
(`password_change_required` / `login_failed`), 로그인을 락으로 직렬화, 실패 후 10분
쿨다운(`LOGIN_FAIL_COOLDOWN_S`). `login_problem()` 의 조치 문구가 장마감 브리핑 메시지·
소급 발행 송신·CLI 출력에 한 줄로 붙는다. 자격증명 미설정(의도적으로 끔)은 알리지 않는다.
회귀 `tests/test_krx_login.py`. 진단은 §3 'KRX 로그인 점검'.

---

### VM-AP-16 — 낡은 외부 CLI 가 새 모델을 못 써 검수·작성 실패, 원인 오분류 (2026-10-27 발견)

**증상 ① Claude CLI**: Opus 5.5 교체(v8.7.2) 재배포에서 Stage 3.6 이 재시작을 멈췄다.
`Claude Code 2.1.85 does not support this model; version 2.1.280 or newer is required`.
프리플라이트가 없었다면 재시작 직후부터 모든 보고서가 실패했다.

**증상 ② Codex CLI**: 10/27 보고서 전부 Codex 검수를 건너뛰었고 로그 사유는 `rate_limited`
였다. 그러나 실제 오류는 `The 'gpt-5.5' model is not supported when using Codex with a ChatGPT
account.`(400 `model_not_found`). codex-cli 0.136.0(2026-06)이 새 모델 목록을 해석하지 못해
(`unknown variant max`) 예전 기본값 gpt-5.5 로만 요청했다. `codex login status` 는 내내
`Logged in using ChatGPT` 였다.

**오분류 원인**: codex 는 stderr 에 배너·되풀이한 프롬프트(보고서 9만 자)·내부 추적 로그
(모델 목록 응답 전체)를 함께 찍는다. 봇은 그 전체에서 `429`·`quota`·`auth` 같은 단어를 찾아
분류했고, 로그에는 앞 300자(`Reading prompt from stdin...`)만 남겨 진짜 오류를 가렸다.

**Fix**: ① Claude CLI `sudo npm install -g @anthropic-ai/claude-code@latest`(2.1.311 확인),
Codex CLI `sudo npm install -g @openai/codex@latest`. ② v8.7.4 — `codex_critic` 이 최종 오류
JSON 줄(`ERROR: {"status":…,"error":{"code":…}}`)로 먼저 분류하고, 프롬프트 echo·내부 추적
줄을 걷어낸 뒤에만 키워드를 본다. 새 사유 `model_unsupported`. 로그엔 최종 오류 줄을 남긴다.
③ §1.0 Stage 3.6 이 codex 를 실제로 한 번 호출해 상태를 보여 준다(정보용, 재시작은 막지 않음).
회귀 `tests/regression/test_codex_critic.py`(실출력 재현 4종).

**교훈**: 모델을 바꾸거나 계정 쪽 모델 목록이 바뀌면 *CLI 버전* 부터 의심한다. 외부 도구의
"로그인됨" 은 "작동함" 이 아니다 — 실제로 한 번 호출해 본다.

---

### VM-AP-17 — 단축어(botz 계열)가 systemd 이전 방식에 머묾, `bot-up` 이 중복 기동 유발 (2026-10-28 발견)

**증상**: VM 에서 `botz`·`bot-up` 등 단축어가 안 먹는다는 사용자 질문. 확인해 보니
`scripts/install_bot_aliases.sh`(v5.8.6 시절)는 systemd 도입 전 판이었다. `bot-up` 이
`pkill -f src.main` 후 `nohup python -m src.main` 으로 봇을 띄우고, `bot-log` 는 systemd 가
쓰지 않는 `bot.log` 를 본다. 문서 어디에도 언급이 없어 아무도 갱신하지 않았다.

**위험**: 지금 VM 에서 옛 `bot-up` 을 쓰면 systemd 가 죽은 봇을 다시 살리는 동시에 nohup 봇이
하나 더 뜬다 → 텔레그램 `getUpdates` Conflict + 1GB VM OOM 프리즈(VM-AP-12, 2026-07-11 실사고).

**Fix (v8.7.6)**: 단축어를 systemd 기준 함수로 다시 썼다. `bot-up` 은 §1.0 가드 블록을 문서에서
읽어 `bash -c` 로 실행만 한다(사본 없음 — 재배포 절차의 정본은 §1.0 한 곳). `bot-log` 는
`journalctl -f`, `bot`·`bot-version` 은 서비스 상태와 *떠 있는* 버전까지 보여 준다. 설치 블록이 옛
alias 를 먼저 `unalias` 해, 같은 셸에 옛 정의가 남아 있어도 새 함수가 이긴다. 설치·갱신은 §3
'봇 단축어'. 같은 이유로 §3 '봇 현재 상태 한눈에' 의 `bot.log` 조회도 journal 로 바꿨다.

**교훈**: 운영 방식을 바꾸면(nohup → systemd) 그 방식을 품은 *편의 도구* 까지 같이 바꾼다. 문서에
없는 스크립트는 낡아도 아무도 모른다.

---

## §3 진단 명령어

### 봇 현재 상태 한눈에

```bash
# 봇 인스턴스 수 (1이어야 정상, 0=죽음, 2+=VM-AP-1)
pgrep -fc 'python.*src\.main'

# 봇이 어느 버전으로 떠있나 (systemd — 로그는 journal 에 있다. bot.log 는 nohup 시절 것)
journalctl -u agents-reviewer.service --no-pager | grep -E 'Starting Event Analysis Team bot' | tail -1

# 코드 버전 (떠있는 봇과 일치해야 — 불일치는 VM-AP-4)
grep '^VERSION = ' src/orchestrator.py
```

### 봇 단축어 (v8.7.6 — VM-AP-17)

`bot`(상태) · `bot-up`(재배포 = §1.0 블록 실행) · `bot-log`(로그) · `bot-cancel`(진행 중 분석 취소) ·
`bot-version`(코드/떠 있는 버전) · `botz`(목록). 설치·갱신은 한 줄, 다시 실행해도 안전하다.

```bash
bash ~/agents_reviewer/scripts/install_bot_aliases.sh && source ~/.bashrc && botz
```

### CLI 구독 인증 만료 점검 (2026-07-31 실제 사고 — 보고서 전면 실패의 1순위 용의자)

봇은 Claude Code CLI 구독 플랜으로 돈다 (CLAUDE.md '운영 모드 SSOT'). CLI 의 OAuth
토큰이 만료되면 **봇·텔레그램은 멀쩡한데 모든 보고서 생성만 실패** 한다 (LLM 호출이
전부 401). 보고서가 연속 실패하면 가장 먼저 이걸 확인 (2026-09-27 재발 — VM-AP-14).
v8.7.1 부터는 봇이 브리핑 60분 전에 스스로 점검해 만료면 텔레그램으로 아래 복구
명령을 먼저 보낸다. 실패 알림도 오류 원문 대신 같은 명령을 담는다
(`src/tools/cli_auth.py:CLI_AUTH_FIX` — 이 절과 문구 정합 유지).

```bash
# is_error:false + result 에 응답 텍스트면 정상. "OAuth access token has expired" 면 만료.
claude -p "ping" --output-format json
```

만료 시 조치 (VM 에서, 봇 재시작 불요 — CLI subprocess 가 매 호출마다 자격증명을 읽음):

```bash
# 대화형 로그인: 출력되는 URL 을 로컬 브라우저에서 열고, 코드를 터미널에 붙여넣기.
claude
# 프롬프트에서: /login   → 완료 후 /exit

# 확인
claude -p "ping" --output-format json
```

### osint 번들 전송 점검 (v8.7.1 — VM-AP-14)

번들 메시지에 `⚠️ osint 저장소 번들 전송 실패 (HTTP 403)` 같은 줄이 붙으면 토큰 권한
문제다. 토큰 값은 출력하지 않고 종류·쓰기 권한만 본다. 쓰기 시험은 어디에도 연결되지
않는 빈 데이터 조각(blob) 하나만 만든다 (커밋·파일 생성 없음).

```bash
cd ~/agents_reviewer && source venv/bin/activate
python - <<'EOF'
import json, urllib.request, urllib.error
from src.config import get_config
c = get_config()
tok = c.github_osint_token or c.github_mirror_token
repo = c.github_osint_repo
h = {"Authorization": f"Bearer {tok}", "User-Agent": "diag"}
with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}", headers=h), timeout=15) as r:
    print("토큰 종류:", "classic" if r.headers.get("X-OAuth-Scopes") is not None else "fine-grained", "/ scopes:", r.headers.get("X-OAuth-Scopes"))
print("osint 전용 토큰:", "있음" if c.github_osint_token else "없음(미러 토큰으로 대체)")
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/git/blobs",
    data=json.dumps({"content": "probe", "encoding": "utf-8"}).encode(),
    headers={**h, "Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print("쓰기 권한: 있음 (HTTP", r.status, ")")
except urllib.error.HTTPError as e:
    print("쓰기 권한: 없음 (HTTP", e.code, ")", e.read()[:200].decode(errors="replace"))
EOF
```

쓰기 권한이 없으면 osint_generator 에 Contents 읽기/쓰기 권한을 가진 PAT 를 발급해
`.env` 의 `GITHUB_OSINT_TOKEN=` 에 넣고 `sudo systemctl restart agents-reviewer.service`.
기존 미러 PAT 가 fine-grained 면 새로 발급하는 대신 GitHub → Settings → Developer
settings → Fine-grained tokens → 해당 토큰 → Edit 에서 저장소 목록에 osint_generator 를
추가해도 된다 (토큰 값이 그대로라 `.env`·재시작 불필요).

### KRX 로그인 점검 (v8.7.1 — VM-AP-15)

장마감 브리핑에 `⚠️ 선물·옵션·시장 폭 데이터 빠짐 — KRX …` 가 붙거나 로그에
`breadth=0 deriv=0` 이 보이면 확인한다. `KRX 로그인 완료.` 가 나오면 정상.

```bash
cd ~/agents_reviewer && source venv/bin/activate && python -m src.tools.breadth_fetcher 2>&1 | grep -E 'KRX|하락|warn|krx' | head
```

`비밀번호 변경이 필요` 가 나오면 **먼저 KRX 사이트에 로그인해 '90일 뒤 변경'** 을 누른다.
비밀번호가 그대로라 `.env` 수정·재시작이 필요 없다. 봇은 실패 쿨다운(10분) 뒤 다음 보고서에서
다시 로그인한다. 2026-10-27 이 방법으로 복구됐다 — 같은 날 18:30 장마감 브리핑에 선물·옵션·
시장 폭이 다시 들어갔다. 다음 만료는 2027-01-25 전후로 예상한다.

비밀번호를 실제로 바꿨다면 `.env` 의 `KRX_PW` 를 갱신한 뒤
`sudo systemctl restart agents-reviewer.service`. 특수문자가 있으면
`KRX_PW='새비밀번호'` 처럼 작은따옴표로 감싼다.

v8.7.3 부터 코스피·코스닥 **지수** 도 이 로그인을 쓴다 (그전엔 로그인 세션이 없어 늘
Yahoo 폴백). 로그인이 안 되면 지수만 Yahoo 로 내려가고 보고서는 정상 발행된다.

### Codex 검수 점검 (v8.7.3 · v8.7.4)

진행 알림에 `ⓘ 외부 사실 검수 건너뜀` 이 뜨면 v8.7.3 부터 다음 줄에 사유와 조치가 붙는다.
지난 보고서의 사유는 로그로 본다. v8.7.4 부터 로그에는 첫 줄이 아니라 **최종 오류 줄** 이 남는다.

```bash
journalctl -u agents-reviewer.service --since "3 days ago" --no-pager | grep -E 'codex_critic' | tail -20
cd /tmp && echo "Reply with the single word pong." | timeout 120 codex exec --skip-git-repo-check --sandbox read-only -m gpt-6-astra 2>&1 | grep -E '^ERROR|^pong' | tail -3; codex --version; cd ~
```

`codex login status` 가 `Logged in` 이어도 검수는 실패할 수 있다(VM-AP-16). 위 두 번째 줄처럼
실제로 한 번 물어봐야 확실하다. 검수 모델은 v8.7.5 부터 `gpt-6-astra`(SSOT `src/config.py:CODEX_MODEL_DEFAULT`,
codex-cli 0.153.1 이상). 계정에서 이 모델이 안 열리면 `model_unsupported` 로 건너뛴다 — 그땐 `.env` 에
`V6_CODEX_MODEL=<쓸 수 있는 모델>` 을 넣고 재시작한다.

| 로그 사유 | 뜻 | 조치 |
|---|---|---|
| `auth_failed` | ChatGPT 로그인 만료 | 아래 재로그인 (봇 재시작 불요) |
| `timeout` | `V6_CODEX_TIMEOUT_S`(기본 180초) 초과 | 잦으면 `.env` 에 `V6_CODEX_TIMEOUT_S=300` 후 재시작 |
| `rate_limited` | ChatGPT 사용량 한도 | 한도가 풀리면 자동 복구 |
| `codex_not_found` | codex CLI 없음 | `codex --version` 확인 |
| `model_unsupported` | 모델을 계정이 못 씀 (대개 낡은 CLI) | `sudo npm install -g @openai/codex@latest`, 모델을 고정했다면 `.env` 의 `V6_CODEX_MODEL`·`~/.codex/config.toml` 확인 (봇 재시작 불요) |

재로그인은 이 VM 에서 검증된 방식(V6_TEST_RESULTS)으로 한다. 내 PC 에서
`ssh -L 1455:localhost:1455 ubuntu@<VM주소>` 로 접속 → VM 에서 `codex login` → 출력된 주소를
내 PC 브라우저로 연다. `codex login --device-auth`(브라우저 없이 코드 입력)도 있으나 ChatGPT
보안 설정에서 기기 코드 로그인을 먼저 켜야 한다. 로그인은 파일(`~/.codex/auth.json`)로 남아
봇 재시작 없이 다음 보고서부터 적용된다.

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

### CLI 타임아웃으로 보고서가 통째 실패했는지 (v8.5.5)

```bash
cd ~/agents_reviewer
grep -c 'timeout after 300s' bot.log
journalctl -u agents-reviewer.service --since '7 days ago' --no-pager | grep -c 'timeout after'
```

`claude CLI failed after 3 attempt(s): timeout after 300s` 는 사실수집(context_analyst)이
상한을 넘긴 것. v8.5.5 부터 deep 사실수집 상한이 900s 라 이 라인은 사라져야 정상이다.
여전히 `timeout after 900s` 가 보이면 CLI 자체가 느려진 것이니 `claude -p "ping"
--output-format json` 응답 시간부터 잰다.

### 지난 거래일 장마감 브리핑 소급 발행 (v8.5.4)

정시 스케줄러(18:30 KST)가 못 돈 날 — 봇이 죽어 있었거나, CLI 인증이 만료됐거나,
휴장 판정이 어긋난 날 — 의 장마감 브리핑을 나중에 만든다. **v8.5.4 이상 필요**
(그 아래 버전에선 `No module named` / `unrecognized arguments`).

```bash
cd ~/agents_reviewer && source venv/bin/activate

# 어제자 (구독자 전원에게 텔레그램 송신 + Pages 발행)
python3 -m src.scheduler.market_briefing yesterday

# 특정 날짜 / 생성만 하고 URL 만 확인 / 특정 채팅에만
python3 -m src.scheduler.market_briefing 20260731
python3 -m src.scheduler.market_briefing 20260731 --no-send
python3 -m src.scheduler.market_briefing 20260731 --chat-id 123456789
```

- deep 모드라 수 분 걸린다. SSH 가 끊겨도 살아남게 하려면 앞에 `nohup ... &` 대신
  `tmux new -s brief` 안에서 돌린다 (**봇 본체는 절대 nohup 금지 — VM-AP-12**. 이건
  봇이 아니라 1회성 CLI 라 중복 인스턴스 문제가 없다).
- 휴장일(주말·공휴일)은 종가가 없어 거부된다. 그래도 만들려면 `--force`.
- 발행되는 보고서는 정시 브리핑과 동일 — 선물·옵션 그릭 + 시장 폭 실데이터,
  목록의 `[장마감브리핑]` 배지, 영상용 `.bundle.json` 까지 그대로.
- 파생·시장폭 데이터는 KRX 로그인이 필요하다 (`.env` 의 `KRX_ID`/`KRX_PW`).
  없으면 그 섹션만 비고 보고서는 정상 발행된다.

---

## §4 신규 회귀 발견 시 등록 절차

CHART-AP / WRITE-AP 와 동일 패턴 (append-only):

1. **번호 부여**: 다음 VM-AP-N (현재 9 까지 사용). 같은 패턴은 기존 항목에 사례 추가.
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
