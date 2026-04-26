---
tier: 2
last_synced_with: v2.4.1
ssot_for:
  - "테스트 전략 (CLI gate, 수동 검증 절차)"
  - "테스트 시나리오 카탈로그"
depends_on:
  - "src/agents/* (현재 7개 구성)"
  - "docs/CATALOGS.md"
last_review: 2026-04-26
---

# Event Analysis Team — Testing Strategy

## CLI Gate
```bash
python -m py_compile src/main.py
python -m py_compile src/orchestrator.py
python -m py_compile src/agents/base.py
```

## Manual Verification
1. Send test message via Telegram
2. 7개 에이전트 모두 출력 생성 확인 (현재 구성, [docs/CATALOGS.md](CATALOGS.md))
3. HTML 보고서가 브라우저에서 정상 렌더링되는지 확인
4. 시나리오별 균형 분석 4단락 (핵심 판단/비대칭/민감도/한계) 가독성 확인

## Test Scenarios
| Scenario | Input | Expected |
|----------|-------|----------|
| Basic event | "미국 관세 인상 분석" | 전체 7-에이전트 보고서 |
| Tech event | "OpenAI GPT-5 출시 분석" | 기술 중심 분석 |
| Geopolitical | "러시아-우크라이나 전쟁 분석" | 지정학 중심 보고서 |
