/* charts.js — v4.2.0 inline composer-emitted charts.
 *
 * v3.2.0~v4.1.0 의 chart-payload 전역 단일 객체 + auto-init by element id 패턴
 * 폐기. freeform_essay.html 이 섹션마다 chart-card 를 emit 하고 각각
 * <script class="chart-payload-inline" type="application/json"> 안에 단일 차트
 * 데이터를 담는다. 본 모듈은 그 컨테이너를 모두 찾아 SVG 로 렌더한다.
 *
 * Mono Theme: docs/MONO_THEME_GUIDE.md §4 패턴 시스템 적용.
 *   - 사선은 45° 한 방향만 (cross-hatch / 반대방향 금지 — anti-pattern §6)
 *   - 카테고리는 hue 차이가 아닌 패턴 (hatch-tight / hatch-wide / dots / accent solid)
 *   - 큰 숫자에 액센트 색 금지 (--text 만)
 */
(function () {
  if (!window.d3) { console.warn('[charts] d3 not loaded'); return; }
  const d3 = window.d3;

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

  // 핵심 항목(0) = accent solid, 그 외는 패턴 순환 (mono guide §4.2)
  const PATTERN_SEQ = ['hatch-tight', 'accent-hatch', 'hatch-wide', 'dots'];
  function fillFor(idp, t, i) {
    if (i === 0) return t.accent;
    return `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
  }

  // ===== BAR =====
  function drawBar(stage, payload, t, idp) {
    const data = (payload.data || []).filter(d => isFinite(+d.value));
    if (!data.length) return;
    const W = 360, H = Math.max(120, 28 + data.length * 28);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    definePatterns(svg, t, stage.getAttribute('data-chart-id') || 'pat');
    const idp2 = (n) => `${stage.getAttribute('data-chart-id') || 'pat'}-${n}`;
    const max = d3.max(data, d => +d.value) || 1;
    const labelW = 90, padR = 30;
    const barW = W - labelW - padR;
    data.forEach((d, i) => {
      const y = 14 + i * 28;
      const w = (+d.value / max) * barW;
      svg.append('text').attr('x', labelW - 8).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .text(d.label || '');
      const fill = i === 0 ? t.accent : `url(#${idp2(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('rect').attr('x', labelW).attr('y', y).attr('width', w).attr('height', 14)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', i === 0 ? 0 : 0.4);
      svg.append('text').attr('x', labelW + w + 4).attr('y', y + 11)
        .attr('fill', t.text).attr('font-family', 'Noto Serif KR').attr('font-size', 11)
        .attr('font-weight', 700).text(d.value);
    });
  }

  // ===== DONUT =====
  function drawDonut(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.value) && +d.value > 0);
    if (data.length < 3) return;
    const W = 360, H = 220;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    const cx = 110, cy = H / 2, r = 80, ir = 50;
    const total = d3.sum(data, d => +d.value);
    const pie = d3.pie().value(d => +d.value).sort(null);
    const arc = d3.arc().innerRadius(ir).outerRadius(r);
    pie(data).forEach((a, i) => {
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('path').attr('d', arc(a)).attr('transform', `translate(${cx},${cy})`)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.5);
    });
    const lx = 220, ly = 30;
    data.forEach((d, i) => {
      const y = ly + i * 22;
      const fill = i === 0 ? t.accent : `url(#${idp(PATTERN_SEQ[(i - 1) % PATTERN_SEQ.length])})`;
      svg.append('rect').attr('x', lx).attr('y', y - 8).attr('width', 14).attr('height', 10)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.4);
      svg.append('text').attr('x', lx + 20).attr('y', y).attr('fill', t.text)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
        .text(`${d.label}  ${(+d.value / total * 100).toFixed(0)}%`);
    });
  }

  // ===== LINE (with optional events) =====
  function drawLine(stage, payload, t) {
    const data = (payload.data || []).filter(d => isFinite(+d.y));
    if (data.length < 2) return;
    const W = 360, H = 200;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const m = { t: 18, r: 16, b: 32, l: 38 };
    const cw = W - m.l - m.r, ch = H - m.t - m.b;
    const x = d3.scalePoint().domain(data.map(d => d.x)).range([m.l, m.l + cw]).padding(0.2);
    const yExtent = d3.extent(data, d => +d.y);
    const yPad = (yExtent[1] - yExtent[0]) * 0.1 || 1;
    const y = d3.scaleLinear().domain([yExtent[0] - yPad, yExtent[1] + yPad]).range([m.t + ch, m.t]);
    y.ticks(4).forEach(v => {
      svg.append('line').attr('x1', m.l).attr('x2', m.l + cw).attr('y1', y(v)).attr('y2', y(v))
        .attr('stroke', t.muted).attr('stroke-opacity', 0.25).attr('stroke-width', 0.5);
      svg.append('text').attr('x', m.l - 4).attr('y', y(v) + 3).attr('text-anchor', 'end')
        .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 9).text(v);
    });
    const line = d3.line().x(d => x(d.x)).y(d => y(+d.y)).curve(d3.curveMonotoneX);
    const area = d3.area().x(d => x(d.x)).y0(m.t + ch).y1(d => y(+d.y)).curve(d3.curveMonotoneX);
    svg.append('path').attr('d', area(data)).attr('fill', t.accent).attr('fill-opacity', 0.10);
    svg.append('path').attr('d', line(data)).attr('fill', 'none').attr('stroke', t.text).attr('stroke-width', 1.4);
    const last = data[data.length - 1];
    svg.append('circle').attr('cx', x(last.x)).attr('cy', y(+last.y)).attr('r', 3).attr('fill', t.accent);
    svg.append('text').attr('x', x(last.x) + 6).attr('y', y(+last.y) + 4).attr('fill', t.text)
      .attr('font-family', 'Noto Serif KR').attr('font-size', 11).attr('font-weight', 700).text(last.y);
    const step = Math.max(1, Math.ceil(data.length / 6));
    data.forEach((d, i) => {
      if (i % step !== 0 && i !== data.length - 1) return;
      svg.append('text').attr('x', x(d.x)).attr('y', m.t + ch + 14).attr('text-anchor', 'middle')
        .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 9).text(d.x);
    });
    data.filter(d => d.event).forEach(d => {
      svg.append('line').attr('x1', x(d.x)).attr('x2', x(d.x)).attr('y1', m.t).attr('y2', m.t + ch)
        .attr('stroke', t.down).attr('stroke-width', 0.8).attr('stroke-dasharray', '3,3');
      svg.append('text').attr('x', x(d.x) + 4).attr('y', m.t + 8).attr('fill', t.down)
        .attr('font-family', 'Noto Sans KR').attr('font-size', 9).text(d.event);
    });
  }

  // ===== GANTT =====
  function drawGantt(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 360, H = Math.max(120, 24 + data.length * 22);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const labelW = 110;
    const min = d3.min(data, d => +d.start), max = d3.max(data, d => +d.end || +d.start + 1);
    const xScale = d3.scaleLinear().domain([min, max]).range([labelW + 4, W - 12]);
    data.forEach((d, i) => {
      const y = 12 + i * 22;
      svg.append('text').attr('x', labelW - 6).attr('y', y + 10).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text((d.label || '').slice(0, 16));
      const x0 = xScale(+d.start), x1 = xScale(+(d.end || d.start + 1));
      svg.append('rect').attr('x', x0).attr('y', y).attr('width', Math.max(2, x1 - x0)).attr('height', 12)
        .attr('fill', t.accent).attr('rx', 1.5);
      if (d.note) {
        svg.append('text').attr('x', x1 + 4).attr('y', y + 9).attr('fill', t.muted)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 9).text(d.note);
      }
    });
  }

  // ===== NETWORK (radial static layout) =====
  function drawNetwork(stage, payload, t) {
    const nodes = (payload.data && payload.data.nodes) || [];
    const links = (payload.data && payload.data.links) || [];
    if (nodes.length < 2) return;
    const W = 360, H = 240;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const cx = W / 2, cy = H / 2, r = Math.min(W, H) * 0.32;
    nodes.forEach((n, i) => {
      const ang = -Math.PI / 2 + (2 * Math.PI * i / nodes.length);
      n._x = cx + r * Math.cos(ang);
      n._y = cy + r * Math.sin(ang);
    });
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    links.forEach(l => {
      const a = byId[l.source], b = byId[l.target];
      if (!a || !b) return;
      const lt = (l.type || '').toLowerCase();
      const dash = (lt.includes('대립') || lt.includes('conflict')) ? '5,3'
        : (lt.includes('영향') || lt.includes('influence')) ? '2,3'
        : null;
      svg.append('line').attr('x1', a._x).attr('y1', a._y).attr('x2', b._x).attr('y2', b._y)
        .attr('stroke', t.text).attr('stroke-width', 1.2).attr('stroke-opacity', 0.7)
        .attr('stroke-dasharray', dash);
    });
    nodes.forEach(n => {
      svg.append('circle').attr('cx', n._x).attr('cy', n._y).attr('r', 14)
        .attr('fill', t.accent).attr('stroke', t.text).attr('stroke-width', 0.8);
      svg.append('text').attr('x', n._x).attr('y', n._y + 4).attr('text-anchor', 'middle')
        .attr('fill', t.bg).attr('font-family', 'Noto Sans KR').attr('font-size', 9)
        .attr('font-weight', 700).text((n.label || n.id || '').slice(0, 4));
    });
  }

  // ===== STACKED =====
  // v4.2.1: 음수 / 0 robust 처리. composer 가 ±N 정성 점수로 emit 해도 깨지지 않음.
  // 음수 segment 는 절댓값으로 width 계산 + dashed 보더로 시각 구분.
  function drawStacked(stage, payload, t) {
    const rows = (payload.data && payload.data.scenarios) || [];
    if (!rows.length) return;
    const W = 360, H = Math.max(120, 24 + rows.length * 28);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    const labelW = 90;
    // 모든 row 의 절댓값 합산으로 maxTotal 결정 (음수 포함 robust).
    const rowAbsTotals = rows.map(r =>
      d3.sum((r.segments || []), s => Math.abs(+s.value || 0))
    );
    const maxTotal = d3.max(rowAbsTotals) || 1;
    rows.forEach((row, i) => {
      const y = 12 + i * 28;
      svg.append('text').attr('x', labelW - 6).attr('y', y + 10).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text((row.name || '').slice(0, 14));
      let cur = labelW + 4;
      const totalW = W - cur - 16;
      const segs = (row.segments || []).filter(s => Math.abs(+s.value || 0) > 1e-6);
      if (!segs.length) {
        // 빈 row 표시 — dotted track
        svg.append('rect').attr('x', cur).attr('y', y).attr('width', totalW).attr('height', 14)
          .attr('fill', 'none').attr('stroke', t.muted).attr('stroke-width', 0.5)
          .attr('stroke-dasharray', '2,2');
        return;
      }
      segs.forEach((s, k) => {
        const v = +s.value || 0;
        const w = (Math.abs(v) / maxTotal) * totalW;
        const isNeg = v < 0;
        const fill = k === 0
          ? t.accent
          : `url(#${idp(PATTERN_SEQ[k % PATTERN_SEQ.length])})`;
        const rect = svg.append('rect').attr('x', cur).attr('y', y)
          .attr('width', Math.max(1, w)).attr('height', 14)
          .attr('fill', fill);
        if (isNeg) {
          // 음수 = dashed 보더로 시각 차별화
          rect.attr('stroke', t.down).attr('stroke-width', 1).attr('stroke-dasharray', '3,2');
        } else {
          rect.attr('stroke', t.text).attr('stroke-width', 0.4);
        }
        cur += w;
      });
    });
  }

  // ===== BUBBLE =====
  function drawBubble(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 360, H = 240;
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const m = { t: 18, r: 16, b: 28, l: 36 };
    const cw = W - m.l - m.r, ch = H - m.t - m.b;
    const x = d3.scaleLinear().domain([0, 1]).range([m.l, m.l + cw]);
    const y = d3.scaleLinear().domain([0, 1]).range([m.t + ch, m.t]);
    svg.append('text').attr('x', m.l + cw / 2).attr('y', H - 6).attr('text-anchor', 'middle')
      .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 10).text('확률 →');
    svg.append('text').attr('x', 6).attr('y', m.t + ch / 2).attr('transform', `rotate(-90, 12, ${m.t + ch / 2})`)
      .attr('text-anchor', 'middle').attr('fill', t.muted)
      .attr('font-family', 'Noto Sans KR').attr('font-size', 10).text('영향');
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', cw).attr('height', ch)
      .attr('fill', 'none').attr('stroke', t.muted).attr('stroke-opacity', 0.3);
    data.forEach(d => {
      const r = 6 + 12 * (+(d.size || 0.5));
      svg.append('circle').attr('cx', x(+d.x)).attr('cy', y(+d.y)).attr('r', r)
        .attr('fill', t.accent).attr('fill-opacity', 0.5).attr('stroke', t.text).attr('stroke-width', 0.8);
      svg.append('text').attr('x', x(+d.x)).attr('y', y(+d.y) + 3).attr('text-anchor', 'middle')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 9)
        .text((d.label || '').slice(0, 8));
    });
  }

  // ===== HEATMAP =====
  function drawHeatmap(stage, payload, t) {
    const data = (payload.data || []);
    if (!data.length) return;
    const W = 360, H = Math.max(80, 16 + data.length * 22);
    const svg = d3.select(stage).select('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    const prefix = stage.getAttribute('data-chart-id') || 'pat';
    definePatterns(svg, t, prefix);
    const idp = (n) => `${prefix}-${n}`;
    const labelW = 90;
    data.forEach((d, i) => {
      const y = 8 + i * 22;
      svg.append('text').attr('x', labelW - 6).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.text).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
        .text((d.title || '').slice(0, 14));
      const sev = (d.severity || 'low').toLowerCase();
      const fill = sev === 'high' ? `url(#${idp('hatch-tight')})`
        : sev === 'medium' ? `url(#${idp('hatch-wide')})`
        : `url(#${idp('dots')})`;
      svg.append('rect').attr('x', labelW).attr('y', y).attr('width', W - labelW - 12).attr('height', 14)
        .attr('fill', fill).attr('stroke', t.text).attr('stroke-width', 0.4);
      svg.append('text').attr('x', W - 16).attr('y', y + 11).attr('text-anchor', 'end')
        .attr('fill', t.muted).attr('font-family', 'Noto Sans KR').attr('font-size', 9)
        .text(sev.toUpperCase());
    });
  }

  const RENDERERS = {
    bar: drawBar, donut: drawDonut, line: drawLine, gantt: drawGantt,
    network: drawNetwork, stacked: drawStacked, bubble: drawBubble, heatmap: drawHeatmap,
  };

  function renderStage(stage, idx) {
    const card = stage.parentElement;
    if (!card) return;
    const script = card.querySelector('script.chart-payload-inline');
    if (!script) return;
    let payload;
    try { payload = JSON.parse(script.textContent); }
    catch (e) { console.warn('[charts] payload parse fail', e); return; }
    const type = (payload.type || stage.getAttribute('data-chart-type') || 'bar').toLowerCase();
    const renderer = RENDERERS[type];
    if (!renderer) { console.warn('[charts] unknown type:', type); return; }
    if (!stage.getAttribute('data-chart-id')) {
      stage.setAttribute('data-chart-id', `pat-${idx}`);
    }
    const t = readTheme(stage);
    try { renderer(stage, payload, t); }
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
