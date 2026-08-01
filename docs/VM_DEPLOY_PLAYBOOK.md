---
tier: 1
last_synced_with: v8.5.4
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

### CLI 구독 인증 만료 점검 (2026-07-31 실제 사고 — 보고서 전면 실패의 1순위 용의자)

봇은 Claude Code CLI 구독 플랜으로 돈다 (CLAUDE.md '운영 모드 SSOT'). CLI 의 OAuth
토큰이 만료되면 **봇·텔레그램은 멀쩡한데 모든 보고서 생성만 실패** 한다 (LLM 호출이
전부 401). 보고서가 연속 실패하면 가장 먼저 이걸 확인:

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
