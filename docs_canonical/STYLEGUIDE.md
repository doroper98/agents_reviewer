# Event Analysis Team — Style Guide

## Python
- Python 3.11+ with type hints
- `from __future__ import annotations` in all files
- Pydantic v2 for all data models
- async/await for all I/O operations

## Naming
| Target | Convention | Example |
|--------|-----------|---------|
| Module | snake_case | macro_analyst.py |
| Class | PascalCase | MacroAnalyst |
| Function | snake_case | analyze_event |
| Constant | UPPER_SNAKE | MAX_RETRIES |
| Pydantic Model | PascalCase | EventProfile |

## Imports
- stdlib → third-party → local (separated by blank lines)
- `from __future__ import annotations` always first

## Commit Message
`v{VER}: {brief summary}`

## Forbidden
- `# type: ignore` without justification
- Raw dicts for structured data (use Pydantic)
- Hardcoded API keys
- `print()` in production (use logging)
