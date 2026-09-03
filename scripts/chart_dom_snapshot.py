"""차트 렌더 DOM 스냅샷 회귀 도구 (CHART_REDESIGN_V8_6_PLAN.md §3.2, v8.6.0).

`samples/chart_gallery_v7.html` 의 `PAYLOADS` fixture 를 헤드리스 chromium 으로
렌더한 뒤, 각 `.chart-card-stage svg` 의 DOM 을 *정규화* (태그·정렬된 속성·공백
제거 트리 직렬화) 해 sha256 을 `{type: {theme: {...}}}` 로 기록한다.

**픽셀이 아니라 DOM** 이므로 폰트·OS·렌더 엔진 버전에 무관하다. Phase 1 의
"기본 표현 전환(소급)" 이 *어떤 type 의 DOM 을 바꿨는가* 를 커밋 메시지에
증빙하는 것이 본 도구의 존재 이유다 (플랜 §2.1 불변조건 ⑵).

사용법 (VM-AP-2 — 실행 권한 불요, 항상 `python scripts/...` 로 호출)::

    python scripts/chart_dom_snapshot.py --out tests/regression/fixtures/chart_dom_baseline.json
    python scripts/chart_dom_snapshot.py --check tests/regression/fixtures/chart_dom_baseline.json
    python scripts/chart_dom_snapshot.py --check tests/regression/fixtures/chart_dom_baseline.json --diff-report

브라우저 탐색 순서: Playwright-python → ``$CHROME_BIN`` →
``/opt/pw-browsers/chromium-*/chrome-linux/chrome`` glob. 하나도 없으면
"skip" 을 출력하고 exit 0 (CI·개발 컨테이너에서 조용히 통과).

``getBBox`` 로 viewBox 를 사후 보정하는 3종 (sankey / dot_matrix /
stakeholder_map) 은 텍스트 실측폭이 폰트에 좌우되므로 sha256 대신
**요소 수 + 태그 분포** 만 비교한다 (loose).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
GALLERY = REPO_ROOT / "samples" / "chart_gallery_v7.html"
DEFAULT_BASELINE = REPO_ROOT / "tests" / "regression" / "fixtures" / "chart_dom_baseline.json"

# 갤러리 테마 스위처와 1:1 (samples/chart_gallery_v7.html 의 THEMES).
DEFAULT_THEMES: tuple[str, ...] = (
    "editorial_cream",
    "burgundy_mono",
    "midnight_indigo",
    "pine_forest",
    "graphite_slate",
    "reportage_steel",
)

# getBBox 로 viewBox 를 사후 보정하는 렌더러 — 텍스트 실측폭이 폰트에 좌우되므로
# 해시가 환경마다 달라진다. 요소 수·태그 분포만 비교 (플랜 §3.2).
LOOSE_TYPES: tuple[str, ...] = ("sankey", "dot_matrix", "stakeholder_map")

SNAPSHOT_MARKER = "__chart_dom_snapshot__"

# ── 페이지 주입 하네스 ────────────────────────────────────────────────
# 갤러리 HTML 을 건드리지 않고, 임시 사본의 <head> 맨 앞에 끼워 넣는다.
#  · localStorage 셰임 — file:// 오리진에서 접근이 막히거나 이전 값이 남아
#    테마가 흔들리는 것을 차단하고, 원하는 테마를 결정적으로 주입한다.
#  · matchMedia 셰임 — prefers-reduced-motion 을 항상 참으로 만들어
#    entry/ambient 애니메이션을 끈다 (애니 중간 DOM 을 뜨면 해시가 흔들린다).
#  · IntersectionObserver 제거 — charts.js 의 backward-compat 경로를 타
#    화면 밖 카드까지 전부 즉시 렌더한다.
#  · topojson/world-atlas 로컬 사본 선주입 — choropleth 가 CDN 유무에 따라
#    다른 DOM 을 내지 않도록 (네트워크 의존 제거).
_HARNESS = """
<script>
(function () {
  var THEME = "__THEME__";
  var store = { gal_theme: THEME };
  try {
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
      setItem: function (k, v) { store[k] = String(v); },
      removeItem: function (k) { delete store[k]; },
      clear: function () { store = {}; },
      key: function (i) { return Object.keys(store)[i] || null; },
      get length() { return Object.keys(store).length; }
    } });
  } catch (e) { /* 셰임 실패해도 아래 setAttribute 로 테마는 고정된다 */ }
  document.documentElement.setAttribute('data-theme', THEME);
  window.matchMedia = function (q) {
    return { matches: /prefers-reduced-motion/.test(String(q)), media: String(q),
             addListener: function () {}, removeListener: function () {},
             addEventListener: function () {}, removeEventListener: function () {},
             onchange: null, dispatchEvent: function () { return false; } };
  };
  try { delete window.IntersectionObserver; } catch (e) { window.IntersectionObserver = undefined; }

  var WARNS = [];
  ['warn', 'error'].forEach(function (lvl) {
    var orig = console[lvl];
    console[lvl] = function () {
      try { WARNS.push(lvl + ': ' + Array.prototype.map.call(arguments, String).join(' ')); }
      catch (e) { WARNS.push(lvl + ': <unprintable>'); }
      return orig.apply(console, arguments);
    };
  });

  // DOM 정규화 — 태그명 + 사전순 정렬 속성 + 공백 제거 텍스트 의 재귀 직렬화.
  function ser(node) {
    if (node.nodeType === 3) { var t = String(node.nodeValue || '').trim(); return t ? '#' + t : ''; }
    if (node.nodeType !== 1) return '';
    var attrs = [];
    for (var i = 0; i < node.attributes.length; i++) {
      var a = node.attributes[i];
      attrs.push(a.name + '=' + a.value);
    }
    attrs.sort();
    var kids = [];
    for (var j = 0; j < node.childNodes.length; j++) {
      var s = ser(node.childNodes[j]);
      if (s) kids.push(s);
    }
    return node.tagName.toLowerCase() + '[' + attrs.join(';') + ']{' + kids.join(',') + '}';
  }
  function tagCounts(root) {
    var m = {}, all = root.getElementsByTagName('*');
    for (var i = 0; i < all.length; i++) {
      var tg = all[i].tagName.toLowerCase();
      m[tg] = (m[tg] || 0) + 1;
    }
    return Object.keys(m).sort().map(function (k) { return k + ':' + m[k]; }).join('|');
  }

  function collect() {
    var out = { theme: THEME, warnings: WARNS, charts: {} };
    var stages = document.querySelectorAll('.chart-card-stage[data-chart-type]');
    for (var i = 0; i < stages.length; i++) {
      var st = stages[i];
      var type = st.getAttribute('data-chart-type');
      var svg = st.querySelector('svg');
      out.charts[type] = {
        dom: svg ? ser(svg) : '',
        elements: svg ? svg.getElementsByTagName('*').length : 0,
        tags: svg ? tagCounts(svg) : ''
      };
    }
    var s = document.createElement('script');
    s.type = 'application/json';
    s.id = '__SNAPSHOT_MARKER__';
    s.textContent = JSON.stringify(out);
    document.body.appendChild(s);
  }
  window.addEventListener('load', function () { setTimeout(collect, 2500); });
})();
</script>
<script src="../src/templates/static/topojson-client.min.js"></script>
<script src="../src/templates/static/world-atlas-110m.js"></script>
"""


# ── 브라우저 탐색 ─────────────────────────────────────────────────────
def _playwright_executable() -> str | None:
    """Playwright 가 관리하는 chromium 경로 (설치돼 있고 실제 존재할 때만).

    조회를 *별도 프로세스* 로 돌린다 — `sync_playwright()` 는 node 드라이버에
    붙었다 떨어지며 asyncio 잔여 태스크 경고를 호출 프로세스에 남기는데,
    그 잡음이 스냅샷 도구·pytest 출력을 오염시키기 때문이다.
    """
    try:
        import playwright  # noqa: F401
    except Exception:
        return None
    code = (
        "import sys\n"
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as pw: p = pw.chromium.executable_path\n"
        "sys.stdout.write(p or '')\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=90
        )
    except Exception:
        return None
    path = (proc.stdout or "").strip()
    return path if path and os.path.exists(path) else None


def find_browser() -> str | None:
    """Playwright-python → $CHROME_BIN → /opt/pw-browsers glob 순으로 탐색."""
    path = _playwright_executable()
    if path:
        return path

    env = os.environ.get("CHROME_BIN", "").strip()
    if env and os.path.exists(env):
        return env

    for pat in (
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]

    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


# ── 렌더 ─────────────────────────────────────────────────────────────
def render_theme(browser: str, theme: str, timeout: int = 180) -> dict[str, Any]:
    """한 테마로 갤러리를 헤드리스 렌더하고 in-page 스냅샷 blob 을 회수한다."""
    gallery_src = GALLERY.read_text(encoding="utf-8")
    harness = _HARNESS.replace("__THEME__", theme).replace(
        "__SNAPSHOT_MARKER__", SNAPSHOT_MARKER
    )
    if "<head>" not in gallery_src:
        raise RuntimeError(f"{GALLERY} 에 <head> 가 없다 — 하네스 주입 불가")
    patched = gallery_src.replace("<head>", "<head>" + harness, 1)

    # 갤러리는 `../src/templates/...` 상대 경로 자산을 쓰므로 *같은 디렉토리* 에
    # 임시 파일을 둬야 한다 (tempdir 로 옮기면 자산이 전부 404).
    fd, tmp_path = tempfile.mkstemp(
        prefix=".chart_dom_snapshot_", suffix=".html", dir=str(GALLERY.parent)
    )
    os.close(fd)
    try:
        Path(tmp_path).write_text(patched, encoding="utf-8")
        cmd = [
            browser,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=1400,2000",
            "--virtual-time-budget=20000",
            "--dump-dom",
            Path(tmp_path).as_uri(),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT)
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    dom = proc.stdout or ""
    m = re.search(
        r'<script[^>]*id="%s"[^>]*>(.*?)</script>' % re.escape(SNAPSHOT_MARKER),
        dom,
        re.S,
    )
    if not m:
        raise RuntimeError(
            f"[{theme}] 스냅샷 blob 을 찾지 못했다 (렌더 실패). "
            f"chrome exit={proc.returncode}, dom={len(dom)}B"
        )
    return json.loads(m.group(1))


def digest(dom: str) -> str:
    return hashlib.sha256(dom.encode("utf-8")).hexdigest()


def collect(browser: str, themes: tuple[str, ...]) -> tuple[dict[str, Any], list[str]]:
    """테마별 렌더 결과를 `{type: {theme: entry}}` 로 뒤집어 담는다."""
    types: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for theme in themes:
        blob = render_theme(browser, theme)
        for w in blob.get("warnings") or []:
            warnings.append(f"[{theme}] {w}")
        for ctype, rec in (blob.get("charts") or {}).items():
            entry = {
                "sha256": digest(rec.get("dom") or ""),
                "elements": int(rec.get("elements") or 0),
                "tags": rec.get("tags") or "",
            }
            types.setdefault(ctype, {})[theme] = entry
    return types, warnings


# ── 비교 ─────────────────────────────────────────────────────────────
def compare(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    """baseline ↔ current 를 대조해 `{type: [사유...]}` 를 반환 (빈 dict = 동일).

    테마는 *부분집합 허용* — `--themes` 로 일부만 렌더해 빠르게 확인할 수 있게,
    현재 렌더에 없는 baseline 테마는 diff 로 치지 않는다 (전 테마 검증은
    기본값인 6종 전체 실행이 담당). type 은 부분집합을 허용하지 않는다.
    """
    loose = set(baseline.get("loose_types") or LOOSE_TYPES)
    b_types: dict[str, Any] = baseline.get("types") or {}
    diffs: dict[str, list[str]] = {}

    for ctype in sorted(set(b_types) | set(current)):
        reasons: list[str] = []
        if ctype not in current:
            reasons.append("현재 갤러리에 없음 (fixture 제거?)")
            diffs[ctype] = reasons
            continue
        if ctype not in b_types:
            reasons.append("baseline 에 없음 (신규 type — --out 으로 재기록 필요)")
            diffs[ctype] = reasons
            continue
        b_themes, c_themes = b_types[ctype], current[ctype]
        for theme in sorted(c_themes):
            if theme not in b_themes:
                reasons.append(f"{theme}: baseline 에 없음")
                continue
            b, c = b_themes[theme], c_themes[theme]
            if ctype in loose:
                if b.get("elements") != c.get("elements"):
                    reasons.append(
                        f"{theme}: 요소 수 {b.get('elements')} → {c.get('elements')}"
                    )
                if b.get("tags") != c.get("tags"):
                    reasons.append(f"{theme}: 태그 분포 변경")
            elif b.get("sha256") != c.get("sha256"):
                reasons.append(
                    f"{theme}: DOM 해시 {str(b.get('sha256'))[:12]} → "
                    f"{str(c.get('sha256'))[:12]} (요소 {b.get('elements')} → {c.get('elements')})"
                )
        if reasons:
            diffs[ctype] = reasons
    return diffs


def build_document(types: dict[str, Any], themes: tuple[str, ...], version: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "tool": "scripts/chart_dom_snapshot.py",
        "generated_with": version,
        "gallery": "samples/chart_gallery_v7.html",
        "themes": list(themes),
        "loose_types": list(LOOSE_TYPES),
        "types": {k: types[k] for k in sorted(types)},
    }


def _version() -> str:
    try:
        src = (REPO_ROOT / "src" / "orchestrator.py").read_text(encoding="utf-8")
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="차트 렌더 DOM 스냅샷 기록·대조 (v8.6.0)")
    ap.add_argument("--out", metavar="JSON", help="baseline 을 이 경로에 기록")
    ap.add_argument("--check", metavar="JSON", help="이 baseline 과 대조 (차이 있으면 exit 1)")
    ap.add_argument(
        "--diff-report",
        action="store_true",
        help="--check 와 함께 — 변경된 type 만 요약 (커밋 메시지 증빙용)",
    )
    ap.add_argument(
        "--themes",
        default=",".join(DEFAULT_THEMES),
        help="쉼표로 구분한 테마 목록 (기본: 갤러리 6종)",
    )
    args = ap.parse_args(argv)

    if not args.out and not args.check:
        args.check = str(DEFAULT_BASELINE)

    browser = find_browser()
    if not browser:
        print("skip: 헤드리스 chromium 을 찾지 못했다 (Playwright / $CHROME_BIN / /opt/pw-browsers)")
        return 0
    if not GALLERY.exists():
        print(f"skip: 갤러리가 없다 — {GALLERY}")
        return 0

    themes = tuple(t.strip() for t in args.themes.split(",") if t.strip())
    types, warnings = collect(browser, themes)

    unknown = [w for w in warnings if "unknown type" in w]
    render_err = [w for w in warnings if "render error" in w or "payload parse fail" in w]
    if warnings:
        print(f"[warn] 브라우저 콘솔 경고 {len(warnings)}건:")
        for w in warnings[:20]:
            print(f"  {w}")
    if unknown or render_err:
        print(
            f"[fail] unknown type {len(unknown)}건 / 렌더 예외 {len(render_err)}건 "
            "— 갤러리 fixture 와 RENDERERS 정합이 깨졌다"
        )
        return 2

    if args.out:
        doc = build_document(types, themes, _version())
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(f"[ok] baseline 기록 — {path} (type {len(types)} × theme {len(themes)})")
        return 0

    baseline_path = Path(args.check)
    if not baseline_path.exists():
        print(f"skip: baseline 이 없다 — {baseline_path} (--out 으로 먼저 기록)")
        return 0
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    diffs = compare(baseline, types)
    if not diffs:
        print(f"[ok] DOM 스냅샷 일치 — type {len(types)} × theme {len(themes)}, 변경 0")
        return 0

    if args.diff_report:
        print("변경된 type: " + ", ".join(sorted(diffs)))
    print(f"[diff] {len(diffs)} type 의 렌더 DOM 이 baseline 과 다르다:")
    for ctype in sorted(diffs):
        print(f"  · {ctype}")
        for reason in diffs[ctype]:
            print(f"      - {reason}")
    print(
        "의도한 변경이면 `python scripts/chart_dom_snapshot.py "
        f"--out {baseline_path}` 로 baseline 을 갱신하고 커밋 메시지에 목록을 남긴다."
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    sys.exit(main())
