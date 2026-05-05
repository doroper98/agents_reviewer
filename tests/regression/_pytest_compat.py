"""V5 Phase 0B — pytest compat shim.

``scripts/run_regression.py`` 는 pytest 미설치 환경에서도 동작해야 한다
(REFACTOR_V5_PLAN.md §3.5 의 인수 기준 #2 — "CI 또는 로컬 스크립트").
test_*.py 모듈이 module-level 에서 ``import pytest`` 하기 때문에 pytest
미설치 시 import 자체가 실패하는 것을 방지하기 위한 shim.

pytest 가 설치되어 있으면 진짜 pytest 를 사용 (테스트 정상 작동).
미설치 시 stub 을 export — pytest 기능을 *호출하지 않는* 코드 경로만
정상 동작 (run_one / run_all 등 순수 검증 함수).
"""

from __future__ import annotations

try:  # pragma: no cover  — 실제 pytest 설치 환경에서 검증
    import pytest as _real_pytest

    pytest = _real_pytest  # noqa: F401  — re-export
    PYTEST_AVAILABLE = True

except ImportError:  # pragma: no cover  — pytest 미설치 환경에서 검증
    PYTEST_AVAILABLE = False

    class _SkipException(Exception):
        """pytest.skip() 의 stub 동작 — pytest 미설치 시 단순 RuntimeError."""

    class _Mark:
        @staticmethod
        def parametrize(*_a, **_kw):
            def decorator(f):
                return f
            return decorator

        @staticmethod
        def skipif(*_a, **_kw):
            def decorator(f):
                return f
            return decorator

    class _PytestStub:
        """pytest 미설치 환경의 최소 stub — run_regression.py 의 import 통과 목적."""

        mark = _Mark
        Parser = type("Parser", (), {})  # conftest.py 의 type hint 회피용 stub

        @staticmethod
        def skip(reason: str = "") -> None:
            raise _SkipException(reason)

        @staticmethod
        def fixture(*_a, **_kw):
            def decorator(f):
                return f
            return decorator

        @staticmethod
        def raises(*_a, **_kw):
            class _Ctx:
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    return False
            return _Ctx()

    pytest = _PytestStub  # type: ignore[assignment]  # noqa: F401
