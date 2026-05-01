/* ============================================================
   charts.js — v3.2.0 d3 SVG 차트 라이브러리
   ------------------------------------------------------------
   정적 데이터 (보고서 HTML 의 <script type="application/json">) 를
   읽어 d3 v7 로 SVG 차트 4종을 렌더한다.
   - drawScenarioBar(elem, data)  : 가로 막대 (시나리오 확률)
   - drawKeyFiguresDonut(elem, data) : 도넛 (핵심 수치 분배)
   - drawSeverityHeatmap(elem, data) : 인과 사슬 severity (CSS 기반)
   - drawConfidenceTriple(elem, data): 3축 막대 (source/freshness/expert)
   - drawConfidenceRadar(elem, data) : 6축 레이더 (호환성)
   디자인 토큰은 charts.css 와 일치 (burgundy 테마).
   ============================================================ */
(function(global){
  'use strict';
  if (typeof d3 === 'undefined'){
    console.warn('[charts.js] d3 not loaded — charts will be skipped.');
    return;
  }

  const TOKENS_FALLBACK = {
    bg:           '#321F1F',
    text:         '#F0E2CC',
    textMuted:    '#A89880',
    textSecondary:'#D4C4AA',
    grid:         'rgba(212,196,170,0.08)',
    gridStrong:   'rgba(212,196,170,0.18)',
    gold:         '#C9A84C',
    goldDark:     '#9E8A15',
    green:        '#1A7B3E',
    greenDark:    '#125A2D',
    orange:       '#C76B1E',
    orangeDark:   '#8D4D14',
    red:          '#BD3227',
    redDark:      '#8A2018',
    blue:         '#1D6FA5',
  };

  /* TOKENS 를 :root 의 CSS 변수에서 읽는다 — 페이지 data-theme 변경 시 자동 동기.
     CSS 변수가 비어있으면 burgundy fallback. _read() 는 매 차트 렌더 시 호출되어
     테마 변경에도 반응한다. */
  function _readToken(name, fb){
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fb;
  }
  function _shade(hex, lum){
    /* 단순 음영 함수 — hex 끝에 lum (0~1, <1 어둡게) 곱해 반환. rgba 는 그대로 통과. */
    if (!hex || hex.indexOf('#') !== 0 || hex.length !== 7) return hex;
    var n = parseInt(hex.slice(1), 16);
    var r = Math.max(0, Math.min(255, Math.round(((n>>16)&255) * lum)));
    var g = Math.max(0, Math.min(255, Math.round(((n>>8)&255) * lum)));
    var b = Math.max(0, Math.min(255, Math.round((n&255) * lum)));
    return '#' + ((1<<24) + (r<<16) + (g<<8) + b).toString(16).slice(1);
  }
  function _tokens(){
    var gold   = _readToken('--gold',           TOKENS_FALLBACK.gold);
    var green  = _readToken('--green',          TOKENS_FALLBACK.green);
    var orange = _readToken('--orange',         TOKENS_FALLBACK.orange);
    var red    = _readToken('--red',            TOKENS_FALLBACK.red);
    return {
      bg:            _readToken('--card',           TOKENS_FALLBACK.bg),
      text:          _readToken('--text-primary',   TOKENS_FALLBACK.text),
      textMuted:     _readToken('--text-muted',     TOKENS_FALLBACK.textMuted),
      textSecondary: _readToken('--text-secondary', TOKENS_FALLBACK.textSecondary),
      grid:          TOKENS_FALLBACK.grid,
      gridStrong:    TOKENS_FALLBACK.gridStrong,
      gold:       gold,    goldDark:   _shade(gold,   0.78),
      green:      green,   greenDark:  _shade(green,  0.72),
      orange:     orange,  orangeDark: _shade(orange, 0.72),
      red:        red,     redDark:    _shade(red,    0.74),
      blue:       _readToken('--blue',            TOKENS_FALLBACK.blue),
    };
  }
  /* TOKENS 는 모듈 로드 시 한 번 계산. 테마 변경 시 페이지 reload 가 일반적이므로
     매 렌더마다 재계산할 필요는 없으나, 동적 테마 토글이 필요하면 _tokens() 사용. */
  const TOKENS = _tokens();

  /** tag → (color, dark) */
  function tagPalette(tag){
    switch (tag){
      case '최선':            return [TOKENS.green,  TOKENS.greenDark];
      case '기본': case '기본선': return [TOKENS.gold,   TOKENS.goldDark];
      case '악화':            return [TOKENS.orange, TOKENS.orangeDark];
      case '최악':            return [TOKENS.red,    TOKENS.redDark];
      default:                return [TOKENS.gold,   TOKENS.goldDark];
    }
  }

  /** Single shared tooltip element (lazy creation) */
  let tooltipEl = null;
  function tooltip(){
    if (tooltipEl) return tooltipEl;
    tooltipEl = d3.select('body').append('div').attr('class', 'chart-tooltip');
    return tooltipEl;
  }

  /** Parse a probability like "35%" or 0.35 → 0~100 number. */
  function parseProb(p){
    if (typeof p === 'number'){
      return p > 1.0001 ? Math.round(p) : Math.round(p * 100);
    }
    if (typeof p === 'string'){
      const m = p.match(/(\d{1,3}(?:\.\d+)?)/);
      if (m){
        const n = parseFloat(m[1]);
        return n > 1.0001 ? Math.round(n) : Math.round(n * 100);
      }
    }
    return 0;
  }

  /* ============== 1. Scenario probability bars ============== */
  function drawScenarioBar(svgEl, data){
    if (!data || !data.length) return;
    const W = 600, H = 60 + data.length * 56;
    const padL = 130, padR = 70, padT = 16, padB = 30;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const x = d3.scaleLinear().domain([0, 100]).range([padL, W - padR]);
    const y = d3.scaleBand().domain(data.map(d => d.name))
      .range([padT, H - padB]).padding(0.34);

    const defs = svg.append('defs');
    data.forEach((d, i) => {
      const [c, cd] = tagPalette(d.tag);
      const g = defs.append('linearGradient').attr('id', `chart-grad-${i}`)
        .attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '0%');
      g.append('stop').attr('offset', '0%').attr('stop-color', cd);
      g.append('stop').attr('offset', '100%').attr('stop-color', c);
    });

    /* grid */
    svg.append('g').selectAll('line').data(d3.range(0, 101, 10))
      .enter().append('line')
        .attr('x1', d => x(d)).attr('x2', d => x(d))
        .attr('y1', padT).attr('y2', H - padB + 4)
        .attr('stroke', TOKENS.grid).attr('stroke-width', 1);

    /* x axis labels */
    svg.append('g').selectAll('text').data([0, 25, 50, 75, 100])
      .enter().append('text')
        .attr('x', d => x(d)).attr('y', H - padB + 22)
        .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
        .attr('font-family', '"JetBrains Mono", monospace')
        .attr('font-size', '9px').attr('font-weight', '600')
        .text(d => d + '%');

    /* left labels (name + tag) */
    svg.append('g').selectAll('g').data(data).enter().append('g')
      .each(function(d){
        const g = d3.select(this);
        const [c] = tagPalette(d.tag);
        const yc = y(d.name) + y.bandwidth() / 2;
        g.append('text')
          .attr('x', padL - 14).attr('y', yc - 4)
          .attr('text-anchor', 'end').attr('fill', TOKENS.text)
          .attr('font-family', '"Noto Sans KR", sans-serif')
          .attr('font-size', '11px').attr('font-weight', '700')
          .text(d.name.length > 16 ? d.name.slice(0, 15) + '…' : d.name);
        if (d.tag){
          g.append('text')
            .attr('x', padL - 14).attr('y', yc + 10)
            .attr('text-anchor', 'end').attr('fill', c)
            .attr('font-family', '"Noto Sans KR", sans-serif')
            .attr('font-size', '9px').attr('font-weight', '600')
            .text(d.tag);
        }
      });

    /* bars */
    const bars = svg.append('g').selectAll('rect').data(data).enter()
      .append('rect')
        .attr('x', padL).attr('width', 0)
        .attr('y', d => y(d.name)).attr('height', y.bandwidth())
        .attr('rx', 5).attr('ry', 5)
        .attr('fill', (d, i) => `url(#chart-grad-${i})`)
        .attr('stroke', 'rgba(255,255,255,0.05)').attr('stroke-width', 1)
        .style('cursor', 'pointer')
        .on('mouseenter', function(e, d){
          d3.select(this).transition().duration(140)
            .attr('stroke', 'rgba(255,255,255,0.45)').attr('stroke-width', 2);
          const t = tooltip();
          const tagCls = d.tag ? `tag-${d.tag}` : '';
          t.html(`<b>${d.name}</b><br><span class="${tagCls}">${d.tag || ''}</span> · ${d.prob}%${d.note ? '<br><span style="color:#A89880">' + d.note + '</span>' : ''}`)
            .style('opacity', 1);
        })
        .on('mousemove', function(e){
          tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px');
        })
        .on('mouseleave', function(){
          d3.select(this).transition().duration(140)
            .attr('stroke', 'rgba(255,255,255,0.05)').attr('stroke-width', 1);
          tooltip().style('opacity', 0);
        });
    bars.transition().duration(900).delay((d, i) => i * 110).ease(d3.easeCubicOut)
      .attr('width', d => x(d.prob) - padL);

    /* % labels */
    svg.append('g').selectAll('text').data(data).enter().append('text')
      .attr('x', d => x(d.prob) + 10)
      .attr('y', d => y(d.name) + y.bandwidth() / 2 + 6)
      .attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Serif KR", serif')
      .attr('font-size', '18px').attr('font-weight', '900')
      .attr('opacity', 0).text(d => d.prob + '%')
      .transition().duration(500).delay((d, i) => i * 110 + 700)
      .attr('opacity', 1);
  }

  /* ============== 2. Key figures donut ============== */
  function drawKeyFiguresDonut(svgEl, data){
    if (!data || !data.length) return;
    const W = 360, H = 360, R = 130, r = 78;
    const cx = W / 2, cy = H / 2;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const palette = [TOKENS.gold, TOKENS.blue, TOKENS.green, TOKENS.orange, TOKENS.red, TOKENS.goldDark];
    const total = d3.sum(data, d => Math.abs(d.value || 1));
    const pie = d3.pie().sort(null).value(d => Math.abs(d.value || 1));
    const arc = d3.arc().innerRadius(r).outerRadius(R).cornerRadius(3).padAngle(0.012);
    const arcHover = d3.arc().innerRadius(r).outerRadius(R + 8).cornerRadius(3).padAngle(0.012);

    const root = svg.append('g').attr('transform', `translate(${cx},${cy})`);
    const arcs = root.selectAll('path').data(pie(data)).enter().append('path')
      .attr('d', arc)
      .attr('fill', (d, i) => palette[i % palette.length])
      .attr('stroke', TOKENS.bg).attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('mouseenter', function(e, d){
        d3.select(this).transition().duration(150).attr('d', arcHover);
        const pct = total ? Math.round((Math.abs(d.data.value || 1) / total) * 100) : 0;
        tooltip().html(
          `<b>${d.data.label || ''}</b><br>` +
          `<span style="color:${TOKENS.gold}">${d.data.value || ''}</span>` +
          (d.data.context ? `<br><span style="color:${TOKENS.textMuted}">${d.data.context}</span>` : '') +
          `<br><span style="color:${TOKENS.textMuted}">전체 대비 ${pct}%</span>`
        ).style('opacity', 1);
      })
      .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
      .on('mouseleave', function(){
        d3.select(this).transition().duration(150).attr('d', arc);
        tooltip().style('opacity', 0);
      });

    /* center label */
    root.append('text')
      .attr('text-anchor', 'middle').attr('y', -4)
      .attr('fill', TOKENS.textMuted)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '10px').attr('font-weight', '600')
      .attr('letter-spacing', '1.5px')
      .text('KEY FIGURES');
    root.append('text')
      .attr('text-anchor', 'middle').attr('y', 18)
      .attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Serif KR", serif')
      .attr('font-size', '24px').attr('font-weight', '900')
      .text(data.length);
    root.append('text')
      .attr('text-anchor', 'middle').attr('y', 36)
      .attr('fill', TOKENS.textMuted)
      .attr('font-size', '9px')
      .text('지표');

    /* outer labels (small) */
    const labelArc = d3.arc().innerRadius(R + 14).outerRadius(R + 14);
    root.selectAll('text.k').data(pie(data)).enter().append('text').attr('class', 'k')
      .attr('transform', d => `translate(${labelArc.centroid(d)})`)
      .attr('text-anchor', 'middle')
      .attr('fill', TOKENS.textSecondary)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '9px').attr('font-weight', '600')
      .text(d => (d.data.label || '').slice(0, 6));

    /* arcs intro animation */
    arcs.attr('opacity', 0)
      .transition().duration(450).delay((d, i) => i * 70)
      .attr('opacity', 1);
  }

  /* ============== 3. Severity heatmap (CSS-based, no svg) ============== */
  function drawSeverityHeatmap(rootEl, data){
    if (!data || !data.length) return;
    const root = d3.select(rootEl);
    root.selectAll('*').remove();
    const cells = 5;
    const sevToCells = (sev) => {
      const s = (sev || '').toLowerCase();
      if (/극심|critical|crit|위기/.test(s)) return {n: 5, cls: 's-crit'};
      if (/높|high|warn|경고/.test(s))        return {n: 4, cls: 's-high'};
      if (/중|med|보통/.test(s))               return {n: 3, cls: 's-med'};
      return {n: 2, cls: 's-low'};
    };
    data.forEach(step => {
      const row = root.append('div').attr('class', 'heatmap-row');
      row.append('div').attr('class', 'heatmap-row-label')
        .attr('title', step.title || '')
        .text(step.title || '?');
      const grid = row.append('div').attr('class', 'heatmap-row-cells')
        .style('--cells', cells);
      const sev = sevToCells(step.severity);
      for (let i = 0; i < cells; i++){
        grid.append('div').attr('class', 'heatmap-cell' + (i < sev.n ? ' ' + sev.cls : ''));
      }
    });
  }

  /* ============== 4. Confidence triple-axis bar ============== */
  function drawConfidenceTriple(svgEl, data){
    /* data: {source_diversity, data_freshness, expert_consensus} 0~1 */
    if (!data) return;
    const items = [
      {label: '출처 다양성', value: data.source_diversity || 0, color: TOKENS.blue},
      {label: '데이터 신선도', value: data.data_freshness || 0, color: TOKENS.gold},
      {label: '전문가 합의', value: data.expert_consensus || 0, color: TOKENS.green},
    ];
    const W = 600, H = 240;
    const padL = 110, padR = 60, padT = 18, padB = 22;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const x = d3.scaleLinear().domain([0, 1]).range([padL, W - padR]);
    const y = d3.scaleBand().domain(items.map(d => d.label))
      .range([padT, H - padB]).padding(0.32);

    /* grid */
    svg.append('g').selectAll('line').data([0, 0.25, 0.5, 0.75, 1])
      .enter().append('line')
        .attr('x1', d => x(d)).attr('x2', d => x(d))
        .attr('y1', padT).attr('y2', H - padB + 4)
        .attr('stroke', TOKENS.grid).attr('stroke-width', 1);

    /* x labels */
    svg.append('g').selectAll('text').data([0, 0.25, 0.5, 0.75, 1])
      .enter().append('text')
        .attr('x', d => x(d)).attr('y', H - padB + 16)
        .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
        .attr('font-family', '"JetBrains Mono", monospace')
        .attr('font-size', '9px').attr('font-weight', '600')
        .text(d => Math.round(d * 100) + '%');

    /* labels (left) */
    svg.append('g').selectAll('text').data(items).enter().append('text')
      .attr('x', padL - 14)
      .attr('y', d => y(d.label) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'end').attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '11px').attr('font-weight', '700')
      .text(d => d.label);

    /* bars */
    const defs = svg.append('defs');
    items.forEach((d, i) => {
      const g = defs.append('linearGradient').attr('id', `conf-grad-${i}`)
        .attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '0%');
      g.append('stop').attr('offset', '0%').attr('stop-color', d.color).attr('stop-opacity', 0.45);
      g.append('stop').attr('offset', '100%').attr('stop-color', d.color).attr('stop-opacity', 1);
    });
    const bars = svg.append('g').selectAll('rect').data(items).enter()
      .append('rect')
        .attr('x', padL).attr('width', 0)
        .attr('y', d => y(d.label)).attr('height', y.bandwidth())
        .attr('rx', 4).attr('fill', (d, i) => `url(#conf-grad-${i})`);
    bars.transition().duration(800).delay((d, i) => i * 130).ease(d3.easeCubicOut)
      .attr('width', d => x(d.value) - padL);

    /* % labels right */
    svg.append('g').selectAll('text').data(items).enter().append('text')
      .attr('x', d => x(d.value) + 8)
      .attr('y', d => y(d.label) + y.bandwidth() / 2 + 6)
      .attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Serif KR", serif')
      .attr('font-size', '16px').attr('font-weight', '900')
      .attr('opacity', 0)
      .text(d => Math.round(d.value * 100) + '%')
      .transition().duration(450).delay((d, i) => i * 130 + 600)
      .attr('opacity', 1);
  }

  /* ============== 5. Time-series line chart ============== */
  function drawTimeseriesLine(svgEl, data){
    /* data: {label, points: [{x, y}], unit?} */
    if (!data || !data.points || !data.points.length) return;
    const W = 600, H = 320;
    const padL = 56, padR = 24, padT = 24, padB = 36;
    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const xs = data.points.map((p, i) => p.x != null ? p.x : i);
    const ys = data.points.map(p => +p.y || 0);
    const xIsNumber = xs.every(v => typeof v === 'number');
    const xScale = xIsNumber
      ? d3.scaleLinear().domain(d3.extent(xs)).range([padL, W - padR])
      : d3.scalePoint().domain(xs).range([padL, W - padR]).padding(0.1);
    const yMin = d3.min(ys), yMax = d3.max(ys);
    const yPad = (yMax - yMin) * 0.1 || 1;
    const yScale = d3.scaleLinear().domain([yMin - yPad, yMax + yPad]).nice().range([H - padB, padT]);

    /* grid */
    const yTicks = yScale.ticks(5);
    svg.append('g').selectAll('line').data(yTicks).enter().append('line')
      .attr('x1', padL).attr('x2', W - padR)
      .attr('y1', d => yScale(d)).attr('y2', d => yScale(d))
      .attr('stroke', TOKENS.grid).attr('stroke-width', 1);

    /* y axis labels */
    svg.append('g').selectAll('text').data(yTicks).enter().append('text')
      .attr('x', padL - 8).attr('y', d => yScale(d) + 3)
      .attr('text-anchor', 'end').attr('fill', TOKENS.textMuted)
      .attr('font-family', '"JetBrains Mono", monospace')
      .attr('font-size', '9px').attr('font-weight', '600')
      .text(d => d);

    /* x axis labels (sample) */
    const xLabelSample = xs.length > 8
      ? [xs[0], xs[Math.floor(xs.length / 2)], xs[xs.length - 1]]
      : xs;
    svg.append('g').selectAll('text').data(xLabelSample).enter().append('text')
      .attr('x', d => xScale(d)).attr('y', H - padB + 16)
      .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '9px').attr('font-weight', '600')
      .text(d => String(d).slice(0, 12));

    /* area gradient under line */
    const defs = svg.append('defs');
    const grad = defs.append('linearGradient').attr('id', 'ts-area-grad')
      .attr('x1', '0%').attr('y1', '0%').attr('x2', '0%').attr('y2', '100%');
    grad.append('stop').attr('offset', '0%').attr('stop-color', TOKENS.gold).attr('stop-opacity', 0.36);
    grad.append('stop').attr('offset', '100%').attr('stop-color', TOKENS.gold).attr('stop-opacity', 0);

    const area = d3.area()
      .x((d, i) => xScale(xs[i]))
      .y0(yScale(yMin - yPad))
      .y1((d, i) => yScale(ys[i]))
      .curve(d3.curveMonotoneX);
    svg.append('path').datum(data.points)
      .attr('d', area).attr('fill', 'url(#ts-area-grad)');

    /* line */
    const line = d3.line()
      .x((d, i) => xScale(xs[i]))
      .y((d, i) => yScale(ys[i]))
      .curve(d3.curveMonotoneX);
    const path = svg.append('path').datum(data.points)
      .attr('d', line).attr('fill', 'none')
      .attr('stroke', TOKENS.gold).attr('stroke-width', 2.5)
      .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const totalLen = path.node().getTotalLength();
    path.attr('stroke-dasharray', totalLen).attr('stroke-dashoffset', totalLen)
      .transition().duration(1000).ease(d3.easeCubicOut)
      .attr('stroke-dashoffset', 0);

    /* points + interaction */
    svg.append('g').selectAll('circle').data(data.points).enter().append('circle')
      .attr('cx', (d, i) => xScale(xs[i]))
      .attr('cy', (d, i) => yScale(ys[i]))
      .attr('r', 0).attr('fill', TOKENS.gold)
      .attr('stroke', TOKENS.bg).attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('mouseenter', function(e, d){
        d3.select(this).transition().duration(120).attr('r', 6);
        tooltip().html(`<b>${d.x || ''}</b><br><span style="color:${TOKENS.gold}">${d.y || ''}</span>${data.unit ? ' ' + data.unit : ''}`)
          .style('opacity', 1);
      })
      .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
      .on('mouseleave', function(){
        d3.select(this).transition().duration(120).attr('r', 4);
        tooltip().style('opacity', 0);
      })
      .transition().duration(400).delay((d, i) => 800 + i * 30).attr('r', 4);

    /* title overlay */
    if (data.label){
      svg.append('text').attr('x', padL).attr('y', padT - 6)
        .attr('fill', TOKENS.textSecondary)
        .attr('font-family', '"Noto Sans KR", sans-serif')
        .attr('font-size', '10px').attr('font-weight', '600')
        .text(data.label);
    }
  }

  /* ============== 6. Stacked horizontal bar (scenario × actor impact) ============== */
  function drawStackedBar(svgEl, data){
    /* data: {scenarios: [{name, segments: [{label, value, color?}]}]} */
    if (!data || !data.scenarios || !data.scenarios.length) return;
    const items = data.scenarios;
    const W = 600, H = 60 + items.length * 56;
    const padL = 130, padR = 24, padT = 16, padB = 36;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const totals = items.map(s => d3.sum(s.segments, d => +d.value || 0));
    const maxTotal = d3.max(totals) || 1;
    const x = d3.scaleLinear().domain([0, maxTotal]).range([padL, W - padR]);
    const y = d3.scaleBand().domain(items.map(s => s.name))
      .range([padT, H - padB]).padding(0.32);

    const palette = [TOKENS.green, TOKENS.gold, TOKENS.blue, TOKENS.orange, TOKENS.red];

    /* axis */
    svg.append('g').selectAll('line').data(d3.range(0, 1.01, 0.25))
      .enter().append('line')
        .attr('x1', d => x(d * maxTotal)).attr('x2', d => x(d * maxTotal))
        .attr('y1', padT).attr('y2', H - padB + 4)
        .attr('stroke', TOKENS.grid);

    /* left labels */
    svg.append('g').selectAll('text').data(items).enter().append('text')
      .attr('x', padL - 10)
      .attr('y', d => y(d.name) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'end').attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '11px').attr('font-weight', '700')
      .text(d => d.name.length > 16 ? d.name.slice(0, 15) + '…' : d.name);

    /* segments */
    items.forEach((row, ri) => {
      let cum = 0;
      row.segments.forEach((seg, si) => {
        const w = x(seg.value || 0) - x(0);
        const xx = x(cum);
        cum += seg.value || 0;
        svg.append('rect')
          .attr('x', xx).attr('y', y(row.name))
          .attr('width', 0).attr('height', y.bandwidth())
          .attr('fill', seg.color || palette[si % palette.length])
          .attr('rx', si === 0 ? 4 : 0).attr('ry', si === 0 ? 4 : 0)
          .style('cursor', 'pointer')
          .on('mouseenter', function(e){
            d3.select(this).attr('opacity', 0.8);
            tooltip().html(`<b>${row.name}</b><br>${seg.label}: <span style="color:${TOKENS.gold}">${seg.value}</span>`)
              .style('opacity', 1);
          })
          .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
          .on('mouseleave', function(){
            d3.select(this).attr('opacity', 1);
            tooltip().style('opacity', 0);
          })
          .transition().duration(700).delay(ri * 80 + si * 80).ease(d3.easeCubicOut)
          .attr('width', w);
      });
    });

    /* legend */
    const legendItems = (items[0] || {segments: []}).segments.map((s, i) => ({
      label: s.label,
      color: s.color || palette[i % palette.length],
    }));
    const legendY = H - 16;
    let legX = padL;
    legendItems.forEach(li => {
      const g = svg.append('g').attr('transform', `translate(${legX}, ${legendY})`);
      g.append('rect').attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', li.color);
      g.append('text').attr('x', 14).attr('y', 9).attr('fill', TOKENS.textMuted)
        .attr('font-family', '"Noto Sans KR", sans-serif').attr('font-size', '9px')
        .text(li.label);
      legX += (li.label.length * 7) + 30;
    });
  }

  /* ============== 7. Bubble chart (risk matrix) ============== */
  function drawBubble(svgEl, data){
    /* data: [{label, x, y, size, color?}] — x: probability(0~1), y: impact(0~1), size: weight */
    if (!data || !data.length) return;
    const W = 600, H = 360;
    const padL = 50, padR = 28, padT = 24, padB = 40;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const x = d3.scaleLinear().domain([0, 1]).range([padL, W - padR]);
    const y = d3.scaleLinear().domain([0, 1]).range([H - padB, padT]);
    const sizes = data.map(d => +d.size || 1);
    const r = d3.scaleSqrt().domain([0, d3.max(sizes) || 1]).range([6, 28]);

    /* quadrant lines (mid) */
    svg.append('line').attr('x1', x(0.5)).attr('x2', x(0.5))
      .attr('y1', padT).attr('y2', H - padB)
      .attr('stroke', TOKENS.gridStrong).attr('stroke-dasharray', '3,3');
    svg.append('line').attr('y1', y(0.5)).attr('y2', y(0.5))
      .attr('x1', padL).attr('x2', W - padR)
      .attr('stroke', TOKENS.gridStrong).attr('stroke-dasharray', '3,3');

    /* quadrant labels */
    const ql = (xv, yv, txt, col) =>
      svg.append('text').attr('x', x(xv)).attr('y', y(yv))
        .attr('text-anchor', 'middle').attr('fill', col)
        .attr('font-family', '"Noto Sans KR", sans-serif')
        .attr('font-size', '9px').attr('font-weight', '700')
        .attr('opacity', 0.55).text(txt);
    ql(0.78, 0.92, '고확률 · 고영향', TOKENS.red);
    ql(0.22, 0.92, '저확률 · 고영향', TOKENS.orange);
    ql(0.78, 0.08, '고확률 · 저영향', TOKENS.gold);
    ql(0.22, 0.08, '저확률 · 저영향', TOKENS.blue);

    /* axes */
    svg.append('text').attr('x', (padL + W - padR) / 2).attr('y', H - 6)
      .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '10px').attr('font-weight', '600')
      .text('확률 →');
    svg.append('text').attr('transform', `rotate(-90,${padL - 30},${(padT + H - padB) / 2})`)
      .attr('x', padL - 30).attr('y', (padT + H - padB) / 2)
      .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '10px').attr('font-weight', '600')
      .text('영향 →');

    /* bubbles */
    const bubbles = svg.append('g').selectAll('g').data(data).enter().append('g')
      .attr('transform', d => `translate(${x(d.x || 0)}, ${y(d.y || 0)})`)
      .style('cursor', 'pointer')
      .on('mouseenter', function(e, d){
        d3.select(this).select('circle').transition().duration(140)
          .attr('stroke', 'rgba(255,255,255,0.55)').attr('stroke-width', 2.5);
        tooltip().html(`<b>${d.label || '?'}</b><br>확률: <span style="color:${TOKENS.gold}">${Math.round((d.x||0)*100)}%</span><br>영향: <span style="color:${TOKENS.gold}">${Math.round((d.y||0)*100)}%</span>${d.note ? '<br><span style="color:'+TOKENS.textMuted+'">'+d.note+'</span>' : ''}`)
          .style('opacity', 1);
      })
      .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
      .on('mouseleave', function(){
        d3.select(this).select('circle').transition().duration(140)
          .attr('stroke', 'rgba(255,255,255,0.15)').attr('stroke-width', 1.5);
        tooltip().style('opacity', 0);
      });

    bubbles.append('circle').attr('r', 0)
      .attr('fill', d => d.color || TOKENS.orange).attr('fill-opacity', 0.55)
      .attr('stroke', 'rgba(255,255,255,0.15)').attr('stroke-width', 1.5)
      .transition().duration(700).delay((d, i) => i * 80).ease(d3.easeBackOut.overshoot(1.4))
      .attr('r', d => r(d.size || 1));

    bubbles.append('text').attr('text-anchor', 'middle').attr('y', 4)
      .attr('fill', TOKENS.text).attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '9.5px').attr('font-weight', '700').attr('opacity', 0)
      .text(d => (d.label || '').slice(0, 6))
      .transition().duration(400).delay((d, i) => 700 + i * 80).attr('opacity', 1);
  }

  /* ============== 8. Gantt timeline ============== */
  function drawGantt(svgEl, data){
    /* data: [{label, start, end, color?}] — start/end: number or sortable string */
    if (!data || !data.length) return;
    const items = data;
    const W = 600, H = 60 + items.length * 30;
    const padL = 130, padR = 30, padT = 16, padB = 30;

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    /* scale: numeric if possible, else point-based */
    const allEnds = items.flatMap(d => [d.start, d.end]).map(v => +v).filter(v => !isNaN(v));
    let xScale;
    if (allEnds.length === items.length * 2){
      xScale = d3.scaleLinear().domain([d3.min(allEnds), d3.max(allEnds)]).range([padL, W - padR]);
    } else {
      const points = items.flatMap(d => [d.start, d.end]).filter(Boolean);
      xScale = d3.scalePoint().domain(points).range([padL, W - padR]).padding(0.1);
    }
    const y = d3.scaleBand().domain(items.map((d, i) => i + ': ' + d.label))
      .range([padT, H - padB]).padding(0.28);

    /* time axis labels */
    if (allEnds.length === items.length * 2){
      const ticks = xScale.ticks(5);
      svg.append('g').selectAll('text').data(ticks).enter().append('text')
        .attr('x', d => xScale(d)).attr('y', H - padB + 16)
        .attr('text-anchor', 'middle').attr('fill', TOKENS.textMuted)
        .attr('font-family', '"JetBrains Mono", monospace')
        .attr('font-size', '9px').attr('font-weight', '600')
        .text(d => d);
      svg.append('g').selectAll('line').data(ticks).enter().append('line')
        .attr('x1', d => xScale(d)).attr('x2', d => xScale(d))
        .attr('y1', padT).attr('y2', H - padB)
        .attr('stroke', TOKENS.grid);
    }

    /* labels (left) */
    svg.append('g').selectAll('text').data(items).enter().append('text')
      .attr('x', padL - 10)
      .attr('y', (d, i) => y(i + ': ' + d.label) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'end').attr('fill', TOKENS.text)
      .attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '11px').attr('font-weight', '700')
      .text(d => d.label.length > 16 ? d.label.slice(0, 15) + '…' : d.label);

    /* bars */
    svg.append('g').selectAll('rect').data(items).enter().append('rect')
      .attr('x', d => xScale(d.start))
      .attr('y', (d, i) => y(i + ': ' + d.label))
      .attr('width', 0).attr('height', y.bandwidth())
      .attr('rx', 4).attr('fill', d => d.color || TOKENS.gold).attr('fill-opacity', 0.85)
      .style('cursor', 'pointer')
      .on('mouseenter', function(e, d){
        d3.select(this).attr('fill-opacity', 1);
        tooltip().html(`<b>${d.label}</b><br><span style="color:${TOKENS.gold}">${d.start}</span> → <span style="color:${TOKENS.gold}">${d.end}</span>${d.note ? '<br><span style="color:'+TOKENS.textMuted+'">'+d.note+'</span>' : ''}`)
          .style('opacity', 1);
      })
      .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
      .on('mouseleave', function(){
        d3.select(this).attr('fill-opacity', 0.85);
        tooltip().style('opacity', 0);
      })
      .transition().duration(700).delay((d, i) => i * 70).ease(d3.easeCubicOut)
      .attr('width', d => Math.max(8, xScale(d.end) - xScale(d.start)));
  }

  /* ============== 9. Network force graph (actor relationships) ============== */
  function drawNetwork(svgEl, data){
    /* data: {nodes: [{id, label, group?}], links: [{source, target, type?}]} */
    if (!data || !data.nodes || !data.nodes.length) return;
    const W = 600, H = 420;
    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');
    svg.selectAll('*').remove();

    const groupColor = (g) => {
      const map = {
        '주요': TOKENS.gold, '동맹': TOKENS.green,
        '대립': TOKENS.red, '중립': TOKENS.blue,
        '미디어': TOKENS.orange,
      };
      return map[g] || TOKENS.gold;
    };

    /* Pre-process */
    const nodes = data.nodes.map(n => Object.assign({}, n));
    const links = data.links.map(l => Object.assign({}, l));

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(110).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-260))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collide', d3.forceCollide().radius(38))
      .stop();
    /* run synchronously to avoid layout flicker */
    for (let i = 0; i < 220; i++) simulation.tick();

    const link = svg.append('g').attr('stroke', TOKENS.textMuted).attr('stroke-opacity', 0.35)
      .selectAll('line').data(links).enter().append('line')
      .attr('stroke-width', 1.2)
      .attr('stroke-dasharray', d => (d.type === '대립' ? '4 3' : null))
      .attr('stroke', d => (d.type === '대립' ? TOKENS.red : TOKENS.textMuted))
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    const node = svg.append('g').selectAll('g').data(nodes).enter().append('g')
      .attr('transform', d => `translate(${d.x},${d.y})`)
      .style('cursor', 'pointer')
      .on('mouseenter', function(e, d){
        d3.select(this).select('circle').transition().duration(120).attr('r', 28);
        tooltip().html(`<b>${d.label || d.id}</b>${d.group ? '<br><span style="color:'+groupColor(d.group)+'">'+d.group+'</span>' : ''}${d.note ? '<br><span style="color:'+TOKENS.textMuted+'">'+d.note+'</span>' : ''}`)
          .style('opacity', 1);
      })
      .on('mousemove', e => tooltip().style('left', (e.pageX + 12) + 'px').style('top', (e.pageY - 10) + 'px'))
      .on('mouseleave', function(){
        d3.select(this).select('circle').transition().duration(120).attr('r', 22);
        tooltip().style('opacity', 0);
      });

    node.append('circle').attr('r', 0).attr('fill', d => groupColor(d.group))
      .attr('fill-opacity', 0.7)
      .attr('stroke', TOKENS.bg).attr('stroke-width', 2)
      .transition().duration(550).ease(d3.easeBackOut.overshoot(1.3)).attr('r', 22);

    node.append('text').attr('text-anchor', 'middle').attr('y', 4)
      .attr('fill', TOKENS.text).attr('font-family', '"Noto Sans KR", sans-serif')
      .attr('font-size', '10px').attr('font-weight', '700').attr('opacity', 0)
      .text(d => (d.label || d.id || '').slice(0, 5))
      .transition().duration(400).delay(500).attr('opacity', 1);
  }

  /* ============== Auto-init: read embedded JSON and render ============== */
  function autoInit(){
    const cfgEl = document.getElementById('chart-payload');
    if (!cfgEl) return;
    let cfg;
    try { cfg = JSON.parse(cfgEl.textContent); }
    catch (e) { console.warn('[charts.js] payload JSON parse failed', e); return; }

    if (cfg.scenarios){
      const el = document.getElementById('chart-scenarios');
      if (el) drawScenarioBar(el, cfg.scenarios);
    }
    if (cfg.key_figures){
      const el = document.getElementById('chart-figures');
      if (el) drawKeyFiguresDonut(el, cfg.key_figures);
    }
    if (cfg.severity_chain){
      const el = document.getElementById('chart-severity');
      if (el) drawSeverityHeatmap(el, cfg.severity_chain);
    }
    if (cfg.confidence){
      const el = document.getElementById('chart-confidence');
      if (el) drawConfidenceTriple(el, cfg.confidence);
    }
    if (cfg.timeseries){
      const el = document.getElementById('chart-timeseries');
      if (el) drawTimeseriesLine(el, cfg.timeseries);
    }
    if (cfg.stacked){
      const el = document.getElementById('chart-stacked');
      if (el) drawStackedBar(el, cfg.stacked);
    }
    if (cfg.bubble){
      const el = document.getElementById('chart-bubble');
      if (el) drawBubble(el, cfg.bubble);
    }
    if (cfg.gantt){
      const el = document.getElementById('chart-gantt');
      if (el) drawGantt(el, cfg.gantt);
    }
    if (cfg.network){
      const el = document.getElementById('chart-network');
      if (el) drawNetwork(el, cfg.network);
    }
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  /* Expose API */
  global.AnalysisCharts = {
    drawScenarioBar,
    drawKeyFiguresDonut,
    drawSeverityHeatmap,
    drawConfidenceTriple,
    drawTimeseriesLine,
    drawStackedBar,
    drawBubble,
    drawGantt,
    drawNetwork,
    parseProb,
    TOKENS,
  };
})(window);
