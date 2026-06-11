/* maps.js — d3 + d3-geo + TopoJSON map renderer.
 *
 * v3.4.0~v4.1.0 의 maplibre-gl 의존 폐기 (mono guide §2).
 * v4.4.6 추가: d3.zoom() pan/zoom 인터랙션 + 소말릴란드 해칭 폴리곤.
 * v4.5.x: 소말릴란드 폴리곤·legend 를 viewport 가시성으로 게이트 (CHART-AP-13).
 * v7.2.0: 지도 어휘 격상 (사용자 승인 — samples/map_redesign_v7_compare.html).
 *   additive 신규 필드 — arcs.kind(flow/alt/tension)·weight(1~3)·label_t,
 *   markers.kind(chokepoint/port/military/city)·value·label_side,
 *   regions(국가 역할 색조), sea_labels(세리프 워터마크). 무지정 payload 는
 *   기존 렌더와 동일 (구 발행본 소급 안전). + graticule·해안 정의선·라벨 pill/헤일로.
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
      down: r('--down') || '#C9837A',
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

    // v7.2.0 — flow 방향 화살촉 + contested 지역 해치
    defs.append('marker').attr('id', 'map-arrow').attr('viewBox', '0 0 10 10')
      .attr('refX', 8).attr('refY', 5).attr('markerWidth', 5.5).attr('markerHeight', 5.5)
      .attr('orient', 'auto-start-reverse')
      .append('path').attr('d', 'M 0 1 L 9 5 L 0 9 Z').attr('fill', t.accent);
    defs.append('pattern').attr('id', 'map-contested').attr('patternUnits', 'userSpaceOnUse')
      .attr('width', 5).attr('height', 5).attr('patternTransform', 'rotate(45)')
      .append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 5)
      .attr('stroke', t.accent).attr('stroke-width', 1).attr('stroke-opacity', 0.5);

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
      // v7.2.0 — 경위선 graticule (카르토그래피 질감, 아주 옅게)
      gMap.append('path').datum(d3.geoGraticule10())
        .attr('d', path).attr('fill', 'none')
        .attr('stroke', t.text).attr('stroke-opacity', 0.045).attr('stroke-width', 0.5)
        .attr('vector-effect', 'non-scaling-stroke');
      gMap.selectAll('path.country').data(countries.features).join('path')
        .attr('class', 'country').attr('d', path).attr('fill', t.land).attr('stroke', 'none');
      // v7.2.0 — 해안 정의선 (대륙 외곽) + 내부 국경
      gMap.append('path').datum(topojson.merge(world, world.objects.countries.geometries))
        .attr('d', path).attr('fill', 'none')
        .attr('stroke', t.boundary).attr('stroke-width', 0.5).attr('stroke-opacity', 0.35)
        .attr('vector-effect', 'non-scaling-stroke');
      gMap.append('path').datum(borders)
        .attr('class', 'country-border').attr('d', path).attr('fill', 'none')
        .attr('stroke', t.boundary).attr('stroke-width', 0.7).attr('stroke-opacity', 0.7)
        .attr('vector-effect', 'non-scaling-stroke');

      // v7.2.0 — regions: 국가 역할 색조 (subject/ally/rival/contested).
      // composer 가 명시 emit 한 국가만 (CHART-AP-14/15 원칙 유지).
      const ROLE = {
        subject:   { fill: t.accent, op: 0.20 },
        ally:      { fill: t.text,   op: 0.10 },
        rival:     { fill: t.down,   op: 0.16 },
        contested: { fill: 'url(#map-contested)', op: null },
      };
      (payload.regions || []).forEach(rg => {
        if (!rg || !rg.name) return;
        const feat = countries.features.find(f =>
          f.properties && f.properties.name === rg.name);
        if (!feat) return;
        const role = ROLE[String(rg.role || 'ally').toLowerCase()] || ROLE.ally;
        const rp = gMap.append('path').attr('d', path(feat)).attr('fill', role.fill);
        if (role.op != null) rp.attr('fill-opacity', role.op);
        rp.attr('stroke', role.fill === 'url(#map-contested)' ? t.accent : role.fill)
          .attr('stroke-opacity', 0.5).attr('stroke-width', 0.7)
          .attr('vector-effect', 'non-scaling-stroke');
        if (rg.label) {
          const c = path.centroid(feat);
          gMap.append('text').attr('x', c[0]).attr('y', c[1]).attr('text-anchor', 'middle')
            .attr('font-family', 'IBM Plex Sans KR, Noto Sans KR').attr('font-size', 10)
            .attr('letter-spacing', 2).attr('font-weight', 600)
            .attr('fill', String(rg.role) === 'rival' ? t.down : t.text)
            .attr('fill-opacity', 0.75)
            .attr('data-region-label', '1').attr('data-base-font', 10)
            .text(rg.label);
        }
      });

      // v7.2.0 — sea_labels: 바다·해역 세리프 이탤릭 워터마크 (FT 지도 문법).
      (payload.sea_labels || []).forEach(sl => {
        if (!sl || !sl.name) return;
        const p = project(+sl.lng, +sl.lat);
        if (!p) return;
        gMap.append('text').attr('x', p[0]).attr('y', p[1]).attr('text-anchor', 'middle')
          .attr('font-family', 'Newsreader, Noto Serif KR, serif')
          .attr('font-style', 'italic').attr('font-size', 15).attr('letter-spacing', 5)
          .attr('fill', t.text).attr('fill-opacity', 0.30)
          .attr('data-sea-label', '1').attr('data-base-font', 15)
          .text(sl.name);
      });

      // CHART-AP-15: 소말릴란드 자동 렌더 제거. composer 가 명시 요청한 경우만.
    }

    loadWorld().then(world => {
      renderBase(world);

      const markersById = Object.fromEntries((payload.markers || []).map(m => [m.id, m]));
      // v7.2.0 — 선 굵기 사다리 (weight 1~3 = 물동량·중요도)
      const ARC_WEIGHT = { 1: 1.2, 2: 2.1, 3: 3.2 };
      const usedArcKinds = new Set();
      (payload.arcs || []).forEach(a => {
        const f = markersById[a.from_id], to = markersById[a.to_id];
        if (!f || !to) return;
        const p1 = project(+f.lng, +f.lat);
        const p2 = project(+to.lng, +to.lat);
        if (!p1 || !p2) return;
        const bow = Math.min(70, Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * 0.22);
        const kind = String(a.kind || '').toLowerCase();
        const g = gArc.append('g').attr('class', 'arc');
        let labelColor;
        if (kind === 'flow') {
          // 이동·수출 흐름 — 물색 헤일로 + 실선 + 방향 화살촉, 굵기 = weight
          usedArcKinds.add('flow');
          const sw = ARC_WEIGHT[a.weight] || 2.1;
          const d = curvedPath(p1, p2, bow);
          g.append('path').attr('d', d).attr('fill', 'none')
            .attr('stroke', t.water).attr('stroke-width', sw + 2.6).attr('stroke-opacity', 0.65)
            .attr('vector-effect', 'non-scaling-stroke');
          g.append('path').attr('d', d).attr('fill', 'none')
            .attr('stroke', t.accent).attr('stroke-width', sw).attr('stroke-opacity', 0.95)
            .attr('marker-end', 'url(#map-arrow)')
            .attr('vector-effect', 'non-scaling-stroke');
          labelColor = t.accent;
        } else if (kind === 'alt') {
          // 우회·대안 경로 — 긴 점선
          usedArcKinds.add('alt');
          g.append('path').attr('d', curvedPath(p1, p2, bow))
            .attr('fill', 'none').attr('stroke', t.muted)
            .attr('stroke-width', Math.max(1.2, (ARC_WEIGHT[a.weight] || 1.6) - 0.4))
            .attr('stroke-dasharray', '7,5').attr('stroke-opacity', 0.9)
            .attr('vector-effect', 'non-scaling-stroke');
          labelColor = t.muted;
        } else if (kind === 'tension') {
          // 대립·긴장 — 하락색 짧은 점선 + 중간 ✕ 글리프
          usedArcKinds.add('tension');
          const tp = g.append('path').attr('d', curvedPath(p1, p2, bow))
            .attr('fill', 'none').attr('stroke', t.down).attr('stroke-width', 1.3)
            .attr('stroke-dasharray', '2,4').attr('stroke-opacity', 0.85)
            .attr('vector-effect', 'non-scaling-stroke');
          try {
            const node = tp.node();
            const mid = node.getPointAtLength(node.getTotalLength() / 2);
            [[-1, -1, 1, 1], [-1, 1, 1, -1]].forEach(seg => {
              g.append('line')
                .attr('x1', mid.x + seg[0] * 4).attr('y1', mid.y + seg[1] * 4)
                .attr('x2', mid.x + seg[2] * 4).attr('y2', mid.y + seg[3] * 4)
                .attr('stroke', t.down).attr('stroke-width', 1.8)
                .attr('stroke-linecap', 'round')
                .attr('vector-effect', 'non-scaling-stroke');
            });
          } catch (e) { /* getPointAtLength 미지원 환경 — 글리프만 생략 */ }
          labelColor = t.down;
        } else {
          // 무지정 — 기존 렌더와 동일 (구 발행본 소급 안전)
          const color = a.highlight ? t.accent : t.muted;
          const dash = a.highlight ? null : '5,3';
          g.append('path').attr('d', curvedPath(p1, p2, bow))
            .attr('fill', 'none').attr('stroke', color)
            .attr('stroke-width', a.highlight ? 2.4 : 1.6)
            .attr('stroke-dasharray', dash).attr('opacity', 0.9)
            .attr('vector-effect', 'non-scaling-stroke');
          labelColor = color;
        }
        if (a.label) {
          // v7.2.0 — 경로 위 t 지점 (label_t 0~1, 기본 0.5) 의 물색 pill 라벨.
          // 줌 시 마커처럼 카운터-스케일 (.arc-pill + data-px/py).
          let pt;
          try {
            const node = g.select('path').node();
            const L = node.getTotalLength();
            pt = node.getPointAtLength(L * (a.label_t != null ? +a.label_t : 0.5));
          } catch (e) {
            pt = { x: (p1[0] + p2[0]) / 2, y: (p1[1] + p2[1]) / 2 - bow * 0.5 };
          }
          const tw = String(a.label).length * 10 + 14;
          const pill = gArc.append('g').attr('class', 'arc-pill')
            .attr('transform', `translate(${pt.x},${pt.y - 13})`)
            .attr('data-px', pt.x).attr('data-py', pt.y - 13);
          pill.append('rect').attr('x', -tw / 2).attr('y', -10).attr('width', tw)
            .attr('height', 16).attr('rx', 8)
            .attr('fill', t.water).attr('fill-opacity', 0.82)
            .attr('stroke', labelColor).attr('stroke-opacity', 0.35).attr('stroke-width', 0.6);
          pill.append('text').attr('x', 0).attr('y', 2).attr('text-anchor', 'middle')
            .attr('fill', labelColor).attr('font-family', 'Noto Sans KR')
            .attr('font-size', 10).attr('font-weight', 600)
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
      const usedMarkerKinds = new Set();
      (payload.markers || []).forEach(m => {
        const p = project(+m.lng, +m.lat);
        if (!p) return;
        const isHL = !!m.highlight;
        const color = isHL ? t.accent : t.muted;
        const kind = String(m.kind || '').toLowerCase();
        const g = gMarker.append('g').attr('class', 'marker')
          .attr('transform', `translate(${p[0]},${p[1]})`)
          .attr('data-px', p[0]).attr('data-py', p[1]);
        let r;
        if (kind === 'chokepoint') {
          // 병목 지점 — ◆ + 이중 링 (해협·운하·관문)
          usedMarkerKinds.add('chokepoint');
          r = 8;
          g.append('circle').attr('r', 11).attr('fill', 'none')
            .attr('stroke', t.accent).attr('stroke-opacity', 0.4).attr('stroke-width', 1);
          g.append('rect').attr('x', -5).attr('y', -5).attr('width', 10).attr('height', 10)
            .attr('transform', 'rotate(45)').attr('fill', t.accent)
            .attr('stroke', t.water).attr('stroke-width', 1.2);
        } else if (kind === 'port') {
          // 항만·터미널 — 이중 원
          usedMarkerKinds.add('port');
          r = isHL ? 6.5 : 5;
          g.append('circle').attr('r', r).attr('fill', t.water)
            .attr('stroke', color).attr('stroke-width', 1.6);
          g.append('circle').attr('r', isHL ? 2.6 : 2).attr('fill', color);
        } else if (kind === 'military') {
          // 군사 거점 — ▲
          usedMarkerKinds.add('military');
          r = 6;
          g.append('path').attr('d', 'M 0 -6 L 5.5 4 L -5.5 4 Z')
            .attr('fill', t.text).attr('fill-opacity', 0.85)
            .attr('stroke', t.water).attr('stroke-width', 1);
        } else {
          // 무지정/city — 기존 점 렌더와 동일 (구 발행본 소급 안전)
          r = isHL ? 6 : 4;
          g.append('circle').attr('r', r + 2).attr('fill', t.water).attr('opacity', 0.85);
          g.append('circle').attr('r', r).attr('fill', color)
            .attr('stroke', t.text).attr('stroke-width', isHL ? 1.0 : 0.6)
            .attr('vector-effect', 'non-scaling-stroke');
        }
        markerPositions.push({ m, px: p[0], py: p[1], r, isHL, gNode: g.node() });
      });
      const sorted = markerPositions.slice().sort((a, b) => (b.isHL ? 1 : 0) - (a.isHL ? 1 : 0));
      sorted.forEach(({ m, px, py, r, isHL }) => {
        if (!m.name) return;
        const text = String(m.name);
        const fontSize = 11;
        const labelW = text.length * 6.8;
        const labelH = fontSize + 2;
        // v7.2.0 — label_side 힌트가 있으면 그 후보를 1순위로 (composer 가
        // 권역 혼잡을 알고 지정한 경우). 없으면 기존 occupancy 순서 그대로.
        const SIDE = {
          right:  { x: px + r + 6,          y: py - labelH / 2, anchor: 'start' },
          left:   { x: px - r - 6 - labelW, y: py - labelH / 2, anchor: 'start' },
          top:    { x: px - labelW / 2,     y: py - r - 14,     anchor: 'start' },
          bottom: { x: px - labelW / 2,     y: py + r + 4,      anchor: 'start' },
        };
        let candidates = [SIDE.right, SIDE.left, SIDE.top, SIDE.bottom];
        const hint = SIDE[String(m.label_side || '').toLowerCase()];
        if (hint) candidates = [hint, ...candidates.filter(c => c !== hint)];
        let placed = null;
        for (const c of candidates) {
          if (!labelOcc.hits(c.x - 2, c.y - 2, labelW + 4, labelH + 4)) {
            placed = c; break;
          }
        }
        if (!placed) placed = candidates[0];
        // v7.2.0 — paint-order 물색 헤일로 (육지·경계선 위 가독)
        gLabel.append('text').attr('x', placed.x).attr('y', placed.y + labelH - 3)
          .attr('text-anchor', placed.anchor)
          .attr('font-family', 'Noto Sans KR').attr('font-size', fontSize)
          .attr('font-weight', isHL ? 700 : 500).attr('fill', t.text)
          .attr('stroke', t.water).attr('stroke-width', 3).attr('paint-order', 'stroke')
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
        // v7.2.0 — value 보조 행 (세리프, 이름 아래) — 마커가 수치 근거까지 운반
        if (m.value) {
          const vText = String(m.value);
          const vW = vText.length * 6.2;
          const vy = placed.y + labelH + 9;
          gLabel.append('text').attr('x', placed.x).attr('y', vy)
            .attr('text-anchor', placed.anchor)
            .attr('font-family', 'Noto Serif KR, serif').attr('font-size', 9.5)
            .attr('fill', isHL ? t.accent : t.muted)
            .attr('stroke', t.water).attr('stroke-width', 3).attr('paint-order', 'stroke')
            .attr('data-marker-label', '1')
            .text(vText);
          labelOcc.add(placed.x - 2, vy - 10, vW + 4, 12);
        }
      });
    });

    // 범례는 zoom 영향 받지 않게 svg 직속.
    if (payload.legend && payload.legend.length) {
      const lg = svg.append('g').attr('class', 'legend')
        .attr('transform', `translate(12, ${H - 12 - payload.legend.length * 16})`);
      payload.legend.forEach((l, i) => {
        const y = i * 16;
        const color = l.highlight ? t.accent : t.muted;
        if (l.kind === 'flow') {
          lg.append('line').attr('x1', 0).attr('y1', y + 5).attr('x2', 18).attr('y2', y + 5)
            .attr('stroke', t.accent).attr('stroke-width', 3)
            .attr('marker-end', 'url(#map-arrow)');
        } else if (l.kind === 'alt') {
          lg.append('line').attr('x1', 0).attr('y1', y + 5).attr('x2', 18).attr('y2', y + 5)
            .attr('stroke', t.muted).attr('stroke-width', 1.4).attr('stroke-dasharray', '7,5');
        } else if (l.kind === 'tension') {
          lg.append('line').attr('x1', 0).attr('y1', y + 5).attr('x2', 18).attr('y2', y + 5)
            .attr('stroke', t.down).attr('stroke-width', 1.3).attr('stroke-dasharray', '2,4');
        } else if (l.kind === 'chokepoint') {
          lg.append('rect').attr('x', 5).attr('y', y + 1).attr('width', 8).attr('height', 8)
            .attr('transform', `rotate(45 9 ${y + 5})`).attr('fill', t.accent);
        } else if (l.kind === 'military') {
          lg.append('path').attr('d', `M 9 ${y - 1} L 14 ${y + 9} L 4 ${y + 9} Z`)
            .attr('fill', t.text).attr('fill-opacity', 0.85);
        } else if (l.kind === 'line') {
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
        // v7.2.0 — arc 라벨 pill 은 마커처럼 그룹째 카운터-스케일
        gArc.selectAll('.arc-pill').each(function () {
          const sel = d3.select(this);
          const px = +sel.attr('data-px'), py = +sel.attr('data-py');
          sel.attr('transform', `translate(${px},${py}) scale(${1 / k})`);
        });
        // v7.2.0 — 바다·지역 워터마크도 화면상 크기 유지
        gMap.selectAll('text[data-sea-label], text[data-region-label]').each(function () {
          const sel = d3.select(this);
          sel.attr('font-size', (+sel.attr('data-base-font') || 12) / k);
        });
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

  // v5.3.0 — entry 애니메이션. 베이스맵 fade-in → 경로 dashoffset 그리기 →
  // 마커 r grow. prefers-reduced-motion 시 즉시 정적 렌더.
  function _motionEnabled() {
    if (!window.matchMedia) return true;
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function _applyMapEntryAnimation(container) {
    if (!_motionEnabled()) return;
    const svg = d3.select(container).select('svg');
    if (svg.empty()) return;
    // 베이스맵 (국가 경계 path with fill) 페이드 인
    svg.selectAll('path').each(function () {
      const node = this, sel = d3.select(node);
      const fill = sel.attr('fill');
      if (fill && fill !== 'none' && fill !== 'transparent') {
        sel.style('opacity', 0)
          .transition().duration(300).ease(d3.easeCubicOut)
          .style('opacity', 1);
      } else {
        // 경로 arc — dashoffset 그리기
        let len;
        try { len = node.getTotalLength(); } catch (e) { return; }
        if (!isFinite(len) || len < 4 || len > 8000) return;
        sel.attr('stroke-dasharray', `${len} ${len}`)
          .attr('stroke-dashoffset', len)
          .transition().delay(280).duration(700).ease(d3.easeCubicOut)
          .attr('stroke-dashoffset', 0)
          .on('end', function () { d3.select(this).attr('stroke-dasharray', null); });
      }
    });
    // 마커 r grow
    svg.selectAll('circle').each(function () {
      const node = this;
      const r = parseFloat(node.getAttribute('r') || '0');
      if (r < 1.5) return;
      d3.select(node).attr('r', 0)
        .transition().delay(700).duration(320).ease(d3.easeBackOut.overshoot(1.4))
        .attr('r', r);
    });
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

    // IntersectionObserver 가 있으면 viewport 진입 시 렌더 + 애니메이션.
    // 미지원 브라우저는 backward-compat 즉시 렌더 (애니메이션 X).
    if (!window.IntersectionObserver) {
      renderMap(container, payload);
      return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        io.unobserve(container);
        renderMap(container, payload);
        // renderMap 은 fetch (TopoJSON) 까지 포함 → fetch 끝나면 SVG 안착.
        // 추가 setTimeout 으로 안착 보장 후 애니메이션.
        setTimeout(() => _applyMapEntryAnimation(container), 50);
        break;
      }
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
    io.observe(container);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
