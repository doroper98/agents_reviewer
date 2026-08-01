"""v8.5.6 — 르포 팔레트 8종을 일반 보고서에도 개방 (사용자 결정 2026-08-01).

"보고서의 색감과 테마를 르포의 양식을 한번 적용해 본느건 어떨까" → "색상팔레트만
적용하자". **가져오는 것은 색뿐** — 르포의 플랫 지오메트리(radius 0 / shadow none)와
G마켓 Sans 디스플레이는 가져오지 않는다. 일반 보고서는 그 색을 쓰면서 둥근 모서리 +
Newsreader 세리프 조판을 유지한다.

가드:
  ① 8종이 일반 풀(ALL_THEMES)에 들어있고 CSS 블록이 존재
  ② **색 동일성** — 일반 이름과 `reportage_*` 쌍이 같은 팔레트. CSS 는 선언을 복제하지
     않고 선택자만 겹쳐 두는데, 누군가 복제로 되돌리면 한쪽만 손볼 때 색이 갈라진다.
  ③ **색만** — 일반 이름이 플랫 지오메트리·G마켓 Sans 에 걸리면 안 된다 (사용자 결정
     위반이자 장르 구분 소멸). 오버라이드는 `[data-theme^="reportage_"]` 접두 전용.
  ④ 지도 토큰 — 없으면 :root(라이트) 로 폴백해 어두운 배경에 밝은 지도가 박힌다.
  ⑤ 대비 — 본문·보조 텍스트가 WCAG AA(4.5:1) 이상. 일반 보고서는 르포보다 muted
     사용처가 훨씬 많다(사진 크레딧·각주·감시신호 설명·차트 note·fact_grid 라벨).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.lens_policy import ALL_THEMES, REPORTAGE_THEMES, select_reportage_theme, select_theme

_CSS = (Path(__file__).resolve().parents[2] / "src" / "templates" / "report.css").read_text(
    encoding="utf-8"
)

# 르포에서 넘어온 8종 (접두 없는 일반 이름).
SHARED = tuple(t[len("reportage_"):] for t in REPORTAGE_THEMES)


def _block(theme: str) -> str:
    """해당 테마 선택자의 선언 블록. :root 겸용(editorial_cream) 도 처리."""
    if theme == "editorial_cream":
        pat = r':root, \[data-theme="editorial_cream"\] \{(.*?)\n\}'
    else:
        pat = r'\[data-theme="%s"\][^{]*\{(.*?)\n\}' % re.escape(theme)
    m = re.search(pat, _CSS, re.S)
    assert m, f"{theme}: CSS 블록 없음"
    return m.group(1)


def _tokens(theme: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", _block(theme)))


def _luminance(hex_color: str) -> float:
    ch = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    ch = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------------
# ① 풀 등록
# --------------------------------------------------------------------------


def test_shared_palettes_joined_regular_pool() -> None:
    for name in SHARED:
        assert name in ALL_THEMES, f"{name}: 일반 테마 풀에 미등록 — 뽑힐 일이 없다"
    assert len(ALL_THEMES) == len(set(ALL_THEMES)), "테마 이름 중복"


def test_every_regular_theme_has_css() -> None:
    for theme in ALL_THEMES:
        assert _tokens(theme).get("--bg"), f"{theme}: --bg 미정의 (렌더 시 흰 배경)"


# --------------------------------------------------------------------------
# ② 색 동일성 (복제 회귀 차단)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SHARED)
def test_palette_identical_to_reportage_twin(name: str) -> None:
    plain, rep = _tokens(name), _tokens(f"reportage_{name}")
    assert plain == rep, (
        f"{name} ↔ reportage_{name} 팔레트가 갈라짐. CSS 는 선언을 *공유* 해야 한다 "
        f"(선택자만 겹치기). 복제하면 한쪽만 손볼 때 색이 어긋난다."
    )


# --------------------------------------------------------------------------
# ③ 색만 — 지오메트리·폰트는 안 가져온다
# --------------------------------------------------------------------------


def test_regular_names_excluded_from_flat_and_font_overrides() -> None:
    """플랫/폰트 오버라이드는 `[data-theme^="reportage_"]` 접두 전용이어야 한다."""
    assert '[data-theme^="reportage_"]' in _CSS
    for name in SHARED:
        for prop in ("border-radius:0", "GmarketSans"):
            # 접두 없는 이름을 셀렉터로 갖는 규칙에 해당 속성이 있으면 위반.
            for rule in re.findall(
                r'([^{}]*\[data-theme="%s"\][^{}]*)\{([^}]*)\}' % re.escape(name), _CSS
            ):
                sel, body = rule
                if "reportage_" in sel and f'[data-theme="{name}"]' not in sel:
                    continue
                assert prop not in body.replace(" ", ""), (
                    f"{name}: 색만 가져오기로 했는데 '{prop}' 가 붙음 — "
                    f"르포의 플랫 지오메트리/폰트는 이식 대상이 아니다"
                )


def test_geometry_stays_rounded_for_regular_names() -> None:
    """일반 이름 블록은 radius/shadow 를 정의하지 않아 :root(둥근 모서리)를 상속한다."""
    for name in SHARED:
        body = _block(name)
        assert "--radius" not in body and "--shadow" not in body, (
            f"{name}: 지오메트리 토큰이 팔레트 블록에 들어옴 — 색만 공유해야 한다"
        )


def test_reportage_pool_keeps_prefixed_names_only() -> None:
    """르포가 접두 없는 이름을 뽑으면 플랫 지오메트리·G마켓 Sans 를 잃는다."""
    for t in REPORTAGE_THEMES:
        assert t.startswith("reportage_")
    assert select_reportage_theme().startswith("reportage_")
    assert not select_theme("any").startswith("reportage_"), (
        "일반 보고서가 reportage_ 테마를 뽑으면 플랫 지오메트리가 딸려온다"
    )


# --------------------------------------------------------------------------
# ④ 지도 토큰
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", SHARED)
def test_map_tokens_present(name: str) -> None:
    """미정의면 :root(라이트)로 폴백 → 어두운 배경에 밝은 지도."""
    assert re.search(
        r'\[data-theme="%s"\][^{]*\{[^}]*--map-water' % re.escape(name), _CSS
    ), f"{name}: 지도 토큰 없음 — 라이트 지도가 박힌다"


# --------------------------------------------------------------------------
# ⑤ 대비 (WCAG AA)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ALL_THEMES)
def test_text_and_muted_meet_wcag_aa(theme: str) -> None:
    tk = _tokens(theme)
    bg, text, muted = tk["--bg"], tk["--text"], tk["--muted"]
    assert _contrast(text, bg) >= 4.5, (
        f"{theme}: 본문 대비 {_contrast(text, bg):.2f} — AA(4.5) 미달"
    )
    assert _contrast(muted, bg) >= 4.5, (
        f"{theme}: 보조 텍스트 대비 {_contrast(muted, bg):.2f} — AA(4.5) 미달. "
        f"일반 보고서는 muted 사용처가 많다(크레딧·각주·차트 note·감시신호 설명)"
    )


# --------------------------------------------------------------------------
# ⑥ ReportBundle 계약 — 영상(osint_generator)이 쓰는 테마 색
# --------------------------------------------------------------------------


@pytest.mark.parametrize("theme", tuple(ALL_THEMES) + tuple(REPORTAGE_THEMES))
def test_bundle_theme_tokens_extractable(theme: str) -> None:
    """번들의 `report.theme.tokens` 는 report.css 를 문자열 파싱해 뽑는다.

    선택자를 묶어 두면(`[data-theme="reportage_x"],\\n[data-theme="x"] {`) 파서가
    여는 중괄호를 못 찾아 빈 dict 로 떨어질 수 있다. 그러면 영상 쪽이 색을 잃는다
    (보고서는 멀쩡해 보여서 눈치채기 어렵다).
    """
    from src.handoff.bundle_builder import _theme_tokens

    tokens = _theme_tokens(theme)
    for key in ("bg", "card", "text", "muted", "accent", "up", "down", "border"):
        assert tokens.get(key, "").startswith("#"), (
            f"{theme}: 번들 테마 토큰 '{key}' 추출 실패 → 영상 색 유실"
        )
