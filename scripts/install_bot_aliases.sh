#!/usr/bin/env bash
# 봇 운영 단축어 4종 설치 — 1번만 실행하면 됨.
#
# 사용:
#   bash ~/agents_reviewer/scripts/install_bot_aliases.sh
#
# 설치 후 ``source ~/.bashrc`` 또는 새 터미널 / 재접속.
#
# 단축어:
#   bot         — 상태 확인 (봇이 떠있는지 한 줄)
#   bot-up      — 봇 켜기 (이미 떠있으면 죽이고 다시 켬 — 중복 차단)
#   bot-log     — 봇 로그 실시간 (Ctrl-C 로 빠짐)
#   bot-cancel  — 진행 중인 분석만 취소 (봇 본체는 유지)
set -e

RC=~/.bashrc
MARK="# >>> agents_reviewer bot aliases >>>"
MARK_END="# <<< agents_reviewer bot aliases <<<"

if grep -q "$MARK" "$RC" 2>/dev/null; then
  echo "[bot-aliases] 이미 설치돼 있음 — 갱신합니다."
  # 기존 블록 삭제 (mark 사이)
  sed -i "/$MARK/,/$MARK_END/d" "$RC"
fi

cat >> "$RC" <<'EOF'
# >>> agents_reviewer bot aliases >>>
# 봇 한 줄 단축어 — scripts/install_bot_aliases.sh 로 자동 생성됨.
alias bot='ps aux | grep -E "src.main|claude.*dangerously" | grep -v grep || echo "✗ 봇이 꺼져 있음 (bot-up 으로 켜기)"'
alias bot-up='pkill -f "src.main" 2>/dev/null; sleep 2; cd ~/agents_reviewer && git pull && source venv/bin/activate && nohup python -m src.main > bot.log 2>&1 & disown && sleep 3 && echo "✓ 봇 켜짐" && tail -20 bot.log'
alias bot-log='tail -f ~/agents_reviewer/bot.log'
alias bot-cancel='pkill -f "claude.*--dangerously-skip-permissions" && echo "✓ 진행 중 분석만 취소 (봇은 살아있음)" || echo "✗ 취소할 분석이 없음"'
# <<< agents_reviewer bot aliases <<<
EOF

echo "[bot-aliases] 설치 완료. 다음 중 하나 실행 후 사용:"
echo "  source ~/.bashrc                  # 같은 터미널에서 즉시 활성"
echo "  exit && 재접속                     # 새로 SSH"
echo ""
echo "단축어:"
echo "  bot         — 봇이 떠있는지 한 줄로"
echo "  bot-up      — 봇 켜기 (중복 자동 차단 + git pull 포함)"
echo "  bot-log     — 로그 실시간 보기 (Ctrl-C 로 빠짐)"
echo "  bot-cancel  — 진행 중인 분석만 취소"
