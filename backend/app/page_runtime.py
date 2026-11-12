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

  // 4. Câblage de secours pour les boutons de Thème
  document.addEventListener('click', function(e) {
    var themeBtn = e.target && e.target.closest ? e.target.closest('#theme-toggle, #themeToggle, #themeButton, #themeBtn, #theme, .theme-btn, .theme-toggle, .theme-switcher') : null;
    if (!themeBtn) return;
    var root = document.documentElement;
    var cur = root.getAttribute('data-theme') || (root.classList.contains('dark') ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    if (next === 'dark') root.classList.add('dark'); else root.classList.remove('dark');
  }, true);

  // 5. Nettoyer les éléments de navigation cachés à tort (.tabs[hidden])
  function initDoc() {
    document.querySelectorAll('.tabs[hidden], nav[hidden]').forEach(function(el) {
      el.removeAttribute('hidden');
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDoc);
  } else {
    initDoc();
  }
})();
"""



def sanitize_and_enhance_html(html_code: str, *, title: str = "") -> str:
    """
    Garantit la complétude structurelle, la sécurité des liens et le runtime d'interactivité.
    - Ferme les balises tronquées (script, body, html).
    - Ajoute target="_blank" et rel="noopener noreferrer" sur tous les liens externes.
    - Rend visibles les barres d'onglets masquées par défaut.
    - Injecte CLAIR_PAGE_RUNTIME_JS pour assurer la navigation et les onglets.
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

    # 4. Injecter le script runtime universel
    if "__clair_runtime_installed__" not in code:
        runtime_tag = f"\n<script>\n{CLAIR_PAGE_RUNTIME_JS.strip()}\n</script>\n"
        if "</body>" in code:
            code = code.replace("</body>", f"{runtime_tag}</body>", 1)
        elif "</html>" in code:
            code = code.replace("</html>", f"{runtime_tag}</html>", 1)
        else:
            code += runtime_tag

    return code

