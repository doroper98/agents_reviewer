/* maps.js — v4.2.0 d3 + d3-geo + TopoJSON map renderer.
 *
 * v3.4.0~v4.1.0 의 maplibre-gl 의존 폐기 (mono guide §2).
 * - 외부 타일 / 글리프 PBF / 스키마 변경 취약점 제거.
 * - world-atlas 110m TopoJSON (~100KB) 한 번 로드 → 정적 SVG 렌더.
 * - 인쇄·캡처 친화. 모바일 ISP 차단/CDN 캐시 영향 없음.
 *
 * 데이터 입력: <script type="application/json" id="map-payload">
 *   { center: [lng, lat], zoom: float,
 *     markers: [{id, name, lng, lat, highlight}],
 *     arcs: [{from_id, to_id, highlight?, label?}],
 *     legend?: [{label, kind, highlight?}] }
 *
 * Mono Theme: 호 색상은 highlight 여부로 accent/muted, dash 로 1차/보조 구분.
 */
(function () {
  if (!window.d3) { console.warn('[map] d3 not loaded'); return; }
  if (!window.topojson) { console.warn('[map] topojson-client not loaded'); return; }
  const d3 = window.d3, topojson = window.topojson;

  function readTheme(rootEl) {
    const cs = getComputedStyle(rootEl || document.documentElement);
    const r = (n) => cs.getPropertyValue(n).trim();
    return {
      bg: r('--bg') || '#3D1820',
      text: r('--text') || '#EFE5D1',
      muted: r('--muted') || '#A88E7A',
      accent: r('--accent') || '#D4A858',
      land: r('--map-land') || r('--bg') || '#3D1820',
      water: r('--map-water') || '#2A0E16',
      boundary: r('--map-boundary') || r('--text') || '#EFE5D1',
    };
  }

  const WORLD_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';
  let worldPromise = null;
  function loadWorld() {
    if (window.__WORLD_TOPO__) return Promise.resolve(window.__WORLD_TOPO__);
    if (worldPromise) return worldPromise;
    worldPromise = fetch(WORLD_URL).then(r => r.ok ? r.json() : null).then(w => {
      if (w) window.__WORLD_TOPO__ = w;
      return w;
    }).catch(e => { console.warn('[map] world-atlas fetch failed', e); return null; });
    return worldPromise;
  }

  function curvedPath(p1, p2, bow) {
    const mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = -dy / dist, ny = dx / dist;
    const cx = mx + nx * bow, cy = my + ny * bow;
    return `M${p1[0]},${p1[1]} Q${cx},${cy} ${p2[0]},${p2[1]}`;
  }

  function renderMap(container, payload) {
    const t = readTheme(container);
    const W = 720, H = 380;
    container.innerHTML = '';
    const svg = d3.select(container).append('svg')
      .attr('width', '100%').attr('height', '100%')
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .style('display', 'block');

    svg.append('rect').attr('width', W).attr('height', H).attr('fill', t.water);

    const center = payload.center || [0, 0];
    const zoom = payload.zoom || 3.0;
    const scale = 110 * zoom;
    const projection = d3.geoMercator()
      .center(center).scale(scale).translate([W / 2, H * 0.55]);
    const path = d3.geoPath(projection);

    const gMap = svg.append('g').attr('class', 'map-base');
    const gArc = svg.append('g').attr('class', 'arcs');
    const gMarker = svg.append('g').attr('class', 'markers');

    function project(lng, lat) { return projection([lng, lat]); }

    function renderBase(world) {
      if (!world) return;
      const countries = topojson.feature(world, world.objects.countries);
      const borders = topojson.mesh(world, world.objects.countries, (a, b) => a !== b);
      gMap.selectAll('path.country').data(countries.features).join('path')
        .attr('class', 'country').attr('d', path).attr('fill', t.land).attr('stroke', 'none');
      gMap.append('path').datum(borders)
        .attr('class', 'country-border').attr('d', path).attr('fill', 'none')
        .attr('stroke', t.boundary).attr('stroke-width', 0.7).attr('stroke-opacity', 0.7);
    }

    loadWorld().then(world => {
      renderBase(world);

      const markersById = Object.fromEntries((payload.markers || []).map(m => [m.id, m]));
      (payload.arcs || []).forEach(a => {
        const f = markersById[a.from_id], to = markersById[a.to_id];
        if (!f || !to) return;
        const p1 = project(+f.lng, +f.lat);
        const p2 = project(+to.lng, +to.lat);
        if (!p1 || !p2) return;
        const bow = Math.min(70, Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * 0.22);
        const color = a.highlight ? t.accent : t.muted;
        const dash = a.highlight ? null : '5,3';
        const g = gArc.append('g').attr('class', 'arc');
        g.append('path').attr('d', curvedPath(p1, p2, bow))
          .attr('fill', 'none').attr('stroke', color)
          .attr('stroke-width', a.highlight ? 2.4 : 1.6)
          .attr('stroke-dasharray', dash).attr('opacity', 0.9);
        if (a.label) {
          const mx = (p1[0] + p2[0]) / 2 + 4, my = (p1[1] + p2[1]) / 2 - 6 - bow * 0.5;
          g.append('text').attr('x', mx).attr('y', my).attr('text-anchor', 'middle')
            .attr('fill', color).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
            .attr('font-weight', 600).text(a.label);
        }
      });

      (payload.markers || []).forEach(m => {
        const p = project(+m.lng, +m.lat);
        if (!p) return;
        const isHL = !!m.highlight;
        const r = isHL ? 6 : 4;
        const color = isHL ? t.accent : t.muted;
        const g = gMarker.append('g').attr('class', 'marker').attr('transform', `translate(${p[0]},${p[1]})`);
        g.append('circle').attr('r', r + 2).attr('fill', t.water).attr('opacity', 0.85);
        g.append('circle').attr('r', r).attr('fill', color)
          .attr('stroke', t.text).attr('stroke-width', isHL ? 1.0 : 0.6);
        if (m.name) {
          g.append('text').attr('x', r + 4).attr('y', 4).attr('fill', t.text)
            .attr('font-family', 'Noto Sans KR').attr('font-size', 11)
            .attr('font-weight', isHL ? 700 : 500).text(m.name);
        }
      });
    });

    if (payload.legend && payload.legend.length) {
      const lg = svg.append('g').attr('transform', `translate(12, ${H - 12 - payload.legend.length * 16})`);
      payload.legend.forEach((l, i) => {
        const y = i * 16;
        const color = l.highlight ? t.accent : t.muted;
        if (l.kind === 'line') {
          lg.append('line').attr('x1', 0).attr('y1', y + 5).attr('x2', 18).attr('y2', y + 5)
            .attr('stroke', color).attr('stroke-width', l.highlight ? 2.4 : 1.6)
            .attr('stroke-dasharray', l.highlight ? null : '5,3');
        } else {
          lg.append('circle').attr('cx', 9).attr('cy', y + 5).attr('r', l.highlight ? 5 : 3.5)
            .attr('fill', color).attr('stroke', t.text).attr('stroke-width', 0.6);
        }
        lg.append('text').attr('x', 24).attr('y', y + 9).attr('fill', t.text)
          .attr('font-family', 'Noto Sans KR').attr('font-size', 10).text(l.label);
      });
    }
  }

  function init() {
    const container = document.getElementById('freeform-map');
    if (!container) return;
    const script = document.getElementById('map-payload');
    if (!script) return;
    let payload;
    try { payload = JSON.parse(script.textContent); }
    catch (e) { console.warn('[map] payload parse fail', e); return; }
    if (!payload || !(payload.markers || []).length) return;
    renderMap(container, payload);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
