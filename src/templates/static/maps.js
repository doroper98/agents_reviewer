/* maps.js — d3 + d3-geo + TopoJSON map renderer.
 *
 * v3.4.0~v4.1.0 의 maplibre-gl 의존 폐기 (mono guide §2).
 * v4.4.6 추가: d3.zoom() pan/zoom 인터랙션 + 소말릴란드 해칭 폴리곤.
 * v4.5.x: 소말릴란드 폴리곤·legend 를 viewport 가시성으로 게이트 (CHART-AP-13).
 *   해당 지역이 화면에 안 잡히는 보고서에서는 둘 다 자동으로 사라짐 —
 *   "지도 = 보고서 주제와 정합" 원칙.
 *
 * 데이터 입력: <script type="application/json" id="map-payload">
 *   { center: [lng, lat], zoom: float,
 *     markers: [{id, name, lng, lat, highlight}],
 *     arcs: [{from_id, to_id, highlight?, label?}],
 *     legend?: [{label, kind, highlight?}] }
 *
 * 인터랙션: 휠/핀치 zoom, 드래그 pan, 컨트롤 버튼 (+/−/⟲).
 * 마커/라벨/호 두께는 zoom 시 카운터-스케일 → 화면상 크기 일정 유지.
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

  // 소말릴란드 (de facto 독립국가, 110m TopoJSON 은 소말리아에 통합) 의
  // 단순화된 경계 폴리곤. 정확한 행정경계 아님 — 시각적 강조 목적.
  // 좌표 출처: Natural Earth 1:50m disputed boundaries 단순화 (v4.4.6).
  const SOMALILAND_GEOJSON = {
    type: 'Feature',
    properties: { name: 'Somaliland' },
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [43.40, 11.10], [43.65, 10.85], [44.10, 10.95], [44.95, 11.30],
        [45.55, 11.55], [46.30, 11.55], [47.10, 11.20], [48.00, 11.30],
        [48.95, 10.10], [49.10, 9.40], [48.50, 8.50], [47.40, 8.10],
        [46.50, 8.05], [45.50, 8.10], [44.50, 8.30], [43.55, 8.65],
        [43.30, 9.20], [43.18, 9.85], [43.20, 10.50], [43.40, 11.10],
      ]],
    },
  };

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

    // SVG defs — 해칭 패턴 (소말릴란드 + 차트와 동일한 45° hatch-tight 변종)
    const defs = svg.append('defs');
    const hatchId = 'somaliland-hatch';
    defs.append('pattern')
      .attr('id', hatchId)
      .attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 6).attr('height', 6)
      .attr('patternTransform', 'rotate(45)')
      .call(p => {
        p.append('rect').attr('width', 6).attr('height', 6).attr('fill', t.land);
        p.append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 6)
          .attr('stroke', t.accent).attr('stroke-width', 1.4).attr('stroke-opacity', 0.85);
      });

    svg.append('rect').attr('width', W).attr('height', H).attr('fill', t.water);

    const center = payload.center || [0, 0];
    const baseZoom = payload.zoom || 3.0;
    const scale = 110 * baseZoom;
    const projection = d3.geoMercator()
      .center(center).scale(scale).translate([W / 2, H * 0.55]);
    const path = d3.geoPath(projection);

    // v4.4.6: 모든 콘텐츠를 단일 g 안에 — d3.zoom() transform 적용 대상.
    const gContent = svg.append('g').attr('class', 'map-content');
    const gMap = gContent.append('g').attr('class', 'map-base');
    const gArc = gContent.append('g').attr('class', 'arcs');
    const gMarker = gContent.append('g').attr('class', 'markers');
    const gLabel = gContent.append('g').attr('class', 'labels');

    function project(lng, lat) { return projection([lng, lat]); }

    // CHART-AP-15 (v5.0.1): 소말릴란드 (Somaliland) 자동 렌더 *완전 제거*.
    // v4.4.6 의 자동 추가 + v4.5.7 의 viewport gating 모두 부분적 해결이었음 —
    // 호른 오브 아프리카 가까운 경로(예: 호르무즈→싱가포르→동북아) 보고서는
    // viewport 가 인도양까지 확장되어 소말릴랜드가 무관함에도 그려졌다.
    // 결정: 어떤 보고서든 *composer 가 명시적으로 emit 한 마커/지역만* 표시.
    // 보고서 주제와 무관한 자동 annotation 일체 금지 (CHART-AP-14 강화).

    function renderBase(world) {
      if (!world) return;
      const countries = topojson.feature(world, world.objects.countries);
      const borders = topojson.mesh(world, world.objects.countries, (a, b) => a !== b);
      gMap.selectAll('path.country').data(countries.features).join('path')
        .attr('class', 'country').attr('d', path).attr('fill', t.land).attr('stroke', 'none');
      gMap.append('path').datum(borders)
        .attr('class', 'country-border').attr('d', path).attr('fill', 'none')
        .attr('stroke', t.boundary).attr('stroke-width', 0.7).attr('stroke-opacity', 0.7)
        .attr('vector-effect', 'non-scaling-stroke');

      // CHART-AP-15: 소말릴란드 자동 렌더 제거. composer 가 명시 요청한 경우만.
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
          .attr('stroke-dasharray', dash).attr('opacity', 0.9)
          .attr('vector-effect', 'non-scaling-stroke');
        if (a.label) {
          const mx = (p1[0] + p2[0]) / 2 + 4, my = (p1[1] + p2[1]) / 2 - 6 - bow * 0.5;
          g.append('text').attr('x', mx).attr('y', my).attr('text-anchor', 'middle')
            .attr('fill', color).attr('font-family', 'Noto Sans KR').attr('font-size', 10)
            .attr('font-weight', 600)
            .attr('data-arc-label', '1')
            .text(a.label);
        }
      });

      // v4.4.4 (CHART-AP-10): 마커 라벨 collision-aware placement.
      const labelOcc = (function () {
        const taken = [];
        return {
          hits: (x, y, w, h) => taken.some(b =>
            x < b.x + b.w && x + w > b.x && y < b.y + b.h && y + h > b.y),
          add: (x, y, w, h) => taken.push({ x, y, w, h }),
        };
      })();
      const markerPositions = [];
      (payload.markers || []).forEach(m => {
        const p = project(+m.lng, +m.lat);
        if (!p) return;
        const isHL = !!m.highlight;
        const r = isHL ? 6 : 4;
        const color = isHL ? t.accent : t.muted;
        const g = gMarker.append('g').attr('class', 'marker')
          .attr('transform', `translate(${p[0]},${p[1]})`)
          .attr('data-px', p[0]).attr('data-py', p[1]);
        g.append('circle').attr('r', r + 2).attr('fill', t.water).attr('opacity', 0.85);
        g.append('circle').attr('r', r).attr('fill', color)
          .attr('stroke', t.text).attr('stroke-width', isHL ? 1.0 : 0.6)
          .attr('vector-effect', 'non-scaling-stroke');
        markerPositions.push({ m, px: p[0], py: p[1], r, isHL, gNode: g.node() });
      });
      const sorted = markerPositions.slice().sort((a, b) => (b.isHL ? 1 : 0) - (a.isHL ? 1 : 0));
      sorted.forEach(({ m, px, py, r, isHL }) => {
        if (!m.name) return;
        const text = String(m.name);
        const fontSize = 11;
        const labelW = text.length * 6.8;
        const labelH = fontSize + 2;
        const candidates = [
          { x: px + r + 6,         y: py - labelH / 2,  anchor: 'start' },
          { x: px - r - 6 - labelW, y: py - labelH / 2, anchor: 'start' },
          { x: px - labelW / 2,     y: py - r - 14,     anchor: 'start' },
          { x: px - labelW / 2,     y: py + r + 4,      anchor: 'start' },
        ];
        let placed = null;
        for (const c of candidates) {
          if (!labelOcc.hits(c.x - 2, c.y - 2, labelW + 4, labelH + 4)) {
            placed = c; break;
          }
        }
        if (!placed) placed = candidates[0];
        gLabel.append('text').attr('x', placed.x).attr('y', placed.y + labelH - 3)
          .attr('text-anchor', placed.anchor)
          .attr('font-family', 'Noto Sans KR').attr('font-size', fontSize)
          .attr('font-weight', isHL ? 700 : 500).attr('fill', t.text)
          .attr('data-marker-label', '1')
          .text(text);
        const labelCenterX = placed.x + labelW / 2;
        const labelCenterY = placed.y + labelH / 2;
        const dist = Math.hypot(labelCenterX - px, labelCenterY - py);
        if (dist > r + 18) {
          gLabel.append('line')
            .attr('x1', px).attr('y1', py)
            .attr('x2', placed.x + (placed.anchor === 'start' ? -2 : labelW + 2))
            .attr('y2', placed.y + labelH / 2)
            .attr('stroke', t.muted).attr('stroke-width', 0.5).attr('stroke-opacity', 0.5)
            .attr('vector-effect', 'non-scaling-stroke');
        }
        labelOcc.add(placed.x - 2, placed.y - 2, labelW + 4, labelH + 4);
      });
    });

    // 범례는 zoom 영향 받지 않게 svg 직속.
    if (payload.legend && payload.legend.length) {
      const lg = svg.append('g').attr('class', 'legend')
        .attr('transform', `translate(12, ${H - 12 - payload.legend.length * 16})`);
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
    // CHART-AP-15: 소말릴란드 범례 자동 추가 제거.

    // v4.4.6 — d3.zoom() 인터랙션. transform 은 gContent 에만 적용.
    // 마커 dot/label/arc-label 텍스트는 zoom 시 카운터-스케일 (화면상 동일 크기).
    const zoomBehavior = d3.zoom()
      .scaleExtent([1, 8])
      .translateExtent([[-W * 0.5, -H * 0.5], [W * 1.5, H * 1.5]])
      .on('start', () => container.classList.add('dragging'))
      .on('end', () => container.classList.remove('dragging'))
      .on('zoom', (event) => {
        const k = event.transform.k;
        gContent.attr('transform', event.transform);
        // 마커 원 카운터-스케일 (translate 유지, scale 만 1/k 로)
        gMarker.selectAll('.marker').each(function () {
          const sel = d3.select(this);
          const px = +sel.attr('data-px'), py = +sel.attr('data-py');
          sel.attr('transform', `translate(${px},${py}) scale(${1 / k})`);
        });
        // 텍스트는 font-size 를 직접 조정 (translate 유지, scale 변환 X)
        gLabel.selectAll('text[data-marker-label]')
          .attr('font-size', 11 / k);
        gArc.selectAll('text[data-arc-label]')
          .attr('font-size', 10 / k);
      });

    svg.call(zoomBehavior);
    // 더블클릭 줌 비활성 (대신 버튼 사용)
    svg.on('dblclick.zoom', null);

    // 컨트롤 버튼 — map-card 안의 .map-controls 에 위임.
    const card = container.closest('.map-card');
    if (card) {
      card.querySelectorAll('[data-map-zoom]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          const op = btn.getAttribute('data-map-zoom');
          if (op === 'in') svg.transition().duration(220).call(zoomBehavior.scaleBy, 1.5);
          else if (op === 'out') svg.transition().duration(220).call(zoomBehavior.scaleBy, 1 / 1.5);
          else if (op === 'reset') svg.transition().duration(280).call(zoomBehavior.transform, d3.zoomIdentity);
        });
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
