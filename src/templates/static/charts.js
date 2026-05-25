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
    // v5.2.11: 값 포맷 통일 — 축 tick 과 막대 라벨이 같은 포맷. 천 단위 구분 +
    // |v| 규모별 소수점 자동 (≥100 정수 / ≥10 .1f / 그 외 .2f). 부호 보존.
    const fmt = (v) => {
      const av = Math.abs(+v);
      if (av >= 100) return d3.format(',.0f')(+v);
      if (av >= 10) return d3.format(',.1f')(+v);
      return d3.format(',.2f')(+v);
    };
    // v5.2.11: 라벨 22자 초과면 ellipsis (이전엔 무음 truncate — 잘림 인지 X).
    const truncLabel = (s) => {
      const str = String(s || '');
      return str.length > 22 ? str.slice(0, 21) + '…' : str;
    };

    // Bars + smart label placement
    data.forEach((d, i) => {
      const y = zones.data.y + 4 + i * rowH;
      const x0 = zones.data.x;
      const x1 = xScale(d.value);
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('text').attr('x', zones.data.x - 8).attr('y', y + 13).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .text(truncLabel(d.label));
      // v5.2.11: 0/극소값도 시각적 흔적 — 최소 2px 너비 floor (이전엔 막대가 사라져
      // 빈 행처럼 보임).
      const barW = Math.max(2, x1 - x0);
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', barW).attr('height', 16)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', i === 0 ? 0 : 0.4)
        .attr('data-anim', 'bar-grow').attr('data-final-w', barW);
      // v5.2.11: 값 라벨도 fmt 적용. 이전엔 raw String(d.value) → "13567",
      // 축은 "13,567" → 같은 차트 안에서 포맷 불일치 회귀.
      const labelText = fmt(d.value);
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

    // X axis — fmt 로 막대 라벨과 동일 포맷.
    svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
      .attr('y1', H - zones.bottom + 4).attr('y2', H - zones.bottom + 4)
      .attr('stroke', t.muted).attr('stroke-opacity', 0.4).attr('stroke-width', 0.5);
    [0, 0.25, 0.5, 0.75, 1].forEach(p => {
      const x = zones.data.x + p * zones.data.w;
      svg.append('text').attr('x', x).attr('y', H - zones.bottom + 18).attr('text-anchor', 'middle')
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).attr('fill', t.muted)
        .text(fmt(p * max));
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
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.5)
        .attr('data-anim', 'donut-arc')
        .attr('data-start', a.startAngle).attr('data-end', a.endAngle);
    });
    // v5.3.1 — entry 애니메이션 (arc sweep) 재구성용 geometry 메타.
    // _applyEntryAnimation 이 arcGen 을 다시 빚어 attrTween('d') 수행.
    svg.attr('data-donut-cx', cx).attr('data-donut-cy', cy)
      .attr('data-donut-ir', ir).attr('data-donut-r', r);
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

    const line = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    const area = d3.area().x(d => x(String(d.x))).y0(zones.data.y + zones.data.h)
      .y1(d => y(+d.y)).curve(d3.curveMonotoneX);
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

  // ----- NETWORK → adjacency matrix (v5.5.5) -----
  // 행위자 관계도. radial hairball (CHART-AP-25) 폐기 → 인접행렬.
  //   · 데이터 계약 (nodes/links) 동일 — composer/스키마/레지스트리 무변경.
  //   · 셀이 관계 type 인코딩 (대립/동맹/영향/연관), 대각선 차단.
  //   · 진영(group) 으로 정렬해 같은 진영이 대각선 근처에 블록으로 모임.
  //   · viewBox 는 getBBox content-fit → 자동 중앙 정렬 + 라벨/범례 클리핑 0.
  function drawNetwork(stage, payload, t) {
    const rawNodes = (payload.data && payload.data.nodes) || [];
    const links = (payload.data && payload.data.links) || [];
    if (rawNodes.length < 2) return;

    const svg = d3.select(stage).select('svg')
      .attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    const idp = definePatterns(svg, t, prefix);

    // group → 진영 rank (정렬용). 같은 진영을 대각선 근처에 모은다.
    function nodeRank(group) {
      const g = String(group || '').toLowerCase();
      if (/승인|찬성|주도|동맹|approve|support|ally|core|lead/.test(g)) return 0;
      if (/검토|중립|관망|review|neutral|considering/.test(g)) return 1;
      if (/반대|대립|적|oppose|against|hostile/.test(g)) return 2;
      if (/비공식|간접|informal|covert|indirect/.test(g)) return 3;
      return 4;
    }
    const nodes = rawNodes
      .map((nd, i) => ({ nd, i, rank: nodeRank(nd.group) }))
      .sort((a, b) => a.rank - b.rank || a.i - b.i)
      .map(o => o.nd);
    const n = nodes.length;

    // 관계 type → 시각 클래스
    function linkClass(type) {
      const s = String(type || '').toLowerCase();
      if (/대립|충돌|갈등|적대|conflict|oppose|against|hostile|rival/.test(s)) return 'conflict';
      if (/동맹|협력|지지|연합|제휴|ally|alliance|support|coop|partner/.test(s)) return 'ally';
      if (/영향|압박|의존|leverage|influence|pressure|depend/.test(s)) return 'influence';
      return 'assoc';
    }
    const idIndex = Object.fromEntries(nodes.map((nd, i) => [nd.id, i]));
    const rel = {}; // "r|c" → class (대칭)
    links.forEach(l => {
      const a = idIndex[l.source], b = idIndex[l.target];
      if (a == null || b == null || a === b) return;
      const cls = linkClass(l.type);
      rel[a + '|' + b] = cls;
      rel[b + '|' + a] = cls;
    });

    // 셀 글리프: mono 4종 구분 (solid down / solid accent / accent-hatch / dots)
    const GLYPH = {
      conflict:  { fill: t.down,                          mark: '✕' },
      ally:      { fill: t.accent },
      influence: { fill: `url(#${idp('accent-hatch')})`,  bordered: true },
      assoc:     { fill: `url(#${idp('dots')})`,           bordered: true },
    };

    // 셀 크기 적응 (그리드 폭 ~330 목표), 라벨 폰트 n 에 따라 축소
    const cell = Math.max(24, Math.min(46, Math.round(330 / n)));
    const fs = n > 9 ? 9.5 : 11;
    const labelOf = (nd) => String(nd.label || nd.id || '').slice(0, 14);

    // content 를 g 에 그린 뒤 getBBox 로 viewBox 산출 → 자동 중앙 정렬
    const root = svg.append('g');

    // 그리드 셀
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
      const X = cell * c, Y = cell * r;
      root.append('rect').attr('x', X).attr('y', Y).attr('width', cell).attr('height', cell)
        .attr('fill', 'none').attr('stroke', t.border).attr('stroke-width', 0.6);
      if (r === c) {
        root.append('rect').attr('x', X).attr('y', Y).attr('width', cell).attr('height', cell)
          .attr('fill', t.border).attr('fill-opacity', 0.35);
        continue;
      }
      const cls = rel[r + '|' + c];
      if (!cls) continue;
      const g = GLYPH[cls];
      const s = cell * 0.6, cxv = X + cell / 2, cyv = Y + cell / 2;
      const sq = root.append('rect').attr('x', cxv - s / 2).attr('y', cyv - s / 2)
        .attr('width', s).attr('height', s).attr('fill', g.fill);
      if (g.bordered) sq.attr('stroke', t.border).attr('stroke-width', 0.5);
      if (g.mark) {
        root.append('text').attr('x', cxv).attr('y', cyv + s * 0.34)
          .attr('text-anchor', 'middle').attr('font-family', 'Noto Sans KR')
          .attr('font-size', s * 0.6).attr('font-weight', 700).attr('fill', t.bg)
          .text(g.mark);
      }
    }

    // 라벨 — 행: 좌측 거터 우측정렬 / 열: -45° 회전 (위로)
    nodes.forEach((nd, i) => {
      const lbl = labelOf(nd);
      root.append('text').attr('x', -8).attr('y', cell * i + cell / 2 + fs * 0.35)
        .attr('text-anchor', 'end').attr('font-family', 'Noto Sans KR')
        .attr('font-size', fs).attr('fill', t.text).text(lbl);
      const cxl = cell * i + cell / 2, cyl = -8;
      root.append('text').attr('x', cxl).attr('y', cyl)
        .attr('text-anchor', 'start').attr('font-family', 'Noto Sans KR')
        .attr('font-size', fs).attr('fill', t.text)
        .attr('transform', `rotate(-45 ${cxl} ${cyl})`).text(lbl);
    });

    // 범례 — 실제 등장한 관계 type 만, 그리드 하단 중앙
    const seen = new Set(Object.values(rel));
    const present = [['conflict', '대립'], ['ally', '동맹'], ['influence', '영향'], ['assoc', '연관']]
      .filter(([k]) => seen.has(k));
    if (present.length) {
      const SW = 15, GAP = 6, ITEMGAP = 22, lgFs = 10.5;
      const lgY = cell * n + 30;
      const itemW = (label) => SW + GAP + label.length * lgFs * 0.95;
      const totalW = present.reduce((a, [, l]) => a + itemW(l) + ITEMGAP, -ITEMGAP);
      let lx = (cell * n) / 2 - totalW / 2;
      present.forEach(([k, label]) => {
        const g = GLYPH[k];
        const sw = root.append('rect').attr('x', lx).attr('y', lgY - SW + 3)
          .attr('width', SW).attr('height', SW).attr('fill', g.fill);
        if (g.bordered) sw.attr('stroke', t.border).attr('stroke-width', 0.5);
        if (g.mark) root.append('text').attr('x', lx + SW / 2).attr('y', lgY - SW / 2 + 4.5)
          .attr('text-anchor', 'middle').attr('font-size', SW * 0.62)
          .attr('font-weight', 700).attr('fill', t.bg).text(g.mark);
        root.append('text').attr('x', lx + SW + GAP).attr('y', lgY)
          .attr('font-family', 'Noto Sans KR').attr('font-size', lgFs).attr('fill', t.text)
          .text(label);
        lx += itemW(label) + ITEMGAP;
      });
    }

    // 정적 렌더 — 셀 fade 캐스케이드/opacity 덮어쓰기 방지 (CHART-AP-18 무관 안전)
    root.selectAll('rect').attr('data-anim', 'static');

    // content-fit viewBox: 모든 라벨/범례/회전 텍스트 포함 bbox + 패딩 → 중앙 정렬
    const bb = root.node().getBBox();
    const pad = 12;
    svg.attr('viewBox',
      `${bb.x - pad} ${bb.y - pad} ${bb.width + pad * 2} ${bb.height + pad * 2}`);
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
        .y0(d => y(+d.low)).y1(d => y(+d.high)).curve(d3.curveMonotoneX);
      svg.append('path').attr('d', area(forecastBridge))
        .attr('fill', t.accent).attr('fill-opacity', 0.15);
    }

    // Actual line
    const lineA = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    svg.append('path').attr('d', lineA(actual)).attr('fill', 'none')
      .attr('stroke', t.text).attr('stroke-width', 1.6);
    // Forecast (mid) dashed line — bridge prepended for visual continuity
    if (forecastBridge.length) {
      const lineF = d3.line().x(d => x(String(d.x))).y(d => y(+d.mid)).curve(d3.curveMonotoneX);
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

    // Gradient fill
    const gradId = `grad-area-${stage.getAttribute('data-chart-id') || Math.random().toString(36).slice(2,8)}`;
    const grad = svg.append('defs').append('linearGradient')
      .attr('id', gradId).attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 1);
    grad.append('stop').attr('offset', '0%').attr('stop-color', t.accent).attr('stop-opacity', 0.28);
    grad.append('stop').attr('offset', '100%').attr('stop-color', t.accent).attr('stop-opacity', 0.02);

    const lineGen = d3.line().x(d => x(String(d.x))).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    const areaGen = d3.area().x(d => x(String(d.x)))
      .y0(zones.data.y + zones.data.h).y1(d => y(+d.y)).curve(d3.curveMonotoneX);
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
    // points + labels
    data.forEach(d => {
      const cx = xScale(+d.x), cy = yScale(+d.y);
      const isAccent = !!d.accent;
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 5)
        .attr('fill', isAccent ? t.accent : t.text).attr('fill-opacity', 0.85);
      svg.append('text').attr('x', cx + 8).attr('y', cy + 4).attr('font-size', 10)
        .attr('font-family', 'Noto Sans KR').attr('fill', isAccent ? t.accent : t.text)
        .text(String(d.label || ''));
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
      .curve(d3.curveMonotoneX);
    // grid
    yScale.ticks(5).forEach(yt => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yScale(yt)).attr('y2', yScale(yt))
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
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
    const H = 50 + data.length * rowH + 30;
    const zones = computeZones(W, H, { left: 160, right: 60, top: 24, bottom: 30 });
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
    items.forEach(it => {
      const yA = yScale(+it.a), yB = yScale(+it.b);
      const rising = +it.b > +it.a;
      const stroke = rising ? t.accent : t.muted;
      svg.append('line').attr('x1', xA).attr('y1', yA).attr('x2', xB).attr('y2', yB)
        .attr('stroke', stroke).attr('stroke-width', 1.4);
      svg.append('circle').attr('cx', xA).attr('cy', yA).attr('r', 4).attr('fill', t.text);
      svg.append('circle').attr('cx', xB).attr('cy', yB).attr('r', 4)
        .attr('fill', rising ? t.accent : t.text);
      svg.append('text').attr('x', xA - 10).attr('y', yA + 4).attr('text-anchor', 'end')
        .attr('font-size', 11).attr('fill', t.text)
        .text(`${it.label} ${d3.format(',.1f')(+it.a)}`);
      svg.append('text').attr('x', xB + 10).attr('y', yB + 4).attr('font-size', 11)
        .attr('fill', rising ? t.accent : t.text).text(d3.format(',.1f')(+it.b));
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
      const line = d3.line().x(d => xScale(+d.x)).y(d => yScale(+d.y)).curve(d3.curveMonotoneX);
      svg.append('path').datum(data).attr('fill', 'none')
        .attr('stroke', t.text).attr('stroke-width', 1.4).attr('d', line);
    });
  }

  // ----- WATERFALL (P&L 스타일) -----
  function drawWaterfall(stage, payload, t) {
    const items = (payload.data || []).slice();
    if (items.length < 3) return;
    if (items[0].type !== 'total' || items[items.length - 1].type !== 'total') return;
    // compute baselines
    let running = 0;
    items.forEach(it => {
      if (it.type === 'total') { it.y0 = 0; it.y1 = +it.value; running = +it.value; }
      else if (+it.value >= 0) { it.y0 = running; it.y1 = running + (+it.value); running = it.y1; }
      else { it.y0 = running + (+it.value); it.y1 = running; running = it.y0; }
    });
    const W = 720, H = 360;
    const zones = computeZones(W, H, { left: 60, right: 30, top: 24, bottom: 80 });
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const xScale = d3.scaleBand().domain(items.map((d, i) => i)).range([zones.data.x, zones.data.x + zones.data.w]).padding(0.3);
    const yMax = d3.max(items, d => Math.max(d.y0, d.y1)) * 1.1;
    const yScale = d3.scaleLinear().domain([0, yMax]).range([zones.data.y + zones.data.h, zones.data.y]);
    yScale.ticks(5).forEach(yt => {
      svg.append('line').attr('x1', zones.data.x).attr('x2', zones.data.x + zones.data.w)
        .attr('y1', yScale(yt)).attr('y2', yScale(yt))
        .attr('stroke', t.border).attr('stroke-opacity', 0.35).attr('stroke-dasharray', '2 3');
    });
    items.forEach((it, i) => {
      const fill = it.type === 'total' ? t.text : (it.type === 'pos' ? t.accent : t.muted);
      svg.append('rect').attr('x', xScale(i)).attr('width', xScale.bandwidth())
        .attr('y', yScale(it.y1)).attr('height', yScale(it.y0) - yScale(it.y1))
        .attr('fill', fill).attr('fill-opacity', it.type === 'total' ? 1 : 0.85);
      // value label above bar
      svg.append('text').attr('x', xScale(i) + xScale.bandwidth() / 2)
        .attr('y', yScale(it.y1) - 4).attr('text-anchor', 'middle')
        .attr('font-size', 10).attr('font-weight', 700).attr('fill', t.text)
        .text(d3.format(',.0f')(+it.value));
      // connector to next
      if (i < items.length - 1) {
        svg.append('line').attr('x1', xScale(i) + xScale.bandwidth())
          .attr('x2', xScale(i + 1))
          .attr('y1', yScale(it.y1)).attr('y2', yScale(it.y1))
          .attr('stroke', t.muted).attr('stroke-dasharray', '2 3').attr('stroke-width', 0.8);
      }
    });
    // x labels (rotated)
    items.forEach((it, i) => {
      svg.append('text').attr('x', xScale(i) + xScale.bandwidth() / 2)
        .attr('y', zones.data.y + zones.data.h + 14)
        .attr('text-anchor', 'end').attr('font-size', 10).attr('fill', t.muted)
        .attr('transform', `rotate(-25 ${xScale(i) + xScale.bandwidth() / 2},${zones.data.y + zones.data.h + 14})`)
        .text(String(it.label || '').slice(0, 18));
    });
    // y axis
    svg.append('g').attr('transform', `translate(${zones.data.x},0)`)
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll('text').attr('fill', t.muted).attr('font-size', 10);
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
    nodes.forEach(n => {
      nodeG.append('rect')
        .attr('x', n.x0).attr('y', n.y0)
        .attr('width', n.x1 - n.x0).attr('height', n.height)
        .attr('fill', n.color)
        .attr('fill-opacity', n.accent ? ACCENT_OPACITY : NODE_OPACITY);
      // 라벨 — 첫 컬럼은 노드 왼쪽 / 마지막 컬럼은 노드 오른쪽 / 그 외는 위쪽.
      // accent 노드는 weight 700, 일반은 500 (이전 600 → 정류장 격하).
      const labelText = String(n.label || n.id);
      const valueText = n.value_label || (n.outValue > 0
        ? d3.format(',.1f')(n.outValue)
        : (n.inValue > 0 ? d3.format(',.1f')(n.inValue) : ''));
      const isFirst = n.col === 0;
      const isLast = n.col === maxCol;
      const labelWeight = n.accent ? 700 : 500;
      if (isFirst) {
        nodeG.append('text').attr('x', n.x0 - 6).attr('y', n.y0 + n.height / 2 - 2)
          .attr('text-anchor', 'end').attr('font-size', 11)
          .attr('font-family', 'Noto Sans KR').attr('fill', t.text)
          .attr('font-weight', labelWeight).text(labelText);
        if (valueText) {
          nodeG.append('text').attr('x', n.x0 - 6).attr('y', n.y0 + n.height / 2 + 12)
            .attr('text-anchor', 'end').attr('font-size', 10)
            .attr('fill', t.muted).text(valueText);
        }
      } else if (isLast) {
        nodeG.append('text').attr('x', n.x1 + 6).attr('y', n.y0 + n.height / 2 - 2)
          .attr('font-size', 11).attr('font-family', 'Noto Sans KR')
          .attr('fill', t.text)
          .attr('font-weight', labelWeight).text(labelText);
        if (valueText) {
          nodeG.append('text').attr('x', n.x1 + 6).attr('y', n.y0 + n.height / 2 + 12)
            .attr('font-size', 10).attr('fill', t.muted).text(valueText);
        }
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
  }

  // ----- RANGE BAR (Dumbbell) -----
  function drawRangeBar(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.low) && isFinite(+d.high) && +d.low < +d.high);
    if (data.length < 3 || data.length > 15) return;
    const W = 720, rowH = 26;
    const H = 50 + data.length * rowH + 40;
    const zones = computeZones(W, H, { left: 140, right: 60, top: 24, bottom: 30 });
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
  // Dispatcher
  // ============================================================
  const RENDERERS = {
    bar: drawBar, donut: drawDonut, line: drawLine, gantt: drawGantt,
    network: drawNetwork, stacked: drawStacked, bubble: drawBubble, heatmap: drawHeatmap,
    dual_line: drawDualLine, forecast: drawForecast, choropleth: drawChoropleth,
    // v5.2.0 — 시계열 OHLC 차트 (market_fetcher 데이터)
    candle: drawCandle, area: drawArea,
    // v5.2.14 — FT/Economist 스타일 신규 7종
    scatter: drawScatter, stacked_area: drawStackedArea, lollipop: drawLollipop,
    slope: drawSlope, small_multiples: drawSmallMultiples,
    waterfall: drawWaterfall, range_bar: drawRangeBar,
    // v5.3.0 — Sankey (재무 분해 / 자본 배분). orphan 해결.
    sankey: drawSankey,
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
