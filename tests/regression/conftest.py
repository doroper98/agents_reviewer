"""V5 Phase 0B — pytest fixtures for regression tests.

pytest 미설치 환경에서도 ``helpers.py`` 만 import 해서 회귀 테스트를
직접 호출할 수 있도록 (``scripts/run_regression.py``), 본 파일은 *순전히*
pytest 한정 fixture 만 담당한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.regression.helpers import (
    load_baseline,
    load_distribution,
    load_golden_prompts,
)


@pytest.fixture(scope="session")
def golden_prompts() -> list[dict[str, Any]]:
    """fixtures/golden_prompts.yaml 의 prompts 배열."""
    return load_golden_prompts()


@pytest.fixture(scope="session")
def golden_distribution() -> dict[str, int]:
    return load_distribution()


@pytest.fixture(scope="session")
def baseline() -> dict[str, Any]:
    """v4.5.7 baseline 측정 결과. 미녹화 시 ``recorded: false``."""
    return load_baseline()


def pytest_addoption(parser: pytest.Parser) -> None:
    """`--require-baseline` 옵션 — true 면 baseline 미녹화 시 fail."""
    parser.addoption(
        "--require-baseline",
        action="store_true",
        default=False,
        help=(
            "baseline_v4_5_7.json 이 미녹화 (recorded=false) 면 회귀 테스트 fail. "
            "CI 본가동 시 활성. Phase 0B 완료 직후엔 비활성 (사용자가 record 후 활성)."
        ),
    )
