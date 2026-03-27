# Event Analysis Team — Testing Strategy

## CLI Gate
```bash
python -m py_compile src/main.py
python -m py_compile src/orchestrator.py
python -m py_compile src/agents/base.py
```

## Manual Verification
1. Send test message via Telegram
2. Verify all 9 agents produce output
3. Verify HTML report renders correctly in browser
4. Verify Devil's Advocate audit section present

## Test Scenarios
| Scenario | Input | Expected |
|----------|-------|----------|
| Basic event | "미국 관세 인상 분석" | Full 9-agent report |
| Tech event | "OpenAI GPT-5 출시 분석" | Tech-focused analysis |
| Geopolitical | "러시아-우크라이나 전쟁 분석" | Geopolitical-heavy report |
