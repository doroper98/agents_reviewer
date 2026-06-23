/* charts.js — v4.4.0 zone-based layout + annotations + 11 chart types.
 * v7.9.17 — network(행위자 관계도) 포맷 폐기 (CHART-AP-36) — RENDERERS·drawNetwork 제거.
 * v7.1.0 — 초기 7종 (bar/donut/stacked/bubble/heatmap/waterfall) 비주얼
 *          리디자인 (사용자 승인, samples/chart_redesign_v7_compare.html 목업 기준).
 *          해치 = 카테고리 전용으로 환원, 서수/강도 = 단일 잉크 농도 사다리,
 *          값 = 세리프 직접 라벨, 그리드 최소·0-기준선 crisp. 과거 발행본 소급 적용.
 * v7.0.0 — annotation 레이어를 cartesian 전 type 으로 개방 (area/candle/scatter/
 *          stacked_area/lollipop/range_bar 추가 wiring — 기존 payload 무변경이면
 *          렌더 결과 불변, additive) + 신규 3종 (bump/bullet/connected_scatter).
 *
 * 핵심 설계: 모든 차트 SVG = 4 zone 으로 명확 분리, annotation 끼리 절대 겹치지
 * 않도록 OccupancyTracker (bbox 충돌 검사) + staggering fallback.
 *
 *   ┌─────────────────────────────────────────┐
 *   │ TOP MARGIN (h=56)                        │  vline callout, band 라벨
 *   ├──────┬─────────────────────────────┬─────┤
 *   │ LEFT │      DATA ZONE              │RIGHT│  RIGHT: end label, forecast cone
 *   │ axis │      (라벨 절대 X)            │ end │
 *   ├──────┴─────────────────────────────┴─────┤
 *   │ BOTTOM (h=32) — x axis only              │
 *   └─────────────────────────────────────────┘
 *
 * Mono Theme: docs/MONO_THEME_GUIDE.md §4 패턴 시스템 적용.
 * type: bar / donut / line / gantt / stacked / bubble / heatmap
 *          + dual_line / forecast / choropleth (Tier 2 신규).
 */
(function () {
  if (!window.d3) { console.warn('[charts] d3 not loaded'); return; }
  const d3 = window.d3;

  // ============================================================
  // Theme + Patterns
  // ============================================================
  function readTheme(rootEl) {
    const cs = getComputedStyle(rootEl || document.documentElement);
    const r = (n) => cs.getPropertyValue(n).trim();
    return {
      bg: r('--bg') || '#3D1820',
      card: r('--card') || '#4A222E',
      text: r('--text') || '#EFE5D1',
      muted: r('--muted') || '#A88E7A',
      accent: r('--accent') || '#D4A858',
      up: r('--up') || '#A8B582',
      down: r('--down') || '#C9837A',
      border: r('--border') || '#6E3340',
    };
  }

  function definePatterns(svg, t, prefix) {
    const defs = svg.append('defs');
    const id = (n) => `${prefix}-${n}`;
    defs.append('pattern').attr('id', id('hatch-tight')).attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 2.4).attr('height', 2.4).attr('patternTransform', 'rotate(45)')
      .append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 2.4)
      .attr('stroke', t.text).attr('stroke-width', 0.85);
    defs.append('pattern').attr('id', id('hatch-wide')).attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 3.8).attr('height', 3.8).attr('patternTransform', 'rotate(45)')
      .append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 3.8)
      .attr('stroke', t.text).attr('stroke-width', 0.7);
    defs.append('pattern').attr('id', id('dots')).attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 2.4).attr('height', 2.4)
      .append('circle').attr('cx', 1.2).attr('cy', 1.2).attr('r', 0.22).attr('fill', t.text);
    defs.append('pattern').attr('id', id('accent-hatch')).attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 2.4).attr('height', 2.4).attr('patternTransform', 'rotate(45)')
      .append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 2.4)
      .attr('stroke', t.accent).attr('stroke-width', 0.85);
    return id;
  }

  const PATTERN_SEQ = ['hatch-tight', 'accent-hatch', 'hatch-wide', 'dots'];

  // ============================================================
  // Zone engine + Occupancy tracker (collision detection)
  // ============================================================
  function computeZones(W, H, opts) {
    opts = opts || {};
    const top    = opts.top    != null ? opts.top    : 56;
    const right  = opts.right  != null ? opts.right  : 100;
    const bottom = opts.bottom != null ? opts.bottom : 32;
    const left   = opts.left   != null ? opts.left   : 80;
    return {
      W: W, H: H,
      top: top, right: right, bottom: bottom, left: left,
      data: {
        x: left, y: top,
        w: W - left - right,
        h: H - top - bottom
      },
      topMargin:    { x: 0, y: 0, w: W, h: top },
      rightMargin:  { x: W - right, y: top, w: right, h: H - top - bottom },
      bottomMargin: { x: 0, y: H - bottom, w: W, h: bottom },
    };
  }

  function makeOccupancy() {
    const taken = [];
    return {
      hits: function (x, y, w, h) {
        return taken.some(b =>
          x < b.x + b.w && x + w > b.x &&
          y < b.y + b.h && y + h > b.y
        );
      },
      add: function (x, y, w, h) { taken.push({ x: x, y: y, w: w, h: h }); },
      list: function () { return taken.slice(); }
    };
  }

  // ============================================================
  // Annotation renderers (zone-aware, collision-aware)
  // ============================================================
  function renderBand(svg, ann, zones, t) {
    const xFrom = ann._x_from, xTo = ann._x_to;
    if (xFrom == null || xTo == null) return;
    const x0 = Math.min(xFrom, xTo), x1 = Math.max(xFrom, xTo);
    svg.insert('rect', ':first-child + *')
      .attr('x', x0).attr('y', zones.data.y)
      .attr('width', x1 - x0).attr('height', zones.data.h)
      .attr('fill', t.accent).attr('fill-opacity', 0.08);
    if (ann.label) {
      svg.append('text')
        .attr('x', (x0 + x1) / 2).attr('y', zones.data.y + 14)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('fill', t.accent).attr('font-weight', 600).attr('font-style', 'italic')
        .text(ann.label);
    }
  }

  function renderHline(svg, ann, zones, t) {
    const y = ann._y;
    if (y == null) return;
    svg.append('line')
      .attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', y).attr('y2', y)
      .attr('stroke', t.accent).attr('stroke-width', 1.4)
      .attr('stroke-dasharray', '5,3');
    if (ann.label) {
      // Label in right margin (so doesn't overlap with end labels of data lines)
      svg.append('text')
        .attr('x', zones.data.x + zones.data.w + 4).attr('y', y + 3)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('fill', t.accent).attr('font-weight', 600)
        .text(ann.label);
    }
  }

  function renderVlinesStaggered(svg, vlines, zones, t, occupancy) {
    const sorted = vlines.slice().sort((a, b) => (a._x || 0) - (b._x || 0));
    const calloutW = 110, calloutH = 32, gap = 4;
    sorted.forEach(v => {
      const x = v._x;
      if (x == null) return;
      // 1) Vertical dashed line through data zone
      svg.append('line')
        .attr('x1', x).attr('x2', x)
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.accent).attr('stroke-width', 1.2)
        .attr('stroke-dasharray', '4,3');

      // 2) Callout box position — try y stagger if collision in topMargin
      let cx = x - calloutW / 2;
      cx = Math.max(2, Math.min(zones.W - calloutW - 2, cx));
      let cy = 4;  // top of topMargin
      // Try multiple stagger positions
      while (cy + calloutH < zones.top && occupancy.hits(cx, cy, calloutW, calloutH)) {
        cy += calloutH + gap;
      }
      // If no room in topMargin, place inside data zone top (less ideal)
      if (cy + calloutH >= zones.top) cy = zones.top - calloutH - 2;

      // 3) Render callout box
      const g = svg.append('g').attr('transform', `translate(${cx},${cy})`);
      g.append('rect')
        .attr('width', calloutW).attr('height', calloutH)
        .attr('fill', t.card).attr('stroke', t.accent).attr('stroke-width', 0.7).attr('rx', 3);
      g.append('text')
        .attr('x', calloutW / 2).attr('y', 14).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('fill', t.accent).attr('font-weight', 700)
        .text((v.label || '').slice(0, 16));
      if (v.sublabel) {
        g.append('text')
          .attr('x', calloutW / 2).attr('y', 26).attr('text-anchor', 'middle')
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9)
          .attr('fill', t.accent)
          .text(String(v.sublabel).slice(0, 16));
      }

      // 4) Connector from callout bottom to vline top
      svg.append('path')
        .attr('d', `M ${cx + calloutW / 2} ${cy + calloutH} ` +
                   `L ${cx + calloutW / 2} ${zones.data.y - 2} ` +
                   `L ${x} ${zones.data.y - 2}`)
        .attr('fill', 'none').attr('stroke', t.accent).attr('stroke-width', 0.6);

      occupancy.add(cx, cy, calloutW, calloutH);
    });
  }

  function renderPoint(svg, ann, zones, t, occupancy) {
    const x = ann._x, y = ann._y;
    if (x == null || y == null) return;
    svg.append('circle')
      .attr('cx', x).attr('cy', y).attr('r', 4)
      .attr('fill', t.accent).attr('stroke', t.text).attr('stroke-width', 0.8);
    if (!ann.label) return;
    // Try upper-right of point first
    const labelW = (ann.label.length * 6) + 4, labelH = 14;
    const candidates = [
      { x: x + 8,         y: y - 8         },  // upper-right
      { x: x - labelW - 8, y: y - 8         },  // upper-left
      { x: x + 8,         y: y + 14        },  // lower-right
      { x: x - labelW - 8, y: y + 14        },  // lower-left
    ];
    let placed = candidates[0];
    for (const c of candidates) {
      if (c.x >= zones.data.x && c.x + labelW <= zones.W &&
          c.y >= zones.data.y && c.y + labelH <= zones.data.y + zones.data.h &&
          !occupancy.hits(c.x, c.y, labelW, labelH)) {
        placed = c;
        break;
      }
    }
    svg.append('text')
      .attr('x', placed.x).attr('y', placed.y + 8)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
      .attr('fill', t.accent).attr('font-weight', 600)
      .text(ann.label);
    occupancy.add(placed.x, placed.y, labelW, labelH);
  }

  // Main annotation pipeline. scaleX/scaleY are functions to project x/y data
  // values to pixel coordinates (or pass null for prepass scenarios).
  function renderAnnotations(svg, payload, zones, t, scaleX, scaleY) {
    const ann = (payload.annotations || []).map(a => Object.assign({}, a));
    ann.forEach(a => {
      if (scaleX) {
        if (a.x != null)      a._x      = scaleX(a.x);
        if (a.x_from != null) a._x_from = scaleX(a.x_from);
        if (a.x_to != null)   a._x_to   = scaleX(a.x_to);
      }
      if (scaleY && a.y != null) a._y = scaleY(a.y);
    });
    const occupancy = makeOccupancy();
    // Order matters: bands first (background), then hlines, then vlines (which take topMargin), then points
    ann.filter(a => a.kind === 'band').forEach(a => renderBand(svg, a, zones, t));
    ann.filter(a => a.kind === 'hline').forEach(a => renderHline(svg, a, zones, t));
    const vlines = ann.filter(a => a.kind === 'vline');
    if (vlines.length) renderVlinesStaggered(svg, vlines, zones, t, occupancy);
    ann.filter(a => a.kind === 'point').forEach(a => renderPoint(svg, a, zones, t, occupancy));
    return occupancy;
  }

  // v7.0.0 — 세로 라벨 dodge (CHART-AP-26 의 일반화). 동일/근접 y 라벨을 최소
  // 간격으로 밀어내고 [lo, hi] 범위로 클램프. slope 의 로컬 dodge 와 동일 알고리즘.
  function dodgeYs(ys, minGap, lo, hi) {
    const order = ys.map((y, i) => i).sort((p, q) => ys[p] - ys[q]);
    const adj = order.map(i => ys[i]);
    for (let i = 1; i < adj.length; i++)
      if (adj[i] - adj[i - 1] < minGap) adj[i] = adj[i - 1] + minGap;
    const over = adj[adj.length - 1] - hi;
    if (over > 0) for (let i = 0; i < adj.length; i++) adj[i] -= over;
    if (adj[0] < lo) { const d = lo - adj[0]; for (let i = 0; i < adj.length; i++) adj[i] += d; }
    const out = new Array(ys.length);
    order.forEach((origI, k) => { out[origI] = adj[k]; });
    return out;
  }

  // End label placement helper (used by line/dual_line/forecast)
  function placeEndLabel(svg, x, y, text, t, occupancy, zones, color) {
    const labelW = Math.min(120, (String(text).length * 7) + 6);
    const labelH = 14;
    const candidates = [
      { x: x + 6,            y: y - 8,  anchor: 'start' },  // right of marker
      { x: x + 6,            y: y - 18, anchor: 'start' },  // upper-right
      { x: x - 6 - labelW,   y: y - 8,  anchor: 'start' },  // left
    ];
    let placed = null;
    for (const c of candidates) {
      if (c.x + labelW > zones.W - 2 || c.x < 2) continue;
      if (!occupancy.hits(c.x, c.y, labelW, labelH)) {
        placed = c;
        break;
      }
    }
    placed = placed || candidates[0];
    svg.append('text')
      .attr('x', placed.x).attr('y', placed.y + 10).attr('text-anchor', placed.anchor)
      .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700)
      .attr('fill', color || t.text)
      .text(text);
    occupancy.add(placed.x, placed.y, labelW, labelH);
  }

  // ============================================================
  // Chart renderers (all use zones)
  // ============================================================

  // ----- BAR (horizontal) -----
  // v7.1.0 리디자인 (사용자 승인 — samples/chart_redesign_v7_compare.html):
  // 순위 비교에 해치 금지 — 단일 잉크 농도 + 1위만 액센트, 옅은 풀폭 트랙,
  // 세리프 값 직접 라벨, note 보조 행. 그리드 폐기, 0-기준선만 crisp.
  // annotations(값 축)·bar-grow entry 애니메이션 계약은 기존 그대로.
  function drawBar(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value));
    if (!data.length) return;
    const hasNotes = data.some(d => d.note);
    const W = 720;
    const rowH = hasNotes ? 38 : 30;
    const annTop = (payload.annotations || []).some(a => a.kind === 'vline') ? 56 : 18;
    const H = annTop + data.length * rowH + 26;
    const zones = computeZones(W, H, { left: 170, right: 92, top: annTop, bottom: 26 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const max = d3.max(data, d => Math.abs(+d.value)) || 1;
    const x0 = zones.data.x, x1 = zones.data.x + zones.data.w;
    const xScale = (v) => x0 + (Math.abs(+v) / max) * (x1 - x0);
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(+v);
      if (av >= 10) return d3.format(',.1f')(+v);
      return d3.format(',.2f')(+v);
    };
    const trunc = (sv, n) => {
      const str = String(sv || '');
      return str.length > n ? str.slice(0, n - 1) + '…' : str;
    };
    data.forEach((d, i) => {
      const y = zones.data.y + i * rowH + 5;
      const key = i === 0;
      svg.append('text').attr('x', x0 - 14).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 12)
        .attr('font-weight', key ? 700 : 400).attr('fill', t.text)
        .text(trunc(d.label, 20));
      if (d.note) {
        svg.append('text').attr('x', x0 - 14).attr('y', y + 24).attr('text-anchor', 'end')
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
          .text(trunc(d.note, 26));
      }
      // 옅은 풀폭 트랙 (상대 크기의 받침) + 값 막대
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', x1 - x0).attr('height', 13)
        .attr('rx', 1).attr('fill', t.text).attr('fill-opacity', 0.055)
        .attr('data-anim', 'static');
      const barW = Math.max(2, xScale(d.value) - x0);
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', barW).attr('height', 13)
        .attr('rx', 1).attr('fill', key ? t.accent : t.text)
        .attr('fill-opacity', key ? 1 : 0.30)
        .attr('data-anim', 'bar-grow').attr('data-final-w', barW);
      svg.append('text').attr('x', xScale(d.value) + 9).attr('y', y + 11.5)
        .attr('font-family', 'Noto Serif KR').attr('font-size', 13).attr('font-weight', 700)
        .attr('fill', key ? t.accent : t.text).text(fmt(d.value));
    });
    // 0-기준선만 crisp
    svg.append('line').attr('x1', x0).attr('x2', x0)
      .attr('y1', zones.data.y - 2).attr('y2', zones.data.y + data.length * rowH + 2)
      .attr('stroke', t.text).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
    // Annotations (값 축 기준) — 기존 계약 유지
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }

  // ----- DONUT -----
  // v7.1.0 리디자인: 핵심 조각만 액센트 + 잉크 농도 사다리, 중앙 = 핵심 점유율
  // 큰 숫자, 우측 범례 = 값 정렬 열. arc sweep entry 애니메이션 계약(donut-arc +
  // data-donut-*) 유지. CHART-AP-16 (3조각 미만 emit 금지) 유지.
  function drawDonut(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value) && +d.value > 0);
    if (data.length < 3) return;
    const W = 560;
    const H = Math.max(230, data.length * 26 + 44);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const cx = 122, cy = H / 2, r = 84, ir = 62;
    const total = d3.sum(data, d => +d.value) || 1;
    const keyIdx = data.reduce((b, d, i) => (+d.value > +data[b].value ? i : b), 0);
    const LADDER = [0.32, 0.20, 0.13, 0.08];
    const trunc = (sv, n) => {
      const str = String(sv || '');
      return str.length > n ? str.slice(0, n - 1) + '…' : str;
    };
    const pie = d3.pie().value(d => +d.value).sort(null).padAngle(0.018);
    const arc = d3.arc().innerRadius(ir).outerRadius(r);
    let li = 0;
    pie(data).forEach((a, i) => {
      const key = i === keyIdx;
      const op = key ? 1 : LADDER[Math.min(li++, LADDER.length - 1)];
      svg.append('path').attr('d', arc(a)).attr('transform', `translate(${cx},${cy})`)
        .attr('fill', key ? t.accent : t.text).attr('fill-opacity', op)
        .attr('data-anim', 'donut-arc')
        .attr('data-start', a.startAngle).attr('data-end', a.endAngle);
    });
    svg.attr('data-donut-cx', cx).attr('data-donut-cy', cy)
      .attr('data-donut-ir', ir).attr('data-donut-r', r);
    // 중앙 — 핵심 점유율
    svg.append('text').attr('x', cx).attr('y', cy + 2).attr('text-anchor', 'middle')
      .attr('font-family', 'Newsreader, Noto Serif KR, serif').attr('font-size', 30)
      .attr('font-weight', 800).attr('fill', t.text)
      .text(d3.format('.0f')(+data[keyIdx].value / total * 100) + '%');
    svg.append('text').attr('x', cx).attr('y', cy + 22).attr('text-anchor', 'middle')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5).attr('fill', t.muted)
      .text(trunc(data[keyIdx].label, 14));
    // 우측 범례 — 값 정렬 열 + hairline
    const ly0 = cy - (data.length * 26) / 2 + 8;
    li = 0;
    data.forEach((d, i) => {
      const key = i === keyIdx;
      const op = key ? 1 : LADDER[Math.min(li++, LADDER.length - 1)];
      const y = ly0 + i * 26;
      svg.append('circle').attr('cx', 262).attr('cy', y).attr('r', 4.5)
        .attr('fill', key ? t.accent : t.text).attr('fill-opacity', op);
      svg.append('text').attr('x', 276).attr('y', y + 4)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 12)
        .attr('font-weight', key ? 700 : 400).attr('fill', t.text)
        .text(trunc(d.label, 14));
      svg.append('text').attr('x', 510).attr('y', y + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Serif KR').attr('font-size', 12.5).attr('font-weight', 700)
        .attr('fill', key ? t.accent : t.text)
        .text(fmtShare(d.value) + ' · ' + d3.format('.0f')(+d.value / total * 100) + '%');
      svg.append('line').attr('x1', 254).attr('x2', 510).attr('y1', y + 12).attr('y2', y + 12)
        .attr('stroke', t.border).attr('stroke-opacity', 0.5).attr('stroke-width', 0.5);
    });
    function fmtShare(v) {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(+v);
      if (av >= 10) return d3.format(',.1f')(+v);
      return d3.format(',.2f')(+v);
    }
  }

  // ----- LINE (with optional events) -----
  function drawLine(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.y));
    if (data.length < 2) return;
    const W = 760, H = 320;
    // v5.2.3 — right padding 110 → 70: placeEndLabel 후보가 좌측으로도 떨어질
    // 수 있어 110 은 과도. line/area 가 캔버스 우측 ~14% 비워두는 시각적
    // 좌측 치우침을 해소.
    const zones = computeZones(W, H, { left: 60, right: 70 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    // v5.2.3 — scalePoint padding 0.10 → 0.04: 첫·마지막 점이 plot 끝에서
    // 5% 안쪽으로 들어와 좌우 cropped 처럼 보이던 현상 완화.
    const x = d3.scalePoint().domain(data.map(d => String(d.x))).range([zones.data.x, zones.data.x + zones.data.w]).padding(0.04);
    const yExtent = d3.extent(data, d => +d.y);
    const yPad = (yExtent[1] - yExtent[0]) * 0.1 || 1;
    const y = d3.scaleLinear().domain([yExtent[0] - yPad, yExtent[1] + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);

    // y grid + labels
    y.ticks(5).forEach(v => {
      svg.append('line')
        .attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', y(v)).attr('y2', y(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.18).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('.0f')(v));
    });

    // Annotations need to render *before* line so they're behind it
    const occupancy = renderAnnotations(svg, payload, zones, t,
      (xv) => x(String(xv)), (yv) => y(+yv));

    // v5.2.3 — Area fill 은 linearGradient (drawArea 와 일관). 이전 단색 0.10
    // 평탄 fill 은 그라데이션이 아니라는 사용자 지적의 직접 원인.
    const gradId = `grad-line-${stage.getAttribute('data-chart-id') || Math.random().toString(36).slice(2,8)}`;
    const grad = svg.append('defs').append('linearGradient')
      .attr('id', gradId).attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 1);
    grad.append('stop').attr('offset', '0%').attr('stop-color', t.accent).attr('stop-opacity', 0.28);
    grad.append('stop').attr('offset', '100%').attr('stop-color', t.accent).attr('stop-opacity', 0.02);

    // v7.0.1 (CHART-AP-30, 사용자 catch) — curveMonotoneX 는 점 사이를 베지에로
    // 평탄화해 실제 가격 경로를 왜곡. v5.2.9 가 sparkline 만 curveLinear 로 고치고
    // 풀 카드엔 잔재가 남았었다. 시장 시계열 전 렌더러 curveLinear 통일.
    const line = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveLinear);
    const area = d3.area().x(d => x(String(d.x))).y0(zones.data.y + zones.data.h)
      .y1(d => y(+d.y)).curve(d3.curveLinear);
    svg.append('path').attr('d', area(data)).attr('fill', `url(#${gradId})`);
    svg.append('path').attr('d', line(data)).attr('fill', 'none').attr('stroke', t.text).attr('stroke-width', 1.4);

    // End marker + label
    // v5.2.3 — last.y 부동소수점 그대로 (e.g. "7493.180175125") 노출되던
    // 회귀 수정. Y 라벨과 동일한 format 규칙 (`.0f` for >=1000, `.2f` otherwise).
    const last = data[data.length - 1];
    const lastY = +last.y;
    const lastText = Math.abs(lastY) >= 1000 ? d3.format(',.0f')(lastY) : d3.format(',.2f')(lastY);
    svg.append('circle').attr('cx', x(String(last.x))).attr('cy', y(lastY)).attr('r', 3.5).attr('fill', t.accent);
    placeEndLabel(svg, x(String(last.x)), y(lastY), lastText, t, occupancy, zones, t.accent);

    // x labels (sparse)
    const step = Math.max(1, Math.ceil(data.length / 7));
    data.forEach((d, i) => {
      if (i % step !== 0 && i !== data.length - 1) return;
      svg.append('text').attr('x', x(String(d.x))).attr('y', H - zones.bottom + 16).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(String(d.x).slice(0, 12));
    });
    // v5.2.0 — Bloomberg/FT 풍 이벤트 번호 배지 + footnote (드림라인 위 점선만 그리던
    // legacy 처리를 candle/area 와 일관 스타일로 교체). 함수 정의는 아래쪽
    // _renderEventBadgesAndFootnote 가 hoisted (function declaration).
    const lineEvents = data
      .map((d, i) => ({ idxInData: i, dataItem: d, eventLabel: d.event, dateStr: d.x, valueY: y(+d.y) }))
      .filter(e => e.eventLabel);
    if (lineEvents.length) {
      _renderEventBadgesAndFootnote(
        stage, svg, lineEvents,
        (item) => x(String(item.x)),
        zones, t,
      );
    }
  }

  // ----- GANTT -----
  function drawGantt(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 720;
    const rowH = 26;
    const axisH = 28;  // v4.5.4 — 시간축 그릴 자리
    const H = 48 + axisH + (data.length * rowH) + 8;
    const zones = computeZones(W, H, { left: 150, right: 80, top: 28, bottom: axisH + 8 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    // v5.2.11 (CHART-AP-13 + AP-17 신설): parseTime 가 day-precision 까지.
    // 이전엔 'YYYY-MM-DD' 의 day 부분이 silent 무시 → 같은 월 안의 모든 이벤트가
    // 같은 시점으로 collapse → start==end 폴백 +0.4 (≈5개월) 가 발동 →
    // 모든 막대가 데이터 영역 *풀폭* 으로 렌더되던 회귀. encoding:
    // y + ((m-1)*31 + (day-1)) / 372 — month-only 입력 호환 (372/12 = 31).
    function parseTime(v) {
      if (typeof v === 'number') return v;
      const s = String(v || '').trim();
      const dMatch = s.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})/);
      if (dMatch) {
        return +dMatch[1] + ((+dMatch[2] - 1) * 31 + (+dMatch[3] - 1)) / 372;
      }
      const mMatch = s.match(/^(\d{4})[-./](\d{1,2})/);
      if (mMatch) return +mMatch[1] + (+mMatch[2] - 1) / 12;
      const yMatch = s.match(/^(\d{4})/);
      if (yMatch) return +yMatch[1];
      const n = +s;
      return isNaN(n) ? 0 : n;
    }
    const starts = data.map(d => parseTime(d.start));
    // v5.2.11: zero-duration 폴백 +0.4 제거. 막대 폭 visibility 는 아래의
    // Math.max(6, ...) floor 가 보장. day-precision 시대에 +0.4 는 풀폭 회귀의
    // 원인 (CHART-AP-13 후속 — AP-15 가드를 우회한 케이스도 잡힘).
    const ends = data.map((d, i) => {
      const e = parseTime(d.end);
      return e > starts[i] ? e : starts[i];
    });
    const min = Math.min(...starts);
    const maxRaw = Math.max(...ends);
    const span = Math.max(1 / 372, maxRaw - min);  // 최소 1일 span (붕괴 방지)
    const max = min + span;
    const xScale = d3.scaleLinear()
      .domain([min - span * 0.02, max + span * 0.02])
      .range([zones.data.x, zones.data.x + zones.data.w]);

    // v5.2.11: span 에 따라 tick 단위/포맷 자동.
    // - span ≥ 4 yr: 연도 정수
    // - 0.4 ≤ span < 4: 월 boundary ("YYYY-MM")
    // - span < 0.4: 일 단위 ("MM-DD") — 사건성 보고서 (수주 단위 timeline)
    let ticksFinal = [];
    let fmtTick;
    if (span >= 4) {
      const lo = Math.ceil(min), hi = Math.floor(max);
      for (let y = lo; y <= hi; y++) ticksFinal.push(y);
      fmtTick = (v) => String(Math.round(v));
    } else if (span >= 0.4) {
      const yLo = Math.floor(min), yHi = Math.ceil(max);
      const all = [];
      for (let y = yLo; y <= yHi; y++) {
        for (let m = 0; m < 12; m++) {
          const tv = y + m / 12;
          if (tv >= min - 0.01 && tv <= max + 0.01) all.push(tv);
        }
      }
      const step = Math.max(1, Math.ceil(all.length / 7));
      ticksFinal = all.filter((_, i) => i % step === 0);
      fmtTick = (v) => {
        const y = Math.floor(v + 1e-6);
        let m = Math.round((v - y) * 12) + 1;
        let yy = y;
        if (m > 12) { m = 1; yy++; }
        return `${yy}-${String(m).padStart(2, '0')}`;
      };
    } else {
      const totalDays = span * 372;
      const stepDays = Math.max(1, Math.ceil(totalDays / 6));
      const startY = Math.floor(min + 1e-6);
      const startUnits = Math.round((min - startY) * 372);
      for (let off = 0; off <= totalDays + 0.5; off += stepDays) {
        ticksFinal.push(startY + (startUnits + off) / 372);
      }
      fmtTick = (v) => {
        const y = Math.floor(v + 1e-6);
        const units = Math.round((v - y) * 372);
        const m = Math.floor(units / 31) + 1;
        const day = (units % 31) + 1;
        return `${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      };
    }

    // 시간축 (하단)
    const axisG = svg.append('g').attr('class', 'axis-x')
      .attr('transform', `translate(0, ${zones.data.y + zones.data.h + 4})`);
    ticksFinal.forEach(tick => {
      const x = xScale(tick);
      axisG.append('line').attr('x1', x).attr('x2', x).attr('y1', 0).attr('y2', 4)
        .attr('stroke', t.muted).attr('stroke-width', 0.7);
      axisG.append('text').attr('x', x).attr('y', 16).attr('text-anchor', 'middle')
        .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text(fmtTick(tick));
    });
    // 가로 격자 (가벼운)
    ticksFinal.forEach(tick => {
      const x = xScale(tick);
      svg.append('line').attr('x1', x).attr('x2', x)
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.muted).attr('stroke-width', 0.4).attr('stroke-opacity', 0.25)
        .attr('stroke-dasharray', '2,3');
    });

    data.forEach((d, i) => {
      const y = zones.data.y + 6 + i * rowH;
      // 행 라벨 (왼쪽 zone). 길면 25자로 truncate (이전 22 → 25, 가독성↑).
      const label = String(d.label || '').slice(0, 25);
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('font-weight', 600)
        .text(label);
      const x0 = xScale(starts[i]);
      const x1 = xScale(ends[i]);
      const barW = Math.max(6, x1 - x0);  // 최소 6px (이전 2 → 6, 점이 아니게)
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', barW).attr('height', 14)
        .attr('fill', t.accent).attr('rx', 2);
      // note placement — 막대 폭에 따라 안 / 밖. 이전엔 항상 막대 우측 → 다음 행 라벨과
      // X 가 겹치면 글자 충돌. 이제 막대 폭 ≥ 60px 이면 *안*에 흰글자, 아니면 *밖* 우측.
      if (d.note) {
        const noteText = String(d.note).slice(0, 22);
        const inside = barW >= 60;
        svg.append('text')
          .attr('x', inside ? x0 + 6 : x1 + 6)
          .attr('y', y + 11)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9)
          .attr('fill', inside ? t.bg : t.muted)
          .attr('font-weight', inside ? 600 : 400)
          .text(noteText);
      }
    });
    // v5.2.11: annotation 의 시간 x 도 parseTime 통과시켜 day-precision 지원.
    // 이전엔 vline/band 의 'YYYY-MM-DD' 가 raw 로 d3 linear scale 에 들어가 NaN.
    const annXScale = (v) => xScale(typeof v === 'number' ? v : parseTime(v));
    renderAnnotations(svg, payload, zones, t, annXScale, null);
  }

  // ----- NETWORK 관계도 폐기 (CHART-AP-36, 2026-06-20) -----
  // 행위자 관계도(인접행렬) 포맷은 정보 밀도 대비 공간 점유가 커 보고서 가독성을
  // 떨어뜨려 시스템에서 제거됐다. composer 는 더는 emit 하지 않고, schemas.py 의
  // validate_chart_data 가 network 차트를 drop 한다. RENDERERS 에도 미등록.


  // ----- STACKED (positive magnitude only — composer prompt enforces) -----
  // v7.1.0 리디자인 (병합 — bar 와 같은 가로 막대 문법, 사용자 승인): 세로 막대 +
  // 하단 범례 폐기 → 가로 세그먼트 막대 + 상단 범례. 세그먼트는 액센트 + 잉크 농도
  // 사다리 (해치 폐기), 1.5px 배경 갭 구분, 합계는 막대 끝 세리프 볼드, 세그먼트
  // 값은 폭 충분할 때만 안에 직접. 데이터 계약 (scenarios/segments) 불변.
  function drawStacked(stage, payload, t) {
    const rows = (payload.data && payload.data.scenarios) || [];
    if (!rows.length) return;
    // 모든 row 의 unique segment.label — 같은 label 같은 농도 (v4.4.2 일관성 유지)
    const labelOrder = [];
    rows.forEach(r => (r.segments || []).forEach(sg => {
      const lbl = String(sg.label || '').trim();
      if (lbl && labelOrder.indexOf(lbl) === -1) labelOrder.push(lbl);
    }));
    const labelToIndex = Object.fromEntries(labelOrder.map((l, i) => [l, i]));
    const segStyle = (idx) => idx === 0
      ? { f: t.accent, o: 1 }
      : { f: t.text, o: [0.42, 0.24, 0.13][Math.min(idx - 1, 2)] };
    const trunc = (sv, n) => {
      const str = String(sv || '');
      return str.length > n ? str.slice(0, n - 1) + '…' : str;
    };
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(+v);
      if (av >= 10) return d3.format(',.1f')(+v);
      return d3.format(',.2f')(+v);
    };
    const W = 720, rowH = 46, top = 34;
    const H = top + rows.length * rowH + 12;
    const x0 = 100, x1 = W - 96;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const maxTotal = d3.max(rows, r =>
      d3.sum(r.segments || [], sg => Math.abs(+sg.value) || 0)) || 1;
    // 상단 범례
    let lx = 0;
    const lg = svg.append('g').attr('transform', `translate(${x0},10)`);
    labelOrder.forEach((nm, i) => {
      const st = segStyle(i);
      lg.append('rect').attr('x', lx).attr('y', 0).attr('width', 11).attr('height', 11)
        .attr('rx', 2).attr('fill', st.f).attr('fill-opacity', st.o)
        .attr('data-anim', 'static');
      lg.append('text').attr('x', lx + 16).attr('y', 9.5).attr('font-family', 'Noto Sans KR')
        .attr('font-size', 10.5).attr('fill', t.muted).text(trunc(nm, 10));
      lx += 16 + Math.min(nm.length, 10) * 11 + 22;
    });
    rows.forEach((r, ri) => {
      const y = top + ri * rowH + 9;
      svg.append('text').attr('x', x0 - 14).attr('y', y + 13).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 12).attr('font-weight', 600)
        .attr('fill', t.text).text(trunc(r.name, 12));
      let acc = 0;
      const total = d3.sum(r.segments || [], sg => Math.abs(+sg.value) || 0);
      (r.segments || []).forEach((sg, si) => {
        const v = Math.abs(+sg.value) || 0;
        const w = (v / maxTotal) * (x1 - x0);
        const x = x0 + (acc / maxTotal) * (x1 - x0);
        const idx = labelToIndex[String(sg.label || '').trim()] || 0;
        const st = segStyle(idx);
        const segW = Math.max(0, w - (si ? 1.5 : 0));
        svg.append('rect').attr('x', x + (si ? 1.5 : 0)).attr('y', y)
          .attr('width', segW).attr('height', 18).attr('rx', 1)
          .attr('fill', st.f).attr('fill-opacity', st.o)
          .attr('data-anim', 'bar-grow').attr('data-final-w', segW);
        if (w >= 36) {
          svg.append('text').attr('x', x + w / 2).attr('y', y + 13).attr('text-anchor', 'middle')
            .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('font-weight', 600)
            .attr('fill', idx === 0 ? t.bg : t.text)
            .attr('fill-opacity', idx === 0 ? 0.95 : 0.85)
            .text(fmt(v));
        }
        acc += v;
      });
      svg.append('text').attr('x', x0 + (total / maxTotal) * (x1 - x0) + 10).attr('y', y + 13.5)
        .attr('font-family', 'Noto Serif KR').attr('font-size', 13.5).attr('font-weight', 700)
        .attr('fill', t.text).text(fmt(total));
    });
    // 0-기준선
    svg.append('line').attr('x1', x0).attr('x2', x0)
      .attr('y1', top + 4).attr('y2', top + rows.length * rowH - 6)
      .attr('stroke', t.text).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
  }

  // ----- BUBBLE -----
  // v7.1.0 리디자인 (사용자 승인): 중앙값 십자선 사분면 + 윤곽/옅은 면 버블 +
  // 강조 1개 (accent 플래그 > 최대 size) + 크기 범례 (플롯 밖). 프레임 박스 폐기.
  // v4.5.3 (CHART-AP-12) 의 스케일 자동 감지 + annotations 계약은 유지.
  function drawBubble(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.x) && isFinite(+d.y));
    if (!data.length) return;
    const W = 720, H = 380;
    const zones = computeZones(W, H, { left: 64, right: 44, top: 28, bottom: 58 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    // 스케일 — 입력 extent 기반 + 0 포함 (CHART-AP-12 가드 유지)
    const xsv = data.map(d => +d.x), ysv = data.map(d => +d.y);
    const xMin = Math.min(0, d3.min(xsv));
    const xMax = Math.max(d3.max(xsv) * 1.08, xMin === 0 && d3.max(xsv) === 0 ? 1 : d3.max(xsv) * 1.08);
    const yMin = Math.min(0, d3.min(ysv));
    const yMax = Math.max(d3.max(ysv) * 1.12, yMin === 0 && d3.max(ysv) === 0 ? 1 : d3.max(ysv) * 1.12);
    const x = d3.scaleLinear().domain([xMin, xMax]).range([zones.data.x, zones.data.x + zones.data.w]);
    const y = d3.scaleLinear().domain([yMin, yMax]).range([zones.data.y + zones.data.h, zones.data.y]);
    const sizes = data.map(d => +(d.size || 0)).filter(v => !isNaN(v) && v > 0);
    const sMax = sizes.length ? Math.max(...sizes, 1) : 1;
    const rs = (sv) => 7 + 18 * Math.sqrt(Math.min(1, Math.max(0, (+(sv || 0.5)) / sMax)));
    // 사분면 십자선 (중앙값) + '중앙값' 마커
    const mx = d3.median(data, d => +d.x), my = d3.median(data, d => +d.y);
    svg.append('line').attr('x1', x(mx)).attr('x2', x(mx))
      .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
      .attr('stroke', t.muted).attr('stroke-opacity', 0.45).attr('stroke-dasharray', '3 4');
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', y(my)).attr('y2', y(my))
      .attr('stroke', t.muted).attr('stroke-opacity', 0.45).attr('stroke-dasharray', '3 4');
    svg.append('text').attr('x', zones.data.x + zones.data.w + 4).attr('y', y(my) + 3)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 8.5).attr('fill', t.muted)
      .text('중앙값');
    svg.append('text').attr('x', x(mx)).attr('y', zones.data.y - 6).attr('text-anchor', 'middle')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 8.5).attr('fill', t.muted)
      .text('중앙값');
    // 축 — 숫자만 (도메인 패스 없음)
    x.ticks(5).forEach(v => {
      svg.append('text').attr('x', x(v)).attr('y', zones.data.y + zones.data.h + 16)
        .attr('text-anchor', 'middle').attr('font-family', 'IBM Plex Mono, monospace')
        .attr('font-size', 9).attr('fill', t.muted).text(v);
    });
    y.ticks(5).forEach(v => {
      svg.append('text').attr('x', zones.data.x - 10).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'IBM Plex Mono, monospace').attr('font-size', 9)
        .attr('fill', t.muted).text(v);
    });
    svg.append('text').attr('x', zones.data.x + zones.data.w / 2).attr('y', H - 10)
      .attr('text-anchor', 'middle').attr('fill', t.muted)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
      .text(payload.x_label || '확률 →');
    svg.append('text').attr('x', 14).attr('y', zones.data.y + zones.data.h / 2)
      .attr('transform', `rotate(-90, 14, ${zones.data.y + zones.data.h / 2})`)
      .attr('text-anchor', 'middle').attr('fill', t.muted)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
      .text(payload.y_label || '영향');
    const occupancy = renderAnnotations(svg, payload, zones, t, x, y);
    // 강조 1개 — accent 플래그 우선, 없으면 최대 size
    let keyIdx = data.findIndex(d => d.accent === true);
    if (keyIdx < 0) keyIdx = data.reduce((b, d, i) =>
      (+(d.size || 0) > +(data[b].size || 0) ? i : b), 0);
    data.forEach((d, i) => {
      const key = i === keyIdx;
      const cx = x(+d.x), cy = y(+d.y), r = rs(d.size);
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', r)
        .attr('fill', t.accent).attr('fill-opacity', key ? 0.45 : 0.16)
        .attr('stroke', t.accent).attr('stroke-width', key ? 1.8 : 1.1);
      const text = String(d.label || '');
      if (!text) return;
      const labelW = text.length * 7.5 + 4, labelH = 13;
      // 위 → 아래 → 우측 후보 (annotation occupancy 와 충돌 회피)
      const candidates = [
        { x: cx - labelW / 2, y: cy - r - 17, anchor: 'middle', tx: cx },
        { x: cx - labelW / 2, y: cy + r + 4, anchor: 'middle', tx: cx },
        { x: cx + r + 6, y: cy - 6, anchor: 'start', tx: cx + r + 6 },
      ];
      let placed = candidates[0];
      for (const c of candidates) {
        if (c.x < 2 || c.x + labelW > W - 2) continue;
        if (!occupancy.hits(c.x, c.y, labelW, labelH)) { placed = c; break; }
      }
      svg.append('text').attr('x', placed.tx).attr('y', placed.y + 10)
        .attr('text-anchor', placed.anchor)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5)
        .attr('font-weight', key ? 700 : 500)
        .attr('fill', key ? t.accent : t.text).text(text);
      occupancy.add(placed.x, placed.y, labelW, labelH);
    });
    // 크기 범례 — 플롯 밖 하단 우측
    const lgy = H - 14, lgx = zones.data.x + zones.data.w - 4;
    svg.append('text').attr('x', lgx).attr('y', lgy + 3).attr('text-anchor', 'end')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
      .text(payload.size_label ? `크기 = ${payload.size_label}` : '원 크기 = 상대 비중');
    let off = (payload.size_label ? String(payload.size_label).length * 9 : 9 * 9) + 76;
    [sMax / 3, sMax].forEach(sv => {
      const r = Math.max(3.5, rs(sv) * 0.42);
      svg.append('circle').attr('cx', lgx - off).attr('cy', lgy).attr('r', r)
        .attr('fill', 'none').attr('stroke', t.muted).attr('stroke-opacity', 0.7)
        .attr('stroke-width', 0.9);
      off += r * 2 + 12;
    });
  }

  // ----- HEATMAP -----
  // v7.1.0 리디자인 (사용자 승인): 풀폭 해치 띠 → 5칸 강도 트랙 (채운 칸 수 =
  // 위험도) + 우측 등급 태그 + 범례. 농도/칸수가 서수 위계를 직접 운반 — 패턴
  // 식별 퀴즈 폐기. 데이터 계약 ({title, severity}) 불변.
  function drawHeatmap(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 720, rowH = 34, top = 30;
    const H = top + data.length * rowH + 10;
    const x0 = 184, cells = 5;
    const gap = 5, cellW = Math.floor((W - x0 - 96 - gap * (cells - 1)) / cells);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const SPEC = {
      high:   { n: 5, f: t.accent, o: 0.92, tag: '높음' },
      medium: { n: 3, f: t.text,   o: 0.38, tag: '중간' },
      low:    { n: 1, f: t.text,   o: 0.20, tag: '낮음' },
    };
    const trunc = (sv, n) => {
      const str = String(sv || '');
      return str.length > n ? str.slice(0, n - 1) + '…' : str;
    };
    // 범례 (우상단)
    const lg = svg.append('g').attr('transform', `translate(${W - 256},8)`);
    [['high', 0], ['medium', 94], ['low', 182]].forEach(pair => {
      const sp = SPEC[pair[0]];
      lg.append('rect').attr('x', pair[1]).attr('y', 0).attr('width', 10).attr('height', 10)
        .attr('rx', 2).attr('fill', sp.f).attr('fill-opacity', sp.o)
        .attr('data-anim', 'static');
      lg.append('text').attr('x', pair[1] + 14).attr('y', 9)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9.5).attr('fill', t.muted)
        .text(`${sp.tag} ${sp.n}/5`);
    });
    data.forEach((d, i) => {
      const y = top + i * rowH + 6;
      const sp = SPEC[String(d.severity || 'low').toLowerCase()] || SPEC.low;
      svg.append('text').attr('x', x0 - 14).attr('y', y + 12).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 12)
        .attr('font-weight', sp.n === 5 ? 600 : 400).attr('fill', t.text)
        .text(trunc(d.title, 22));
      for (let c = 0; c < cells; c++) {
        const filled = c < sp.n;
        svg.append('rect').attr('x', x0 + c * (cellW + gap)).attr('y', y)
          .attr('width', cellW).attr('height', 15).attr('rx', 2)
          .attr('fill', filled ? sp.f : t.text)
          .attr('fill-opacity', filled ? sp.o : 0.06);
      }
      svg.append('text').attr('x', x0 + cells * (cellW + gap) + 10).attr('y', y + 12)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5).attr('font-weight', 700)
        .attr('fill', sp.n === 5 ? t.accent : t.text)
        .attr('fill-opacity', sp.n === 1 ? 0.7 : 1).text(sp.tag);
    });
  }

  // ============================================================
  // Tier 2 — NEW TYPES
  // ============================================================

  // ----- DUAL_LINE — 두 metric, 좌·우 y축 -----
  function drawDualLine(stage, payload, t) {
    const left = payload.data && payload.data.left;
    const right = payload.data && payload.data.right;
    if (!left || !right || !(left.series || []).length || !(right.series || []).length) return;
    const W = 760, H = 340;
    const zones = computeZones(W, H, { left: 60, right: 60, top: 56, bottom: 40 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;

    // Shared x domain (union of both series)
    const xVals = Array.from(new Set([...left.series, ...right.series].map(d => String(d.x))));
    const x = d3.scalePoint().domain(xVals).range([zones.data.x, zones.data.x + zones.data.w]).padding(0.1);
    const yL = d3.scaleLinear().domain(d3.extent(left.series, d => +d.y))
      .nice().range([zones.data.y + zones.data.h, zones.data.y]);
    const yR = d3.scaleLinear().domain(d3.extent(right.series, d => +d.y))
      .nice().range([zones.data.y + zones.data.h, zones.data.y]);

    // Y axis L (left)
    yL.ticks(4).forEach(v => {
      svg.append('text').attr('x', zones.data.x - 6).attr('y', yL(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('.0f')(v));
    });
    svg.append('text').attr('x', zones.data.x).attr('y', zones.data.y - 6)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.text)
      .attr('font-weight', 600)
      .text(`${left.label || ''} (${left.unit || ''})`);
    // Y axis R (right)
    yR.ticks(4).forEach(v => {
      svg.append('text').attr('x', zones.data.x + zones.data.w + 6).attr('y', yR(v) + 3)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('.0f')(v));
    });
    svg.append('text').attr('x', zones.data.x + zones.data.w).attr('y', zones.data.y - 6).attr('text-anchor', 'end')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.accent)
      .attr('font-weight', 600)
      .text(`${right.label || ''} (${right.unit || ''})`);

    const occupancy = renderAnnotations(svg, payload, zones, t,
      (xv) => x(String(xv)), null);  // y not unique — annotations use x only

    // Lines
    // CHART-AP-30 — 실제 데이터 경로 (곡선 보간 금지).
    const lineL = d3.line().x(d => x(String(d.x))).y(d => yL(+d.y)).curve(d3.curveLinear);
    const lineR = d3.line().x(d => x(String(d.x))).y(d => yR(+d.y)).curve(d3.curveLinear);
    svg.append('path').attr('d', lineL(left.series)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.6);
    svg.append('path').attr('d', lineR(right.series)).attr('fill', 'none')
      .attr('stroke', t.accent).attr('stroke-width', 1.6).attr('stroke-dasharray', '4,2');

    // End markers + labels
    const lL = left.series[left.series.length - 1];
    const lR = right.series[right.series.length - 1];
    svg.append('circle').attr('cx', x(String(lL.x))).attr('cy', yL(+lL.y)).attr('r', 3.2).attr('fill', t.text);
    svg.append('circle').attr('cx', x(String(lR.x))).attr('cy', yR(+lR.y)).attr('r', 3.2).attr('fill', t.accent);
    placeEndLabel(svg, x(String(lL.x)), yL(+lL.y), `${left.label} ${lL.y}`, t, occupancy, zones, t.text);
    placeEndLabel(svg, x(String(lR.x)), yR(+lR.y), `${right.label} ${lR.y}`, t, occupancy, zones, t.accent);

    // x labels (sparse)
    const step = Math.max(1, Math.ceil(xVals.length / 7));
    xVals.forEach((xv, i) => {
      if (i % step !== 0 && i !== xVals.length - 1) return;
      svg.append('text').attr('x', x(xv)).attr('y', H - zones.bottom + 16).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(String(xv).slice(0, 10));
    });
  }

  // ----- FORECAST — actual + cone -----
  function drawForecast(stage, payload, t) {
    const actual = (payload.data && payload.data.actual) || [];
    const forecast = (payload.data && payload.data.forecast) || [];
    if (actual.length < 2) return;
    const W = 760, H = 320;
    const zones = computeZones(W, H, { left: 60, right: 110 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const allPoints = actual.map(d => ({ x: d.x, y: +d.y }))
      .concat(forecast.map(d => ({ x: d.x, y: +d.mid })));
    const xVals = allPoints.map(d => String(d.x));
    const x = d3.scalePoint().domain(xVals).range([zones.data.x, zones.data.x + zones.data.w]).padding(0.1);
    // v5.4.8 — y 도메인 산정 시 actual 과 forecast 를 *모두* 포함.
    // 이전 `?? fallback` 은 forecast 가 비어있을 때만 actual 을 보는 결함 — forecast
    // 가 있으면 actual.y 가 y축 범위 밖으로 떨어져 데이터 점이 차트 영역 밖에 박힘.
    const yValues = actual.map(d => +d.y)
      .concat(forecast.flatMap(d => [+d.low, +d.mid, +d.high]));
    const yMin = d3.min(yValues);
    const yMax = d3.max(yValues);
    const yPad = (yMax - yMin) * 0.1 || 1;
    const y = d3.scaleLinear().domain([yMin - yPad, yMax + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);

    y.ticks(5).forEach(v => {
      svg.append('line')
        .attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', y(v)).attr('y2', y(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.18).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('.0f')(v));
    });

    const occupancy = renderAnnotations(svg, payload, zones, t,
      (xv) => x(String(xv)), (yv) => y(+yv));

    // v5.4.8 — 실측 ↔ 예측 시각 연결 (표준 fan chart 컨벤션).
    // 이전: cone 과 forecast 선이 forecast 의 첫 해부터 시작 → actual 마지막 점과
    // 단절. 픽스: actual 의 마지막 점을 forecast 의 *bridge 첫 점* 으로 prepend.
    // cone 은 그 점에서 low=high=actual.y (한 점에서 시작해 미래로 확장하는 fan
    // 형태), mid 선은 actual 끝점에서 시작하는 dashed 연속선.
    let forecastBridge = forecast;
    if (forecast.length && actual.length) {
      const lastA = actual[actual.length - 1];
      forecastBridge = [
        { x: lastA.x, low: +lastA.y, mid: +lastA.y, high: +lastA.y },
        ...forecast,
      ];
    }

    // Forecast cone (low~high) — render before lines so it's behind
    if (forecastBridge.length) {
      const area = d3.area().x(d => x(String(d.x)))
        .y0(d => y(+d.low)).y1(d => y(+d.high)).curve(d3.curveLinear);  // CHART-AP-30
      svg.append('path').attr('d', area(forecastBridge))
        .attr('fill', t.accent).attr('fill-opacity', 0.15);
    }

    // Actual line
    const lineA = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveLinear);  // CHART-AP-30
    svg.append('path').attr('d', lineA(actual)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.6);
    // Forecast (mid) dashed line — bridge prepended for visual continuity
    if (forecastBridge.length) {
      const lineF = d3.line().x(d => x(String(d.x))).y(d => y(+d.mid)).curve(d3.curveLinear);  // CHART-AP-30
      svg.append('path').attr('d', lineF(forecastBridge)).attr('fill', 'none')
        .attr('stroke', t.accent).attr('stroke-width', 1.6).attr('stroke-dasharray', '3,2');
    }
    // Fork point
    if (payload.data.fork_at) {
      const fx = x(String(payload.data.fork_at));
      if (fx != null) {
        svg.append('line').attr('x1', fx).attr('x2', fx).attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
          .attr('stroke', t.muted).attr('stroke-width', 0.8).attr('stroke-dasharray', '2,2');
        svg.append('text').attr('x', fx).attr('y', zones.data.y - 4).attr('text-anchor', 'middle')
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
          .text('실측↔예측');
      }
    }

    // End markers
    const lastA = actual[actual.length - 1];
    svg.append('circle').attr('cx', x(String(lastA.x))).attr('cy', y(+lastA.y)).attr('r', 3.2).attr('fill', t.text);
    placeEndLabel(svg, x(String(lastA.x)), y(+lastA.y), String(lastA.y), t, occupancy, zones, t.text);
    if (forecast.length) {
      const lastF = forecast[forecast.length - 1];
      svg.append('circle').attr('cx', x(String(lastF.x))).attr('cy', y(+lastF.mid)).attr('r', 3.2).attr('fill', t.accent);
      placeEndLabel(svg, x(String(lastF.x)), y(+lastF.mid), `${lastF.mid} (예측)`, t, occupancy, zones, t.accent);
    }

    // x labels
    const step = Math.max(1, Math.ceil(xVals.length / 7));
    xVals.forEach((xv, i) => {
      if (i % step !== 0 && i !== xVals.length - 1) return;
      svg.append('text').attr('x', x(xv)).attr('y', H - zones.bottom + 16).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(String(xv).slice(0, 10));
    });
  }

  // ----- CHOROPLETH — 국가별 색농도 -----
  // Lazy-loaded topojson + world-atlas
  let _worldPromise = null;
  function loadWorld() {
    if (window.__WORLD_TOPO__) return Promise.resolve(window.__WORLD_TOPO__);
    if (_worldPromise) return _worldPromise;
    _worldPromise = fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')
      .then(r => r.ok ? r.json() : null)
      .then(w => { if (w) window.__WORLD_TOPO__ = w; return w; })
      .catch(() => null);
    return _worldPromise;
  }
  function loadTopojson() {
    if (window.topojson) return Promise.resolve(window.topojson);
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/topojson-client@3';
      s.onload = () => resolve(window.topojson);
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  // ISO alpha-2 → numeric (subset for common countries; extend as needed)
  const ISO_A2_TO_NUM = {
    KR: '410', JP: '392', US: '840', CN: '156', TW: '158', HK: '344',
    IN: '356', VN: '704', TH: '764', SG: '702', ID: '360', MY: '458', PH: '608',
    DE: '276', FR: '250', GB: '826', IT: '380', ES: '724', NL: '528', RU: '643',
    SA: '682', AE: '784', IR: '364', IL: '376', TR: '792', EG: '818',
    BR: '076', MX: '484', CA: '124', AR: '032',
    AU: '036', NZ: '554', ZA: '710', NG: '566'
  };

  // ============================================================
  // v5.2.0 — CANDLE / AREA (시계열 OHLC 차트)
  //
  // market_fetcher 로 fetch 한 실데이터를 받아 그림. event 마커는 mockup 의
  // Bloomberg/FT 스타일 — 차트 상단 같은 Y 베이스라인 번호 배지 + 가로 cascade
  // + leader line + 카드 하단 HTML footnote (chart-card-footnote 안에 채움).
  // ============================================================

  function _renderEventBadgesAndFootnote(stage, svg, events, xFn, zones, t) {
    // events: [{idxInData, dataItem, eventLabel, dateStr, valueY}], xFn(item) -> px
    if (!events || !events.length) {
      // 기존 footnote 비우기 (재렌더 시)
      const card = stage.parentElement;
      if (card) {
        const foot = card.querySelector('.chart-card-footnote');
        if (foot) foot.innerHTML = '';
      }
      return;
    }
    const naturalX = events.map(e => xFn(e.dataItem));
    const badgeY = zones.data.y - 14;
    const badgeR = 6;
    const minSpacing = 14;
    const badgeXs = new Array(events.length);

    // Pass 1 — 오른쪽 → 왼쪽 캐스케이드
    for (let i = events.length - 1; i >= 0; i--) {
      let bx = naturalX[i];
      if (i < events.length - 1 && bx > badgeXs[i + 1] - minSpacing) {
        bx = badgeXs[i + 1] - minSpacing;
      }
      badgeXs[i] = bx;
    }
    // Pass 2 — 왼쪽 가장자리 보호
    const minBx = zones.data.x + badgeR;
    for (let i = 0; i < events.length; i++) {
      const prevBx = i > 0 ? badgeXs[i - 1] : minBx - minSpacing;
      if (badgeXs[i] < prevBx + minSpacing) badgeXs[i] = prevBx + minSpacing;
    }

    // Draw
    events.forEach((ev, idx) => {
      const ex = naturalX[idx];
      const bx = badgeXs[idx];

      // 1) 수직 가이드 라인 (실제 이벤트 x)
      svg.append('line').attr('x1', ex).attr('x2', ex)
         .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
         .attr('stroke', t.accent).attr('stroke-opacity', 0.30)
         .attr('stroke-width', 0.8).attr('stroke-dasharray', '3,3');

      // 2) 데이터 포인트 점 (가능하면)
      if (ev.valueY != null && isFinite(ev.valueY)) {
        svg.append('circle').attr('cx', ex).attr('cy', ev.valueY)
           .attr('r', 2.5).attr('fill', t.accent)
           .attr('stroke', t.bg).attr('stroke-width', 1.2);
      }

      // 3) Leader line — 시프트된 배지만
      if (Math.abs(bx - ex) > 1) {
        svg.append('line').attr('x1', bx).attr('x2', ex)
           .attr('y1', badgeY + badgeR).attr('y2', zones.data.y - 1)
           .attr('stroke', t.accent).attr('stroke-opacity', 0.45)
           .attr('stroke-width', 0.7);
      }

      // 4) 번호 배지
      svg.append('circle').attr('cx', bx).attr('cy', badgeY)
         .attr('r', badgeR).attr('fill', t.accent);
      svg.append('text').attr('x', bx).attr('y', badgeY + 3.2)
         .attr('text-anchor', 'middle')
         .attr('font-family', 'JetBrains Mono, monospace')
         .attr('font-size', 8).attr('font-weight', 700)
         .attr('fill', t.bg)
         .text(idx + 1);
    });

    // 5) HTML footnote — chart-card 안에 .chart-card-footnote div 채우기.
    //    재렌더 시 innerHTML 만 갱신 (DOM duplicate 회피).
    const card = stage.parentElement;
    if (!card) return;
    let foot = card.querySelector('.chart-card-footnote');
    if (!foot) {
      foot = document.createElement('div');
      foot.className = 'chart-card-footnote';
      const note = card.querySelector('.chart-card-note');
      if (note) card.insertBefore(foot, note);
      else card.appendChild(foot);
    }
    foot.innerHTML = events.map((ev, i) => {
      const date = String(ev.dateStr || '').replace(/^\d{4}-/, '');  // YYYY-MM-DD → MM-DD
      const label = String(ev.eventLabel || '').replace(/[<>]/g, '');  // strip basic html
      return `<div class="chart-note-row">`
        + `<span class="chart-note-num">${i + 1}</span>`
        + `<span class="chart-note-date">${date}</span>`
        + `<span class="chart-note-text">${label}</span>`
        + `</div>`;
    }).join('');
  }

  function drawCandle(stage, payload, t) {
    const raw = (payload.data || []).filter(d =>
      isFinite(+d.close) && isFinite(+d.open)
      && isFinite(+d.high) && isFinite(+d.low)
    );
    if (raw.length < 2) return;
    const W = 760;
    const eventsCount = raw.filter(d => d.event).length;
    const H = 320;
    const zones = computeZones(W, H, {
      left: 60, right: 60,
      top: eventsCount ? 30 : 18,
      bottom: 30,
    });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    const x = d3.scaleBand()
      .domain(raw.map(d => String(d.date)))
      .range([zones.data.x, zones.data.x + zones.data.w])
      .padding(0.25);
    const yMin = d3.min(raw, d => +d.low);
    const yMax = d3.max(raw, d => +d.high);
    const yPad = (yMax - yMin) * 0.06 || 1;
    const y = d3.scaleLinear()
      .domain([yMin - yPad, yMax + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);

    // Y grid + labels
    y.ticks(5).forEach(v => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', y(v)).attr('y2', y(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.18).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(v >= 1000 ? d3.format(',.0f')(v) : d3.format('.2f')(v));
    });

    // v7.0.0 — annotation 개방 (사건 vline·임계 hline·국면 band). 기존 payload
    // 에 annotations 가 없으면 no-op (렌더 불변).
    renderAnnotations(svg, payload, zones, t,
      (xv) => { const px = x(String(xv)); return px == null ? null : px + x.bandwidth() / 2; },
      (yv) => y(+yv));

    // Candles — body + wick. accent = bull (close>=open), down = bear.
    raw.forEach(d => {
      const cx = x(String(d.date)) + x.bandwidth() / 2;
      const bw = Math.max(2, x.bandwidth() - 1);
      const up = +d.close >= +d.open;
      const col = up ? t.accent : (t.down || '#C45C4C');
      // wick
      svg.append('line').attr('x1', cx).attr('x2', cx)
        .attr('y1', y(+d.high)).attr('y2', y(+d.low))
        .attr('stroke', col).attr('stroke-width', 0.9);
      // body — bull 은 outline, bear 는 fill (mono guide 정합)
      const yTop = Math.min(y(+d.open), y(+d.close));
      const bodyH = Math.max(1, Math.abs(y(+d.close) - y(+d.open)));
      svg.append('rect').attr('x', cx - bw / 2).attr('y', yTop)
        .attr('width', bw).attr('height', bodyH)
        .attr('fill', up ? 'none' : col)
        .attr('stroke', col).attr('stroke-width', 1);
    });

    // v7.9.9 — 대표 이동평균선 오버레이 (item 1, 사용자 요청). payload.moving_average
    // = {period:N, label} 또는 숫자 N. close 의 단순이동평균(SMA)을 캔들 위에 선으로.
    const maCfg = payload.moving_average;
    if (maCfg) {
      const period = Math.max(2, +(maCfg.period || maCfg) || 20);
      const maLabel = maCfg.label || `${period}일 이동평균`;
      const maPts = [];
      raw.forEach((d, i) => {
        if (i < period - 1) return;
        let s = 0;
        for (let j = i - period + 1; j <= i; j += 1) s += +raw[j].close;
        maPts.push({ cx: x(String(d.date)) + x.bandwidth() / 2, cy: y(s / period) });
      });
      if (maPts.length >= 2) {
        const ln = d3.line().x(p => p.cx).y(p => p.cy).curve(d3.curveLinear);
        svg.append('path').attr('d', ln(maPts)).attr('fill', 'none')
          .attr('stroke', t.muted).attr('stroke-width', 1.5).attr('stroke-opacity', 0.92);
        // 범례 — 좌상단, 선 견본 + 라벨
        svg.append('line').attr('x1', zones.data.x + 2).attr('x2', zones.data.x + 20)
          .attr('y1', zones.data.y + 8).attr('y2', zones.data.y + 8)
          .attr('stroke', t.muted).attr('stroke-width', 1.5);
        svg.append('text').attr('x', zones.data.x + 25).attr('y', zones.data.y + 11)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.muted)
          .text(maLabel);
      }
    }

    // X labels — sparse, MM-DD
    const step = Math.max(1, Math.ceil(raw.length / 7));
    raw.forEach((d, i) => {
      if (i % step !== 0 && i !== raw.length - 1) return;
      const cx = x(String(d.date)) + x.bandwidth() / 2;
      svg.append('text').attr('x', cx).attr('y', zones.data.y + zones.data.h + 16)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(String(d.date).slice(5));
    });

    // Event 배지 + footnote
    const events = raw
      .map((d, i) => ({ idxInData: i, dataItem: d, eventLabel: d.event, dateStr: d.date, valueY: y(+d.close) }))
      .filter(e => e.eventLabel);
    _renderEventBadgesAndFootnote(
      stage, svg, events,
      (item) => x(String(item.date)) + x.bandwidth() / 2,
      zones, t,
    );
  }

  function drawArea(stage, payload, t) {
    // data shape: [{x, y, event?}]  — line 과 동일하지만 gradient fill 강조.
    const data = (payload.data || []).filter(d => isFinite(+d.y));
    if (data.length < 2) return;
    const W = 760, H = 320;
    const eventsCount = data.filter(d => d.event).length;
    const zones = computeZones(W, H, {
      left: 60, right: 60,
      top: eventsCount ? 30 : 18,
      bottom: 30,
    });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    const x = d3.scalePoint().domain(data.map(d => String(d.x)))
      .range([zones.data.x, zones.data.x + zones.data.w]).padding(0.05);
    const yExtent = d3.extent(data, d => +d.y);
    const yPad = (yExtent[1] - yExtent[0]) * 0.10 || 1;
    const y = d3.scaleLinear().domain([yExtent[0] - yPad, yExtent[1] + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);

    // Y grid + labels
    y.ticks(5).forEach(v => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', y(v)).attr('y2', y(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.18).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(v >= 1000 ? d3.format(',.0f')(v) : d3.format('.2f')(v));
    });

    // v7.0.0 — annotation 개방 (line 과 동일 계약). payload 에 없으면 no-op.
    renderAnnotations(svg, payload, zones, t,
      (xv) => x(String(xv)), (yv) => y(+yv));

    // Gradient fill
    const gradId = `grad-area-${stage.getAttribute('data-chart-id') || Math.random().toString(36).slice(2,8)}`;
    const grad = svg.append('defs').append('linearGradient')
      .attr('id', gradId).attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 1);
    grad.append('stop').attr('offset', '0%').attr('stop-color', t.accent).attr('stop-opacity', 0.28);
    grad.append('stop').attr('offset', '100%').attr('stop-color', t.accent).attr('stop-opacity', 0.02);

    // CHART-AP-30 — 실제 데이터 경로 (곡선 보간 금지).
    const lineGen = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveLinear);
    const areaGen = d3.area().x(d => x(String(d.x)))
      .y0(zones.data.y + zones.data.h).y1(d => y(+d.y)).curve(d3.curveLinear);
    svg.append('path').attr('d', areaGen(data)).attr('fill', `url(#${gradId})`);
    svg.append('path').attr('d', lineGen(data)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.4);

    // End marker
    const last = data[data.length - 1];
    svg.append('circle').attr('cx', x(String(last.x))).attr('cy', y(+last.y))
      .attr('r', 3.5).attr('fill', t.accent);

    // X labels (sparse)
    const step = Math.max(1, Math.ceil(data.length / 7));
    data.forEach((d, i) => {
      if (i % step !== 0 && i !== data.length - 1) return;
      svg.append('text').attr('x', x(String(d.x))).attr('y', zones.data.y + zones.data.h + 16)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(String(d.x).slice(-5));
    });

    // Event 배지 + footnote
    const events = data
      .map((d, i) => ({ idxInData: i, dataItem: d, eventLabel: d.event, dateStr: d.x, valueY: y(+d.y) }))
      .filter(e => e.eventLabel);
    _renderEventBadgesAndFootnote(
      stage, svg, events,
      (item) => x(String(item.x)),
      zones, t,
    );
  }

  async function drawChoropleth(stage, payload, t) {
    const data = (payload.data || []).filter(d => d.country_code && isFinite(+d.value));
    if (!data.length) return;
    const W = 760, H = 380;
    const zones = computeZones(W, H, { left: 0, right: 0, top: 0, bottom: 0 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    svg.append('rect').attr('width', W).attr('height', H).attr('fill', t.bg);

    let topojson, world;
    try {
      [topojson, world] = await Promise.all([loadTopojson(), loadWorld()]);
    } catch (e) { console.warn('[charts] choropleth failed to load topo', e); return; }
    if (!topojson || !world) return;

    const projection = d3.geoMercator()
      .scale(120).center([20, 25]).translate([W / 2, H * 0.55]);
    const path = d3.geoPath(projection);
    const countries = topojson.feature(world, world.objects.countries);

    // Value → fill (5 buckets via quantile)
    const values = data.map(d => +d.value);
    const scale = (payload.scale || 'quantile').toLowerCase();
    let buckets;
    if (scale === 'quantile') {
      const sorted = values.slice().sort((a, b) => a - b);
      buckets = [
        sorted[0],
        d3.quantile(sorted, 0.25),
        d3.quantile(sorted, 0.5),
        d3.quantile(sorted, 0.75),
        sorted[sorted.length - 1]
      ];
    } else {
      const min = d3.min(values), max = d3.max(values);
      buckets = [min, min + (max - min) / 4, min + (max - min) / 2, min + (max - min) * 3 / 4, max];
    }

    // Build numeric_id → value lookup
    const valueByNum = {};
    data.forEach(d => {
      const num = ISO_A2_TO_NUM[String(d.country_code).toUpperCase()];
      if (num) valueByNum[num] = +d.value;
    });

    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    function bucketFor(v) {
      if (v == null) return null;
      if (v <= buckets[1]) return idp('dots');
      if (v <= buckets[2]) return idp('hatch-wide');
      if (v <= buckets[3]) return idp('hatch-tight');
      return null;  // top bucket = accent solid
    }

    // Render base + value fills
    countries.features.forEach(f => {
      const v = valueByNum[String(f.id).padStart(3, '0')];
      let fill = t.card;
      if (v != null) {
        const pat = bucketFor(v);
        fill = pat ? `url(#${pat})` : t.accent;
      }
      svg.append('path').attr('d', path(f)).attr('fill', fill)
        .attr('stroke', t.text).attr('stroke-width', 0.3).attr('stroke-opacity', 0.4);
    });

    // Legend (bottom-left)
    const lx = 16, ly = H - 60;
    svg.append('text').attr('x', lx).attr('y', ly - 4)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
      .attr('font-weight', 700).attr('fill', t.text)
      .text(payload.value_label || 'Value');
    [
      { label: `≤${d3.format('.0f')(buckets[1])}`, fill: `url(#${idp('dots')})` },
      { label: `~${d3.format('.0f')(buckets[2])}`, fill: `url(#${idp('hatch-wide')})` },
      { label: `~${d3.format('.0f')(buckets[3])}`, fill: `url(#${idp('hatch-tight')})` },
      { label: `≤${d3.format('.0f')(buckets[4])}`, fill: t.accent },
    ].forEach((b, i) => {
      const y = ly + i * 14;
      svg.append('rect').attr('x', lx).attr('y', y).attr('width', 18).attr('height', 10)
        .attr('fill', b.fill).attr('stroke', t.text).attr('stroke-width', 0.4);
      svg.append('text').attr('x', lx + 24).attr('y', y + 9)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.text)
        .text(b.label);
    });

    // Country labels for top values (max 5)
    const sorted = data.slice().sort((a, b) => +b.value - +a.value).slice(0, 5);
    sorted.forEach(d => {
      const num = ISO_A2_TO_NUM[String(d.country_code).toUpperCase()];
      const f = countries.features.find(ft => String(ft.id).padStart(3, '0') === num);
      if (!f) return;
      const c = path.centroid(f);
      if (!isFinite(c[0]) || !isFinite(c[1])) return;
      svg.append('text').attr('x', c[0]).attr('y', c[1])
        .attr('text-anchor', 'middle').attr('font-family', 'Noto Sans KR').attr('font-size', 9)
        .attr('fill', t.text).attr('font-weight', 700)
        .text(`${d.country_code} ${d3.format('.1f')(+d.value)}`);
    });
  }

  // ============================================================
  // Sparkline — compact strip (v5.2.9)
  //
  // 22px 인라인 sparkline. 풀 카드 (180px stage + axes + labels) 와 달리
  // 축·라벨·이벤트 마커 없이 단순 linear line + 끝점 dot 만. 첫·끝 close
  // 비교로 up/down 색 자동.
  //
  // v5.2.9 (사용자 catch): curveMonotoneX 는 일간 종가 변동을 부드러운
  // 베지에로 평탄화 → 실제 가격 변동 (jaggedness) 이 시각적으로 사라짐.
  // curveLinear 로 교체해 segment-by-segment 가격 흐름을 그대로 표시. 5종
  // 추가 보강: (1) min/max 점에 작은 dot 으로 극값 표시 (2) zero-line
  // (첫 종가) 를 옅은 dashed 로 표기해 변동의 기준선 보이기 (3) 행 높이
  // 22px 유지 (외부 layout 의존성 lock-in 보호).
  //
  // Layout 안정 후 그리기 (rAF 2회 + ResizeObserver). 0px width 에서 그리면
  // ============================================================
  // v5.2.14 신규 7종 (FT/Economist 스타일)
  // ============================================================

  // ----- SCATTER (라벨 산점도) -----
  function drawScatter(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.x) && isFinite(+d.y));
    if (data.length < 3) return;
    const W = 720, H = 360;
    const zones = computeZones(W, H, { left: 60, right: 30, top: 30, bottom: 40 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const xExt = d3.extent(data, d => +d.x), yExt = d3.extent(data, d => +d.y);
    const xPad = (xExt[1] - xExt[0]) * 0.08 || 1;
    const yPad = (yExt[1] - yExt[0]) * 0.08 || 1;
    const xScale = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    const yScale = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);
    // grid
    yScale.ticks(5).forEach(yt => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yScale(yt)).attr('y2', yScale(yt))
        .attr('stroke', t.border).attr('stroke-opacity', 0.4).attr('stroke-dasharray', '2 3');
    });
    // axes
    svg.append('g').attr('transform', `translate(0,${zones.data.y + zones.data.h})`)
      .call(d3.axisBottom(xScale).ticks(6))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    svg.append('g').attr('transform', `translate(${zones.data.x},0)`)
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    // labels (axis)
    if (payload.x_label) {
      svg.append('text').attr('x', W / 2).attr('y', H - 8).attr('text-anchor', 'middle')
        .attr('font-size', 11).attr('fill', t.muted).text(payload.x_label);
    }
    if (payload.y_label) {
      svg.append('text').attr('transform', `rotate(-90)`).attr('x', -H / 2).attr('y', 14)
        .attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', t.muted).text(payload.y_label);
    }
    // v7.0.0 — annotation 개방. top 마진(30px)이 vline callout(32px)보다 작아
    // vline 은 제외 (잘림 = CHART-AP-5 회피) — 사건 점 강조는 'point' kind 로.
    renderAnnotations(svg,
      { annotations: (payload.annotations || []).filter(a => a.kind !== 'vline') },
      zones, t, xScale, yScale);

    // points
    const pts = data.map(d => ({
      d, cx: xScale(+d.x), cy: yScale(+d.y), isAccent: !!d.accent,
      label: String(d.label || ''),
    }));
    pts.forEach(p => {
      svg.append('circle').attr('cx', p.cx).attr('cy', p.cy).attr('r', 5)
        .attr('fill', p.isAccent ? t.accent : t.text).attr('fill-opacity', 0.85);
    });

    // v7.9.8 — 라벨 충돌 회피 (CHART-AP-33, 사용자 catch: IV 스큐 우측 군집
    // '풋 1,525'/'콜 1,527.5' 라벨 중첩). ① 우측 끝 점은 라벨을 왼쪽에 둠(plot
    // 밖 잘림 방지) ② 같은 쪽 라벨끼리 세로 dodge(minGap 13) ③ 점에서 멀어진
    // 라벨엔 가는 connector. 점·축 위치는 실제 값 그대로(불변).
    const rightEdge = zones.data.x + zones.data.w * 0.66;
    const loY = zones.data.y + 6, hiY = zones.data.y + zones.data.h - 4;
    const sides = { L: [], R: [] };
    pts.forEach(p => { (p.cx > rightEdge ? sides.L : sides.R).push(p); });
    Object.keys(sides).forEach(sideKey => {
      const grp = sides[sideKey];
      if (!grp.length) return;
      const dodged = dodgeYs(grp.map(p => p.cy + 4), 13, loY, hiY);
      grp.forEach((p, i) => {
        const ly = dodged[i];
        const left = sideKey === 'L';
        const lx = left ? p.cx - 9 : p.cx + 9;
        const col = p.isAccent ? t.accent : t.text;
        if (Math.abs(ly - (p.cy + 4)) > 6 || left) {
          svg.append('line').attr('x1', p.cx).attr('y1', p.cy)
            .attr('x2', lx).attr('y2', ly - 3)
            .attr('stroke', col).attr('stroke-width', 0.6).attr('stroke-opacity', 0.4);
        }
        svg.append('text').attr('x', lx).attr('y', ly)
          .attr('text-anchor', left ? 'end' : 'start')
          .attr('font-size', 10).attr('font-family', 'Noto Sans KR')
          .attr('fill', col).text(p.label);
      });
    });
  }

  // ----- STACKED AREA (시계열 누적) -----
  function drawStackedArea(stage, payload, t) {
    const series = (payload.data && payload.data.series) || payload.series || [];
    if (!series.length || series.length > 5) return;
    if (!series[0].values || series[0].values.length < 5) return;
    const W = 720, H = 320;
    const zones = computeZones(W, H, { left: 50, right: 30, top: 50, bottom: 36 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const xs = series[0].values.map(p => p.x);
    const isNumX = xs.every(v => isFinite(+v));
    const xScale = isNumX
      ? d3.scaleLinear().domain(d3.extent(xs.map(v => +v))).range([zones.data.x, zones.data.x + zones.data.w])
      : d3.scalePoint().domain(xs.map(String)).range([zones.data.x, zones.data.x + zones.data.w]);
    // build stacked dataset: for each x index, sum series in order
    const stackData = xs.map((x, i) => {
      const row = { x };
      series.forEach(s => { row[s.name] = +(s.values[i] && s.values[i].y) || 0; });
      return row;
    });
    const stack = d3.stack().keys(series.map(s => s.name))(stackData);
    const yMax = d3.max(stack[stack.length - 1], d => d[1]);
    const yScale = d3.scaleLinear().domain([0, yMax]).range([zones.data.y + zones.data.h, zones.data.y]);
    const area = d3.area()
      .x((d, i) => isNumX ? xScale(+xs[i]) : xScale(String(xs[i])))
      .y0(d => yScale(d[0])).y1(d => yScale(d[1]))
      .curve(d3.curveLinear);  // CHART-AP-30 — 점유율도 실제 데이터 경로
    // grid
    yScale.ticks(5).forEach(yt => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yScale(yt)).attr('y2', yScale(yt))
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
    // v7.0.0 — annotation 개방. 상단 legend 와 vline callout 충돌 → vline 제외.
    renderAnnotations(svg,
      { annotations: (payload.annotations || []).filter(a => a.kind !== 'vline') },
      zones, t,
      (xv) => isNumX ? xScale(+xv) : xScale(String(xv)), yScale);

    // layers
    const idp = (n) => `${prefix}-${n}`;
    stack.forEach((layer, i) => {
      const fill = i === stack.length - 1 ? t.accent : `url(#${idp(PATTERN_SEQ[i % PATTERN_SEQ.length])})`;
      svg.append('path').datum(layer).attr('fill', fill).attr('d', area)
        .attr('stroke', t.bg).attr('stroke-width', 0.5);
    });
    // axes
    svg.append('g').attr('transform', `translate(0,${zones.data.y + zones.data.h})`)
      .call(isNumX ? d3.axisBottom(xScale).ticks(6) : d3.axisBottom(xScale))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    svg.append('g').attr('transform', `translate(${zones.data.x},0)`)
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    // legend (top)
    const lg = svg.append('g').attr('transform', `translate(${zones.data.x},${zones.data.y - 24})`);
    series.forEach((s, i) => {
      const fill = i === stack.length - 1 ? t.accent : `url(#${idp(PATTERN_SEQ[i % PATTERN_SEQ.length])})`;
      const g = lg.append('g').attr('transform', `translate(${i * 110},0)`);
      g.append('rect').attr('width', 10).attr('height', 10).attr('fill', fill);
      g.append('text').attr('x', 14).attr('y', 9).attr('font-size', 10).attr('fill', t.text).text(s.name);
    });
  }

  // ----- LOLLIPOP (bar 의 우아한 대안) -----
  function drawLollipop(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value));
    if (data.length < 8 || data.length > 15) return;
    const W = 720, rowH = 26;
    // v7.0.0 — vline annotation (값 임계 콜아웃) 동반 시 top 마진 확장 (잘림 방지).
    const annTop = (payload.annotations || []).some(a => a.kind === 'vline') ? 60 : 24;
    const H = annTop + 26 + data.length * rowH + 30;
    const zones = computeZones(W, H, { left: 160, right: 60, top: annTop, bottom: 30 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const max = d3.max(data, d => Math.abs(+d.value)) || 1;
    const xScale = d3.scaleLinear().domain([0, max * 1.1])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    // grid
    xScale.ticks(5).forEach(xt => {
      svg.append('line').attr('x1', xScale(xt)).attr('x2', xScale(xt))
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
    data.forEach((d, i) => {
      const y = zones.data.y + 14 + i * rowH;
      const xv = xScale(+d.value);
      const isAccent = i === 0;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11).attr('fill', t.text)
        .text(String(d.label || '').slice(0, 22));
      svg.append('line').attr('x1', zones.data.x).attr('x2', xv).attr('y1', y).attr('y2', y)
        .attr('stroke', t.muted).attr('stroke-width', 1.2);
      svg.append('circle').attr('cx', xv).attr('cy', y).attr('r', 6)
        .attr('fill', isAccent ? t.accent : t.text);
      svg.append('text').attr('x', xv + 10).attr('y', y + 4).attr('font-size', 11)
        .attr('font-family', 'Noto Serif KR').attr('font-weight', 700).attr('fill', t.text)
        .text(d3.format(',.1f')(+d.value));
    });
    // x axis
    svg.append('g').attr('transform', `translate(0,${zones.data.y + zones.data.h + 4})`)
      .call(d3.axisBottom(xScale).ticks(5))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 9);
    // v7.0.0 — annotation 개방 (값 축 기준: vline=임계값, band=값 구간).
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }

  // ----- SLOPE (slopegraph) -----
  function drawSlope(stage, payload, t) {
    const items = (payload.data && payload.data.items) || payload.items || [];
    const leftLabel = (payload.data && payload.data.left_label) || payload.left_label || '';
    const rightLabel = (payload.data && payload.data.right_label) || payload.right_label || '';
    if (items.length < 3 || items.length > 10) return;
    const W = 640, H = 360;
    const zones = computeZones(W, H, { left: 130, right: 130, top: 50, bottom: 30 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const vals = items.flatMap(d => [+d.a, +d.b]);
    const yScale = d3.scaleLinear().domain([d3.min(vals), d3.max(vals)]).nice()
      .range([zones.data.y + zones.data.h, zones.data.y]);
    const xA = zones.data.x, xB = zones.data.x + zones.data.w;
    // axis headers
    svg.append('text').attr('x', xA).attr('y', zones.data.y - 18).attr('text-anchor', 'middle')
      .attr('font-size', 12).attr('font-weight', 700).attr('fill', t.text).text(leftLabel);
    svg.append('text').attr('x', xB).attr('y', zones.data.y - 18).attr('text-anchor', 'middle')
      .attr('font-size', 12).attr('font-weight', 700).attr('fill', t.text).text(rightLabel);
    const rows = items.map(it => ({
      it, yA: yScale(+it.a), yB: yScale(+it.b), rising: +it.b > +it.a,
    }));
    // lines + dots (실제 값 위치)
    rows.forEach(r => {
      const stroke = r.rising ? t.accent : t.muted;
      svg.append('line').attr('x1', xA).attr('y1', r.yA).attr('x2', xB).attr('y2', r.yB)
        .attr('stroke', stroke).attr('stroke-width', 1.4);
      svg.append('circle').attr('cx', xA).attr('cy', r.yA).attr('r', 4).attr('fill', t.text);
      svg.append('circle').attr('cx', xB).attr('cy', r.yB).attr('r', 4)
        .attr('fill', r.rising ? t.accent : t.text);
    });
    // CHART-AP-26 — 동일/근접 값 다수 시 라벨이 같은 y 에 겹침 (예: 모두 100.0 기준선).
    // 라벨 baseline 을 최소 간격으로 dodge + 범위 클램프. 점은 실제 위치 유지, 멀어지면 connector.
    const minGap = 13, lo = zones.data.y - 4, hi = zones.data.y + zones.data.h + 12;
    const dodge = (ys) => {
      const order = ys.map((y, i) => i).sort((p, q) => ys[p] - ys[q]);
      const adj = order.map(i => ys[i]);
      for (let i = 1; i < adj.length; i++)
        if (adj[i] - adj[i - 1] < minGap) adj[i] = adj[i - 1] + minGap;
      const over = adj[adj.length - 1] - hi;
      if (over > 0) for (let i = 0; i < adj.length; i++) adj[i] -= over;
      if (adj[0] < lo) { const d = lo - adj[0]; for (let i = 0; i < adj.length; i++) adj[i] += d; }
      const out = new Array(ys.length);
      order.forEach((origI, k) => { out[origI] = adj[k]; });
      return out;
    };
    const fmt = d3.format(',.1f');
    const ladY = dodge(rows.map(r => r.yA));
    const lbdY = dodge(rows.map(r => r.yB));
    rows.forEach((r, i) => {
      if (Math.abs(ladY[i] - r.yA) > 2)
        svg.append('line').attr('x1', xA - 4).attr('y1', r.yA).attr('x2', xA - 9).attr('y2', ladY[i])
          .attr('stroke', t.border).attr('stroke-width', 0.6);
      if (Math.abs(lbdY[i] - r.yB) > 2)
        svg.append('line').attr('x1', xB + 4).attr('y1', r.yB).attr('x2', xB + 9).attr('y2', lbdY[i])
          .attr('stroke', t.border).attr('stroke-width', 0.6);
      svg.append('text').attr('x', xA - 10).attr('y', ladY[i] + 4).attr('text-anchor', 'end')
        .attr('font-size', 11).attr('fill', t.text)
        .text(`${r.it.label} ${fmt(+r.it.a)}`);
      svg.append('text').attr('x', xB + 10).attr('y', lbdY[i] + 4).attr('font-size', 11)
        .attr('fill', r.rising ? t.accent : t.text).text(fmt(+r.it.b));
    });
  }

  // ----- SMALL MULTIPLES (4-9 면 그리드) -----
  function drawSmallMultiples(stage, payload, t) {
    const panels = (payload.data && payload.data.panels) || payload.panels || [];
    if (panels.length < 4 || panels.length > 9) return;
    const W = 720, H = 360;
    const cols = panels.length <= 4 ? 2 : 3;
    const rows = Math.ceil(panels.length / cols);
    const padX = 12, padY = 12;
    const cellW = (W - padX * (cols + 1)) / cols;
    const cellH = (H - padY * (rows + 1)) / rows;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    // shared y domain
    const allVals = panels.flatMap(p => (p.series || []).map(d => +d.y).filter(isFinite));
    const yDomain = d3.extent(allVals);
    panels.forEach((p, idx) => {
      const cx = padX + (idx % cols) * (cellW + padX);
      const cy = padY + Math.floor(idx / cols) * (cellH + padY);
      svg.append('rect').attr('x', cx).attr('y', cy).attr('width', cellW).attr('height', cellH)
        .attr('fill', 'none').attr('stroke', t.border).attr('stroke-width', 0.6);
      svg.append('text').attr('x', cx + 8).attr('y', cy + 16).attr('font-size', 12)
        .attr('font-weight', 700).attr('fill', t.text).text(String(p.label || ''));
      const data = (p.series || []).filter(d => isFinite(+d.y));
      if (data.length < 2) return;
      const xs = data.map(d => d.x);
      const xExt = d3.extent(xs.map(v => +v));
      const xScale = d3.scaleLinear().domain(xExt).range([cx + 8, cx + cellW - 8]);
      const yScale = d3.scaleLinear().domain(yDomain).range([cy + cellH - 12, cy + 24]);
      const line = d3.line().x(d => xScale(+d.x)).y(d => yScale(+d.y)).curve(d3.curveLinear);  // CHART-AP-30
      svg.append('path').datum(data).attr('fill', 'none')
        .attr('stroke', t.text).attr('stroke-width', 1.4).attr('d', line);
    });
  }

  // ----- WATERFALL (P&L 스타일) -----
  // v7.1.0 리디자인 (사용자 승인): 증가=액센트 / 감소=하락색 / 합계=잉크색 3색
  // 의미론 + 부호 라벨 (+24.5 / −3.0) + 수평 라벨 (회전 폐기, 길면 2줄) + 시작·끝
  // 합계 기둥 배경 밴드 + 가는 실선 연결선.
  // CHART-AP-27 호환 — neg row 의 value 가 magnitude(양수)든 음수든 동일하게
  // 동작: delta = (type==='neg' ? -1 : +1) * |value|.
  function drawWaterfall(stage, payload, t) {
    const items = (payload.data || []).slice();
    if (items.length < 3) return;
    if (items[0].type !== 'total' || items[items.length - 1].type !== 'total') return;
    let running = 0;
    items.forEach(it => {
      const mag = Math.abs(+it.value) || 0;
      if (it.type === 'total') { it.y0 = Math.min(0, mag); it.y1 = Math.max(0, mag); running = mag; }
      else if (it.type === 'pos') { it.y0 = running; it.y1 = running + mag; running = it.y1; }
      else { it.y0 = running - mag; it.y1 = running; running = it.y0; }
    });
    const W = 720, H = 330;
    const x0 = 58, x1 = W - 24, yTop = 30, yBot = H - 58;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const xs = d3.scaleBand().domain(items.map((d, i) => i)).range([x0, x1]).padding(0.34);
    const yLo = Math.min(0, d3.min(items, d => Math.min(d.y0, d.y1)));
    const yHi = d3.max(items, d => Math.max(d.y0, d.y1)) * 1.12 || 1;
    const ys = d3.scaleLinear().domain([yLo, yHi]).range([yBot, yTop]);
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(av);
      if (av >= 10) return d3.format(',.1f')(av);
      return d3.format(',.2f')(av);
    };
    // y 눈금 — 옅은 가로선 + 좌측 숫자, 0-기준선 crisp
    ys.ticks(4).forEach(v => {
      svg.append('text').attr('x', x0 - 8).attr('y', ys(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'IBM Plex Mono, monospace').attr('font-size', 9)
        .attr('fill', t.muted).text(fmt(v));
      if (v !== 0) svg.append('line').attr('x1', x0).attr('x2', x1)
        .attr('y1', ys(v)).attr('y2', ys(v))
        .attr('stroke', t.text).attr('stroke-opacity', 0.06);
    });
    svg.append('line').attr('x1', x0).attr('x2', x1).attr('y1', ys(0)).attr('y2', ys(0))
      .attr('stroke', t.text).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
    items.forEach((it, i) => {
      const bx = xs(i), bw = xs.bandwidth();
      const isTotal = it.type === 'total';
      const col = isTotal ? t.text : (it.type === 'pos' ? t.accent : t.down);
      // 시작·끝 합계 기둥 배경 밴드 (앵커)
      if (isTotal) {
        svg.append('rect').attr('x', bx - 7).attr('y', yTop - 6).attr('width', bw + 14)
          .attr('height', yBot - yTop + 30).attr('rx', 4)
          .attr('fill', t.text).attr('fill-opacity', 0.045).attr('data-anim', 'static');
      }
      svg.append('rect').attr('x', bx).attr('y', ys(it.y1)).attr('width', bw)
        .attr('height', Math.max(1.5, ys(it.y0) - ys(it.y1))).attr('rx', 1.5)
        .attr('fill', col).attr('fill-opacity', isTotal ? 0.92 : 0.88);
      const sign = isTotal ? '' : (it.type === 'pos' ? '+' : '−');
      svg.append('text').attr('x', bx + bw / 2).attr('y', ys(it.y1) - 7).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Serif KR').attr('font-size', isTotal ? 13.5 : 12)
        .attr('font-weight', 700).attr('fill', col)
        .text(sign + fmt(it.value));
      // 연결선 (가는 실선) — 다음 막대 시작 레벨로
      if (i < items.length - 1) {
        const yc = ys(it.type === 'neg' ? it.y0 : it.y1);
        svg.append('line').attr('x1', bx + bw).attr('x2', xs(i + 1))
          .attr('y1', yc).attr('y2', yc)
          .attr('stroke', t.text).attr('stroke-opacity', 0.35).attr('stroke-width', 0.8);
      }
      // 수평 라벨 — 길면 2줄 (회전 금지)
      const lbl = String(it.label || '');
      const lines = lbl.length > 6
        ? [lbl.slice(0, Math.ceil(lbl.length / 2)), lbl.slice(Math.ceil(lbl.length / 2))]
        : [lbl];
      lines.forEach((ln, k) => {
        svg.append('text').attr('x', bx + bw / 2).attr('y', yBot + 16 + k * 12)
          .attr('text-anchor', 'middle').attr('font-family', 'Noto Sans KR')
          .attr('font-size', 10.5).attr('font-weight', isTotal ? 700 : 400)
          .attr('fill', isTotal ? t.text : t.muted).text(ln);
      });
    });
  }

  // ----- SANKEY (재무 분해 / 자본 배분 / 매출 → segment → 비용 → 이익) -----
  // 외부 d3-sankey 의존 없는 minimal layout — DAG 흐름.
  // 노드 자동 column 할당 (longest path), 각 column 내 vertical layout 은
  // value 비례 + 인접 padding. 링크는 source.x1 → target.x0 의 cubic Bezier.
  function drawSankey(stage, payload, t) {
    const data = payload.data || {};
    const nodes = (data.nodes || []).map(n => ({ ...n }));
    const links = (data.links || []).map(l => ({ ...l }));
    if (nodes.length < 2 || links.length < 1) return;
    const W = 760;
    const H = Math.max(320, Math.min(560, 60 + nodes.length * 28));
    // v5.4.7 — 첫 컬럼 라벨 (text-anchor: end at x0-6) 과 마지막 컬럼 라벨
    // (text-anchor: start at x1+6) 이 viewBox 안에 들어가도록 좌·우 margin 확보.
    // 이전 left=8/right=8 은 "DS 매출" / "100.0" 라벨이 음수 좌표까지 뻗어 잘림.
    const zones = computeZones(W, H, { left: 80, right: 120, top: 28, bottom: 24 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    const nodeById = new Map(nodes.map(n => [n.id, n]));
    nodes.forEach(n => { n.inValue = 0; n.outValue = 0; n.col = 0; });
    // 유효 링크만 (참조 가능)
    const validLinks = links.filter(l => {
      const src = nodeById.get(l.source), tgt = nodeById.get(l.target);
      if (!src || !tgt) return false;
      const v = +l.value;
      if (!isFinite(v) || v <= 0) return false;
      src.outValue += v;
      tgt.inValue += v;
      return true;
    });
    if (!validLinks.length) return;

    // column 할당 — topological BFS (가장 긴 경로)
    const adj = new Map(nodes.map(n => [n.id, []]));
    const inDeg = new Map(nodes.map(n => [n.id, 0]));
    validLinks.forEach(l => {
      adj.get(l.source).push(l.target);
      inDeg.set(l.target, (inDeg.get(l.target) || 0) + 1);
    });
    const queue = nodes.filter(n => inDeg.get(n.id) === 0);
    let head = 0;
    while (head < queue.length) {
      const n = queue[head++];
      (adj.get(n.id) || []).forEach(tid => {
        const tgt = nodeById.get(tid);
        tgt.col = Math.max(tgt.col, n.col + 1);
        inDeg.set(tid, inDeg.get(tid) - 1);
        if (inDeg.get(tid) === 0) queue.push(tgt);
      });
    }
    const maxCol = d3.max(nodes, n => n.col);
    if (maxCol < 1) return;  // 단일 컬럼 sankey 는 의미 X

    // v5.3.0 — sankey 전용 default palette (MONO_THEME_GUIDE 의 sankey 예외).
    // composer 가 node.color 박았으면 그것 사용, 없으면 column index 기반 fallback.
    const SANKEY_PAL = [
      '#5A7A9B', '#4C7C7A', '#A88A4C', '#9C6049',
      '#8A7553', '#6C5E8E', '#7E956D', '#B07159',
    ];
    nodes.forEach((n, i) => {
      if (!n.color) {
        // anchor (첫 컬럼이 아니면서 column 안의 max value 노드) 는 t.text 로
        n.color = n.accent ? (t.accent || t.text) : SANKEY_PAL[i % SANKEY_PAL.length];
      }
    });

    const colWidth = zones.data.w / (maxCol + 1);
    const nodeWidth = 9;
    // v5.4.7 — 중간 컬럼 노드의 위쪽 라벨 (y0-6, font 11) 과 아래쪽 value 라벨
    // (y1+14, font 10) 이 인접 노드의 라벨과 stacking 충돌하는 회귀.
    // 이전 18 은 너무 좁아 메모리/파운드리 사이에서 "65.0" ↔ "파운드리" 라벨이
    // 7px 겹쳐 시인성 박살. 36 = 위 라벨(8) + 값 라벨(7) + 텍스트 여백(5) ×2.
    const MIN_NODE_PAD = 36;
    const MAX_NODE_H_RATIO = 0.50;

    // v5.3.0 sankey 시각 균형 4원칙:
    // 1. Anchor 압축: cardinality==1 + value==globalMax 노드는 75% 추가 cap
    // 2. Source-weighted ordering: col 1+ 정렬을 incoming source y 가중평균으로
    // 3. 분기 V 분산: 원칙 2 의 자연 결과
    // 4. Column y-positioning: col 시작 y 를 expectedY 평균에 맞춤
    const colMap = d3.group(nodes, n => n.col);
    const globalMax = d3.max(Array.from(colMap.values()),
      cnodes => d3.sum(cnodes, n => Math.max(n.inValue, n.outValue))) || 1;
    const baseScale = (zones.data.h * MAX_NODE_H_RATIO) / globalMax;

    function nodeScale(n, cnodesInCol) {
      // 원칙 1: 한 컬럼 한 노드인 globalMax value 노드 추가 cap
      if (cnodesInCol.length === 1 &&
          Math.abs(Math.max(n.inValue, n.outValue) - globalMax) < 1e-6) {
        return baseScale * 0.75;
      }
      return baseScale;
    }

    const colKeys = Array.from(colMap.keys()).sort((a, b) => a - b);
    colKeys.forEach((col, idx) => {
      const cnodes = colMap.get(col);
      cnodes.forEach(n => {
        const v = Math.max(n.inValue, n.outValue);
        n.height = Math.max(6, v * nodeScale(n, cnodes));
      });
      const nodesH = d3.sum(cnodes, n => n.height);
      const totalPad = (cnodes.length - 1) * MIN_NODE_PAD;
      const totalH = nodesH + totalPad;

      let colStart;
      if (idx === 0) {
        // 첫 컬럼: value 정렬 + 중앙 정렬 (부모 없음 → fallback)
        cnodes.sort((a, b) =>
          (Math.max(b.inValue, b.outValue) - Math.max(a.inValue, a.outValue)));
        colStart = zones.data.y + (zones.data.h - totalH) / 2;
      } else {
        // 원칙 2 + 4: expectedY = Σ(src.y_center × value) / Σ(value)
        cnodes.forEach(n => {
          let sumYV = 0, sumV = 0;
          validLinks.filter(l => l.target === n.id).forEach(l => {
            const src = nodeById.get(l.source);
            const srcCenter = (src.y0 + src.y1) / 2;
            sumYV += srcCenter * l.value;
            sumV += l.value;
          });
          n.expectedY = sumV > 0 ? sumYV / sumV : zones.data.y + zones.data.h / 2;
        });
        cnodes.sort((a, b) => a.expectedY - b.expectedY);
        const meanExpY = d3.mean(cnodes, n => n.expectedY);
        colStart = meanExpY - totalH / 2;
        colStart = Math.max(zones.data.y,
          Math.min(zones.data.y + zones.data.h - totalH, colStart));
      }

      let y = colStart;
      cnodes.forEach(n => {
        n.x0 = zones.data.x + col * colWidth + 8;
        n.x1 = n.x0 + nodeWidth;
        n.y0 = y;
        n.y1 = y + n.height;
        y += n.height + MIN_NODE_PAD;
      });
    });

    // v5.4.6 — content-fit viewBox (CHART-AP-20).
    // H 공식 (max 320 / min 560) 이 작은 노드 수에선 과대 프로비저닝 → 컨텐츠가
    // 윗쪽 60~70% 만 차지하고 아래가 휑함. 가중치 큰 노드(예: 메모리 65)가 위에
    // 배치되는 자연스러운 sankey 구조와 결합돼 "위로 쏠림" 시각 인상 강화.
    // 픽스: 레이아웃 끝난 뒤 실제 content extent + 라벨 여백을 측정해 viewBox H
    // 를 타이트하게 줄이고, 컨텐츠를 desiredTop 까지 시프트. 알고리즘은 보존.
    const LABEL_PAD_ABOVE = 18;   // 중간 col 노드 위쪽 라벨 (y0-6, font 11)
    const LABEL_PAD_BELOW = 22;   // 중간 col 노드 아래쪽 value 라벨 (y1+14, font 10)
    const SVG_TOP_BREATH = 14;
    const SVG_BOT_BREATH = 14;
    let contentTop = Infinity, contentBot = -Infinity;
    nodes.forEach(n => {
      const above = (n.col > 0 && n.col < maxCol) ? LABEL_PAD_ABOVE : 0;
      const below = (n.col > 0 && n.col < maxCol) ? LABEL_PAD_BELOW : 0;
      if (n.y0 - above < contentTop) contentTop = n.y0 - above;
      if (n.y1 + below > contentBot) contentBot = n.y1 + below;
    });
    const tightH = (contentBot - contentTop) + SVG_TOP_BREATH + SVG_BOT_BREATH;
    if (tightH > 0 && tightH < H) {
      const dy = SVG_TOP_BREATH - contentTop;
      nodes.forEach(n => { n.y0 += dy; n.y1 += dy; });
      svg.attr('viewBox', `0 0 ${W} ${Math.round(tightH)}`);
    }

    // 링크 slice 할당 — 각 노드의 outgoing/incoming 을 target/source y 기준 정렬
    nodes.forEach(n => {
      n.outLinks = validLinks.filter(l => l.source === n.id);
      n.inLinks = validLinks.filter(l => l.target === n.id);
      n.outLinks.sort((a, b) => nodeById.get(a.target).y0 - nodeById.get(b.target).y0);
      n.inLinks.sort((a, b) => nodeById.get(a.source).y0 - nodeById.get(b.source).y0);
      let sy = n.y0;
      n.outLinks.forEach(l => {
        const slice = (+l.value / Math.max(n.outValue, 1e-9)) * n.height;
        l._sy0 = sy; l._sy1 = sy + slice; sy += slice;
      });
      let ty = n.y0;
      n.inLinks.forEach(l => {
        const slice = (+l.value / Math.max(n.inValue, 1e-9)) * n.height;
        l._ty0 = ty; l._ty1 = ty + slice; ty += slice;
      });
    });

    // 링크 그리기 — source.x1 → target.x0 의 4-point cubic Bezier 채워진 영역
    // v5.3.0 sankey 예외: flow color = source.color (mono 의 단일 hue 규약을
    // sankey 에 한해 완화). 흐름 추적 직관성 우선.
    const FLOW_OPACITY = 0.55;
    const NODE_OPACITY = 0.85;
    const ACCENT_OPACITY = 1.00;
    const NEG_OPACITY = 0.55;

    const linkG = svg.append('g').attr('class', 'sankey-links');
    const inFlowLabels = [];
    validLinks.forEach(l => {
      const src = nodeById.get(l.source), tgt = nodeById.get(l.target);
      const x1 = src.x1, x2 = tgt.x0;
      const midX = (x1 + x2) / 2;
      const path = [
        `M ${x1},${l._sy0}`,
        `C ${midX},${l._sy0} ${midX},${l._ty0} ${x2},${l._ty0}`,
        `L ${x2},${l._ty1}`,
        `C ${midX},${l._ty1} ${midX},${l._sy1} ${x1},${l._sy1}`,
        `Z`,
      ].join(' ');
      const isNeg = l.negative === true || (+l.value < 0);
      // flow color = source 노드 색 (적자만 t.down 빨강)
      const fill = isNeg ? (t.down || '#C9837A') : src.color;
      linkG.append('path').attr('d', path).attr('fill', fill)
        .attr('fill-opacity', isNeg ? NEG_OPACITY : FLOW_OPACITY)
        .attr('stroke', 'none');
      // v5.3.0 — 큰 흐름에 in-flow 라벨 (cut-out 효과, t.bg 색으로 대비).
      // 흐름 두께 ≥22px 이고 너비 ≥80px 일 때만 — 좁은 흐름엔 안 박음.
      const sHeight = Math.min(l._sy1 - l._sy0, l._ty1 - l._ty0);
      const flowW = x2 - x1;
      if (sHeight >= 22 && flowW >= 80) {
        const midY = (l._sy0 + l._sy1 + l._ty0 + l._ty1) / 4;
        inFlowLabels.push({
          x: midX, y: midY,
          text: l.value_label || d3.format(',.1f')(+l.value),
          negative: isNeg,
        });
      }
    });

    // v5.3.0 — in-flow 라벨 (큰 흐름 안에). cut-out 효과: t.bg 색으로 흐름과 대비.
    // 노드보다 *아래* 그려야 노드가 라벨 위로 안 덮음 — 노드 그리기 전에.
    const flowLabelG = svg.append('g').attr('class', 'sankey-flow-labels');
    inFlowLabels.forEach(fl => {
      flowLabelG.append('text').attr('x', fl.x).attr('y', fl.y + 3)
        .attr('text-anchor', 'middle').attr('font-size', 10)
        .attr('font-family', 'Noto Serif KR').attr('font-weight', 700)
        .attr('fill', t.bg).text(fl.text);
    });

    // 노드 그리기 — node.color (palette 또는 composer 지정). accent 는 opacity 1.0.
    const nodeG = svg.append('g').attr('class', 'sankey-nodes');

    // v6.0.4 — 첫·마지막 컬럼의 긴 라벨을 2줄로 줄바꿈 (CHART-AP-21).
    // 배경: 끝-컬럼 라벨이 길면("Colossus 2 (블랙웰 GPU 55.5만 발주)" ~28자) 가로
    // overhang 이 커져, 코어를 중앙에 둬도 반대쪽(짧은 라벨 측)에 빈 여백이 남아
    // 여전히 "치우침" 으로 보인다. 라벨을 " (" 또는 공백에서 2줄로 접으면 overhang
    // 이 ~40% 줄고 좌·우가 대칭에 가까워져 흐름이 빈 공간 없이 중앙에 온다.
    function wrapEndLabel(s, maxChars) {
      s = String(s == null ? '' : s);
      if (s.length <= maxChars) return [s];
      const p = s.indexOf(' (');               // "이름 (부연)" → 괄호 앞에서 접기
      if (p > 0 && p <= maxChars + 6) return [s.slice(0, p), s.slice(p + 1)];
      const c = s.lastIndexOf(' ', maxChars);   // 아니면 maxChars 직전 공백
      if (c > 0) return [s.slice(0, c), s.slice(c + 1)];
      return [s];                               // 접을 곳 없으면 그대로(드묾)
    }
    // 끝-컬럼 라벨(+값) 을 노드에 세로 중앙 정렬해 다줄 렌더.
    function drawEndLabel(ax, anchor, node, lblText, valText, weight) {
      const lines = wrapEndLabel(lblText, 14);
      const lineH = 13;
      const nLines = lines.length + (valText ? 1 : 0);
      const cy = node.y0 + node.height / 2;
      const yTop = cy - ((nLines - 1) * lineH) / 2;
      lines.forEach((ln, i) => {
        nodeG.append('text').attr('x', ax).attr('y', yTop + i * lineH + 4)
          .attr('text-anchor', anchor).attr('font-size', 11)
          .attr('font-family', 'Noto Sans KR').attr('fill', t.text)
          .attr('font-weight', weight).text(ln);
      });
      if (valText) {
        nodeG.append('text').attr('x', ax).attr('y', yTop + lines.length * lineH + 4)
          .attr('text-anchor', anchor).attr('font-size', 10)
          .attr('fill', t.muted).text(valText);
      }
    }

    nodes.forEach(n => {
      nodeG.append('rect')
        .attr('x', n.x0).attr('y', n.y0)
        .attr('width', n.x1 - n.x0).attr('height', n.height)
        .attr('fill', n.color)
        .attr('fill-opacity', n.accent ? ACCENT_OPACITY : NODE_OPACITY);
      // 라벨 — 첫 컬럼은 노드 왼쪽 / 마지막 컬럼은 노드 오른쪽 / 그 외는 위쪽.
      // accent 노드는 weight 700, 일반은 500 (이전 600 → 정류장 격하).
      const labelText = String(n.label || n.id);
      // CHART-AP-32 — 라벨에 같은 수치가 이미 박혀 있으면 자동 값 라벨 생략.
      // composer 가 'DS 81.7' 식으로 emit 하면 아래 자동 합계와 중복 표기
      // ('하만 3.8' + '3.8') 되던 회귀의 결정적 가드. value_label 명시는 존중.
      const autoVal = n.outValue > 0 ? d3.format(',.1f')(n.outValue)
        : (n.inValue > 0 ? d3.format(',.1f')(n.inValue) : '');
      const plainLabel = labelText.replace(/,/g, '');
      const dupInLabel = autoVal && (
        plainLabel.includes(autoVal.replace(/,/g, '')) ||
        plainLabel.includes(String(+autoVal.replace(/,/g, ''))));
      const valueText = n.value_label || (dupInLabel ? '' : autoVal);
      const isFirst = n.col === 0;
      const isLast = n.col === maxCol;
      const labelWeight = n.accent ? 700 : 500;
      if (isFirst) {
        drawEndLabel(n.x0 - 6, 'end', n, labelText, valueText, labelWeight);
      } else if (isLast) {
        drawEndLabel(n.x1 + 6, 'start', n, labelText, valueText, labelWeight);
      } else {
        // 중간 컬럼 — 라벨은 노드 위쪽
        nodeG.append('text').attr('x', n.x0 + (n.x1 - n.x0) / 2).attr('y', n.y0 - 6)
          .attr('text-anchor', 'middle').attr('font-size', 11)
          .attr('font-family', 'Noto Sans KR').attr('fill', t.text)
          .attr('font-weight', labelWeight).text(labelText);
        if (valueText) {
          nodeG.append('text').attr('x', n.x0 + (n.x1 - n.x0) / 2).attr('y', n.y1 + 14)
            .attr('text-anchor', 'middle').attr('font-size', 10)
            .attr('fill', t.muted).text(valueText);
        }
      }
    });

    // v6.0.3 — 수평 정렬: *흐름 코어(노드 컬럼)* 를 카드 중앙에 맞춘다 (CHART-AP-21).
    // 배경/경위:
    //  - 첫 컬럼 라벨(text-anchor:end, x0-6)은 왼쪽, 마지막 컬럼 라벨(x1+6)은 오른쪽
    //    으로 뻗어 고정 margin(v5.4.7 left80/right120)을 넘으면 잘린다.
    //  - v6.0.1 expand-only → 우측 빈 여백(좌측 쏠림). v6.0.2 bbox tight-fit →
    //    라벨 포함 bbox 를 중앙에 두나, 좌·우 라벨 폭이 비대칭이면(여기선 좌측
    //    "Colossus 2 (블랙웰 GPU 55.5만 발주)" ≫ 우측) *흐름 코어가 오른쪽으로 쏠림*.
    // 픽스(핵심): 라벨 포함 bbox 가 아니라 **노드 코어**(첫 컬럼 x0 ~ 마지막 컬럼 x1)
    // 를 중앙에 둔다. 좌·우 여백 m 을 *양쪽 라벨 overhang 중 큰 값* 으로 동일하게
    // 잡으면 ① 코어 중심이 viewBox 중심과 일치(코어 중앙정렬) ② m ≥ 각 overhang
    // 이라 어느 라벨도 안 잘림. 짧은 라벨 쪽엔 여분 여백이 생기지만 코어는 정중앙.
    // preserveAspectRatio=xMidYMid 가 viewBox 중심을 카드 중심에 매핑. 수직 보존.
    try {
      const cur = (svg.attr('viewBox') || `0 0 ${W} ${H}`).split(/\s+/).map(Number);
      const vy = cur[1], vh = cur[3];
      const bb = svg.node().getBBox();              // 라벨 포함 실제 extent
      const coreLeft = d3.min(nodes, n => n.x0);    // 첫 컬럼 노드 좌변
      const coreRight = d3.max(nodes, n => n.x1);   // 마지막 컬럼 노드 우변
      const padX = 14;
      const overhangL = Math.max(0, coreLeft - bb.x);
      const overhangR = Math.max(0, (bb.x + bb.width) - coreRight);
      const m = Math.max(overhangL, overhangR) + padX;
      const vx = coreLeft - m;
      const vw = (coreRight - coreLeft) + 2 * m;
      if (vw > 0) {
        svg.attr('viewBox', `${vx.toFixed(1)} ${vy} ${vw.toFixed(1)} ${vh}`);
      }
    } catch (e) { /* getBBox 불가(레이아웃 전) — 기존 viewBox 유지 */ }
  }

  // ----- RANGE BAR (Dumbbell) -----
  function drawRangeBar(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.low) && isFinite(+d.high) && +d.low < +d.high);
    if (data.length < 3 || data.length > 15) return;
    const W = 720, rowH = 26;
    // v7.0.0 — vline annotation 동반 시 top 마진 확장 (콜아웃 잘림 방지).
    const annTop = (payload.annotations || []).some(a => a.kind === 'vline') ? 60 : 24;
    const H = annTop + 36 + data.length * rowH + 30;
    const zones = computeZones(W, H, { left: 140, right: 60, top: annTop, bottom: 30 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const lo = d3.min(data, d => +d.low), hi = d3.max(data, d => +d.high);
    const pad = (hi - lo) * 0.05 || 1;
    const xScale = d3.scaleLinear().domain([lo - pad, hi + pad])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    xScale.ticks(6).forEach(xt => {
      svg.append('line').attr('x1', xScale(xt)).attr('x2', xScale(xt))
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
    data.forEach((d, i) => {
      const y = zones.data.y + 14 + i * rowH;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11).attr('fill', t.text)
        .text(String(d.label || '').slice(0, 18));
      svg.append('line').attr('x1', xScale(+d.low)).attr('x2', xScale(+d.high))
        .attr('y1', y).attr('y2', y).attr('stroke', t.muted).attr('stroke-width', 1.4);
      svg.append('circle').attr('cx', xScale(+d.low)).attr('cy', y).attr('r', 5).attr('fill', t.text);
      svg.append('circle').attr('cx', xScale(+d.high)).attr('cy', y).attr('r', 5).attr('fill', t.accent);
    });
    svg.append('g').attr('transform', `translate(0,${zones.data.y + zones.data.h + 4})`)
      .call(d3.axisBottom(xScale).ticks(6))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 9);
    // legend
    const lg = svg.append('g').attr('transform', `translate(${W - 120},${10})`);
    lg.append('circle').attr('cx', 0).attr('cy', 4).attr('r', 4).attr('fill', t.text);
    lg.append('text').attr('x', 8).attr('y', 8).attr('font-size', 10).attr('fill', t.text).text(payload.low_label || 'low');
    lg.append('circle').attr('cx', 60).attr('cy', 4).attr('r', 4).attr('fill', t.accent);
    lg.append('text').attr('x', 68).attr('y', 8).attr('font-size', 10).attr('fill', t.accent).text(payload.high_label || 'high');
    // v7.0.0 — annotation 개방 (값 축 기준).
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }


  // ----- BUMP (시기별 순위 변화, v7.0.0) -----
  // data: {periods: ["2023","2024","2025"], items: [{name, ranks: [2,1,1], accent?}]}
  // slope 는 2 시점뿐, line 은 값 축 — '순위' 축의 다시점 경쟁은 본 type 이 SSOT.
  function drawBump(stage, payload, t) {
    const d0 = payload.data || {};
    const periods = (d0.periods || []).map(String);
    const items = (d0.items || []).filter(it => Array.isArray(it.ranks)
      && it.ranks.length === periods.length
      && it.ranks.every(r => isFinite(+r) && +r >= 1));
    if (periods.length < 2 || periods.length > 6) return;
    if (items.length < 3 || items.length > 8) return;
    const n = items.length;
    const W = 720, rowH = 34;
    const H = 56 + n * rowH + 30;
    const zones = computeZones(W, H, { left: 170, right: 170, top: 34, bottom: 24 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const x = d3.scalePoint().domain(periods)
      .range([zones.data.x, zones.data.x + zones.data.w]).padding(0.06);
    const maxRank = Math.max(n, d3.max(items, it => d3.max(it.ranks.map(Number))));
    const y = (rank) => zones.data.y + 10
      + ((+rank - 1) / Math.max(1, maxRank - 1)) * (zones.data.h - 20);
    // 시기 헤더 + 옅은 세로 가이드
    periods.forEach(pv => {
      svg.append('text').attr('x', x(pv)).attr('y', zones.data.y - 12).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11).attr('font-weight', 700)
        .attr('fill', t.muted).text(pv);
      svg.append('line').attr('x1', x(pv)).attr('x2', x(pv))
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
    // 강조: accent 플래그 항목, 없으면 최종 1위 항목.
    const accentIdx = (() => {
      const fl = items.findIndex(it => it.accent);
      if (fl >= 0) return fl;
      return items.findIndex(it => +it.ranks[it.ranks.length - 1] === 1);
    })();
    const lineGen = (ranks) => d3.line()
      .x((_, k) => x(periods[k])).y(r => y(r)).curve(d3.curveMonotoneX)(ranks.map(Number));
    items.forEach((it, i) => {
      const isAccent = i === accentIdx;
      const col = isAccent ? t.accent : t.muted;
      svg.append('path').attr('d', lineGen(it.ranks)).attr('fill', 'none')
        .attr('stroke', col).attr('stroke-width', isAccent ? 2.2 : 1.3)
        .attr('stroke-opacity', isAccent ? 1 : 0.8);
      it.ranks.forEach((r, k) => {
        svg.append('circle').attr('cx', x(periods[k])).attr('cy', y(r))
          .attr('r', isAccent ? 5 : 3.8)
          .attr('fill', isAccent ? t.accent : t.text)
          .attr('stroke', t.bg).attr('stroke-width', 1);
      });
    });
    // 좌·우 끝 라벨 (이름 + 순위) — 동순위 충돌은 dodgeYs 로 (CHART-AP-26 일반화).
    const lo = zones.data.y - 2, hi = zones.data.y + zones.data.h + 10;
    const lY = dodgeYs(items.map(it => y(it.ranks[0])), 14, lo, hi);
    const rY = dodgeYs(items.map(it => y(it.ranks[it.ranks.length - 1])), 14, lo, hi);
    items.forEach((it, i) => {
      const isAccent = i === accentIdx;
      const col = isAccent ? t.accent : t.text;
      svg.append('text').attr('x', zones.data.x - 12).attr('y', lY[i] + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .attr('font-weight', isAccent ? 700 : 400).attr('fill', col)
        .text(`${String(it.name || '').slice(0, 14)} ${Math.round(+it.ranks[0])}위`);
      svg.append('text').attr('x', zones.data.x + zones.data.w + 12).attr('y', rY[i] + 4)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .attr('font-weight', isAccent ? 700 : 400).attr('fill', col)
        .text(`${Math.round(+it.ranks[it.ranks.length - 1])}위 ${String(it.name || '').slice(0, 14)}`);
    });
  }

  // ----- BULLET (목표 대비 실적, v7.0.0) -----
  // data: [{label, value, target, ranges?: [경계 오름차순 ≤4]}] 1~7행.
  // bar 는 단일 값 — 실적 vs 가이던스/컨센서스의 목표 중첩은 본 type 이 SSOT.
  function drawBullet(stage, payload, t) {
    const data = (payload.data || []).filter(d =>
      isFinite(+d.value) && isFinite(+d.target) && +d.target > 0);
    if (!data.length || data.length > 7) return;
    const W = 720, rowH = 44;
    const annTop = (payload.annotations || []).some(a => a.kind === 'vline') ? 60 : 28;
    const H = annTop + data.length * rowH + 34;
    const zones = computeZones(W, H, { left: 150, right: 96, top: annTop, bottom: 30 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const maxVal = d3.max(data, d => Math.max(
      Math.abs(+d.value), Math.abs(+d.target),
      ...((d.ranges || []).map(Number).filter(isFinite).map(Math.abs)),
    )) || 1;
    const xScale = d3.scaleLinear().domain([0, maxVal * 1.06])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(+v);
      if (av >= 10) return d3.format(',.1f')(+v);
      return d3.format(',.2f')(+v);
    };
    data.forEach((d, i) => {
      const yRow = zones.data.y + 8 + i * rowH;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', yRow + 13).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11).attr('fill', t.text)
        .text(String(d.label || '').slice(0, 18));
      // 배경 구간 밴드 (낮음→높음, 옅은 단계).
      const bounds = (d.ranges || []).map(Number).filter(v => isFinite(v) && v > 0)
        .sort((a, b) => a - b).slice(0, 4);
      let xPrev = zones.data.x;
      bounds.forEach((b, k) => {
        const xB = xScale(Math.min(b, maxVal * 1.06));
        if (xB > xPrev) {
          svg.append('rect').attr('x', xPrev).attr('y', yRow).attr('width', xB - xPrev)
            .attr('height', 18).attr('fill', t.text)
            .attr('fill-opacity', 0.05 + k * 0.045).attr('data-static', '1');
        }
        xPrev = xB;
      });
      // 실적 바 (accent, 중앙 절반 높이) — entry 애니메이션 호환 (bar-grow).
      const barW = Math.max(2, xScale(+d.value) - zones.data.x);
      svg.append('rect').attr('x', zones.data.x).attr('y', yRow + 5)
        .attr('width', barW).attr('height', 8).attr('fill', t.accent)
        .attr('data-anim', 'bar-grow').attr('data-final-w', barW);
      // 목표 tick (text 색 세로 마커 — 큰 숫자 accent 금지 정신과 별개의 기준선).
      const xT = xScale(+d.target);
      svg.append('line').attr('x1', xT).attr('x2', xT)
        .attr('y1', yRow - 3).attr('y2', yRow + 21)
        .attr('stroke', t.text).attr('stroke-width', 2).attr('data-static', '1');
      // 우측 값 라벨: 실적 (목표 대비 %).
      const pct = (+d.value / +d.target) * 100;
      svg.append('text').attr('x', zones.data.x + zones.data.w + 8).attr('y', yRow + 13)
        .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700)
        .attr('fill', t.text)
        .text(`${fmt(+d.value)} (${d3.format('.0f')(pct)}%)`);
    });
    // X 축
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', zones.data.y + zones.data.h + 4).attr('y2', zones.data.y + zones.data.h + 4)
      .attr('stroke', t.muted).attr('stroke-opacity', 0.4).attr('stroke-width', 0.5);
    xScale.ticks(5).forEach(v => {
      svg.append('text').attr('x', xScale(v)).attr('y', zones.data.y + zones.data.h + 18)
        .attr('text-anchor', 'middle').attr('font-family', 'Noto Sans KR')
        .attr('font-size', 9).attr('fill', t.muted).text(fmt(v));
    });
    // 미니 범례 (우상단): 실적 바 + 목표 tick.
    const lg = svg.append('g').attr('transform', `translate(${W - 150},${annTop - 18})`);
    lg.append('rect').attr('x', 0).attr('y', 2).attr('width', 16).attr('height', 6)
      .attr('fill', t.accent).attr('data-static', '1');
    lg.append('text').attr('x', 20).attr('y', 9).attr('font-size', 9.5).attr('fill', t.muted).text('실적');
    lg.append('line').attr('x1', 62).attr('x2', 62).attr('y1', 0).attr('y2', 10)
      .attr('stroke', t.text).attr('stroke-width', 2).attr('data-static', '1');
    lg.append('text').attr('x', 68).attr('y', 9).attr('font-size', 9.5).attr('fill', t.muted).text('목표');
    // annotation 개방 (값 축 기준).
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }

  // ----- CONNECTED SCATTER (2변수 시간 경로, v7.0.0) -----
  // data: [{x, y, label?}] *시간 순서* 4~30점. dual_line 은 두 축 분리 — 두 변수가
  // 함께 그리는 '궤적' 서사 (금리×환율, 물가×실업 등) 는 본 type 이 SSOT.
  function drawConnectedScatter(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.x) && isFinite(+d.y));
    if (data.length < 4 || data.length > 30) return;
    const W = 720, H = 380;
    const zones = computeZones(W, H, { left: 64, right: 44, top: 30, bottom: 44 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const xExt = d3.extent(data, d => +d.x), yExt = d3.extent(data, d => +d.y);
    const xPad = (xExt[1] - xExt[0]) * 0.1 || 1;
    const yPad = (yExt[1] - yExt[0]) * 0.1 || 1;
    const xScale = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    const yScale = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);
    // grid + axes (scatter 와 동일 문법)
    yScale.ticks(5).forEach(yt => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yScale(yt)).attr('y2', yScale(yt))
        .attr('stroke', t.border).attr('stroke-opacity', 0.4).attr('stroke-dasharray', '2 3');
    });
    svg.append('g').attr('transform', `translate(0,${zones.data.y + zones.data.h})`)
      .call(d3.axisBottom(xScale).ticks(6))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    svg.append('g').attr('transform', `translate(${zones.data.x},0)`)
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
    if (payload.x_label) {
      svg.append('text').attr('x', W / 2).attr('y', H - 8).attr('text-anchor', 'middle')
        .attr('font-size', 11).attr('fill', t.muted).text(payload.x_label);
    }
    if (payload.y_label) {
      svg.append('text').attr('transform', 'rotate(-90)').attr('x', -H / 2).attr('y', 14)
        .attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', t.muted).text(payload.y_label);
    }
    // annotation 개방 (vline 은 top 30 잘림 → point 로 대체 유도).
    renderAnnotations(svg,
      { annotations: (payload.annotations || []).filter(a => a.kind !== 'vline') },
      zones, t, xScale, yScale);
    // 경로 (시간 순서, muted 가는 선 — 점이 주연, 선은 동선).
    // CHART-AP-30 — CatmullRom 은 점 사이가 부풀어 실제 좌표 경로를 왜곡. 직선 연결.
    const lineGen = d3.line().x(d => xScale(+d.x)).y(d => yScale(+d.y))
      .curve(d3.curveLinear);
    svg.append('path').attr('d', lineGen(data)).attr('fill', 'none')
      .attr('stroke', t.muted).attr('stroke-width', 1.2).attr('stroke-opacity', 0.85);
    // 진행 방향 화살촉 (마지막 구간 각도).
    const pn = data[data.length - 1], pp = data[data.length - 2];
    const angle = Math.atan2(
      yScale(+pn.y) - yScale(+pp.y), xScale(+pn.x) - xScale(+pp.x),
    ) * 180 / Math.PI;
    svg.append('path').attr('d', 'M 0 -4 L 8 0 L 0 4 Z')
      .attr('fill', t.accent)
      .attr('transform',
        `translate(${xScale(+pn.x)},${yScale(+pn.y)}) rotate(${angle}) translate(10,0)`);
    // 점: 시작 hollow / 중간 작은 점 / 끝 accent 강조.
    const occ = makeOccupancy();
    data.forEach((d, i) => {
      const cx = xScale(+d.x), cy = yScale(+d.y);
      const first = i === 0, last = i === data.length - 1;
      svg.append('circle').attr('cx', cx).attr('cy', cy)
        .attr('r', first ? 4.5 : (last ? 6 : 2.6))
        .attr('fill', first ? t.bg : (last ? t.accent : t.text))
        .attr('fill-opacity', first || last ? 1 : 0.8)
        .attr('stroke', first ? t.text : (last ? t.text : 'none'))
        .attr('stroke-width', first ? 1.4 : (last ? 0.8 : 0));
      // 라벨: label 있는 점 + 시작·끝 (renderPoint 와 동일 4-후보 충돌 회피).
      const text = d.label || (first ? '시작' : (last ? '최근' : ''));
      if (!text) return;
      const labelW = String(text).length * 7 + 4, labelH = 14;
      const candidates = [
        { x: cx + 9, y: cy - 9 }, { x: cx - labelW - 9, y: cy - 9 },
        { x: cx + 9, y: cy + 13 }, { x: cx - labelW - 9, y: cy + 13 },
      ];
      let placed = candidates[0];
      for (const c of candidates) {
        if (c.x >= zones.data.x - 30 && c.x + labelW <= zones.W - 2
            && c.y >= zones.data.y - 4 && c.y + labelH <= zones.data.y + zones.data.h + 12
            && !occ.hits(c.x, c.y, labelW, labelH)) { placed = c; break; }
      }
      svg.append('text').attr('x', placed.x).attr('y', placed.y + 10)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('font-weight', first || last ? 700 : 400)
        .attr('fill', last ? t.accent : t.text).text(text);
      occ.add(placed.x, placed.y, labelW, labelH);
    });
  }

  // ----- COMBO — 이중 축 막대+선 (v7.5.0) -----
  // dual_line 의 자매 type: 한쪽 metric 이 부피·건수 성격 (거래량/체결 건수/
  // 재고) 일 때 그 축을 막대로. 막대 = 좌축 저농도 잉크 (보조), 선 = 우축
  // 액센트 (주연) — dual_line 의 좌 잉크/우 액센트 색 계약과 동일.
  // annotations (x 축 기준) 지원. CHART-AP-30: curveLinear.
  function drawCombo(stage, payload, t) {
    const bars = payload.data && payload.data.bars;
    const line = payload.data && payload.data.line;
    if (!bars || !line || !(bars.series || []).length || !(line.series || []).length) return;
    const W = 760, H = 340;
    const zones = computeZones(W, H, { left: 60, right: 60, top: 56, bottom: 40 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    // x 격자 — 막대가 밴드의 주인, 선은 밴드 중앙을 지난다.
    const xVals = Array.from(new Set([...bars.series, ...line.series].map(d => String(d.x))));
    const xBand = d3.scaleBand().domain(xVals)
      .range([zones.data.x, zones.data.x + zones.data.w])
      .paddingInner(0.25).paddingOuter(0.08);
    const xc = (xv) => {
      const bx = xBand(String(xv));
      return bx == null ? null : bx + xBand.bandwidth() / 2;
    };
    const yB = d3.scaleLinear()
      .domain([0, (d3.max(bars.series, d => +d.y) || 1) * 1.08])
      .range([zones.data.y + zones.data.h, zones.data.y]);
    const yL = d3.scaleLinear().domain(d3.extent(line.series, d => +d.y))
      .nice().range([zones.data.y + zones.data.h, zones.data.y]);

    // 좌축 (막대) 눈금 + 헤더 — 부피는 자릿수가 커서 SI 축약 표기
    yB.ticks(4).forEach(v => {
      svg.append('text').attr('x', zones.data.x - 6).attr('y', yB(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('~s')(v));
    });
    svg.append('text').attr('x', zones.data.x).attr('y', zones.data.y - 6)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.text)
      .attr('font-weight', 600)
      .text(`${bars.label || ''} (${bars.unit || ''})`);
    // 우축 (선) 눈금 + 헤더
    yL.ticks(4).forEach(v => {
      svg.append('text').attr('x', zones.data.x + zones.data.w + 6).attr('y', yL(v) + 3)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format('.0f')(v));
    });
    svg.append('text').attr('x', zones.data.x + zones.data.w).attr('y', zones.data.y - 6).attr('text-anchor', 'end')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.accent)
      .attr('font-weight', 600)
      .text(`${line.label || ''} (${line.unit || ''})`);

    const occupancy = renderAnnotations(svg, payload, zones, t, (xv) => xc(xv), null);

    // 막대 — 저농도 잉크 (선이 주연)
    bars.series.forEach(d => {
      const bx = xBand(String(d.x));
      if (bx == null || !isFinite(+d.y)) return;
      const y = yB(Math.max(0, +d.y));
      svg.append('rect').attr('x', bx).attr('y', y)
        .attr('width', xBand.bandwidth())
        .attr('height', Math.max(0, zones.data.y + zones.data.h - y))
        .attr('fill', t.text).attr('fill-opacity', 0.30);
    });
    // 0-기준선 crisp
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', yB(0)).attr('y2', yB(0))
      .attr('stroke', t.text).attr('stroke-opacity', 0.45).attr('stroke-width', 1);

    // 선 — 액센트 실선 (CHART-AP-30: 실제 데이터 경로, 곡선 보간 금지)
    const lp = d3.line().x(d => xc(d.x)).y(d => yL(+d.y)).curve(d3.curveLinear);
    svg.append('path').attr('d', lp(line.series)).attr('fill', 'none')
      .attr('stroke', t.accent).attr('stroke-width', 1.8);

    // 끝점 마커 + 라벨 (우축 헤더가 이미 시리즈명을 운반 — 값만)
    const lastL = line.series[line.series.length - 1];
    svg.append('circle').attr('cx', xc(lastL.x)).attr('cy', yL(+lastL.y))
      .attr('r', 3.2).attr('fill', t.accent);
    placeEndLabel(svg, xc(lastL.x), yL(+lastL.y), String(lastL.y),
      t, occupancy, zones, t.accent);

    // x 라벨 (sparse)
    const step = Math.max(1, Math.ceil(xVals.length / 7));
    xVals.forEach((xv, i) => {
      if (i % step !== 0 && i !== xVals.length - 1) return;
      svg.append('text').attr('x', xc(xv)).attr('y', H - zones.bottom + 16).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(String(xv).slice(0, 10));
    });
  }

  // ----- DIVERGING BAR — 대립 쌍 발산 막대 (v7.5.0, 사회 이슈·여론) -----
  // 0 공유 기준선에서 좌 (neg) ·우 (pos) 발산. 색 계약은 waterfall 과 동일:
  // pos = 액센트, neg = 하락색. 값은 세리프 직접 라벨 (v7.1.0 문법).
  function drawDivergingBar(stage, payload, t) {
    const rows = (payload.data || []).filter(d =>
      isFinite(+d.neg) && isFinite(+d.pos) && (+d.neg > 0 || +d.pos > 0));
    if (rows.length < 2) return;
    const W = 720, rowH = 32, top = 38, bottom = 22, labelW = 132;
    const H = top + rows.length * rowH + bottom;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const x0 = labelW + 14, x1 = W - 56;
    const cx = x0 + (x1 - x0) / 2;
    const half = (x1 - x0) / 2 - 44;  // 값 라벨 여유
    const max = d3.max(rows, d => Math.max(+d.neg, +d.pos)) || 1;
    const scale = (v) => (Math.abs(+v) / max) * half;
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(av);
      if (av >= 10) return d3.format(',.1f')(av);
      return d3.format(',.2f')(av);
    };
    const trunc = (sv, n) => {
      const str = String(sv || '');
      return str.length > n ? str.slice(0, n - 1) + '…' : str;
    };
    // 헤더 — 좌·우 방향 의미 (neg_label / pos_label)
    svg.append('text').attr('x', cx - 10).attr('y', top - 16).attr('text-anchor', 'end')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('font-weight', 700)
      .attr('fill', t.down).text('◀ ' + (payload.neg_label || '반대'));
    svg.append('text').attr('x', cx + 10).attr('y', top - 16)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('font-weight', 700)
      .attr('fill', t.accent).text((payload.pos_label || '찬성') + ' ▶');
    rows.forEach((d, i) => {
      const y = top + i * rowH + 4;
      const h = rowH - 11;
      // 행 라벨 (좌측 고정 컬럼)
      svg.append('text').attr('x', labelW).attr('y', y + h / 2 + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11.5).attr('fill', t.text)
        .text(trunc(d.label, 11));
      // neg (좌향)
      const nw = scale(d.neg);
      if (nw > 0) {
        svg.append('rect').attr('x', cx - nw).attr('y', y).attr('width', nw).attr('height', h)
          .attr('rx', 1.5).attr('fill', t.down).attr('fill-opacity', 0.85);
        svg.append('text').attr('x', cx - nw - 5).attr('y', y + h / 2 + 4).attr('text-anchor', 'end')
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11.5).attr('font-weight', 700)
          .attr('fill', t.down).text(fmt(d.neg));
      }
      // pos (우향)
      const pw = scale(d.pos);
      if (pw > 0) {
        svg.append('rect').attr('x', cx).attr('y', y).attr('width', pw).attr('height', h)
          .attr('rx', 1.5).attr('fill', t.accent).attr('fill-opacity', 0.9);
        svg.append('text').attr('x', cx + pw + 5).attr('y', y + h / 2 + 4)
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11.5).attr('font-weight', 700)
          .attr('fill', t.accent).text(fmt(d.pos));
      }
    });
    // 0 공유 기준선 crisp (막대 위)
    svg.append('line').attr('x1', cx).attr('x2', cx)
      .attr('y1', top - 6).attr('y2', top + rows.length * rowH - 4)
      .attr('stroke', t.text).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
  }

  // ----- PYRAMID — 인구 피라미드 (v7.5.0, 인구·연령 구조) -----
  // 입력 순서 = 젊은층부터 → 렌더는 아래→위 적층 (인구 피라미드 표준 문법).
  // left = 잉크, right = 액센트. bracket 라벨은 중앙 공유 축.
  function drawPyramid(stage, payload, t) {
    const rows = (payload.data || []).filter(d => isFinite(+d.left) && isFinite(+d.right));
    if (rows.length < 4) return;
    const W = 720, rowH = 22, top = 40, bottom = 30, centerW = 78;
    const H = top + rows.length * rowH + bottom;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const cx = W / 2;
    const half = (W - centerW) / 2 - 58;  // 좌우 각 측 최대 막대 폭 (값 라벨 여유)
    const max = d3.max(rows, d => Math.max(+d.left, +d.right)) || 1;
    const scale = (v) => (Math.abs(+v) / max) * half;
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(av);
      if (av >= 10) return d3.format(',.1f')(av);
      return d3.format(',.2f')(av);
    };
    // 헤더
    svg.append('text').attr('x', cx - centerW / 2 - 6).attr('y', top - 16).attr('text-anchor', 'end')
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('font-weight', 700)
      .attr('fill', t.text).text(payload.left_label || '남');
    svg.append('text').attr('x', cx + centerW / 2 + 6).attr('y', top - 16)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('font-weight', 700)
      .attr('fill', t.accent).text(payload.right_label || '여');
    const maxL = d3.max(rows, d => +d.left), maxR = d3.max(rows, d => +d.right);
    rows.forEach((d, i) => {
      const y = top + (rows.length - 1 - i) * rowH;  // 첫 행이 최하단
      const h = rowH - 6;
      // bracket — 중앙 공유 축
      svg.append('text').attr('x', cx).attr('y', y + h / 2 + 3.5).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9.5).attr('fill', t.muted)
        .text(String(d.bracket).slice(0, 7));
      const lw = scale(d.left), rw = scale(d.right);
      svg.append('rect').attr('x', cx - centerW / 2 - lw).attr('y', y)
        .attr('width', Math.max(0.5, lw)).attr('height', h).attr('rx', 1.5)
        .attr('fill', t.text).attr('fill-opacity', 0.55);
      svg.append('rect').attr('x', cx + centerW / 2).attr('y', y)
        .attr('width', Math.max(0.5, rw)).attr('height', h).attr('rx', 1.5)
        .attr('fill', t.accent).attr('fill-opacity', 0.9);
      // 값 라벨 — 각 측 최대 행만 세리프 직접 라벨 (전 행 라벨은 소음)
      if (+d.left === maxL) {
        svg.append('text').attr('x', cx - centerW / 2 - lw - 5).attr('y', y + h / 2 + 4)
          .attr('text-anchor', 'end').attr('font-family', 'Noto Serif KR')
          .attr('font-size', 11).attr('font-weight', 700).attr('fill', t.text)
          .text(fmt(d.left));
      }
      if (+d.right === maxR) {
        svg.append('text').attr('x', cx + centerW / 2 + rw + 5).attr('y', y + h / 2 + 4)
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11)
          .attr('font-weight', 700).attr('fill', t.accent)
          .text(fmt(d.right));
      }
    });
    // 하단 축 눈금 (0 / max, 양측)
    const yAxis = top + rows.length * rowH + 12;
    [[cx - centerW / 2, cx - centerW / 2 - half], [cx + centerW / 2, cx + centerW / 2 + half]]
      .forEach(([zx, mx]) => {
        svg.append('text').attr('x', zx).attr('y', yAxis).attr('text-anchor', 'middle')
          .attr('font-family', 'IBM Plex Mono, monospace').attr('font-size', 8.5)
          .attr('fill', t.muted).text('0');
        svg.append('text').attr('x', mx).attr('y', yAxis).attr('text-anchor', 'middle')
          .attr('font-family', 'IBM Plex Mono, monospace').attr('font-size', 8.5)
          .attr('fill', t.muted).text(fmt(max));
      });
  }

  // ----- DOT MATRIX — 100칸 와플 / 아이소타입 (v7.5.0, 사회 통계 체감) -----
  // '100명 중 N명' — largest-remainder 로 정확히 100칸 배분. 칸 잉크: accent
  // segment = 액센트 솔리드, 나머지는 잉크 농도 사다리 (칸이 작아 해치는
  // 모아레 — 소면적에서 농도 사다리 사용은 mono guide §10 위계 문법).
  function drawDotMatrix(stage, payload, t) {
    const segs = (payload.data || []).filter(d => isFinite(+d.value) && +d.value > 0);
    if (segs.length < 2) return;
    const total = d3.sum(segs, d => +d.value);
    if (!(total > 0)) return;
    // largest remainder — 합이 정확히 100칸
    const quota = segs.map(d => {
      const raw = (+d.value / total) * 100;
      return { d, raw, n: Math.floor(raw), rem: raw - Math.floor(raw) };
    });
    let left = 100 - d3.sum(quota, q => q.n);
    quota.slice().sort((a, b) => b.rem - a.rem).forEach(q => {
      if (left > 0) { q.n += 1; left -= 1; }
    });
    // 잉크 배정 — accent 명시 segment 우선, 없으면 첫 segment
    const hasAccent = segs.some(d => d.accent);
    const LADDER = [0.85, 0.5, 0.3, 0.18, 0.11];
    let ladderIdx = 0;
    const fills = quota.map((q, i) => {
      const isAcc = hasAccent ? !!q.d.accent : i === 0;
      if (isAcc) return { color: t.accent, op: 0.95 };
      const op = LADDER[Math.min(ladderIdx, LADDER.length - 1)];
      ladderIdx += 1;
      return { color: t.text, op };
    });
    const cell = 23, grid = cell * 10, padT = 18, padL = 26;
    const W = 720, H = grid + padT + 26;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    // v7.9.8 — 그리드+범례를 그룹에 담아 getBBox 로 가로 중앙정렬 (sankey 와 동일
    // content-fit). 이전엔 grid 좌측 고정 + 범례 우측 고정이라 우측에 빈 여백이
    // 남아 차트가 왼쪽으로 쏠려 보였다 (사용자 catch).
    const g = svg.append('g');
    let k = 0;
    quota.forEach((q, si) => {
      for (let j = 0; j < q.n; j += 1, k += 1) {
        const row = Math.floor(k / 10), col = k % 10;
        g.append('circle')
          .attr('cx', padL + col * cell + cell / 2)
          .attr('cy', padT + row * cell + cell / 2)
          .attr('r', 7.4)
          .attr('fill', fills[si].color).attr('fill-opacity', fills[si].op);
      }
    });
    // 범례 — 우측: 점 견본 + 라벨 + 세리프 n/100
    const lx = padL + grid + 46;
    quota.forEach((q, i) => {
      const y = padT + 16 + i * 40;
      g.append('circle').attr('cx', lx).attr('cy', y - 4).attr('r', 6.5)
        .attr('fill', fills[i].color).attr('fill-opacity', fills[i].op);
      g.append('text').attr('x', lx + 15).attr('y', y)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11.5).attr('fill', t.text)
        .text(String(q.d.label).slice(0, 18));
      g.append('text').attr('x', lx + 15).attr('y', y + 17)
        .attr('font-family', 'Noto Serif KR').attr('font-size', 13.5)
        .attr('font-weight', 700).attr('fill', fills[i].color)
        .attr('fill-opacity', Math.max(0.65, fills[i].op))
        .text(`${q.n} / 100`);
    });
    // 가로 중앙정렬 — 렌더 후 실제 content extent 측정해 W 중앙으로 시프트.
    try {
      const bb = g.node().getBBox();
      const dx = (W - bb.width) / 2 - bb.x;
      if (isFinite(dx)) g.attr('transform', `translate(${dx},0)`);
    } catch (e) { /* getBBox 미지원 환경 — 좌측정렬 폴백 */ }
  }

  // ============================================================
  // viewBox 가 작아져 컨테이너에 stretch 되는 회귀 (v5.2.4 P0-Patch7 의 첫
  // catch) 를 차단.
  // ============================================================
  function drawSparkline(svg, data, color) {
    const rect = svg.getBoundingClientRect();
    let W = rect.width || svg.clientWidth || (svg.parentElement ? svg.parentElement.clientWidth : 0);
    let H = rect.height || svg.clientHeight || 22;
    if (!W || W < 20) W = 100;
    if (!H || H < 8)  H = 22;
    svg.innerHTML = '';
    svg.removeAttribute('preserveAspectRatio');
    const sel = d3.select(svg).attr('viewBox', `0 0 ${W} ${H}`);
    if (!data || data.length < 2) return;
    const closes = data
      .map(d => (d.y != null ? +d.y : (d.close != null ? +d.close : NaN)))
      .filter(v => Number.isFinite(v));
    if (closes.length < 2) return;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const rng = max - min || 1;
    const pad = 2;
    const x = i => pad + (i / (closes.length - 1)) * (W - 2 * pad);
    const y = v => H - pad - ((v - min) / rng) * (H - 2 * pad);
    // v5.2.9 — baseline (첫 종가) 을 옅은 dashed 로. 가격이 시작 대비 어디
    // 까지 움직였는지 한눈에. mono 가이드 위반 없음 (액센트 색 아님).
    const baseY = y(closes[0]);
    sel.append('line')
      .attr('x1', pad).attr('x2', W - pad)
      .attr('y1', baseY).attr('y2', baseY)
      .attr('stroke', color)
      .attr('stroke-width', 0.6)
      .attr('stroke-dasharray', '2,2')
      .attr('opacity', 0.35);
    const line = d3.line()
      .x((_, i) => x(i))
      .y(d => y(d))
      .curve(d3.curveLinear);
    sel.append('path')
      .attr('d', line(closes))
      .attr('fill', 'none')
      .attr('stroke', color)
      .attr('stroke-width', 1.2)
      .attr('stroke-linejoin', 'miter')
      .attr('stroke-linecap', 'butt');
    // v5.2.9 — min/max 극값 dot. 데이터가 평평할 경우 (rng=0) skip.
    if (max > min) {
      const iMax = closes.indexOf(max);
      const iMin = closes.indexOf(min);
      sel.append('circle')
        .attr('cx', x(iMax)).attr('cy', y(max))
        .attr('r', 1.1).attr('fill', color).attr('opacity', 0.55);
      sel.append('circle')
        .attr('cx', x(iMin)).attr('cy', y(min))
        .attr('r', 1.1).attr('fill', color).attr('opacity', 0.55);
    }
    sel.append('circle')
      .attr('cx', x(closes.length - 1))
      .attr('cy', y(closes[closes.length - 1]))
      .attr('r', 1.8)
      .attr('fill', color);
  }

  function _drawAllSparklines(sparks) {
    const cs = getComputedStyle(document.documentElement);
    const cssVar = name => cs.getPropertyValue(name).trim();
    const upColor = cssVar('--up') || '#4A6B3E';
    const downColor = cssVar('--down') || '#8B2A2A';
    const mutedColor = cssVar('--muted') || '#6B5C4A';
    sparks.forEach(svg => {
      const row = svg.closest('.compact-row');
      if (!row) return;
      const script = row.querySelector('script.chart-payload-inline');
      if (!script) return;
      let payload;
      try { payload = JSON.parse(script.textContent); }
      catch (e) { console.warn('[sparkline] payload parse fail', e); return; }
      const data = payload.data || [];
      if (data.length < 2) return;
      const first = (data[0].y != null ? +data[0].y : +data[0].close);
      const last = (data[data.length - 1].y != null
        ? +data[data.length - 1].y
        : +data[data.length - 1].close);
      let color = mutedColor;
      if (Number.isFinite(first) && Number.isFinite(last)) {
        color = last >= first ? upColor : downColor;
      }
      try { drawSparkline(svg, data, color); }
      catch (e) { console.warn('[sparkline] render error', e); }
    });
  }

  function renderSparklines() {
    const sparks = document.querySelectorAll('svg.sparkline');
    if (!sparks.length) return;
    const drawAll = () => _drawAllSparklines(sparks);
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => requestAnimationFrame(drawAll));
    } else {
      setTimeout(drawAll, 0);
    }
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => drawAll());
      sparks.forEach(s => { const row = s.closest('.compact-row'); if (row) ro.observe(row); });
    }
  }

  // ============================================================
  // ----- COMBO_CANDLE (좌축 비율 line + 우축 지수 candle) -----
  // v7.9.9 — 장마감 브리핑: 하락 종목 비율(좌, %) 위에 지수(우)를 캔들로 겹쳐,
  // '지수는 올랐는데 체감(폭)은 약하다' 같은 괴리를 한 차트에서 읽게 한다.
  // data: { line: {series:[{x,y}], label}, candle: {series:[{date,open,high,low,close}], label} }
  function drawComboCandle(stage, payload, t) {
    const lineS = payload.data && payload.data.line;
    const candleS = payload.data && payload.data.candle;
    if (!lineS || !candleS || !(lineS.series || []).length || !(candleS.series || []).length) return;
    const W = 760, H = 340;
    const zones = computeZones(W, H, { left: 52, right: 66, top: 54, bottom: 40 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const xVals = Array.from(new Set([
      ...lineS.series.map(d => String(d.x)),
      ...candleS.series.map(d => String(d.date)),
    ])).sort();
    const xScale = d3.scalePoint().domain(xVals)
      .range([zones.data.x, zones.data.x + zones.data.w]).padding(0.5);
    // 좌축 — 비율(line). 0~max(100) 고정 하한 0.
    const yLmax = Math.max(100, d3.max(lineS.series, d => +d.y) || 100);
    const yL = d3.scaleLinear().domain([0, yLmax]).range([zones.data.y + zones.data.h, zones.data.y]);
    // 우축 — 지수(candle).
    const cMin = d3.min(candleS.series, d => +d.low);
    const cMax = d3.max(candleS.series, d => +d.high);
    const cPad = (cMax - cMin) * 0.08 || 1;
    const yR = d3.scaleLinear().domain([cMin - cPad, cMax + cPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);
    // grid + 좌축 라벨
    yL.ticks(5).forEach(v => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yL(v)).attr('y2', yL(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.14).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', yL(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(v);
    });
    // 50% 기준선 (하락 우위 경계) — 점선 강조
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', yL(50)).attr('y2', yL(50)).attr('stroke', t.muted)
      .attr('stroke-width', 0.8).attr('stroke-dasharray', '3 3').attr('stroke-opacity', 0.5);
    // 우축 라벨 (accent)
    yR.ticks(5).forEach(v => {
      svg.append('text').attr('x', zones.data.x + zones.data.w + 6).attr('y', yR(v) + 3)
        .attr('text-anchor', 'start').attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-size', 9).attr('fill', t.accent).attr('fill-opacity', 0.85)
        .text(v >= 1000 ? d3.format(',.0f')(v) : d3.format('.1f')(v));
    });
    // 캔들 (우축) — 배경
    const step = zones.data.w / Math.max(1, xVals.length);
    const bw = Math.max(2.5, step * 0.5);
    candleS.series.forEach(d => {
      const cx = xScale(String(d.date));
      if (cx == null || !isFinite(+d.close)) return;
      const up = +d.close >= +d.open;
      const col = up ? t.accent : (t.down || '#C45C4C');
      svg.append('line').attr('x1', cx).attr('x2', cx)
        .attr('y1', yR(+d.high)).attr('y2', yR(+d.low))
        .attr('stroke', col).attr('stroke-width', 0.9).attr('stroke-opacity', 0.8);
      const yTop = Math.min(yR(+d.open), yR(+d.close));
      const bh = Math.max(1, Math.abs(yR(+d.close) - yR(+d.open)));
      svg.append('rect').attr('x', cx - bw / 2).attr('y', yTop)
        .attr('width', bw).attr('height', bh)
        .attr('fill', up ? 'none' : col).attr('stroke', col)
        .attr('stroke-width', 1).attr('opacity', 0.8);
    });
    // 비율 line (좌축) — 전경
    const ln = d3.line().x(d => xScale(String(d.x))).y(d => yL(+d.y))
      .defined(d => xScale(String(d.x)) != null && isFinite(+d.y)).curve(d3.curveLinear);
    svg.append('path').attr('d', ln(lineS.series)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.9);
    // x 라벨 (sparse)
    const xstep = Math.max(1, Math.ceil(xVals.length / 7));
    xVals.forEach((xv, i) => {
      if (i % xstep !== 0 && i !== xVals.length - 1) return;
      const cx = xScale(xv);
      svg.append('text').attr('x', cx).attr('y', zones.data.y + zones.data.h + 16)
        .attr('text-anchor', 'middle').attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-size', 9).attr('fill', t.muted).text(String(xv).slice(5));
    });
    // 범례 (상단 2줄)
    svg.append('text').attr('x', zones.data.x).attr('y', zones.data.y - 30)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5).attr('fill', t.text)
      .text(`${lineS.label || '하락 종목 비율'} (좌, %)`);
    svg.append('text').attr('x', zones.data.x).attr('y', zones.data.y - 14)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5).attr('fill', t.accent)
      .text(`${candleS.label || '지수'} (우, 캔들)`);
  }

  // ----- IV_SKEW (변동성 스큐 곡선) -----
  // v7.9.11 — 풋(파랑)/콜(빨강) 곡선 + 행사가 라벨 + 지난 N영업일 오버레이(나이순
  // 페이드). 각 점에 date 가 있으면 일자별로 그려 오늘=진하게, 과거=옅게.
  // data: [{strike, iv, type:'put'|'call', date?}], payload.atm_iv (선택).
  function drawIvSkew(stage, payload, t) {
    var raw = (payload.data || []).filter(function (d) {
      return isFinite(+d.strike) && isFinite(+d.iv);
    });
    if (raw.length < 3) return;
    var PUT = '#4F8BF0', CALL = '#E0604A';
    var W = 720, H = 404;
    var zones = computeZones(W, H, { left: 56, right: 58, top: 46, bottom: 58 });
    var svg = d3.select(stage).select('svg')
      .attr('viewBox', '0 0 ' + W + ' ' + H).attr('preserveAspectRatio', 'xMidYMid meet');
    var dates = Array.from(new Set(raw.map(function (d) { return d.date || ''; })))
      .filter(Boolean).sort();
    var hasDates = dates.length > 1;
    var today = dates.length ? dates[dates.length - 1] : null;
    var xExt = d3.extent(raw, function (d) { return +d.strike; });
    var yvals = raw.map(function (d) { return +d.iv; });
    var atm = (payload.atm_iv != null && isFinite(+payload.atm_iv)) ? +payload.atm_iv : null;
    if (atm != null) yvals.push(atm);
    var yMin = d3.min(yvals), yMax = d3.max(yvals);
    var xPad = (xExt[1] - xExt[0]) * 0.04 || 1, yPad = (yMax - yMin) * 0.12 || 1;
    var xS = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    var yS = d3.scaleLinear().domain([yMin - yPad, yMax + yPad])
      .range([zones.data.y + zones.data.h, zones.data.y]);
    // y grid + labels
    yS.ticks(5).forEach(function (v) {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yS(v)).attr('y2', yS(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.14).attr('stroke-width', 0.5);
      svg.append('text').attr('x', zones.data.x - 6).attr('y', yS(v) + 3).attr('text-anchor', 'end')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 9).attr('fill', t.muted)
        .text(v + '%');
    });
    // ATM IV 가로 기준선 — 라벨 plot 안 좌상단 (우측 잘림 방지)
    if (atm != null) {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yS(atm)).attr('y2', yS(atm))
        .attr('stroke', t.text).attr('stroke-width', 1).attr('stroke-dasharray', '5 4')
        .attr('stroke-opacity', 0.55);
      svg.append('text').attr('x', zones.data.x + 5).attr('y', yS(atm) - 5)
        .attr('text-anchor', 'start').attr('font-family', 'Noto Sans KR')
        .attr('font-size', 10).attr('fill', t.text).attr('fill-opacity', 0.8)
        .text('ATM IV ' + atm.toFixed(1) + '% (등가격 기준선)');
    }
    function drawDay(rows, opacity, withDots) {
      var puts = rows.filter(function (d) { return (d.type || '') === 'put'; });
      var calls = rows.filter(function (d) { return (d.type || '') === 'call'; });
      [[puts, PUT], [calls, CALL]].forEach(function (pair) {
        var s = pair[0], col = pair[1];
        s.sort(function (a, b) { return (+a.strike) - (+b.strike); });
        if (s.length >= 2) {
          var ln = d3.line().x(function (d) { return xS(+d.strike); })
            .y(function (d) { return yS(+d.iv); }).curve(d3.curveLinear);
          svg.append('path').attr('d', ln(s)).attr('fill', 'none').attr('stroke', col)
            .attr('stroke-width', withDots ? 1.9 : 1.1).attr('stroke-opacity', opacity);
        }
        if (withDots) {
          s.forEach(function (d) {
            svg.append('circle').attr('cx', xS(+d.strike)).attr('cy', yS(+d.iv)).attr('r', 3.2)
              .attr('fill', col).attr('fill-opacity', 0.95);
          });
        }
      });
      if (!puts.length && !calls.length) {
        rows.sort(function (a, b) { return (+a.strike) - (+b.strike); });
        var ln2 = d3.line().x(function (d) { return xS(+d.strike); })
          .y(function (d) { return yS(+d.iv); });
        svg.append('path').attr('d', ln2(rows)).attr('fill', 'none')
          .attr('stroke', t.accent).attr('stroke-width', withDots ? 1.9 : 1.1)
          .attr('stroke-opacity', opacity);
      }
    }
    if (hasDates) {
      dates.forEach(function (dt, i) {
        var age = dates.length - 1 - i;  // 0 = 오늘
        var op = age === 0 ? 0.95 : Math.max(0.10, 0.5 * Math.pow(0.8, age));
        drawDay(raw.filter(function (d) { return d.date === dt; }), op, age === 0);
      });
    } else {
      drawDay(raw.slice(), 0.95, true);
    }
    // x축 — 각 행사가 라벨 (#1). 오늘(또는 전체) distinct 행사가에 눈금+회전 라벨.
    var base = (hasDates ? raw.filter(function (d) { return d.date === today; }) : raw);
    var strikes = Array.from(new Set(base.map(function (d) { return +d.strike; })))
      .sort(function (a, b) { return a - b; });
    var st = strikes.length > 16 ? Math.ceil(strikes.length / 16) : 1;
    var yb = zones.data.y + zones.data.h;
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', yb).attr('y2', yb).attr('stroke', t.muted).attr('stroke-opacity', 0.4);
    strikes.forEach(function (s, i) {
      if (i % st !== 0 && i !== strikes.length - 1) return;
      svg.append('line').attr('x1', xS(s)).attr('x2', xS(s)).attr('y1', yb).attr('y2', yb + 4)
        .attr('stroke', t.muted).attr('stroke-opacity', 0.5);
      svg.append('text').attr('x', xS(s)).attr('y', yb + 7)
        .attr('transform', 'rotate(-42,' + xS(s) + ',' + (yb + 7) + ')')
        .attr('text-anchor', 'end').attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-size', 8.5).attr('fill', t.muted).text(d3.format(',.0f')(s));
    });
    if (payload.x_label) {
      svg.append('text').attr('x', zones.data.x + zones.data.w).attr('y', yb + 30)
        .attr('text-anchor', 'end').attr('font-size', 10).attr('fill', t.muted).text(payload.x_label);
    }
    // 범례 (우상단) + 다일자 안내
    function legend(x, color, label) {
      svg.append('circle').attr('cx', x).attr('cy', zones.data.y - 16).attr('r', 4).attr('fill', color);
      svg.append('text').attr('x', x + 9).attr('y', zones.data.y - 12)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11).attr('fill', t.text).text(label);
    }
    legend(zones.data.x + zones.data.w - 120, PUT, '풋 (Put)');
    legend(zones.data.x + zones.data.w - 56, CALL, '콜 (Call)');
    if (hasDates) {
      svg.append('text').attr('x', zones.data.x).attr('y', zones.data.y - 12)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.muted)
        .text('진한 곡선 = 오늘 · 옅을수록 과거 (' + dates.length + '영업일)');
    }
  }

  // ----- INDICATOR (부호 있는 한 줄 지표 — 0 중심) -----
  // v7.9.10 — 선물 베이시스/콘탱고 같은 ± 스칼라 한 줄 시각화. 0 중심 축 위에
  // 현재값 막대 + 부호별 색(양수=accent, 음수=down) + 값 라벨.
  // data: [{label, value, unit?, pos_label?, neg_label?}]
  function drawIndicator(stage, payload, t) {
    var rows = (payload.data || []).filter(function (d) { return isFinite(+d.value); });
    if (!rows.length || rows.length > 4) return;
    var W = 720, rowH = 52, top = 20, bottom = 18;
    var H = top + rows.length * rowH + bottom;
    var svg = d3.select(stage).select('svg')
      .attr('viewBox', '0 0 ' + W + ' ' + H).attr('preserveAspectRatio', 'xMidYMid meet');
    var labelW = 150, x0 = labelW + 16, x1 = W - 30;
    var cx = (x0 + x1) / 2;
    var maxAbs = d3.max(rows, function (d) { return Math.abs(+d.value); }) || 1;
    var half = (x1 - x0) / 2 - 70;
    var sc = function (v) { return (Math.abs(+v) / maxAbs) * half; };
    rows.forEach(function (d, i) {
      var cy = top + i * rowH + rowH / 2;
      // 라벨
      svg.append('text').attr('x', labelW).attr('y', cy + 4).attr('text-anchor', 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 12).attr('fill', t.text)
        .text(String(d.label || ''));
      // 0 중심선 (세로)
      svg.append('line').attr('x1', cx).attr('x2', cx).attr('y1', cy - 18).attr('y2', cy + 18)
        .attr('stroke', t.muted).attr('stroke-width', 1).attr('stroke-opacity', 0.6);
      svg.append('text').attr('x', cx).attr('y', cy - 22).attr('text-anchor', 'middle')
        .attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 8).attr('fill', t.muted).text('0');
      var v = +d.value, pos = v >= 0;
      var col = pos ? t.accent : (t.down || '#C45C4C');
      var w = sc(v);
      svg.append('rect').attr('x', pos ? cx : cx - w).attr('y', cy - 9)
        .attr('width', Math.max(1, w)).attr('height', 18).attr('fill', col).attr('fill-opacity', 0.85);
      // 값 라벨
      var vtxt = (v >= 0 ? '+' : '') + (Math.abs(v) >= 100 ? d3.format(',.0f')(v) : d3.format(',.2f')(v)) + (d.unit || '');
      var sub = pos ? (d.pos_label || '') : (d.neg_label || '');
      svg.append('text').attr('x', pos ? (cx + w + 8) : (cx - w - 8)).attr('y', cy + 4)
        .attr('text-anchor', pos ? 'start' : 'end').attr('font-family', 'Noto Serif KR')
        .attr('font-size', 14).attr('font-weight', 700).attr('fill', col)
        .text(vtxt + (sub ? '  ' + sub : ''));
    });
  }

  // ----- STAKEHOLDER_MAP (v8.0.0 — 르포 행위자 관계도) -----
  // force/hairball 금지 (CHART-AP-36): 노드는 진영(col) 칼럼에 결정적 배치, 칼럼 내
  // 세로 중앙 정렬(같은 행 = 직선), 엣지는 직각+라운딩으로 노드 위 후행 레이어 +
  // 노드별 다중 연결을 가장자리에 분산. 자산(국기/인물)은 sprite(#sm-*)로 분리 —
  // osint_generator 자산으로 교체 가능. 로고/사진 미제공 시 이니셜 모노그램.
  const SM_FLAGS = { US:1, TW:1, CN:1, JP:1, UA:1, RU:1 };
  const SM_SPRITE =
    '<defs>' +
    '<marker id="sm-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker>' +
    '<symbol id="sm-person" viewBox="0 0 32 32"><clipPath id="sm-cph"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cph)"><rect width="32" height="32" fill="#c9b79a"/><circle cx="16" cy="12.5" r="6" fill="#f1e6d4"/><path d="M4 30c0-7 6-10 12-10s12 3 12 10z" fill="#f1e6d4"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.18)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-US" viewBox="0 0 32 32"><clipPath id="sm-cUS"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cUS)"><rect width="32" height="32" fill="#fff"/><g fill="#b22234"><rect y="0" width="32" height="2.46"/><rect y="4.92" width="32" height="2.46"/><rect y="9.84" width="32" height="2.46"/><rect y="14.76" width="32" height="2.46"/><rect y="19.69" width="32" height="2.46"/><rect y="24.61" width="32" height="2.46"/><rect y="29.54" width="32" height="2.46"/></g><rect width="14.2" height="13.2" fill="#3c3b6e"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-TW" viewBox="0 0 32 32"><clipPath id="sm-cTW"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cTW)"><rect width="32" height="32" fill="#fe0000"/><rect width="16" height="16" fill="#000095"/><g transform="translate(8,8)" fill="#fff"><circle r="3.4"/><circle r="2.8" fill="#000095"/><circle r="2.2" fill="#fff"/></g></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-CN" viewBox="0 0 32 32"><clipPath id="sm-cCN"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cCN)"><rect width="32" height="32" fill="#de2910"/><circle cx="8" cy="9" r="3.2" fill="#ffde00"/><circle cx="14" cy="4" r="1.1" fill="#ffde00"/><circle cx="16" cy="7.5" r="1.1" fill="#ffde00"/><circle cx="16" cy="11.5" r="1.1" fill="#ffde00"/><circle cx="14" cy="14.5" r="1.1" fill="#ffde00"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-JP" viewBox="0 0 32 32"><clipPath id="sm-cJP"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cJP)"><rect width="32" height="32" fill="#fff"/><circle cx="16" cy="16" r="7.5" fill="#bc002d"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-UA" viewBox="0 0 32 32"><clipPath id="sm-cUA"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cUA)"><rect width="32" height="16" fill="#0057b7"/><rect y="16" width="32" height="16" fill="#ffd700"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '<symbol id="sm-flag-RU" viewBox="0 0 32 32"><clipPath id="sm-cRU"><circle cx="16" cy="16" r="16"/></clipPath><g clip-path="url(#sm-cRU)"><rect width="32" height="10.67" fill="#fff"/><rect y="10.67" width="32" height="10.67" fill="#0039a6"/><rect y="21.33" width="32" height="10.67" fill="#d52b1e"/></g><circle cx="16" cy="16" r="15.3" fill="none" stroke="rgba(0,0,0,.16)" stroke-width="1.3"/></symbol>' +
    '</defs>';

  function smSprite() {
    if (document.getElementById('sm-sprite')) return;
    const w = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    w.setAttribute('id', 'sm-sprite');
    w.setAttribute('width', '0'); w.setAttribute('height', '0');
    w.setAttribute('aria-hidden', 'true');
    w.style.position = 'absolute';
    w.innerHTML = SM_SPRITE;
    document.body.appendChild(w);
  }

  function smColor(group, t) {
    const g = String(group || '').toLowerCase();
    if (/반대|대립|적|oppose|against|hostile|rival/.test(g)) return t.down;
    if (/주도|동맹|찬성|승인|핵심|ally|support|lead|core/.test(g)) return t.accent;
    return t.muted;
  }

  function smRoute(x0, y0, x1, y1, r) {
    r = r || 12;
    if (Math.abs(y0 - y1) < 0.5) return `M${x0},${y0} H${x1}`;
    if (Math.abs(x0 - x1) < 0.5) return `M${x0},${y0} V${y1}`;
    const sx = x1 >= x0 ? 1 : -1, sy = y1 >= y0 ? 1 : -1, mx = (x0 + x1) / 2;
    const rr = Math.min(r, Math.abs(mx - x0), Math.abs(y1 - y0) / 2);
    return `M${x0},${y0} H${mx - sx * rr} Q${mx},${y0} ${mx},${y0 + sy * rr} V${y1 - sy * rr} Q${mx},${y1} ${mx + sx * rr},${y1} H${x1}`;
  }

  function smLinkStyle(type, t) {
    const s = String(type || '').toLowerCase();
    if (/대립|충돌|갈등|적|conflict|oppose|against|hostile|rival/.test(s))
      return { stroke: t.down, w: 1.9, dash: '5 4', gl: '✕', gc: t.down, arrow: false };
    if (/동맹|협력|지지|연합|제휴|지원|자금|출자|ally|alliance|support|coop|partner|fund/.test(s))
      return { stroke: t.accent, w: 2.1, dash: null, gl: '●', gc: t.accent, arrow: false };
    if (/영향|압박|의존|주도|환류|통제|leverage|influence|pressure|depend|drive|control/.test(s))
      return { stroke: t.text, w: 2, dash: null, gl: null, gc: null, arrow: true };
    return { stroke: t.muted, w: 1.5, dash: null, gl: '○', gc: t.muted, arrow: false };
  }

  function drawStakeholderMap(stage, payload, t) {
    const D = payload.data || {};
    const rawNodes = D.nodes || [];
    const edges = D.edges || D.links || [];
    if (rawNodes.length < 2) return;
    smSprite();

    const svg = d3.select(stage).select('svg').attr('preserveAspectRatio', 'xMidYMid meet');
    const root = svg.append('g');
    // v8.0.0 — 르포(reportage)면 플랫(rx 0) + ambient 애니메이션(엣지 흐름 + hub 펄스).
    // prefers-reduced-motion 시 애니 OFF. 일반 보고서는 기존 정적 렌더 그대로.
    const SM_REP = ((document.documentElement.getAttribute('data-theme') || '').indexOf('reportage_') === 0);
    const SM_RM = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const SM_ANIM = SM_REP && !SM_RM;
    const SM_RX = SM_REP ? 0 : 10;

    function colOf(nd) {
      let c = nd.col;
      if (c === undefined || c === null) c = 0;
      if (c === 'left' || c === 'l') c = 0;
      else if (c === 'center' || c === 'c' || c === 'mid' || c === 'hub') c = 1;
      else if (c === 'right' || c === 'r') c = 2;
      else c = (+c) || 0;
      return Math.max(0, Math.min(2, c));
    }
    const cols = [[], [], []];
    rawNodes.forEach(nd => cols[colOf(nd)].push(nd));

    const LW = 210, CW = 176, RW = 210, GAP = 128, H = 54, CH = 62, VSP = 120;
    const colX = [0, LW + GAP, LW + GAP + CW + GAP];
    const colW = [LW, CW, RW];
    const pos = {};
    cols.forEach((list, ci) => {
      const k = list.length; if (!k) return;
      const top = -(k - 1) * VSP / 2;
      list.forEach((nd, i) => {
        const h = (ci === 1) ? CH : H, w = colW[ci], cy = top + i * VSP;
        pos[nd.id] = { x: colX[ci], y: cy - h / 2, w, h, cx: colX[ci] + w / 2,
                       cy, lx: colX[ci], rx: colX[ci] + w, col: ci, node: nd };
      });
    });

    const valid = edges.filter(e => pos[e.source] && pos[e.target] && e.source !== e.target);

    // 노드+side 별 엣지 → other-cy 정렬 후 가장자리에 분산 (한 점 겹침 방지)
    function sides(a, b) {
      const A = pos[a], B = pos[b];
      if (A.col < B.col) return ['R', 'L'];
      if (A.col > B.col) return ['L', 'R'];
      return (A.cy <= B.cy) ? ['B', 'T'] : ['T', 'B'];
    }
    const slots = {};
    valid.forEach((e, ei) => {
      const [sa, sb] = sides(e.source, e.target);
      (slots[e.source + '|' + sa] = slots[e.source + '|' + sa] || []).push({ ei, other: pos[e.target].cy, ox: pos[e.target].cx });
      (slots[e.target + '|' + sb] = slots[e.target + '|' + sb] || []).push({ ei, other: pos[e.source].cy, ox: pos[e.source].cx });
    });
    const attach = {};
    Object.keys(slots).forEach(key => {
      const idx = key.lastIndexOf('|'); const id = key.slice(0, idx), sd = key.slice(idx + 1);
      const P = pos[id], arr = slots[key], n = arr.length;
      if (sd === 'L' || sd === 'R') {
        arr.sort((p, q) => p.other - q.other);
        const span = Math.min(P.h - 14, (n - 1) * 16), top = P.cy - span / 2, X = (sd === 'R') ? P.rx : P.lx;
        arr.forEach((it, i) => { attach[it.ei + '|' + id] = { x: X, y: n === 1 ? P.cy : top + i * (span / (n - 1)) }; });
      } else {
        arr.sort((p, q) => p.ox - q.ox);
        const span = Math.min(P.w - 24, (n - 1) * 18), left = P.cx - span / 2, Y = (sd === 'B') ? (P.y + P.h) : P.y;
        arr.forEach((it, i) => { attach[it.ei + '|' + id] = { x: n === 1 ? P.cx : left + i * (span / (n - 1)), y: Y }; });
      }
    });

    // 엣지 (노드 아래 레이어)
    valid.forEach((e, ei) => {
      const A = attach[ei + '|' + e.source] || { x: pos[e.source].rx, y: pos[e.source].cy };
      const B = attach[ei + '|' + e.target] || { x: pos[e.target].lx, y: pos[e.target].cy };
      const st = smLinkStyle(e.type, t);
      const p = root.append('path').attr('d', smRoute(A.x, A.y, B.x, B.y))
        .attr('fill', 'none').attr('stroke', st.stroke).attr('stroke-width', st.w)
        .attr('data-anim', 'static');
      if (st.dash) p.attr('stroke-dasharray', st.dash);
      if (st.arrow) p.attr('marker-end', 'url(#sm-arr)');
      if (SM_ANIM) p.attr('stroke-dasharray', st.dash || '5 9').classed('sm-flow', true);
    });

    // 노드 카드
    function drawCard(P) {
      const nd = P.node, isHub = P.col === 1;
      const accent = !!nd.accent || /주도|핵심|당사자|hub|lead|core/.test(String(nd.group || ''));
      const g = root.append('g').attr('transform', `translate(${P.x},${P.y})`);
      g.append('rect').attr('width', P.w).attr('height', P.h).attr('rx', SM_RX)
        .attr('fill', t.card)
        .attr('stroke', isHub ? t.text : (accent ? t.accent : t.border))
        .attr('stroke-width', isHub ? 2.2 : (accent ? 1.6 : 1)).attr('data-anim', 'static');
      const ay = (P.h - 30) / 2;
      const fc = String(nd.flag || '').toUpperCase();
      if (fc && SM_FLAGS[fc]) {
        g.append('use').attr('href', '#sm-flag-' + fc).attr('x', 12).attr('y', ay).attr('width', 30).attr('height', 30);
      } else if (nd.kind === 'person' || nd.type === 'person') {
        g.append('use').attr('href', '#sm-person').attr('x', 12).attr('y', ay).attr('width', 30).attr('height', 30);
      } else {
        const ini = String(nd.label || nd.id || '?').trim().slice(0, 2);
        g.append('rect').attr('x', 12).attr('y', ay).attr('width', 30).attr('height', 30).attr('rx', SM_REP ? 0 : 7).attr('fill', smColor(nd.group, t));
        g.append('text').attr('x', 27).attr('y', ay + 20).attr('text-anchor', 'middle')
          .attr('font-family', 'Noto Sans KR').attr('font-weight', 700).attr('font-size', 12).attr('fill', t.bg).text(ini);
      }
      const bc = String(nd.badge || '').toUpperCase();
      if (bc && SM_FLAGS[bc]) g.append('use').attr('href', '#sm-flag-' + bc).attr('x', 30).attr('y', ay + 18).attr('width', 14).attr('height', 14);
      g.append('text').attr('x', 52).attr('y', P.h / 2 - 3).attr('font-family', 'Noto Sans KR')
        .attr('font-weight', 600).attr('font-size', 13).attr('fill', t.text).text(String(nd.label || nd.id || '').slice(0, 16));
      if (nd.role) g.append('text').attr('x', 52).attr('y', P.h / 2 + 13).attr('font-family', 'Noto Sans KR')
        .attr('font-size', 10.5).attr('fill', t.muted).text(String(nd.role).slice(0, 22));
    }
    Object.values(pos).forEach(drawCard);

    // v8.0.0 — 르포 ambient: hub 펄스 링 (살아있는 느낌)
    if (SM_ANIM) {
      const hub = Object.values(pos).find(p => p.col === 1);
      if (hub) root.append('rect').attr('x', hub.x - 6).attr('y', hub.y - 6)
        .attr('width', hub.w + 12).attr('height', hub.h + 12).attr('rx', 0)
        .attr('fill', 'none').attr('stroke', t.accent).attr('stroke-width', 1.4)
        .attr('class', 'sm-pulse');
    }

    // 라벨 (선 위 중앙) — 카드 위 레이어
    valid.forEach((e, ei) => {
      const A = attach[ei + '|' + e.source], B = attach[ei + '|' + e.target];
      if (!A || !B) return;
      const st = smLinkStyle(e.type, t), lab = String(e.label || '');
      if (!lab && !st.gl) return;
      const cx = (A.x + B.x) / 2, cy = (A.y + B.y) / 2;
      const wch = 16 + lab.length * 9 + (st.gl ? 14 : 0);
      const gg = root.append('g').attr('transform', `translate(${cx},${cy})`);
      gg.append('rect').attr('x', -wch / 2).attr('y', -9).attr('width', wch).attr('height', 18).attr('rx', 5)
        .attr('fill', t.bg).attr('fill-opacity', 0.9).attr('data-anim', 'static');
      const te = gg.append('text').attr('y', 3.5).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10.5);
      if (st.gl) te.append('tspan').attr('fill', st.gc).attr('font-weight', 700).text(st.gl + ' ');
      te.append('tspan').attr('fill', t.muted).text(lab);
    });

    const bb = root.node().getBBox(); const pad = 14;
    svg.attr('viewBox', `${bb.x - pad} ${bb.y - pad} ${bb.width + pad * 2} ${bb.height + pad * 2}`);
  }


  // Dispatcher
  // ============================================================
  const RENDERERS = {
    bar: drawBar, donut: drawDonut, line: drawLine, gantt: drawGantt,
    stacked: drawStacked, bubble: drawBubble, heatmap: drawHeatmap,
    dual_line: drawDualLine, forecast: drawForecast, choropleth: drawChoropleth,
    // v5.2.0 — 시계열 OHLC 차트 (market_fetcher 데이터)
    candle: drawCandle, area: drawArea,
    // v5.2.14 — FT/Economist 스타일 신규 7종
    scatter: drawScatter, stacked_area: drawStackedArea, lollipop: drawLollipop,
    slope: drawSlope, small_multiples: drawSmallMultiples,
    waterfall: drawWaterfall, range_bar: drawRangeBar,
    // v5.3.0 — Sankey (재무 분해 / 자본 배분). orphan 해결.
    sankey: drawSankey,
    // v7.0.0 — Track A 신규 3종 (순위 경쟁 / 목표 대비 / 2변수 궤적)
    bump: drawBump, bullet: drawBullet, connected_scatter: drawConnectedScatter,
    // v7.5.0 — 이중 축 결합 + 사회 이슈 어휘 4종
    combo: drawCombo, diverging_bar: drawDivergingBar,
    pyramid: drawPyramid, dot_matrix: drawDotMatrix,
    // v7.9.9 — 좌축 line(비율) + 우축 candle(지수) 결합 (장마감 브리핑 breadth)
    combo_candle: drawComboCandle,
    // v7.9.10 — 옵션 데스크: 변동성 스큐 곡선 + 부호 한 줄 지표
    iv_skew: drawIvSkew, indicator: drawIndicator,
    // v8.0.0 — 르포 전용 행위자 관계도 (진영 칼럼 결정적 배치, force 금지)
    stakeholder_map: drawStakeholderMap,
  };

  async function renderStage(stage, idx) {
    const card = stage.parentElement;
    if (!card) return;
    const script = card.querySelector('script.chart-payload-inline');
    if (!script) return;
    let payload;
    try { payload = JSON.parse(script.textContent); }
    catch (e) { console.warn('[charts] payload parse fail', e); return; }
    const type = String(payload.type || stage.getAttribute('data-chart-type') || 'bar').toLowerCase();
    const renderer = RENDERERS[type];
    if (!renderer) { console.warn('[charts] unknown type:', type); return; }
    if (!stage.getAttribute('data-chart-id')) {
      stage.setAttribute('data-chart-id', `pat-${idx}`);
    }
    const t = readTheme(stage);
    try { await renderer(stage, payload, t); }
    catch (e) { console.warn('[charts] render error for', type, e); }
  }

  // ============================================================
  // v5.3.0 — Entry Animation Framework
  // v5.3.1 — bar grow + donut arc sweep + fill-path fade-in (option C).
  //
  // IntersectionObserver 로 차트 카드가 뷰포트 진입 시점에 renderStage 호출,
  // SVG 생성 직후 _applyEntryAnimation 이 type-aware 분기 후 post-process.
  //
  // 분기:
  //   (A) bar  → rect[data-anim="bar-grow"] 의 width 0→final, stagger 40ms
  //   (B) donut→ path[data-anim="donut-arc"] 의 arc sweep (attrTween)
  //   (C) 공통 path  → fill-only/stroked+fill = opacity fade,
  //                    stroke-only = stroke-dashoffset 그리기 (대시 패턴 보존)
  //   (D) 공통 rect  → opacity fade-in (tagged 는 skip)
  //   (E) 공통 circle→ r=0 → r 확장
  //
  // CHART-AP-18 (motion regression) 방지:
  // - duration ≤ 700ms (스크롤 속도 방해 차단)
  // - 1회 재생 후 unobserve (반복 재생 X)
  // - IntersectionObserver 미지원 브라우저 → backward-compat 즉시 렌더
  // - prefers-reduced-motion → 모든 분기 즉시 return, 정적 final state 유지
  // ============================================================

  function _motionEnabled() {
    if (!window.matchMedia) return true;
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function _animateBars(svg) {
    let barIdx = 0;
    svg.selectAll('rect[data-anim="bar-grow"]').each(function () {
      const node = this;
      const finalW = parseFloat(node.getAttribute('data-final-w') || '0');
      if (!isFinite(finalW) || finalW <= 0) return;
      d3.select(node).attr('width', 0)
        .transition().delay((barIdx++) * 40).duration(380).ease(d3.easeCubicOut)
        .attr('width', finalW);
    });
  }

  function _animateDonut(svg) {
    const cxAttr = svg.attr('data-donut-cx');
    if (!cxAttr) return;
    const cx = parseFloat(cxAttr);
    const cy = parseFloat(svg.attr('data-donut-cy'));
    const ir = parseFloat(svg.attr('data-donut-ir'));
    const r = parseFloat(svg.attr('data-donut-r'));
    if (![cx, cy, ir, r].every(isFinite)) return;
    const arcGen = d3.arc().innerRadius(ir).outerRadius(r);
    svg.selectAll('path[data-anim="donut-arc"]').each(function () {
      const node = this;
      const sa = parseFloat(node.getAttribute('data-start'));
      const ea = parseFloat(node.getAttribute('data-end'));
      if (!isFinite(sa) || !isFinite(ea)) return;
      // 시작 프레임 깜빡임 방지 — transition 직전 d 를 zero-arc 로 동기 세팅.
      d3.select(node).attr('d', arcGen({ startAngle: sa, endAngle: sa }))
        .transition().duration(680).ease(d3.easeCubicOut)
        .attrTween('d', function () {
          const interp = d3.interpolate(
            { startAngle: sa, endAngle: sa },
            { startAngle: sa, endAngle: ea }
          );
          return tt => arcGen(interp(tt));
        });
    });
  }

  function _applyEntryAnimation(stage) {
    if (!_motionEnabled()) return;
    const svg = d3.select(stage).select('svg');
    if (svg.empty()) return;

    // (A,B) Type-specific 우선 — bar/donut 의 tagged 요소 처리.
    _animateBars(svg);
    _animateDonut(svg);

    // (C) 공통 path — tagged 는 skip. fill 존재 여부로 분기.
    svg.selectAll('path').each(function () {
      const node = this;
      if (node.getAttribute('data-anim')) return;  // 이미 처리됨
      const sel = d3.select(node);
      const stroke = sel.attr('stroke');
      const fill = sel.attr('fill');
      const hasStroke = stroke && stroke !== 'none';
      const hasFill = fill && fill !== 'none' && fill !== 'transparent';
      if (!hasStroke && !hasFill) return;

      if (hasFill) {
        // 채워진 path (sankey flow / choropleth 국경 / stacked_area layer /
        // forecast cone / area gradient fill) — opacity fade-in.
        // 채워진 path 에 stroke-draw 를 걸면 채움이 먼저 보여 어색함 → fade 가 안전.
        sel.style('opacity', 0)
          .transition().duration(360).ease(d3.easeCubicOut)
          .style('opacity', 1);
        return;
      }
      // stroke-only path — stroke-dashoffset 그리기.
      let len;
      try { len = node.getTotalLength(); } catch (e) { return; }
      if (!isFinite(len) || len < 4 || len > 8000) return;
      // v5.3.1 — 원래 dasharray (dual_line/forecast 의 점선) 보존 fix.
      // 이전엔 data-orig-dasharray 를 어디서도 set 안 해 on('end') 의 복원이
      // 항상 null → 점선이 솔리드로 둔갑하는 회귀가 있었음.
      const origDashArr = sel.attr('stroke-dasharray');
      if (origDashArr) sel.attr('data-orig-dasharray', origDashArr);
      sel.attr('stroke-dasharray', `${len} ${len}`)
        .attr('stroke-dashoffset', len)
        .transition().duration(700).ease(d3.easeCubicOut)
        .attr('stroke-dashoffset', 0)
        .on('end', function () {
          const orig = sel.attr('data-orig-dasharray');
          d3.select(this).attr('stroke-dasharray', orig || null);
          if (orig) sel.attr('data-orig-dasharray', null);
        });
    });

    // (D) 공통 rect — tagged (bar-grow) 는 skip. clipPath/배경 제외.
    let rectIdx = 0;
    svg.selectAll('rect').each(function () {
      const node = this;
      if (node.getAttribute('data-anim')) return;  // bar-grow 처리됨
      const parent = node.parentNode;
      if (parent && parent.tagName === 'clipPath') return;
      const w = parseFloat(node.getAttribute('width') || '0');
      const h = parseFloat(node.getAttribute('height') || '0');
      if (w < 3 || h < 3) return;
      const vbAttr = svg.attr('viewBox');
      if (vbAttr) {
        const parts = vbAttr.split(/\s+/);
        const vbW = parseFloat(parts[2] || '0');
        if (w >= vbW * 0.95 && h >= 1) return;
      }
      d3.select(node).style('opacity', 0)
        .transition().delay((rectIdx++) * 20).duration(380).ease(d3.easeCubicOut)
        .style('opacity', 1);
    });

    // (E) 공통 circle — r=0 → r 확장. r ≥1.5 만.
    svg.selectAll('circle').each(function () {
      const node = this;
      const r = parseFloat(node.getAttribute('r') || '0');
      if (r < 1.5) return;
      d3.select(node).attr('r', 0)
        .transition().duration(440).ease(d3.easeBackOut.overshoot(1.3))
        .attr('r', r);
    });
  }

  function init() {
    const stages = document.querySelectorAll('.chart-card-stage[data-chart-type]');
    // v5.2.5 — compact strip sparkline 은 항상 즉시 렌더 (작아서 애니 의미 없음).
    renderSparklines();

    // IntersectionObserver 미지원 브라우저 → backward-compat 즉시 렌더.
    if (!window.IntersectionObserver || !stages.length) {
      stages.forEach((stage, i) => renderStage(stage, i));
      return;
    }
    const io = new IntersectionObserver(async (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const stage = entry.target;
        const idx = parseInt(stage.dataset.animIdx || '0', 10);
        io.unobserve(stage);
        await renderStage(stage, idx);
        // 다음 RAF 틱에 애니메이션 적용 (SVG DOM 안착 후)
        requestAnimationFrame(() => _applyEntryAnimation(stage));
      }
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
    stages.forEach((stage, i) => {
      stage.dataset.animIdx = String(i);
      io.observe(stage);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
