"""
Typography and text-shaping module for cLAIr Pages.
Integrates techniques and concepts inspired by:
- Charming.js: letter-by-letter splitting, accessible aria-labels, kinetic wave and gradient animations.
- Pretext: high-speed geometric canvas measurement to auto-fit titles and headings perfectly without reflow.
- xsvg: vector text shaping, curved text along SVG paths (textPath), and auto-contained text boxes.

All code is 100% autonomous, vanilla JavaScript and CSS3, requiring 0 external libraries or CDNs.
"""

import html
import re

TEXT_FX_CSS = """
/* === Charming & Kinetic Typography Effects === */
.charming, [data-fx] {
  display: inline-block;
  letter-spacing: -0.01em;
}

.c-char {
  display: inline-block;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), color 0.2s ease;
  animation-duration: 2.2s;
  animation-iteration-count: infinite;
  animation-timing-function: ease-in-out;
}

.c-space {
  width: 0.3em;
}

/* Effect 1: Wave (Ondulation fluide) */
[data-fx="wave"] .c-char,
.charming-wave .c-char {
  animation-name: charWave;
  animation-delay: calc(var(--i) * 0.055s);
}

@keyframes charWave {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-7px); }
}

/* Effect 2: Gradient Flow (Dégradé chromatique animé le long des lettres) */
[data-fx="gradient"] .c-char,
.charming-gradient .c-char {
  color: hsl(calc(var(--primary-h, 210) + (var(--i) * 8)), 85%, 65%);
  animation-name: charHue;
  animation-delay: calc(var(--i) * 0.08s);
}

@keyframes charHue {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.25) drop-shadow(0 0 6px var(--primary)); }
}

/* Effect 3: Bounce / Pop au survol */
[data-fx="bounce"] .c-char:hover,
.charming-bounce .c-char:hover {
  transform: translateY(-8px) scale(1.15) rotate(-3deg);
  color: var(--accent);
}

/* Effect 4: Glow / Halos doux sur termes clés */
[data-fx="glow"] .c-char,
.charming-glow .c-char {
  animation-name: charGlow;
  animation-delay: calc(var(--i) * 0.07s);
}

@keyframes charGlow {
  0%, 100% { text-shadow: 0 0 3px rgba(56, 189, 248, 0.2); }
  50% { text-shadow: 0 0 14px var(--primary), 0 0 25px var(--accent); }
}

/* Effect 5: Cascade / Reveal progressif */
[data-fx="stagger"] .c-char {
  animation: charStagger 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: calc(var(--i) * 0.04s);
}

@keyframes charStagger {
  0% { opacity: 0; transform: translateY(16px) rotate(6deg); filter: blur(4px); }
  100% { opacity: 1; transform: translateY(0) rotate(0); filter: blur(0); }
}

/* === Pretext: Monumental Auto-fit Headings === */
.pretext-fit, [data-fit="true"] {
  display: block;
  width: 100%;
  text-align: center;
  font-weight: 800;
  letter-spacing: -0.03em;
  white-space: nowrap;
  overflow: hidden;
  line-height: 1.05;
  margin: 0.5rem auto;
}

/* === xsvg: Curved Text on Vector Path & Text Badges === */
.xsvg-curved-wrap {
  width: 100%;
  max-width: 720px;
  margin: 0.75rem auto 1.5rem;
  overflow: hidden;
  display: block;
}

.xsvg-curved-wrap svg {
  width: 100%;
  height: auto;
  display: block;
}

.xsvg-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.85rem;
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(168, 85, 247, 0.12));
  border: 1px solid var(--primary);
  border-radius: 999px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}
"""

TEXT_FX_JS = """
  // === 1. Charming.js: Accessible Letter-by-Letter Kinetic Typography ===
  function initCharmingTypography() {
    const targets = document.querySelectorAll('.charming, [data-fx]');
    targets.forEach(el => {
      if (el.dataset.charmingDone) return;
      el.dataset.charmingDone = 'true';
      const text = el.textContent.trim();
      if (!text) return;

      el.setAttribute('aria-label', text);
      el.innerHTML = '';

      [...text].forEach((char, index) => {
        const span = document.createElement('span');
        span.className = 'c-char' + (char === ' ' ? ' c-space' : '');
        span.textContent = char;
        span.style.setProperty('--i', index);
        span.style.setProperty('--total', text.length);
        el.appendChild(span);
      });
    });
  }

  // === 2. Pretext: High-Performance Canvas-Assisted Auto-Fit Titles ===
  function initPretextAutoFit() {
    const targets = document.querySelectorAll('.pretext-fit, [data-fit="true"]');
    if (!targets.length) return;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    function recalculate() {
      targets.forEach(el => {
        const parent = el.parentElement || document.body;
        const availableWidth = parent.clientWidth * 0.95;
        if (!availableWidth) return;

        const text = el.getAttribute('aria-label') || el.textContent.trim();
        const style = window.getComputedStyle(el);
        const fontFam = style.fontFamily || 'system-ui, sans-serif';
        const fontWeight = style.fontWeight || '800';

        // Fast binary search to find optimal pixel size (inspired by Pretext arithmetic)
        let minSize = 14;
        let maxSize = 96;
        let best = minSize;

        while (minSize <= maxSize) {
          const mid = Math.floor((minSize + maxSize) / 2);
          ctx.font = `${fontWeight} ${mid}px ${fontFam}`;
          const measured = ctx.measureText(text).width;
          if (measured <= availableWidth) {
            best = mid;
            minSize = mid + 1;
          } else {
            maxSize = mid - 1;
          }
        }

        el.style.fontSize = best + 'px';
      });
    }

    recalculate();
    window.addEventListener('resize', recalculate);
  }

  // Initialize on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initCharmingTypography();
      initPretextAutoFit();
    });
  } else {
    initCharmingTypography();
    initPretextAutoFit();
  }
"""


def render_curved_text(
    text: str,
    curve: str = "wave",
    primary: str = "var(--primary)",
    accent: str = "var(--accent)",
) -> str:
    """
    Renders an xsvg-inspired curved text path that takes organic shape.
    curve options: 'wave' (sinusoidal flow), 'arc' (gentle dome arch).
    """
    safe_text = html.escape(text.strip())
    path_id = f"text_curve_{abs(hash(text)) % 10000}"

    if curve == "arc":
        path_d = "M 40,75 Q 350,15 660,75"
        view_box = "0 0 700 95"
    else:  # wave
        path_d = "M 30,55 Q 190,15 350,55 T 670,55"
        view_box = "0 0 700 90"

    return f"""<div class="xsvg-curved-wrap no-print">
  <svg viewBox="{view_box}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="{path_id}_grad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="{primary}" />
        <stop offset="100%" stop-color="{accent}" />
      </linearGradient>
      <path id="{path_id}" d="{path_d}" fill="none" />
    </defs>
    <text font-size="22" font-weight="700" letter-spacing="1" fill="url(#{path_id}_grad)" text-anchor="middle">
      <textPath href="#{path_id}" startOffset="50%">
        {safe_text}
      </textPath>
    </text>
  </svg>
</div>"""


def inject_text_fx_placeholders(html_content: str, primary: str = "var(--primary)", accent: str = "var(--accent)") -> str:
    """
    Scans HTML for <clair-curved-text text="..." curve="..." /> placeholders
    and substitutes them with responsive SVG textPath elements.
    Also ensures TEXT_FX_CSS and TEXT_FX_JS are embedded if effects are present.
    """
    def _replace_curved(match: re.Match) -> str:
        text = match.group(1).strip()
        curve = match.group(2).strip().lower() if match.group(2) else "wave"
        return render_curved_text(text, curve=curve, primary=primary, accent=accent)

    # 1. Match <clair-curved-text text="..." (curve="...")? />
    content = re.sub(
        r'<clair-curved-text\s+text=["\']([^"\']+)["\'](?:\s+curve=["\'](wave|arc)["\'])?\s*(?:/>|>\s*</clair-curved-text>)',
        _replace_curved,
        html_content,
        flags=re.IGNORECASE,
    )

    # 2. Match alternative attribute order: <clair-curved-text curve="..." text="..." />
    def _replace_curved_alt(match: re.Match) -> str:
        curve = match.group(1).strip().lower()
        text = match.group(2).strip()
        return render_curved_text(text, curve=curve, primary=primary, accent=accent)

    content = re.sub(
        r'<clair-curved-text\s+curve=["\'](wave|arc)["\']\s+text=["\']([^"\']+)["\']\s*(?:/>|>\s*</clair-curved-text>)',
        _replace_curved_alt,
        content,
        flags=re.IGNORECASE,
    )

    # 3. If charming, pretext-fit or curved-text are detected in the HTML, ensure CSS and JS are present
    has_fx = any(token in content for token in ["charming", "pretext-fit", "data-fx", "data-fit", "xsvg-curved-wrap"])

    if has_fx:
        # Inject CSS into </style> if not already present
        if "charWave" not in content and "</style>" in content:
            content = content.replace("</style>", f"{TEXT_FX_CSS}\n  </style>", 1)
        # Inject JS into </script> if not already present
        if "initCharmingTypography" not in content and "</script>" in content:
            content = content.replace("</script>", f"{TEXT_FX_JS}\n  </script>", 1)

    return content

