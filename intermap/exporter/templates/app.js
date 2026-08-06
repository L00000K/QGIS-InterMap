(function() {
  "use strict";

  var FEAT = @@_feat_js@@;

  var map = L.map('map', {
    center: [0, 0], zoom: 2,
    maxZoom: 23,
    zoomControl: false,
    preferCanvas: true,
    contextmenu: true,
    contextmenuWidth: 180,
    contextmenuItems: [
      {text: 'Centre map here',  callback: function(e) { map.panTo(e.latlng); }},
      {text: 'Zoom in',          callback: function(e) { map.zoomIn(); }},
      {text: 'Zoom out',         callback: function(e) { map.zoomOut(); }},
      '-',
      {text: 'Copy lat, lon',    callback: function(e) {
        var t = e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6);
        try { navigator.clipboard.writeText(t); } catch(x) {}
      }},
      {text: 'Fit to all data',  callback: function() {
        try { map.fitBounds(bounds, {padding:[20,20]}); } catch(x) {}
      }}
    ]
  });
  var bounds = @@bounds_json@@;
  try { map.fitBounds(@@initial_bounds_json@@, {padding: [20, 20]}); }
  catch(e) { map.setView([0, 0], 2); }
  setTimeout(function() { map.invalidateSize(); }, 50);

  // ── Left panel close & toggle ─────────────────────────────────────────────
  // Registered immediately after map init so it works even if later sections fail.
  (function() {
    var panel = document.getElementById('left-panel');
    var chip  = document.getElementById('map-title-chip');
    var chipText = document.getElementById('map-title-chip-text');
    var chipBtn  = document.getElementById('map-title-chip-btn');

    // Populate chip text from the panel title
    if (chip && chipText) {
      var titleEl = document.getElementById('left-panel-title');
      chipText.textContent = titleEl ? (titleEl.textContent || titleEl.innerText || '') : '';
    }

    function showPanel() {
      if (!panel) return;
      panel.style.display = 'flex';
      if (chip) chip.classList.remove('visible');
      map.getContainer().classList.remove('chip-visible');
      map.invalidateSize();
    }
    function hidePanel() {
      if (!panel) return;
      panel.style.display = 'none';
      if (chip) chip.classList.add('visible');
      map.getContainer().classList.add('chip-visible');
      map.invalidateSize();
    }

    if (!panel) {
      return;
    }

    var closeBtn = document.getElementById('left-panel-close');
    if (closeBtn) closeBtn.addEventListener('click', hidePanel);
    // Only the ▼ button opens the panel; clicking a view item must NOT open the panel
    if (chipBtn) chipBtn.addEventListener('click', function(e) { e.stopPropagation(); showPanel(); });
    if (chip) chip.addEventListener('click', showPanel);

    // ── Populate chip map-view list ──────────────────────────────────────────
    var chipViews = document.getElementById('map-title-chip-views');
    if (chipViews && typeof THEMES !== 'undefined' && THEMES.length > 0) {
      var _chipViewEls = [];
      THEMES.forEach(function(th, i) {
        if (th.kind === 'text') return;   // notes are not views to jump to
        var el = document.createElement('div');
        el.className = 'mv-chip-item';
        el.textContent = th.name || ('Map View ' + (i + 1));
        el.title = th.name || '';
        el.addEventListener('click', function(e) {
          e.stopPropagation();
          _chipViewEls.forEach(function(x) { x.classList.remove('active'); });
          el.classList.add('active');
          if (typeof applyTheme === 'function') applyTheme(i);
        });
        _chipViewEls.push(el);
        chipViews.appendChild(el);
      });
      // Also mark active when map-views-section items are clicked
      var mvSection = document.getElementById('map-views-section');
      if (mvSection) {
        mvSection.addEventListener('click', function(e) {
          var idx = parseInt(e.target.closest && e.target.closest('[data-mv-idx]') && e.target.closest('[data-mv-idx]').dataset.mvIdx, 10);
          if (!isNaN(idx)) {
            _chipViewEls.forEach(function(x) { x.classList.remove('active'); });
            if (_chipViewEls[idx]) _chipViewEls[idx].classList.add('active');
          }
        });
      }
      // Mirror the active state when first map view auto-loads
      window._setChipViewActive = function(idx) {
        _chipViewEls.forEach(function(x) { x.classList.remove('active'); });
        if (_chipViewEls[idx]) _chipViewEls[idx].classList.add('active');
      };
    }

    // Left-panel resize handle
    var rh = document.getElementById('left-panel-resize-h');
    if (rh) {
      var _lpResizeStart = null;
      rh.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        _lpResizeStart = { x: e.clientX, w: panel.offsetWidth };
        rh.classList.add('dragging');
        e.preventDefault();
      });
      document.addEventListener('mousemove', function(e) {
        if (!_lpResizeStart) return;
        var nw = Math.max(200, Math.min(600, _lpResizeStart.w + e.clientX - _lpResizeStart.x));
        panel.style.width = nw + 'px';
        map.invalidateSize();
      });
      document.addEventListener('mouseup', function() {
        if (!_lpResizeStart) return;
        _lpResizeStart = null;
        rh.classList.remove('dragging');
      });
    }

    // Title block collapse toggle
    var cadHdr = document.querySelector('.cad-block-hdr');
    if (cadHdr) {
      cadHdr.addEventListener('click', function() {
        var body = cadHdr.nextElementSibling;
        var btn  = cadHdr.querySelector('.cad-collapse-btn');
        var collapsed = body.classList.toggle('collapsed');
        btn.innerHTML = collapsed ? '&#9660;' : '&#9650;';
        btn.setAttribute('aria-label', collapsed ? 'Expand title block' : 'Collapse title block');
      });
    }

    // Changelog collapse toggle
    var clHdr = document.getElementById('changelog-hdr');
    if (clHdr) {
      clHdr.addEventListener('click', function() {
        var list = document.getElementById('changelog-list');
        var btn  = clHdr.querySelector('.cad-collapse-btn');
        if (!list) return;
        var collapsed = list.classList.toggle('collapsed');
        // Chevron points the way the click will move the list: up to open it,
        // down to put it away again. The arrow itself is drawn in CSS.
        btn.classList.toggle('up', collapsed);
        btn.classList.toggle('down', !collapsed);
        btn.setAttribute('aria-label', collapsed ? 'Expand changelog' : 'Collapse changelog');
      });
    }
  })();

  var LAYERS = @@layers_json@@;
  var INCLUDE_LEGEND = @@include_legend@@;
  var INCLUDE_LAYERS = @@include_layers@@;
  var LAYER_TREE = @@tree_json@@;
  var THEMES = @@themes_json@@;
  var _cogProxy = @@_cog_proxy_json@@;

  // ── Basemap (optional) ───────────────────────────────────────────────────
  var INCLUDE_BASEMAP = @@include_basemap_json@@;
  var basemap = null;
  var _basemapGreyscale = @@basemap_greyscale_json@@;
  if (INCLUDE_BASEMAP) {
    basemap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxNativeZoom: 19,
      maxZoom: 23,
      className: 'basemap-tiles'
    }).addTo(map);
  }

  // Greyscale is a property of the basemap, not a one-off style tweak: applying
  // it to the tile container alone gets wiped whenever Leaflet rebuilds that
  // container (theme switches, opacity changes, re-adds), which is why the
  // basemap kept reverting to colour. Keep the flag and re-assert it.
  function setBasemapGreyscale(on) {
    _basemapGreyscale = !!on;
    var cls = 'basemap-greyscale';
    if (_basemapGreyscale) map.getContainer().classList.add(cls);
    else map.getContainer().classList.remove(cls);
    var cb = document.getElementById('basemap-greyscale');
    if (cb && cb.checked !== _basemapGreyscale) cb.checked = _basemapGreyscale;
  }
  if (basemap) {
    setBasemapGreyscale(_basemapGreyscale);
    // Re-assert after any event that can rebuild or replace the tile container.
    basemap.on('add load', function() { setBasemapGreyscale(_basemapGreyscale); });
    map.on('baselayerchange overlayadd overlayremove zoomend', function() {
      setBasemapGreyscale(_basemapGreyscale);
    });
  }

  // ── Scale bar (built-in) ──────────────────────────────────────────────────
  L.control.scale({position: 'bottomleft', imperial: true, metric: true}).addTo(map);

  // ── Fullscreen ────────────────────────────────────────────────────────────
  try {
    if (typeof L.Control.Fullscreen !== 'undefined') {
      new L.Control.Fullscreen({
        position: 'topleft',
        title: {false: 'Enter fullscreen', true: 'Exit fullscreen'}
      }).addTo(map);
    }
  } catch(e) { console.warn('Fullscreen plugin error:', e); }

  // ── Mini-map overview ────────────────────────────────────────────────────
  if (FEAT.minimap) {
    try {
      if (typeof L.Control.MiniMap !== 'undefined') {
        var miniTile = L.tileLayer(
          'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19});
        new L.Control.MiniMap(miniTile, {
          position: 'bottomright', toggleDisplay: true, minimized: true,
          width: 160, height: 160
        }).addTo(map);
      }
    } catch(e) { console.warn('MiniMap plugin error:', e); }
  }


  // ── Helpers ──────────────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // Return the inner SVG element(s) for a marker shape centred at (cx, cy)
  // with circumradius r. Used by both map markers and legend swatches.
  function shapeSvgInner(shape, cx, cy, r, fill, fillOp, stroke, strokeW, strokeOp) {
    if (strokeOp == null) strokeOp = 1;
    var attrs = ' fill="' + escHtml(fill) + '" fill-opacity="' + fillOp + '"'
              + ' stroke="' + escHtml(stroke) + '" stroke-width="' + strokeW + '"'
              + ' stroke-opacity="' + strokeOp + '"';
    function poly(pts) {
      return '<polygon points="' + pts.map(function(p) { return p[0] + ',' + p[1]; }).join(' ') + '"' + attrs + '/>';
    }
    function regular(n, rot) {
      var pts = [];
      for (var i = 0; i < n; i++) {
        var a = rot + i * 2 * Math.PI / n;
        pts.push([(cx + r * Math.sin(a)).toFixed(2), (cy - r * Math.cos(a)).toFixed(2)]);
      }
      return poly(pts);
    }
    function starPts(points, outer, inner, rot) {
      var pts = [];
      for (var i = 0; i < points * 2; i++) {
        var rad = (i % 2 === 0) ? outer : inner;
        var a = rot + i * Math.PI / points;
        pts.push([(cx + rad * Math.sin(a)).toFixed(2), (cy - rad * Math.cos(a)).toFixed(2)]);
      }
      return poly(pts);
    }
    switch (shape) {
      case 'square':
        return '<rect x="' + (cx - r) + '" y="' + (cy - r) + '" width="' + (2 * r) + '" height="' + (2 * r) + '"' + attrs + '/>';
      case 'diamond':
        return poly([[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]]);
      case 'triangle':
        return regular(3, 0);
      case 'pentagon':
        return regular(5, 0);
      case 'hexagon':
        return regular(6, 0);
      case 'octagon':
        return regular(8, Math.PI / 8);
      case 'star':
        return starPts(5, r, r * 0.5, 0);
      case 'cross':
        return '<path d="M' + cx + ' ' + (cy - r) + ' V' + (cy + r) + ' M' + (cx - r) + ' ' + cy + ' H' + (cx + r) + '"'
             + ' stroke="' + escHtml(stroke !== 'none' ? stroke : fill) + '" stroke-width="' + Math.max(1.5, strokeW * 2) + '" fill="none"/>';
      case 'x':
        return '<path d="M' + (cx - r) + ' ' + (cy - r) + ' L' + (cx + r) + ' ' + (cy + r)
             + ' M' + (cx + r) + ' ' + (cy - r) + ' L' + (cx - r) + ' ' + (cy + r) + '"'
             + ' stroke="' + escHtml(stroke !== 'none' ? stroke : fill) + '" stroke-width="' + Math.max(1.5, strokeW * 2) + '" fill="none"/>';
      default: // circle
        return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"' + attrs + '/>';
    }
  }

  function makeMarker(latlng, style, paneName) {
    // Hybrid: use the QGIS-rendered SVG when available (exact symbology)
    if (style.markerSvg) {
      var m = style.markerSvg;
      // vw/vh are the 2× SVG coordinate space; w/h are the 1× CSS display size.
      // This gives crisp rendering on HiDPI screens for any rasterized effects.
      var vw = m.vw !== undefined ? m.vw : m.w;
      var vh = m.vh !== undefined ? m.vh : m.h;
      var html = '<svg width="' + m.w + '" height="' + m.h + '" viewBox="0 0 ' + vw + ' ' + vh + '"'
               + ' xmlns="http://www.w3.org/2000/svg" style="overflow:visible">' + m.inner + '</svg>';
      var svgIcon = L.divIcon({ html: html, className: 'qgis-marker',
                                 iconSize: [m.w, m.h], iconAnchor: [m.ax, m.ay] });
      var svgOpts = { icon: svgIcon };
      if (paneName) svgOpts.pane = paneName;
      return L.marker(latlng, svgOpts);
    }
    var size = style.markerSize || 8;
    var shape = style.markerShape || 'circle';
    var fill = style.markerColor || '#3388ff';
    var fillOp = style.markerOpacity != null ? style.markerOpacity : 0.9;
    var stroke = style.markerStrokeColor || '#555555';
    var strokeW = style.markerStrokeWidth != null ? style.markerStrokeWidth : 1;
    var strokeOp = (style.markerStrokeOpacity != null) ? style.markerStrokeOpacity : 1;
    if (shape === 'circle') {
      var copts = {
        radius: size / 2,
        fillColor: fill, fillOpacity: fillOp,
        color: stroke, weight: strokeW, opacity: strokeOp
      };
      if (paneName) copts.pane = paneName;
      return L.circleMarker(latlng, copts);
    }
    var pad = Math.max(strokeW, 1) + 2;
    var box = size + pad * 2;
    var c = box / 2, r = size / 2;
    var inner = shapeSvgInner(shape, c, c, r, fill, fillOp, stroke, strokeW, strokeOp);
    var angle = style.markerAngle || 0;
    var rot = angle ? ' transform="rotate(' + angle + ' ' + c + ' ' + c + ')"' : '';
    var svg = '<svg width="' + box + '" height="' + box
            + '" xmlns="http://www.w3.org/2000/svg" style="overflow:visible">'
            + '<g' + rot + '>' + inner + '</g></svg>';
    var icon = L.divIcon({ html: svg, className: 'qgis-marker',
                            iconSize: [box, box], iconAnchor: [c, c] });
    var mopts = { icon: icon };
    if (paneName) mopts.pane = paneName;
    return L.marker(latlng, mopts);
  }

  function resolveStyle(styleMap, props) {
    var t = styleMap.type;
    if (t === 'single') return styleMap.style;
    if (t === 'categorized') {
      var propVal = props[styleMap.field];
      var val = (propVal == null) ? null : String(propVal);
      for (var i = 0; i < styleMap.entries.length; i++) {
        var ev = styleMap.entries[i].value;
        var entVal = (ev == null) ? null : String(ev);
        if (entVal === val) return styleMap.entries[i].style;
      }
      return styleMap.default || {};
    }
    if (t === 'graduated') {
      var v = parseFloat(props[styleMap.field]);
      for (var i = 0; i < styleMap.entries.length; i++) {
        var e = styleMap.entries[i];
        if (v >= e.min && v <= e.max) return e.style;
      }
      return styleMap.default || {};
    }
    if (t === 'rule') {
      return (styleMap.entries[0] && styleMap.entries[0].style) || styleMap.default || {};
    }
    return {};
  }

  function resolveEntryIndex(styleMap, props) {
    var t = styleMap.type;
    if (t === 'categorized') {
      var propVal = props[styleMap.field];
      var val = (propVal == null) ? null : String(propVal);
      for (var i = 0; i < styleMap.entries.length; i++) {
        var ev = styleMap.entries[i].value;
        var entVal = (ev == null) ? null : String(ev);
        if (entVal === val) return i;
      }
      return -1;
    }
    if (t === 'graduated') {
      var v = parseFloat(props[styleMap.field]);
      for (var i = 0; i < styleMap.entries.length; i++) {
        var e = styleMap.entries[i];
        if (v >= e.min && v <= e.max) return i;
      }
      return -1;
    }
    return -1;
  }

  function leafletPathStyle(s) {
    var ps = {
      color: s.color || '#3388ff',
      weight: s.weight != null ? s.weight : 2,
      opacity: s.opacity != null ? s.opacity : 1,
      fillColor: s.fillColor || s.color || '#3388ff',
      fillOpacity: s.fillOpacity != null ? s.fillOpacity : 0.4
    };
    if (s.dashArray) ps.dashArray = s.dashArray;
    return ps;
  }

  // ── Hatch / pattern fills (canvas renderer accepts CanvasPattern as fillStyle)
  var _hatchCache = {};
  function hatchPattern(h) {
    var key = JSON.stringify(h);
    if (key in _hatchCache) return _hatchCache[key];
    var pat = null;
    try {
      var s = Math.max(4, Math.round(h.spacing || 6));
      var cv = document.createElement('canvas');
      cv.width = s; cv.height = s;
      var ctx = cv.getContext('2d');
      ctx.globalAlpha = h.opacity != null ? h.opacity : 1;
      ctx.strokeStyle = h.color || '#000';
      ctx.fillStyle = h.color || '#000';
      ctx.lineWidth = h.width || 1;
      var k = h.kind;
      if (k === 'dots') {
        ctx.beginPath();
        ctx.arc(s / 2, s / 2, Math.min(s / 2 - 0.5, Math.max(0.8, (h.size || 2) / 2)), 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.beginPath();
        if (k === 'hor' || k === 'cross') { ctx.moveTo(0, s / 2); ctx.lineTo(s, s / 2); }
        if (k === 'ver' || k === 'cross') { ctx.moveTo(s / 2, 0); ctx.lineTo(s / 2, s); }
        if (k === 'bdiag' || k === 'diagcross') {
          ctx.moveTo(0, s); ctx.lineTo(s, 0);
          ctx.moveTo(-1, 1); ctx.lineTo(1, -1);
          ctx.moveTo(s - 1, s + 1); ctx.lineTo(s + 1, s - 1);
        }
        if (k === 'fdiag' || k === 'diagcross') {
          ctx.moveTo(0, 0); ctx.lineTo(s, s);
          ctx.moveTo(s - 1, -1); ctx.lineTo(s + 1, 1);
          ctx.moveTo(-1, s - 1); ctx.lineTo(1, s + 1);
        }
        ctx.stroke();
      }
      pat = ctx.createPattern(cv, 'repeat');
    } catch (e) { pat = null; }
    _hatchCache[key] = pat;
    return pat;
  }

  function polygonPathStyle(s) {
    var ps = leafletPathStyle(s);
    if (s.fillHatch) {
      var pat = hatchPattern(s.fillHatch);
      if (pat) { ps.fillColor = pat; ps.fillOpacity = 1; }
      else {
        // Pattern creation failed — approximate with translucent solid colour
        ps.fillColor = s.fillHatch.color || '#888';
        ps.fillOpacity = (s.fillHatch.opacity != null ? s.fillHatch.opacity : 1) * 0.35;
      }
    }
    return ps;
  }

  // ── Data export helpers (shared by the attribute table & the toolbar) ─────
  function _downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }
  function _safeName(name) {
    return String(name || 'layer').replace(/[^\w.-]+/g, '_');
  }
  function _layerCSV(item) {
    var feats = item.ld.geojson && item.ld.geojson.features;
    if (!feats || !feats.length) return null;
    var cols = [], seen = {};
    feats.forEach(function(f) {
      var p = f.properties || {};
      Object.keys(p).forEach(function(k) { if (!(k in seen)) { seen[k] = 1; cols.push(k); } });
    });
    var esc = function(v) { return '"' + String(v).replace(/"/g, '""') + '"'; };
    var lines = [cols.map(esc).join(',')];
    feats.forEach(function(f) {
      var p = f.properties || {};
      lines.push(cols.map(function(c) { return p[c] == null ? '' : esc(p[c]); }).join(','));
    });
    return lines.join('\n');
  }

  // Vector layers currently on the map, in legend order.
  function _vectorItems() {
    return legendItems.filter(function(it) { return it.ld && it.ld.kind === 'vector'; });
  }

  // ── Swatch SVG ───────────────────────────────────────────────────────────
  var _swatchPatternId = 0;
  function swatchSvg(geomType, style, rasterLegend) {
    var W = 20, H = 16;
    var svg = '<svg width="' + W + '" height="' + H + '" xmlns="http://www.w3.org/2000/svg">';
    if (geomType === 'point') {
      if (style.markerSvg) {
        var m = style.markerSvg;
        // Use the 2× SVG coordinate space (vw/vh) so the content fills the viewBox correctly.
        var vw = m.vw !== undefined ? m.vw : m.w;
        var vh = m.vh !== undefined ? m.vh : m.h;
        return '<svg width="' + W + '" height="' + H + '" xmlns="http://www.w3.org/2000/svg">'
             + '<svg x="2" y="1" width="' + (W - 4) + '" height="' + (H - 2) + '"'
             + ' viewBox="0 0 ' + vw + ' ' + vh + '" preserveAspectRatio="xMidYMid meet">'
             + m.inner + '</svg></svg>';
      }
      var r = Math.min(6, Math.max(3, (style.markerSize || 8) / 2));
      var cx = W / 2, cy = H / 2;
      svg += shapeSvgInner(
        style.markerShape || 'circle', cx, cy, r,
        style.markerColor || '#3388ff',
        style.markerOpacity != null ? style.markerOpacity : 0.9,
        style.markerStrokeColor || '#666',
        Math.min(1.5, style.markerStrokeWidth != null ? style.markerStrokeWidth : 1),
        style.markerStrokeOpacity != null ? style.markerStrokeOpacity : 1
      );
    } else if (geomType === 'line') {
      var w = Math.min(5, Math.max(1, style.weight || 2));
      svg += '<line x1="1" y1="' + (H/2) + '" x2="' + (W-1) + '" y2="' + (H/2) + '"'
          + ' stroke="' + escHtml(style.color || '#3388ff') + '"'
          + ' stroke-opacity="' + (style.opacity != null ? style.opacity : 1) + '"'
          + ' stroke-width="' + w + '"/>';
    } else if (geomType === 'raster') {
      var rl = rasterLegend || {};
      if (rl.type === 'paletted' && rl.classes && rl.classes.length) {
        var c0 = rl.classes[0].color || '#aaa';
        svg += '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
            + ' fill="' + escHtml(c0) + '" stroke="#999" stroke-width="0.5"/>';
      } else if ((rl.type === 'pseudocolor' || rl.type === 'gray') && rl.stops && rl.stops.length) {
        var gid = 'rsw' + Math.random().toString(36).slice(2, 7);
        var stSvg = rl.stops.map(function(s, i) {
          var pct = rl.stops.length > 1 ? Math.round(100 * i / (rl.stops.length - 1)) : 100;
          return '<stop offset="' + pct + '%" stop-color="' + escHtml(s.color) + '"/>';
        }).join('');
        svg += '<defs><linearGradient id="' + gid + '">' + stSvg + '</linearGradient></defs>'
            + '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
            + ' fill="url(#' + gid + ')" stroke="#999" stroke-width="0.5"/>';
      } else if (rl.type === 'gray') {
        var gid2 = 'rsw' + Math.random().toString(36).slice(2, 7);
        var g1 = rl.blackFirst ? '#000' : '#fff', g2 = rl.blackFirst ? '#fff' : '#000';
        svg += '<defs><linearGradient id="' + gid2 + '"><stop offset="0%" stop-color="' + g1 + '"/>'
            + '<stop offset="100%" stop-color="' + g2 + '"/></linearGradient></defs>'
            + '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
            + ' fill="url(#' + gid2 + ')" stroke="#999" stroke-width="0.5"/>';
      } else {
        var hid = 'rsh' + Math.random().toString(36).slice(2, 7);
        svg += '<defs><pattern id="' + hid + '" patternUnits="userSpaceOnUse" width="4" height="4">'
            + '<path d="M0,4 L4,0" stroke="#777" stroke-width="1"/></pattern></defs>'
            + '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
            + ' fill="url(#' + hid + ')" stroke="#999" stroke-width="1"/>';
      }
    } else {
      var fillAttr = escHtml(style.fillColor || '#3388ff');
      var fillOpAttr = (style.fillOpacity != null ? style.fillOpacity : 0.4);
      if (style.fillHatch) {
        var h = style.fillHatch, sp = 5, pid = 'swp' + (++_swatchPatternId);
        var pi = '';
        if (h.kind === 'dots') {
          pi = '<circle cx="' + (sp/2) + '" cy="' + (sp/2) + '" r="1" fill="' + escHtml(h.color || '#000') + '"/>';
        } else {
          var d = '';
          if (h.kind === 'hor'   || h.kind === 'cross')     d += 'M0 ' + (sp/2) + ' H' + sp + ' ';
          if (h.kind === 'ver'   || h.kind === 'cross')     d += 'M' + (sp/2) + ' 0 V' + sp + ' ';
          if (h.kind === 'bdiag' || h.kind === 'diagcross') d += 'M0 ' + sp + ' L' + sp + ' 0 ';
          if (h.kind === 'fdiag' || h.kind === 'diagcross') d += 'M0 0 L' + sp + ' ' + sp + ' ';
          pi = '<path d="' + d + '" stroke="' + escHtml(h.color || '#000') + '" stroke-width="' + (h.width || 1) + '"/>';
        }
        svg += '<defs><pattern id="' + pid + '" patternUnits="userSpaceOnUse" width="' + sp + '" height="' + sp + '">'
            + pi + '</pattern></defs>';
        fillAttr = 'url(#' + pid + ')';
        fillOpAttr = (h.opacity != null ? h.opacity : 1);
      }
      svg += '<rect x="1" y="1" width="' + (W-2) + '" height="' + (H-2) + '"'
          + ' fill="' + fillAttr + '"'
          + ' fill-opacity="' + fillOpAttr + '"'
          + ' stroke="' + escHtml(style.color || '#333') + '"'
          + ' stroke-opacity="' + (style.opacity != null ? style.opacity : 1) + '"'
          + (style.dashArray ? ' stroke-dasharray="3 2"' : '')
          + ' stroke-width="' + Math.min(3, style.weight || 1) + '"/>';
    }
    return svg + '</svg>';
  }

  // ── Layer builder ────────────────────────────────────────────────────────
  // Highest number of stroke layers across a line layer's styleMap entries —
  // determines how many casing underlays we need to stack.
  function _maxStrokeLevels(styleMap) {
    var max = 0;
    function consider(s) {
      if (s && s.strokes && s.strokes.length > max) max = s.strokes.length;
    }
    if (!styleMap) return 0;
    consider(styleMap.style);
    consider(styleMap.default);
    (styleMap.entries || []).forEach(function(e) { consider(e.style); });
    return max;
  }

  // Style for one stroke level of a feature (level 0 = bottom casing). Returns
  // null when this feature has no stroke at that level (drawn invisibly).
  function _strokeLevelStyle(featStyle, level) {
    var strokes = featStyle && featStyle.strokes;
    if (!strokes || !strokes.length) {
      // single-stroke line: only the top level carries the flat style
      return null;
    }
    var s = strokes[level];
    if (!s) return { stroke: false, fill: false };
    if (s.tick) return { stroke: false, fill: false };  // ticks drawn separately
    return {
      color: s.color || '#3388ff',
      weight: s.weight != null ? s.weight : 2,
      opacity: s.opacity != null ? s.opacity : 1,
      dashArray: s.dashArray || null,
      fill: false, lineCap: 'round', lineJoin: 'round'
    };
  }

  function buildVectorLayer(item) {
    var ld = item.ld;
    var featFilter = function(feature) {
      if (item.filterFn && !item.filterFn(feature)) return false;
      if (item.layerFilterFn && !item.layerFilterFn(feature)) return false;
      if (item.hiddenClasses && item.hiddenClasses.length) {
        var idx = resolveEntryIndex(item.ld.styleMap, feature.properties || {});
        if (item.hiddenClasses.indexOf(idx) !== -1) return false;
      }
      return true;
    };
    var opts = {
      pane: item.paneName,
      onEachFeature: onEachFeature,
      filter: featFilter
    };
    // Cased / multi-stroke lines: stack one non-interactive geoJSON per lower
    // stroke level beneath the interactive top layer, so casing + core (and
    // any tick overlay) reproduce QGIS's layered line symbology.
    item.casings = [];
    item.tickStrokes = null;
    if (ld.geomType === 'line') {
      var levels = _maxStrokeLevels(ld.styleMap);
      if (levels > 1) {
        // levels-1 underlays (bottom→top); the top level is the interactive layer
        for (var lv = 0; lv < levels - 1; lv++) (function(lv) {
          var casing = L.geoJSON(ld.geojson, {
            pane: item.paneName,
            interactive: false,
            filter: featFilter,
            renderer: L.canvas({ pane: item.paneName }),
            style: function(feature) {
              return _strokeLevelStyle(
                resolveStyle(ld.styleMap, feature.properties || {}), lv);
            }
          });
          item.casings.push(casing);
        })(lv);
      }
      item.tickStrokes = true;  // let the tick overlay pass inspect this layer
    }
    if (ld.geomType === 'point') {
      opts.pointToLayer = function(feature, latlng) {
        var mkr = makeMarker(latlng, resolveStyle(ld.styleMap, feature.properties || {}), item.paneName);
        mkr._origLatLng = latlng;
        return mkr;
      };
    } else if (ld.geomType === 'line') {
      // Top (core) stroke is the interactive layer.
      opts.style = function(feature) {
        var fs = resolveStyle(ld.styleMap, feature.properties || {});
        if (fs && fs.strokes && fs.strokes.length) {
          var top = _strokeLevelStyle(fs, fs.strokes.length - 1);
          if (top) return top;
          // top level is a tick stroke with no core — draw an invisible hit line
          return { color: fs.color || '#3388ff', weight: Math.max(6, fs.weight || 2),
                   opacity: 0, fill: false };
        }
        return polygonPathStyle(fs);
      };
      opts.renderer = L.canvas({ pane: item.paneName });
    } else {
      opts.style = function(feature) {
        return polygonPathStyle(resolveStyle(ld.styleMap, feature.properties || {}));
      };
      opts.renderer = L.canvas({ pane: item.paneName });
    }
    var geoLayer = L.geoJSON(ld.geojson, opts);
    if (item.groupEnabled && item.groupMode === 'cluster' && ld.geomType === 'point' && typeof L.markerClusterGroup !== 'undefined') {
      item.spreadMarkers = [];
      var cg = L.markerClusterGroup({
        chunkedLoading: true,
        maxClusterRadius: 80,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true
      });
      cg.addLayer(geoLayer);
      return cg;
    }
    return geoLayer;
  }

  function buildRasterLayer(item) {
    return L.imageOverlay('data:image/png;base64,' + item.ld.data, item.ld.bounds, {
      opacity: 1, pane: item.paneName
    });
  }

  function buildWmsLayer(item) {
    var ld = item.ld;
    var op = (ld.opacity != null) ? ld.opacity : 1;
    // XYZ and WMTS tile services use a URL template — serve directly as tile layer
    if (ld.tileType === 'xyz' || ld.tileType === 'wmts') {
      return L.tileLayer(ld.wmsUrl, { pane: item.paneName, maxZoom: 23, opacity: op });
    }
    return L.tileLayer.wms(ld.wmsUrl, {
      layers:      ld.wmsLayers,
      format:      ld.wmsFormat  || 'image/png',
      styles:      ld.wmsStyles  || '',
      version:     ld.wmsVersion || '1.1.1',
      transparent: true,
      opacity:     op,
      pane:        item.paneName,
      maxZoom:     23
    });
  }

  // ── Cloud Optimized GeoTIFF (remote raster on blob storage) ─────────────
  // Loaded client-side via geotiff.js + georaster-layer-for-leaflet, which
  // stream the COG using HTTP range requests. The blob MUST send CORS headers
  // (Access-Control-Allow-Origin + allow the Range request header) or the
  // browser will refuse to fetch it.
  var _georasterLoading = false, _georasterQueue = [];
  function _loadGeoRaster(cb) {
    if (window.parseGeoraster && window.GeoRasterLayer) { cb(); return; }
    _georasterQueue.push(cb);
    if (_georasterLoading) return;
    _georasterLoading = true;
    function loadScript(src, next) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = next;
      s.onerror = function() { console.warn('COG: failed to load ' + src); next(); };
      document.head.appendChild(s);
    }
    // georaster bundles geotiff.js; the leaflet layer depends on georaster,
    // so load them in order.
    loadScript('https://unpkg.com/georaster@1/dist/georaster.browser.bundle.min.js', function() {
      loadScript('https://unpkg.com/georaster-layer-for-leaflet@3/dist/georaster-layer-for-leaflet.min.js', function() {
        _georasterLoading = false;
        var q = _georasterQueue; _georasterQueue = [];
        q.forEach(function(fn) { fn(); });
      });
    });
  }

  // Route a COG URL through the configured CORS proxy, if any. A proxy
  // template may contain {url} where the encoded URL should be inserted;
  // otherwise the encoded URL is appended to the end.
  function _cogProxied(url) {
    if (!_cogProxy) return url;
    var enc = encodeURIComponent(url);
    return (_cogProxy.indexOf('{url}') !== -1)
      ? _cogProxy.replace('{url}', enc)
      : _cogProxy + enc;
  }

  function buildCogLayer(item) {
    var ld = item.ld;
    var op = (ld.opacity != null) ? ld.opacity : 1;
    // Return a group immediately; the georaster layer is added once it loads.
    var group = L.layerGroup([], { pane: item.paneName });
    _loadGeoRaster(function() {
      if (!window.parseGeoraster || !window.GeoRasterLayer) {
        console.warn('COG libraries unavailable — cannot render "' + ld.name + '"');
        return;
      }
      parseGeoraster(_cogProxied(ld.url)).then(function(georaster) {
        var gl = new GeoRasterLayer({
          georaster:  georaster,
          opacity:    op,
          pane:       item.paneName,
          resolution: 256
        });
        group.addLayer(gl);
        item._cogLayer = gl;
      }).catch(function(e) {
        var hint = _cogProxy
          ? 'Check the CORS proxy forwards Range requests and is reachable.'
          : 'The blob storage did not allow the request (CORS). Set a COG CORS ' +
            'proxy in export settings, or ask the data host to enable CORS.';
        console.warn('COG load failed for "' + ld.name + '". ' + hint, e);
        _cogNotify('Could not load raster "' + ld.name + '" — ' + hint);
      });
    });
    return group;
  }

  // One-time, dismissible on-map notice so a failed COG isn't silently absent.
  var _cogNotified = false;
  function _cogNotify(msg) {
    if (_cogNotified) return;
    _cogNotified = true;
    var n = document.createElement('div');
    n.style.cssText = 'position:absolute;bottom:12px;left:50%;transform:translateX(-50%);'
      + 'z-index:1500;background:rgba(180,30,30,0.95);color:#fff;padding:8px 14px;'
      + 'border-radius:6px;font-size:12px;max-width:80%;box-shadow:0 2px 8px rgba(0,0,0,0.3);'
      + 'cursor:pointer;';
    n.textContent = msg + '  (click to dismiss)';
    n.title = 'Click to dismiss';
    n.addEventListener('click', function() { n.parentNode && n.parentNode.removeChild(n); });
    var mc = document.getElementById('map') || document.body;
    mc.appendChild(n);
  }

  function buildLayer(item) {
    if (item.ld.kind === 'vector') return buildVectorLayer(item);
    if (item.ld.kind === 'wms')    return buildWmsLayer(item);
    if (item.ld.kind === 'cog')    return buildCogLayer(item);
    return buildRasterLayer(item);
  }

  // Add/remove a layer together with its line casing underlays. Casings are
  // added first so the interactive core stroke draws on top of them.
  function addItemLayer(item) {
    (item.casings || []).forEach(function(c) { c.addTo(map); });
    item.lfl.addTo(map);
  }
  function removeItemLayer(item) {
    if (item.lfl) map.removeLayer(item.lfl);
    (item.casings || []).forEach(function(c) { map.removeLayer(c); });
  }

  // Rebuild a layer in place (used after a filter change), preserving visibility.
  function rebuildLayer(item) {
    var wasVisible = item.visible;
    // The markers are about to be replaced, so any click-spread pins on this
    // layer point at objects that will no longer be on the map.
    if ((item._pinnedCount || 0) > 0) clearPinnedSpread(item);
    removeItemLayer(item);
    item.lfl = buildLayer(item);
    if (wasVisible) addItemLayer(item);
    // Repopulate spreadMarkers from the newly-built layer so the explode system
    // always references live markers, not the old detached ones.
    if (item.ld.geomType === 'point' && item.ld.kind === 'vector') {
      item.spreadMarkers = [];
      item.lfl.eachLayer(function(lyr) { if (lyr._origLatLng) item.spreadMarkers.push(lyr); });
    }
    if (item.ld.labelConfig) {
      buildLabels(item);
      setLayerLabels(item, item.labelsVisible);
    }
    if (item.ld.geomType === 'line') {
      setTimeout(renderLineTicks, 0);
      setTimeout(renderLineLabels, 0);
    }
  }

  function onEachFeature(feature, layer) {
    if (!feature.properties) return;
    var rows = Object.entries(feature.properties)
      .filter(function(e) { return e[1] != null; })
      .map(function(e) {
        return '<tr><th>'+escHtml(e[0])+'</th><td>'+escHtml(String(e[1]))+'</td></tr>';
      }).join('');
    if (rows) {
      layer._infoHtml = '<table>'+rows+'</table>';
      layer._feature = feature;
    }
  }

  // Build Leaflet layers and collect metadata for legend.
  // Each layer gets a dedicated map pane so its opacity can be controlled
  // uniformly (works for vector markers, paths, rasters and WMS alike).
  var legendItems = [];
  var _allLabelItems = [];
  var _lineLabelItems = [];   // line layers whose labels follow the line path
  var _lineLabelPathId = 0;
  var _labelPlacementMode = 'candidate';
  var _labelSvg = document.getElementById('label-svg');
  for (var i = 0; i < LAYERS.length; i++) {
    var paneName = 'layerPane' + i;
    map.createPane(paneName);
    map.getPane(paneName).style.zIndex = 400 + i;

    var labelPaneName = 'labelPane' + i;
    map.createPane(labelPaneName);
    map.getPane(labelPaneName).style.zIndex = 650 + i;
    map.getPane(labelPaneName).style.pointerEvents = 'none';

    var item = {
      ld: LAYERS[i], paneName: paneName, labelPaneName: labelPaneName,
      visible: true, labelsVisible: false, filterFn: null, layerFilterFn: null,
      lfl: null, index: i, groupEnabled: false, groupMode: 'spread', hiddenClasses: [], spreadMarkers: []
    };
    try {
      item.lfl = buildLayer(item);
      addItemLayer(item);
      // collect point markers for de-overlap spread
      if (item.ld.geomType === 'point' && item.ld.kind === 'vector') {
        item.lfl.eachLayer(function(lyr) { if (lyr._origLatLng) item.spreadMarkers.push(lyr); });
      }
      if (item.ld.labelConfig) {
        buildLabels(item);
        if (item.ld.labelConfig.enabled) setLayerLabels(item, true);
      }
      legendItems.push(item);
    } catch(layerErr) {
      console.error('Layer render failed:', LAYERS[i] && LAYERS[i].name, layerErr);
    }
  }

  // ── Feature info panel ───────────────────────────────────────────────────
  var infoPanel = document.getElementById('info-panel');
  var infoPanelBody = document.getElementById('info-panel-body');
  document.getElementById('info-panel-close').addEventListener('click', function() {
    infoPanel.classList.remove('open');
    infoPanel.classList.remove('split');
    // also deactivate identify mode
    if (_identifyMode) {
      _identifyMode = false;
      var iBtn = document.getElementById('identify-btn');
      if (iBtn) iBtn.classList.remove('ident-active');
      map.getContainer().classList.remove('identify-mode');
      selectRect.style.display = 'none';
    }
  });

  // Info panel resize handle
  (function() {
    var rh = document.getElementById('info-panel-resize-h');
    if (!rh) return;
    var _ipResizeStart = null;
    rh.addEventListener('mousedown', function(e) {
      if (e.button !== 0) return;
      _ipResizeStart = { x: e.clientX, w: infoPanel.offsetWidth };
      rh.classList.add('dragging');
      e.preventDefault();
    });
    document.addEventListener('mousemove', function(e) {
      if (!_ipResizeStart) return;
      var nw = Math.max(220, Math.min(600, _ipResizeStart.w + e.clientX - _ipResizeStart.x));
      infoPanel.style.width = nw + 'px';
    });
    document.addEventListener('mouseup', function() {
      if (!_ipResizeStart) return;
      _ipResizeStart = null;
      rh.classList.remove('dragging');
    });
  })();

  // ── WMS GetFeatureInfo ────────────────────────────────────────────────────
  function wmsIdentify(item, latlng, cb) {
    var ld = item.ld;
    if (!ld.wmsUrl || !ld.wmsLayers || ld.tileType === 'xyz' || ld.tileType === 'wmts') {
      cb(null, null); return;
    }
    var bounds = map.getBounds();
    var size   = map.getSize();
    var pt     = map.latLngToContainerPoint(latlng);
    var ver    = ld.wmsVersion || '1.1.1';
    var is13   = ver.indexOf('1.3') === 0;
    var crs    = ld.wmsCrs || 'EPSG:4326';
    var bbox   = is13 && (crs === 'EPSG:4326' || crs === 'CRS:84')
      ? [bounds.getSouth(), bounds.getWest(), bounds.getNorth(), bounds.getEast()].join(',')
      : [bounds.getWest(),  bounds.getSouth(), bounds.getEast(),  bounds.getNorth()].join(',');
    var base   = ld.wmsUrl;
    var sep    = base.indexOf('?') !== -1 ? '&' : '?';
    var url    = base + sep
      + 'SERVICE=WMS&VERSION=' + encodeURIComponent(ver)
      + '&REQUEST=GetFeatureInfo'
      + '&LAYERS='        + encodeURIComponent(ld.wmsLayers)
      + '&QUERY_LAYERS='  + encodeURIComponent(ld.wmsLayers)
      + '&STYLES='        + encodeURIComponent(ld.wmsStyles || '')
      + '&FORMAT='        + encodeURIComponent(ld.wmsFormat || 'image/png')
      + '&INFO_FORMAT=text%2Fhtml'
      + '&TRANSPARENT=true'
      + '&BBOX='          + bbox
      + '&WIDTH='         + size.x
      + '&HEIGHT='        + size.y
      + '&FEATURE_COUNT=10'
      + (is13
          ? ('&CRS=' + encodeURIComponent(crs) + '&I=' + Math.round(pt.x) + '&J=' + Math.round(pt.y))
          : ('&SRS=' + encodeURIComponent(crs) + '&X=' + Math.round(pt.x) + '&Y=' + Math.round(pt.y)));
    fetch(url).then(function(r) {
      if (!r.ok) { cb('HTTP ' + r.status, null); return; }
      r.text().then(function(t) { cb(null, t); });
    }).catch(function() { cb('cors', null); });
  }

  // ── Identify mode button ─────────────────────────────────────────────────
  var _identifyMode = false;
  if (FEAT.identify) {
    var IdentifyBtn = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
        btn.id = 'identify-btn';
        btn.title = 'Identify features';
        btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;';
        btn.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg"><path d="M3 1L3 15L6.5 11.5L9.5 17.5L11.5 16.5L8.5 10.5L13.5 10.5Z" fill="currentColor"/><circle cx="14.5" cy="5" r="4" fill="@@_th_acc@@"/><text x="14.5" y="8" font-family="Georgia,serif" font-weight="bold" font-size="7" fill="#fff" text-anchor="middle">i</text></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          _identifyMode = !_identifyMode;
          btn.classList.toggle('ident-active', _identifyMode);
          map.getContainer().classList.toggle('identify-mode', _identifyMode);
          if (!_identifyMode) { selectRect.style.display = 'none'; }
        });
        return btn;
      }
    });
    new IdentifyBtn({position: 'topleft'}).addTo(map);
  }

  // ── Attribute table button ────────────────────────────────────────────────
  var _selectMode = false;
  if (FEAT.attrTable) {
    var AttrTableBtn = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
        btn.title = 'Attribute table';
        btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;';
        btn.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="2" width="16" height="16" rx="1" fill="none" stroke="currentColor" stroke-width="1.7"/><line x1="2" y1="7.5" x2="18" y2="7.5" stroke="currentColor" stroke-width="1.5"/><line x1="2" y1="13" x2="18" y2="13" stroke="currentColor" stroke-width="1"/><line x1="9" y1="7.5" x2="9" y2="18" stroke="currentColor" stroke-width="1"/></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          var panel = document.getElementById('attr-table-panel');
          panel.classList.toggle('open');
          if (panel.classList.contains('open')) populateAttrTable();
        });
        return btn;
      }
    });
    new AttrTableBtn({position: 'topleft'}).addTo(map);

    // ── Drag-select button (in attr-table header) ─────────────────────────
    var _attrSelectBtn = document.getElementById('attr-select-btn');
    if (_attrSelectBtn) {
      _attrSelectBtn.addEventListener('click', function() {
        _selectMode = !_selectMode;
        _attrSelectBtn.classList.toggle('select-btn-active', _selectMode);
        map.getContainer().style.cursor = _selectMode ? 'crosshair' : '';
        if (!_selectMode) selectRect.style.display = 'none';
      });
    }
  }

  var _highlightLayer = null;
  function highlightFeatureOnMap(feat) {
    if (_highlightLayer) { map.removeLayer(_highlightLayer); _highlightLayer = null; }
    if (!feat || !feat.geometry) return;
    try {
      _highlightLayer = L.geoJSON(feat, {
        style: { color: '#ffcc00', weight: 4, opacity: 1, fillColor: '#ffff00', fillOpacity: 0.3 },
        pointToLayer: function(f, latlng) {
          return L.circleMarker(latlng, { radius: 12, color: '#ffcc00', weight: 3, fillColor: '#ffff00', fillOpacity: 0.5 });
        }
      }).addTo(map);
    } catch(e) {}
  }

  var attrTablePanel = null, attrTableLayer = null, attrTableBody = null,
      attrTableSearch = null, _attrSelectSet = null;
  function populateAttrTable() {}  // stub; real impl assigned below if feature enabled

  if (FEAT.attrTable) {
    attrTablePanel = document.getElementById('attr-table-panel');
    attrTableLayer = document.getElementById('attr-table-layer');
    attrTableBody  = document.getElementById('attr-table-body');
    attrTableSearch = document.getElementById('attr-table-search');

    document.getElementById('attr-table-close').addEventListener('click', function() {
      attrTablePanel.classList.remove('open');
      if (_highlightLayer) { map.removeLayer(_highlightLayer); _highlightLayer = null; }
    });

    document.getElementById('attr-select-clear').addEventListener('click', function() {
      _attrSelectSet = null;
      populateAttrTable();
    });

    if (FEAT.attrCsv) {
      document.getElementById('attr-table-csv').addEventListener('click', function() {
        var item = legendItems[parseInt(attrTableLayer.value, 10)];
        if (!item || item.ld.kind !== 'vector') return;
        var csv = _layerCSV(item);
        if (csv == null) return;
        _downloadBlob(new Blob([csv], {type: 'text/csv'}), _safeName(item.ld.name) + '.csv');
      });
    }

    if (FEAT.attrGeojson) {
      var _gjBtn = document.getElementById('attr-table-geojson');
      if (_gjBtn) {
        _gjBtn.addEventListener('click', function() {
          var item = legendItems[parseInt(attrTableLayer.value, 10)];
          if (!item || item.ld.kind !== 'vector') return;
          var gj = item.ld.geojson;
          if (!gj || !gj.features) return;
          _downloadBlob(new Blob([JSON.stringify(gj, null, 2)], {type: 'application/json'}),
                        _safeName(item.ld.name) + '.geojson');
        });
      }
    }

    // ── Attribute table state ────────────────────────────────────────────
    // Large layers used to build every row into one HTML string and then
    // attach a click handler per row, and the search filtered by walking
    // every <tr> on each keystroke. Both scale linearly with feature count
    // and fall over on big datasets. Instead: filter and sort the data,
    // render only the current page, and use delegated listeners.
    var _attrSortCol = null, _attrSortAsc = true;
    var _attrPage = 0;
    var _ATTR_PAGE_SIZE = 200;
    var _attrFeats = null;        // features of the layer on show
    var _attrCols = [];           // column names currently rendered
    var _attrRows = [];           // filtered + sorted {fi, f} pairs
    var _attrHay = null;          // lowercase search haystack per feature
    var _attrHayIdx = -1;         // layer index _attrHay was built for
    var _attrSearchTimer = null;

    // One lowercase string per feature, built once per layer and reused for
    // every keystroke.
    function _attrHaystacks(idx, feats) {
      if (_attrHayIdx === idx && _attrHay) return _attrHay;
      var hay = new Array(feats.length);
      for (var i = 0; i < feats.length; i++) {
        var p = feats[i].properties || {}, parts = [];
        for (var k in p) { if (p[k] != null) parts.push(String(p[k])); }
        hay[i] = parts.join(' ').toLowerCase();
      }
      _attrHay = hay; _attrHayIdx = idx;
      return hay;
    }

    function filterAttrTable() {
      _attrPage = 0;
      populateAttrTable();
    }
    if (attrTableSearch) {
      attrTableSearch.addEventListener('input', function() {
        // Debounce so typing does not re-filter a large layer per keystroke.
        if (_attrSearchTimer) clearTimeout(_attrSearchTimer);
        _attrSearchTimer = setTimeout(filterAttrTable, 160);
      });
    }

    // Delegated listeners — attached once, and they keep working across
    // re-renders, so no per-row handlers are ever created.
    attrTableBody.addEventListener('click', function(ev) {
      var th = ev.target.closest && ev.target.closest('th[data-col]');
      if (th && attrTableBody.contains(th)) {
        var col = th.getAttribute('data-col');
        if (_attrSortCol === col) { _attrSortAsc = !_attrSortAsc; }
        else { _attrSortCol = col; _attrSortAsc = true; }
        _attrPage = 0;
        populateAttrTable();
        return;
      }

      var pg = ev.target.closest && ev.target.closest('[data-attr-page]');
      if (pg && attrTableBody.contains(pg)) {
        var to = parseInt(pg.getAttribute('data-attr-page'), 10);
        if (!isNaN(to)) { _attrPage = to; populateAttrTable(); }
        return;
      }

      var tr = ev.target.closest && ev.target.closest('tr[data-fi]');
      if (!tr || !attrTableBody.contains(tr)) return;
      var prev = attrTableBody.querySelector('tr.selected');
      if (prev) prev.classList.remove('selected');
      tr.classList.add('selected');
      var fi = parseInt(tr.getAttribute('data-fi'), 10);
      var feat = _attrFeats && _attrFeats[fi];
      if (!feat) return;
      if (feat.properties) {
        var rws = Object.entries(feat.properties)
          .filter(function(e){ return e[1]!=null; })
          .map(function(e){ return '<tr><th>'+escHtml(e[0])+'</th><td>'+escHtml(String(e[1]))+'</td></tr>'; }).join('');
        infoPanelBody.innerHTML = '<table>'+rws+'</table>';
        infoPanel.classList.add('open');
      }
      highlightFeatureOnMap(feat);
      if (feat.geometry) {
        try {
          var geo = L.geoJSON(feat);
          var b = geo.getBounds();
          if (b.isValid()) map.fitBounds(b, {maxZoom: 16, padding: [40,40]});
        } catch(e) {}
      }
    });

    populateAttrTable = function() {
    var idx = parseInt(attrTableLayer.value, 10);
    var item = legendItems[idx];
    if (!item || item.ld.kind !== 'vector') return;
    var feats = item.ld.geojson.features;
    _attrFeats = feats;
    if (!feats || !feats.length) { attrTableBody.innerHTML = '<p style="padding:8px;color:#888">No features.</p>'; return; }

    // Apply drag-select filter: build {fi, f} pairs preserving original indices
    var pairs = feats.map(function(f, fi) { return {fi: fi, f: f}; });
    if (_attrSelectSet !== null) {
      // Set lookup, not indexOf — a linear scan per feature is quadratic.
      var selLookup = {};
      for (var s = 0; s < _attrSelectSet.length; s++) selLookup[_attrSelectSet[s]] = 1;
      pairs = pairs.filter(function(p) { return selLookup[p.fi] === 1; });
    }

    // Update selection badge
    var badge = document.getElementById('attr-select-badge');
    var clearBtn = document.getElementById('attr-select-clear');
    if (badge) { badge.textContent = _attrSelectSet !== null ? pairs.length + ' selected' : ''; badge.style.display = _attrSelectSet !== null ? '' : 'none'; }
    if (clearBtn) clearBtn.style.display = _attrSelectSet !== null ? '' : 'none';

    // Text search, applied to the data rather than to rendered rows
    var q = attrTableSearch ? attrTableSearch.value.trim().toLowerCase() : '';
    var total = pairs.length;
    if (q) {
      var hay = _attrHaystacks(idx, feats);
      pairs = pairs.filter(function(p) { return hay[p.fi].indexOf(q) !== -1; });
    }

    // Collect columns from the first 100 filtered features
    var cols = [], seen = {};
    for (var i = 0; i < Math.min(pairs.length, 100); i++) {
      var p = pairs[i].f.properties || {};
      Object.keys(p).forEach(function(k) { if (!(k in seen)) { seen[k]=1; cols.push(k); } });
    }
    _attrCols = cols;

    // Sort pairs preserving original feature index
    if (_attrSortCol !== null && cols.indexOf(_attrSortCol) !== -1) {
      pairs.sort(function(a, b) {
        var va = (a.f.properties || {})[_attrSortCol], vb = (b.f.properties || {})[_attrSortCol];
        var na = parseFloat(va), nb = parseFloat(vb);
        var cmp = (!isNaN(na) && !isNaN(nb)) ? (na-nb) : (String(va) < String(vb) ? -1 : String(va) > String(vb) ? 1 : 0);
        return _attrSortAsc ? cmp : -cmp;
      });
    }
    _attrRows = pairs;

    // Page the render — only this slice reaches the DOM
    var pageCount = Math.max(1, Math.ceil(pairs.length / _ATTR_PAGE_SIZE));
    if (_attrPage >= pageCount) _attrPage = pageCount - 1;
    if (_attrPage < 0) _attrPage = 0;
    var from = _attrPage * _ATTR_PAGE_SIZE;
    var to = Math.min(from + _ATTR_PAGE_SIZE, pairs.length);

    var html = '<table><thead><tr>';
    cols.forEach(function(c) {
      var cls = (_attrSortCol === c) ? ('sort-' + (_attrSortAsc?'asc':'desc')) : '';
      html += '<th class="'+cls+'" data-col="'+escHtml(c)+'">'+escHtml(c)+'</th>';
    });
    html += '</tr></thead><tbody>';
    for (var r = from; r < to; r++) {
      var pair = pairs[r], pp = pair.f.properties || {};
      html += '<tr data-fi="'+pair.fi+'">';
      for (var ci = 0; ci < cols.length; ci++) {
        var v = pp[cols[ci]];
        var sv = v != null ? escHtml(String(v)) : '';
        html += '<td title="'+sv+'">'+sv+'</td>';
      }
      html += '</tr>';
    }
    html += '</tbody></table>';

    // Pager / result count
    if (pairs.length === 0) {
      html += '<p style="padding:8px;color:#888">No features match "'+escHtml(q)+'".</p>';
    } else {
      html += '<div class="attr-pager">';
      html += '<span class="attr-pager-count">' + (from+1) + '–' + to + ' of ' + pairs.length
            + (q ? ' (filtered from ' + total + ')' : '') + '</span>';
      if (pageCount > 1) {
        html += '<span class="attr-pager-btns">';
        html += '<button data-attr-page="0"'+(_attrPage===0?' disabled':'')+' title="First page">&#171;</button>';
        html += '<button data-attr-page="'+(_attrPage-1)+'"'+(_attrPage===0?' disabled':'')+' title="Previous page">&#8249;</button>';
        html += '<span class="attr-pager-pos">' + (_attrPage+1) + ' / ' + pageCount + '</span>';
        html += '<button data-attr-page="'+(_attrPage+1)+'"'+(_attrPage>=pageCount-1?' disabled':'')+' title="Next page">&#8250;</button>';
        html += '<button data-attr-page="'+(pageCount-1)+'"'+(_attrPage>=pageCount-1?' disabled':'')+' title="Last page">&#187;</button>';
        html += '</span>';
      }
      html += '</div>';
    }
    attrTableBody.innerHTML = html;
    }
  }  // end if (FEAT.attrTable)

  // ── Legend panel ─────────────────────────────────────────────────────────
  try { if ((INCLUDE_LAYERS || INCLUDE_LEGEND) && legendItems.length > 0) {
    var panel = document.getElementById('legend');
    panel.style.display = 'flex';

    // Header. With both modes exported the title becomes a two-way switch:
    // "Layers" is the interactive control, "Legend" is the read-only
    // symbology list with every class expanded and no toggles.
    var _bothModes = INCLUDE_LAYERS && INCLUDE_LEGEND;
    var _titleHtml = _bothModes
      ? '<span id="legend-mode-toggle" role="group" aria-label="Panel mode">'
        + '<button type="button" data-mode="layers" class="active">Layers</button>'
        + '<button type="button" data-mode="legend">Legend</button></span>'
      : '<span>' + (INCLUDE_LAYERS ? 'Layers' : 'Legend') + '</span>';
    var hdr = document.getElementById('legend-header') || document.createElement('div');
    hdr.id = 'legend-header';
    hdr.innerHTML = _titleHtml
      + '<span id="legend-hdr-actions" style="display:flex;align-items:center;gap:4px;">'
      + '<button id="legend-tools-btn" title="Show layer tools">'
      + '<svg width="13" height="13" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
      + '<path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/>'
      + '</svg></button>'
      + '<button id="legend-toggle-all">Hide all</button></span>';
    panel.appendChild(hdr);

    var toolsBtn = document.getElementById('legend-tools-btn');
    toolsBtn.addEventListener('click', function() {
      var on = panel.classList.toggle('tools-mode');
      toolsBtn.classList.toggle('active', on);
      toolsBtn.title = on ? 'Hide layer tools' : 'Show layer tools';
    });

    function setPanelMode(mode) {
      var legendMode = mode === 'legend';
      panel.classList.toggle('legend-mode', legendMode);
      // The layer tools have no meaning in a read-only legend.
      if (legendMode && panel.classList.contains('tools-mode')) {
        panel.classList.remove('tools-mode');
        toolsBtn.classList.remove('active');
      }
      var tgl = document.getElementById('legend-mode-toggle');
      if (tgl) {
        Array.prototype.forEach.call(tgl.children, function(b) {
          b.classList.toggle('active', b.getAttribute('data-mode') === mode);
        });
      }
    }
    if (_bothModes) {
      document.getElementById('legend-mode-toggle')
        .addEventListener('click', function(e) {
          var b = e.target.closest ? e.target.closest('button[data-mode]') : null;
          if (b) setPanelMode(b.getAttribute('data-mode'));
        });
    }
    // Legend-only exports open straight into the read-only view.
    if (!INCLUDE_LAYERS) setPanelMode('legend');

    var body = document.createElement('div');
    body.id = 'legend-body';
    panel.appendChild(body);

    var allVisible = true;
    document.getElementById('legend-toggle-all').addEventListener('click', function() {
      allVisible = !allVisible;
      this.textContent = allVisible ? 'Hide all' : 'Show all';
      legendItems.forEach(function(item) {
        setLayerVisible(item, allVisible);
      });
    });

    // Legend items are shown top-to-bottom (reverse of draw order)
    var displayItems = legendItems.slice().reverse();

    var COG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
      + '<path d="M12 15.5a3.5 3.5 0 0 1-3.5-3.5 3.5 3.5 0 0 1 3.5-3.5 3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5m7.43-2.92c.04-.32.07-.64.07-.97s-.03-.66-.07-1l2.16-1.68c.19-.15.24-.42.12-.64l-2.04-3.53c-.12-.22-.39-.3-.61-.22l-2.55 1.03c-.52-.4-1.08-.73-1.69-.98l-.38-2.72C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.72c-.61.25-1.17.59-1.69.98l-2.55-1.03c-.22-.08-.49 0-.61.22L2.74 8.87c-.13.22-.07.49.12.64L5.02 11.19c-.04.34-.07.67-.07 1s.03.65.07.97L2.86 14.84c-.19.15-.24.42-.12.64l2.04 3.53c.12.22.39.3.61.22l2.55-1.03c.52.4 1.08.73 1.69.98l.38 2.72c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.72c.61-.25 1.17-.58 1.69-.98l2.55 1.03c.22.08.49 0 .61-.22l2.04-3.53c.12-.22.07-.49-.12-.64l-2.16-1.68z"/>'
      + '</svg>';

    function makeCogBtn(settingsDiv) {
      var btn = document.createElement('button');
      btn.className = 'legend-cog-btn';
      btn.title = 'Layer settings';
      btn.innerHTML = COG_SVG;
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var isOpen = settingsDiv.classList.toggle('open');
        btn.classList.toggle('active', isOpen);
        if (isOpen) {
          document.querySelectorAll('.layer-settings.open').forEach(function(el) {
            if (el !== settingsDiv) el.classList.remove('open');
          });
          document.querySelectorAll('.legend-cog-btn.active').forEach(function(el) {
            if (el !== btn) el.classList.remove('active');
          });
        }
      });
      return btn;
    }

    // ── Per-layer filter panel (same setup as the global filter, layer-scoped)
    function buildLayerFilterPanel(item) {
      var div = document.createElement('div');
      div.className = 'layer-filter';

      var attrSel = document.createElement('select');
      attrSel.className = 'lf-attr';
      attrSel.title = 'Attribute to filter on';
      var feats = item.ld.geojson.features || [];
      var keys = [], seen = {};
      for (var i = 0; i < Math.min(feats.length, 50); i++) {
        var p = feats[i].properties || {};
        for (var k in p) { if (!(k in seen)) { seen[k] = 1; keys.push(k); } }
      }
      // First option: "Any field" — full-text search across all attributes
      var anyOpt = document.createElement('option');
      anyOpt.value = ''; anyOpt.textContent = '— Any field —';
      attrSel.appendChild(anyOpt);
      keys.forEach(function(k) {
        var o = document.createElement('option');
        o.value = k; o.textContent = k;
        attrSel.appendChild(o);
      });

      var search = document.createElement('input');
      search.type = 'text';
      search.className = 'lf-search';
      search.placeholder = 'Contains…';
      search.autocomplete = 'off';

      var list = document.createElement('div');
      list.className = 'lf-values';
      list.style.display = 'none';   // hidden in "any field" mode by default

      var foot = document.createElement('div');
      foot.className = 'lf-foot';
      var clearB = document.createElement('button');
      clearB.type = 'button';
      clearB.textContent = 'Clear';
      var countS = document.createElement('span');
      countS.className = 'filter-count';
      foot.appendChild(clearB);
      foot.appendChild(countS);

      function checkedVals() {
        var out = [];
        Array.prototype.forEach.call(list.querySelectorAll('input:checked'), function(c) {
          out.push(c.value);
        });
        return out;
      }

      function apply() {
        var attr = attrSel.value;
        var q = search.value.trim().toLowerCase();
        var sel = checkedVals();
        if (attr === '') {
          // Any-field text search
          if (!q) {
            item.layerFilterFn = null;
          } else {
            item.layerFilterFn = function(feature) {
              var props = feature.properties || {};
              for (var fk in props) {
                var sv = String(props[fk] == null ? '' : props[fk]).toLowerCase();
                if (sv.indexOf(q) !== -1) return true;
              }
              return false;
            };
          }
        } else {
          // Field-specific filter
          if (sel.length === 0 && !q) {
            item.layerFilterFn = null;
          } else {
            item.layerFilterFn = function(feature) {
              var v = (feature.properties || {})[attr];
              var sv = (v == null ? '' : String(v));
              if (sel.length) return sel.indexOf(sv) !== -1;
              return sv.toLowerCase().indexOf(q) !== -1;
            };
          }
        }
        rebuildLayer(item);
        var total = feats.length;
        var shown = item.layerFilterFn ? feats.filter(item.layerFilterFn).length : total;
        countS.textContent = shown + ' / ' + total;
        if (item._actFilterBtn) item._actFilterBtn.classList.toggle('filtered', !!item.layerFilterFn);
      }

      function populateVals() {
        list.innerHTML = '';
        var attr = attrSel.value;
        if (!attr) { list.style.display = 'none'; return; }
        list.style.display = '';
        var vseen = {}, vals = [];
        for (var i = 0; i < feats.length; i++) {
          var v = (feats[i].properties || {})[attr];
          var sv = (v == null ? '' : String(v));
          if (!(sv in vseen)) { vseen[sv] = 1; vals.push(sv); }
          if (vals.length > 2000) break;
        }
        vals.sort(function(a, b) {
          var na = parseFloat(a), nb = parseFloat(b);
          if (!isNaN(na) && !isNaN(nb)) return na - nb;
          return a < b ? -1 : (a > b ? 1 : 0);
        });
        vals.forEach(function(val) {
          var lab = document.createElement('label');
          lab.className = 'filter-value-item';
          var c = document.createElement('input');
          c.type = 'checkbox'; c.value = val;
          c.addEventListener('change', apply);
          var s = document.createElement('span');
          s.textContent = (val === '' ? '(empty)' : val);
          s.title = val;
          lab.appendChild(c); lab.appendChild(s);
          list.appendChild(lab);
        });
      }

      attrSel.addEventListener('change', function() { search.value = ''; populateVals(); apply(); });
      search.addEventListener('input', function() {
        var attr = attrSel.value;
        if (attr) {
          // When on a specific field, filter the visible value list
          var q = search.value.trim().toLowerCase();
          Array.prototype.forEach.call(list.children, function(el) {
            el.style.display = el.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
          });
        }
        apply();
      });
      clearB.addEventListener('click', function() {
        search.value = '';
        Array.prototype.forEach.call(list.querySelectorAll('input:checked'), function(c) { c.checked = false; });
        Array.prototype.forEach.call(list.children, function(el) { el.style.display = ''; });
        apply();
      });

      div.appendChild(attrSel);
      div.appendChild(search);
      div.appendChild(list);
      div.appendChild(foot);
      var total0 = feats.length;
      countS.textContent = total0 + ' / ' + total0;
      return div;
    }

    // ── Per-layer tool buttons, revealed by the header tools toggle ──────
    function buildLayerActions(item, layerDiv) {
      var acts = document.createElement('span');
      acts.className = 'layer-actions';
      var cfg = item.ld.labelConfig || null;
      var ld = item.ld;
      var layerFilterDiv = null;

      function mkBtn(title, svg) {
        var b = document.createElement('button');
        b.className = 'layer-act-btn';
        b.title = title;
        b.innerHTML = svg;
        return b;
      }

      // Attribute table
      if (FEAT.attrTable) {
        var tBtn = mkBtn('Open attribute table',
          '<svg width="11" height="11" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">'
          + '<rect x="1" y="1" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4"/>'
          + '<line x1="1" y1="5.5" x2="15" y2="5.5" stroke="currentColor" stroke-width="1.4"/>'
          + '<line x1="1" y1="10" x2="15" y2="10" stroke="currentColor" stroke-width="1"/>'
          + '<line x1="6" y1="5.5" x2="6" y2="15" stroke="currentColor" stroke-width="1"/>'
          + '<line x1="10.5" y1="5.5" x2="10.5" y2="15" stroke="currentColor" stroke-width="1"/></svg>');
        tBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          var panel = document.getElementById('attr-table-panel');
          var sel = document.getElementById('attr-table-layer');
          if (sel) sel.value = item.index;
          if (panel) panel.classList.add('open');
          populateAttrTable();
        });
        acts.appendChild(tBtn);
      }

      // Layer filter
      if (FEAT.filter) {
        var fBtn = mkBtn('Filter this layer',
          '<svg width="11" height="11" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">'
          + '<path d="M2 3h14l-5 5.5V15l-4-2V8.5z" fill="currentColor"/></svg>');
        item._actFilterBtn = fBtn;
        fBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          if (!layerFilterDiv) {
            layerFilterDiv = buildLayerFilterPanel(item);
            layerDiv.appendChild(layerFilterDiv);
          }
          var open = layerFilterDiv.classList.toggle('open');
          fBtn.classList.toggle('active', open);
        });
        acts.appendChild(fBtn);
      }

      // Labels on/off
      if (cfg) {
        var lBtn = mkBtn('Toggle labels',
          '<svg width="11" height="11" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">'
          + '<text x="8" y="12" text-anchor="middle" font-size="12" font-weight="bold" fill="currentColor" font-family="serif">T</text></svg>');
        lBtn.classList.toggle('active', !!item.labelsVisible);
        item._actLblBtn = lBtn;
        lBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          var on = !item.labelsVisible;
          setLayerLabels(item, on);
          lBtn.classList.toggle('active', on);
          if (item._cogLblCb) item._cogLblCb.checked = on;
        });
        acts.appendChild(lBtn);
      }

      // Explode / group toggle (point layers only) — on/off only
      if (FEAT.fancyLabels && ld.kind === 'vector' && ld.geomType === 'point') {
        var _spreadSvg = '<svg width="13" height="13" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">'
          + '<circle cx="8" cy="8" r="1.5" fill="currentColor"/>'
          + '<line x1="8" y1="8" x2="3" y2="3.5" stroke="currentColor" stroke-width="0.8"/>'
          + '<line x1="8" y1="8" x2="13" y2="3.5" stroke="currentColor" stroke-width="0.8"/>'
          + '<line x1="8" y1="8" x2="3" y2="12.5" stroke="currentColor" stroke-width="0.8"/>'
          + '<line x1="8" y1="8" x2="13" y2="12.5" stroke="currentColor" stroke-width="0.8"/>'
          + '<circle cx="3" cy="3.5" r="2" fill="currentColor"/>'
          + '<circle cx="13" cy="3.5" r="2" fill="currentColor"/>'
          + '<circle cx="3" cy="12.5" r="2" fill="currentColor"/>'
          + '<circle cx="13" cy="12.5" r="2" fill="currentColor"/></svg>';
        var gBtn = mkBtn('Explode / group points: Off — click to enable', _spreadSvg);
        function _refreshGBtn() {
          gBtn.classList.toggle('active', !!item.groupEnabled);
          gBtn.title = item.groupEnabled
            ? 'Explode / group points: On — click to turn off'
            : 'Explode / group points: Off — click to enable';
        }
        _refreshGBtn();
        item._actGrpBtn = gBtn;
        item._refreshActGrpBtn = _refreshGBtn;

        gBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          if (!item.groupEnabled) {
            // Store prior label placement so we can restore it on turn-off
            item._preLabelMode = item._preLabelMode || _labelPlacementMode;
            item.groupEnabled = true;
            item.groupMode = (item._cogGrpModeSel && item._cogGrpModeSel.value) || 'spread';
            if (item._cogGrpCb) item._cogGrpCb.checked = true;
            if (item._cogGrpModeSel) item._cogGrpModeSel.disabled = false;
            rebuildLayer(item);
            spreadMarkers();
          } else {
            item.groupEnabled = false;
            item.spreadMarkers.forEach(function(mkr) { if (mkr._origLatLng) mkr.setLatLng(mkr._origLatLng); });
            if (_spreadLeaderSvg) _spreadLeaderSvg.innerHTML = '';
            if (item._cogGrpCb) item._cogGrpCb.checked = false;
            if (item._cogGrpModeSel) item._cogGrpModeSel.disabled = true;
            rebuildLayer(item);
            layoutAllLabels();
          }
          _refreshGBtn();
        });
        acts.appendChild(gBtn);
      }

      return acts;
    }

    function buildRasterLegend(rleg, legendUrl) {
      var div = document.createElement('div');
      div.className = 'legend-entries raster-legend';

      if (legendUrl) {
        var img = document.createElement('img');
        img.src = legendUrl;
        img.style.cssText = 'max-width:100%;padding:4px 8px 6px;display:block;';
        img.onerror = function() { this.style.display = 'none'; };
        div.appendChild(img);
        return div;
      }

      if (!rleg) return null;
      var type = rleg.type;

      if (type === 'paletted' && rleg.classes && rleg.classes.length) {
        rleg.classes.forEach(function(cls) {
          var eRow = document.createElement('div');
          eRow.className = 'legend-entry';
          var sw = document.createElement('span');
          sw.className = 'legend-swatch';
          sw.innerHTML = '<svg width="16" height="14" xmlns="http://www.w3.org/2000/svg">'
              + '<rect x="1" y="1" width="14" height="12" rx="1"'
              + ' fill="' + escHtml(cls.color || '#aaa') + '"'
              + ' fill-opacity="' + (cls.alpha != null ? cls.alpha : 1) + '"'
              + ' stroke="#888" stroke-width="0.5"/></svg>';
          var lbl = document.createElement('span');
          lbl.className = 'legend-entry-label';
          lbl.textContent = cls.label || String(cls.value);
          eRow.appendChild(sw);
          eRow.appendChild(lbl);
          div.appendChild(eRow);
        });
        return div;
      }

      if ((type === 'pseudocolor' || type === 'gray') && rleg.stops && rleg.stops.length) {
        var gradParts = rleg.stops.map(function(s, i) {
          var pct = rleg.stops.length > 1 ? Math.round(100 * i / (rleg.stops.length - 1)) : 100;
          return s.color + ' ' + pct + '%';
        });
        var gradBar = document.createElement('div');
        gradBar.style.cssText = 'margin:4px 10px 2px;height:14px;border-radius:2px;'
            + 'border:1px solid #ddd;background:linear-gradient(to right,' + gradParts.join(',') + ');';
        var labRow = document.createElement('div');
        labRow.style.cssText = 'display:flex;justify-content:space-between;padding:0 10px 5px;font-size:9px;color:#666;';
        var minL = document.createElement('span');
        minL.textContent = rleg.stops[0].label || (rleg.min != null ? String(rleg.min) : '');
        var maxL = document.createElement('span');
        maxL.textContent = rleg.stops[rleg.stops.length-1].label
            || (rleg.max != null ? String(rleg.max) : '');
        labRow.appendChild(minL);
        labRow.appendChild(maxL);
        div.appendChild(gradBar);
        div.appendChild(labRow);
        return div;
      }

      if (type === 'gray') {
        var g1 = rleg.blackFirst ? '#000' : '#fff';
        var g2 = rleg.blackFirst ? '#fff' : '#000';
        var gradBar2 = document.createElement('div');
        gradBar2.style.cssText = 'margin:4px 10px 2px;height:14px;border-radius:2px;'
            + 'border:1px solid #ddd;background:linear-gradient(to right,' + g1 + ',' + g2 + ');';
        var labRow2 = document.createElement('div');
        labRow2.style.cssText = 'display:flex;justify-content:space-between;padding:0 10px 5px;font-size:9px;color:#666;';
        var minL2 = document.createElement('span');
        minL2.textContent = rleg.min != null ? String(rleg.min) : '';
        var maxL2 = document.createElement('span');
        maxL2.textContent = rleg.max != null ? String(rleg.max) : '';
        labRow2.appendChild(minL2);
        labRow2.appendChild(maxL2);
        div.appendChild(gradBar2);
        div.appendChild(labRow2);
        return div;
      }

      if (type === 'multiband') {
        var lbl = document.createElement('div');
        lbl.style.cssText = 'padding:4px 10px 5px;font-size:9px;color:#666;';
        lbl.textContent = 'RGB — Band ' + (rleg.redBand||'?') + ' / ' + (rleg.greenBand||'?') + ' / ' + (rleg.blueBand||'?');
        div.appendChild(lbl);
        return div;
      }

      return null;
    }

    function buildLayerRow(item, container) {
      var ld = item.ld;
      var sm = ld.styleMap || {};
      var geomType = (ld.kind === 'raster' || ld.kind === 'wms' || ld.kind === 'cog') ? 'raster' : ld.geomType;
      var cfg = ld.labelConfig || null;

      var hasEntries = sm.entries && sm.entries.length > 1;

      var primaryStyle = {};
      if (sm.type === 'single') {
        primaryStyle = sm.style || {};
      } else if (!hasEntries && sm.entries && sm.entries.length) {
        primaryStyle = sm.entries[0].style || {};
      } else if (hasEntries && geomType !== 'point') {
        // Show the first entry style for lines/polygons (colour/pattern gives useful context).
        var _e0 = sm.entries[0].style || {};
        primaryStyle = { color: _e0.color, weight: _e0.weight,
                          fillColor: _e0.fillColor, fillOpacity: _e0.fillOpacity };
      }
      // For multi-symbol point layers: leave primaryStyle empty → generic circle swatch.

      var layerDiv = document.createElement('div');
      layerDiv.className = 'legend-layer';

      // ── Main row ─────────────────────────────────────────────────────
      var row = document.createElement('div');
      row.className = 'legend-layer-row';

      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.title = 'Toggle layer visibility';
      cb.addEventListener('change', function() {
        setLayerVisible(item, cb.checked);
      });

      var swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.innerHTML = swatchSvg(geomType, primaryStyle, ld.rasterLegend);

      var nameEl = document.createElement('span');
      nameEl.className = 'legend-layer-name';
      nameEl.title = ld.name;
      nameEl.textContent = ld.name;

      row.appendChild(cb);
      row.appendChild(swatch);
      row.appendChild(nameEl);

      // ── Expand button (categories) ────────────────────────────────────
      var entriesDiv = null;
      if (hasEntries) {
        var expBtn = document.createElement('span');
        expBtn.className = 'legend-expand';
        expBtn.textContent = '▶';
        expBtn.title = 'Expand / collapse categories';
        expBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          var open = entriesDiv.classList.toggle('open');
          expBtn.style.transform = open ? 'rotate(90deg)' : '';
        });
        row.appendChild(expBtn);

        entriesDiv = document.createElement('div');
        entriesDiv.className = 'legend-entries';
        var classTogglable = sm.type === 'categorized' || sm.type === 'graduated';
        sm.entries.forEach(function(entry, ei) {
          var eRow = document.createElement('div');
          eRow.className = 'legend-entry';
          if (classTogglable) {
            var eCb = document.createElement('input');
            eCb.type = 'checkbox';
            eCb.checked = true;
            eCb.title = 'Toggle this class';
            (function(entryIndex, row) {
              eCb.addEventListener('change', function() {
                if (!eCb.checked) {
                  if (item.hiddenClasses.indexOf(entryIndex) === -1)
                    item.hiddenClasses.push(entryIndex);
                  row.classList.add('class-hidden');
                } else {
                  var pos = item.hiddenClasses.indexOf(entryIndex);
                  if (pos !== -1) item.hiddenClasses.splice(pos, 1);
                  row.classList.remove('class-hidden');
                }
                rebuildLayer(item);
              });
            })(ei, eRow);
            eRow.appendChild(eCb);
          }
          var eSwatch = document.createElement('span');
          eSwatch.className = 'legend-swatch';
          eSwatch.innerHTML = swatchSvg(geomType, entry.style || {});
          var eLabel = document.createElement('span');
          eLabel.className = 'legend-entry-label';
          eLabel.title = entry.label || '';
          eLabel.textContent = entry.label || '';
          eRow.appendChild(eSwatch);
          eRow.appendChild(eLabel);
          entriesDiv.appendChild(eRow);
        });
      }

      // ── Settings panel (behind cog) ───────────────────────────────────
      var settingsDiv = document.createElement('div');
      settingsDiv.className = 'layer-settings';

      // Opacity row
      var opRow = document.createElement('div');
      opRow.className = 'layer-settings-row';
      var opLbl = document.createElement('span');
      opLbl.className = 'layer-settings-label';
      opLbl.textContent = 'Opacity';
      var slider = document.createElement('input');
      slider.type = 'range';
      slider.min = '0'; slider.max = '100';
      slider.value = String(Math.round((ld.opacity != null ? ld.opacity : 1) * 100));
      slider.title = 'Layer opacity';
      slider.addEventListener('input', function() {
        setLayerOpacity(item, parseInt(slider.value, 10) / 100);
      });
      // Apply initial opacity if not 100%
      if (ld.opacity != null && ld.opacity < 1) setLayerOpacity(item, ld.opacity);
      opRow.appendChild(opLbl);
      opRow.appendChild(slider);
      settingsDiv.appendChild(opRow);

      // Labels row — checkbox + inline placement mode dropdown
      if (cfg && ld.kind === 'vector') {
        var lblRow = document.createElement('div');
        lblRow.className = 'layer-settings-row';
        var lblLbl = document.createElement('span');
        lblLbl.className = 'layer-settings-label';
        lblLbl.textContent = 'Labels';
        var lblCb = document.createElement('input');
        lblCb.type = 'checkbox';
        lblCb.checked = cfg.enabled || false;
        lblCb.title = 'Toggle feature labels';
        item._cogLblCb = lblCb;
        lblCb.addEventListener('change', function() {
          setLayerLabels(item, lblCb.checked);
          if (item._actLblBtn) item._actLblBtn.classList.toggle('active', lblCb.checked);
        });
        var modeSel = document.createElement('select');
        modeSel.className = 'label-mode-sel layer-settings-sel';
        modeSel.title = 'Label placement — applies to all label layers';
        [['candidate','Candidate'],['force','Force'],['static','Static']].forEach(function(opt) {
          var o = document.createElement('option');
          o.value = opt[0]; o.textContent = opt[1];
          if (opt[0] === _labelPlacementMode) o.selected = true;
          modeSel.appendChild(o);
        });
        modeSel.addEventListener('change', function() {
          _labelPlacementMode = modeSel.value;
          document.querySelectorAll('.label-mode-sel').forEach(function(s) { s.value = _labelPlacementMode; });
          layoutAllLabels();
        });
        lblRow.appendChild(lblLbl);
        lblRow.appendChild(lblCb);
        lblRow.appendChild(modeSel);
        settingsDiv.appendChild(lblRow);
      }

      // Explode / group points — checkbox + inline mode dropdown (point layers only)
      if (ld.kind === 'vector' && ld.geomType === 'point') {
        var grpRow = document.createElement('div');
        grpRow.className = 'layer-settings-row';
        var grpLbl = document.createElement('span');
        grpLbl.className = 'layer-settings-label';
        grpLbl.textContent = 'Explode / group';
        var grpCb = document.createElement('input');
        grpCb.type = 'checkbox';
        grpCb.checked = false;
        grpCb.title = 'Explode / group overlapping point markers';
        var grpModeSel = document.createElement('select');
        grpModeSel.className = 'layer-settings-sel';
        grpModeSel.disabled = true;
        var clusterAvail = typeof L.markerClusterGroup !== 'undefined';
        grpModeSel.innerHTML = '<option value="spread">Spread</option>'
          + '<option value="cluster" ' + (clusterAvail ? '' : 'disabled') + '>Cluster</option>';
        grpRow.appendChild(grpLbl);
        grpRow.appendChild(grpCb);
        grpRow.appendChild(grpModeSel);
        settingsDiv.appendChild(grpRow);
        item._cogGrpCb = grpCb;
        item._cogGrpModeSel = grpModeSel;

        grpCb.addEventListener('change', function() {
          item.groupEnabled = grpCb.checked;
          grpModeSel.disabled = !grpCb.checked;
          if (grpCb.checked) {
            item._preLabelMode = item._preLabelMode || _labelPlacementMode;
          } else {
            item.spreadMarkers.forEach(function(mkr) {
              if (mkr._origLatLng) mkr.setLatLng(mkr._origLatLng);
            });
            if (_spreadLeaderSvg) _spreadLeaderSvg.innerHTML = '';
          }
          rebuildLayer(item);
          if (item.groupEnabled) spreadMarkers();
          else layoutAllLabels();
          if (item._refreshActGrpBtn) item._refreshActGrpBtn();
        });
        grpModeSel.addEventListener('change', function() {
          item.groupMode = grpModeSel.value;
          rebuildLayer(item);
          if (item.groupEnabled) spreadMarkers();
          if (item._refreshActGrpBtn) item._refreshActGrpBtn();
        });
      }

      if (ld.kind === 'vector') row.appendChild(buildLayerActions(item, layerDiv));
      if (FEAT.fancyLabels) row.appendChild(makeCogBtn(settingsDiv));

      // ── Raster legend (gradient bar / palette / WMS image) ───────────
      var rasterLegDiv = null;
      if (ld.kind === 'raster' || ld.kind === 'wms') {
        rasterLegDiv = buildRasterLegend(ld.rasterLegend, ld.legendUrl);
        if (rasterLegDiv) {
          var rExpBtn = document.createElement('span');
          rExpBtn.className = 'legend-expand';
          rExpBtn.textContent = '▶';
          rExpBtn.title = 'Expand / collapse legend';
          rExpBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var open = rasterLegDiv.classList.toggle('open');
            rExpBtn.style.transform = open ? 'rotate(90deg)' : '';
          });
          row.appendChild(rExpBtn);
        }
      }

      layerDiv.appendChild(row);
      if (entriesDiv) layerDiv.appendChild(entriesDiv);
      if (rasterLegDiv) layerDiv.appendChild(rasterLegDiv);
      layerDiv.appendChild(settingsDiv);
      container.appendChild(layerDiv);
      item.checkbox = cb;
      item.layerDiv = layerDiv;
    }

    function setGroupVisible(nodeList, visible) {
      nodeList.forEach(function(node) {
        if (node.type === 'layer') {
          var it = displayItems[node.index];
          if (it) setLayerVisible(it, visible);
        } else if (node.type === 'group') {
          setGroupVisible(node.children, visible);
        }
      });
    }

    function buildLegendNodes(nodes, container) {
      nodes.forEach(function(node) {
        if (node.type === 'group') {
          var grpDiv = document.createElement('div');
          grpDiv.className = 'legend-group';
          var grpHdr = document.createElement('div');
          grpHdr.className = 'legend-group-hdr';

          // Visibility checkbox for the whole group
          var grpCb = document.createElement('input');
          grpCb.type = 'checkbox';
          grpCb.checked = true;
          grpCb.title = 'Toggle group visibility';
          grpCb.addEventListener('change', function() {
            setGroupVisible(node.children, grpCb.checked);
          });

          var grpExp = document.createElement('span');
          grpExp.className = 'legend-expand';
          grpExp.textContent = '▼';
          var grpName = document.createElement('span');
          grpName.className = 'legend-group-name';
          grpName.textContent = node.name;
          grpHdr.appendChild(grpCb);
          grpHdr.appendChild(grpExp);
          grpHdr.appendChild(grpName);
          var grpBody = document.createElement('div');
          grpBody.className = 'legend-group-body open';
          grpHdr.addEventListener('click', function(e) {
            if (e.target === grpCb) return;
            var open = grpBody.classList.toggle('open');
            grpExp.textContent = open ? '▼' : '▶';
          });
          grpDiv.appendChild(grpHdr);
          grpDiv.appendChild(grpBody);
          container.appendChild(grpDiv);
          // Store DOM refs so applyTheme can sync group state
          node._grpCb = grpCb;
          node._grpBody = grpBody;
          node._grpExp = grpExp;
          buildLegendNodes(node.children, grpBody);
        } else {
          var item = displayItems[node.index];
          if (item) {
            buildLayerRow(item, container);
            node._item = item; // ref for applyTheme sync
          }
        }
      });
    }

    if (LAYER_TREE.length > 0) {
      buildLegendNodes(LAYER_TREE, body);
    } else {
      displayItems.forEach(function(item) {
        buildLayerRow(item, body);
      });
    }

    // ── Basemap entry (only when basemap is included) ─────────────────────────
    if (basemap) (function() {
      var bDiv = document.createElement('div');
      bDiv.className = 'legend-layer';

      var bRow = document.createElement('div');
      bRow.className = 'legend-layer-row';

      var bSwatch = document.createElement('span');
      bSwatch.className = 'legend-swatch';
      bSwatch.innerHTML = '<svg width="20" height="16" xmlns="http://www.w3.org/2000/svg">'
        + '<rect x="1" y="1" width="18" height="14" fill="#e8e4dc" stroke="#bbb"/>'
        + '<path d="M1 11 L7 6 L11 9 L19 3" stroke="#8bbf8b" stroke-width="1.5" fill="none"/>'
        + '<circle cx="14" cy="11" r="1.5" fill="#7a9fd0"/></svg>';

      var bName = document.createElement('span');
      bName.className = 'legend-layer-name';
      bName.textContent = 'OpenStreetMap';
      bName.title = 'OpenStreetMap basemap';

      var bSettingsDiv = document.createElement('div');
      bSettingsDiv.className = 'layer-settings';
      var bOpRow = document.createElement('div');
      bOpRow.className = 'layer-settings-row';
      var bOpLbl = document.createElement('span');
      bOpLbl.className = 'layer-settings-label';
      bOpLbl.textContent = 'Opacity';
      var bSlider = document.createElement('input');
      bSlider.type = 'range';
      bSlider.min = '0'; bSlider.max = '100'; bSlider.value = '100';
      bSlider.title = 'Basemap opacity';
      bSlider.addEventListener('input', function() {
        basemap.setOpacity(parseInt(bSlider.value, 10) / 100);
      });
      bOpRow.appendChild(bOpLbl);
      bOpRow.appendChild(bSlider);
      bSettingsDiv.appendChild(bOpRow);

      var bGsRow = document.createElement('div');
      bGsRow.className = 'layer-settings-row';
      var bGsLbl = document.createElement('label');
      bGsLbl.className = 'layer-settings-label';
      bGsLbl.textContent = 'Greyscale';
      bGsLbl.htmlFor = 'basemap-greyscale';
      var bGs = document.createElement('input');
      bGs.type = 'checkbox';
      bGs.id = 'basemap-greyscale';
      bGs.checked = _basemapGreyscale;
      bGs.title = 'Render the basemap in greyscale so data layers read more clearly';
      bGs.addEventListener('change', function() {
        setBasemapGreyscale(bGs.checked);
      });
      bGsRow.appendChild(bGsLbl);
      bGsRow.appendChild(bGs);
      bSettingsDiv.appendChild(bGsRow);

      bRow.appendChild(bSwatch);
      bRow.appendChild(bName);
      if (FEAT.fancyLabels) bRow.appendChild(makeCogBtn(bSettingsDiv));
      bDiv.appendChild(bRow);
      bDiv.appendChild(bSettingsDiv);
      body.appendChild(bDiv);
    })();  // end basemap legend entry
  } } catch(legendErr) { console.error('Legend build failed:', legendErr); }

  // ── Map-level click + drag (select or identify) ──────────────────────────
  var selectRect = document.getElementById('select-rect');
  var _dragStart = null, _dragRx, _dragRy, _dragRw, _dragRh;
  var _pickSpreadMode = false;
  function _dragModeOn() { return _selectMode || _identifyMode || _pickSpreadMode; }

  map.getContainer().addEventListener('mousedown', function(e) {
    if (!_dragModeOn() || e.button !== 0) return;
    e.preventDefault();
    map.dragging.disable();
    var rc = map.getContainer().getBoundingClientRect();
    _dragStart = {x: e.clientX - rc.left, y: e.clientY - rc.top};
    // Reset the rectangle: without this a plain click re-uses the previous
    // drag's dimensions and repeats that selection.
    _dragRx = _dragStart.x; _dragRy = _dragStart.y; _dragRw = 0; _dragRh = 0;
    selectRect.style.cssText += ';left:'+_dragStart.x+'px;top:'+_dragStart.y+'px;width:0;height:0;display:block';
  });

  document.addEventListener('mousemove', function(e) {
    if (!_dragModeOn() || !_dragStart) return;
    var rc = map.getContainer().getBoundingClientRect();
    var cx = e.clientX - rc.left, cy = e.clientY - rc.top;
    _dragRx = Math.min(_dragStart.x, cx); _dragRy = Math.min(_dragStart.y, cy);
    _dragRw = Math.abs(cx - _dragStart.x); _dragRh = Math.abs(cy - _dragStart.y);
    selectRect.style.left = _dragRx+'px'; selectRect.style.top = _dragRy+'px';
    selectRect.style.width = _dragRw+'px'; selectRect.style.height = _dragRh+'px';
  });

  document.addEventListener('mouseup', function(e) {
    if (!_dragModeOn() || !_dragStart) return;
    map.dragging.enable();
    selectRect.style.display = 'none';
    var ds = _dragStart;
    _dragStart = null;
    var tinyDrag = (_dragRw < 5 || _dragRh < 5);

    if (_pickSpreadMode) {
      // A click opens the cluster under the cursor; a drag takes the box.
      if (tinyDrag) pickSpreadAtPoint(ds);
      else pickSpreadInBounds(L.latLngBounds(
        map.containerPointToLatLng(L.point(_dragRx, _dragRy + _dragRh)),
        map.containerPointToLatLng(L.point(_dragRx + _dragRw, _dragRy))));
      return;
    }
    if (tinyDrag) return;

    var sw = map.containerPointToLatLng(L.point(_dragRx, _dragRy + _dragRh));
    var ne = map.containerPointToLatLng(L.point(_dragRx + _dragRw, _dragRy));
    var dragBounds = L.latLngBounds(sw, ne);

    if (_identifyMode) {
      // Identify drag: collect features across all visible vector layers
      var dragFound = [];
      legendItems.forEach(function(it) {
        if (!it.visible || it.ld.kind !== 'vector') return;
        it.lfl.eachLayer(function(fl) {
          if (!fl._infoHtml) return;
          var ll = fl.getLatLng ? fl.getLatLng()
                 : (fl.getBounds ? fl.getBounds().getCenter() : null);
          if (ll && dragBounds.contains(ll)) {
            dragFound.push({layerName: it.ld.name, html: fl._infoHtml, lfl: fl, legendItem: it});
          }
        });
      });
      if (dragFound.length) {
        showIdentifyResults(dragFound);
        infoPanel.classList.add('open');
      }
    } else if (FEAT.attrTable && attrTableLayer) {
      // Select drag: filter attribute table to one layer
      var selIdx = parseInt(attrTableLayer.value, 10);
      var targetItem = null;
      legendItems.forEach(function(it) { if (it.index === selIdx && it.ld.kind === 'vector') targetItem = it; });
      if (!targetItem) legendItems.forEach(function(it) { if (!targetItem && it.ld.kind === 'vector' && it.visible) targetItem = it; });
      if (targetItem) {
        var selSet = [];
        targetItem.ld.geojson.features.forEach(function(feat, fi) {
          if (!feat.geometry) return;
          var coords = feat.geometry.type === 'Point' ? [feat.geometry.coordinates]
                     : feat.geometry.type === 'MultiPoint' ? feat.geometry.coordinates : null;
          if (coords) {
            for (var ci = 0; ci < coords.length; ci++) {
              if (dragBounds.contains(L.latLng(coords[ci][1], coords[ci][0]))) { selSet.push(fi); return; }
            }
          } else {
            try {
              var center = L.geoJSON(feat).getBounds().getCenter();
              if (dragBounds.contains(center)) selSet.push(fi);
            } catch(ex) {}
          }
        });
        if (selSet.length) {
          attrTableLayer.value = targetItem.index;
          _attrSelectSet = selSet;
          populateAttrTable();
          attrTablePanel.classList.add('open');
        }
      }
    }
  });

  // ── Shared identify helpers ───────────────────────────────────────────────
  function getDisplayName(f) {
    var props = f.lfl._feature && f.lfl._feature.properties || {};
    var vals = Object.values(props).filter(function(v) { return v != null && v !== ''; });
    return vals.length ? String(vals[0]) : '(feature)';
  }

  function showIdentifySingle(f) {
    infoPanel.classList.remove('split');
    infoPanelBody.innerHTML = f.html;
    highlightFeatureOnMap(f.lfl._feature);
  }

  function showIdentifySplit(found) {
    infoPanel.classList.add('split');
    infoPanelBody.innerHTML = '';
    var splitDiv = document.createElement('div');
    splitDiv.className = 'info-split';
    var listPane = document.createElement('div');
    listPane.className = 'info-list-pane';
    var detailPane = document.createElement('div');
    detailPane.className = 'info-detail-pane';
    found.forEach(function(f) {
      var item = document.createElement('div');
      item.className = 'mf-item';
      var fStyle = resolveStyle(f.legendItem.ld.styleMap, f.lfl._feature && f.lfl._feature.properties || {});
      var fSwatch = swatchSvg(f.legendItem.ld.geomType, fStyle);
      item.innerHTML = '<span class="mf-swatch">'+fSwatch+'</span>'
                     + '<span class="mf-text">'
                     + '<div class="mf-feature-name">'+escHtml(getDisplayName(f))+'</div>'
                     + '<div class="mf-layer-name">'+escHtml(f.layerName)+'</div>'
                     + '</span>';
      item.addEventListener('click', function() {
        listPane.querySelectorAll('.mf-item').forEach(function(el) { el.classList.remove('active'); });
        item.classList.add('active');
        detailPane.innerHTML = f.html;
        highlightFeatureOnMap(f.lfl._feature);
      });
      listPane.appendChild(item);
    });
    splitDiv.appendChild(listPane);
    splitDiv.appendChild(detailPane);
    infoPanelBody.appendChild(splitDiv);
    listPane.querySelector('.mf-item').click();
  }

  function showIdentifyResults(found) {
    if (found.length === 1) showIdentifySingle(found[0]); else showIdentifySplit(found);
  }

  // ── Click identify ────────────────────────────────────────────────────────
  map.on('click', function(e) {
    if (_selectMode) return;  // select mode takes priority; identify always passive
    var clickPt = map.latLngToContainerPoint(e.latlng);
    var found = [];
    legendItems.forEach(function(it) {
      if (!it.visible || it.ld.kind !== 'vector') return;
      it.lfl.eachLayer(function(fl) {
        if (!fl._infoHtml) return;
        var latlng = fl.getLatLng ? fl.getLatLng()
                   : (fl.getBounds ? fl.getBounds().getCenter() : null);
        if (!latlng) return;
        var pt = map.latLngToContainerPoint(latlng);
        var d = Math.sqrt(Math.pow(pt.x - clickPt.x, 2) + Math.pow(pt.y - clickPt.y, 2));
        if (d <= 10) found.push({layerName: it.ld.name, html: fl._infoHtml, lfl: fl, legendItem: it});
      });
    });

    // WMS GetFeatureInfo — only when identify mode is explicitly active
    if (_identifyMode) {
      var wmsItems = legendItems.filter(function(it) {
        return it.visible && it.ld.kind === 'wms' && it.ld.wmsUrl
            && it.ld.tileType !== 'xyz' && it.ld.tileType !== 'wmts';
      });
      if (wmsItems.length > 0) {
        var pending = wmsItems.length;
        var wmsFound = [];
        wmsItems.forEach(function(it) {
          wmsIdentify(it, e.latlng, function(err, text) {
            pending--;
            if (!err && text) {
              var t = text.trim();
              if (t && t !== '' && !/no\s*feature/i.test(t) && !/<body>\s*<\/body>/i.test(t)
                  && !/<body>\s*no features/i.test(t)) {
                wmsFound.push({layerName: it.ld.name, text: t, legendItem: it});
              }
            }
            if (pending === 0 && (found.length || wmsFound.length)) {
              if (wmsFound.length) {
                wmsFound.forEach(function(w) {
                  var wrapper = {
                    layerName: w.layerName,
                    html: '<div style="font-size:11px;color:@@_th_acc@@;font-weight:600;margin-bottom:4px">'
                        + escHtml(w.layerName) + ' <em style="color:#999;font-weight:400">(WMS)</em></div>'
                        + '<iframe sandbox="allow-same-origin" srcdoc="'
                        + w.text.replace(/"/g, '&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                        + '" style="width:100%;min-height:80px;border:none;resize:vertical"></iframe>',
                    lfl: {_feature: null},
                    legendItem: w.legendItem
                  };
                  found.push(wrapper);
                });
              }
              showIdentifyResults(found);
              infoPanel.classList.add('open');
            }
          });
        });
        // Show any vector hits immediately while WMS queries are in flight
        if (found.length) {
          showIdentifyResults(found);
          infoPanel.classList.add('open');
        }
        return;
      }
    }

    if (!found.length) return;
    showIdentifyResults(found);
    infoPanel.classList.add('open');
  });

  // ── Populate attribute table layer selector ───────────────────────────────
  if (FEAT.attrTable && attrTableLayer) {
    legendItems.forEach(function(it) {
      if (it.ld.kind !== 'vector') return;
      var o = document.createElement('option');
      o.value = it.index; o.textContent = it.ld.name;
      attrTableLayer.appendChild(o);
    });
    attrTableLayer.addEventListener('change', function() {
      if (attrTableSearch) attrTableSearch.value = '';
      populateAttrTable();
    });
  }

  // A layer's label group stays on when the click-spread tool has pinned some
  // of its points, even though the layer's own labels are switched off.
  function _syncLabelGroup(item) {
    if (!item.labelGroup) return;
    var wanted = item.visible && (item.labelsVisible || (item._pinnedCount || 0) > 0);
    item.labelGroup.style.display = wanted ? '' : 'none';
  }

  function setLayerVisible(item, visible) {
    item.visible = visible;
    if (visible) addItemLayer(item);
    else removeItemLayer(item);
    if (item.checkbox) item.checkbox.checked = visible;
    if (item.layerDiv) item.layerDiv.classList.toggle('hidden', !visible);
    _syncLabelGroup(item);
    setTimeout(layoutAllLabels, 100);
    setTimeout(renderLineLabels, 100);
    setTimeout(renderLineTicks, 100);
  }

  function setLayerOpacity(item, factor) {
    var pane = map.getPane(item.paneName);
    if (pane) pane.style.opacity = factor;
  }

  function setLayerLabels(item, visible) {
    item.labelsVisible = visible;
    _syncLabelGroup(item);
    setTimeout(layoutAllLabels, 100);
    if (item.ld.geomType === 'line') setTimeout(renderLineLabels, 100);
  }

  // ── Label placement helpers ───────────────────────────────────────────────
  function _lblDims(text, fontSize) {
    return { w: text.length * fontSize * 0.55 + 8, h: fontSize * 1.4 };
  }

  function _lblOverlap(ax, ay, aw, ah, bx, by, bw, bh) {
    var ox = Math.max(0, (aw + bw) / 2 + 3 - Math.abs(ax - bx));
    var oy = Math.max(0, (ah + bh) / 2 + 3 - Math.abs(ay - by));
    return ox * oy;
  }

  function _candidatePlacement(labels) {
    var DIRS_ALL   = [[0,-1],[0.71,-0.71],[1,0],[0.71,0.71],[0,1],[-0.71,0.71],[-1,0],[-0.71,-0.71]];
    var DIRS_RIGHT = [[1,0],[0.71,-0.71],[0.71,0.71]]; // strictly right-side candidates
    var placed = [];
    labels.forEach(function(lbl) {
      var DIRS = lbl.rightForced ? DIRS_RIGHT : DIRS_ALL;
      var baseR = lbl.h * 0.55 + 6;
      var best = null, bestScore = Infinity;
      [1.0, 1.7, 2.6].forEach(function(rm) {
        DIRS.forEach(function(d) {
          var cx = lbl.ax + d[0] * (lbl.w / 2 + baseR * rm);
          var cy = lbl.ay + d[1] * (lbl.h / 2 + baseR * rm);
          var score = 0;
          placed.forEach(function(p) {
            score += _lblOverlap(cx, cy, lbl.w, lbl.h, p.x, p.y, p.w, p.h);
          });
          score += Math.sqrt(Math.pow(cx-lbl.ax,2)+Math.pow(cy-lbl.ay,2)) * 0.08;
          if (score < bestScore) { bestScore = score; best = {x:cx,y:cy}; }
        });
      });
      lbl.x = best.x; lbl.y = best.y;
      placed.push(lbl);
    });
  }

  function _forcePlacement(labels) {
    _candidatePlacement(labels); // warm start
    labels.forEach(function(l) { l.vx = 0; l.vy = 0; });
    for (var iter = 0; iter < 45; iter++) {
      var alpha = 1 - iter / 45;
      labels.forEach(function(li) {
        li.vx += (li.ax - li.x) * 0.035 * alpha;
        li.vy += (li.ay - li.y) * 0.035 * alpha;
        labels.forEach(function(lj) {
          if (li === lj) return;
          var ov = _lblOverlap(li.x, li.y, li.w, li.h, lj.x, lj.y, lj.w, lj.h);
          if (!ov) return;
          var dx = (li.x - lj.x) || 0.1, dy = (li.y - lj.y) || 0.1;
          var dist = Math.sqrt(dx*dx + dy*dy);
          var f = Math.sqrt(ov) * 0.75;
          li.vx += dx/dist*f; li.vy += dy/dist*f;
        });
        li.vx *= 0.62; li.vy *= 0.62;
        li.x += li.vx; li.y += li.vy;
      });
    }
  }

  // Return the LatLng at the midpoint of a Leaflet Polyline by arc length
  function _lineMidpoint(fl) {
    var latLngs = fl.getLatLngs();
    var pts = (latLngs.length && Array.isArray(latLngs[0])) ? latLngs[0] : latLngs;
    if (!pts.length) return null;
    if (pts.length === 1) return pts[0];
    var segs = [], total = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var d = map.distance(pts[i], pts[i + 1]);
      segs.push({ d: d, a: pts[i], b: pts[i + 1] });
      total += d;
    }
    var half = total / 2, cum = 0;
    for (var i = 0; i < segs.length; i++) {
      var seg = segs[i];
      if (cum + seg.d >= half) {
        var t = seg.d > 0 ? (half - cum) / seg.d : 0;
        return L.latLng(seg.a.lat + t * (seg.b.lat - seg.a.lat),
                        seg.a.lng + t * (seg.b.lng - seg.a.lng));
      }
      cum += seg.d;
    }
    return pts[pts.length - 1];
  }

  // ── Icon de-overlap / spread system ──────────────────────────────────────
  // Replaces marker clustering: overlapping point icons are stacked to the
  // right of their geographic centroid with thin leader lines back to their
  // true positions. Only activates at zoom >= SPREAD_MIN_ZOOM.
  var SPREAD_MIN_ZOOM   = 14;   // below this zoom, icons stay at true positions
  var SPREAD_THRESHOLD  = 38;   // px — icons closer than this get spread
  // Upper bound only — groups too tall for one column wrap into extra columns
  // rather than being skipped, so this no longer has to be small.
  var SPREAD_MAX_GROUP  = 60;   // beyond this, warn and leave the stack alone
  var SPREAD_MAX_MARKERS = 8000; // total visible spreadable markers before bailing
  var SPREAD_OFFSET_X   = 31;   // px right of group centroid for stack anchor
  var SPREAD_ICON_GAP   = 30;   // px vertical spacing between stacked icons
  var SPREAD_COL_GAP    = 54;   // px horizontal spacing between stacked columns

  var _spreadLeaderSvg = document.getElementById('spread-leader-svg');

  function _spreadGroupByProximity(pts, threshold) {
    // Bucket the markers into a grid of threshold-sized cells, so each marker
    // only has to be compared against the nine cells around it rather than
    // against every other marker. The previous all-pairs scan was quadratic,
    // which is why a marker cap existed — and that cap silently switched the
    // whole feature off on any reasonably sized layer.
    var grid = {}, i, j, key;
    for (i = 0; i < pts.length; i++) {
      key = Math.floor(pts[i].px / threshold) + ':' + Math.floor(pts[i].py / threshold);
      if (grid[key]) grid[key].push(i);
      else grid[key] = [i];
    }

    var groups = [], assigned = {}, t2 = threshold * threshold;
    for (i = 0; i < pts.length; i++) {
      if (assigned[i]) continue;
      var g = [i];
      assigned[i] = true;
      var cx = Math.floor(pts[i].px / threshold), cy = Math.floor(pts[i].py / threshold);
      for (var dx = -1; dx <= 1; dx++) {
        for (var dy = -1; dy <= 1; dy++) {
          var bucket = grid[(cx + dx) + ':' + (cy + dy)];
          if (!bucket) continue;
          for (var b = 0; b < bucket.length; b++) {
            j = bucket[b];
            // Same seed-point semantics as before: only pair against later,
            // still-unassigned markers.
            if (j <= i || assigned[j]) continue;
            var ddx = pts[i].px - pts[j].px, ddy = pts[i].py - pts[j].py;
            if (ddx * ddx + ddy * ddy < t2) { g.push(j); assigned[j] = true; }
          }
        }
      }
      // Keep index order so the stacking order matches the old behaviour.
      if (g.length > 1) g.sort(function(a, c) { return a - c; });
      groups.push(g);
    }
    return groups;
  }

  // Markers explicitly picked out with the click-spread tool, as
  // {mkr, item} pairs. They spread regardless of their layer's group setting.
  var _pinnedSpread = [];
  // Markers currently displaced from their true position. Kept so a re-run can
  // send home only the ones that no longer belong to a group, instead of
  // resetting every marker and immediately moving most of them back — that
  // round trip was visible as a flicker on every pan.
  var _spreadMoved = [];

  function _spreadCollect() {
    var all = [], touched = [];
    function add(mkr) {
      if (!mkr || !mkr._origLatLng || mkr._spreadSeen) return;
      mkr._spreadSeen = true;
      touched.push(mkr);
      var pt = map.latLngToContainerPoint(mkr._origLatLng);
      all.push({ mkr: mkr, px: pt.x, py: pt.y, origLatLng: mkr._origLatLng });
    }
    legendItems.forEach(function(item) {
      if (!item.visible || !item.spreadMarkers || !item.spreadMarkers.length) return;
      if (item.groupEnabled && item.groupMode === 'spread') item.spreadMarkers.forEach(add);
    });
    _pinnedSpread.forEach(function(p) { if (p.item.visible) add(p.mkr); });
    touched.forEach(function(m) { m._spreadSeen = false; });
    return all;
  }

  function spreadMarkers() {
    var zoom = map.getZoom();
    var moved = [];

    // Send home anything that was displaced last time but is not this time,
    // then re-run label layout. Markers that stay in a group are never moved
    // back through their true position on the way to their new slot.
    function finish() {
      _spreadMoved.forEach(function(mkr) {
        if (!mkr._spreadOn && mkr._origLatLng) mkr.setLatLng(mkr._origLatLng);
      });
      moved.forEach(function(mkr) { mkr._spreadOn = false; });
      _spreadMoved = moved;
      setTimeout(layoutAllLabels, 0);
    }

    // Clear leader lines — they are drawn in container space, so they are
    // redrawn from scratch on every view change.
    if (_spreadLeaderSvg) {
      _spreadLeaderSvg.innerHTML = '';
      _spreadLeaderSvg.style.opacity = '1';
    }
    if (zoom < SPREAD_MIN_ZOOM) { finish(); return; }

    // Positions are read from _origLatLng rather than the marker's current
    // location, so no restore pass is needed before measuring.
    var all = _spreadCollect();
    if (!all.length) { finish(); return; }
    // Grouping is now linear (see _spreadGroupByProximity), so this bound only
    // guards against the cost of repositioning a very large number of markers.
    // It says so rather than failing silently, which is what the old limit of
    // 400 did — that switched spreading off on any sizeable layer with no
    // indication why.
    if (all.length > SPREAD_MAX_MARKERS) {
      console.warn('Explode/spread: ' + all.length + ' points visible exceeds the '
        + 'limit of ' + SPREAD_MAX_MARKERS + ' — filter the layer or zoom in.');
      finish();
      return;
    }

    // 3. Group overlapping markers
    var groups = _spreadGroupByProximity(all, SPREAD_THRESHOLD);

    // 4. Spread groups of 2+
    var NS = 'http://www.w3.org/2000/svg';
    var leaderFrag = _spreadLeaderSvg ? document.createDocumentFragment() : null;

    // How many icons fit in one column at the current map height. A single
    // column taller than the map would push markers off-screen, so wide
    // groups wrap into further columns to the right instead of being skipped.
    var _mapH = map.getSize().y;
    var _perCol = Math.max(2, Math.floor((_mapH - SPREAD_ICON_GAP) / SPREAD_ICON_GAP));

    groups.forEach(function(g) {
      if (g.length < 2) return;
      if (g.length > SPREAD_MAX_GROUP) {
        // Still bounded, so a pathological stack cannot lock up the browser,
        // but say so rather than silently doing nothing.
        console.warn('Explode/spread: ' + g.length + ' overlapping points at this '
          + 'location exceeds the limit of ' + SPREAD_MAX_GROUP
          + ' — zoom in to separate them.');
        return;
      }

      // Centroid of original positions
      var cx = 0, cy = 0;
      g.forEach(function(i) { cx += all[i].px; cy += all[i].py; });
      cx /= g.length; cy /= g.length;

      var nCols   = Math.ceil(g.length / _perCol);
      var perCol  = Math.ceil(g.length / nCols);   // balance the columns
      var anchorX = cx + SPREAD_OFFSET_X;

      g.forEach(function(i, idx) {
        var m = all[i];
        var col = Math.floor(idx / perCol);
        var row = idx % perCol;
        // Height of this column (the last one may be short) so each is centred.
        var colCount = Math.min(perCol, g.length - col * perCol);
        var startY = cy - (colCount * SPREAD_ICON_GAP) / 2 + SPREAD_ICON_GAP / 2;
        var newPx = anchorX + col * SPREAD_COL_GAP;
        var newPy = startY + row * SPREAD_ICON_GAP;
        var newLatLng = map.containerPointToLatLng([newPx, newPy]);
        m.mkr.setLatLng(newLatLng);
        m.mkr._spreadOn = true;
        moved.push(m.mkr);

        // Draw leader line: original → spread position
        if (leaderFrag) {
          // Dot at true location
          var dot = document.createElementNS(NS, 'circle');
          dot.setAttribute('cx', m.px.toFixed(1));
          dot.setAttribute('cy', m.py.toFixed(1));
          dot.setAttribute('r', '2.5');
          dot.setAttribute('fill', '#666');
          dot.setAttribute('fill-opacity', '0.55');
          leaderFrag.appendChild(dot);
          // Leader line
          var line = document.createElementNS(NS, 'line');
          line.setAttribute('x1', m.px.toFixed(1));
          line.setAttribute('y1', m.py.toFixed(1));
          line.setAttribute('x2', newPx.toFixed(1));
          line.setAttribute('y2', newPy.toFixed(1));
          line.setAttribute('stroke', '#555');
          line.setAttribute('stroke-width', '1');
          line.setAttribute('stroke-opacity', '0.4');
          leaderFrag.appendChild(line);
        }
      });
    });

    if (_spreadLeaderSvg && leaderFrag) _spreadLeaderSvg.appendChild(leaderFrag);

    finish();
  }

  map.on('moveend zoomend viewreset', spreadMarkers);
  // Leader lines are anchored to container pixels, so during a pan they stay
  // put while the markers they point at move away. Hide them until the view
  // settles, the same way labels are handled.
  map.on('movestart zoomstart', function() {
    if (_spreadLeaderSvg) _spreadLeaderSvg.style.opacity = '0';
  });
  setTimeout(spreadMarkers, 250);

  // ── Label pan/zoom hide ────────────────────────────────────────────────────
  // Hide labels while the map is moving; they are recalculated on moveend so
  // the brief disappearance is less jarring than labels drifting behind the map.
  map.on('movestart zoomstart', function() {
    if (_labelSvg) _labelSvg.style.opacity = '0';
    if (_lineDecoSvg) _lineDecoSvg.style.opacity = '0';
  });

  // ── Marker / hashed line ticks ────────────────────────────────────────────
  // QGIS marker-lines and hashed-lines (repeated ticks/markers along a line)
  // are exported as 'tick' strokes; they can't be a Leaflet polyline dash, so
  // they are drawn as perpendicular hash marks in a container-space SVG,
  // re-projected on every move/zoom like the labels.
  var _lineDecoSvg = document.getElementById('line-deco-svg');

  function _tickStrokesOf(featStyle) {
    var out = [];
    if (featStyle && featStyle.strokes) {
      featStyle.strokes.forEach(function(s) { if (s.tick) out.push(s); });
    }
    return out;
  }

  function _drawTicksAlong(pts, ts, w, h, frag, NS) {
    var interval = Math.max(4, ts.interval || 8);
    var half = (ts.tickLen || 6) / 2;
    var color = ts.color || '#000';
    var width = ts.weight || 1.5;
    var opacity = ts.opacity != null ? ts.opacity : 1;
    var next = interval * 0.5;   // first tick half an interval in
    var run = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i], b = pts[i + 1];
      var dx = b.x - a.x, dy = b.y - a.y;
      var segLen = Math.sqrt(dx * dx + dy * dy);
      if (segLen < 0.001) continue;
      var ux = dx / segLen, uy = dy / segLen;   // unit along segment
      var nx = -uy, ny = ux;                     // unit perpendicular
      while (next <= run + segLen) {
        var d = next - run;
        var px = a.x + ux * d, py = a.y + uy * d;
        next += interval;
        if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue; // cull
        var line = document.createElementNS(NS, 'line');
        line.setAttribute('x1', (px - nx * half).toFixed(1));
        line.setAttribute('y1', (py - ny * half).toFixed(1));
        line.setAttribute('x2', (px + nx * half).toFixed(1));
        line.setAttribute('y2', (py + ny * half).toFixed(1));
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', width);
        line.setAttribute('stroke-opacity', opacity);
        frag.appendChild(line);
      }
      run += segLen;
    }
  }

  function renderLineTicks() {
    if (!_lineDecoSvg) return;
    _lineDecoSvg.style.opacity = '1';
    _lineDecoSvg.innerHTML = '';
    var NS = 'http://www.w3.org/2000/svg';
    var size = map.getSize(), w = size.x, h = size.y;
    var frag = document.createDocumentFragment();
    legendItems.forEach(function(item) {
      if (!item.visible || item.ld.kind !== 'vector' || item.ld.geomType !== 'line') return;
      if (!item.lfl || !item.lfl.eachLayer) return;
      item.lfl.eachLayer(function(fl) {
        if (!fl.getLatLngs) return;
        var props = fl.feature && fl.feature.properties || {};
        var ticks = _tickStrokesOf(resolveStyle(item.ld.styleMap, props));
        if (!ticks.length) return;
        var raw = fl.getLatLngs();
        // normalise to an array of coordinate lists (handle multi-part lines)
        var lines = (raw.length && raw[0] && raw[0].lat !== undefined) ? [raw] : raw;
        lines.forEach(function(latlngs) {
          if (!latlngs || !latlngs.length) return;
          var pts = latlngs.map(function(ll) { return map.latLngToContainerPoint(ll); });
          ticks.forEach(function(ts) { _drawTicksAlong(pts, ts, w, h, frag, NS); });
        });
      });
    });
    _lineDecoSvg.appendChild(frag);
  }

  map.on('moveend zoomend viewreset', renderLineTicks);
  setTimeout(renderLineTicks, 300);

  // ── SVG label render pass ─────────────────────────────────────────────────
  function layoutAllLabels() {
    if (!_labelSvg) return;
    _labelSvg.style.opacity = '1';  // restore after pan/zoom
    var staticLabels = [];   // rendered directly at seeded position — no solver
    var solverLabels = [];   // run through candidate/force solver
    var _vpBounds = map.getBounds().pad(0.15); // viewport + 15% margin for culling

    _allLabelItems.forEach(function(item) {
      if (!item.visible || !item.labelData) return;
      // Points picked out with the click-spread tool carry their labels even
      // when the layer's own labels are switched off.
      var hasPinned = (item._pinnedCount || 0) > 0;
      if (!item.labelsVisible && !hasPinned) return;
      var cfg = item.labelCfg;
      var fsz = cfg.fontSize || 11;
      // Scale-based label visibility: convert QGIS scale denominators to zoom levels
      if (cfg.labelScaleMin || cfg.labelScaleMax) {
        var zoom = map.getZoom();
        var LOG2 = Math.log(2);
        // labelScaleMin = most-zoomed-in denominator → cap at high zoom
        var maxAllowedZoom = cfg.labelScaleMin ?
            Math.log(559082264 / cfg.labelScaleMin) / LOG2 : 24;
        // labelScaleMax = most-zoomed-out denominator → floor at low zoom
        var minAllowedZoom = cfg.labelScaleMax ?
            Math.log(559082264 / cfg.labelScaleMax) / LOG2 : 0;
        if (zoom < minAllowedZoom || zoom > maxAllowedZoom) return;
      }
      // Spread mode forces labels to the right and uses static placement
      var layerSpread = item.groupEnabled && item.groupMode === 'spread';
      var isLine = item.ld.geomType === 'line';
      var isPolygon = item.ld.geomType === 'polygon';
      // Line/polygon labels: vertical offset; centered on anchor; no right-side shift; always static
      var lineOffsetY = 0;
      if (isLine && cfg.linePlacement) {
        var lineOffsetPx = Math.round(fsz * 0.7 + 2);
        if (cfg.linePlacement === 'above') lineOffsetY = -lineOffsetPx;
        else if (cfg.linePlacement === 'below') lineOffsetY = lineOffsetPx;
      }

      item.labelData.forEach(function(ld) {
        var pinned = !!(ld.lyr && ld.lyr._spreadPinned);
        if (!item.labelsVisible && !pinned) return;
        var rightForced = layerSpread || pinned;
        var useStatic = rightForced || _labelPlacementMode === 'static';
        var curLatLng = (ld.lyr && ld.lyr.getLatLng) ? ld.lyr.getLatLng() : ld.latlng;
        if (!_vpBounds.contains(curLatLng)) return; // skip labels outside current viewport
        var pt = map.latLngToContainerPoint(curLatLng);
        var dims = _lblDims(ld.text, fsz);
        var initX = (useStatic && !isLine && !isPolygon) ? pt.x + dims.w * 0.5 + 8 : pt.x;
        var initY = pt.y + lineOffsetY;
        var lblObj = {
          text: ld.text, cfg: cfg,
          ax: pt.x, ay: pt.y,
          x: initX, y: initY,
          w: dims.w, h: dims.h,
          vx: 0, vy: 0,
          rightForced: rightForced,
          suppressCallout: (useStatic && !rightForced) || isLine || isPolygon,
          group: item.labelGroup
        };
        if (useStatic || isLine || isPolygon) {
          staticLabels.push(lblObj);
        } else {
          solverLabels.push(lblObj);
        }
      });
    });

    // Clear SVG groups
    _allLabelItems.forEach(function(item) {
      if (item.labelGroup) item.labelGroup.innerHTML = '';
    });
    if (!staticLabels.length && !solverLabels.length) return;

    if (solverLabels.length) {
      if (_labelPlacementMode === 'force') {
        _forcePlacement(solverLabels);
      } else {
        _candidatePlacement(solverLabels);
      }
    }

    // Render labels and callouts
    var NS = 'http://www.w3.org/2000/svg';
    staticLabels.concat(solverLabels).forEach(function(lbl) {
      if (!lbl.group) return;
      var cfg = lbl.cfg;
      var fsz = cfg.fontSize || 11;
      var g = document.createElementNS(NS, 'g');

      // Solid callout line when displaced > 8 px (suppressed for pure static labels)
      var dx = lbl.x - lbl.ax, dy = lbl.y - lbl.ay;
      if (!lbl.suppressCallout && Math.sqrt(dx*dx + dy*dy) > 8) {
        var line = document.createElementNS(NS, 'line');
        line.setAttribute('x1', lbl.ax.toFixed(1));
        line.setAttribute('y1', lbl.ay.toFixed(1));
        line.setAttribute('x2', lbl.x.toFixed(1));
        line.setAttribute('y2', lbl.y.toFixed(1));
        line.setAttribute('stroke', cfg.fontColor || '#333');
        line.setAttribute('stroke-width', '1');
        line.setAttribute('stroke-opacity', '0.4');
        g.appendChild(line);
      }

      var t = document.createElementNS(NS, 'text');
      t.setAttribute('x', lbl.x.toFixed(1));
      t.setAttribute('y', lbl.y.toFixed(1));
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'central');
      t.setAttribute('font-size', fsz + 'px');
      t.setAttribute('font-family', (cfg.fontFamily || 'Arial') + ', Arial, sans-serif');
      t.setAttribute('fill', cfg.fontColor || '#000');
      t.setAttribute('fill-opacity', cfg.fontOpacity != null ? cfg.fontOpacity : 1);
      if (cfg.bold) t.setAttribute('font-weight', 'bold');
      if (cfg.italic) t.setAttribute('font-style', 'italic');
      if (cfg.bufferSize > 0) {
        t.setAttribute('stroke', cfg.bufferColor || '#fff');
        t.setAttribute('stroke-width', (cfg.bufferSize * 1.5) + 'px');
        t.setAttribute('paint-order', 'stroke fill');
        t.setAttribute('stroke-linejoin', 'round');
      }
      t.textContent = lbl.text;
      g.appendChild(t);
      lbl.group.appendChild(g);
    });
  }

  // ── Curved line labels (SVG textPath) ─────────────────────────────────────
  // Line labels are rendered as one self-contained pass over all line layers
  // into a dedicated group, cleared and rebuilt each time — deliberately
  // independent of the point-label group lifecycle so a layer rebuild or a
  // point-label relayout can never wipe them.
  function buildLineLabels(item) {
    item.labelCfg = item.ld.labelConfig;
    if (_lineLabelItems.indexOf(item) === -1) _lineLabelItems.push(item);
    map.off('moveend zoomend viewreset', renderLineLabels);
    map.on('moveend zoomend viewreset', renderLineLabels);
    setTimeout(renderLineLabels, 150);
  }

  function _projectLine(latlngs) {
    var pts = [];
    for (var i = 0; i < latlngs.length; i++) {
      pts.push(map.latLngToContainerPoint(latlngs[i]));
    }
    return pts;
  }

  function _polylineLenPx(pts) {
    var d = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var dx = pts[i + 1].x - pts[i].x, dy = pts[i + 1].y - pts[i].y;
      d += Math.sqrt(dx * dx + dy * dy);
    }
    return d;
  }

  var _lineLabelGroup = null;
  function renderLineLabels() {
    if (!_labelSvg) return;
    _labelSvg.style.opacity = '1';  // restore after pan/zoom (may be line-only map)
    var NS = 'http://www.w3.org/2000/svg';
    // One dedicated group, rebuilt each pass and kept last so line labels
    // paint above point labels; never touched by the point-label relayout.
    if (!_lineLabelGroup) {
      _lineLabelGroup = document.createElementNS(NS, 'g');
      _lineLabelGroup.setAttribute('id', 'line-label-layer');
    }
    _lineLabelGroup.innerHTML = '';
    _labelSvg.appendChild(_lineLabelGroup);  // (re)attach and keep last = on top
    var g = _lineLabelGroup;
    var size = map.getSize(), W = size.x, H = size.y;
    _lineLabelItems.forEach(function(item) {
      if (!item.visible || !item.labelsVisible || !item.lfl || !item.lfl.eachLayer) return;
      var cfg = item.labelCfg || item.ld.labelConfig || {};
      var fsz = cfg.fontSize || 11;
      // Scale-based visibility (same rule as point labels)
      if (cfg.labelScaleMin || cfg.labelScaleMax) {
        var zoom = map.getZoom(), LOG2 = Math.log(2);
        var maxZ = cfg.labelScaleMin ? Math.log(559082264 / cfg.labelScaleMin) / LOG2 : 24;
        var minZ = cfg.labelScaleMax ? Math.log(559082264 / cfg.labelScaleMax) / LOG2 : 0;
        if (zoom < minZ || zoom > maxZ) return;
      }
      var side = cfg.linePlacement || 'above';
      item.lfl.eachLayer(function(fl) {
        if (!fl.getLatLngs) return;
        var props = fl.feature && fl.feature.properties;
        if (!props) return;
        var val = props[cfg.field];
        if (val == null || val === '') return;
        var text = String(val);
        var raw = fl.getLatLngs();
        var lines = (raw.length && raw[0] && raw[0].lat !== undefined) ? [raw] : raw;
        // Label the longest part only, to avoid repeating on every segment
        var best = null, bestLen = -1;
        lines.forEach(function(ll) {
          var pts = _projectLine(ll);
          var len = _polylineLenPx(pts);
          if (len > bestLen) { bestLen = len; best = pts; }
        });
        if (!best || best.length < 2) return;
        // Cull if the whole line is off-screen
        var onScreen = best.some(function(p) { return p.x > -40 && p.x < W + 40 && p.y > -40 && p.y < H + 40; });
        if (!onScreen) return;
        // Need room for the text along the line
        var textLen = text.length * fsz * 0.6;
        if (bestLen < textLen * 0.8) return;
        // Ensure left-to-right reading direction
        var pts = best;
        if (pts[pts.length - 1].x < pts[0].x) pts = pts.slice().reverse();
        var dPath = 'M' + pts.map(function(p) { return p.x.toFixed(1) + ' ' + p.y.toFixed(1); }).join(' L');
        var pid = 'llp' + (++_lineLabelPathId);
        var path = document.createElementNS(NS, 'path');
        path.setAttribute('id', pid);
        path.setAttribute('d', dPath);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'none');
        g.appendChild(path);
        var t = document.createElementNS(NS, 'text');
        t.setAttribute('font-size', fsz);
        t.setAttribute('font-family', cfg.fontFamily || 'sans-serif');
        if (cfg.bold) t.setAttribute('font-weight', 'bold');
        if (cfg.italic) t.setAttribute('font-style', 'italic');
        t.setAttribute('fill', cfg.fontColor || '#222');
        if (cfg.fontOpacity != null) t.setAttribute('fill-opacity', cfg.fontOpacity);
        // Buffer / halo via paint-order stroke behind the fill
        if (cfg.bufferSize) {
          t.setAttribute('stroke', cfg.bufferColor || '#fff');
          t.setAttribute('stroke-width', cfg.bufferSize * 2);
          t.setAttribute('stroke-linejoin', 'round');
          t.setAttribute('paint-order', 'stroke');
        }
        // above / on / below → vertical shift relative to the path
        var dy = 0;
        if (side === 'above') dy = -Math.round(fsz * 0.35);
        else if (side === 'below') dy = Math.round(fsz * 0.9);
        else dy = Math.round(fsz * 0.35);
        t.setAttribute('dy', dy);
        var tp = document.createElementNS(NS, 'textPath');
        tp.setAttribute('href', '#' + pid);
        tp.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', '#' + pid);
        tp.setAttribute('startOffset', '50%');
        tp.setAttribute('text-anchor', 'middle');
        tp.textContent = text;
        t.appendChild(tp);
        g.appendChild(t);
      });
    });
  }

  function buildLabels(item) {
    var ld = item.ld;
    if (!ld.labelConfig || ld.kind !== 'vector') return;
    var cfg = ld.labelConfig;

    // Line layers: labels follow the line via SVG textPath (see
    // renderLineLabels) rather than being placed as horizontal text.
    if (ld.geomType === 'line') {
      buildLineLabels(item);
      return;
    }

    // Collect label anchor points — store lyr reference so labels follow spread markers
    var labelData = [];
    item.lfl.eachLayer(function(fl) {
      var props = fl.feature && fl.feature.properties;
      if (!props) return;
      var val = props[cfg.field];
      if (val == null || val === '') return;
      var initLatLng;
      if (ld.geomType === 'line' && fl.getLatLngs) {
        initLatLng = _lineMidpoint(fl);
      } else if (fl.getLatLng) {
        initLatLng = fl.getLatLng();
      } else if (fl.getBounds) {
        initLatLng = fl.getBounds().getCenter();
      }
      if (initLatLng) labelData.push({ text: String(val), lyr: fl.getLatLng ? fl : null, latlng: initLatLng });
    });
    item.labelData = labelData;
    item.labelCfg = cfg;

    // Replace any old SVG group for this item
    if (item.labelGroup && item.labelGroup.parentNode) {
      item.labelGroup.parentNode.removeChild(item.labelGroup);
    }
    var NS = 'http://www.w3.org/2000/svg';
    var g = document.createElementNS(NS, 'g');
    g.style.display = (item.visible && (item.labelsVisible || (item._pinnedCount || 0) > 0)) ? '' : 'none';
    if (_labelSvg) _labelSvg.appendChild(g);
    item.labelGroup = g;

    if (_allLabelItems.indexOf(item) === -1) _allLabelItems.push(item);
    map.off('moveend zoomend viewreset', layoutAllLabels);
    map.on('moveend zoomend viewreset', layoutAllLabels);
    setTimeout(layoutAllLabels, 150);
  }

  // ── Filter toolbar ─────────────────────────────────────────────────────────
  if (FEAT.filter) (function initFilter() {
    var vectorItems = legendItems.filter(function(it) { return it.ld.kind === 'vector'; });
    if (vectorItems.length === 0) return;

    var bar          = document.getElementById('filterbar');
    var layerSel     = document.getElementById('filter-layer');
    var attrSel      = document.getElementById('filter-attr');
    var valuesBtn    = document.getElementById('filter-values-btn');
    var valuesPanel  = document.getElementById('filter-values-panel');
    var valuesSearch = document.getElementById('filter-values-search');
    var valuesList   = document.getElementById('filter-values-list');
    var clearBtn     = document.getElementById('filter-clear');
    var countEl      = document.getElementById('filter-count');

    // Create the filter toggle as a Leaflet control so it stacks with other controls
    var FilterToggle = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-filter');
        btn.title = 'Toggle attribute filter';
        btn.setAttribute('aria-label', 'Toggle attribute filter');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">'
          + '<path d="M2 3h14l-5 5.5V15l-4-2V8.5z" fill="#555" stroke="#444" stroke-width="0.5" stroke-linejoin="round"/></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          var isOpen = bar.style.display === 'flex';
          bar.style.display = isOpen ? 'none' : 'flex';
          btn.classList.toggle('active', !isOpen);
        });
        return btn;
      }
    });
    new FilterToggle({ position: 'topleft' }).addTo(map);

    // Populate layer dropdown (value = index into legendItems)
    vectorItems.forEach(function(it) {
      var o = document.createElement('option');
      o.value = it.index;
      o.textContent = it.ld.name;
      layerSel.appendChild(o);
    });

    function currentItem() {
      return legendItems[parseInt(layerSel.value, 10)];
    }

    function checkedValues() {
      var out = [];
      Array.prototype.forEach.call(valuesList.querySelectorAll('input:checked'), function(c) {
        out.push(c.value);
      });
      return out;
    }

    function updateValuesBtn() {
      var sel = checkedValues();
      if (sel.length) valuesBtn.textContent = sel.length + ' selected';
      else if (valuesSearch.value.trim()) valuesBtn.textContent = 'contains: ' + valuesSearch.value.trim();
      else valuesBtn.textContent = 'All values';
    }

    function updateCount(item) {
      var total = item.ld.geojson.features.length;
      var shown = item.filterFn ? item.ld.geojson.features.filter(item.filterFn).length : total;
      countEl.textContent = shown + ' / ' + total;
    }

    function clearOtherFilters(keep) {
      legendItems.forEach(function(it) {
        if (it !== keep && it.filterFn) { it.filterFn = null; rebuildLayer(it); }
      });
    }

    function applyFilter() {
      var item = currentItem();
      if (!item) return;
      var attr = attrSel.value;
      var search = valuesSearch.value.trim().toLowerCase();
      var selected = checkedValues();
      if (!attr || (selected.length === 0 && !search)) {
        item.filterFn = null;
      } else {
        // Lookup object, not indexOf: the predicate runs once per feature, so a
        // linear scan of the selected values makes filtering quadratic.
        var selLookup = null;
        if (selected.length) {
          selLookup = {};
          for (var si = 0; si < selected.length; si++) selLookup['v' + selected[si]] = 1;
        }
        item.filterFn = function(feature) {
          var v = (feature.properties || {})[attr];
          var sv = (v == null ? '' : String(v));
          if (selLookup) return selLookup['v' + sv] === 1;
          return sv.toLowerCase().indexOf(search) !== -1;
        };
      }
      rebuildLayer(item);
      updateCount(item);
    }

    function populateAttrs() {
      var item = currentItem();
      attrSel.innerHTML = '';
      if (!item) return;
      var feats = item.ld.geojson.features;
      var keys = [], seen = {};
      for (var i = 0; i < Math.min(feats.length, 50); i++) {
        var p = feats[i].properties || {};
        for (var k in p) { if (!(k in seen)) { seen[k] = 1; keys.push(k); } }
      }
      keys.forEach(function(k) {
        var o = document.createElement('option');
        o.value = k; o.textContent = k;
        attrSel.appendChild(o);
      });
    }

    function populateValues() {
      var item = currentItem();
      var attr = attrSel.value;
      valuesList.innerHTML = '';
      valuesSearch.value = '';
      if (!item || !attr) { updateValuesBtn(); return; }
      var feats = item.ld.geojson.features;
      var seen = {}, vals = [];
      for (var i = 0; i < feats.length; i++) {
        var v = (feats[i].properties || {})[attr];
        var sv = (v == null ? '' : String(v));
        if (!(sv in seen)) { seen[sv] = 1; vals.push(sv); }
        if (vals.length > 2000) break;
      }
      vals.sort(function(a, b) {
        var na = parseFloat(a), nb = parseFloat(b);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return a < b ? -1 : (a > b ? 1 : 0);
      });
      vals.forEach(function(val) {
        var lab = document.createElement('label');
        lab.className = 'filter-value-item';
        var c = document.createElement('input');
        c.type = 'checkbox'; c.value = val;
        var s = document.createElement('span');
        s.textContent = (val === '' ? '(empty)' : val);
        s.title = val;
        lab.appendChild(c); lab.appendChild(s);
        valuesList.appendChild(lab);
      });
      updateValuesBtn();
    }

    // Events
    // One delegated listener on the value list, rather than one per checkbox —
    // populateValues can render up to 2000 of them for a large layer.
    valuesList.addEventListener('change', function(ev) {
      if (!ev.target || ev.target.type !== 'checkbox') return;
      applyFilter();
      updateValuesBtn();
    });
    layerSel.addEventListener('change', function() {
      var item = currentItem();
      clearOtherFilters(item);
      populateAttrs();
      populateValues();
      applyFilter();
    });
    attrSel.addEventListener('change', function() {
      populateValues();
      applyFilter();
    });
    // Narrowing the value list is cheap and should stay immediate; re-applying
    // the filter rebuilds the whole layer, so that part is debounced — without
    // it, every keystroke rebuilt a large layer and the filter appeared to hang.
    var _filterSearchTimer = null;
    valuesSearch.addEventListener('input', function() {
      var q = valuesSearch.value.trim().toLowerCase();
      Array.prototype.forEach.call(valuesList.children, function(el) {
        el.style.display = el.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
      });
      updateValuesBtn();
      if (_filterSearchTimer) clearTimeout(_filterSearchTimer);
      _filterSearchTimer = setTimeout(applyFilter, 200);
    });
    valuesBtn.addEventListener('click', function() {
      valuesPanel.classList.toggle('open');
    });
    document.addEventListener('click', function(e) {
      if (!document.getElementById('filter-values-wrap').contains(e.target)) {
        valuesPanel.classList.remove('open');
      }
    });
    clearBtn.addEventListener('click', function() {
      valuesSearch.value = '';
      Array.prototype.forEach.call(valuesList.querySelectorAll('input:checked'), function(c) {
        c.checked = false;
      });
      Array.prototype.forEach.call(valuesList.children, function(el) { el.style.display = ''; });
      applyFilter();
      updateValuesBtn();
    });

    // Initialise with the first vector layer
    populateAttrs();
    populateValues();
    var first = currentItem();
    if (first) updateCount(first);
  })();

  // ── Global smart search (greys out non-matching features in all layers) ────
  if (FEAT.search) (function initGlobalSearch() {
    var vectorItems = legendItems.filter(function(it) { return it.ld.kind === 'vector'; });
    if (vectorItems.length === 0) return;

    var bar     = document.getElementById('searchbar');
    var input   = document.getElementById('search-input');
    var clearB  = document.getElementById('search-clear');
    var countEl = document.getElementById('search-count');
    var _searchQ = '';

    var SearchToggle = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-filter');
        btn.title = 'Search all layers';
        btn.setAttribute('aria-label', 'Search all layers');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
          + '<circle cx="8" cy="8" r="5.4" fill="none" stroke="#444" stroke-width="1.9"/>'
          + '<path d="M9.8 2.5 L6.0 8.5 h2.8 L7.2 13.5 L12.2 7.5 h-3 z" fill="#f5a623" stroke="#c47f00" stroke-width="0.6" stroke-linejoin="round"/>'
          + '<line x1="12.2" y1="12.2" x2="17.2" y2="17.2" stroke="#444" stroke-width="2.5" stroke-linecap="round"/></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          var isOpen = bar.style.display === 'flex';
          bar.style.display = isOpen ? 'none' : 'flex';
          btn.classList.toggle('active', !isOpen);
          if (!isOpen) input.focus();
        });
        return btn;
      }
    });
    new SearchToggle({ position: 'topleft' }).addTo(map);

    function featureText(f) {
      var p = (f && f.properties) || {};
      var out = [];
      for (var k in p) {
        var v = p[k];
        if (v != null) out.push(String(v).toLowerCase());
      }
      return out.join('\u0001');
    }

    function dimLayer(lyr) {
      if (lyr.setStyle) {
        try {
          lyr.setStyle({ color: '#9e9e9e', fillColor: '#9e9e9e',
                          opacity: 0.1, fillOpacity: 0.1 });
        } catch (e) {}
      }
      if (lyr.setOpacity) {
        try { lyr.setOpacity(0.1); } catch (e) {}
      }
      try {
        var el = lyr.getElement && lyr.getElement();
        if (el && el.style) el.style.filter = 'grayscale(1)';
      } catch (e) {}
    }

    function walkFeatureLayers(group, fn) {
      group.eachLayer(function(l) {
        if (l.feature || l._feature) fn(l);
        else if (typeof l.eachLayer === 'function') walkFeatureLayers(l, fn);
      });
    }

    function applySearch() {
      var q = input.value.trim().toLowerCase();
      _searchQ = q;
      // Reset all vector layers to their true symbology first
      vectorItems.forEach(function(it) { rebuildLayer(it); });
      if (!q) { countEl.textContent = ''; return; }
      var matched = 0, total = 0;
      vectorItems.forEach(function(it) {
        if (!it.lfl || !it.visible) return;
        walkFeatureLayers(it.lfl, function(l) {
          var f = l.feature || l._feature;
          if (!f) return;
          total++;
          if (featureText(f).indexOf(q) !== -1) { matched++; return; }
          dimLayer(l);
        });
      });
      countEl.textContent = matched + ' / ' + total + ' match';
    }

    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') applySearch();
      if (e.key === 'Escape') { input.value = ''; applySearch(); }
    });
    clearB.addEventListener('click', function() {
      input.value = '';
      applySearch();
    });
  })();

  // ── Measure tool ─────────────────────────────────────────────────────────────
  if (FEAT.measure) {
    var _measureMode = false, _measurePoints = [], _measureLayer = null, _measureMarkers = [];
    // Own panes above every data/label pane, so measurements are never buried
    // under the basemap, an overlay raster or the label layer.
    if (!map.getPane('measurePane')) {
      map.createPane('measurePane');
      map.getPane('measurePane').style.zIndex = 900;
      map.getPane('measurePane').style.pointerEvents = 'none';
    }
    if (!map.getPane('measureLabelPane')) {
      map.createPane('measureLabelPane');
      map.getPane('measureLabelPane').style.zIndex = 901;
      map.getPane('measureLabelPane').style.pointerEvents = 'none';
    }
    var MeasureBtn = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
        btn.id = 'measure-btn';
        btn.title = 'Measure distance (click points, double-click to finish)';
        btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;';
        btn.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg">'
          + '<line x1="2" y1="18" x2="18" y2="2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
          + '<line x1="2" y1="18" x2="6" y2="18" stroke="currentColor" stroke-width="1.5"/>'
          + '<line x1="2" y1="18" x2="2" y2="14" stroke="currentColor" stroke-width="1.5"/>'
          + '<line x1="7" y1="13" x2="9" y2="15" stroke="currentColor" stroke-width="1"/>'
          + '<line x1="11" y1="9" x2="13" y2="11" stroke="currentColor" stroke-width="1"/>'
          + '</svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          _measureMode = !_measureMode;
          btn.classList.toggle('measure-active', _measureMode);
          if (_measureMode) {
            map.getContainer().style.cursor = 'crosshair';
          } else {
            _clearMeasure();
          }
        });
        return btn;
      }
    });
    new MeasureBtn({position: 'topleft'}).addTo(map);

    function _clearMeasure() {
      _measurePoints = [];
      if (_measureLayer) { map.removeLayer(_measureLayer); _measureLayer = null; }
      _measureMarkers.forEach(function(m) { map.removeLayer(m); });
      _measureMarkers = [];
      map.getContainer().style.cursor = '';
    }

    function _fmtDist(m) {
      return m >= 1000 ? (m / 1000).toFixed(2) + ' km' : Math.round(m) + ' m';
    }

    map.on('click', function(e) {
      if (!_measureMode) return;
      _measurePoints.push(e.latlng);
      if (_measureLayer) map.removeLayer(_measureLayer);
      _measureLayer = L.polyline(_measurePoints, {
        color: '#e63329', weight: 2, dashArray: '6 4', interactive: false,
        pane: 'measurePane'
      }).addTo(map);
      var dist = 0;
      for (var i = 1; i < _measurePoints.length; i++) {
        dist += _measurePoints[i - 1].distanceTo(_measurePoints[i]);
      }
      var lbl = L.marker(e.latlng, {
        icon: L.divIcon({
          html: '<div class="measure-label">' + _fmtDist(dist) + '</div>',
          className: '', iconAnchor: [0, -6]
        }),
        interactive: false,
        pane: 'measureLabelPane'
      }).addTo(map);
      _measureMarkers.push(lbl);
    });

    map.on('dblclick', function(e) {
      if (!_measureMode) return;
      L.DomEvent.stop(e);
      _measureMode = false;
      var btn = document.getElementById('measure-btn');
      if (btn) btn.classList.remove('measure-active');
      map.getContainer().style.cursor = '';
    });
  }

  // ── Click-spread tool ────────────────────────────────────────────────────
  // Spread on demand: click a knot of overlapping points, or drag a box over
  // them, and just those points fan out with their labels pinned on. Unlike
  // the per-layer Explode setting this ignores layer boundaries and leaves
  // the rest of the map alone.
  if (FEAT.fancyLabels) (function() {
    var SpreadPickBtn = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
        btn.id = 'spread-pick-btn';
        btn.title = 'Spread points: click a cluster or drag a box over points';
        btn.setAttribute('aria-label', 'Spread points');
        btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;';
        btn.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg">'
          + '<circle cx="6" cy="10" r="2.2" fill="currentColor"/>'
          + '<circle cx="15" cy="4.5" r="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
          + '<circle cx="15" cy="10" r="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
          + '<circle cx="15" cy="15.5" r="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
          + '<path d="M7.8 9.2 13.2 5.2M8.2 10h4.9M7.8 10.8l5.4 4" fill="none" stroke="currentColor" stroke-width="1" stroke-opacity="0.55"/>'
          + '</svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() { setSpreadPick(!_pickSpreadMode); });
        return btn;
      }
    });
    new SpreadPickBtn({position: 'topleft'}).addTo(map);

    window._imSetSpreadPick = setSpreadPick;

    function setSpreadPick(on) {
      _pickSpreadMode = !!on;
      var btn = document.getElementById('spread-pick-btn');
      if (btn) btn.classList.toggle('measure-active', _pickSpreadMode);
      map.getContainer().style.cursor = _pickSpreadMode ? 'crosshair' : '';
      // Leaving the tool puts everything it spread back where it belongs.
      if (!_pickSpreadMode) clearPinnedSpread();
    }

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && _pickSpreadMode) setSpreadPick(false);
    });
  })();

  function clearPinnedSpread(onlyItem) {
    var kept = [];
    _pinnedSpread.forEach(function(p) {
      if (onlyItem && p.item !== onlyItem) { kept.push(p); return; }
      p.mkr._spreadPinned = false;
      p.item._pinnedCount = Math.max(0, (p.item._pinnedCount || 0) - 1);
      _syncLabelGroup(p.item);
    });
    _pinnedSpread = kept;
    spreadMarkers();
  }

  // Pin every spreadable marker the caller matched. `hit(latlng, containerPt)`
  // decides; returning true pins that marker.
  function _pinSpreadWhere(hit) {
    var added = 0;
    legendItems.forEach(function(item) {
      if (!item.visible || !item.spreadMarkers || !item.spreadMarkers.length) return;
      item.spreadMarkers.forEach(function(mkr) {
        if (!mkr._origLatLng || mkr._spreadPinned) return;
        if (!hit(mkr._origLatLng, map.latLngToContainerPoint(mkr._origLatLng))) return;
        mkr._spreadPinned = true;
        item._pinnedCount = (item._pinnedCount || 0) + 1;
        _pinnedSpread.push({ mkr: mkr, item: item });
        added++;
      });
      _syncLabelGroup(item);
    });
    if (added) spreadMarkers();
    return added;
  }

  function pickSpreadAtPoint(pt) {
    // A single point is not a cluster — take everything within the same
    // proximity radius the automatic spread uses, so one click opens the knot.
    var r2 = SPREAD_THRESHOLD * SPREAD_THRESHOLD;
    _pinSpreadWhere(function(_ll, p) {
      var dx = p.x - pt.x, dy = p.y - pt.y;
      return dx * dx + dy * dy <= r2;
    });
  }

  function pickSpreadInBounds(bounds) {
    _pinSpreadWhere(function(ll) { return bounds.contains(ll); });
  }

  // ── Data export ───────────────────────────────────────────────────────────
  // Toolbar button that lets the viewer download the underlying layer data as
  // GeoJSON or CSV (per layer, or all vector layers combined as GeoJSON).
  if (FEAT.dataExport && _vectorItems().length) {
    var DataExportBtn = L.Control.extend({
      onAdd: function() {
        var wrap = L.DomUtil.create('div', 'leaflet-bar leaflet-control data-export-wrap');
        var btn = L.DomUtil.create('button', '', wrap);
        btn.id = 'data-export-btn';
        btn.title = 'Download layer data (GeoJSON / CSV)';
        btn.setAttribute('aria-label', 'Download layer data');
        btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:#fff;border-radius:4px;display:flex;align-items:center;justify-content:center;';
        btn.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" xmlns="http://www.w3.org/2000/svg">'
          + '<path d="M10 2v9m0 0 3.2-3.2M10 11 6.8 7.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
          + '<path d="M3.5 13.5v2A1.5 1.5 0 0 0 5 17h10a1.5 1.5 0 0 0 1.5-1.5v-2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>'
          + '</svg>';

        var panel = L.DomUtil.create('div', 'data-export-panel', wrap);
        panel.style.display = 'none';

        function build() {
          var items = _vectorItems();
          var html = '<div class="de-hdr">Download data</div>';
          html += '<button class="de-all" data-all="1">All layers · GeoJSON</button>';
          items.forEach(function(it) {
            var i = legendItems.indexOf(it);
            var n = (it.ld.geojson && it.ld.geojson.features || []).length;
            html += '<div class="de-row"><span class="de-name" title="' + escHtml(it.ld.name) + '">'
                  + escHtml(it.ld.name) + ' <em>(' + n + ')</em></span>'
                  + '<button class="de-fmt" data-i="' + i + '" data-fmt="geojson">GeoJSON</button>'
                  + '<button class="de-fmt" data-i="' + i + '" data-fmt="csv">CSV</button></div>';
          });
          panel.innerHTML = html;
        }

        L.DomEvent.disableClickPropagation(wrap);
        L.DomEvent.on(btn, 'click', function() {
          var open = panel.style.display !== 'none';
          if (!open) build();
          panel.style.display = open ? 'none' : 'block';
          btn.classList.toggle('active', !open);
        });
        L.DomEvent.on(panel, 'click', function(e) {
          var t = e.target.closest ? e.target.closest('button') : null;
          if (!t) return;
          if (t.getAttribute('data-all')) {
            var fc = { type: 'FeatureCollection', features: [] };
            _vectorItems().forEach(function(it) {
              (it.ld.geojson && it.ld.geojson.features || []).forEach(function(f) {
                var g = JSON.parse(JSON.stringify(f));
                g.properties = g.properties || {};
                g.properties._layer = it.ld.name;
                fc.features.push(g);
              });
            });
            _downloadBlob(new Blob([JSON.stringify(fc, null, 2)], {type: 'application/json'}),
                          'all-layers.geojson');
            return;
          }
          var item = legendItems[parseInt(t.getAttribute('data-i'), 10)];
          if (!item) return;
          if (t.getAttribute('data-fmt') === 'csv') {
            var csv = _layerCSV(item);
            if (csv != null) _downloadBlob(new Blob([csv], {type: 'text/csv'}), _safeName(item.ld.name) + '.csv');
          } else {
            var gj = item.ld.geojson;
            if (gj) _downloadBlob(new Blob([JSON.stringify(gj, null, 2)], {type: 'application/json'}),
                                  _safeName(item.ld.name) + '.geojson');
          }
        });
        return wrap;
      }
    });
    new DataExportBtn({position: 'topleft'}).addTo(map);
  }

  // ── Map Views ────────────────────────────────────────────────────────────────

  // Sync legend group checkboxes and expand/collapse after a theme is applied.
  // Nodes have _grpCb/_grpBody/_grpExp/_item set by buildLegendNodes.
  function _syncLegendGroups(nodes) {
    var hasVisible = false;
    nodes.forEach(function(node) {
      if (node.type === 'group') {
        var childVis = _syncLegendGroups(node.children);
        if (node._grpCb) node._grpCb.checked = childVis;
        if (node._grpBody) {
          node._grpBody.classList.toggle('open', childVis);
          if (node._grpExp) node._grpExp.textContent = childVis ? '▼' : '▶';
        }
        hasVisible = hasVisible || childVis;
      } else if (node.type === 'layer' && node._item) {
        hasVisible = hasVisible || node._item.visible;
      }
    });
    return hasVisible;
  }

  function applyTheme(idx) {
    var theme = THEMES[idx];
    if (!theme || theme.kind === 'text') return;   // a text block is not a view
    if (theme.layerIds) {
      legendItems.forEach(function(it) {
        var vis = theme.layerIds.indexOf(it.ld.name) !== -1;
        setLayerVisible(it, vis);
      });
      if (LAYER_TREE.length) _syncLegendGroups(LAYER_TREE);
    }
    if (theme.extent) {
      try { map.fitBounds(theme.extent, {padding: [20, 20]}); } catch(e) {}
    }
    if (typeof window._setChipViewActive === 'function') window._setChipViewActive(idx);
  }

  if (THEMES.length > 0) {
    var mvSection = document.getElementById('map-views-section');
    var _hasRealView = THEMES.some(function(t) { return t.kind !== 'text'; });
    if (mvSection) {
      if (_hasRealView) {
        var mvHeader = document.createElement('div');
        mvHeader.className = 'mv-section-header';
        mvHeader.textContent = 'Map Views';
        mvSection.appendChild(mvHeader);
      }
      THEMES.forEach(function(th, i) {
        // A text block is a note in the list, not a view: it has a heading you
        // can fold away and no effect on the map.
        if (th.kind === 'text') {
          var block = document.createElement('div');
          block.className = 'mv-text-block';
          var bHdr = document.createElement('div');
          bHdr.className = 'mv-text-hdr';
          bHdr.innerHTML = '<span>' + escHtml(th.name || 'Notes') + '</span>'
                         + '<button type="button" class="mv-text-chev down" aria-label="Collapse"></button>';
          var bBody = document.createElement('div');
          bBody.className = 'mv-text-body';
          bBody.innerHTML = th.notes || '';
          bHdr.addEventListener('click', function() {
            var closed = bBody.classList.toggle('collapsed');
            var chev = bHdr.querySelector('.mv-text-chev');
            chev.classList.toggle('up', closed);
            chev.classList.toggle('down', !closed);
            chev.setAttribute('aria-label', closed ? 'Expand' : 'Collapse');
          });
          block.appendChild(bHdr);
          block.appendChild(bBody);
          mvSection.appendChild(block);
          return;
        }
        var mvItem = document.createElement('div');
        mvItem.className = 'mv-item';
        mvItem.dataset.mvIdx = i;
        mvItem.innerHTML = '<div class="mv-item-name">' + escHtml(th.name || 'Map View ' + (i + 1)) + '</div>'
                         + (th.notes ? '<div class="mv-item-notes">' + th.notes + '</div>' : '');
        mvItem.addEventListener('click', function() {
          mvSection.querySelectorAll('.mv-item').forEach(function(el) { el.classList.remove('active'); });
          mvItem.classList.add('active');
          applyTheme(i);
        });
        mvSection.appendChild(mvItem);
      });
      // Auto-select the first map view. This runs synchronously rather than on
      // a timer: every layer starts visible, so a delayed apply let the full
      // set of layers and labels paint before the view culled them, which read
      // as all the labels switching on and then vanishing.
      var firstMvItem = mvSection.querySelector('.mv-item');
      if (firstMvItem) firstMvItem.click();
    }
  }

  // ── Help button & overlay ────────────────────────────────────────────────────
  var _helpActive = false;
  var helpOverlay = document.getElementById('help-overlay');

  var _helpTools = [
    // ── Left panel / project info
    { sel: '#map-title-chip',                    name: 'Project Info',      text: 'Click to re-open the project info panel. Shows the map title, description, and title block.', side:'right' },
    { sel: '#left-panel-close',                  name: 'Close Info Panel',  text: 'Collapse the left panel. The map title chip will appear at the top-left — click it to reopen.', side:'right' },
    // ── Legend / layers
    { sel: '#legend-header',                     name: 'Layers Panel',      text: 'The layers panel lists all map layers. Click the eye icon to toggle visibility. Drag layers to re-order. The gear icon opens per-layer settings. Switch to Legend for a read-only symbology list with every class shown.', side:'right' },
    { sel: '.legend-cog-btn',                    name: 'Layer Settings',    text: 'Open layer settings: adjust opacity, symbol colours, and attribute filters for this layer.', side:'right' },
    { sel: '#legend-tools-btn',                  name: 'Legend Options',    text: 'Toggle the label column and other legend display options.', side:'right' },
    // ── Map controls
    { sel: '[title="Identify features"]',        name: 'Identify Features', text: 'Click any feature to view its attributes. Use this button to enable crosshair mode for drag-to-identify across multiple features. Also queries WMS layers via GetFeatureInfo.' },
    { sel: '[title="Attribute table"]',          name: 'Attribute Table',   text: 'Open the full attribute table for the selected layer. Supports sorting, searching and CSV export.' },
    { sel: '[title="Drag to select features"]',  name: 'Select &amp; Highlight', text: 'Click and drag a rectangle to select features. Selected rows are highlighted in the attribute table.' },
    { sel: '[title="Toggle attribute filter"]',  name: 'Attribute Filter',  text: 'Show or hide the filter bar to display only features matching a chosen attribute value.' },
    { sel: '[title="Search all layers"]',        name: 'Smart Search',      text: 'Type a term and press Enter to search all layers at once. Non-matching features are greyed out. Click the lightning bolt to activate.' },
    { sel: '#measure-btn',                       name: 'Measure',           text: 'Measure distance along a path: click each point, then double-click to finish. Running totals are labelled on the map. Click the button again to clear.' },
    { sel: '#spread-pick-btn',                   name: 'Spread Points',     text: 'Click a knot of overlapping points, or drag a box over them, to fan just those points out with their labels shown. Click the button again to put them back.' },
    { sel: '#print-btn',                         name: 'Print',             text: 'Print the current map. The printed sheet includes the legend, scale bar, north arrow, title and data credit; the on-screen tool buttons are left off.' },
    { sel: '#data-export-btn',                   name: 'Data Export',       text: 'Download layers as GeoJSON or CSV, either individually or all at once.' },
    { sel: '.leaflet-control-fullscreen-button', name: 'Full Screen',       text: 'Toggle full-screen mode.' },
    { sel: '.leaflet-control-minimap',           name: 'Minimap',           text: 'Overview minimap showing your current extent. Click to toggle.' },
    { sel: '.view-toggle-ctrl',                  name: '2D / 3D',           text: 'Switch between the flat map and the 3D globe view.' },
    { sel: '.leaflet-pm-toolbar',                name: 'Sketch Tools',      text: 'Draw and annotate on the map: lines, shapes, markers and text. Sketches are not saved with the file.' },
    // ── Left panel sections
    { sel: '#map-views-section',                 name: 'Map Views',         text: 'Saved views of the map. Click one to jump to its extent and switch to its layer set. The active view is highlighted.', side:'right' },
    { sel: '.cad-block-hdr',                     name: 'Title Block',       text: 'Drawing title block: client, project number, document number, revision and sign-off. Click the header to collapse or expand it.', side:'right' },
    { sel: '#changelog-hdr',                     name: 'Changelog',         text: 'Revision history for this map. Click the header to collapse or expand the list.', side:'right' },
  ];

  var _helpBtn;

  function buildHelpTips() {
    helpOverlay.innerHTML = '';
    var tipW = 240;
    var GAP  = 6;      // px between neighbouring tips
    var placed = [];

    // Pass 1 — create every tip at its preferred position. Heights are not
    // known until the tips are in the DOM, so nothing is deconflicted yet.
    _helpTools.forEach(function(tool) {
      var el = document.querySelector(tool.sel);
      if (!el) return;
      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      // Skip anything scrolled or collapsed out of view.
      if (r.bottom < 0 || r.top > window.innerHeight) return;
      var tip = document.createElement('div');
      tip.className = 'help-tip';
      tip.innerHTML = '<div class="help-tip-name">' + tool.name + '</div>'
                    + '<div class="help-tip-text">' + escHtml(tool.text) + '</div>';
      var side = tool.side || 'right';
      // Check if placing right would overflow; fall back to left of element
      if (side === 'right' && r.right + 10 + tipW > window.innerWidth) side = 'left';
      var left;
      if (side === 'right') {
        left = r.right + 10;
      } else {
        left = Math.max(4, r.left - tipW - 10);
        tip.style.setProperty('--arrow-side', 'right');
      }
      tip.style.left = left + 'px';
      tip.style.top = Math.max(4, r.top + r.height / 2 - 24) + 'px';
      helpOverlay.appendChild(tip);
      placed.push({ tip: tip, left: left, want: Math.max(4, r.top + r.height / 2 - 24) });
    });

    // Pass 2 — measure, then lay the tips out so none overlap. Tips anchored
    // to the same toolbar sit ~30px apart while each tip is far taller than
    // that, so without this they pile up and become unreadable. Grouping by
    // column is not enough: tips are ~240px wide, so ones with quite different
    // anchors still collide. Test real rectangles instead.
    var vh = window.innerHeight, vw = window.innerWidth;
    placed.forEach(function(p) {
      p.h = p.tip.offsetHeight || 48;
      p.w = p.tip.offsetWidth || tipW;
    });
    placed.sort(function(a, b) { return a.want - b.want; });

    var done = [];

    function firstFreeTop(left, p, from) {
      // Slide down from `from` until the rectangle clears everything placed.
      var top = Math.max(4, from), guard = 0;
      while (guard++ < 80) {
        var hit = null;
        for (var i = 0; i < done.length; i++) {
          var q = done[i];
          if (left < q.left + q.w && q.left < left + p.w &&
              top  < q.top  + q.h && q.top  < top  + p.h) { hit = q; break; }
        }
        if (!hit) return top;
        top = hit.top + hit.h + GAP;
      }
      return top;
    }

    placed.forEach(function(p) {
      // Candidate columns: the anchor's own, then alternating outwards. A tip
      // that cannot fit beside its control moves to the next column over
      // rather than being stacked on top of another tip.
      var cands = [p.left];
      for (var k = 1; k <= 4; k++) {
        var rx = p.left + k * (p.w + 12);
        if (rx + p.w <= vw - 4) cands.push(rx);
        var lx = p.left - k * (p.w + 12);
        if (lx >= 4) cands.push(lx);
      }
      var best = null;
      for (var c = 0; c < cands.length; c++) {
        var top = firstFreeTop(cands[c], p, p.want);
        if (top + p.h <= vh - 4) { best = { left: cands[c], top: top }; break; }
        // Retry this column from the very top before giving up on it.
        top = firstFreeTop(cands[c], p, 4);
        if (top + p.h <= vh - 4) { best = { left: cands[c], top: top }; break; }
      }
      // Nothing fits in the columns derived from the anchor (a narrow window
      // with the report pane open, say) — sweep the whole width on a finer
      // grid before accepting an overlap.
      if (!best) {
        var step = Math.max(40, Math.round(p.w / 3));
        for (var x = 4; x + p.w <= vw - 4; x += step) {
          var t2 = firstFreeTop(x, p, 4);
          if (t2 + p.h <= vh - 4) { best = { left: x, top: t2 }; break; }
        }
      }
      // Last resort: keep it on screen even if it has to overlap.
      if (!best) best = { left: p.left, top: Math.max(4, vh - 4 - p.h) };
      p.left = best.left;
      p.top = best.top;
      p.tip.style.left = Math.round(p.left) + 'px';
      p.tip.style.top  = Math.round(p.top) + 'px';
      done.push(p);
    });
  }

  function toggleHelp() {
    _helpActive = !_helpActive;
    // Show the overlay *before* building: it is display:none until .active,
    // and tips measure zero height while hidden, which breaks the layout.
    if (_helpActive) { helpOverlay.classList.add('active'); buildHelpTips(); }
    else { helpOverlay.classList.remove('active'); }
    if (_helpBtn) _helpBtn.classList.toggle('help-btn-active', _helpActive);
  }

  helpOverlay.addEventListener('click', function() {
    _helpActive = false;
    helpOverlay.classList.remove('active');
    if (_helpBtn) _helpBtn.classList.remove('help-btn-active');
  });

  var HelpControl = L.Control.extend({
    onAdd: function() {
      var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
      btn.title = 'Help — tool guide';
      btn.innerHTML = '<svg viewBox="0 0 20 20" width="16" height="16" xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" stroke-width="1.6"/><text x="10" y="15" font-family="Georgia,serif" font-weight="bold" font-size="13" fill="currentColor" text-anchor="middle">?</text></svg>';
      btn.style.cssText = 'width:30px;height:30px;padding:0;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;';
      _helpBtn = btn;
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', toggleHelp);
      return btn;
    }
  });
  new HelpControl({position: 'topleft'}).addTo(map);

  // ── Brand watermark (bottomleft Leaflet control, above scale bar) ─────────
  var _brandHtml = @@brand_content_json@@;
  // Only add the control when there is something to show — an empty watermark
  // still paints its background, border and padding, which reads as a blank
  // square in the bottom-left corner of the map.
  if (_brandHtml && String(_brandHtml).replace(/\s+/g, '') !== '') {
    var BrandControl = L.Control.extend({
      onAdd: function() {
        var div = L.DomUtil.create('div', 'brand-watermark leaflet-control');
        div.style.pointerEvents = 'none';  // don't absorb map mouse events
        div.innerHTML = _brandHtml;
        // A logo SVG that carries only a viewBox collapses to zero width in a
        // flex row; pin its height and let the width follow the aspect ratio.
        var _bsvg = div.querySelector('svg');
        if (_bsvg) {
          if (!_bsvg.getAttribute('height')) _bsvg.setAttribute('height', '22');
          _bsvg.style.height = '22px';
          _bsvg.style.width = 'auto';
        }
        return div;
      }
    });
    new BrandControl({position: 'bottomleft'}).addTo(map);
  }

  // ── Sketch / annotation (Geoman) ─────────────────────────────────────────
  if (FEAT.sketch && typeof L.PM !== 'undefined') {
    try {
      map.pm.addControls({
        position:         'topleft',
        drawCircle:       false,
        drawCircleMarker: false,
        drawRectangle:    false,
        rotateMode:       false,
        cutPolygon:       false,
      });
      map.on('pm:create', function(e) {
        var l = e.layer;
        if (l.setStyle) l.setStyle({color:'#e74c3c', fillColor:'#e74c3c', fillOpacity:0.2, weight:2});
      });
    } catch(ex) { console.warn('Geoman init failed', ex); }

    var SketchToggle = L.Control.extend({
      options: { position: 'topleft' },
      onAdd: function() {
        var c = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
        var a = L.DomUtil.create('a', '', c);
        a.href = '#'; a.title = 'Sketch / annotate'; a.innerHTML = '&#9998;';
        a.style.fontSize = '16px';
        L.DomEvent.on(a, 'click', function(e) {
          L.DomEvent.preventDefault(e);
          var active = L.DomUtil.hasClass(map.getContainer(), 'sketch-active');
          if (active) {
            L.DomUtil.removeClass(map.getContainer(), 'sketch-active');
            a.style.background = '';
            a.style.color = '';
          } else {
            L.DomUtil.addClass(map.getContainer(), 'sketch-active');
            a.style.background = '#3f32f1';
            a.style.color = '#fff';
          }
        });
        return c;
      }
    });
    new SketchToggle().addTo(map);
  }

  // ── Expose for cross-block hooks (Cesium, extensions) ───────────────────
  window.setLayerVisible  = setLayerVisible;
  window.setLayerOpacity  = setLayerOpacity;
  window._im_applyTheme   = applyTheme;
  window._im_highlightFeature = highlightFeatureOnMap;
  window.applyTheme       = applyTheme;
  window._legendItems     = legendItems;
  window._im_map          = map;
  window._im_feat         = FEAT;
  window._im_layers       = LAYERS;
  window._im_themes       = THEMES;
  window._im_escHtml      = escHtml;

  // ── Opacity persistence via localStorage ────────────────────────────────
  (function() {
    var LS_KEY = 'intermap_opacity';
    try {
      var saved = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
      legendItems.forEach(function(item) {
        var key = item.ld.name;
        if (saved[key] !== undefined) {
          var pane = map.getPane(item.paneName);
          if (pane) pane.style.opacity = saved[key];
        }
      });
    } catch(e) {}

    // Patch setLayerOpacity to also persist
    var _baseSetLayerOpacity = window.setLayerOpacity;
    window.setLayerOpacity = function(item, factor) {
      _baseSetLayerOpacity(item, factor);
      try {
        var saved = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
        saved[item.ld.name] = factor;
        localStorage.setItem(LS_KEY, JSON.stringify(saved));
      } catch(e) {}
    };
  })();

  // ── Permalink ─────────────────────────────────────────────────────────────
  (function() {
    // Restore state from hash on load
    function _parseHash() {
      try {
        var h = location.hash.replace('#', '');
        if (!h) return;
        var parts = h.split(';');
        var geo = parts[0] ? parts[0].split(',') : [];
        if (geo.length === 3) {
          map.setView([parseFloat(geo[0]), parseFloat(geo[1])], parseInt(geo[2], 10));
        }
        if (parts[1]) {
          var vis = parts[1].split(',');
          legendItems.forEach(function(item, i) {
            if (vis[i] !== undefined) setLayerVisible(item, vis[i] === '1');
          });
        }
        if (parts[2] !== undefined) {
          var ti = parseInt(parts[2], 10);
          if (!isNaN(ti) && THEMES[ti]) applyTheme(ti);
        }
      } catch(e) {}
    }
    _parseHash();

    // The permalink button was removed; #-hash views are still readable via
    // _parseHash above, so hand-shared links keep working.
  })();

  // ── Print tool ───────────────────────────────────────────────────────────
  // Lives in the map toolbar alongside the other tools rather than floating
  // over the corner of the map.
  if (FEAT.print) (function() {
    var PrintBtn = L.Control.extend({
      onAdd: function() {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-filter');
        btn.id = 'print-btn';
        btn.title = 'Print map (with legend, scale bar and north arrow)';
        btn.setAttribute('aria-label', 'Print map');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
          + '<rect x="5.5" y="2.5" width="9" height="4" fill="none" stroke="#444" stroke-width="1.6"/>'
          + '<rect x="2.5" y="6.5" width="15" height="7" rx="1.2" fill="none" stroke="#444" stroke-width="1.6"/>'
          + '<rect x="5.5" y="11.5" width="9" height="6" fill="#fff" stroke="#444" stroke-width="1.6"/>'
          + '<circle cx="14.8" cy="9" r="1" fill="#444"/></svg>';
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, 'click', function() {
          _fillPrintDecor();
          window.print();
        });
        return btn;
      }
    });
    new PrintBtn({position: 'topleft'}).addTo(map);
    // Decorations belong to the print tool: only mark them printable when the
    // tool is enabled, so an export without it never emits empty framed boxes.
    document.body.classList.add('print-tool-on');
    // Also populate for a browser-initiated print (Ctrl+P), not just the button.
    window.addEventListener('beforeprint', function() { _fillPrintDecor(); });

    // Populate the print-only decorations (title, date, scale note, credit)
    // just before printing, so they reflect the view actually being printed.
    function _fillPrintDecor() {
      var t = document.getElementById('print-decor-title');
      if (t) {
        var src = document.getElementById('map-title-chip-text');
        var title = (src && src.textContent.trim())
          || (document.title || '').trim();
        t.textContent = title;
        t.style.display = title ? '' : 'none';
      }
      var m = document.getElementById('print-decor-meta');
      if (m) {
        var c = map.getCenter();
        m.textContent = 'Printed ' + new Date().toLocaleDateString()
          + '  ·  Scale 1:' + Math.round(_printScaleDenominator())
          + '  ·  Centre ' + c.lat.toFixed(4) + ', ' + c.lng.toFixed(4)
          + '  ·  WGS 84';
      }
      var cr = document.getElementById('print-decor-credit');
      if (cr) {
        // Reuse whatever attribution Leaflet is already showing.
        var att = document.querySelector('.leaflet-control-attribution');
        cr.textContent = att ? att.textContent.replace(/^\s*\|?\s*/, '') : '';
        cr.style.display = cr.textContent ? '' : 'none';
      }
    }

    // Approximate representative fraction for the current view, from the
    // metres-per-pixel at the map centre and a nominal 96dpi screen.
    function _printScaleDenominator() {
      try {
        var c = map.getCenter();
        var mPerPx = 40075016.686 * Math.abs(Math.cos(c.lat * Math.PI / 180))
                   / Math.pow(2, map.getZoom() + 8);
        return mPerPx * 96 / 0.0254;
      } catch (e) { return 0; }
    }
  })();

})();

