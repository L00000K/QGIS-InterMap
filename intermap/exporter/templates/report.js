// ── Report / story mode ──────────────────────────────────────────────────────
(function() {
  var REPORT = @@_report_json@@;
  if (!REPORT || (!REPORT.md && !REPORT.pdf)) return;

  var map      = window._im_map;
  var THEMES   = window._im_themes || [];
  var escHtml  = window._im_escHtml || function(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  };
  var pane      = document.getElementById('report-pane');
  var content   = document.getElementById('report-content');
  var scroller  = document.getElementById('report-scroll');
  var tocBody   = document.getElementById('report-toc-body');
  var media     = document.getElementById('report-media');
  var mediaCard = document.getElementById('report-media-card');
  var divider   = document.getElementById('report-divider');
  if (!pane || !content || !scroller || !media || !mediaCard) return;

  document.body.classList.add('report-on');
  var titleEl = document.getElementById('report-title');
  if (titleEl) titleEl.textContent = REPORT.title || 'Report';
  (REPORT.warnings || []).forEach(function(w) { console.warn('Report:', w); });

  // The report replaces the project-info panel as "the document" — collapse
  // it through its own button so the reopen chip behaviour stays intact.
  var _lpClose = document.getElementById('left-panel-close');
  if (_lpClose) _lpClose.click();

  // ── Markdown preprocessing: directives → placeholder HTML ────────────────
  function _parseAttrs(s) {
    var out = {};
    var idm = /#(fig|tbl):([\w-]+)/.exec(s || '');
    if (idm) { out.kind = idm[1]; out.id = idm[2]; }
    var re = /(\w+)="([^"]*)"/g, m;
    while ((m = re.exec(s || ''))) out[m[1]] = m[2];
    return out;
  }

  function preprocess(md) {
    var lines = md.split('\n');
    var out = [];
    var inFence = false;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i], m;
      if (/^```/.test(line)) { inFence = !inFence; out.push(line); continue; }
      if (inFence) { out.push(line); continue; }

      // :::view View Name [3d pitch=-35 heading=120]
      if ((m = /^:::view[ \t]+(.+)$/.exec(line))) {
        var rest = m[1], opts = {};
        var om = /\[([^\]]*)\]\s*$/.exec(rest);
        if (om) {
          rest = rest.slice(0, om.index);
          om[1].split(/\s+/).forEach(function(tok) {
            if (tok === '3d') { opts.mode3d = true; return; }
            var kv = tok.split('=');
            if (kv.length === 2 && isFinite(parseFloat(kv[1]))) opts[kv[0]] = parseFloat(kv[1]);
          });
        }
        out.push('<div class="rp-anchor rp-viewbind" data-view="' + escHtml(rest.trim())
               + '" data-opts="' + escHtml(JSON.stringify(opts)) + '"></div>');
        continue;
      }
      // :::table layer="Boreholes" filter="depth > 10" {#tbl:id caption="..."}
      if ((m = /^:::table\b(.*)$/.exec(line))) {
        var ta = _parseAttrs(m[1]);
        var tid = ta.id || ('t' + i);
        out.push('<div class="rp-anchor rp-media-anchor" data-media="tbl:' + tid + '"></div>');
        out.push('<div class="rp-livetable" data-id="' + tid
               + '" data-layer="' + escHtml(ta.layer || '')
               + '" data-filter="' + escHtml(ta.filter || '')
               + '" data-caption="' + escHtml(ta.caption || '') + '"></div>');
        continue;
      }
      // ![caption](path){#fig:id} — figure promoted to the media panel
      if ((m = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*\{#fig:([\w-]+)\}\s*$/.exec(line))) {
        var src = (REPORT.figures && REPORT.figures[m[2]]) || m[2];
        out.push('<div class="rp-anchor rp-media-anchor" data-media="fig:' + m[3] + '"></div>');
        out.push('<div class="rp-fig" data-id="' + m[3] + '" data-src="' + escHtml(src)
               + '" data-caption="' + escHtml(m[1]) + '"></div>');
        continue;
      }
      // {#tbl:id caption="..."} on its own line marks the NEXT markdown table
      if ((m = /^\{#tbl:([\w-]+)([^}]*)\}\s*$/.exec(line))) {
        var ma = _parseAttrs('#tbl:' + m[1] + ' ' + m[2]);
        out.push('<div class="rp-anchor rp-media-anchor" data-media="tbl:' + m[1] + '"></div>');
        out.push('<div class="rp-tblmark" data-id="' + m[1]
               + '" data-caption="' + escHtml(ma.caption || '') + '"></div>');
        continue;
      }
      // Spaces in gis:/view: destinations break CommonMark link parsing —
      // percent-encode them here; the click handler decodes.
      line = line.replace(/\]\((gis|view):([^)]+)\)/g, function(_, proto, rest) {
        return '](' + proto + ':' + rest.replace(/ /g, '%20') + ')';
      });
      // inline cross-references (fig:id) / (tbl:id) → "Figure N" links
      line = line.replace(/\((fig|tbl):([\w-]+)\)/g, function(_, k, id) {
        return '<a href="' + k + ':' + id + '" class="rp-medialink" data-ref="' + k + ':' + id + '"></a>';
      });
      out.push(line);
    }
    return out.join('\n');
  }

  // ── Render ────────────────────────────────────────────────────────────────
  if (REPORT.pdf) {
    // PDF mode — pages are rendered asynchronously by initPdfReport() below.
  } else if (typeof marked !== 'undefined') {
    if (marked.use) marked.use({
      renderer: {
        image: function(href, title, text) {
          var src = (REPORT.figures && REPORT.figures[href]) || href;
          return '<img src="' + escHtml(src) + '" alt="' + escHtml(text || '') + '" style="max-width:100%">';
        }
      }
    });
    content.innerHTML = marked.parse(preprocess(REPORT.md));
  } else {
    // marked failed to embed — degrade to plain text rather than nothing
    var pre = document.createElement('pre');
    pre.style.whiteSpace = 'pre-wrap';
    pre.textContent = REPORT.md;
    content.appendChild(pre);
  }

  // ── Live attribute tables from exported layers ────────────────────────────
  function _rowPasses(props, filter) {
    if (!filter) return true;
    return filter.split('&&').every(function(clause) {
      var cm = /^\s*([\w ]+?)\s*(==|!=|>=|<=|>|<|contains)\s*(.+?)\s*$/.exec(clause);
      if (!cm) return true;
      var val = props[cm[1].trim()];
      var want = cm[3].replace(/^["']|["']$/g, '');
      if (cm[2] === 'contains') return String(val).toLowerCase().indexOf(want.toLowerCase()) !== -1;
      var a = parseFloat(val), b = parseFloat(want);
      var numeric = isFinite(a) && isFinite(b);
      switch (cm[2]) {
        case '==': return numeric ? a === b : String(val) === want;
        case '!=': return numeric ? a !== b : String(val) !== want;
        case '>':  return numeric && a >  b;
        case '>=': return numeric && a >= b;
        case '<':  return numeric && a <  b;
        case '<=': return numeric && a <= b;
      }
      return true;
    });
  }

  function _buildLiveTable(layerName, filter) {
    var LAYERS = window._im_layers || [];
    var ld = null;
    LAYERS.forEach(function(l) { if (!ld && l.kind === 'vector' && l.name === layerName) ld = l; });
    if (!ld) return null;
    var feats = (ld.geojson.features || []).filter(function(f) {
      return _rowPasses(f.properties || {}, filter);
    });
    if (!feats.length) return null;
    var cols = Object.keys(feats[0].properties || {});
    var t = document.createElement('table');
    t.innerHTML = '<thead><tr>' + cols.map(function(c) {
      return '<th>' + escHtml(c) + '</th>';
    }).join('') + '</tr></thead>';
    var tb = document.createElement('tbody');
    feats.slice(0, 500).forEach(function(f) {
      var tr = document.createElement('tr');
      tr.innerHTML = cols.map(function(c) {
        var v = (f.properties || {})[c];
        return '<td>' + escHtml(v == null ? '' : String(v)) + '</td>';
      }).join('');
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }

  // ── Figure / table registry, numbering, inline print copies ──────────────
  var mediaReg = {};
  var figN = 0, tblN = 0;

  function _makeChip(icon, label, caption, key) {
    var chip = document.createElement('div');
    chip.className = 'rp-chip';
    chip.dataset.media = key;
    chip.innerHTML = icon + ' <span class="rp-chip-num">' + escHtml(label) + '</span> '
                   + '<span>' + escHtml(caption || '') + '</span>';
    return chip;
  }

  Array.prototype.slice.call(
    content.querySelectorAll('.rp-fig, .rp-tblmark, .rp-livetable')
  ).forEach(function(el) {
    var id = el.dataset.id, key, label, inline;
    if (el.classList.contains('rp-fig')) {
      figN++; key = 'fig:' + id; label = 'Figure ' + figN;
      inline = document.createElement('figure');
      inline.className = 'rp-inline';
      inline.innerHTML = '<img src="' + escHtml(el.dataset.src) + '">'
        + '<figcaption class="rp-caption"><b>' + escHtml(label) + '</b> — '
        + escHtml(el.dataset.caption || '') + '</figcaption>';
      el.parentNode.insertBefore(_makeChip('&#128444;', label, el.dataset.caption, key), el);
      el.parentNode.insertBefore(inline, el);
      el.remove();
      mediaReg[key] = { num: figN, label: label, caption: el.dataset.caption || '', inline: inline };
    } else {
      tblN++; key = 'tbl:' + id; label = 'Table ' + tblN;
      var tableEl = null;
      if (el.classList.contains('rp-livetable')) {
        tableEl = _buildLiveTable(el.dataset.layer, el.dataset.filter);
        if (!tableEl) {
          console.warn('Report: live table has no data —', el.dataset.layer);
          el.remove();
          return;
        }
      } else {
        // marker binds to the next rendered <table>
        var sib = el.nextElementSibling;
        while (sib && sib.tagName !== 'TABLE') sib = sib.nextElementSibling;
        tableEl = sib;
        if (!tableEl) { el.remove(); return; }
        tableEl.parentNode.removeChild(tableEl);
      }
      inline = document.createElement('figure');
      inline.className = 'rp-inline';
      inline.appendChild(tableEl);
      var fc = document.createElement('figcaption');
      fc.className = 'rp-caption';
      fc.innerHTML = '<b>' + escHtml(label) + '</b> — ' + escHtml(el.dataset.caption || '');
      inline.appendChild(fc);
      el.parentNode.insertBefore(_makeChip('&#128202;', label, el.dataset.caption, key), el);
      el.parentNode.insertBefore(inline, el);
      el.remove();
      mediaReg[key] = { num: tblN, label: label, caption: el.dataset.caption || '', inline: inline };
    }
  });

  // Resolve inline (fig:x)/(tbl:x) cross-reference labels
  Array.prototype.slice.call(content.querySelectorAll('a.rp-medialink')).forEach(function(a) {
    var reg = mediaReg[a.dataset.ref];
    a.textContent = reg ? reg.label : a.dataset.ref;
  });

  // ── Auto-linking of feature IDs in prose ──────────────────────────────────
  (REPORT.autolink || []).forEach(function(rule) {
    var re;
    try { re = new RegExp('\\b(' + rule.pattern + ')\\b', 'g'); }
    catch(e) { console.warn('Report: bad autolink pattern', rule.pattern); return; }
    var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, {
      acceptNode: function(n) {
        var p = n.parentNode;
        while (p && p !== content) {
          var tag = p.tagName;
          if (tag === 'A' || tag === 'CODE' || tag === 'PRE' || tag === 'SCRIPT') return NodeFilter.FILTER_REJECT;
          p = p.parentNode;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) {
      re.lastIndex = 0;  // .test() with /g is stateful — reset per node
      if (re.test(walker.currentNode.nodeValue)) nodes.push(walker.currentNode);
    }
    nodes.forEach(function(node) {
      var frag = document.createDocumentFragment();
      var last = 0, text = node.nodeValue, m;
      re.lastIndex = 0;
      while ((m = re.exec(text))) {
        frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var a = document.createElement('a');
        a.className = 'rp-gis';
        a.href = 'gis:' + rule.layer + '?' + rule.field + '=' + encodeURIComponent(m[1]);
        a.textContent = m[1];
        frag.appendChild(a);
        last = m.index + m[0].length;
      }
      frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  });

  // ── Table of contents ─────────────────────────────────────────────────────
  var headings = Array.prototype.slice.call(content.querySelectorAll('h1, h2, h3'));
  var _slugSeen = {};
  headings.forEach(function(h) {
    var slug = (h.textContent || '').toLowerCase().replace(/[^\w]+/g, '-').replace(/^-|-$/g, '') || 'sec';
    if (_slugSeen[slug]) slug += '-' + (++_slugSeen[slug]);
    else _slugSeen[slug] = 1;
    h.id = 'rp-' + slug;
    if (tocBody) {
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = 'toc-' + h.tagName.toLowerCase();
      a.textContent = h.textContent;
      a.addEventListener('click', function(e) {
        e.preventDefault();
        scroller.scrollTo({ top: _offsetIn(h) - 8, behavior: 'smooth' });
      });
      tocBody.appendChild(a);
    }
  });

  // ── Media panel ───────────────────────────────────────────────────────────
  var _activeMedia = null;
  function showMedia(key) {
    var reg = mediaReg[key];
    if (!reg) return;
    if (_activeMedia === key) return;
    _activeMedia = key;
    mediaCard.innerHTML = '';
    var clone = reg.inline.cloneNode(true);
    clone.classList.remove('rp-inline');
    clone.style.display = 'block';
    clone.style.margin = '0';
    mediaCard.appendChild(clone);
    media.classList.add('visible');
  }
  function hideMedia() {
    if (_activeMedia === null) return;
    _activeMedia = null;
    media.classList.remove('visible');
  }

  // ── View activation (2D map or 3D camera) ─────────────────────────────────
  function _in3d() {
    var c = document.getElementById('cesium-container');
    return !!(window._im_cesiumViewer && c && c.style.display === 'block');
  }

  function applyView(name, opts) {
    var idx = -1;
    THEMES.forEach(function(t, i) { if (idx === -1 && (t.name || '') === name) idx = i; });
    if (idx === -1) return console.warn('Report: unknown view', name);
    if (window._im_applyTheme) window._im_applyTheme(idx);
    var ext = THEMES[idx].extent;
    if (_in3d() && ext && window.Cesium) {
      var cv = window._im_cesiumViewer;
      if (opts && (opts.pitch !== undefined || opts.heading !== undefined || opts.height !== undefined)) {
        var cLon = (ext[0][1] + ext[1][1]) / 2, cLat = (ext[0][0] + ext[1][0]) / 2;
        var spanM = Math.max(
          Math.abs(ext[1][1] - ext[0][1]) * 111320 * Math.cos(cLat * Math.PI / 180),
          Math.abs(ext[1][0] - ext[0][0]) * 110540);
        cv.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(cLon, cLat, opts.height || spanM * 1.3),
          orientation: {
            heading: Cesium.Math.toRadians(opts.heading || 0),
            pitch:   Cesium.Math.toRadians(opts.pitch !== undefined ? opts.pitch : -90),
            roll: 0
          },
          duration: 1.0
        });
      } else {
        cv.camera.flyTo({
          destination: Cesium.Rectangle.fromDegrees(ext[0][1], ext[0][0], ext[1][1], ext[1][0]),
          duration: 1.0
        });
      }
    }
  }

  // ── GIS feature links ─────────────────────────────────────────────────────
  function gisFly(layerName, field, value) {
    var items = window._legendItems || [];
    var target = null;
    items.forEach(function(it) {
      if (!target && it.ld && it.ld.kind === 'vector' && it.ld.name === layerName) target = it;
    });
    if (!target) return console.warn('Report gis link: layer not in export —', layerName);
    if (!target.visible && window.setLayerVisible) window.setLayerVisible(target, true);
    var feat = null;
    (target.ld.geojson.features || []).forEach(function(f) {
      if (!feat && String((f.properties || {})[field]) === String(value)) feat = f;
    });
    if (!feat) return console.warn('Report gis link: no feature where', field, '=', value);
    var b = null;
    try { b = L.geoJSON(feat).getBounds(); } catch(e) {}
    if (b && b.isValid()) {
      if (b.getNorth() === b.getSouth() && b.getEast() === b.getWest()) {
        map.flyTo(b.getCenter(), Math.max(map.getZoom(), 16));
      } else {
        map.flyToBounds(b.pad(0.6));
      }
      if (_in3d() && window.Cesium) {
        window._im_cesiumViewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(
            b.getCenter().lng, b.getCenter().lat, 1200),
          duration: 1.0
        });
      }
    }
    if (window._im_highlightFeature) window._im_highlightFeature(feat);
    if (b && b.isValid()) {
      var rows = Object.keys(feat.properties || {}).map(function(k) {
        return '<tr><th style="text-align:left;padding:1px 8px 1px 0;opacity:0.65;white-space:nowrap">'
          + escHtml(k) + '</th><td>' + escHtml(String(feat.properties[k] != null ? feat.properties[k] : ''))
          + '</td></tr>';
      }).join('');
      L.popup({ maxHeight: 240 })
        .setLatLng(b.getCenter())
        .setContent('<b>' + escHtml(layerName) + '</b>'
          + '<table style="font-size:11px;border-collapse:collapse">' + rows + '</table>')
        .openOn(map);
    }
  }

  // ── Link interception (report text AND cloned media-panel content) ───────
  function _onLinkClick(e) {
    var chip = e.target.closest ? e.target.closest('.rp-chip') : null;
    if (chip) { showMedia(chip.dataset.media); return; }
    var a = e.target.closest ? e.target.closest('a') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.indexOf('gis:') === 0) {
      e.preventDefault();
      var qm = href.indexOf('?');
      if (qm === -1) return;
      var layer = decodeURIComponent(href.slice(4, qm));
      var eq = href.indexOf('=', qm);
      if (eq === -1) return;
      hideMedia();  // links act on the map — make sure it is visible
      gisFly(layer, decodeURIComponent(href.slice(qm + 1, eq)),
             decodeURIComponent(href.slice(eq + 1)));
    } else if (href.indexOf('view:') === 0) {
      e.preventDefault();
      hideMedia();
      applyView(decodeURIComponent(href.slice(5)), null);
    } else if (/^(fig|tbl):/.test(href)) {
      e.preventDefault();
      showMedia(href);
    }
  }
  content.addEventListener('click', _onLinkClick);
  mediaCard.addEventListener('click', _onLinkClick);

  // ── Scrollytelling ────────────────────────────────────────────────────────
  function _offsetIn(el) {
    return el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
  }

  var anchors = [];
  Array.prototype.slice.call(
    content.querySelectorAll('.rp-anchor, .rp-chip, h1, h2, h3')
  ).forEach(function(el) {
    if (el.classList.contains('rp-viewbind')) {
      anchors.push({ el: el, kind: 'view', view: el.dataset.view,
                     opts: JSON.parse(el.dataset.opts || '{}') });
    } else if (el.classList.contains('rp-media-anchor')) {
      anchors.push({ el: el, kind: 'media', key: el.dataset.media });
    } else if (el.classList.contains('rp-chip')) {
      // chips are visible stand-ins for their media anchor; skip (anchor precedes)
    } else {
      anchors.push({ el: el, kind: 'heading', heading: el });
    }
  });

  var _activeAnchor = -1, _activeHeading = null, _scrollScheduled = false;
  function _onScroll() {
    _scrollScheduled = false;
    var trigger = scroller.scrollTop + scroller.clientHeight * 0.42;
    var act = -1;
    for (var i = 0; i < anchors.length; i++) {
      if (_offsetIn(anchors[i].el) <= trigger) act = i;
      else break;
    }
    if (act === _activeAnchor) return;
    _activeAnchor = act;
    var a = act >= 0 ? anchors[act] : null;
    if (!a) { hideMedia(); return; }
    if (a.kind === 'view')       { hideMedia(); applyView(a.view, a.opts); }
    else if (a.kind === 'media') { showMedia(a.key); }
    else                         { hideMedia(); }
    // TOC highlight tracks the last heading crossed
    var h = null;
    for (var j = act; j >= 0; j--) if (anchors[j].kind === 'heading') { h = anchors[j].heading; break; }
    if (h !== _activeHeading && tocBody) {
      _activeHeading = h;
      Array.prototype.slice.call(tocBody.querySelectorAll('a')).forEach(function(t) {
        t.classList.toggle('active', h !== null && t.getAttribute('href') === '#' + h.id);
      });
    }
  }
  scroller.addEventListener('scroll', function() {
    if (_scrollScheduled) return;
    _scrollScheduled = true;
    requestAnimationFrame(_onScroll);
  });
  setTimeout(_onScroll, 300);

  // ── PDF report mode ───────────────────────────────────────────────────────
  // Renders the uploaded PDF page-by-page into the report pane and drives the
  // map from the page→view bindings as the reader scrolls: whichever page
  // sits closest to the middle of the pane is "current", and if it has a
  // bound map view, that view is applied (same applyView machinery as the
  // markdown scrollytelling).
  function initPdfReport() {
    var lib = window['pdfjs-dist/build/pdf'] || window.pdfjsLib;
    if (!lib) {
      content.textContent = 'PDF viewer failed to load.';
      return;
    }
    var wsEl = document.getElementById('pdfjs-worker-src');
    if (wsEl) {
      lib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(
        new Blob([wsEl.textContent], {type: 'text/javascript'}));
    }
    var raw = atob(REPORT.pdf);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

    var bindings = {};                       // page number → {page, view, opts}
    (REPORT.bindings || []).forEach(function(b) {
      if (b && b.page >= 1 && b.view) bindings[b.page] = b;
    });

    var pageEls = [];
    var _current = 0;

    lib.getDocument({data: bytes}).promise.then(function(doc) {
      var total = doc.numPages;
      var chain = Promise.resolve();
      for (var n = 1; n <= total; n++) (function(n) {
        chain = chain.then(function() {
          return doc.getPage(n);
        }).then(function(page) {
          // Render at 1.5x and let CSS fit the pane width — crisp on normal
          // displays without re-rendering on divider drags.
          var vp = page.getViewport({scale: 1.5});
          var holder = document.createElement('div');
          holder.className = 'rp-pdf-page';
          holder.dataset.page = String(n);
          var canvas = document.createElement('canvas');
          canvas.width = vp.width;
          canvas.height = vp.height;
          holder.appendChild(canvas);
          var b = bindings[n];
          if (b) {
            var chip = document.createElement('div');
            chip.className = 'rp-pdf-chip';
            chip.textContent = '◎ ' + b.view;
            chip.title = 'This page is linked to map view "' + b.view + '"';
            holder.appendChild(chip);
          }
          content.appendChild(holder);
          pageEls.push(holder);
          return page.render({canvasContext: canvas.getContext('2d'),
                              viewport: vp}).promise;
        });
      })(n);
      return chain.then(function() {
        buildPdfToc(total);
        scroller.addEventListener('scroll', _onPdfScroll);
        updateCurrentPage(true);
      });
    }).catch(function(e) {
      console.error('PDF report failed:', e);
      content.textContent = 'Could not render the PDF report.';
    });

    function buildPdfToc(total) {
      if (!tocBody) return;
      for (var n = 1; n <= total; n++) (function(n) {
        var a = document.createElement('a');
        a.href = '#';
        var b = bindings[n];
        a.textContent = 'Page ' + n + (b ? ' — ' + b.view : '');
        a.addEventListener('click', function(e) {
          e.preventDefault();
          var el = pageEls[n - 1];
          if (el) scroller.scrollTo({top: el.offsetTop - 8, behavior: 'smooth'});
        });
        tocBody.appendChild(a);
      })(n);
    }

    function dominantPage() {
      var mid = scroller.getBoundingClientRect().top + scroller.clientHeight / 2;
      var best = 1, bestDist = Infinity;
      for (var i = 0; i < pageEls.length; i++) {
        var r = pageEls[i].getBoundingClientRect();
        var d = Math.abs((r.top + r.bottom) / 2 - mid);
        if (d < bestDist) { bestDist = d; best = i + 1; }
      }
      return best;
    }

    function updateCurrentPage(force) {
      var n = dominantPage();
      if (!force && n === _current) return;
      _current = n;
      pane.dataset.currentPage = String(n);
      if (titleEl) {
        titleEl.textContent = (REPORT.title || 'Report')
                            + '  ·  p.' + n + '/' + pageEls.length;
      }
      if (tocBody) {
        Array.prototype.forEach.call(tocBody.children, function(a, i) {
          a.classList.toggle('rp-pdf-current', i === n - 1);
        });
      }
      var b = bindings[n];
      if (b) {
        pane.dataset.activeView = b.view;
        applyView(b.view, b.opts || null);
      }
    }

    var _pdfRaf = null;
    function _onPdfScroll() {
      if (_pdfRaf) return;
      _pdfRaf = requestAnimationFrame(function() {
        _pdfRaf = null;
        updateCurrentPage(false);
      });
    }
  }
  if (REPORT.pdf) initPdfReport();

  // ── Divider drag + collapse / restore ─────────────────────────────────────
  if (divider) {
    var _dragging = false;
    divider.addEventListener('pointerdown', function(e) {
      _dragging = true;
      divider.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    divider.addEventListener('pointermove', function(e) {
      if (!_dragging) return;
      var left = pane.getBoundingClientRect().left;
      var w = Math.min(Math.max(e.clientX - left, 240), document.body.clientWidth - left - 320);
      pane.style.width = w + 'px';
      if (map) map.invalidateSize();
    });
    divider.addEventListener('pointerup', function() { _dragging = false; });
  }

  var collapseBtn = document.getElementById('report-collapse');
  var restoreBtn  = document.getElementById('report-restore');
  if (collapseBtn) collapseBtn.addEventListener('click', function() {
    document.body.classList.add('report-collapsed');
    if (map) map.invalidateSize();
  });
  if (restoreBtn) restoreBtn.addEventListener('click', function() {
    document.body.classList.remove('report-collapsed');
    if (map) map.invalidateSize();
  });
})();
