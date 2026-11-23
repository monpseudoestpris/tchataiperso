"""
Runtime de robustesse et d'interactivité universelle pour les pages HTML cLAIr Pages.
Respecte la règle un module = une responsabilité.
Garantit que tous les liens, onglets, ancres et boutons fonctionnent dans l'iframe srcDoc.
"""

import re

CLAIR_PAGE_RUNTIME_JS = """
// === cLAIr Pages - Runtime Universel d'Interactivité, Navigation & Robustesse ===
(function() {
  if (typeof window === 'undefined' || window.__clair_runtime_installed__) return;
  window.__clair_runtime_installed__ = true;

  // 1. Interception sécurisée de location.reload dans un iframe srcDoc
  try {
    var _safeReload = function() {
      try {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        document.querySelectorAll('form').forEach(function(f) { try { f.reset(); } catch(e){} });
        document.querySelectorAll('.quiz-option, .quiz-btn, .quiz-choice').forEach(function(b) {
          b.disabled = false;
          b.classList.remove('correct', 'incorrect', 'selected', 'active');
        });
        document.querySelectorAll('.quiz-feedback, #quizFeedback').forEach(function(fb) {
          fb.textContent = '';
          fb.className = fb.className.replace(/\\b(show|correct|incorrect)\\b/g, '').trim();
        });
      } catch (err) {}
    };
    if (window.location) {
      window.location.reload = _safeReload;
    }
  } catch (e) {}

  // 2. Gestionnaire universel de liens d'ancres (<a href="#...">)
  document.addEventListener('click', function(e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';

    // Liens externes : forcer target="_blank"
    if (/^https?:\\/\\//i.test(href)) {
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
      return;
    }

    // Liens d'ancres internes
    if (href.startsWith('#')) {
      var id = href.slice(1).trim();
      if (!id || id === 'haut' || id === 'top') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      var target = document.getElementById(id) || document.querySelector('[name="' + CSS.escape(id) + '"]');
      if (!target) {
        target = document.querySelector('[data-section="' + CSS.escape(id) + '"]') ||
                 document.querySelector('[data-target="' + CSS.escape(id) + '"]') ||
                 document.querySelector('.' + CSS.escape(id));
      }
      if (target) {
        e.preventDefault();
        // Si l'élément cible est dans un panneau ou onglet masqué, activer cet onglet
        var hiddenAncestor = target.closest('[hidden], .panel:not(.active), .tab-content:not(.active)');
        if (hiddenAncestor) {
          hiddenAncestor.removeAttribute('hidden');
          hiddenAncestor.classList.add('active');
          if (hiddenAncestor.style.display === 'none') hiddenAncestor.style.display = '';
          var panelId = hiddenAncestor.id || hiddenAncestor.getAttribute('data-section');
          if (panelId) {
            var tabBtn = document.querySelector('[data-tab="' + CSS.escape(panelId) + '"], [data-target="' + CSS.escape(panelId) + '"], [data-filter="' + CSS.escape(panelId) + '"], [aria-controls="' + CSS.escape(panelId) + '"]');
            if (tabBtn) {
              var parentGroup = tabBtn.closest('.tabs, [role="tablist"], nav, .theme-tabs, .explore-links');
              if (parentGroup) {
                parentGroup.querySelectorAll('button, a').forEach(function(b) {
                  b.classList.remove('active');
                  b.removeAttribute('aria-current');
                  if (b.hasAttribute('aria-selected')) b.setAttribute('aria-selected', 'false');
                  if (b.hasAttribute('aria-pressed')) b.setAttribute('aria-pressed', 'false');
                });
              }
              tabBtn.classList.add('active');
              if (tabBtn.hasAttribute('aria-selected')) tabBtn.setAttribute('aria-selected', 'true');
              if (tabBtn.hasAttribute('aria-pressed')) tabBtn.setAttribute('aria-pressed', 'true');
            }
          }
        }
        try {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
          window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - 20, behavior: 'smooth' });
        }
      }
    }
  }, true);

  // 3. Gestionnaire universel d'onglets et filtres de navigation
  document.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest ? e.target.closest('button, [role="tab"], .explore-link, .tab-btn, .theme-tab') : null;
    if (!btn) return;

    var filter = btn.getAttribute('data-filter') || btn.getAttribute('data-category');
    var tabTarget = btn.getAttribute('data-tab') || btn.getAttribute('data-target') || btn.getAttribute('aria-controls');

    // Cas 3A : Filtrage par section (ex: data-filter="all" ou "methode")
    if (filter) {
      e.preventDefault();
      var filterContainer = btn.closest('.tabs, .theme-tabs, nav, [role="group"]');
      if (filterContainer) {
        filterContainer.querySelectorAll('button, .theme-tab').forEach(function(b) {
          b.classList.remove('active');
          if (b.hasAttribute('aria-pressed')) b.setAttribute('aria-pressed', 'false');
          if (b.hasAttribute('aria-selected')) b.setAttribute('aria-selected', 'false');
        });
      }
      btn.classList.add('active');
      if (btn.hasAttribute('aria-pressed')) btn.setAttribute('aria-pressed', 'true');
      if (btn.hasAttribute('aria-selected')) btn.setAttribute('aria-selected', 'true');

      var sections = document.querySelectorAll('[data-section], [data-category], .chapter, .panel');
      sections.forEach(function(sec) {
        var secVal = sec.getAttribute('data-section') || sec.getAttribute('data-category') || sec.id;
        var match = (filter === 'all' || !secVal || secVal === filter);
        if (match) {
          sec.removeAttribute('hidden');
          sec.style.display = '';
        } else {
          sec.setAttribute('hidden', '');
        }
      });
      return;
    }

    // Cas 3B : Onglets à panneaux exclusifs (ex: data-target="methode" ou aria-controls="methode")
    if (tabTarget) {
      var targetEl = document.getElementById(tabTarget) || document.querySelector('[data-tab="' + CSS.escape(tabTarget) + '"]') || document.querySelector('[data-section="' + CSS.escape(tabTarget) + '"]');
      if (targetEl) {
        e.preventDefault();
        var tabGroup = btn.closest('.tabs, [role="tablist"], nav, .explore-links, .theme-tabs');
        if (tabGroup) {
          tabGroup.querySelectorAll('button, a, [role="tab"]').forEach(function(b) {
            b.classList.remove('active');
            b.removeAttribute('aria-current');
            if (b.hasAttribute('aria-selected')) b.setAttribute('aria-selected', 'false');
            if (b.hasAttribute('aria-pressed')) b.setAttribute('aria-pressed', 'false');
          });
        }
        btn.classList.add('active');
        if (btn.hasAttribute('aria-selected')) btn.setAttribute('aria-selected', 'true');
        if (btn.hasAttribute('aria-pressed')) btn.setAttribute('aria-pressed', 'true');
        btn.setAttribute('aria-current', 'location');

        var allPanels = document.querySelectorAll('.panel, .tab-content, [role="tabpanel"]');
        allPanels.forEach(function(p) {
          p.classList.remove('active');
          p.setAttribute('hidden', '');
        });
        targetEl.classList.add('active');
        targetEl.removeAttribute('hidden');
        try { targetEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (err) {}

        // Déclencher le rafraîchissement d'AOS pour animer les nouveaux éléments affichés
        try {
          if (window.AOS && typeof window.AOS.refresh === 'function') {
            window.AOS.refresh();
          }
          if (window.ScrollTrigger && typeof window.ScrollTrigger.refresh === 'function') {
            window.ScrollTrigger.refresh();
          }
        } catch (err) {}
      }
    }
  }, true);

  // 4. Désactivation du bouton de bascule de thème dans clAIr pages
  // (Le changement de thème est désactivé pour éviter les incompatibilités de rendu)

  // 5. Nettoyer les éléments de navigation cachés à tort (.tabs[hidden]) et calibrer les fiches A4
  function fitA4Sheets() {
    try {
      var body = document.body;
      if (!body) return;
      var mode = body.getAttribute('data-a4-mode');
      var sheets = Array.prototype.slice.call(document.querySelectorAll('.a4-sheet'));
      if (!mode && sheets.length === 0) return;
      mode = mode || (sheets.length >= 2 ? '2p' : '1p');

      // Copier le fond du body sur la feuille A4 s'il n'est pas déjà défini sur .a4-sheet
      var bodyStyle = window.getComputedStyle(body);
      var bodyBg = bodyStyle.backgroundColor;
      var bodyBgImg = bodyStyle.backgroundImage;

      // Si le LLM n'a pas créé de .a4-sheet, encapsuler le contenu principal automatiquement
      if (sheets.length === 0) {
        var wrapper = document.createElement('div');
        wrapper.className = 'a4-sheet';
        var children = Array.prototype.slice.call(body.childNodes);
        children.forEach(function(ch) {
          if (ch.nodeType === 1) {
            var tag = ch.tagName ? ch.tagName.toUpperCase() : '';
            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK') return;
            if (ch.classList && ch.classList.contains('no-print') && ch.classList.contains('a4-floating-toolbar')) return;
          }
          wrapper.appendChild(ch);
        });
        body.insertBefore(wrapper, body.firstChild);
        sheets = [wrapper];
      }

      // En mode 1 page stricte, fusionner tout débordement dans une unique .a4-sheet
      if (mode === '1p' && sheets.length > 1) {
        var primary = sheets[0];
        for (var i = 1; i < sheets.length; i++) {
          while (sheets[i].firstChild) {
            primary.appendChild(sheets[i].firstChild);
          }
          if (sheets[i].parentNode) sheets[i].parentNode.removeChild(sheets[i]);
        }
        sheets = [primary];
      }

      // En mode recto-verso (2p), plafonner strictement à 2 feuilles .a4-sheet
      if (mode === '2p' && sheets.length > 2) {
        var second = sheets[1];
        for (var j = 2; j < sheets.length; j++) {
          while (sheets[j].firstChild) {
            second.appendChild(sheets[j].firstChild);
          }
          if (sheets[j].parentNode) sheets[j].parentNode.removeChild(sheets[j]);
        }
        sheets = [sheets[0], second];
      }

      sheets.forEach(function(sheet) {
        // Préserver le thème de fond sur la feuille avant le cadrage bureau de body
        var sStyle = window.getComputedStyle(sheet);
        var hasSheetBg = (sStyle.backgroundColor && sStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' && sStyle.backgroundColor !== 'transparent') ||
                         (sStyle.backgroundImage && sStyle.backgroundImage !== 'none');
        if (!hasSheetBg) {
          if (bodyBgImg && bodyBgImg !== 'none') {
            sheet.style.backgroundImage = bodyBgImg;
          }
          if (bodyBg && bodyBg !== 'rgba(0, 0, 0, 0)' && bodyBg !== 'transparent') {
            sheet.style.backgroundColor = bodyBg;
          } else {
            sheet.style.backgroundColor = '#ffffff';
          }
        }

        // Assurer la présence d'un conteneur interne mesurable (.a4-sheet-inner)
        var inner = sheet.querySelector(':scope > .a4-sheet-inner');
        if (!inner) {
          inner = document.createElement('div');
          inner.className = 'a4-sheet-inner';
          while (sheet.firstChild) {
            inner.appendChild(sheet.firstChild);
          }
          sheet.appendChild(inner);
        }

        // Réinitialiser avant mesure
        inner.style.transform = '';
        inner.style.transformOrigin = '';
        inner.style.width = '';
        sheet.style.fontSize = '';
        sheet.style.padding = '';

        var cs = window.getComputedStyle(sheet);
        var padTop = parseFloat(cs.paddingTop) || 0;
        var padBottom = parseFloat(cs.paddingBottom) || 0;
        var padLeft = parseFloat(cs.paddingLeft) || 0;
        var padRight = parseFloat(cs.paddingRight) || 0;
        var availH = sheet.clientHeight - padTop - padBottom;
        var availW = sheet.clientWidth - padLeft - padRight;
        if (availH <= 100 || availW <= 100) return;

        // Étape A : compression typographique douce si léger débordement
        var steps = [
          { font: '92%', pad: '7mm 9mm' },
          { font: '85%', pad: '6mm 8mm' },
          { font: '78%', pad: '5.5mm 7mm' }
        ];
        for (var k = 0; k < steps.length; k++) {
          if (inner.scrollHeight <= availH && inner.scrollWidth <= availW) break;
          sheet.style.fontSize = steps[k].font;
          sheet.style.padding = steps[k].pad;
          cs = window.getComputedStyle(sheet);
          availH = sheet.clientHeight - (parseFloat(cs.paddingTop) || 0) - (parseFloat(cs.paddingBottom) || 0);
          availW = sheet.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
        }

        // Étape B : mise à l'échelle géométrique exacte si le contenu dépasse encore
        var curH = inner.scrollHeight;
        var curW = inner.scrollWidth;
        if (curH > availH || curW > availW) {
          var ratioH = curH > availH ? (availH - 2) / curH : 1;
          var ratioW = curW > availW ? (availW - 2) / curW : 1;
          var ratio = Math.max(0.42, Math.min(ratioH, ratioW));
          inner.style.transformOrigin = 'top left';
          inner.style.transform = 'scale(' + ratio.toFixed(4) + ')';
          inner.style.width = (100 / ratio).toFixed(3) + '%';
        }
      });

      body.classList.add('clair-a4-desk');
    } catch (err) {}
  }

  window.__clairFitA4 = fitA4Sheets;

  function initDoc() {
    document.querySelectorAll('.tabs[hidden], nav[hidden]').forEach(function(el) {
      el.removeAttribute('hidden');
    });
    fitA4Sheets();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDoc);
  } else {
    initDoc();
  }
  window.addEventListener('load', fitA4Sheets);
  window.addEventListener('beforeprint', fitA4Sheets);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(fitA4Sheets).catch(function(){});
  }
})();
"""

_A4_LAYOUT_STYLES = {"print_sheet", "a4_1p", "a4_2p", "cheat_sheet"}


def _build_a4_enforcer_css(orientation: str) -> str:
    is_landscape = orientation == "landscape"
    page_w = "297mm" if is_landscape else "210mm"
    page_h = "210mm" if is_landscape else "297mm"
    page_size = "A4 landscape" if is_landscape else "A4 portrait"
    return f"""<style id="clair-a4-enforcer-css">
@page {{
  size: {page_size};
  margin: 0;
}}
:root {{
  --a4-w: {page_w};
  --a4-h: {page_h};
  --a4-pad: 8mm 10mm;
}}
body[data-a4-mode],
body.clair-a4-desk {{
  margin: 0 !important;
  padding: 14px 10px !important;
  max-width: none !important;
  width: 100% !important;
  box-sizing: border-box !important;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}}
body.clair-a4-desk {{
  background-color: #e2e8f0 !important;
  background-image: none !important;
}}
.a4-sheet {{
  width: var(--a4-w);
  height: var(--a4-h);
  min-height: var(--a4-h);
  max-height: var(--a4-h);
  padding: var(--a4-pad);
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
  border-radius: 4px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
  page-break-after: always;
  break-after: page;
  flex-shrink: 0;
}}
.a4-sheet:last-of-type {{
  page-break-after: auto;
  break-after: auto;
}}
.a4-sheet-inner {{
  width: 100%;
  box-sizing: border-box;
}}
@media print {{
  html, body, body[data-a4-mode], body.clair-a4-desk {{
    margin: 0 !important;
    padding: 0 !important;
    background: #ffffff !important;
    background-image: none !important;
    display: block !important;
    width: {page_w} !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  .no-print {{
    display: none !important;
  }}
  .a4-sheet {{
    margin: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    border: none !important;
    width: {page_w} !important;
    height: {page_h} !important;
    max-height: {page_h} !important;
    overflow: hidden !important;
  }}
}}
</style>"""


def inject_a4_sheet_enforcer(
    html_code: str,
    layout_style: str = "auto",
    orientation: str = "portrait",
) -> str:
    """
    Injecte la géométrie physique A4 stricte (210x297mm ou 297x210mm) et les attributs
    `data-a4-mode` / `data-a4-orientation` sur <body> lorsque le document est une fiche A4.
    """
    is_a4 = layout_style in _A4_LAYOUT_STYLES or "a4-sheet" in html_code or "data-a4-mode" in html_code
    if not is_a4:
        return html_code

    resolved_orientation = "landscape" if (layout_style == "cheat_sheet" or orientation == "landscape") else "portrait"
    if 'data-a4-orientation="landscape"' in html_code and layout_style == "auto":
        resolved_orientation = "landscape"

    resolved_mode = "2p" if (layout_style == "a4_2p" or 'data-a4-mode="2p"' in html_code) else "1p"

    code = html_code
    # S'assurer que <body> porte data-a4-mode et data-a4-orientation
    if "data-a4-mode=" not in code:
        code = re.sub(
            r"<body\b([^>]*)>",
            rf'<body\1 data-a4-mode="{resolved_mode}" data-a4-orientation="{resolved_orientation}">',
            code,
            count=1,
            flags=re.I,
        )

    if "clair-a4-enforcer-css" not in code:
        a4_css = _build_a4_enforcer_css(resolved_orientation)
        if "</head>" in code:
            code = code.replace("</head>", f"\n{a4_css}\n</head>", 1)
        elif "<body" in code:
            code = re.sub(r"(<body\b[^>]*>)", f"{a4_css}\n\\1", code, count=1, flags=re.I)
        else:
            code = f"{a4_css}\n{code}"

    return code


SANDBOX_STORAGE_SHIM_JS = r"""
(function() {
  if (typeof window === 'undefined' || window.__clair_storage_shim__) return;
  window.__clair_storage_shim__ = true;
  function makeMemStorage() {
    var data = Object.create(null);
    return {
      get length() { return Object.keys(data).length; },
      key: function(i) { var k = Object.keys(data); return i >= 0 && i < k.length ? k[i] : null; },
      getItem: function(k) { k = String(k); return Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null; },
      setItem: function(k, v) { data[String(k)] = String(v); },
      removeItem: function(k) { delete data[String(k)]; },
      clear: function() { data = Object.create(null); }
    };
  }
  ['localStorage', 'sessionStorage'].forEach(function(name) {
    try {
      var s = window[name];
      s.setItem('__clair_probe__', '1');
      s.removeItem('__clair_probe__');
    } catch (err) {
      try {
        Object.defineProperty(window, name, { value: makeMemStorage(), configurable: true });
      } catch (err2) {}
    }
  });
})();
"""


def inject_sandbox_storage_shim(html_code: str) -> str:
    """Injecte en tête de <head> un repli mémoire pour localStorage/sessionStorage sous origine opaque `null`."""
    if not html_code or "__clair_storage_shim__" in html_code:
        return html_code
    shim_tag = f"<script data-clair-storage-shim>\n{SANDBOX_STORAGE_SHIM_JS.strip()}\n</script>"
    head_match = re.search(r"<head\b[^>]*>", html_code, flags=re.I)
    if head_match:
        idx = head_match.end()
        return f"{html_code[:idx]}\n{shim_tag}\n{html_code[idx:]}"
    html_match = re.search(r"<html\b[^>]*>", html_code, flags=re.I)
    if html_match:
        idx = html_match.end()
        return f"{html_code[:idx]}\n<head>{shim_tag}</head>\n{html_code[idx:]}"
    return f"{shim_tag}\n{html_code}"


def sanitize_and_enhance_html(
    html_code: str,
    *,
    title: str = "",
    layout_style: str = "auto",
    orientation: str = "portrait",
    bricks: list[dict] | None = None,
) -> str:
    """
    Garantit la complétude structurelle, la sécurité des liens et le runtime d'interactivité.
    - Ferme les balises tronquées (script, body, html).
    - Ajoute target="_blank" et rel="noopener noreferrer" sur tous les liens externes.
    - Rend visibles les barres d'onglets masquées par défaut.
    - Injecte le gabarit physique A4 si la page est une fiche A4.
    - Injecte CLAIR_PAGE_RUNTIME_JS pour assurer la navigation, les onglets et l'auto-fit A4.
    - Injecte le pont `window.clair.runBrick(...)` lorsque des briques sont fournies (ou présentes).
    """
    code = html_code.strip()
    if not code:
        return code

    lower = code.lower()

    # 1. Fermeture des balises non terminées si réponse tronquée
    if "<body" in lower and "</body" not in lower:
        last_script_open = lower.rfind("<script")
        last_script_close = lower.rfind("</script")
        if last_script_open > last_script_close:
            code += "\n</script>"
        code += "\n</body>"
    if "<html" in lower and "</html" not in lower:
        code += "\n</html>"

    # 2. Sécurisation des liens externes (target="_blank" + rel="noopener noreferrer")
    def _fix_link(match: re.Match) -> str:
        tag = match.group(0)
        href_match = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if not href_match:
            return tag
        href = href_match.group(1).strip()
        if href.startswith(("http://", "https://", "//")):
            if "target=" not in tag.lower():
                tag = tag[:-1] + ' target="_blank">'
            elif 'target="_blank"' not in tag and "target='_blank'" not in tag:
                tag = re.sub(r'target=["\'][^"\']*["\']', 'target="_blank"', tag, flags=re.I)
            if "rel=" not in tag.lower():
                tag = tag[:-1] + ' rel="noopener noreferrer">'
            elif 'noopener' not in tag.lower():
                tag = re.sub(r'rel=["\']([^"\']*)["\']', r'rel="\1 noopener noreferrer"', tag, flags=re.I)
        return tag

    code = re.sub(r'<a\b[^>]*>', _fix_link, code, flags=re.I)

    # 3. Retirer hidden sur les barres d'onglets
    code = re.sub(r'(<(?:div|nav)\b[^>]*class=["\'][^"\']*(?:tabs|explore|filter)[^"\']*["\'][^>]*)\bhidden\b', r'\1', code, flags=re.I)

    # 4. Supprimer tout bouton de bascule de thème résiduel pour éviter les dysfonctionnements visuels
    code = re.sub(
        r'<button\b[^>]*\b(?:id|class)=["\'][^"\']*(?:theme-toggle|themeToggle|themeButton|themeBtn|theme-switcher)[^"\']*["\'][^>]*>.*?</button>',
        '',
        code,
        flags=re.I | re.DOTALL,
    )

    # 5. Injecter le shim mémoire localStorage/sessionStorage avant tout script de la page
    code = inject_sandbox_storage_shim(code)

    # 6. Injecter le gabarit physique A4 si la page est au format A4 strict
    code = inject_a4_sheet_enforcer(code, layout_style=layout_style, orientation=orientation)

    # 6. Injecter le script runtime universel
    if "__clair_runtime_installed__" not in code:
        runtime_tag = f"\n<script>\n{CLAIR_PAGE_RUNTIME_JS.strip()}\n</script>\n"
        if "</body>" in code:
            code = code.replace("</body>", f"{runtime_tag}</body>", 1)
        elif "</html>" in code:
            code = code.replace("</html>", f"{runtime_tag}</html>", 1)
        else:
            code += runtime_tag

    # 7. Injecter / actualiser le runtime des Briques Préfaites (window.clair.runBrick)
    if bricks is not None:
        from .page_bricks import inject_bricks_runtime_html

        code = inject_bricks_runtime_html(code, bricks)

    return code

