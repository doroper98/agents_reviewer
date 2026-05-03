/* charts.js — v4.4.0 zone-based layout + annotations + 11 chart types.
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
 * 11 type: bar / donut / line / gantt / network / stacked / bubble / heatmap
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
  function drawBar(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value));
    if (!data.length) return;
    const W = 720;
    const rowH = 28;
    const H = 56 + 32 + (data.length * rowH) + 16;
    const zones = computeZones(W, H, { left: 140, right: 60 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    const max = d3.max(data, d => Math.abs(+d.value)) || 1;
    const xScale = (v) => zones.data.x + (Math.abs(+v) / max) * zones.data.w;

    // Bars + smart label placement
    data.forEach((d, i) => {
      const y = zones.data.y + 4 + i * rowH;
      const x0 = zones.data.x;
      const x1 = xScale(d.value);
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 13).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .text(String(d.label || '').slice(0, 22));
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', x1 - x0).attr('height', 16)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', i === 0 ? 0 : 0.4);
      // Smart label: if not enough room outside (right of bar), place INSIDE bar
      // right-aligned with bg color (JPM 풍 inverse). Label width estimate: chars * 7.
      const labelText = String(d.value);
      const labelW = labelText.length * 7 + 4;
      if (x1 + 6 + labelW <= zones.W - 4) {
        // Outside, right of bar
        svg.append('text').attr('x', x1 + 6).attr('y', y + 12)
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700)
          .attr('fill', t.text).text(labelText);
      } else if (x1 - x0 > labelW + 8) {
        // Inside bar (bar is wide enough), right-aligned, inverse color
        const insideColor = i === 0 ? t.bg : t.text;
        svg.append('text').attr('x', x1 - 4).attr('y', y + 12).attr('text-anchor', 'end')
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700)
          .attr('fill', insideColor).text(labelText);
      } else {
        // Fallback: right-aligned at viewBox edge (small bar in narrow chart)
        svg.append('text').attr('x', zones.W - 4).attr('y', y + 12).attr('text-anchor', 'end')
          .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700)
          .attr('fill', t.text).text(labelText);
      }
    });

    // X axis
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', H - zones.bottom + 4).attr('y2', H - zones.bottom + 4)
      .attr('stroke', t.muted).attr('stroke-opacity', 0.4).attr('stroke-width', 0.5);
    [0, 0.25, 0.5, 0.75, 1].forEach(p => {
      const x = zones.data.x + p * zones.data.w;
      svg.append('text').attr('x', x).attr('y', H - zones.bottom + 18).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(d3.format(max >= 100 ? ',' : '.1f')(p * max));
    });

    // Annotations: hline (=vertical reference line on x axis), band (vertical region), vline (rare for bar)
    // For bar: scaleX is value→pixel
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }

  // ----- DONUT -----
  function drawDonut(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value) && +d.value > 0);
    if (data.length < 3) return;
    const W = 480, H = 240;
    const zones = computeZones(W, H, { left: 0, right: 0, top: 8, bottom: 8 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    const cx = 120, cy = H / 2, r = 90, ir = 56;
    const total = d3.sum(data, d => +d.value);
    const pie = d3.pie().value(d => +d.value).sort(null);
    const arc = d3.arc().innerRadius(ir).outerRadius(r);
    pie(data).forEach((a, i) => {
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('path').attr('d', arc(a)).attr('transform', `translate(${cx},${cy})`)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.5);
    });
    // Center label
    svg.append('text').attr('x', cx).attr('y', cy - 4).attr('text-anchor', 'middle')
      .attr('font-family', 'Noto Serif KR').attr('font-size', 11)
      .attr('fill', t.muted).text('TOTAL');
    svg.append('text').attr('x', cx).attr('y', cy + 14).attr('text-anchor', 'middle')
      .attr('font-family', 'Noto Serif KR').attr('font-size', 18).attr('font-weight', 700)
      .attr('fill', t.text).text(d3.format(total > 100 ? ',.0f' : '.1f')(total));
    // Legend
    const lx = 250;
    data.forEach((d, i) => {
      const y = 24 + i * 22;
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('rect').attr('x', lx).attr('y', y - 9).attr('width', 16).attr('height', 11)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.4);
      svg.append('text').attr('x', lx + 22).attr('y', y).attr('fill', t.text)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .text(`${String(d.label || '').slice(0, 14)}  ${(+d.value / total * 100).toFixed(0)}%`);
    });
  }

  // ----- LINE (with optional events) -----
  function drawLine(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.y));
    if (data.length < 2) return;
    const W = 760, H = 320;
    const zones = computeZones(W, H, { left: 60, right: 110 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');

    const x = d3.scalePoint().domain(data.map(d => String(d.x))).range([zones.data.x, zones.data.x + zones.data.w]).padding(0.1);
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

    // Area fill + line
    const line = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    const area = d3.area().x(d => x(String(d.x))).y0(zones.data.y + zones.data.h)
      .y1(d => y(+d.y)).curve(d3.curveMonotoneX);
    svg.append('path').attr('d', area(data)).attr('fill', t.accent).attr('fill-opacity', 0.10);
    svg.append('path').attr('d', line(data)).attr('fill', 'none').attr('stroke', t.text).attr('stroke-width', 1.4);

    // End marker + label
    const last = data[data.length - 1];
    svg.append('circle').attr('cx', x(String(last.x))).attr('cy', y(+last.y)).attr('r', 3.5).attr('fill', t.accent);
    placeEndLabel(svg, x(String(last.x)), y(+last.y), String(last.y), t, occupancy, zones, t.accent);

    // x labels (sparse)
    const step = Math.max(1, Math.ceil(data.length / 7));
    data.forEach((d, i) => {
      if (i % step !== 0 && i !== data.length - 1) return;
      svg.append('text').attr('x', x(String(d.x))).attr('y', H - zones.bottom + 16).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(String(d.x).slice(0, 12));
    });
    // Inline events from data points (legacy support)
    data.filter(d => d.event).forEach(d => {
      svg.append('line').attr('x1', x(String(d.x))).attr('x2', x(String(d.x)))
        .attr('y1', zones.data.y).attr('y2', zones.data.y + zones.data.h)
        .attr('stroke', t.down).attr('stroke-width', 0.8).attr('stroke-dasharray', '3,3');
    });
  }

  // ----- GANTT -----
  function drawGantt(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 720;
    const rowH = 24;
    const H = 56 + 32 + (data.length * rowH) + 8;
    const zones = computeZones(W, H, { left: 150, right: 60 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const min = d3.min(data, d => +d.start);
    const max = d3.max(data, d => +d.end || (+d.start + 1));
    const xScale = d3.scaleLinear().domain([min, max])
      .range([zones.data.x, zones.data.x + zones.data.w]);
    data.forEach((d, i) => {
      const y = zones.data.y + 4 + i * rowH;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text(String(d.label || '').slice(0, 22));
      const x0 = xScale(+d.start);
      const x1 = xScale(+(d.end || d.start + 1));
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', Math.max(2, x1 - x0)).attr('height', 14)
        .attr('fill', t.accent).attr('rx', 1.5);
      if (d.note) {
        svg.append('text').attr('x', x1 + 6).attr('y', y + 11)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
          .text(String(d.note).slice(0, 18));
      }
    });
    renderAnnotations(svg, payload, zones, t, xScale, null);
  }

  // ----- NETWORK (radial static) -----
  // ----- NETWORK (radial static) -----
  // v4.4.4: 작은 노드 (색만) + 외부 라벨 (각도별 placement) — JPM 풍.
  //         한국어 라벨이 노드 안에 안 들어가는 CHART-AP-1 후속 이슈 해결.
  //         link type legend 추가 — 선 의미 (대립/영향/연관) 명시.
  function drawNetwork(stage, payload, t) {
    const nodes = (payload.data && payload.data.nodes) || [];
    const links = (payload.data && payload.data.links) || [];
    if (nodes.length < 2) return;
    const W = 640, H = 400;
    const zones = computeZones(W, H, { left: 16, right: 140, top: 16, bottom: 16 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;

    // group → 시각 스타일 매핑 (v4.4.2 와 동일)
    const SEMANTIC_STYLES = {
      approve: { kind: 'solid',   fill: t.accent,                       stroke: t.text,  strokeStyle: null   },
      review:  { kind: 'pattern', fill: `url(#${idp('accent-hatch')})`, stroke: t.text,  strokeStyle: null   },
      oppose:  { kind: 'open',    fill: t.bg,                           stroke: t.down,  strokeStyle: 'solid' },
      informal:{ kind: 'pattern', fill: `url(#${idp('dots')})`,         stroke: t.text,  strokeStyle: null   },
      other:   { kind: 'muted',   fill: t.card,                         stroke: t.muted, strokeStyle: 'dashed'},
    };
    function classify(group) {
      const g = String(group || '').toLowerCase();
      if (/승인|찬성|동맹|approve|support|ally|core/.test(g)) return 'approve';
      if (/검토|중립|관망|review|neutral|considering/.test(g)) return 'review';
      if (/반대|대립|적|oppose|against|hostile/.test(g)) return 'oppose';
      if (/비공식|간접|informal|covert|indirect/.test(g)) return 'informal';
      return null;
    }
    const groupOrder = [];
    const groupClass = {};
    nodes.forEach(n => {
      const g = String(n.group || '_default');
      if (groupClass[g]) return;
      const sem = classify(g);
      if (sem) {
        groupClass[g] = sem;
      } else {
        const fallbackOrder = ['approve', 'review', 'oppose', 'informal', 'other'];
        const used = new Set(Object.values(groupClass));
        const next = fallbackOrder.find(s => !used.has(s)) || 'other';
        groupClass[g] = next;
      }
      groupOrder.push(g);
    });

    const cx = zones.data.x + zones.data.w / 2;
    const cy = zones.data.y + zones.data.h / 2;
    const r = Math.min(zones.data.w, zones.data.h) * 0.40;
    nodes.forEach((n, i) => {
      const ang = -Math.PI / 2 + (2 * Math.PI * i / nodes.length);
      n._x = cx + r * Math.cos(ang);
      n._y = cy + r * Math.sin(ang);
      n._ang = ang;
    });
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));

    // Render links first (behind)
    links.forEach(l => {
      const a = byId[l.source], b = byId[l.target];
      if (!a || !b) return;
      const lt = String(l.type || '').toLowerCase();
      const dash = (lt.includes('대립') || lt.includes('conflict')) ? '5,3'
        : (lt.includes('영향') || lt.includes('influence')) ? '2,3'
        : null;
      svg.append('line').attr('x1', a._x).attr('y1', a._y).attr('x2', b._x).attr('y2', b._y)
        .attr('stroke', t.text).attr('stroke-width', 1.2).attr('stroke-opacity', 0.55)
        .attr('stroke-dasharray', dash);
    });

    // Render nodes (small dots) + external labels (angular placement, no overflow)
    const nodeR = 10;
    nodes.forEach(n => {
      const sem = groupClass[String(n.group || '_default')] || 'other';
      const style = SEMANTIC_STYLES[sem];
      const c = svg.append('circle').attr('cx', n._x).attr('cy', n._y).attr('r', nodeR)
        .attr('fill', style.fill).attr('stroke', style.stroke);
      if (style.kind === 'open') {
        c.attr('stroke-width', 1.6);
      } else if (style.strokeStyle === 'dashed') {
        c.attr('stroke-width', 0.9).attr('stroke-dasharray', '3,2');
      } else {
        c.attr('stroke-width', 0.8);
      }
      // External label: angular placement based on node's position relative to center
      // Right half: anchor=start (label to right of node)
      // Left half: anchor=end (label to left)
      const labelText = String(n.label || n.id || '').slice(0, 8);
      const isRight = Math.cos(n._ang) >= 0;
      const lx = n._x + (isRight ? nodeR + 6 : -(nodeR + 6));
      const ly = n._y + 4;
      svg.append('text').attr('x', lx).attr('y', ly)
        .attr('text-anchor', isRight ? 'start' : 'end')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .attr('font-weight', sem === 'approve' ? 700 : 500)
        .attr('fill', t.text).text(labelText);
    });

    // Legend in right zone — group + link type
    const legendX = W - 130;
    let legendY = 24;
    svg.append('text').attr('x', legendX).attr('y', legendY)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
      .attr('font-weight', 700).attr('fill', t.text).text('진영');
    legendY += 18;
    groupOrder.forEach(g => {
      const sem = groupClass[g];
      const style = SEMANTIC_STYLES[sem];
      const swc = svg.append('circle').attr('cx', legendX + 7).attr('cy', legendY - 3).attr('r', 6)
        .attr('fill', style.fill).attr('stroke', style.stroke);
      if (style.kind === 'open') swc.attr('stroke-width', 1.4);
      else if (style.strokeStyle === 'dashed') swc.attr('stroke-width', 0.8).attr('stroke-dasharray', '2,1');
      else swc.attr('stroke-width', 0.6);
      svg.append('text').attr('x', legendX + 20).attr('y', legendY)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.text)
        .text(String(g).slice(0, 12));
      legendY += 17;
    });

    // Link type legend (only if multiple types observed)
    const linkTypes = new Set(links.map(l => String(l.type || '').toLowerCase()));
    const linkLegendItems = [];
    let hasConflict = false, hasInfluence = false, hasOther = false;
    linkTypes.forEach(lt => {
      if (lt.includes('대립') || lt.includes('conflict')) hasConflict = true;
      else if (lt.includes('영향') || lt.includes('influence')) hasInfluence = true;
      else if (lt) hasOther = true;
    });
    if (hasConflict || hasInfluence || hasOther) {
      legendY += 8;
      svg.append('text').attr('x', legendX).attr('y', legendY)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .attr('font-weight', 700).attr('fill', t.text).text('관계');
      legendY += 16;
      const linkLegend = (label, dash) => {
        svg.append('line').attr('x1', legendX).attr('y1', legendY - 3)
          .attr('x2', legendX + 18).attr('y2', legendY - 3)
          .attr('stroke', t.text).attr('stroke-width', 1.2).attr('stroke-opacity', 0.7)
          .attr('stroke-dasharray', dash);
        svg.append('text').attr('x', legendX + 24).attr('y', legendY)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.text)
          .text(label);
        legendY += 16;
      };
      if (hasConflict)  linkLegend('대립', '5,3');
      if (hasInfluence) linkLegend('영향', '2,3');
      if (hasOther)     linkLegend('연관', null);
    }
  }


  // ----- STACKED (positive magnitude only — composer prompt enforces) -----
  // ----- STACKED (positive magnitude only) -----
  // v4.4.2: 모든 row 의 unique segment.label 을 모아 *하단 자동 legend* 추가.
  //         같은 label 은 같은 fill 일관 적용 (이전엔 row 안 k 인덱스로 row 간 fill 불일치).
  function drawStacked(stage, payload, t) {
    const rows = (payload.data && payload.data.scenarios) || [];
    if (!rows.length) return;
    // Pre-pass: collect unique segment labels in encounter order → consistent fill mapping
    const labelOrder = [];
    rows.forEach(r => (r.segments || []).forEach(s => {
      const lbl = String(s.label || '').trim();
      if (lbl && labelOrder.indexOf(lbl) === -1) labelOrder.push(lbl);
    }));
    const labelToIndex = Object.fromEntries(labelOrder.map((l, i) => [l, i]));

    const W = 720;
    const rowH = 30;
    const legendH = labelOrder.length > 0 ? 30 : 0;
    const H = 56 + 32 + (rows.length * rowH) + 8 + legendH;
    const zones = computeZones(W, H, { left: 130, right: 50, bottom: 32 + legendH });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;

    function fillForLabel(lbl) {
      const idx = labelToIndex[lbl] != null ? labelToIndex[lbl] : 0;
      if (idx === 0) return t.accent;
      return `url(#${idp(PATTERN_SEQ[(idx - 1) % PATTERN_SEQ.length])})`;
    }

    const rowAbsTotals = rows.map(r =>
      d3.sum((r.segments || []), s => Math.abs(+s.value || 0))
    );
    const maxTotal = d3.max(rowAbsTotals) || 1;
    rows.forEach((row, i) => {
      const y = zones.data.y + 4 + i * rowH;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text(String(row.name || '').slice(0, 18));
      let cur = zones.data.x;
      const totalW = zones.data.w;
      const segs = (row.segments || []).filter(s => Math.abs(+s.value || 0) > 1e-6);
      if (!segs.length) {
        svg.append('rect').attr('x', cur).attr('y', y).attr('width', totalW).attr('height', 16)
          .attr('fill', 'none').attr('stroke', t.muted).attr('stroke-width', 0.5)
          .attr('stroke-dasharray', '2,2');
        return;
      }
      segs.forEach((s) => {
        const v = +s.value || 0;
        const w = (Math.abs(v) / maxTotal) * totalW;
        const isNeg = v < 0;
        const fill = fillForLabel(String(s.label || '').trim());
        const rect = svg.append('rect').attr('x', cur).attr('y', y)
          .attr('width', Math.max(1, w)).attr('height', 16).attr('fill', fill);
        if (isNeg) {
          rect.attr('stroke', t.down).attr('stroke-width', 1).attr('stroke-dasharray', '3,2');
        } else {
          rect.attr('stroke', t.text).attr('stroke-width', 0.4);
        }
        cur += w;
      });
    });

    // Legend at bottom — unique labels with consistent fill
    if (labelOrder.length) {
      const legendY = zones.data.y + zones.data.h + 14;
      const legendStartX = zones.data.x;
      const itemSpacing = Math.min(140, (zones.data.w / Math.max(1, labelOrder.length)) - 4);
      labelOrder.forEach((lbl, i) => {
        const lx = legendStartX + i * itemSpacing;
        if (lx > zones.data.x + zones.data.w - 60) return;  // 너무 많으면 끊기
        svg.append('rect').attr('x', lx).attr('y', legendY - 9).attr('width', 14).attr('height', 10)
          .attr('fill', fillForLabel(lbl)).attr('stroke', t.text).attr('stroke-width', 0.4);
        svg.append('text').attr('x', lx + 18).attr('y', legendY)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 10).attr('fill', t.text)
          .text(lbl.slice(0, 14));
      });
    }
  }

  // ----- BUBBLE -----
  function drawBubble(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 600, H = 360;
    const zones = computeZones(W, H, { left: 50, right: 24, top: 28, bottom: 36 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    // v4.5.3 (CHART-AP-11): x/y 스케일 자동 감지. 이전엔 [0,1] 고정 — composer 가 0~5
    // / 0~100 으로 emit 시 모든 bubble 이 frame 밖. 이제 입력 extent 기반 + 0 포함
    // + 약간의 padding 으로 frame 안에 항상 들어옴.
    const xs = data.map(d => +d.x).filter(v => !isNaN(v));
    const ys = data.map(d => +d.y).filter(v => !isNaN(v));
    const xMin = xs.length ? Math.min(0, d3.min(xs)) : 0;
    const xMax = xs.length ? Math.max(d3.max(xs), xMin === 0 && d3.max(xs) === 0 ? 1 : d3.max(xs) * 1.05) : 1;
    const yMin = ys.length ? Math.min(0, d3.min(ys)) : 0;
    const yMax = ys.length ? Math.max(d3.max(ys), yMin === 0 && d3.max(ys) === 0 ? 1 : d3.max(ys) * 1.05) : 1;
    const x = d3.scaleLinear().domain([xMin, xMax]).range([zones.data.x, zones.data.x + zones.data.w]);
    const y = d3.scaleLinear().domain([yMin, yMax]).range([zones.data.y + zones.data.h, zones.data.y]);
    // size 도 robust — 0~1 가정이지만 1 초과해도 정규화
    const sizes = data.map(d => +(d.size || 0)).filter(v => !isNaN(v) && v > 0);
    const sMax = sizes.length ? Math.max(...sizes, 1) : 1;
    // Axes labels
    svg.append('text').attr('x', zones.data.x + zones.data.w / 2).attr('y', H - 8).attr('text-anchor', 'middle')
      .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 10).text('확률 →');
    svg.append('text').attr('x', 14).attr('y', zones.data.y + zones.data.h / 2)
      .attr('transform', `rotate(-90, 14, ${zones.data.y + zones.data.h / 2})`)
      .attr('text-anchor', 'middle').attr('fill', t.muted)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).text('영향');
    // Frame
    svg.append('rect').attr('x', zones.data.x).attr('y', zones.data.y)
      .attr('width', zones.data.w).attr('height', zones.data.h)
      .attr('fill', 'none').attr('stroke', t.muted).attr('stroke-opacity', 0.3);
    const occupancy = renderAnnotations(svg, payload, zones, t, x, y);
    // Bubbles + smart label placement
    data.forEach(d => {
      const cx = x(+d.x), cy = y(+d.y);
      const sNorm = (+(d.size || 0.5)) / sMax;  // 0~1 정규화
      const r = 6 + 16 * Math.min(1, Math.max(0, sNorm));
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', r)
        .attr('fill', t.accent).attr('fill-opacity', 0.5).attr('stroke', t.text).attr('stroke-width', 0.8);
      const lbl = String(d.label || '').slice(0, 10);
      const labelW = lbl.length * 6;
      const candidates = [
        { x: cx + r + 4, y: cy - 4 },
        { x: cx - r - 4 - labelW, y: cy - 4 },
        { x: cx - labelW / 2, y: cy + r + 14 },
      ];
      let placed = candidates[0];
      for (const c of candidates) {
        if (c.x >= zones.data.x && c.x + labelW <= zones.data.x + zones.data.w &&
            c.y >= zones.data.y && c.y + 12 <= zones.data.y + zones.data.h &&
            !occupancy.hits(c.x, c.y, labelW, 12)) {
          placed = c;
          break;
        }
      }
      svg.append('text').attr('x', placed.x).attr('y', placed.y + 8)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.text)
        .text(lbl);
      occupancy.add(placed.x, placed.y, labelW, 12);
    });
  }

  // ----- HEATMAP -----
  function drawHeatmap(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 720;
    const rowH = 24;
    const H = 56 + (data.length * rowH) + 24;
    const zones = computeZones(W, H, { left: 140, right: 60, bottom: 24 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    data.forEach((d, i) => {
      const y = zones.data.y + 4 + i * rowH;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 13).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text(String(d.title || '').slice(0, 22));
      const sev = String(d.severity || 'low').toLowerCase();
      const fill = sev === 'high' ? `url(#${idp('hatch-tight')})`
        : sev === 'medium' ? `url(#${idp('hatch-wide')})`
        : `url(#${idp('dots')})`;
      svg.append('rect').attr('x', zones.data.x).attr('y', y)
        .attr('width', zones.data.w).attr('height', 16)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.4);
      svg.append('text').attr('x', zones.data.x + zones.data.w + 6).attr('y', y + 13)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(sev.toUpperCase());
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
    const lineL = d3.line().x(d => x(String(d.x))).y(d => yL(+d.y)).curve(d3.curveMonotoneX);
    const lineR = d3.line().x(d => x(String(d.x))).y(d => yR(+d.y)).curve(d3.curveMonotoneX);
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
    const yMin = d3.min(forecast, d => +d.low) ?? d3.min(actual, d => +d.y);
    const yMax = d3.max(forecast, d => +d.high) ?? d3.max(actual, d => +d.y);
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

    // Forecast cone (low~high) — render before lines so it's behind
    if (forecast.length) {
      const area = d3.area().x(d => x(String(d.x)))
        .y0(d => y(+d.low)).y1(d => y(+d.high)).curve(d3.curveMonotoneX);
      svg.append('path').attr('d', area(forecast))
        .attr('fill', t.accent).attr('fill-opacity', 0.15);
    }

    // Actual line
    const lineA = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    svg.append('path').attr('d', lineA(actual)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.6);
    // Forecast (mid) dashed line
    if (forecast.length) {
      const lineF = d3.line().x(d => x(String(d.x))).y(d => y(+d.mid)).curve(d3.curveMonotoneX);
      svg.append('path').attr('d', lineF(forecast)).attr('fill', 'none')
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
  // Dispatcher
  // ============================================================
  const RENDERERS = {
    bar: drawBar, donut: drawDonut, line: drawLine, gantt: drawGantt,
    network: drawNetwork, stacked: drawStacked, bubble: drawBubble, heatmap: drawHeatmap,
    dual_line: drawDualLine, forecast: drawForecast, choropleth: drawChoropleth,
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

  function init() {
    const stages = document.querySelectorAll('.chart-card-stage[data-chart-type]');
    stages.forEach((stage, i) => renderStage(stage, i));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
