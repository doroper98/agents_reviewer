/* report_design_sheet_v8_6_0.charts.js — 차트 전 종 디자인 견본 (v8.6 흡수 어휘)
 *
 * 디자인 시트 §6.4 에 끼워 넣는 견본 모듈. 시트의 THEMES 토큰(curTok())으로 그린다.
 * production charts.js 가 아니라 *목표 디자인* 을 손으로 그린 목업이다 — v8.6.x 구현
 * (docs/CHART_REDESIGN_V8_6_PLAN.md) 의 시각 기준. 값은 전부 예시 데이터.
 *
 * 어휘 SSOT: docs/MONO_THEME_GUIDE.md §4 / §6 / §10 / §10.1(v8.6.0 신설 예정).
 *  - 칸 질감(tick·rung·dot) = 셀 수 있는 값 전용. 칸 하나의 뜻은 자동 산출·표기.
 *  - 잉크 사다리: ≤4 구성 / 5~7 순위 (LADDER7). accent 는 차트당 1 요소.
 *  - 캡슐(rx = h/2) = 막대류 공통. 캔들 몸통도 캡슐.
 *  - 속빈 = 이전·주말·미확정, 채움 = 이후·평일·확정.
 *  - 읽는 법 캡션(keyFooter) = 칸 질감·형태 인코딩을 쓴 차트는 필수.
 */
(function (global) {
  'use strict';
  var W = 360, H = 232, FOOT = 16;
  var SANS = "'Noto Sans KR','IBM Plex Sans KR',sans-serif";
  var SERIF = "Newsreader,'Noto Serif KR',serif";
  var MONO = "'IBM Plex Mono',monospace";
  var LADDER4 = [1, .42, .24, .13];
  var LADDER7 = [1, .78, .60, .44, .30, .20, .12];

  // ── 문자열 SVG 빌더 ─────────────────────────────────────────
  function el(tag, attrs, inner) {
    var s = '<' + tag;
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) s += ' ' + k + '="' + attrs[k] + '"';
    return inner === undefined ? s + '/>' : s + '>' + inner + '</' + tag + '>';
  }
  function T(x, y, s, o) {
    o = o || {};
    var fam = o.fam === 'serif' ? SERIF : o.fam === 'mono' ? MONO : SANS;
    return el('text', { x: x, y: y, 'font-family': fam, 'font-size': o.size || 9.5, 'font-weight': o.w || 400,
      fill: o.fill, 'fill-opacity': o.op, 'text-anchor': o.anchor || 'start', 'letter-spacing': o.ls,
      'font-style': o.italic ? 'italic' : undefined, 'dominant-baseline': o.base }, esc(String(s)));
  }
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function ladder(n) {
    if (n <= 4) return LADDER4.slice(0, n);
    if (n <= 7) return LADDER7.slice(0, n);
    return d3.range(n).map(function (i) { return 1 - (i / (n - 1)) * .88; });
  }
  function niceUnit(maxValue, maxMarks) {
    var raw = Math.abs(+maxValue) / Math.max(1, maxMarks);
    if (!(raw > 0)) return 1;
    var k = Math.floor(Math.log10(raw)), ms = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < ms.length; i++) { var u = ms[i] * Math.pow(10, k); if (u >= raw) return u; }
    return Math.pow(10, k + 1);
  }
  function fmtKo(u) {
    if (u >= 1e12) return (u / 1e12) + '조'; if (u >= 1e8) return (u / 1e8) + '억';
    if (u >= 1e4) return (u / 1e4) + '만'; if (u >= 1e3) return (u / 1e3) + '천'; return String(u);
  }
  function fmt(v) { var a = Math.abs(v); return a >= 100 ? d3.format(',.0f')(v) : a >= 10 ? d3.format(',.1f')(v) : d3.format(',.2f')(v); }
  function frame(t, inner, h) { return el('svg', { viewBox: '0 0 ' + W + ' ' + (h || H), role: 'img' }, el('rect', { width: W, height: h || H, rx: 6, fill: t['card-deep'] }) + inner); }
  function footer(t, text, h) {
    return T(W / 2, (h || H) - 6, text.replace(/[a-z]/g, function (c) { return c.toUpperCase(); }), { size: 8.2, fill: t.muted, anchor: 'middle', ls: '.08em' });
  }
  function capsule(x, y, w, h, fill, op) { var ww = Math.max(w, h); return el('rect', { x: x, y: y, width: ww, height: h, rx: h / 2, fill: fill, 'fill-opacity': op }); }
  function hollow(cx, cy, r, t, col) { return el('circle', { cx: cx, cy: cy, r: r, fill: t['card-deep'], stroke: col || t.text, 'stroke-width': 1.4 }); }
  function dot(cx, cy, r, fill, op) { return el('circle', { cx: cx, cy: cy, r: r, fill: fill, 'fill-opacity': op }); }
  function zero(x1, y1, x2, y2, t) { return el('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: t.text, 'stroke-opacity': .55, 'stroke-width': 1 }); }
  function grid(x1, y1, x2, y2, t) { return el('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: t.text, 'stroke-opacity': .06, 'stroke-width': 1 }); }
  function inv(t, op) { return op >= .55 ? t.card : t.text; }
  // 칸 질감 — tick(세로 눈금, 가로 진행) / rung(가로 실선, 세로 진행) / dot(점, 가로 진행)
  function marks(o, t) {
    var n = Math.round(o.value / o.unit), s = '', col = o.color || t.text, op = o.op == null ? 1 : o.op;
    for (var i = 0; i < n; i++) {
      var big = (i + 1) % 5 === 0;
      if (o.kind === 'tick') {
        var len = big ? o.len + 4 : o.len, x = o.x + i * o.gap;
        s += el('line', { x1: x, y1: o.y - len / 2, x2: x, y2: o.y + len / 2, stroke: col, 'stroke-opacity': op, 'stroke-width': big ? 1.4 : .9 });
      } else if (o.kind === 'rung') {
        var y = o.y - i * o.gap;
        s += el('line', { x1: o.x, y1: y, x2: o.x + o.len, y2: y, stroke: col, 'stroke-opacity': op, 'stroke-width': big ? 1.5 : .9 });
      } else {
        s += dot(o.x + i * o.gap, o.y, big ? 3.1 : 2.4, col, op);
      }
    }
    var end = o.kind === 'rung' ? o.y - (n - 1) * o.gap : o.x + (n - 1) * o.gap;
    return { svg: s, n: n, end: end };
  }
  function pathLine(pts) { return d3.line().x(function (d) { return d[0]; }).y(function (d) { return d[1]; }).curve(d3.curveLinear)(pts); }
  // 결정적 의사난수 (LCG) — 시드 고정이라 테마를 바꿔도 같은 그림
  function rng(seed) { var s = seed || 7; return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  function series(n, start, drift, vol, seed) { var r = rng(seed), v = start, out = []; for (var i = 0; i < n; i++) { v = v * (1 + drift + (r() - .5) * vol); out.push(v); } return out; }
  function isoDays(n, from) { var d0 = new Date(from || '2026-06-01T00:00:00Z'), out = []; for (var i = 0; i < n; i++) { var d = new Date(d0.getTime() + i * 864e5); out.push(d); } return out; }
  function iso(d) { return d.toISOString().slice(0, 10); }

  // ═══════════════════════════════════════════════════════════
  // 견본 정의 — {id, tier, family, name, when, absorbed, draw(t)}
  // tier: safe | guarded | injected | new (v8.6 신설) | new2 (v8.7 2차)
  // ═══════════════════════════════════════════════════════════
  var SPECS = [];
  function spec(o) { SPECS.push(o); }

  // ── A. 비교·순위 ─────────────────────────────────────────────
  spec({ id: 'bar', variant: 'capsule', tier: 'safe', family: '비교 · 순위', name: 'bar · 캡슐 (비율·지수 기본)',
    when: '순위·크기 비교. 값이 비율·지수처럼 셀 수 없으면 캡슐이 기본',
    absorbed: 'G3 Chunky Bars — 캡슐 끝 + 7단 잉크 사다리(1위가 가장 진함) + 막대 끝 세리프 값. 트랙·그리드 없음',
    draw: function (t) {
      var rows = [['미국', 69.0], ['중국', 33.0], ['EU', 30.0], ['일본', 18.0], ['한국', 9.0], ['대만', 6.5]];
      var x0 = 78, x1 = 300, max = 69, lad = ladder(rows.length), s = '';
      rows.forEach(function (r, i) {
        var y = 22 + i * 30, w = (r[1] / max) * (x1 - x0);
        s += T(x0 - 10, y + 12, r[0], { anchor: 'end', size: 10.5, w: i === 0 ? 700 : 400, fill: t.text });
        s += capsule(x0, y, w, 18, t.text, lad[i]);
        s += T(x0 + Math.max(w, 18) + 8, y + 13.5, fmt(r[1]) + '%', { fam: 'serif', size: 12.5, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      s += zero(x0, 18, x0, 22 + rows.length * 30 - 8, t);
      return frame(t, s + footer(t, '진할수록 상위 · 1위 값만 액센트'));
    } });

  spec({ id: 'bar', variant: 'tick', tier: 'safe', family: '비교 · 순위', name: 'bar · tick (셀 수 있는 값 기본)',
    when: '건수·인원·금액처럼 정수로 셀 수 있는 값. 항목 이름이 길면 가로',
    absorbed: 'F5 Tick Rows / L15 Ballot Tally — 눈금 하나 = 고정 수량, 다섯 번째마다 긴 눈금. 읽는 법 캡션 필수',
    draw: function (t) {
      var rows = [['플랫폼', 34], ['성장', 28], ['모바일', 22], ['인프라', 17], ['머신러닝', 11], ['디자인', 8]];
      var x0 = 78, unit = niceUnit(34, 48), gap = 5.6, s = '';
      rows.forEach(function (r, i) {
        var y = 30 + i * 30;
        s += T(x0 - 10, y + 4, r[0], { anchor: 'end', size: 10.5, w: i === 0 ? 700 : 400, fill: t.text });
        var m = marks({ kind: 'tick', x: x0 + 2, y: y, value: r[1], unit: unit, gap: gap, len: 11, op: i === 0 ? 1 : .62 }, t);
        s += m.svg + T(m.end + 10, y + 4.5, r[1], { fam: 'serif', size: 12.5, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      return frame(t, s + footer(t, '한 칸 = ' + fmtKo(unit) + '건 · 다섯 칸마다 긴 눈금'));
    } });

  spec({ id: 'bar', variant: 'rung', tier: 'safe', family: '비교 · 순위', name: 'bar · rung (세로 · 짧은 라벨)',
    when: '항목 ≤8 이고 이름이 6자 이하일 때만 세로. 아니면 렌더러가 tick 으로 강등',
    absorbed: 'F1 Rung Bars — 가로 실선 층이 칸. 값은 기둥 위 세리프. 한글 긴 라벨 금지(참고 §03)',
    draw: function (t) {
      var rows = [['무료', 38], ['스타터', 27], ['프로', 22], ['팀', 16], ['스케일', 11], ['기업', 7]];
      var unit = niceUnit(38, 40), base = 190, colW = 30, gapX = (W - 60 - colW * rows.length) / (rows.length - 1), s = '';
      rows.forEach(function (r, i) {
        var x = 30 + i * (colW + gapX);
        var m = marks({ kind: 'rung', x: x, y: base, value: r[1], unit: unit, gap: 4, len: colW, op: i === 0 ? 1 : .62 }, t);
        s += m.svg + T(x + colW / 2, m.end - 7, r[1], { fam: 'serif', size: 12, w: 700, anchor: 'middle', fill: i === 0 ? t.accent : t.text });
        s += T(x + colW / 2, base + 16, r[0], { size: 9.5, anchor: 'middle', fill: t.muted });
      });
      s += zero(24, base + 3, W - 24, base + 3, t);
      return frame(t, s + footer(t, '한 칸 = ' + fmtKo(unit) + '억 원 · 다섯 칸마다 진한 선'));
    } });

  spec({ id: 'bar', variant: 'dot', tier: 'safe', family: '비교 · 순위', name: 'bar · dot',
    when: '적은 건수(≤40칸)를 점으로 세게 할 때. lollipop 의 희소 항목과 같은 자리',
    absorbed: 'L2 Dot Cascade — 점 하나 = 정해진 수량. 다섯 번째 점이 크다',
    draw: function (t) {
      var rows = [['사람 실수', 27], ['배포', 22], ['설정', 18], ['외부 API', 13], ['용량', 9], ['네트워크', 5]];
      var x0 = 84, unit = niceUnit(27, 40), s = '';
      rows.forEach(function (r, i) {
        var y = 30 + i * 30;
        s += T(x0 - 10, y + 4, r[0], { anchor: 'end', size: 10.5, w: i === 0 ? 700 : 400, fill: t.text });
        var m = marks({ kind: 'dot', x: x0 + 3, y: y, value: r[1], unit: unit, gap: 7.2, op: i === 0 ? 1 : .62 }, t);
        s += m.svg + T(m.end + 10, y + 4.5, r[1], { fam: 'serif', size: 12.5, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      return frame(t, s + footer(t, '점 하나 = ' + fmtKo(unit) + '건 · 다섯 번째 점은 크게'));
    } });

  spec({ id: 'bar', variant: 'prior', tier: 'safe', family: '비교 · 순위', name: 'bar · prior (올해 vs 작년)',
    when: '같은 항목의 이전 값이 있을 때. 행마다 prior 필드 하나',
    absorbed: 'F6 Paired Rungs — 진한 칸 = 이번, 흐린 칸 = 이전. 두 계열을 색이 아니라 농도로',
    draw: function (t) {
      var rows = [['무료', 38, 31], ['스타터', 27, 22], ['프로', 22, 16], ['팀', 16, 13], ['기업', 9, 6]];
      var x0 = 70, unit = niceUnit(38, 48), gap = 5.6, s = '';
      rows.forEach(function (r, i) {
        var y = 24 + i * 38;
        s += T(x0 - 10, y + 6, r[0], { anchor: 'end', size: 10.5, w: i === 0 ? 700 : 400, fill: t.text });
        var m = marks({ kind: 'tick', x: x0 + 2, y: y, value: r[1], unit: unit, gap: gap, len: 11, op: i === 0 ? 1 : .62 }, t);
        s += m.svg + T(m.end + 9, y + 4.5, r[1], { fam: 'serif', size: 12.5, w: 700, fill: i === 0 ? t.accent : t.text });
        var p = marks({ kind: 'tick', x: x0 + 2, y: y + 15, value: r[2], unit: unit, gap: gap, len: 8, op: .22 }, t);
        s += p.svg + T(p.end + 9, y + 18, r[2], { size: 9.5, fill: t.muted });
      });
      return frame(t, s + footer(t, '2026 진하게 · 2025 흐리게 · 한 칸 = ' + fmtKo(unit) + '억'));
    } });

  spec({ id: 'lollipop', tier: 'guarded', family: '비교 · 순위', name: 'lollipop',
    when: '8~15 개 희소 항목의 순위. 막대가 무거울 때',
    absorbed: '줄기는 0.8px 실선, 점은 7단 사다리(순위). 셀 수 있는 값이면 줄기 대신 dot 질감',
    draw: function (t) {
      var rows = [['반도체', 34.2], ['이차전지', 28.7], ['자동차', 18.9], ['바이오', 15.3], ['조선', 12.8], ['석유화학', 9.4], ['철강', 6.1], ['디스플레이', 4.7]];
      var x0 = 82, x1 = 300, max = 34.2, lad = ladder(rows.length), s = '';
      rows.forEach(function (r, i) {
        var y = 22 + i * 23, x = x0 + (r[1] / max) * (x1 - x0);
        s += T(x0 - 10, y + 3.5, r[0], { anchor: 'end', size: 10, w: i === 0 ? 700 : 400, fill: t.text });
        s += el('line', { x1: x0, y1: y, x2: x, y2: y, stroke: t.text, 'stroke-opacity': .35, 'stroke-width': .8 });
        s += dot(x, y, 5, i === 0 ? t.accent : t.text, i === 0 ? 1 : lad[i]);
        s += T(x + 9, y + 4, fmt(r[1]), { fam: 'serif', size: 11.5, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      s += zero(x0, 16, x0, 22 + rows.length * 23 - 12, t);
      return frame(t, s + footer(t, '수출 증가율 % · 진할수록 상위'));
    } });

  spec({ id: 'diverging_bar', tier: 'guarded', family: '비교 · 순위', name: 'diverging_bar',
    when: '찬반·유입유출·증감처럼 0 을 기준으로 갈리는 쌍',
    absorbed: 'G10 Diverging Bar — 바깥 끝만 캡슐, 0 기준선 점선, 값은 바깥쪽 세리프. 감소는 --down',
    draw: function (t) {
      var rows = [['기업', 86, 0], ['팀', 54, 0], ['프로', 31, 0], ['스타터', 12, 0], ['구형 요금제', 0, 18], ['체험 종료', 0, 42], ['홈페이지', 0, 67]];
      var cx = 190, scale = 1.35, s = '';
      rows.forEach(function (r, i) {
        var y = 22 + i * 26, h = 14;
        s += T(78, y + 10.5, r[0], { anchor: 'end', size: 10, fill: t.text });
        if (r[1]) { s += el('rect', { x: cx, y: y, width: r[1] * scale, height: h, rx: h / 2, fill: t.accent, 'fill-opacity': .9 }) + el('rect', { x: cx, y: y, width: h, height: h, fill: t.accent, 'fill-opacity': .9 });
          s += T(cx + r[1] * scale + 7, y + 11, '+' + r[1], { fam: 'serif', size: 11.5, w: 700, fill: t.accent }); }
        if (r[2]) { s += el('rect', { x: cx - r[2] * scale, y: y, width: r[2] * scale, height: h, rx: h / 2, fill: t.down, 'fill-opacity': .75 }) + el('rect', { x: cx - h, y: y, width: h, height: h, fill: t.down, 'fill-opacity': .75 });
          s += T(cx - r[2] * scale - 7, y + 11, '-' + r[2], { fam: 'serif', size: 11.5, w: 700, anchor: 'end', fill: t.down }); }
      });
      s += el('line', { x1: cx, y1: 16, x2: cx, y2: 210, stroke: t.text, 'stroke-opacity': .55, 'stroke-dasharray': '2 2' });
      return frame(t, s + footer(t, '왼쪽 이탈 · 오른쪽 증가 · 계정 수'));
    } });

  spec({ id: 'bullet', tier: 'guarded', family: '비교 · 순위', name: 'bullet',
    when: '실적 vs 목표·컨센서스, 항목 여러 개',
    absorbed: '실적 막대 캡슐, 목표는 얇은 세로 표식, 달성률 세리프. 범위 밴드는 농도 2단',
    draw: function (t) {
      var rows = [['매출', 134, 128, 150], ['영업이익', 31.2, 33.5, 40], ['영업이익률', 23.3, 26.2, 30]];
      var x0 = 86, x1 = 320, s = '';
      rows.forEach(function (r, i) {
        var y = 34 + i * 60, sc = function (v) { return x0 + (v / r[3]) * (x1 - x0); };
        s += T(x0 - 10, y + 12, r[0], { anchor: 'end', size: 10.5, w: 500, fill: t.text });
        s += el('rect', { x: x0, y: y - 2, width: sc(r[3]) - x0, height: 22, rx: 11, fill: t.text, 'fill-opacity': .06 });
        s += el('rect', { x: x0, y: y - 2, width: sc(r[3] * .7) - x0, height: 22, rx: 11, fill: t.text, 'fill-opacity': .06 });
        s += capsule(x0, y + 3, sc(r[1]) - x0, 12, i === 0 ? t.accent : t.text, i === 0 ? 1 : .6);
        s += el('line', { x1: sc(r[2]), y1: y - 6, x2: sc(r[2]), y2: y + 24, stroke: t.text, 'stroke-width': 2 });
        s += T(sc(r[2]) + 6, y - 8, '목표 ' + r[2], { size: 8.5, fill: t.muted });
        s += T(x1 + 6, y + 13, Math.round(r[1] / r[2] * 100) + '%', { fam: 'serif', size: 12, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      return frame(t, s + footer(t, '캡슐 = 실적 · 세로선 = 목표 · 오른쪽 = 달성률'));
    } });

  spec({ id: 'range_bar', tier: 'guarded', family: '비교 · 순위', name: 'range_bar · before_after (덤벨)',
    when: '항목별 두 값(최저·최고 / 개편 전·후). 8개 이상 2시점 비교는 slope 대신 이것',
    absorbed: 'F12 Dumbbell Queue — 속빈 원 = 이전, 채운 원 = 이후, 사이는 구슬. 감소는 --down 구슬',
    draw: function (t) {
      var rows = [['초대 흐름', 14, 6], ['첫 보드', 19, 9], ['데이터 가져오기', 26, 13], ['팀 설정', 31, 21], ['출시', 38, 30], ['정산', 17, 21]];
      var x0 = 118, x1 = 330, max = 40, s = '';
      rows.forEach(function (r, i) {
        var y = 28 + i * 30, a = x0 + r[1] / max * (x1 - x0), b = x0 + r[2] / max * (x1 - x0), down = r[2] < r[1];
        s += T(x0 - 12, y + 4, r[0], { anchor: 'end', size: 10, fill: t.text });
        for (var k = 1; k < 7; k++) s += dot(a + (b - a) * k / 7, y, 1.6, down ? t.text : t.down, .7);
        s += hollow(a, y, 5, t) + dot(b, y, 5.2, t.text, 1);
        s += T(a + (a < b ? -9 : 9), y - 7, r[1], { size: 8.5, fill: t.muted, anchor: 'middle' });
        s += T(b + (a < b ? 10 : -10), y + 4, r[2], { fam: 'serif', size: 11.5, w: 700, fill: t.text, anchor: a < b ? 'start' : 'end' });
      });
      return frame(t, s + footer(t, '속빈 원 = 개편 전 · 채운 원 = 개편 후 · 분'));
    } });

  spec({ id: 'slope', tier: 'guarded', family: '비교 · 순위', name: 'slope',
    when: '두 시점, 3~7 항목의 순위 변화. 8개 넘으면 덤벨로 재배치',
    absorbed: '값 라벨 dodge 유지 + 상승 accent 1개 + 나머지 농도. 캡슐 끝점',
    draw: function (t) {
      var rows = [['반도체', 8.1, 24.3], ['자동차', 10.2, 9.8], ['철강', 4.0, 3.1], ['배터리', 5.4, 4.2], ['정유', 6.5, 5.0]];
      var xa = 110, xb = 250, y = d3.scaleLinear().domain([2, 26]).range([200, 30]), s = '';
      s += T(xa, 20, '2024', { size: 10, w: 700, anchor: 'middle', fill: t.text }) + T(xb, 20, '2026', { size: 10, w: 700, anchor: 'middle', fill: t.text });
      var ya = rows.map(function (r) { return y(r[1]); }); ya = dodge(ya, 13);
      var yb = rows.map(function (r) { return y(r[2]); }); yb = dodge(yb, 13);
      rows.forEach(function (r, i) {
        var key = i === 0, col = key ? t.accent : t.text, op = key ? 1 : .45;
        s += el('line', { x1: xa, y1: y(r[1]), x2: xb, y2: y(r[2]), stroke: col, 'stroke-opacity': op, 'stroke-width': key ? 2 : 1.2 });
        s += dot(xa, y(r[1]), 3.2, col, op) + dot(xb, y(r[2]), 3.2, col, op);
        s += T(xa - 8, ya[i] + 3.5, r[0] + ' ' + r[1], { size: 9.5, anchor: 'end', fill: col, w: key ? 700 : 400 });
        s += T(xb + 8, yb[i] + 3.5, r[2] + '%', { fam: 'serif', size: 11, w: 700, fill: col });
      });
      return frame(t, s + footer(t, '영업이익률 · 상승 1위만 액센트'));
    } });
  function dodge(ys, gap) { var idx = ys.map(function (v, i) { return i; }).sort(function (a, b) { return ys[a] - ys[b]; }); var out = ys.slice(); for (var k = 1; k < idx.length; k++) { if (out[idx[k]] - out[idx[k - 1]] < gap) out[idx[k]] = out[idx[k - 1]] + gap; } return out; }

  spec({ id: 'bump', tier: 'guarded', family: '비교 · 순위', name: 'bump',
    when: '시기별 순위 경쟁 (3시점 이상)',
    absorbed: '순위 축은 유일한 곡선 허용 예외(monotone). 1위 선만 accent, 나머지 7단 농도. 끝점 캡슐 라벨',
    draw: function (t) {
      var periods = ['2023', '2024', '2025', '2026'], items = [['TSMC', [1, 1, 1, 1]], ['삼성', [2, 2, 3, 2]], ['SMIC', [4, 3, 2, 3]], ['글로벌파운드리', [3, 4, 4, 4]], ['UMC', [5, 5, 5, 5]]];
      var x = d3.scalePoint().domain(periods).range([70, 250]), y = function (r) { return 30 + (r - 1) * 38; }, lad = ladder(items.length), s = '';
      periods.forEach(function (p) { s += T(x(p), 18, p, { size: 9.5, anchor: 'middle', fill: t.muted }); });
      items.forEach(function (it, i) {
        var key = i === 1, col = key ? t.accent : t.text, op = key ? 1 : lad[i];
        var pts = it[1].map(function (r, k) { return [x(periods[k]), y(r)]; });
        s += el('path', { d: d3.line().curve(d3.curveMonotoneX)(pts), fill: 'none', stroke: col, 'stroke-opacity': op, 'stroke-width': key ? 2.4 : 1.4 });
        pts.forEach(function (p) { s += dot(p[0], p[1], 3, col, op); });
        s += T(258, y(it[1][3]) + 3.5, it[1][3] + '위 ' + it[0], { size: 9.5, fill: col, w: key ? 700 : 400 });
      });
      return frame(t, s + footer(t, '파운드리 점유율 순위 · 주인공 선만 액센트'));
    } });

  // ── B. 구성 ──────────────────────────────────────────────────
  spec({ id: 'donut', tier: 'safe', family: '구성', name: 'donut · 눈금 링 (≤6 조각 기본)',
    when: '구성비 3~6 조각. 조각이 7 이상이면 기존 arc',
    absorbed: 'F4 Tick Donut — 100 눈금(1% = 1눈금), 매 10번째 길게, 12시가 0. 중앙 큰 숫자, 조각 사이 2px 틈',
    draw: function (t) {
      var data = [['파운드리', 62], ['메모리', 21], ['설계', 11], ['기타', 6]], cx = 120, cy = 116, r = 62, lad = ladder(data.length), s = '';
      var acc = 0;
      data.forEach(function (d, i) {
        var col = i === 0 ? t.accent : t.text, op = i === 0 ? 1 : lad[i];
        for (var k = 0; k < d[1]; k++) {
          var pct = acc + k, ang = (pct / 100) * Math.PI * 2 - Math.PI / 2, big = pct % 10 === 0, len = big ? 15 : 10;
          if (k === 0 && i > 0) continue; // 조각 경계 틈
          s += el('line', { x1: cx + Math.cos(ang) * r, y1: cy + Math.sin(ang) * r, x2: cx + Math.cos(ang) * (r + len), y2: cy + Math.sin(ang) * (r + len), stroke: col, 'stroke-opacity': op, 'stroke-width': big ? 1.6 : 1.1 });
        }
        acc += d[1];
      });
      s += T(cx, cy + 9, '62%', { fam: 'serif', size: 28, w: 700, anchor: 'middle', fill: t.text });
      s += T(cx, cy + 24, '파운드리', { size: 9, anchor: 'middle', fill: t.muted });
      data.forEach(function (d, i) {
        var y = 70 + i * 26;
        s += dot(230, y - 3, 4, i === 0 ? t.accent : t.text, i === 0 ? 1 : lad[i]);
        s += T(242, y, d[0], { size: 10, fill: t.text }) + T(330, y, d[1] + '%', { fam: 'serif', size: 11.5, w: 700, anchor: 'end', fill: i === 0 ? t.accent : t.text });
      });
      return frame(t, s + footer(t, '눈금 하나 = 1% · 12시 방향이 0 · 시계 방향'));
    } });

  spec({ id: 'stacked', tier: 'safe', family: '구성', name: 'stacked',
    when: '시나리오 × 구성요소 (양수 크기만)',
    absorbed: '행 = 캡슐 막대, 구간은 4단 농도 + 마지막 구간 accent. 합계는 끝 세리프, 범례는 위 한 줄',
    draw: function (t) {
      var rows = [['악화', [15.8, 38.9, 24.8]], ['기준', [42.8, 26.8, 17.8]], ['완화', [39.8, 18.8, 8.4]]], segs = ['수출', '환율', '내수'];
      var x0 = 60, sc = 2.9, lad = LADDER4, s = '';
      segs.forEach(function (n, i) { s += dot(x0 + i * 60, 18, 3.5, i === 2 ? t.accent : t.text, i === 2 ? 1 : lad[i + 1]) + T(x0 + i * 60 + 8, 21, n, { size: 9.5, fill: t.muted }); });
      rows.forEach(function (r, i) {
        var y = 48 + i * 50, x = x0, total = d3.sum(r[1]);
        s += T(x0 - 10, y + 13, r[0], { anchor: 'end', size: 10.5, w: 500, fill: t.text });
        s += el('rect', { x: x0, y: y, width: total * sc, height: 20, rx: 10, fill: t.text, 'fill-opacity': .06 });
        r[1].forEach(function (v, k) {
          var w = v * sc, first = k === 0, last = k === r[1].length - 1;
          s += el('rect', { x: x, y: y, width: w, height: 20, rx: first || last ? 10 : 0, fill: last ? t.accent : t.text, 'fill-opacity': last ? .9 : lad[k + 1] });
          if (!first && !last) s += '';
          if (w > 26) s += T(x + w / 2, y + 14, v, { size: 9.5, anchor: 'middle', fill: inv(t, last ? .9 : lad[k + 1]) });
          x += w;
        });
        s += T(x + 8, y + 14.5, total.toFixed(0), { fam: 'serif', size: 12, w: 700, fill: t.text });
      });
      return frame(t, s + footer(t, '시나리오별 영향 구성 · 마지막 구간만 액센트'));
    } });

  spec({ id: 'treemap', tier: 'new', family: '구성', name: 'treemap (v8.6 신설)',
    when: '2층 구성 — 부문 → 세부 항목. 잎 6개 이상. 1층이면 donut/stacked',
    absorbed: 'F13 Nested Treemap — 3px 틈, 그룹 헤더 캡션, 잎은 그룹 사다리 × 잎 내 농도. 큰 잎만 두 줄 라벨',
    draw: function (t) {
      var root = { children: [
        { label: '메모리', children: [{ label: 'DRAM', value: 320 }, { label: 'NAND', value: 190 }, { label: 'HBM', value: 140 }] },
        { label: '시스템', children: [{ label: '파운드리', value: 210 }, { label: '설계', value: 95 }] },
        { label: '장비', children: [{ label: '전공정', value: 120 }, { label: '후공정', value: 60 }, { label: '검사', value: 40 }] }] };
      var h = d3.hierarchy(root).sum(function (d) { return d.value || 0; }).sort(function (a, b) { return b.value - a.value; });
      d3.treemap().size([W - 28, H - FOOT - 28]).paddingInner(3).paddingTop(24).paddingOuter(2).tile(d3.treemapSquarify)(h);
      var groups = h.children, lad = ladder(groups.length), s = '', maxLeaf = d3.max(h.leaves(), function (d) { return d.value; });
      var ox = 14, oy = 14;
      groups.forEach(function (g, gi) {
        var gw = g.x1 - g.x0, ghead = gw >= 84 ? g.data.label + ' · ' + Math.round(g.value / h.value * 100) + '%' : (gw >= 40 ? g.data.label : '');
        if (ghead) s += T(g.x0 + ox + 4, g.y0 + oy + 15, ghead, { size: 8.5, fill: t.muted, ls: '.06em' });
        g.leaves().forEach(function (l, li) {
          var op = lad[gi] * (.6 + .32 * (l.value / maxLeaf)), w = l.x1 - l.x0, hh = l.y1 - l.y0, big = l === h.leaves()[0];
          s += el('rect', { x: l.x0 + ox, y: l.y0 + oy, width: w, height: hh, rx: 3, fill: t.text, 'fill-opacity': op, stroke: big ? t.accent : 'none', 'stroke-width': big ? 1.4 : 0 });
          if (w >= 56 && hh >= 30) { s += T(l.x0 + ox + 6, l.y0 + oy + 14, l.data.label, { size: 9.5, fill: inv(t, op) }) + T(l.x0 + ox + 6, l.y0 + oy + 27, l.value, { fam: 'serif', size: 11, w: 700, fill: inv(t, op) }); }
          else if (w >= 30 && hh >= 16) s += T(l.x0 + ox + 5, l.y0 + oy + 12, l.data.label, { size: 8.5, fill: inv(t, op) });
        });
      });
      return frame(t, s + footer(t, '면적 = 억 달러 · 진할수록 큰 묶음'));
    } });

  spec({ id: 'dot_matrix', tier: 'guarded', family: '구성', name: 'dot_matrix',
    when: "'100명 중 N명' 체감. 사회 이슈 어휘",
    absorbed: 'G4 Dot Waffle — 점 100개 = 100%. 항목별 농도 사다리, 범례에 큰 숫자',
    draw: function (t) {
      var data = [['비정규직', 37], ['정규직 · 대기업', 21], ['정규직 · 중소', 42]], lad = ladder(3), s = '', k = 0;
      for (var i = 0; i < 100; i++) {
        var col = i % 10, row = Math.floor(i / 10), which = i < 37 ? 0 : i < 58 ? 1 : 2;
        s += dot(30 + col * 17, 24 + row * 17, 6.2, which === 0 ? t.accent : t.text, which === 0 ? 1 : lad[which]);
      }
      data.forEach(function (d, i) { var y = 60 + i * 44; s += dot(232, y - 4, 5, i === 0 ? t.accent : t.text, i === 0 ? 1 : lad[i]); s += T(246, y - 8, d[0], { size: 9.5, fill: t.muted }) + T(246, y + 10, d[1] + '명', { fam: 'serif', size: 15, w: 700, fill: i === 0 ? t.accent : t.text }); });
      return frame(t, s + footer(t, '점 하나 = 임금근로자 100명 중 1명'));
    } });

  spec({ id: 'pyramid', tier: 'guarded', family: '구성', name: 'pyramid',
    when: '연령 × 두 집단 (인구 피라미드)',
    absorbed: '바깥 끝 캡슐, 가운데 연령 축, 최대 구간 값만 세리프. 왼쪽 농도 · 오른쪽 accent',
    draw: function (t) {
      var ages = ['80+', '70대', '60대', '50대', '40대', '30대', '20대', '10대', '0~9'], m = [80, 190, 320, 428, 400, 330, 310, 230, 170], f = [150, 240, 350, 421, 390, 300, 280, 215, 160];
      var cx = 180, sc = .3, s = '';
      ages.forEach(function (a, i) {
        var y = 16 + i * 21, h = 14;
        s += el('rect', { x: cx - 16 - m[i] * sc, y: y, width: m[i] * sc, height: h, rx: h / 2, fill: t.text, 'fill-opacity': .5 }) + el('rect', { x: cx - 16 - h, y: y, width: h, height: h, fill: t.text, 'fill-opacity': .5 });
        s += el('rect', { x: cx + 16, y: y, width: f[i] * sc, height: h, rx: h / 2, fill: t.accent, 'fill-opacity': .85 }) + el('rect', { x: cx + 16, y: y, width: h, height: h, fill: t.accent, 'fill-opacity': .85 });
        s += T(cx, y + 10.5, a, { size: 8.5, anchor: 'middle', fill: t.muted });
        if (i === 3) { s += T(cx - 22 - m[i] * sc, y + 11, m[i], { fam: 'serif', size: 11, w: 700, anchor: 'end', fill: t.text }) + T(cx + 22 + f[i] * sc, y + 11, f[i], { fam: 'serif', size: 11, w: 700, fill: t.accent }); }
      });
      s += T(cx - 60, 12, '남', { size: 9.5, w: 700, anchor: 'middle', fill: t.text }) + T(cx + 60, 12, '여', { size: 9.5, w: 700, anchor: 'middle', fill: t.accent });
      return frame(t, s + footer(t, '만 명 · 50대가 가장 두터운 허리'));
    } });

  spec({ id: 'funnel', tier: 'new2', family: '구성', name: 'funnel (v8.7 2차)',
    when: '접수→심사→승인처럼 단계마다 줄어드는 수. sankey 를 2열 사슬로 오용하던 자리',
    absorbed: 'L13 Hourglass Stream — 단계 폭 = 인원, tick 질감으로 세게, 단계 사이 전환율',
    draw: function (t) {
      var st = [['방문', 4200], ['가입', 1900], ['첫 사용', 960], ['재방문', 540], ['결제', 310]], unit = niceUnit(4200, 60), cx = 150, s = '';
      st.forEach(function (d, i) {
        var y = 26 + i * 40, n = Math.round(d[1] / unit), w = n * 4.2;
        var m = marks({ kind: 'tick', x: cx - w / 2, y: y, value: d[1], unit: unit, gap: 4.2, len: 14, op: i === st.length - 1 ? 1 : .55 }, t);
        s += m.svg + T(cx + w / 2 + 14, y - 2, d[0], { size: 9.5, fill: t.muted }) + T(cx + w / 2 + 14, y + 11, d3.format(',')(d[1]), { fam: 'serif', size: 12, w: 700, fill: i === st.length - 1 ? t.accent : t.text });
        if (i > 0) s += T(cx - w / 2 - 14, y + 4, Math.round(d[1] / st[i - 1][1] * 100) + '%', { size: 9, fill: t.muted, anchor: 'end' }) + T(cx - w / 2 - 14, y - 7, '전환', { size: 7.5, fill: t.muted, anchor: 'end', ls: '.06em' });
      });
      return frame(t, s + footer(t, '한 눈금 = ' + fmtKo(unit) + '명 · 줄어드는 자리가 새는 자리'));
    } });

  // ── C. 시간 ──────────────────────────────────────────────────
  spec({ id: 'line', tier: 'safe', family: '시간', name: 'line · 일별 점 (≤40 포인트 기본)',
    when: '30일 안팎의 일별 값. 60일 넘는 시장 시계열은 기존 실선',
    absorbed: 'F2 Hairline Line — 점 하나 = 하루, 속빈 점 = 주말. 첫·끝·최고만 라벨, x 축 3 tick',
    draw: function (t) {
      var days = isoDays(30), vals = series(30, 60, .003, .09, 11), y = d3.scaleLinear().domain([d3.min(vals) * .9, d3.max(vals) * 1.08]).range([190, 34]), x = d3.scalePoint().domain(d3.range(30)).range([30, 330]), s = '';
      var pts = vals.map(function (v, i) { return [x(i), y(v)]; });
      s += el('path', { d: pathLine(pts), fill: 'none', stroke: t.text, 'stroke-width': 1.1 });
      var peak = d3.maxIndex(vals);
      vals.forEach(function (v, i) { var wk = days[i].getUTCDay() === 0 || days[i].getUTCDay() === 6; s += wk ? hollow(x(i), y(v), 2.8, t) : dot(x(i), y(v), 2.8, t.text, 1); });
      s += dot(x(peak), y(vals[peak]), 4.2, t.accent, 1) + T(x(peak), y(vals[peak]) - 9, fmt(vals[peak]), { fam: 'serif', size: 11, w: 700, anchor: 'middle', fill: t.accent });
      s += T(x(29) + 6, y(vals[29]) + 4, fmt(vals[29]), { fam: 'serif', size: 11, w: 700, fill: t.text });
      [0, 14, 29].forEach(function (i) { s += T(x(i), 208, iso(days[i]).slice(5).replace('-', '/'), { size: 8.5, anchor: 'middle', fill: t.muted }); });
      return frame(t, s + footer(t, '점 하나 = 하루 · 속빈 점 = 주말'));
    } });

  spec({ id: 'area', tier: 'safe', family: '시간', name: 'area · 세로 실선 (≤120 포인트 기본)',
    when: '30~120 포인트 추세. 값보다 모양을 볼 때',
    absorbed: 'F3 Hairline Area — 그라데이션 대신 바닥→값 세로 실선. 최고점 원 + 라벨',
    draw: function (t) {
      var vals = series(70, 70, .002, .08, 5), y = d3.scaleLinear().domain([d3.min(vals) * .85, d3.max(vals) * 1.08]).range([192, 34]), x = d3.scaleLinear().domain([0, 69]).range([30, 330]), s = '';
      vals.forEach(function (v, i) { s += el('line', { x1: x(i), y1: 192, x2: x(i), y2: y(v), stroke: t.text, 'stroke-opacity': .28, 'stroke-width': .8 }); });
      s += el('path', { d: pathLine(vals.map(function (v, i) { return [x(i), y(v)]; })), fill: 'none', stroke: t.text, 'stroke-width': 1.3 });
      var p = d3.maxIndex(vals);
      s += dot(x(p), y(vals[p]), 3.5, t.accent, 1) + T(x(p), y(vals[p]) - 9, fmt(vals[p]), { fam: 'serif', size: 11, w: 700, anchor: 'middle', fill: t.accent });
      s += zero(30, 192, 330, 192, t);
      ['5월', '6월', '7월'].forEach(function (m, i) { s += T(30 + i * 150, 208, m, { size: 8.5, anchor: 'middle', fill: t.muted }); });
      return frame(t, s + footer(t, '세로선 하나 = 하루 · 바닥에서 값까지'));
    } });

  spec({ id: 'candle', tier: 'injected', family: '시간', name: 'candle · 둥근 몸통',
    when: '개별주 OHLC (시장 데이터 있을 때만 결정적 주입)',
    absorbed: 'F17 Candlestick — 몸통은 캡슐(rx = 폭/2), 심지 1px. 색은 우리 --up/--down 유지. 마지막 종가 라벨',
    draw: function (t) {
      var r = rng(3), c = 52, rows = [];
      for (var i = 0; i < 26; i++) { var o = c, cl = o * (1 + (r() - .5) * .08 + (i > 8 && i < 16 ? -.02 : .004)), hi = Math.max(o, cl) * (1 + r() * .02), lo = Math.min(o, cl) * (1 - r() * .02); rows.push([o, hi, lo, cl]); c = cl; }
      var y = d3.scaleLinear().domain([d3.min(rows, function (d) { return d[2]; }) * .98, d3.max(rows, function (d) { return d[1]; }) * 1.02]).range([196, 30]), x = d3.scalePoint().domain(d3.range(26)).range([34, 310]), bw = 7, s = '';
      y.ticks(4).forEach(function (v) { s += grid(30, y(v), 330, y(v), t) + T(26, y(v) + 3, '$' + v, { size: 8, anchor: 'end', fill: t.muted }); });
      rows.forEach(function (d, i) {
        var up = d[3] >= d[0], col = up ? t.up : t.down, top = y(Math.max(d[0], d[3])), h = Math.max(2, Math.abs(y(d[0]) - y(d[3])));
        s += el('line', { x1: x(i), y1: y(d[1]), x2: x(i), y2: y(d[2]), stroke: col, 'stroke-width': 1 });
        s += el('rect', { x: x(i) - bw / 2, y: top, width: bw, height: h, rx: Math.min(bw / 2, h / 2), fill: col });
      });
      var last = rows[25];
      s += T(x(25) + 10, y(last[3]) + 4, '$' + fmt(last[3]), { fam: 'serif', size: 11, w: 700, fill: t.text });
      return frame(t, s + footer(t, '몸통 = 시가~종가 · 심지 = 그날 고가~저가'));
    } });

  spec({ id: 'dual_line', tier: 'safe', family: '시간', name: 'dual_line',
    when: '단위가 다른 두 계열 (금리 × 환율)',
    absorbed: '범례 없이 선 끝 직접 라벨. 보조 계열은 점선·농도 .55. 축은 최상단 tick 에만 단위',
    draw: function (t) {
      var a = series(40, 3.5, .004, .03, 21), b = series(40, 1400, .002, .02, 22), x = d3.scaleLinear().domain([0, 39]).range([40, 262]);
      var ya = d3.scaleLinear().domain(d3.extent(a)).range([190, 40]), yb = d3.scaleLinear().domain(d3.extent(b)).range([190, 40]), s = '';
      s += el('path', { d: pathLine(a.map(function (v, i) { return [x(i), ya(v)]; })), fill: 'none', stroke: t.accent, 'stroke-width': 1.6 });
      s += el('path', { d: pathLine(b.map(function (v, i) { return [x(i), yb(v)]; })), fill: 'none', stroke: t.text, 'stroke-opacity': .6, 'stroke-width': 1.2, 'stroke-dasharray': '3 2' });
      s += T(x(39) + 6, ya(a[39]) + 4, '금리 ' + fmt(a[39]) + '%', { fam: 'serif', size: 10.5, w: 700, fill: t.accent });
      s += T(x(39) + 6, yb(b[39]) + 4, '환율 ' + d3.format(',.0f')(b[39]), { fam: 'serif', size: 10.5, w: 700, fill: t.text });
      s += zero(40, 192, 262, 192, t);
      return frame(t, s + footer(t, '실선 = 미 10년 금리(좌) · 점선 = 원/달러(우)'));
    } });

  spec({ id: 'forecast', tier: 'safe', family: '시간', name: 'forecast',
    when: '실적 + 전망 부채꼴',
    absorbed: '실적 마지막 점이 부채꼴의 꼭짓점(CHART-AP-24). 부채꼴은 hatch-wide 면적, 중앙선 점선',
    draw: function (t) {
      var act = series(20, 2400, .01, .05, 8), x = d3.scaleLinear().domain([0, 32]).range([40, 320]), last = act[19];
      var fc = d3.range(20, 33).map(function (i) { var k = (i - 19) / 13; return [i, last * (1 + .12 * k), last * (1 + .28 * k), last * (1 - .06 * k)]; });
      var y = d3.scaleLinear().domain([d3.min(act) * .9, last * 1.32]).range([190, 34]), s = '';
      s += el('defs', {}, el('pattern', { id: 'fc-hw', patternUnits: 'userSpaceOnUse', width: 3.8, height: 3.8, patternTransform: 'rotate(45)' }, el('line', { x1: 0, y1: 0, x2: 0, y2: 3.8, stroke: t.text, 'stroke-width': .7 })));
      var cone = [[x(19), y(last)]].concat(fc.map(function (d) { return [x(d[0]), y(d[2])]; })).concat(fc.slice().reverse().map(function (d) { return [x(d[0]), y(d[3])]; }));
      s += el('path', { d: pathLine(cone) + 'Z', fill: 'url(#fc-hw)', 'fill-opacity': .5, stroke: 'none' });
      s += el('path', { d: pathLine(act.map(function (v, i) { return [x(i), y(v)]; })), fill: 'none', stroke: t.text, 'stroke-width': 1.5 });
      s += el('path', { d: pathLine([[x(19), y(last)]].concat(fc.map(function (d) { return [x(d[0]), y(d[1])]; }))), fill: 'none', stroke: t.accent, 'stroke-width': 1.5, 'stroke-dasharray': '4 3' });
      s += dot(x(19), y(last), 3.5, t.text, 1) + T(x(19), y(last) - 9, d3.format(',.0f')(last), { fam: 'serif', size: 10.5, w: 700, anchor: 'middle', fill: t.text });
      s += T(x(32) + 4, y(fc[12][1]) + 4, d3.format(',.0f')(fc[12][1]), { fam: 'serif', size: 10.5, w: 700, fill: t.accent });
      s += el('line', { x1: x(19), y1: 30, x2: x(19), y2: 192, stroke: t.text, 'stroke-opacity': .25, 'stroke-dasharray': '2 3' }) + T(x(19), 24, '실적 | 전망', { size: 8.5, anchor: 'middle', fill: t.muted });
      return frame(t, s + footer(t, '부채꼴 = 낙관~비관 · 점선 = 중앙 전망'));
    } });

  spec({ id: 'stacked_area', tier: 'guarded', family: '시간', name: 'stacked_area',
    when: '구성의 시간 변화 (합 100 또는 총량)',
    absorbed: '층은 hatch 명목 패턴(§4 유지) + 층 끝 직접 라벨. 곡선 보간 금지(CHART-AP-30)',
    draw: function (t) {
      var n = 12, r = rng(9), a = d3.range(n).map(function (i) { return 30 + i * 2 + r() * 4; }), b = d3.range(n).map(function () { return 28 + r() * 6; }), c = a.map(function (v, i) { return 100 - v - b[i]; });
      var x = d3.scaleLinear().domain([0, n - 1]).range([36, 300]), y = d3.scaleLinear().domain([0, 100]).range([192, 30]), s = '';
      s += el('defs', {}, el('pattern', { id: 'sa-ht', patternUnits: 'userSpaceOnUse', width: 2.4, height: 2.4, patternTransform: 'rotate(45)' }, el('line', { x1: 0, y1: 0, x2: 0, y2: 2.4, stroke: t.text, 'stroke-width': .85 })) + el('pattern', { id: 'sa-dt', patternUnits: 'userSpaceOnUse', width: 2.4, height: 2.4 }, el('circle', { cx: 1.2, cy: 1.2, r: .22, fill: t.text })));
      var layers = [[a, t.accent, null, '재생'], [b, null, 'url(#sa-ht)', '원전'], [c, null, 'url(#sa-dt)', '화석']], cum = d3.range(n).map(function () { return 0; });
      layers.forEach(function (L, li) {
        var top = L[0].map(function (v, i) { return cum[i] + v; });
        var path = pathLine(top.map(function (v, i) { return [x(i), y(v)]; })) + ' ' + pathLine(cum.slice().reverse().map(function (v, i) { return [x(n - 1 - i), y(v)]; })).replace('M', 'L') + 'Z';
        s += el('path', { d: path, fill: L[1] || L[2], 'fill-opacity': L[1] ? .85 : 1, stroke: t.text, 'stroke-opacity': .3, 'stroke-width': .6 });
        s += T(x(n - 1) + 6, y((top[n - 1] + cum[n - 1]) / 2) + 4, L[3] + ' ' + Math.round(L[0][n - 1]) + '%', { fam: 'serif', size: 10, w: 700, fill: li === 0 ? t.accent : t.text });
        cum = top;
      });
      return frame(t, s + footer(t, '층 끝에 직접 라벨 · 패턴 = 명목 범주'));
    } });

  spec({ id: 'combo', tier: 'guarded', family: '시간', name: 'combo',
    when: '부피·건수(막대) × 수준(선), 이중 축',
    absorbed: '막대는 캡슐 상단 + 농도 .24, 최고 막대만 accent 값. 선은 실선, 사건은 vline annotation',
    draw: function (t) {
      var bars = [22, 31, 45, 58, 52, 66, 74, 69, 61, 55, 48, 40], rate = [4, 5, 7, 12, 26, 44, 58, 66, 71, 74, 78, 80], x = function (i) { return 36 + i * 24; }, y = d3.scaleLinear().domain([0, 84]).range([192, 34]), s = '';
      bars.forEach(function (v, i) { var peak = i === 6; s += el('rect', { x: x(i), y: y(v), width: 14, height: 192 - y(v), rx: 7, fill: peak ? t.accent : t.text, 'fill-opacity': peak ? 1 : .24 }) + el('rect', { x: x(i), y: 185, width: 14, height: 7, fill: peak ? t.accent : t.text, 'fill-opacity': peak ? 1 : .24 }); if (peak) s += T(x(i) + 7, y(v) - 6, v, { fam: 'serif', size: 11, w: 700, anchor: 'middle', fill: t.accent }); });
      s += el('path', { d: pathLine(rate.map(function (v, i) { return [x(i) + 7, y(v)]; })), fill: 'none', stroke: t.text, 'stroke-width': 1.6 });
      s += el('line', { x1: x(4) - 5, y1: 26, x2: x(4) - 5, y2: 192, stroke: t.down, 'stroke-width': 1.1, 'stroke-dasharray': '4 3' }) + T(x(4), 22, '봉쇄 선언', { size: 8.5, fill: t.down });
      s += T(x(11) + 18, y(80) + 4, '0.80%', { fam: 'serif', size: 12, w: 700, fill: t.text }) + zero(30, 192, 330, 192, t);
      return frame(t, s + footer(t, '막대 = 거래대금(좌) · 선 = 외국인 비중(우)'));
    } });

  spec({ id: 'connected_scatter', tier: 'guarded', family: '시간', name: 'connected_scatter',
    when: '두 변수의 시간 궤적 (금리 × 환율 12개월)',
    absorbed: '경로 실선 + 시작 속빈 원 · 끝 채운 accent 원. 중간 점은 작은 농도 점, 전환점만 라벨',
    draw: function (t) {
      var r = rng(4), pts = [], gx = 3.4, gy = 1400; for (var i = 0; i < 12; i++) { gx += (r() - .35) * .16; gy += (r() - .3) * 28; pts.push([gx, gy]); }
      var x = d3.scaleLinear().domain(d3.extent(pts, function (d) { return d[0]; })).nice().range([50, 320]), y = d3.scaleLinear().domain(d3.extent(pts, function (d) { return d[1]; })).nice().range([190, 34]), s = '';
      x.ticks(3).forEach(function (v) { s += T(x(v), 206, v.toFixed(2) + '%', { size: 8.5, anchor: 'middle', fill: t.muted }); });
      y.ticks(4).forEach(function (v) { s += grid(46, y(v), 330, y(v), t) + T(42, y(v) + 3, d3.format(',')(v), { size: 8, anchor: 'end', fill: t.muted }); });
      s += el('path', { d: pathLine(pts.map(function (d) { return [x(d[0]), y(d[1])]; })), fill: 'none', stroke: t.text, 'stroke-width': 1.3 });
      pts.forEach(function (d, i) { if (i > 0 && i < 11) s += dot(x(d[0]), y(d[1]), 2.4, t.text, .7); });
      s += hollow(x(pts[0][0]), y(pts[0][1]), 4.5, t) + T(x(pts[0][0]) - 8, y(pts[0][1]) + 4, '1월', { size: 9, anchor: 'end', fill: t.muted });
      s += dot(x(pts[11][0]), y(pts[11][1]), 5, t.accent, 1) + T(x(pts[11][0]) + 9, y(pts[11][1]) + 4, '12월', { fam: 'serif', size: 11, w: 700, fill: t.accent });
      return frame(t, s + footer(t, '속빈 원 = 시작 · 채운 원 = 현재 · x 금리 y 환율'));
    } });

  spec({ id: 'calendar_heat', tier: 'new', family: '시간', name: 'calendar_heat (v8.6 신설)',
    when: "일별 값 60일 이상, '언제 몰렸나'. 시장 종목 |등락률| 은 결정적 자동 주입",
    absorbed: 'L17 Calendar Heat / F10 Dot Heat — 주 열 × 요일 행, 점 농도 5분위, 최대일 점선 링 + 라벨, 주말 속빈',
    draw: function (t) {
      var days = isoDays(126, '2026-04-06T00:00:00Z'), r = rng(13), vals = days.map(function (d) { var wk = d.getUTCDay() === 0 || d.getUTCDay() === 6; return wk ? null : Math.abs(r() - .5) * 4 * (r() > .85 ? 2.5 : 1); });
      var q = d3.scaleQuantile().domain(vals.filter(function (v) { return v != null; })).range([.14, .3, .48, .7, 1]), s = '', cell = 14, ox = 40, oy = 36;
      var peak = d3.maxIndex(vals.map(function (v) { return v == null ? -1 : v; }));
      days.forEach(function (d, i) {
        var col = Math.floor(i / 7), row = (d.getUTCDay() + 6) % 7, cx = ox + col * cell + 6, cy = oy + row * cell + 6;
        if (vals[i] == null) s += el('circle', { cx: cx, cy: cy, r: 4, fill: 'none', stroke: t.text, 'stroke-opacity': .18, 'stroke-width': .7 });
        else s += dot(cx, cy, 4.4, t.text, q(vals[i]));
        if (d.getUTCDate() <= 7 && row === 0) s += T(cx - 6, oy - 8, (d.getUTCMonth() + 1) + '월', { size: 8.5, fill: t.muted, ls: '.06em' });
      });
      ['월', '수', '금'].forEach(function (w, i) { s += T(ox - 8, oy + i * 2 * cell + 9.5, w, { size: 8.5, anchor: 'end', fill: t.muted }); });
      var pc = Math.floor(peak / 7), pr = (days[peak].getUTCDay() + 6) % 7, px = ox + pc * cell + 6, py = oy + pr * cell + 6;
      s += el('circle', { cx: px, cy: py, r: 7, fill: 'none', stroke: t.accent, 'stroke-width': 1.2, 'stroke-dasharray': '2 2' });
      s += el('line', { x1: px, y1: py + 8, x2: px, y2: oy + 7 * cell + 8, stroke: t.accent, 'stroke-width': .8, 'stroke-dasharray': '2 2' }) + T(px, oy + 7 * cell + 20, '최대 ' + iso(days[peak]).slice(5).replace('-', '/') + ' · ' + vals[peak].toFixed(1) + '%', { fam: 'serif', size: 10.5, w: 700, anchor: 'middle', fill: t.accent });
      return frame(t, s + footer(t, '점 하나 = 하루 · 진할수록 등락 폭 큼 · 속빈 = 휴장'));
    } });

  spec({ id: 'small_multiples', tier: 'guarded', family: '시간', name: 'small_multiples',
    when: '같은 축으로 4~8 패널 반복 비교',
    absorbed: '패널마다 끝값 세리프 + 최고점 점. 주인공 패널 1개만 accent 선',
    draw: function (t) {
      var names = ['한국', '미국', '유로존', '일본'], s = '';
      names.forEach(function (n, i) {
        var ox = 20 + (i % 2) * 170, oy = 22 + Math.floor(i / 2) * 96, v = series(24, 100, i === 0 ? .004 : -.002, .05, 30 + i), x = d3.scaleLinear().domain([0, 23]).range([ox + 6, ox + 140]), y = d3.scaleLinear().domain([80, 125]).range([oy + 72, oy + 18]);
        s += T(ox + 6, oy + 10, n, { size: 9.5, w: 700, fill: i === 0 ? t.accent : t.text }) + grid(ox + 6, y(100), ox + 140, y(100), t);
        s += el('path', { d: pathLine(v.map(function (d, k) { return [x(k), y(d)]; })), fill: 'none', stroke: i === 0 ? t.accent : t.text, 'stroke-width': 1.3, 'stroke-opacity': i === 0 ? 1 : .8 });
        s += T(x(23) + 4, y(v[23]) + 3.5, fmt(v[23]), { fam: 'serif', size: 10, w: 700, fill: i === 0 ? t.accent : t.text });
      });
      return frame(t, s + footer(t, '기준 100 · 같은 축 · 주인공 패널만 액센트'));
    } });

  spec({ id: 'gantt', tier: 'safe', family: '시간', name: 'gantt',
    when: '사건 구간 (길이 0 이벤트 모음은 금지, CHART-AP-15)',
    absorbed: '막대 캡슐(rx = h/2), 진행 중 구간은 hatch, 현재 시점 vline. 축은 월 3 tick',
    draw: function (t) {
      var rows = [['1차 실무협상', 0, 34], ['고위급 회담', 30, 52], ['잠정 합의 검토', 50, 88], ['발효 목표', 84, 100]], x = d3.scaleLinear().domain([0, 100]).range([118, 330]), s = '';
      s += el('defs', {}, el('pattern', { id: 'gt-ht', patternUnits: 'userSpaceOnUse', width: 2.4, height: 2.4, patternTransform: 'rotate(45)' }, el('line', { x1: 0, y1: 0, x2: 0, y2: 2.4, stroke: t.accent, 'stroke-width': .85 })));
      rows.forEach(function (r, i) {
        var y = 34 + i * 38, w = x(r[2]) - x(r[1]), open = i === 3;
        s += T(x(0) - 10, y + 11, r[0], { anchor: 'end', size: 10, fill: t.text, w: i === 2 ? 700 : 400 });
        s += el('rect', { x: x(r[1]), y: y, width: w, height: 16, rx: 8, fill: open ? 'url(#gt-ht)' : (i === 2 ? t.accent : t.text), 'fill-opacity': open ? 1 : (i === 2 ? .95 : .3) });
      });
      s += el('line', { x1: x(64), y1: 24, x2: x(64), y2: 196, stroke: t.down, 'stroke-width': 1.1, 'stroke-dasharray': '4 3' }) + T(x(64) + 4, 22, '발행일', { size: 8.5, fill: t.down });
      ['4월', '5월', '6월', '7월'].forEach(function (m, i) { s += T(x(i * 33), 208, m, { size: 8.5, anchor: 'middle', fill: t.muted }); });
      return frame(t, s + footer(t, '캡슐 = 구간 · 빗금 = 아직 열린 구간'));
    } });

  spec({ id: 'combo_candle', tier: 'injected', family: '시간', name: 'combo_candle (브리핑 주입)',
    when: '장마감 브리핑 — 지수 봉 + 비율 선 (코드가 결정적으로 꽂음)',
    absorbed: '둥근 몸통 캔들 + 선은 accent. 두 축 라벨은 끝값에만',
    draw: function (t) {
      var r = rng(17), c = 3100, rows = []; for (var i = 0; i < 20; i++) { var o = c, cl = o * (1 + (r() - .48) * .03), hi = Math.max(o, cl) * (1 + r() * .008), lo = Math.min(o, cl) * (1 - r() * .008); rows.push([o, hi, lo, cl]); c = cl; }
      var ratio = series(20, 34, .002, .02, 18), x = d3.scalePoint().domain(d3.range(20)).range([40, 300]), y = d3.scaleLinear().domain([d3.min(rows, function (d) { return d[2]; }) * .99, d3.max(rows, function (d) { return d[1]; }) * 1.01]).range([196, 40]), yr = d3.scaleLinear().domain(d3.extent(ratio)).range([196, 40]), s = '';
      rows.forEach(function (d, i) { var up = d[3] >= d[0], col = up ? t.up : t.down, top = y(Math.max(d[0], d[3])), h = Math.max(2, Math.abs(y(d[0]) - y(d[3]))); s += el('line', { x1: x(i), y1: y(d[1]), x2: x(i), y2: y(d[2]), stroke: col, 'stroke-width': 1 }) + el('rect', { x: x(i) - 4, y: top, width: 8, height: h, rx: Math.min(4, h / 2), fill: col }); });
      s += el('path', { d: pathLine(ratio.map(function (v, i) { return [x(i), yr(v)]; })), fill: 'none', stroke: t.accent, 'stroke-width': 1.6 });
      s += T(x(19) + 8, yr(ratio[19]) + 4, '외인 ' + fmt(ratio[19]) + '%', { fam: 'serif', size: 10.5, w: 700, fill: t.accent }) + T(x(19) + 8, y(rows[19][3]) + 4, d3.format(',.0f')(rows[19][3]), { fam: 'serif', size: 10.5, w: 700, fill: t.text });
      return frame(t, s + footer(t, '봉 = 코스피 · 선 = 외국인 보유 비중'));
    } });

  spec({ id: 'iv_skew', tier: 'injected', family: '시간', name: 'iv_skew (브리핑 주입)',
    when: '옵션 데스크 — 행사가별 프리미엄(상) + 변동성 스큐(하) 2단',
    absorbed: '2단 패널 공유 x 축. 상단 막대는 캡슐 상단, 하단 스큐는 점+선. ATM 세로 점선',
    draw: function (t) {
      var ks = [400, 405, 410, 415, 420, 425, 430, 435, 440], prem = [1.2, 2.1, 3.6, 6.2, 9.8, 6.4, 3.9, 2.3, 1.4], iv = [21, 19.5, 18.2, 17.4, 17, 17.3, 18, 19.2, 20.6], x = d3.scalePoint().domain(ks).range([50, 320]), s = '';
      var yp = d3.scaleLinear().domain([0, 11]).range([100, 30]), yv = d3.scaleLinear().domain([16, 22]).range([196, 122]);
      prem.forEach(function (v, i) { var atm = i === 4; s += el('rect', { x: x(ks[i]) - 6, y: yp(v), width: 12, height: 100 - yp(v), rx: 6, fill: atm ? t.accent : t.text, 'fill-opacity': atm ? 1 : .28 }) + el('rect', { x: x(ks[i]) - 6, y: 94, width: 12, height: 6, fill: atm ? t.accent : t.text, 'fill-opacity': atm ? 1 : .28 }); });
      s += T(x(ks[4]), yp(prem[4]) - 6, prem[4], { fam: 'serif', size: 10.5, w: 700, anchor: 'middle', fill: t.accent }) + T(44, 34, '프리미엄', { size: 8.5, anchor: 'end', fill: t.muted });
      s += el('path', { d: pathLine(iv.map(function (v, i) { return [x(ks[i]), yv(v)]; })), fill: 'none', stroke: t.text, 'stroke-width': 1.4 });
      iv.forEach(function (v, i) { s += dot(x(ks[i]), yv(v), 3, i === 4 ? t.accent : t.text, 1); });
      s += T(44, 126, 'IV %', { size: 8.5, anchor: 'end', fill: t.muted }) + el('line', { x1: x(420), y1: 24, x2: x(420), y2: 200, stroke: t.text, 'stroke-opacity': .3, 'stroke-dasharray': '2 3' }) + T(x(420), 20, 'ATM 420', { size: 8.5, anchor: 'middle', fill: t.muted });
      ks.forEach(function (k, i) { if (i % 2 === 0) s += T(x(k), 210, k, { size: 8, anchor: 'middle', fill: t.muted }); });
      return frame(t, s + footer(t, '상단 옵션 가격 · 하단 변동성 스큐 · 행사가 공유'));
    } });

  // ── D. 분포 · 관계 · 강도 ────────────────────────────────────
  spec({ id: 'histogram', tier: 'new', family: '분포 · 관계', name: 'histogram (v8.6 신설)',
    when: '순서 있는 구간(연령대·금액대) × 건수. 출처에 구간 집계가 있을 때만. bar 로 넣던 구간 데이터는 type-fit 이 재배치',
    absorbed: 'F14 Rung Histogram — 세로 칸 열, 최빈 열만 진하게 + 값, 중앙값 위치 vline annotation',
    draw: function (t) {
      var bins = [['~1천', 4], ['1~2천', 9], ['2~3천', 15], ['3~5천', 22], ['5~7천', 14], ['7천~1억', 9], ['1~2억', 6], ['2억~', 3]], unit = niceUnit(22, 40), base = 190, colW = 26, gapX = (W - 60 - colW * bins.length) / (bins.length - 1), s = '', peak = 3;
      bins.forEach(function (b, i) {
        var x = 30 + i * (colW + gapX), m = marks({ kind: 'rung', x: x, y: base, value: b[1], unit: unit, gap: 4.6, len: colW, op: i === peak ? 1 : .5 }, t);
        s += m.svg + T(x + colW / 2, base + 15, b[0], { size: 8, anchor: 'middle', fill: t.muted });
        if (i === peak) s += T(x + colW / 2, m.end - 7, b[1] + '%', { fam: 'serif', size: 12, w: 700, anchor: 'middle', fill: t.accent });
      });
      var mx = 30 + 3.6 * (colW + gapX) + colW / 2;
      s += el('line', { x1: mx, y1: 40, x2: mx, y2: base, stroke: t.text, 'stroke-opacity': .5, 'stroke-dasharray': '2 3' }) + T(mx + 5, 38, '절반이 여기까지', { size: 8.5, fill: t.text, ls: '.04em' });
      s += zero(24, base + 3, W - 24, base + 3, t);
      return frame(t, s + footer(t, '한 칸 = 차주 100명 중 ' + unit + '명 · 대출 잔액 구간'));
    } });

  spec({ id: 'scatter', tier: 'guarded', family: '분포 · 관계', name: 'scatter · 추선 (≤20 점 기본)',
    when: '두 변수 상관, 점 20개 이하. 더 많으면 기존 산점',
    absorbed: 'F8 Plumb Scatter — 점마다 바닥까지 추선, 점 크기 균일·농도 7단(y 순), 상위 2점만 라벨, x 축 양 끝 말',
    draw: function (t) {
      var r = rng(23), pts = d3.range(12).map(function (i) { return { x: .1 + i * .075 + r() * .05, y: .2 + r() * .7, n: ['한국', '대만', '미국', '일본', '독일', '중국', '인도', '영국', '프랑스', '호주', '캐나다', '브라질'][i] }; });
      var x = d3.scaleLinear().domain([0, 1]).range([40, 320]), y = d3.scaleLinear().domain([0, 1]).range([190, 34]), order = pts.slice().sort(function (a, b) { return b.y - a.y; }), lad = ladder(7), s = '';
      pts.forEach(function (p) { var rank = order.indexOf(p); s += el('line', { x1: x(p.x), y1: 192, x2: x(p.x), y2: y(p.y), stroke: t.text, 'stroke-opacity': .22, 'stroke-width': .6 }) + dot(x(p.x), y(p.y), 5, rank === 0 ? t.accent : t.text, rank === 0 ? 1 : lad[Math.min(6, rank)]); if (rank < 2) s += T(x(p.x), y(p.y) - 9, p.n + ' · ' + Math.round(p.y * 100), { fam: 'serif', size: 10.5, w: 700, anchor: 'middle', fill: rank === 0 ? t.accent : t.text }); });
      s += zero(36, 192, 326, 192, t) + T(40, 206, '낮은 투자 강도', { size: 8.5, fill: t.muted, ls: '.06em' }) + T(320, 206, '높은 투자 강도', { size: 8.5, anchor: 'end', fill: t.muted, ls: '.06em' });
      s += T(30, 40, '성장률 ↑', { size: 8.5, fill: t.muted, anchor: 'start' });
      return frame(t, s + footer(t, '점마다 추선 · 바닥에서 x 를 읽는다'));
    } });

  spec({ id: 'bubble', tier: 'safe', family: '분포 · 관계', name: 'bubble',
    when: '3변수 — 확률 × 영향 × 크기',
    absorbed: '버블은 속빈 원 + 농도 채움, 주인공만 accent. 사분면 점선, 라벨은 버블 위',
    draw: function (t) {
      var pts = [['전면 확전', .22, .9, 30], ['부분 타결', .55, .55, 44], ['장기 교착', .7, .35, 38], ['조기 합의', .18, .3, 20]], x = d3.scaleLinear().domain([0, 1]).range([40, 320]), y = d3.scaleLinear().domain([0, 1]).range([190, 34]), s = '';
      s += el('line', { x1: x(.5), y1: 30, x2: x(.5), y2: 192, stroke: t.text, 'stroke-opacity': .2, 'stroke-dasharray': '2 3' }) + el('line', { x1: 40, y1: y(.5), x2: 320, y2: y(.5), stroke: t.text, 'stroke-opacity': .2, 'stroke-dasharray': '2 3' });
      pts.forEach(function (p, i) { var key = i === 1; s += el('circle', { cx: x(p[1]), cy: y(p[2]), r: p[3] / 2, fill: key ? t.accent : t.text, 'fill-opacity': key ? .35 : .16, stroke: key ? t.accent : t.text, 'stroke-width': 1.3 }); s += T(x(p[1]), y(p[2]) - p[3] / 2 - 6, p[0], { fam: 'serif', size: 10.5, w: 700, anchor: 'middle', fill: key ? t.accent : t.text }); });
      s += T(40, 206, '확률 낮음', { size: 8.5, fill: t.muted, ls: '.06em' }) + T(320, 206, '확률 높음', { size: 8.5, anchor: 'end', fill: t.muted, ls: '.06em' }) + T(36, 40, '영향 ↑', { size: 8.5, fill: t.muted });
      return frame(t, s + footer(t, '크기 = 시장 영향 · 속빈 원 + 농도 채움'));
    } });

  spec({ id: 'heatmap', tier: 'safe', family: '분포 · 관계', name: 'heatmap · 둥근 칸 (≤60 칸 기본)',
    when: '두 축 교차 강도, 칸 60개 이하. 더 많으면 기존 농도 격자',
    absorbed: 'G20 Matrix Heat (Glance) — 둥근 칸(rx 8) + 6px 틈, 칸 안 숫자 직독, 진한 칸은 글자 반전',
    draw: function (t) {
      var cols = ['에디터', '보드', '문서', '채팅', '금고'], rowsN = ['v2.0', 'v1.9', 'v1.8', 'v1.7'], vals = [[87, 75, 64, 39, 26], [79, 69, 58, 36, 21], [73, 64, 45, 24, 9], [70, 56, 37, 14, 2]], q = d3.scaleQuantile().domain(d3.merge(vals)).range([.12, .28, .48, .7, 1]), s = '', cw = 50, ch = 38, ox = 62, oy = 30;
      cols.forEach(function (c, i) { s += T(ox + i * (cw + 6) + cw / 2, oy - 10, c, { size: 9, anchor: 'middle', fill: t.muted }); });
      vals.forEach(function (row, r) {
        s += T(ox - 10, oy + r * (ch + 6) + ch / 2 + 4, rowsN[r], { size: 9.5, anchor: 'end', fill: t.text, w: r === 0 ? 700 : 400 });
        row.forEach(function (v, c) { var op = q(v); s += el('rect', { x: ox + c * (cw + 6), y: oy + r * (ch + 6), width: cw, height: ch, rx: 8, fill: t.text, 'fill-opacity': op }) + T(ox + c * (cw + 6) + cw / 2, oy + r * (ch + 6) + ch / 2 + 4.5, v, { fam: 'serif', size: 12.5, w: 700, anchor: 'middle', fill: inv(t, op) }); });
      });
      return frame(t, s + footer(t, '농도 = 사용률 · 최신 버전이 진하다'));
    } });

  spec({ id: 'spectrum', tier: 'new2', family: '분포 · 관계', name: 'spectrum (v8.7 2차)',
    when: '양 끝이 둘 다 정답인 척도 — 정책 성향·국가 입장·브랜드 포지션, 경쟁자 대조',
    absorbed: 'L7 Brand Spectrum — 양극 실선 축, 주인공 큰 점 + 비교 대상 작은 농도 점, 축 끝 캡션',
    draw: function (t) {
      var rows = [['확장 재정', '긴축', .35, [-.2, .1, .55]], ['개입', '시장 자율', -.4, [-.1, .2, .5]], ['동맹 우선', '실용 외교', .1, [-.5, -.3, .4]], ['보편 복지', '선별 복지', -.55, [-.2, .3, .6]]], x = d3.scaleLinear().domain([-1, 1]).range([90, 270]), s = '';
      rows.forEach(function (r, i) {
        var y = 36 + i * 44;
        s += el('line', { x1: x(-1), y1: y, x2: x(1), y2: y, stroke: t.text, 'stroke-opacity': .35, 'stroke-width': 1 }) + el('line', { x1: x(-1), y1: y - 5, x2: x(-1), y2: y + 5, stroke: t.text, 'stroke-opacity': .5 }) + el('line', { x1: x(1), y1: y - 5, x2: x(1), y2: y + 5, stroke: t.text, 'stroke-opacity': .5 });
        r[3].forEach(function (v) { s += dot(x(v), y, 3.2, t.text, .45); });
        s += dot(x(r[2]), y, 7, t.accent, 1);
        s += T(x(-1) - 10, y + 4, r[0], { size: 9.5, anchor: 'end', fill: t.text, ls: '.02em' }) + T(x(1) + 10, y + 4, r[1], { size: 9.5, fill: t.text, ls: '.02em' });
      });
      s += dot(120, 212, 5, t.accent, 1) + T(130, 215, '집권당', { size: 8.5, fill: t.muted }) + dot(180, 212, 3, t.text, .45) + T(188, 215, '야 3당', { size: 8.5, fill: t.muted });
      return frame(t, s + footer(t, '양 끝이 둘 다 정답인 척도 · 큰 점 = 주인공'));
    } });

  spec({ id: 'gauge', tier: 'new2', family: '분포 · 관계', name: 'gauge (v8.7 2차)',
    when: '단일 KPI 대 목표 — 지지율·달성률·가동률. 여러 항목이면 bullet',
    absorbed: 'F11 Tick Gauge — 반원 100 눈금, 채운 눈금 = 실적, 중앙 큰 숫자(--text, 액센트 금지), 남은 눈금 캡션',
    draw: function (t) {
      var cx = 180, cy = 168, r = 100, pct = 73, s = '';
      for (var i = 0; i <= 100; i++) { var a = Math.PI + (i / 100) * Math.PI, big = i % 25 === 0, len = big ? 18 : 11, on = i <= pct; s += el('line', { x1: cx + Math.cos(a) * r, y1: cy + Math.sin(a) * r, x2: cx + Math.cos(a) * (r + len), y2: cy + Math.sin(a) * (r + len), stroke: t.text, 'stroke-opacity': on ? 1 : .18, 'stroke-width': big ? 1.6 : 1 }); }
      var pa = Math.PI + (pct / 100) * Math.PI; s += dot(cx + Math.cos(pa) * (r + 24), cy + Math.sin(pa) * (r + 24), 3.5, t.accent, 1);
      s += T(cx, cy - 6, pct + '%', { fam: 'serif', size: 34, w: 700, anchor: 'middle', fill: t.text }) + T(cx, cy + 12, '목표까지 ' + (100 - pct) + ' 눈금', { size: 9, anchor: 'middle', fill: t.muted, ls: '.06em' });
      s += T(cx - r - 4, cy + 14, '0', { size: 8.5, anchor: 'middle', fill: t.muted }) + T(cx + r + 4, cy + 14, '100', { size: 8.5, anchor: 'middle', fill: t.muted });
      return frame(t, s + footer(t, '눈금 하나 = 목표의 1% · 채운 눈금 = 달성'));
    } });

  spec({ id: 'indicator', tier: 'injected', family: '분포 · 관계', name: 'indicator (브리핑 주입)',
    when: '부호 한 줄 지표 (브리핑 헤더)',
    absorbed: '큰 숫자는 --text, 부호·등락은 --up/--down 작은 캡슐 배지. 스파크라인은 hairline',
    draw: function (t) {
      var items = [['코스피', '3,187.4', '+1.24%', true], ['코스닥', '842.1', '-0.38%', false], ['원/달러', '1,392.5', '+4.5원', false]], s = '';
      items.forEach(function (it, i) {
        var y = 40 + i * 62, col = it[3] ? t.up : t.down;
        s += T(24, y, it[0], { size: 9.5, fill: t.muted, ls: '.06em' }) + T(24, y + 26, it[1], { fam: 'serif', size: 22, w: 700, fill: t.text });
        s += el('rect', { x: 150, y: y + 10, width: 62, height: 18, rx: 9, fill: col, 'fill-opacity': .16 }) + T(181, y + 23, it[2], { fam: 'serif', size: 11, w: 700, anchor: 'middle', fill: col });
        var v = series(20, 100, it[3] ? .002 : -.002, .03, 40 + i), x = d3.scaleLinear().domain([0, 19]).range([236, 336]), yy = d3.scaleLinear().domain(d3.extent(v)).range([y + 28, y + 4]);
        s += el('path', { d: pathLine(v.map(function (d, k) { return [x(k), yy(d)]; })), fill: 'none', stroke: t.text, 'stroke-opacity': .6, 'stroke-width': 1 }) + dot(x(19), yy(v[19]), 2.4, col, 1);
      });
      return frame(t, s + footer(t, '큰 숫자 = --text · 등락만 색'));
    } });

  spec({ id: 'waterfall', tier: 'guarded', family: '분포 · 관계', name: 'waterfall (기본 유지 · rung 옵션)',
    when: '증감 분해 (매출 → 순이익). 부호는 라벨에도',
    absorbed: 'F9 Rung Waterfall — texture:"rung" 옵션일 때만: 채운 칸 = 더하기, 점선 칸 = 빼기. 기본 렌더는 CHART-AP-20~27 표면이라 불변',
    draw: function (t) {
      var items = [['총매출', 42, 'total'], ['환불', -6, 'neg'], ['원가', -11, 'neg'], ['운영비', -8, 'neg'], ['순이익', 17, 'total']], unit = 1, base = 190, colW = 34, gapX = (W - 60 - colW * 5) / 4, run = 0, s = '';
      items.forEach(function (it, i) {
        var x = 30 + i * (colW + gapX), v = Math.abs(it[1]), start = it[2] === 'total' ? 0 : (it[1] < 0 ? run + it[1] : run);
        for (var k = 0; k < v; k++) { var yy = base - (start + k) * 3.4 - 2, neg = it[1] < 0; s += el('line', { x1: x, y1: yy, x2: x + colW, y2: yy, stroke: it[2] === 'total' ? t.text : (neg ? t.down : t.accent), 'stroke-opacity': it[2] === 'total' ? (i === 0 ? .9 : 1) : .85, 'stroke-width': (k + 1) % 5 === 0 ? 1.5 : .9, 'stroke-dasharray': neg ? '2 2' : undefined }); }
        if (it[2] !== 'total') run += it[1]; else if (i === 0) run = it[1];
        var topY = base - (start + v) * 3.4 - 8;
        s += T(x + colW / 2, topY, (it[1] > 0 && it[2] !== 'total' ? '+' : '') + it[1], { fam: 'serif', size: 11.5, w: 700, anchor: 'middle', fill: it[2] === 'total' ? t.text : (it[1] < 0 ? t.down : t.accent) }) + T(x + colW / 2, base + 15, it[0], { size: 8.5, anchor: 'middle', fill: t.muted });
        if (i > 0 && i < 4) s += el('line', { x1: x - gapX, y1: base - (run - (it[1] < 0 ? 0 : it[1])) * 3.4 - 2, x2: x, y2: base - (run - (it[1] < 0 ? 0 : it[1])) * 3.4 - 2, stroke: t.text, 'stroke-opacity': .25, 'stroke-width': .6 });
      });
      s += zero(24, base + 3, W - 24, base + 3, t);
      return frame(t, s + footer(t, '채운 칸 = 더하기 · 점선 칸 = 빼기 · 한 칸 = 1천억'));
    } });

  spec({ id: 'sankey', tier: 'guarded', family: '분포 · 관계', name: 'sankey',
    when: '재무 분해·자본 배분 (금융 보고서 필수)',
    absorbed: 'G22 Aggregate Sankey — 노드 캡슐 바, 띠 농도 = 출처별 사다리, 라벨은 노드 바깥 세리프 값. 적자 띠 --down',
    draw: function (t) {
      var left = [['검색', 34], ['추천', 27], ['소셜', 18], ['광고', 12], ['기타', 9]], right = [['무료', 55], ['프로', 28], ['팀', 17]], lad = ladder(5), s = '', xl = 96, xr = 250, yl = 26, yr = 26, tot = 100, hh = 170, ln = [], rn = [];
      left.forEach(function (d, i) { var h = d[1] / tot * hh - 4; ln.push([yl, h]); s += el('rect', { x: xl, y: yl, width: 8, height: h, rx: 4, fill: t.text, 'fill-opacity': lad[i] }) + T(xl - 8, yl + h / 2 + 3.5, d[0] + ' · ' + d[1], { size: 9.5, anchor: 'end', fill: t.text }); yl += h + 6; });
      right.forEach(function (d, i) { var h = d[1] / tot * hh - 2; rn.push([yr, h]); s += el('rect', { x: xr, y: yr, width: 8, height: h, rx: 4, fill: i === 0 ? t.accent : t.text, 'fill-opacity': i === 0 ? 1 : .8 }) + T(xr + 16, yr + h / 2 - 4, d[0], { size: 9.5, fill: t.text }) + T(xr + 16, yr + h / 2 + 9, d[1], { fam: 'serif', size: 12, w: 700, fill: i === 0 ? t.accent : t.text }); yr += h + 8; });
      var flows = [[0, 0, 20], [0, 1, 10], [0, 2, 4], [1, 0, 14], [1, 1, 8], [1, 2, 5], [2, 0, 10], [2, 1, 5], [2, 2, 3], [3, 0, 7], [3, 1, 3], [3, 2, 2], [4, 0, 4], [4, 1, 2], [4, 2, 3]], lo = ln.map(function (n) { return n[0]; }), ro = rn.map(function (n) { return n[0]; }), ribbons = '';
      flows.forEach(function (f) { var h = f[2] / tot * hh - 1, y0 = lo[f[0]], y1 = ro[f[1]]; lo[f[0]] += h; ro[f[1]] += h; ribbons += el('path', { d: 'M' + (xl + 8) + ',' + y0 + ' C' + (xl + 80) + ',' + y0 + ' ' + (xr - 80) + ',' + y1 + ' ' + xr + ',' + y1 + ' v' + h + ' C' + (xr - 80) + ',' + (y1 + h) + ' ' + (xl + 80) + ',' + (y0 + h) + ' ' + (xl + 8) + ',' + (y0 + h) + 'Z', fill: t.text, 'fill-opacity': lad[f[0]] * .38 }); });
      return frame(t, ribbons + s + footer(t, '띠 굵기 = 계정 수 · 농도 = 유입 채널'));
    } });

  spec({ id: 'tree', tier: 'new', family: '분포 · 관계', name: 'tree (v8.6 신설)',
    when: '소속·위계 2~3층 — 지배구조·계열사·조직·정책 체계. 대립·동맹 *관계* 는 stakeholder_map',
    absorbed: 'G7 Tree LR — 좌→우 클러스터, 잎 정렬, 가지별 농도 사다리, 잎 라벨 오른쪽 + 메모',
    draw: function (t) {
      var root = { label: '○○지주', children: [
        { label: '금융', children: [{ label: '○○은행', note: '지분 100%' }, { label: '○○증권', note: '지분 63%' }, { label: '○○카드' }] },
        { label: '산업', children: [{ label: '○○중공업', note: '지분 41%' }, { label: '○○에너지' }] },
        { label: '서비스', children: [{ label: '○○리테일' }, { label: '○○물류', note: '신규 편입' }] }] };
      var h = d3.hierarchy(root); d3.cluster().size([H - FOOT - 36, 190])(h);
      var ox = 76, oy = 18, lad = ladder(h.children.length), s = '';
      h.links().forEach(function (L) { var bi = L.target.ancestors().filter(function (a) { return a.depth === 1; })[0], idx = h.children.indexOf(bi); s += el('path', { d: d3.linkHorizontal().x(function (d) { return d.y + ox; }).y(function (d) { return d.x + oy; })(L), fill: 'none', stroke: t.text, 'stroke-opacity': L.source.depth === 0 ? .9 : lad[idx], 'stroke-width': L.source.depth === 0 ? 1.4 : 1 }); });
      h.descendants().forEach(function (n) {
        var x = n.y + ox, y = n.x + oy;
        if (n.depth === 0) s += dot(x, y, 5, t.text, 1) + T(x - 9, y + 4.5, n.data.label, { fam: 'serif', size: 12.5, w: 700, anchor: 'end', fill: t.text });
        else if (n.depth === 1) s += dot(x, y, 3.5, t.text, 1) + T(x - 6, y - 7, n.data.label, { size: 10, w: 600, anchor: 'end', fill: t.text });
        else { var idx = h.children.indexOf(n.parent); s += dot(x, y, 2.5, t.text, lad[idx]) + T(x + 8, y + 3.5, n.data.label, { size: 9.5, fill: t.text }); if (n.data.note) s += T(x + 8 + n.data.label.length * 9.5 + 4, y + 3.5, n.data.note, { size: 8, fill: t.muted }); }
      });
      return frame(t, s + footer(t, '위계 = 좌→우 · 가지마다 농도'));
    } });

  spec({ id: 'stakeholder_map', tier: 'injected', family: '분포 · 관계', name: 'stakeholder_map (르포 전용)',
    when: '르포 행위자 관계도 — 진영 칼럼 결정적 배치, force 금지(CHART-AP-37)',
    absorbed: '노드 카드 캡슐, 엣지 dash 어휘(§6.3) 유지. 국기·로고·사진 슬롯. 변경 없음 — 시트 정합 확인용',
    draw: function (t) {
      var cols = [['한국', '일본'], ['미국'], ['중국', '러시아']], s = '', pos = {};
      cols.forEach(function (c, ci) { c.forEach(function (n, ni) { var x = 60 + ci * 120, y = 60 + ni * 80 + (ci === 1 ? 40 : 0); pos[n] = [x, y]; s += el('rect', { x: x - 34, y: y - 16, width: 68, height: 32, rx: 16, fill: t.text, 'fill-opacity': ci === 1 ? 1 : .12, stroke: t.text, 'stroke-opacity': .5, 'stroke-width': .8 }) + dot(x - 20, y, 7, ci === 1 ? t.card : t.text, ci === 1 ? .9 : .5) + T(x - 8, y + 4, n, { size: 10, w: ci === 1 ? 700 : 500, fill: ci === 1 ? t.card : t.text }); }); });
      var edges = [['한국', '미국', ''], ['일본', '미국', ''], ['미국', '중국', '5,3'], ['중국', '러시아', '2,3'], ['한국', '중국', '1,3']];
      var e = ''; edges.forEach(function (ed) { var a = pos[ed[0]], b = pos[ed[1]]; e += el('line', { x1: a[0] + 34 * Math.sign(b[0] - a[0] || 1), y1: a[1], x2: b[0] - 34 * Math.sign(b[0] - a[0] || 1), y2: b[1], stroke: ed[2] === '5,3' ? t.down : t.text, 'stroke-width': ed[2] === '5,3' ? 2 : 1.3, 'stroke-dasharray': ed[2] || undefined, 'stroke-opacity': .8 }); });
      return frame(t, e + s + footer(t, '실선 동맹 · 긴 점선 대립 · 짧은 점선 영향'));
    } });

  spec({ id: 'choropleth', tier: 'safe', family: '분포 · 관계', name: 'choropleth',
    when: '지역별 단계 구분 (국가 단위). 대륙 간이면 지구본 자동 승격',
    absorbed: 'M1/M2 — 5단 농도 계급 + 최대 지역만 라벨 + 하단 계급 범례. 지도 3색 토큰 유지',
    draw: function (t) {
      var lad = [.12, .28, .48, .7, 1], s = '';
      var shapes = [['M30 60 L90 40 L150 62 L140 120 L80 140 L34 118 Z', 1, 'CA 96k'], ['M150 62 L230 44 L300 70 L290 130 L220 150 L140 120 Z', 3, null], ['M90 140 L150 128 L200 160 L170 200 L100 196 Z', 2, null], ['M220 150 L290 130 L330 170 L300 205 L230 200 Z', 4, null], ['M250 30 L330 24 L338 60 L300 70 L230 44 Z', 0, null]];
      s += el('rect', { x: 14, y: 14, width: 332, height: 198, rx: 4, fill: t['map-water'] });
      shapes.forEach(function (sh) { s += el('path', { d: sh[0], fill: t.text, 'fill-opacity': lad[sh[1]], stroke: t['map-boundary'], 'stroke-width': .8 }); if (sh[2]) s += T(90, 96, sh[2], { fam: 'serif', size: 11, w: 700, anchor: 'middle', fill: t.card }); });
      lad.forEach(function (o, i) { s += el('rect', { x: 24 + i * 26, y: 196, width: 20, height: 8, rx: 2, fill: t.text, 'fill-opacity': o }); });
      s += T(160, 203, '≤9k · 10~20k · 21~38k · 39~64k · 65k+', { size: 7.5, fill: t.muted, ls: '.04em' });
      return frame(t, s + footer(t, '진할수록 많다 · 최대 지역만 라벨'));
    } });

  // ── 흡수 어휘 카드 (§6.6) ─────────────────────────────────────
  var VOCAB = [
    { k: '칸 질감 3종', d: 'tick · rung · dot — 칸 하나 = 정해진 수량, 다섯 번째마다 강조', draw: function (t) {
      var s = ''; var m1 = marks({ kind: 'tick', x: 14, y: 20, value: 17, unit: 1, gap: 7, len: 12 }, t); s += m1.svg + T(150, 24, 'tick', { fam: 'mono', size: 9, fill: t.muted });
      var m2 = marks({ kind: 'dot', x: 16, y: 48, value: 17, unit: 1, gap: 8 }, t); s += m2.svg + T(150, 52, 'dot', { fam: 'mono', size: 9, fill: t.muted });
      for (var i = 0; i < 4; i++) { var m3 = marks({ kind: 'rung', x: 14 + i * 22, y: 100, value: [17, 12, 8, 5][i], unit: 1, gap: 2.6, len: 16 }, t); s += m3.svg; } s += T(150, 90, 'rung', { fam: 'mono', size: 9, fill: t.muted });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } },
    { k: '잉크 사다리 7단', d: '순위 위계 전용 · 1 · .78 · .60 · .44 · .30 · .20 · .12', draw: function (t) {
      var s = ''; LADDER7.forEach(function (o, i) { s += el('rect', { x: 12 + i * 24, y: 20, width: 20, height: 56, rx: 4, fill: t.text, 'fill-opacity': o }) + T(22 + i * 24, 92, o, { size: 7.5, anchor: 'middle', fill: t.muted, fam: 'mono' }); });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } },
    { k: '캡슐', d: 'rx = h/2 · 폭이 높이보다 작으면 최소폭 = 높이 · 캔들 몸통 포함', draw: function (t) {
      var s = capsule(14, 16, 150, 18, t.text, 1) + capsule(14, 42, 90, 18, t.text, .6) + capsule(14, 68, 12, 18, t.text, .3) + T(40, 81, '← 최소폭 클램프', { size: 8.5, fill: t.muted });
      s += el('rect', { x: 150, y: 44, width: 8, height: 40, rx: 4, fill: t.up }) + el('line', { x1: 154, y1: 36, x2: 154, y2: 92, stroke: t.up, 'stroke-width': 1 }) + el('rect', { x: 168, y: 52, width: 8, height: 26, rx: 4, fill: t.down }) + el('line', { x1: 172, y1: 44, x2: 172, y2: 88, stroke: t.down, 'stroke-width': 1 });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } },
    { k: '속빈 · 채움', d: '속빈 = 이전 · 주말 · 미확정 / 채움 = 이후 · 평일 · 확정', draw: function (t) {
      var s = hollow(30, 34, 6, t) + T(44, 38, '이전 · 주말 · 미확정', { size: 9, fill: t.text }) + dot(30, 64, 6, t.text, 1) + T(44, 68, '이후 · 평일 · 확정', { size: 9, fill: t.text }) + hollow(30, 92, 5, t) + [1, 2, 3, 4, 5].map(function (k) { return dot(30 + k * 9, 92, 1.6, t.text, .7); }).join('') + dot(84, 92, 5.2, t.text, 1) + T(98, 96, '덤벨 구슬', { size: 9, fill: t.muted });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } },
    { k: '읽는 법 캡션', d: '9.5px · 자간 .08em · --muted · SVG 하단 중앙 · 라틴은 대문자', draw: function (t) {
      var s = T(95, 40, '한 칸 = 1천억 원 · 다섯 칸마다 긴 눈금', { size: 8.2, anchor: 'middle', fill: t.muted, ls: '.08em' }) + T(95, 64, 'ONE TICK = 1 · DOT EVERY FIFTH', { size: 8.2, anchor: 'middle', fill: t.muted, ls: '.08em' }) + T(95, 88, '속빈 원 = 이전 · 채운 원 = 이후', { size: 8.2, anchor: 'middle', fill: t.muted, ls: '.08em' });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } },
    { k: '한글 라벨 게이트', d: '세로 칸 막대는 라벨 ≤6자 · 항목 ≤8 일 때만. 아니면 가로 tick 으로 결정적 강등', draw: function (t) {
      var s = T(14, 26, '"스타터" (3자) → 세로 OK', { size: 9, fill: t.text }) + T(14, 50, '"디스플레이 장비" (7자) → 가로 강등', { size: 9, fill: t.down }) + T(14, 74, '항목 9개 → 가로 강등', { size: 9, fill: t.down }) + T(14, 98, '최종 방어는 프롬프트가 아니라 렌더러', { size: 8.5, fill: t.muted });
      return el('svg', { viewBox: '0 0 190 110' }, el('rect', { width: 190, height: 110, rx: 5, fill: t['card-deep'] }) + s); } }
  ];

  var TIER_LABEL = { safe: 'safe', guarded: 'guarded', injected: '주입', 'new': 'v8.6 신설', new2: 'v8.7 2차' };

  function drawChartSpecimens(t, id, vocabId) {
    var host = document.getElementById(id); if (!host) return;
    var byFam = {}; SPECS.forEach(function (sp) { (byFam[sp.family] = byFam[sp.family] || []).push(sp); });
    var html = '';
    Object.keys(byFam).forEach(function (fam) {
      html += '<div class="spec-fam">' + fam + ' <span>' + byFam[fam].length + '</span></div><div class="specs">';
      byFam[fam].forEach(function (sp) {
        var svg; try { svg = sp.draw(t); } catch (e) { svg = '<div class="spec-err">' + esc(String(e)) + '</div>'; if (global.console) console.warn('[specimen]', sp.id, e); }
        html += '<div class="spec" data-tier="' + sp.tier + '">' + svg +
          '<div class="spec-h"><span class="spec-id">' + sp.id + (sp.variant ? '<em> · ' + sp.variant + '</em>' : '') + '</span><span class="spec-tier">' + (TIER_LABEL[sp.tier] || sp.tier) + '</span></div>' +
          '<div class="spec-n">' + esc(sp.name) + '</div>' +
          '<div class="spec-w"><b>언제</b> ' + esc(sp.when) + '</div>' +
          '<div class="spec-a"><b>흡수</b> ' + esc(sp.absorbed) + '</div></div>';
      });
      html += '</div>';
    });
    host.innerHTML = html;
    var vh = document.getElementById(vocabId);
    if (vh) vh.innerHTML = VOCAB.map(function (v) { var svg; try { svg = v.draw(t); } catch (e) { svg = ''; } return '<div class="viz-cell">' + svg + '<div class="k">' + v.k + '</div><div class="d">' + v.d + '</div></div>'; }).join('');
  }

  global.CHART_SPECIMENS = SPECS;
  global.drawChartSpecimens = drawChartSpecimens;
})(window);
