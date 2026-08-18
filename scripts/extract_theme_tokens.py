"""report.css 의 테마 토큰을 JSON 으로 추출한다 (v8.5.9).

목적 — 디자인 문서가 색 값을 *손으로 옮겨적지 않게* 한다. 손으로 베끼면 반드시
드리프트하고, 드리프트한 문서는 며칠 안에 아무도 믿지 않는다.

용례::

    python3 scripts/extract_theme_tokens.py > /tmp/themes.json

산출물은 ``samples/report_design_sheet_v8_5_9.html`` 의 ``THEMES`` 상수로 주입한다
(부록 B '이 시트를 다시 만드는 법' 참조).

동작:
  1. ``src/templates/report.css`` 에서 주석을 걷어내고 ``[data-theme="X"] { … }``
     블록을 모은다. ``:root`` 는 ``editorial_cream`` 으로 취급 (CSS 가 그렇게 선언).
  2. 블록별 ``--key: value`` 를 수집. 셀렉터가 여러 테마를 겹쳐 잡으면 (르포/일반
     공유 팔레트) 각 이름에 같은 선언을 넣는다.
  3. ``var(--other)`` 참조는 같은 테마 안에서 끝까지 재귀 해석.
  4. 선언되지 않은 키는 ``:root`` 폴백으로 채우고 ``_inherited`` 에 이름을 남긴다.
     지오메트리(radius/shadow) 상속은 의도된 것이고, *색*이 상속되고 있으면 버그다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CSS_PATH = Path("src/templates/report.css")

# 디자인 시트가 쓰는 토큰. 순서가 곧 표의 열 순서.
KEYS: tuple[str, ...] = (
    "bg", "card", "card-hover", "border", "border-light", "divider",
    "text", "muted", "accent", "up", "down",
    "bg-3", "card-deep", "fg-2", "border-soft",
    "map-land", "map-water", "map-boundary",
    "radius", "shadow",
)

_ROOT_THEME = "editorial_cream"


def _blocks(css: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """``{theme: {--key: value}}`` 와 등장 순서를 돌려준다."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector, body = m.group(1), m.group(2)
        names = re.findall(r'\[data-theme(?:\^)?="([^"]+)"\]', selector)
        if not names:
            if ":root" in selector and "data-theme" not in selector:
                names = [_ROOT_THEME]
            else:
                continue
        decls = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)(?:;|$)", body))
        if not decls:
            continue
        for name in names:
            if name not in found:
                found[name] = {}
                order.append(name)
            found[name].update({k: v.strip() for k, v in decls.items()})
    return found, order


def _resolve(found: dict[str, dict[str, str]], theme: str, key: str, depth: int = 0) -> str:
    """``var(--x)`` 를 같은 테마 안에서 끝까지 따라간다."""
    value = found.get(theme, {}).get(key, "")
    ref = re.fullmatch(r"var\((--[\w-]+)(?:,[^)]*)?\)", value.strip())
    if ref and depth < 6:
        return _resolve(found, theme, ref.group(1), depth + 1)
    return value.strip()


def extract(css_path: Path = CSS_PATH) -> dict[str, dict[str, object]]:
    found, order = _blocks(css_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, object]] = {}
    for theme in order:
        row: dict[str, object] = {}
        inherited: list[str] = []
        for key in KEYS:
            value = _resolve(found, theme, "--" + key)
            if not value:
                value = _resolve(found, _ROOT_THEME, "--" + key)
                inherited.append(key)
            row[key] = value
        if inherited:
            row["_inherited"] = inherited
        out[theme] = row
    return out


if __name__ == "__main__":
    print(json.dumps(extract(), ensure_ascii=False, indent=1))
