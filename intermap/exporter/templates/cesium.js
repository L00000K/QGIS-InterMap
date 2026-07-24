// ── Cesium 3D viewer ───────────────────────────────────────────────────────
(function() {
  var FEAT    = window._im_feat;
  var map     = window._im_map;
  var LAYERS  = window._im_layers  || [];
  var THEMES  = window._im_themes  || [];
  var escHtml = window._im_escHtml || function(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };
  if (!FEAT || !FEAT.cesium3d) return;

  var cesiumDiv = document.getElementById('cesium-container');
  var mapDiv    = document.getElementById('map');
  var loadingEl = document.getElementById('cesium-loading');

  // Add as a Leaflet control so it sits at the top of the topleft toolbar
  var ViewToggleControl = L.Control.extend({
    options: { position: 'topleft' },
    onAdd: function() {
      var c = L.DomUtil.create('div', 'leaflet-bar leaflet-control view-toggle-ctrl');
      var a = L.DomUtil.create('a', '', c);
      a.href = '#'; a.title = 'Toggle 2D / 3D view'; a.innerHTML = '3D';
      L.DomEvent.on(a, 'click', function(e) {
        L.DomEvent.preventDefault(e);
        _onToggle();
      });
      this._link = a;
      this._container = c;
      return c;
    }
  });
  var _ctrl = new ViewToggleControl();
  _ctrl.addTo(map);
  // Prepend to the topleft container so it appears above all other controls
  var _ctrlEl = _ctrl.getContainer();
  _ctrlEl.parentElement.insertBefore(_ctrlEl, _ctrlEl.parentElement.firstChild);
  var toggleBtn = _ctrl._link;
  var toggleContainer = _ctrl._container;

  // Embedded export-time config
  var _ionToken     = "@@_cesium_ion_token@@";
  var _googleKey    = "@@_google_maps_key@@";
  var _extrudeField = "@@_extrude_field@@";
  var _extrudeScale = @@_extrude_scale@@;
  var _elevDem      = @@_elevation_json@@;  // embedded WGS-84 heightmap, or null

  var _is3d      = false;
  var _viewer    = null;
  var _cesiumOk  = false;
  var _loading   = false;
  var _cesiumLayers = {};   // layer index → DataSource or ImageryLayer

  // ── Viewport sync ─────────────────────────────────────────────────────────
  function _leafletToCesium() {
    if (!_viewer) return;
    var b = map.getBounds();
    _viewer.camera.flyTo({
      destination: Cesium.Rectangle.fromDegrees(
        b.getWest(), b.getSouth(), b.getEast(), b.getNorth()
      ),
      duration: 0.6
    });
  }

  function _cesiumToLeaflet() {
    if (!_viewer) return;
    var rect = _viewer.camera.computeViewRectangle(_viewer.scene.globe.ellipsoid);
    if (rect) {
      map.fitBounds([
        [Cesium.Math.toDegrees(rect.south), Cesium.Math.toDegrees(rect.west)],
        [Cesium.Math.toDegrees(rect.north), Cesium.Math.toDegrees(rect.east)]
      ], {animate: false});
    }
  }

  // ── Style helpers ─────────────────────────────────────────────────────────
  function _resolveStyle(styleMap, props) {
    if (!styleMap) return {};
    var sm = styleMap, entries = sm.entries || [], def = sm['default'] || {};
    if (sm.type === 'single') return sm.style || {};
    if (sm.type === 'categorized') {
      var val = String(props[sm.field] !== undefined ? props[sm.field] : '');
      for (var i = 0; i < entries.length; i++) {
        if (String(entries[i].value) === val) return entries[i].style || def;
      }
      return def;
    }
    if (sm.type === 'graduated') {
      var num = parseFloat(props[sm.field]);
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (!isNaN(num) && num >= e.min && num <= e.max) return e.style || def;
      }
      return def;
    }
    if (sm.type === 'rule') {
      // Cannot evaluate QGIS expressions in browser — use first entry as best effort
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].style) return entries[i].style;
      }
      return def;
    }
    return def;
  }

  function _cssColor(hex, opacity) {
    if (!hex || hex === 'none') return Cesium.Color.TRANSPARENT;
    try { return Cesium.Color.fromCssColorString(hex).withAlpha(opacity !== undefined ? opacity : 1.0); }
    catch(x) { return Cesium.Color.GRAY; }
  }

  function _getProps(entity) {
    var out = {};
    if (!entity.properties) return out;
    try {
      entity.properties.propertyNames.forEach(function(n) {
        out[n] = entity.properties[n].getValue(Cesium.JulianDate.now());
      });
    } catch(x) {}
    return out;
  }

  // ── Z-coordinate detection ────────────────────────────────────────────────
  // A layer counts as 3D when any feature's first position carries a third
  // (Z) value. Exported GeoJSON has uniform dimensionality per geometry, so
  // checking the first position of each geometry is sufficient.
  function _geomHasZ(geom) {
    if (!geom) return false;
    if (geom.type === 'GeometryCollection') {
      var gs = geom.geometries || [];
      for (var i = 0; i < gs.length; i++) if (_geomHasZ(gs[i])) return true;
      return false;
    }
    var c = geom.coordinates;
    while (Array.isArray(c) && Array.isArray(c[0])) c = c[0];
    return Array.isArray(c) && c.length > 2;
  }

  function _geojsonHasZ(geojson) {
    if (!geojson || !geojson.features) return false;
    for (var i = 0; i < geojson.features.length; i++) {
      if (_geomHasZ(geojson.features[i].geometry)) return true;
    }
    return false;
  }

  // ── SVG markers → billboard data URI ─────────────────────────────────────
  function _svgDataUri(ms) {
    if (!ms || !ms.inner) return null;
    var vw = ms.vw || ms.w || 32, vh = ms.vh || ms.h || 32;
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + vw + ' ' + vh + '">' + ms.inner + '</svg>';
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  // ── Apply style to a Cesium entity ────────────────────────────────────────
  // hasZ: the layer carries real Z coordinates — leave loaded heights alone
  // instead of re-clamping everything to the ground.
  function _applyEntityStyle(entity, style, extrudeHeight, hasZ) {
    if (!style) return;
    var fill   = _cssColor(style.fillColor || style.color || '#3388ff',
                           style.fillOpacity !== undefined ? style.fillOpacity : 0.4);
    var stroke = _cssColor(style.color || '#3388ff',
                           style.opacity !== undefined ? style.opacity : 1.0);
    var weight = style.weight || 2;
    var clampRef = hasZ ? Cesium.HeightReference.NONE
                        : Cesium.HeightReference.CLAMP_TO_GROUND;

    if (entity.polygon) {
      entity.polygon.material     = new Cesium.ColorMaterialProperty(fill);
      entity.polygon.outlineColor = new Cesium.ConstantProperty(stroke);
      entity.polygon.outlineWidth = new Cesium.ConstantProperty(weight);
      entity.polygon.outline      = new Cesium.ConstantProperty(true);
      if (extrudeHeight > 0) {
        entity.polygon.extrudedHeight = new Cesium.ConstantProperty(extrudeHeight);
        entity.polygon.closeTop       = new Cesium.ConstantProperty(true);
        entity.polygon.closeBottom    = new Cesium.ConstantProperty(true);
      } else if (!hasZ) {
        entity.polygon.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
      }
    }
    if (entity.polyline) {
      entity.polyline.material      = new Cesium.ColorMaterialProperty(stroke);
      entity.polyline.width         = new Cesium.ConstantProperty(weight);
      entity.polyline.clampToGround = new Cesium.ConstantProperty(!extrudeHeight && !hasZ);
    }

    // Points and billboards
    var ms = style.markerSvg;
    if (entity.billboard || entity.point) {
      if (ms && ms.inner) {
        var uri = _svgDataUri(ms);
        if (uri) {
          entity.billboard = new Cesium.BillboardGraphics({
            image:          new Cesium.ConstantProperty(uri),
            width:          new Cesium.ConstantProperty(ms.w || 24),
            height:         new Cesium.ConstantProperty(ms.h || 24),
            pixelOffset:    new Cesium.ConstantProperty(new Cesium.Cartesian2(
              (ms.w || 24) / 2 - (ms.ax || 0),
              (ms.h || 24) / 2 - (ms.ay || 0)
            )),
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            heightReference: clampRef,
            // Ground-clamped markers otherwise disappear behind the globe's
            // curvature / terrain; keep them drawn on top like a 2D overlay.
            disableDepthTestDistance: new Cesium.ConstantProperty(Number.POSITIVE_INFINITY)
          });
          entity.point = undefined;
          return;
        }
      }
      var mCol = _cssColor(style.markerColor || style.color || '#3388ff',
                           style.markerOpacity !== undefined ? style.markerOpacity : 1.0);
      entity.billboard = undefined;
      entity.point = new Cesium.PointGraphics({
        color:           new Cesium.ConstantProperty(mCol),
        pixelSize:       new Cesium.ConstantProperty(style.markerSize || 8),
        outlineColor:    new Cesium.ConstantProperty(_cssColor(
          style.markerStrokeColor || '#ffffff',
          style.markerStrokeOpacity !== undefined ? style.markerStrokeOpacity : 1.0
        )),
        outlineWidth:    new Cesium.ConstantProperty(style.markerStrokeWidth || 1),
        heightReference: clampRef,
        disableDepthTestDistance: new Cesium.ConstantProperty(Number.POSITIVE_INFINITY)
      });
    }
  }

  // ── Apply labels from labelConfig ─────────────────────────────────────────
  function _applyLabels(entities, labelCfg, hasZ) {
    if (!labelCfg || !labelCfg.enabled || !labelCfg.field) return;
    var col = _cssColor(labelCfg.color || '#222222');
    entities.forEach(function(entity) {
      var props = _getProps(entity);
      var text  = props[labelCfg.field] !== undefined ? String(props[labelCfg.field]) : '';
      if (!text) return;
      entity.label = new Cesium.LabelGraphics({
        text:             new Cesium.ConstantProperty(text),
        font:             new Cesium.ConstantProperty((labelCfg.fontSize || 11) + 'px sans-serif'),
        fillColor:        new Cesium.ConstantProperty(col),
        outlineColor:     new Cesium.ConstantProperty(Cesium.Color.WHITE),
        outlineWidth:     new Cesium.ConstantProperty(2),
        style:            new Cesium.ConstantProperty(Cesium.LabelStyle.FILL_AND_OUTLINE),
        verticalOrigin:   new Cesium.ConstantProperty(Cesium.VerticalOrigin.BOTTOM),
        pixelOffset:      new Cesium.ConstantProperty(new Cesium.Cartesian2(0, -8)),
        heightReference:  hasZ ? Cesium.HeightReference.NONE
                               : Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      });
    });
  }

  // ── Batch style entities in rAF chunks to avoid freezing ─────────────────
  function _batchStyle(entities, styleMap, extrudeField, extrudeScale, labelCfg, hasZ, done) {
    var CHUNK = 200, i = 0;
    function step() {
      var end = Math.min(i + CHUNK, entities.length);
      for (; i < end; i++) {
        var entity = entities[i];
        var props  = _getProps(entity);
        var style  = _resolveStyle(styleMap, props);
        var extH   = 0;
        if (extrudeField) {
          extH = parseFloat(props[extrudeField]) * (extrudeScale || 1);
          if (isNaN(extH)) extH = 0;
        }
        _applyEntityStyle(entity, style, extH, hasZ);
      }
      if (i < entities.length) requestAnimationFrame(step);
      else {
        _applyLabels(entities, labelCfg, hasZ);
        if (done) done();
      }
    }
    requestAnimationFrame(step);
  }

  // ── Load all layers ───────────────────────────────────────────────────────
  function _loadLayers() {
    var items = window._legendItems || [];

    // Add WMS/raster in reversed order so topmost legend layer renders on top in Cesium
    var imgLayers = [];
    LAYERS.forEach(function(ldef, idx) {
      if (ldef.kind === 'raster' || ldef.kind === 'wms') imgLayers.push({ldef: ldef, idx: idx});
    });
    imgLayers.reverse().forEach(function(entry) {
      var ldef = entry.ldef, idx = entry.idx;
      var visible = items[idx] ? items[idx].visible : true;
      if (ldef.kind === 'raster') {
        var rect = Cesium.Rectangle.fromDegrees(
          ldef.bounds[0][1], ldef.bounds[0][0],
          ldef.bounds[1][1], ldef.bounds[1][0]
        );
        var url  = 'data:image/png;base64,' + ldef.data;
        var prom = Cesium.SingleTileImageryProvider.fromUrl
          ? Cesium.SingleTileImageryProvider.fromUrl(url, {rectangle: rect})
          : Promise.resolve(new Cesium.SingleTileImageryProvider({url: url, rectangle: rect}));
        prom.then(function(provider) {
          var il = _viewer.imageryLayers.addImageryProvider(provider);
          il.alpha = ldef.opacity != null ? ldef.opacity : 1.0;
          il.show  = visible;
          _cesiumLayers[idx] = il;
        }).catch(function(e) { console.warn('Cesium raster:', ldef.name, e); });
      } else if (ldef.kind === 'wms') {
        try {
          var il = _viewer.imageryLayers.addImageryProvider(
            new Cesium.WebMapServiceImageryProvider({
              url: ldef.wmsUrl, layers: ldef.wmsLayers,
              parameters: {
                transparent: true,
                format:  ldef.wmsFormat  || 'image/png',
                styles:  ldef.wmsStyles  || '',
                version: ldef.wmsVersion || '1.1.1'
              }
            })
          );
          il.alpha = ldef.opacity != null ? ldef.opacity : 1.0;
          il.show  = visible;
          _cesiumLayers[idx] = il;
        } catch(e) { console.warn('Cesium WMS:', ldef.name, e); }
      }
    });

    // Vector layers
    LAYERS.forEach(function(ldef, idx) {
      if (ldef.kind !== 'vector') return;
      var visible = items[idx] ? items[idx].visible : true;
      var hasZ    = _geojsonHasZ(ldef.geojson);
      Cesium.GeoJsonDataSource.load(ldef.geojson, {
        clampToGround: !_extrudeField && !hasZ,
        stroke: Cesium.Color.fromCssColorString('#3388ff'),
        fill:   Cesium.Color.fromCssColorString('#3388ff').withAlpha(0.4),
        strokeWidth: 2, markerSize: 16
      }).then(function(ds) {
        ds.show = visible;
        _batchStyle(ds.entities.values, ldef.styleMap, _extrudeField, _extrudeScale, ldef.labelConfig, hasZ, null);
        _viewer.dataSources.add(ds);
        _cesiumLayers[idx] = ds;
      }).catch(function(err) {
        console.warn('Cesium vector:', ldef.name, err);
      });
    });
  }

  // ── 3D feature identify ───────────────────────────────────────────────────
  function _initIdentify() {
    var handler = new Cesium.ScreenSpaceEventHandler(_viewer.scene.canvas);
    handler.setInputAction(function(click) {
      var picked = _viewer.scene.pick(click.position);
      if (!Cesium.defined(picked) || !Cesium.defined(picked.id)) return;
      var props = _getProps(picked.id);
      var rows  = Object.keys(props).map(function(k) {
        return '<tr><th style="text-align:left;padding:2px 8px 2px 0;opacity:0.6;white-space:nowrap">'
          + escHtml(k) + '</th><td>' + escHtml(String(props[k] != null ? props[k] : '')) + '</td></tr>';
      }).join('');
      var panel = document.getElementById('info-panel');
      var body  = document.getElementById('info-panel-body');
      if (panel && body) {
        body.innerHTML = rows
          ? '<table style="font-size:12px;border-collapse:collapse;width:100%">' + rows + '</table>'
          : '<em>No attributes</em>';
        panel.classList.add('open');
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    // Middle-drag: orbit the camera around the point at the screen centre.
    // Take middle-drag away from the default tilt gesture first, otherwise
    // both run at once and the camera flies off.
    _viewer.scene.screenSpaceCameraController.tiltEventTypes = [
      Cesium.CameraEventType.PINCH,
      { eventType: Cesium.CameraEventType.LEFT_DRAG,  modifier: Cesium.KeyboardEventModifier.CTRL },
      { eventType: Cesium.CameraEventType.RIGHT_DRAG, modifier: Cesium.KeyboardEventModifier.CTRL }
    ];

    function _pickViewCentre() {
      var canvas = _viewer.scene.canvas;
      var centre = new Cesium.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2);
      var ray = _viewer.camera.getPickRay(centre);
      var p = ray ? _viewer.scene.globe.pick(ray, _viewer.scene) : null;
      if (!p) p = _viewer.camera.pickEllipsoid(centre, _viewer.scene.globe.ellipsoid);
      return p || null;
    }

    var _mc_last = null, _orbitTarget = null;
    handler.setInputAction(function(down) {
      _orbitTarget = _pickViewCentre();
      _mc_last = { x: down.position.x, y: down.position.y };
    }, Cesium.ScreenSpaceEventType.MIDDLE_DOWN);

    handler.setInputAction(function(move) {
      if (!_mc_last || !_orbitTarget) return;
      var dx = move.endPosition.x - _mc_last.x;
      var dy = move.endPosition.y - _mc_last.y;
      _mc_last = { x: move.endPosition.x, y: move.endPosition.y };
      // Orbit the picked centre: rotateLeft/rotateUp move around the origin
      // of the current reference frame, so pin that frame to the target.
      var camera = _viewer.camera;
      camera.lookAtTransform(Cesium.Transforms.eastNorthUpToFixedFrame(_orbitTarget));
      camera.rotateLeft(dx * 0.005);
      camera.rotateUp(-dy * 0.005);
      camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(function() {
      _mc_last = null; _orbitTarget = null;
    }, Cesium.ScreenSpaceEventType.MIDDLE_UP);
  }

  // ── Vertical plane slicer (Leapfrog-style cross-section) ─────────────────
  function _initSlicer() {
    var slicerCanvas = document.getElementById('cesium-slicer-canvas');
    var slicerToggle = document.getElementById('cesium-slicer-toggle');
    if (!slicerToggle || !slicerCanvas) return;

    var _slicerEnabled  = false;
    var _slicerX        = null;   // screen X of the slicer line
    var _slicerDragging = false;
    var GRAB_PX = 20;             // how close to the line a drag must start

    // One persistent clipping plane on the globe, updated in place while
    // dragging. Globe clipping cuts terrain, imagery and ground-clamped
    // features; free-floating extruded entities are unaffected (Cesium
    // clipping planes only apply to the globe, 3D Tiles and models).
    var _clipPlane = new Cesium.ClippingPlane(new Cesium.Cartesian3(1, 0, 0), 0);
    var _clipColl  = new Cesium.ClippingPlaneCollection({
      planes: [_clipPlane],
      enabled: false,
      edgeWidth: 1.0,
      edgeColor: Cesium.Color.RED
    });
    _viewer.scene.globe.clippingPlanes = _clipColl;

    function _drawIndicator() {
      slicerCanvas.width  = cesiumDiv.clientWidth;
      slicerCanvas.height = cesiumDiv.clientHeight;
      var ctx = slicerCanvas.getContext('2d');
      ctx.clearRect(0, 0, slicerCanvas.width, slicerCanvas.height);
      ctx.strokeStyle = 'rgba(255,100,100,0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 5]);
      ctx.beginPath();
      ctx.moveTo(_slicerX, 0);
      ctx.lineTo(_slicerX, slicerCanvas.height);
      ctx.stroke();
      // grab handle
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(255,100,100,0.9)';
      ctx.beginPath();
      ctx.arc(_slicerX, slicerCanvas.height / 2, 7, 0, Math.PI * 2);
      ctx.fill();
    }

    function _updateSlicerPlane() {
      if (!_slicerEnabled || _slicerX === null) return;
      var canvas = _viewer.scene.canvas;
      var pos = new Cesium.Cartesian2(_slicerX, canvas.clientHeight / 2);
      var ray = _viewer.camera.getPickRay(pos);
      var anchor = ray ? _viewer.scene.globe.pick(ray, _viewer.scene) : null;
      if (!anchor) anchor = _viewer.camera.pickEllipsoid(pos, _viewer.scene.globe.ellipsoid);
      if (!anchor) { _drawIndicator(); return; }  // looking at sky — keep last plane
      // Vertical plane through the picked point. Start from the camera's
      // right vector (so the cut follows the on-screen line) but project out
      // its vertical component — a tilted camera must still cut plumb.
      var up = _viewer.scene.globe.ellipsoid.geodeticSurfaceNormal(anchor, new Cesium.Cartesian3());
      var normal = Cesium.Cartesian3.clone(_viewer.camera.right, new Cesium.Cartesian3());
      var vert = Cesium.Cartesian3.multiplyByScalar(
        up, Cesium.Cartesian3.dot(normal, up), new Cesium.Cartesian3());
      Cesium.Cartesian3.subtract(normal, vert, normal);
      if (Cesium.Cartesian3.magnitude(normal) < 1e-6) {
        Cesium.Cartesian3.clone(_viewer.camera.right, normal);  // degenerate: camera right is vertical
      }
      Cesium.Cartesian3.normalize(normal, normal);
      var plane = Cesium.Plane.fromPointNormal(anchor, normal);
      _clipPlane.normal   = plane.normal;
      _clipPlane.distance = plane.distance;
      _clipColl.enabled   = true;
      _drawIndicator();
    }

    slicerToggle.addEventListener('change', function() {
      _slicerEnabled = this.checked;
      slicerCanvas.style.display = _slicerEnabled ? 'block' : 'none';
      if (_slicerEnabled) {
        _slicerX = cesiumDiv.clientWidth / 2;   // start at centre
        _updateSlicerPlane();
      } else {
        _clipColl.enabled = false;
        var ctx = slicerCanvas.getContext('2d');
        ctx.clearRect(0, 0, slicerCanvas.width, slicerCanvas.height);
      }
    });

    // The indicator canvas is pointer-events:none so it never blocks the
    // camera; instead grab drags that start near the line on the container,
    // in the capture phase, before Cesium's own handlers see them. Cesium
    // registers pointer events (not mouse events) where available, so the
    // interceptor must use the same event family or the drag falls through
    // to the default camera pan.
    var EV = window.PointerEvent
      ? { down: 'pointerdown', move: 'pointermove', up: 'pointerup' }
      : { down: 'mousedown',   move: 'mousemove',   up: 'mouseup' };

    cesiumDiv.addEventListener(EV.down, function(e) {
      if (!_slicerEnabled || e.button !== 0) return;
      var rect = cesiumDiv.getBoundingClientRect();
      if (Math.abs((e.clientX - rect.left) - _slicerX) <= GRAB_PX) {
        _slicerDragging = true;
        e.stopPropagation();
        e.preventDefault();
      }
    }, true);

    document.addEventListener(EV.move, function(e) {
      if (!_slicerDragging) return;
      var rect = cesiumDiv.getBoundingClientRect();
      _slicerX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      _updateSlicerPlane();
      e.stopPropagation();
    }, true);

    document.addEventListener(EV.up, function() {
      _slicerDragging = false;
    }, true);
  }

  // ── Embedded-DEM terrain provider ─────────────────────────────────────────
  // The exporter can embed a quantized WGS-84 height grid sampled from a
  // QGIS raster. Serve it as terrain via CustomHeightmapTerrainProvider:
  // Cesium asks for a small heightmap per tile and we answer by bilinear-
  // sampling the grid. Outside the raster's extent the terrain is 0 m.
  function _demTerrainProvider() {
    var bytes = Uint8Array.from(atob(_elevDem.b64), function(ch) { return ch.charCodeAt(0); });
    var grid  = new Uint16Array(bytes.buffer);           // little-endian, row 0 = north
    var W = _elevDem.w, H = _elevDem.h;
    var west = _elevDem.west, south = _elevDem.south;
    var east = _elevDem.east, north = _elevDem.north;
    var hMin = _elevDem.min;
    var hScale = (_elevDem.max - _elevDem.min) / 65535 || 0;
    if (grid.length !== W * H) throw new Error('DEM grid size mismatch');

    function sampleHeight(lonDeg, latDeg) {
      var fx = (lonDeg - west) / (east - west) * (W - 1);
      var fy = (north - latDeg) / (north - south) * (H - 1);
      if (fx < 0 || fy < 0 || fx > W - 1 || fy > H - 1) return 0;
      var x0 = Math.floor(fx), y0 = Math.floor(fy);
      var x1 = Math.min(x0 + 1, W - 1), y1 = Math.min(y0 + 1, H - 1);
      var tx = fx - x0, ty = fy - y0;
      var v = grid[y0 * W + x0] * (1 - tx) * (1 - ty)
            + grid[y0 * W + x1] * tx       * (1 - ty)
            + grid[y1 * W + x0] * (1 - tx) * ty
            + grid[y1 * W + x1] * tx       * ty;
      return hMin + v * hScale;
    }

    var TILE = 32;
    var tilingScheme = new Cesium.GeographicTilingScheme();
    return new Cesium.CustomHeightmapTerrainProvider({
      width: TILE, height: TILE, tilingScheme: tilingScheme,
      callback: function(x, y, level) {
        var r = tilingScheme.tileXYToRectangle(x, y, level);
        var out = new Float32Array(TILE * TILE);
        for (var j = 0; j < TILE; j++) {
          var lat = Cesium.Math.toDegrees(r.north - (r.north - r.south) * (j / (TILE - 1)));
          for (var i = 0; i < TILE; i++) {
            var lon = Cesium.Math.toDegrees(r.west + (r.east - r.west) * (i / (TILE - 1)));
            out[j * TILE + i] = sampleHeight(lon, lat);
          }
        }
        return out;
      }
    });
  }

  // ── Viewer init ───────────────────────────────────────────────────────────
  function _initViewer() {
    Cesium.Ion.defaultAccessToken = _ionToken || 'none';

    // Build base imagery layer up-front and pass via constructor option.
    // This is the only reliable way to get a visible globe in Cesium 1.117:
    // removeAll() + addImageryProvider() leaves the globe surface invisible
    // because the globe renderer skips drawing when the layer list is empty.
    var _baseLayer    = false;
    var _baseProvider = null;
    if (@@include_basemap_json@@ && !_googleKey) {
      try {
        _baseProvider = new Cesium.UrlTemplateImageryProvider({
          url:          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          credit:       '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maximumLevel: 19
        });
        _baseLayer = new Cesium.ImageryLayer(_baseProvider);
      } catch(e) { console.warn('OSM provider init:', e); }
    }

    var viewerOpts = {
      baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false,
      animation: false, timeline: false, fullscreenButton: false,
      infoBox: false, selectionIndicator: false,
      baseLayer: _baseLayer,
    };
    // Terrain precedence: an explicitly chosen elevation raster wins over
    // Cesium Ion world terrain; with neither, the globe is the ellipsoid.
    if (_elevDem) {
      try {
        viewerOpts.terrainProvider = _demTerrainProvider();
      } catch(e) { console.warn('Elevation DEM terrain unavailable:', e); }
    }
    if (!viewerOpts.terrainProvider && _ionToken && Cesium.Terrain) {
      viewerOpts.terrain = Cesium.Terrain.fromWorldTerrain();
    }

    _viewer = new Cesium.Viewer('cesium-container', viewerOpts);

    // Blue fallback colour — shown while tiles load, or when basemap is off
    _viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#1a69b0');
    _viewer.scene.globe.enableLighting = false;
    // Keep ground-clamped features drawn over the terrain surface instead of
    // being culled into it (default, set explicitly so flat/draped data with
    // no Z is reliably visible with or without a terrain provider).
    _viewer.scene.globe.depthTestAgainstTerrain = false;
    _viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#1a1a2e');
    _viewer.scene.skyBox.show    = false;
    _viewer.scene.sun.show       = false;
    _viewer.scene.moon.show      = false;

    // Tile servers (esp. the public OSM one) frequently block or rate-limit
    // requests from exported standalone HTML (no matching Referer, bulk
    // access, offline viewing, corporate proxies, ad-blockers, ...). When
    // every tile request for the sole base layer fails, Cesium's globe
    // renderer never marks any tile "renderable" and the globe surface stops
    // drawing entirely — leaving only the starfield skybox visible. Detect
    // sustained failure and drop the layer so the solid baseColor sphere
    // (set above) becomes visible again instead of an invisible globe.
    if (_baseProvider) {
      var _baseLayerFailures = 0;
      _baseProvider.errorEvent.addEventListener(function() {
        _baseLayerFailures++;
        if (_baseLayerFailures === 6 && _viewer.imageryLayers.contains(_baseLayer)) {
          console.warn('Base imagery unreachable after repeated failures — falling back to solid globe colour.');
          _viewer.imageryLayers.remove(_baseLayer, false);
        }
      });
    }

    if (_googleKey) {
      // Google Photorealistic 3D Tiles include their own imagery
      Cesium.Cesium3DTileset.fromUrl(
        'https://tile.googleapis.com/v1/3dtiles/root.json?key=' + _googleKey
      ).then(function(ts) {
        _viewer.scene.primitives.add(ts);
      }).catch(function(e) {
        console.warn('Google 3D Tiles unavailable:', e);
      });
    }

    if (_ionToken) {
      // OSM Buildings (global 3D footprints) from Cesium Ion
      Cesium.Cesium3DTileset.fromIonAssetId(96188).then(function(ts) {
        _viewer.scene.primitives.add(ts);
      }).catch(function(e) {
        console.warn('Cesium Ion Buildings unavailable:', e);
      });
    }

    _loadLayers();
    _leafletToCesium();
    _initIdentify();
    _initSlicer();
    _cesiumOk = true;
    window._im_cesiumViewer = _viewer;  // cross-block / extension hook
  }

  // ── Lazy-load CesiumJS from CDN ───────────────────────────────────────────
  function _loadCesium(cb) {
    if (window.Cesium) { cb(); return; }
    var BASE = 'https://cesium.com/downloads/cesiumjs/releases/1.117/Build/Cesium/';
    window.CESIUM_BASE_URL = BASE;
    var link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = BASE + 'Widgets/widgets.css';
    document.head.appendChild(link);
    var script = document.createElement('script');
    script.src = BASE + 'Cesium.js';
    script.onload = cb;
    script.onerror = function() {
      loadingEl.style.display = 'none';
      toggleContainer.style.opacity = '0.4';
      toggleContainer.style.cursor  = 'not-allowed';
      toggleBtn.title = '3D unavailable — Cesium could not be loaded (no internet?)';
      toggleBtn.style.pointerEvents = 'none';
    };
    document.head.appendChild(script);
  }

  // ── Toggle ────────────────────────────────────────────────────────────────
  function _setDisplay(id, value) {
    var el = document.getElementById(id);
    if (el) el.style.display = value;
  }

  function _show2d() {
    cesiumDiv.style.display = 'none';
    mapDiv.style.display    = 'block';
    _setDisplay('cesium-slicer-ui', 'none');
    _setDisplay('label-overlay', 'block');
    _setDisplay('filterbar', '');
  }

  function _onToggle() {
    if (_loading) return;
    if (!_is3d) {
      _loading = true;
      loadingEl.style.display = 'block';
      _loadCesium(function() {
        try {
          // Show container BEFORE init — Cesium needs a visible, sized div
          cesiumDiv.style.display = 'block';
          mapDiv.style.display    = 'none';
          _setDisplay('cesium-slicer-ui', 'block');
          _setDisplay('label-overlay', 'none');
          _setDisplay('filterbar', 'none');

          if (!_cesiumOk) _initViewer(); else _leafletToCesium();

          toggleBtn.innerHTML = '2D';
          L.DomUtil.addClass(toggleContainer, 'is-3d');
          _is3d = true;
        } catch(e) {
          console.error('Cesium init failed:', e);
          // Restore 2D view so page isn't left blank
          _show2d();
          L.DomUtil.removeClass(toggleContainer, 'is-3d');
          toggleContainer.style.opacity = '0.4';
          toggleContainer.style.cursor  = 'not-allowed';
          toggleBtn.innerHTML = '3D';
          toggleBtn.title = '3D failed — check browser console for details';
          toggleBtn.style.pointerEvents = 'none';
        } finally {
          loadingEl.style.display = 'none';
          _loading = false;
        }
      });
    } else {
      _cesiumToLeaflet();
      _show2d();
      toggleBtn.innerHTML = '3D';
      L.DomUtil.removeClass(toggleContainer, 'is-3d');
      _is3d = false;
    }
  }

  // ── Hook window-exposed functions (populated at end of main IIFE) ─────────
  var _origVisible = window.setLayerVisible;
  window.setLayerVisible = function(item, visible) {
    if (_origVisible) _origVisible(item, visible);
    if (_cesiumOk && item != null) {
      var cl = _cesiumLayers[item.index !== undefined ? item.index : item];
      if (cl && cl.show !== undefined) cl.show = visible;
    }
  };

  var _origOpacity = window.setLayerOpacity;
  window.setLayerOpacity = function(item, factor) {
    if (_origOpacity) _origOpacity(item, factor);
    if (_cesiumOk && item != null) {
      var cl = _cesiumLayers[item.index !== undefined ? item.index : item];
      if (cl && cl.alpha !== undefined) cl.alpha = factor;
    }
  };

  var _origApplyTheme = window.applyTheme;
  window.applyTheme = function(idx) {
    if (_origApplyTheme) _origApplyTheme(idx);
    if (_cesiumOk && _is3d && THEMES[idx] && THEMES[idx].extent) {
      var ext = THEMES[idx].extent;
      _viewer.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(
          ext[0][1], ext[0][0], ext[1][1], ext[1][0]
        ),
        duration: 0.8
      });
    }
  };
})();

