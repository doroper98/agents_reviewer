/* ============================================================
 * map block init — v3.4.0
 * Requires: window.maplibregl, window.d3 (loaded by archetype template).
 * Scans for .block-map elements, parses their JSON payload, and
 * instantiates a MapLibre map + d3-geo SVG overlay.
 * ========================================================== */
(function () {
  "use strict";

  if (typeof window === "undefined") return;
  if (window.MapBlocks && window.MapBlocks._initialized) return;

  var THEME_TILES = {
    light_mono: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
    burgundy_mono: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png",
  };

  var THEME_PALETTE = {
    light_mono: {
      bg: "#FAFAF7",
      ink2: "#4A4239",
      ink3: "#7A7166",
      ink4: "#A89F92",
      flow: "#9B9388",
      nodeFill: "#FFFFFF",
      nodeStroke: "#5C544B",
      highlight: "#C9A84C",
      highlightDeep: "#A88A2E",
      highlightHalo: "rgba(201,168,76,0.18)",
    },
    burgundy_mono: {
      bg: "#2B1A1A",
      ink2: "#D4C4AA",
      ink3: "#A89880",
      ink4: "#7A6E5E",
      flow: "#A89880",
      nodeFill: "#3D2828",
      nodeStroke: "#A89880",
      highlight: "#C9A84C",
      highlightDeep: "#D4B45C",
      highlightHalo: "rgba(201,168,76,0.22)",
    },
  };

  function buildStyle(tilesUrl) {
    return {
      version: 8,
      sources: {
        base: {
          type: "raster",
          tiles: [
            tilesUrl.replace("{s}", "a"),
            tilesUrl.replace("{s}", "b"),
            tilesUrl.replace("{s}", "c"),
          ],
          tileSize: 256,
          attribution: "© OpenStreetMap, © CARTO",
        },
      },
      layers: [{ id: "base-layer", type: "raster", source: "base" }],
    };
  }

  function initOne(rootEl) {
    if (!rootEl || rootEl.__mapInitialized) return;
    if (typeof maplibregl === "undefined" || typeof d3 === "undefined") {
      console.warn("[MapBlocks] maplibregl or d3 not loaded; skipping", rootEl);
      return;
    }
    var blockId = rootEl.getAttribute("data-block-id");
    var payloadEl = document.getElementById("map-payload-" + blockId);
    if (!payloadEl) {
      console.warn("[MapBlocks] payload element not found for", blockId);
      return;
    }
    var payload;
    try {
      payload = JSON.parse(payloadEl.textContent);
    } catch (e) {
      console.error("[MapBlocks] payload JSON parse failed:", e);
      return;
    }
    var theme = payload.theme || "burgundy_mono";
    var pal = THEME_PALETTE[theme] || THEME_PALETTE.burgundy_mono;
    var tilesUrl = THEME_TILES[theme] || THEME_TILES.burgundy_mono;

    var canvasEl = rootEl.querySelector(".block-map-canvas");
    var overlayEl = rootEl.querySelector(".block-map-overlay");
    if (!canvasEl || !overlayEl) return;

    var map = new maplibregl.Map({
      container: canvasEl,
      style: buildStyle(tilesUrl),
      center: payload.center || [122, 22],
      zoom: payload.zoom != null ? payload.zoom : 3.0,
      minZoom: 1,
      maxZoom: 8,
      attributionControl: { compact: true },
      pitchWithRotate: false,
      dragRotate: false,
    });
    map.touchZoomRotate.disableRotation();

    var svg = d3.select(overlayEl);
    function sizeOverlay() {
      var w = canvasEl.clientWidth, h = canvasEl.clientHeight;
      svg.attr("width", w).attr("height", h);
    }
    function project(lng, lat) {
      var p = map.project(new maplibregl.LngLat(lng, lat));
      return [p.x, p.y];
    }

    var markers = (payload.markers || []).map(function (m) {
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [m.lng, m.lat] },
        properties: m,
      };
    });
    var byId = {};
    (payload.markers || []).forEach(function (m) { byId[m.id] = m; });

    var arcFeatures = (payload.arcs || []).map(function (a) {
      var src = byId[a.from_id];
      var dst = byId[a.to_id];
      if (!src || !dst) return null;
      var interp = d3.geoInterpolate([src.lng, src.lat], [dst.lng, dst.lat]);
      var coords = d3.range(0, 1.0001, 1 / 64).map(function (t) { return interp(t); });
      return {
        type: "Feature",
        geometry: { type: "LineString", coordinates: coords },
        properties: a,
      };
    }).filter(Boolean);

    var transform = d3.geoTransform({
      point: function (lng, lat) {
        var p = project(lng, lat);
        this.stream.point(p[0], p[1]);
      },
    });
    var geoPath = d3.geoPath().projection(transform);

    var gFlows = svg.append("g").attr("class", "flows");
    var gNodes = svg.append("g").attr("class", "nodes");
    var gLabels = svg.append("g").attr("class", "labels");

    var flowSel = gFlows.selectAll("path")
      .data(arcFeatures)
      .join("path")
      .attr("fill", "none")
      .attr("stroke-linecap", "round")
      .attr("stroke", function (d) {
        return d.properties.highlight ? pal.highlight : pal.flow;
      })
      .attr("stroke-width", function (d) {
        return d.properties.highlight ? 2.4 : 1.1;
      })
      .attr("stroke-opacity", function (d) {
        return d.properties.highlight ? 0.92 : 0.55;
      })
      .attr("stroke-dasharray", function (d) {
        return d.properties.highlight ? "0" : "3,3";
      });

    var nodeSel = gNodes.selectAll("g.node")
      .data(markers, function (d) { return d.properties.id; })
      .join(function (enter) {
        var g = enter.append("g").attr("class", "node");
        g.append("circle").attr("class", "halo")
          .attr("r", function (d) { return d.properties.highlight ? 12 : 0; })
          .attr("fill", pal.highlightHalo);
        g.append("circle").attr("class", "dot")
          .attr("r", function (d) { return d.properties.highlight ? 5 : 3.2; })
          .attr("fill", function (d) {
            return d.properties.highlight ? pal.highlight : pal.nodeFill;
          })
          .attr("stroke", function (d) {
            return d.properties.highlight ? pal.highlightDeep : pal.nodeStroke;
          })
          .attr("stroke-width", function (d) {
            return d.properties.highlight ? 1.5 : 1;
          });
        return g;
      });

    var labelSel = gLabels.selectAll("text")
      .data(markers, function (d) { return d.properties.id; })
      .join("text")
      .attr("font-family", "'Noto Sans KR', sans-serif")
      .attr("font-size", function (d) { return d.properties.highlight ? 11 : 10; })
      .attr("font-weight", function (d) { return d.properties.highlight ? 700 : 500; })
      .attr("fill", function (d) {
        return d.properties.highlight ? pal.highlightDeep : pal.ink2;
      })
      .attr("paint-order", "stroke")
      .attr("stroke", pal.bg)
      .attr("stroke-width", 3)
      .attr("stroke-linejoin", "round")
      .text(function (d) { return d.properties.name || d.properties.id; });

    function render() {
      sizeOverlay();
      flowSel.attr("d", geoPath);
      nodeSel.attr("transform", function (d) {
        var p = project(d.geometry.coordinates[0], d.geometry.coordinates[1]);
        return "translate(" + p[0] + "," + p[1] + ")";
      });
      labelSel
        .attr("x", function (d) {
          return project(d.geometry.coordinates[0], d.geometry.coordinates[1])[0] + 8;
        })
        .attr("y", function (d) {
          return project(d.geometry.coordinates[0], d.geometry.coordinates[1])[1] + 4;
        });
    }

    map.on("load", render);
    map.on("move", render);
    map.on("resize", render);

    rootEl.__mapInitialized = true;
    rootEl.__mapInstance = map;
  }

  function initAll() {
    var nodes = document.querySelectorAll(".block-map");
    for (var i = 0; i < nodes.length; i++) initOne(nodes[i]);
  }

  window.MapBlocks = {
    initAll: initAll,
    initOne: initOne,
    _initialized: true,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
