#!/usr/bin/env bash
# 봇 운영 단축어 설치 — 1번만 실행하면 됨 (다시 실행하면 최신 내용으로 갱신).
#
# 사용:
#   bash ~/agents_reviewer/scripts/install_bot_aliases.sh && source ~/.bashrc
#
# 단축어 (v8.7.6 — systemd 서비스 기준으로 다시 씀):
#   bot          — 상태 확인 (서비스 상태 + 지금 떠 있는 버전)
#   bot-up       — 재배포 (VM_DEPLOY_PLAYBOOK §1.0 가드 블록을 그대로 실행)
#   bot-log      — 봇 로그 실시간 (Ctrl-C 로 빠짐)
#   bot-cancel   — 진행 중인 분석만 취소 (봇 본체는 유지)
#   bot-version  — 코드 버전과 지금 떠 있는 버전을 나란히
#   botz         — 단축어 목록 + 설명 cheatsheet
#
# v8.7.6 이전 판은 systemd 도입 전 것이라 bot-up 이 `pkill + nohup` 으로 봇을 띄웠다.
# systemd 가 봇을 다시 살리는 지금은 그 방식이 봇 두 개 → 텔레그램 Conflict + 1GB VM
# OOM 프리즈를 부른다 (2026-07-11 실사고, VM-AP-12). bot-log 도 systemd 가 쓰지 않는
# bot.log 를 보고 있었다. 재배포 절차의 정본은 playbook §1.0 한 곳이고, bot-up 은 그
# 블록을 읽어 실행만 한다 (사본을 두지 않는다).
set -e

RC=~/.bashrc
MARK="# >>> agents_reviewer bot aliases >>>"
MARK_END="# <<< agents_reviewer bot aliases <<<"

if grep -q "$MARK" "$RC" 2>/dev/null; then
  echo "[bot-aliases] 이미 설치돼 있음 — 갱신합니다."
  sed -i "/$MARK/,/$MARK_END/d" "$RC"
fi

cat >> "$RC" <<'EOF'
# >>> agents_reviewer bot aliases >>>
# 봇 단축어 — scripts/install_bot_aliases.sh 로 자동 생성됨 (systemd 서비스 기준).
# 옛 판의 alias 가 같은 셸에 남아 있으면 아래 함수보다 우선하므로 먼저 지운다.
unalias bot bot-up bot-log bot-cancel bot-version 2>/dev/null || true

bot() {
  systemctl status agents-reviewer.service --no-pager 2>/dev/null | sed -n '1,3p'
  journalctl -u agents-reviewer.service --no-pager 2>/dev/null \
    | grep 'Starting Event Analysis Team bot' | tail -1 | sed -E 's/.*bot — /  떠 있는 버전: /'
  local n
  n=$(pgrep -fc 'python.*src\.main' || true)
  [ "${n:-0}" -gt 1 ] && echo "  ⚠️ 봇 프로세스 ${n}개 (1개여야 정상) — pgrep -af 'src\.main' 로 확인"
  return 0
}

bot-up() {
  # 재배포 = playbook §1.0 가드 블록. 사본을 두지 않고 문서에서 읽어 실행한다.
  # bash -c 로 넘겨 표준입력은 터미널에 둔다 (블록 안의 claude·sudo 가 스크립트를 먹지 않게).
  local blk
  blk=$(awk '/^### §1.0/{f=1} f&&/^```bash/{c=1;next} c&&/^```/{exit} c' \
    ~/agents_reviewer/docs/VM_DEPLOY_PLAYBOOK.md 2>/dev/null)
  if [ -z "$blk" ]; then
    echo "✗ 재배포 블록을 찾지 못함 (docs/VM_DEPLOY_PLAYBOOK.md §1.0)"
    return 1
  fi
  bash -c "$blk"
}

bot-log() {
  journalctl -u agents-reviewer.service -f
}

bot-cancel() {
  if pkill -f 'claude.*--dangerously-skip-permissions'; then
    echo "✓ 진행 중 분석만 취소 (봇은 살아있음)"
  else
    echo "✗ 취소할 분석이 없음"
  fi
}

bot-version() {
  grep -E '^VERSION\s*=' ~/agents_reviewer/src/orchestrator.py \
    | sed -E 's/.*"([^"]+)".*/  코드 버전:     \1/'
  journalctl -u agents-reviewer.service --no-pager 2>/dev/null \
    | grep 'Starting Event Analysis Team bot' | tail -1 \
    | sed -E 's/.*bot — (v[0-9.]+).*/  떠 있는 버전:  \1/'
}

botz() {
  cat <<'__BOTZ__'

봇 단축어 (agents_reviewer · systemd)
─────────────────────────────────────────────
  bot          상태 확인 (서비스 상태 + 떠 있는 버전)
  bot-up       재배포 (playbook §1.0 가드 블록 실행)
  bot-log      로그 실시간 보기 (Ctrl-C 로 빠짐)
  bot-cancel   진행 중인 분석만 취소 (봇 본체 유지)
  bot-version  코드 버전 / 떠 있는 버전 나란히
  botz         이 cheatsheet 다시 보기
─────────────────────────────────────────────
재배포 흐름: PR 머지 → bot-up → bot-version 두 줄이 같은지 확인
수동 기동(nohup python -m src.main) 금지 — 봇이 두 개 떠 OOM

__BOTZ__
}
# <<< agents_reviewer bot aliases <<<
EOF

echo "[bot-aliases] 설치 완료. 같은 터미널에서 바로 쓰려면:"
echo "  source ~/.bashrc"
echo ""
echo "단축어: bot · bot-up · bot-log · bot-cancel · bot-version · botz (목록 보기)"
