# Claude Max 구독 기반 아키텍처

## 토큰 활용 전략

Claude Max 구독에서 에이전트 시스템을 운영하는 방법은 3가지입니다:

### 옵션 1: Claude Code + Agent SDK (권장)
```
Telegram → Webhook Server → Claude Code CLI → Agent SDK → 9 Agents
```
- Claude Max 구독에 포함된 Claude Code 사용
- `claude_agent_sdk`를 통해 서브에이전트 생성
- 추가 API 비용 없음 (Max 구독 토큰 내에서 소진)
- **장점**: Max 구독 요금만으로 운영 가능
- **단점**: Claude Code 세션 제한 존재

### 옵션 2: Anthropic API (별도 과금)
```
Telegram → Python Server → Anthropic API → 9 Agents
```
- API 키 발급 후 직접 호출
- 토큰당 과금 (Max 구독과 별개)
- **장점**: 완전 자동화, 제한 없음
- **단점**: 별도 API 비용 발생

### 옵션 3: 하이브리드 (현실적 추천)
```
Telegram → Python Server → Claude Code (subprocess) → Analysis
```
- 텔레그램이 Python 서버에 명령 전달
- Python 서버가 `claude` CLI를 subprocess로 호출
- Claude Code가 Max 구독 토큰으로 분석 수행
- 결과를 파싱하여 보고서 생성
- **장점**: Max 토큰 활용 + 자동화
- **단점**: CLI 출력 파싱 필요

## 현재 구현: 듀얼 모드

이 시스템은 두 가지 모드를 지원합니다:

### Mode A: API Mode (ANTHROPIC_API_KEY 설정 시)
- 직접 API 호출로 9개 에이전트 병렬 실행
- 가장 빠르고 안정적
- API 크레딧 소진

### Mode B: Claude Code Mode (ANTHROPIC_API_KEY 미설정 시)
- `claude` CLI를 subprocess로 호출
- Max 구독 토큰 활용
- 순차 실행 (CLI 특성상)

## 설정

```bash
# Mode A: API Mode
ANTHROPIC_API_KEY=sk-ant-...

# Mode B: Claude Code Mode (API 키 비워두기)
ANTHROPIC_API_KEY=
CLAUDE_CODE_PATH=/usr/local/bin/claude
```
