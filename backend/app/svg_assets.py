"""
Curated local SVG asset bank for cLAIr Pages.
Contains high-quality, self-contained SVG vectors inspired by:
- unDraw: Conceptual thematic didactic scenes with customizable dynamic tinting
- Haikei: Wave section dividers and organic background blobs
- Tabler Icons: Consistent stroke icons and educational pictograms

All assets are 100% autonomous, require 0 external network requests,
and dynamically adapt to the active CSS palette (var(--primary), var(--accent)).
"""

import html
import re
from functools import lru_cache
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "svg"

# 1. unDraw-style Thematic Illustrations
# Uses {primary} and {accent} placeholders that get replaced with CSS variables or hex colors.
THEMATIC_ILLUSTRATIONS: dict[str, dict[str, str]] = {
    "science_biology": {
        "title": "Science & Biologie",
        "category": "science",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="sci_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{primary}" stop-opacity="0.9" />
      <stop offset="100%" stop-color="{accent}" stop-opacity="0.8" />
    </linearGradient>
    <filter id="sci_shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-opacity="0.15" />
    </filter>
  </defs>
  <!-- Background organic blob -->
  <path d="M420,160 C440,240 360,290 280,285 C200,280 150,230 140,160 C130,90 200,45 280,50 C360,55 400,80 420,160 Z" fill="{primary}" opacity="0.1" />
  <!-- Microscope / Flask stand -->
  <path d="M120,270 L380,270" stroke="currentColor" stroke-width="4" stroke-linecap="round" opacity="0.3" />
  <rect x="220" y="240" width="60" height="30" rx="4" fill="currentColor" opacity="0.2" />
  <!-- Erlenmeyer Flask -->
  <path d="M250,110 L250,150 L190,240 L310,240 L250,150" stroke="{primary}" stroke-width="5" fill="none" stroke-linejoin="round" />
  <!-- Liquid in Flask -->
  <path d="M205,220 C230,210 270,230 295,220 L305,236 L195,236 Z" fill="url(#sci_grad)" />
  <!-- Bubbles -->
  <circle cx="245" cy="185" r="7" fill="{accent}" opacity="0.75" />
  <circle cx="260" cy="165" r="5" fill="{primary}" opacity="0.6" />
  <circle cx="240" cy="145" r="4" fill="{accent}" opacity="0.8" />
  <!-- Orbiting Atom / Molecule on Right -->
  <ellipse cx="370" cy="120" rx="45" ry="16" transform="rotate(-30 370 120)" stroke="{accent}" stroke-width="2.5" fill="none" stroke-dasharray="4 3" opacity="0.7" />
  <ellipse cx="370" cy="120" rx="45" ry="16" transform="rotate(30 370 120)" stroke="{primary}" stroke-width="2.5" fill="none" stroke-dasharray="4 3" opacity="0.7" />
  <circle cx="370" cy="120" r="12" fill="{primary}" />
  <circle cx="330" cy="105" r="6" fill="{accent}" />
  <circle cx="410" cy="135" r="6" fill="{accent}" />
  <!-- DNA Helix motif on Left -->
  <path d="M100,70 Q130,110 100,150 T100,230" stroke="{primary}" stroke-width="3" fill="none" opacity="0.5" />
  <path d="M130,70 Q100,110 130,150 T130,230" stroke="{accent}" stroke-width="3" fill="none" opacity="0.5" />
  <line x1="102" y1="90" x2="128" y2="90" stroke="currentColor" stroke-width="2" opacity="0.4" />
  <line x1="102" y1="130" x2="128" y2="130" stroke="currentColor" stroke-width="2" opacity="0.4" />
  <line x1="102" y1="170" x2="128" y2="170" stroke="currentColor" stroke-width="2" opacity="0.4" />
  <line x1="102" y1="210" x2="128" y2="210" stroke="currentColor" stroke-width="2" opacity="0.4" />
</svg>""",
    },
    "education_learning": {
        "title": "Éducation & Révision",
        "category": "education",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="edu_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{primary}" />
      <stop offset="100%" stop-color="{accent}" />
    </linearGradient>
  </defs>
  <!-- Background organic shape -->
  <path d="M100,180 C90,80 200,50 300,60 C400,70 440,150 420,230 C400,300 280,290 180,280 C120,270 105,230 100,180 Z" fill="{primary}" opacity="0.08" />
  <!-- Base Desk Line -->
  <path d="M80,270 L420,270" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" opacity="0.25" />
  <!-- Stack of Books -->
  <rect x="130" y="235" width="130" height="25" rx="4" fill="url(#edu_grad)" />
  <rect x="145" y="210" width="115" height="22" rx="4" fill="{accent}" opacity="0.85" />
  <rect x="135" y="188" width="120" height="20" rx="4" fill="{primary}" />
  <path d="M130,248 L150,248" stroke="#ffffff" stroke-width="3" stroke-linecap="round" opacity="0.7" />
  <!-- Open Large Book -->
  <path d="M250,140 Q310,120 370,140 L370,220 Q310,200 250,220 Z" fill="{primary}" opacity="0.2" />
  <path d="M250,140 Q190,120 130,140 L130,220 Q190,200 250,220 Z" fill="{primary}" opacity="0.15" />
  <path d="M250,135 L250,225" stroke="{primary}" stroke-width="3.5" />
  <!-- Graduation Cap floating -->
  <polygon points="340,65 410,95 340,120 270,95" fill="url(#edu_grad)" />
  <path d="M300,105 L300,135 Q340,155 380,135 L380,105" fill="{primary}" opacity="0.9" />
  <path d="M410,95 L425,145" stroke="{accent}" stroke-width="2.5" stroke-linecap="round" />
  <circle cx="425" cy="148" r="4" fill="{accent}" />
  <!-- Sparkles / Ideas -->
  <path d="M180,90 L185,100 L195,105 L185,110 L180,120 L175,110 L165,105 L175,100 Z" fill="{accent}" />
  <path d="M430,170 L433,178 L441,181 L433,184 L430,192 L427,184 L419,181 L427,178 Z" fill="{primary}" />
</svg>""",
    },
    "tech_coding": {
        "title": "Technologie & Code",
        "category": "tech",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="tech_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{primary}" />
      <stop offset="100%" stop-color="{accent}" />
    </linearGradient>
  </defs>
  <path d="M380,80 C440,120 450,230 380,270 C310,310 180,280 130,230 C80,180 110,90 190,60 C270,30 320,40 380,80 Z" fill="{primary}" opacity="0.08" />
  <!-- Desk Base -->
  <line x1="70" y1="275" x2="430" y2="275" stroke="currentColor" stroke-width="3" opacity="0.25" stroke-linecap="round" />
  <!-- Laptop Body -->
  <rect x="140" y="90" width="220" height="145" rx="8" fill="#1e293b" stroke="{primary}" stroke-width="3" />
  <path d="M110,235 L390,235 L370,250 L130,250 Z" fill="#334155" stroke="currentColor" stroke-width="2" opacity="0.5" />
  <!-- Code on Screen -->
  <circle cx="160" cy="110" r="4" fill="#ef4444" />
  <circle cx="172" cy="110" r="4" fill="#f59e0b" />
  <circle cx="184" cy="110" r="4" fill="#10b981" />
  <line x1="160" y1="130" x2="210" y2="130" stroke="{primary}" stroke-width="3" stroke-linecap="round" />
  <line x1="220" y1="130" x2="270" y2="130" stroke="{accent}" stroke-width="3" stroke-linecap="round" />
  <line x1="180" y1="145" x2="290" y2="145" stroke="#94a3b8" stroke-width="3" stroke-linecap="round" />
  <line x1="180" y1="160" x2="240" y2="160" stroke="{primary}" stroke-width="3" stroke-linecap="round" />
  <line x1="160" y1="175" x2="220" y2="175" stroke="{accent}" stroke-width="3" stroke-linecap="round" />
  <line x1="160" y1="190" x2="310" y2="190" stroke="url(#tech_grad)" stroke-width="3" stroke-linecap="round" />
  <!-- Floating Cloud / Server -->
  <path d="M370,110 C370,95 385,85 400,90 C410,75 435,75 445,90 C455,90 465,100 460,115 C460,125 450,130 435,130 L380,130 C370,130 370,120 370,110 Z" fill="{accent}" opacity="0.8" />
  <path d="M415,115 L415,135 M405,125 L415,135 L425,125" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
</svg>""",
    },
    "analytics_growth": {
        "title": "Analyse & Croissance",
        "category": "business",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="ana_grad" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="{primary}" stop-opacity="0.2" />
      <stop offset="100%" stop-color="{primary}" stop-opacity="0.8" />
    </linearGradient>
  </defs>
  <!-- Background Chart Grid -->
  <rect x="80" y="60" width="340" height="200" rx="10" fill="currentColor" opacity="0.04" />
  <line x1="110" y1="230" x2="390" y2="230" stroke="currentColor" stroke-width="2" opacity="0.3" />
  <line x1="110" y1="180" x2="390" y2="180" stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" opacity="0.2" />
  <line x1="110" y1="130" x2="390" y2="130" stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" opacity="0.2" />
  <!-- Bar charts -->
  <rect x="130" y="170" width="35" height="60" rx="4" fill="{primary}" opacity="0.4" />
  <rect x="185" y="140" width="35" height="90" rx="4" fill="{primary}" opacity="0.6" />
  <rect x="240" y="110" width="35" height="120" rx="4" fill="{primary}" opacity="0.8" />
  <rect x="295" y="80" width="35" height="150" rx="4" fill="url(#ana_grad)" />
  <!-- Growth Curve with Arrow -->
  <path d="M120,200 Q200,170 260,110 T380,60" stroke="{accent}" stroke-width="4.5" stroke-linecap="round" fill="none" />
  <polygon points="380,60 365,65 372,76" fill="{accent}" />
  <!-- Rocket Icon on Top -->
  <circle cx="380" cy="55" r="18" fill="{accent}" opacity="0.2" />
  <circle cx="380" cy="55" r="8" fill="{accent}" />
</svg>""",
    },
    "nature_ecology": {
        "title": "Environnement & Nature",
        "category": "nature",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="nat_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="100%" stop-color="{primary}" />
    </linearGradient>
  </defs>
  <!-- Background Sun / Halo -->
  <circle cx="250" cy="140" r="80" fill="{primary}" opacity="0.1" />
  <circle cx="340" cy="80" r="30" fill="{accent}" opacity="0.25" />
  <!-- Rolling Hills -->
  <path d="M60,260 Q160,200 270,240 T440,220 L440,270 L60,270 Z" fill="{primary}" opacity="0.2" />
  <path d="M90,270 Q200,220 310,250 T450,240 L450,270 L90,270 Z" fill="url(#nat_grad)" opacity="0.35" />
  <!-- Central Sprout / Plant -->
  <path d="M250,250 C250,180 250,150 250,120" stroke="#059669" stroke-width="4.5" stroke-linecap="round" />
  <!-- Leaves -->
  <path d="M250,180 C220,160 210,130 250,120 C250,150 240,170 250,180 Z" fill="#10b981" />
  <path d="M250,150 C280,130 290,100 250,90 C250,120 260,140 250,150 Z" fill="url(#nat_grad)" />
  <!-- Wind / Atmosphere Lines -->
  <path d="M120,100 Q180,80 220,100" stroke="{primary}" stroke-width="2.5" stroke-linecap="round" opacity="0.4" fill="none" />
  <path d="M280,70 Q340,60 380,80" stroke="{accent}" stroke-width="2.5" stroke-linecap="round" opacity="0.4" fill="none" />
</svg>""",
    },
    "ideas_brainstorm": {
        "title": "Idées & Créativité",
        "category": "creativity",
        "svg": """<svg viewBox="0 0 500 320" fill="none" xmlns="http://www.w3.org/2000/svg" class="clair-illustration" style="max-width: 100%; height: auto;">
  <defs>
    <linearGradient id="bulb_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="{primary}" />
    </linearGradient>
  </defs>
  <!-- Background Glow -->
  <circle cx="250" cy="140" r="95" fill="{primary}" opacity="0.12" />
  <!-- Central Lightbulb -->
  <path d="M220,195 L280,195 M225,210 L275,210 M235,225 L265,225" stroke="currentColor" stroke-width="4" stroke-linecap="round" opacity="0.6" />
  <path d="M220,195 C200,175 190,150 190,125 C190,90 215,65 250,65 C285,65 310,90 310,125 C310,150 300,175 280,195 Z" fill="url(#bulb_grad)" opacity="0.9" />
  <!-- Filament -->
  <path d="M235,130 Q250,105 265,130" stroke="#ffffff" stroke-width="4" stroke-linecap="round" fill="none" />
  <!-- Light Rays -->
  <line x1="250" y1="35" x2="250" y2="48" stroke="{accent}" stroke-width="4" stroke-linecap="round" />
  <line x1="170" y1="60" x2="180" y2="70" stroke="{accent}" stroke-width="4" stroke-linecap="round" />
  <line x1="330" y1="60" x2="320" y2="70" stroke="{accent}" stroke-width="4" stroke-linecap="round" />
  <line x1="140" y1="125" x2="155" y2="125" stroke="{primary}" stroke-width="4" stroke-linecap="round" />
  <line x1="360" y1="125" x2="345" y2="125" stroke="{primary}" stroke-width="4" stroke-linecap="round" />
  <!-- Thought nodes -->
  <circle cx="120" cy="200" r="14" fill="{primary}" opacity="0.7" />
  <circle cx="380" cy="210" r="16" fill="{accent}" opacity="0.7" />
  <path d="M135,195 Q180,180 205,175" stroke="{primary}" stroke-width="2" stroke-dasharray="4 4" opacity="0.5" fill="none" />
  <path d="M365,200 Q320,185 295,175" stroke="{accent}" stroke-width="2" stroke-dasharray="4 4" opacity="0.5" fill="none" />
</svg>""",
    },
}

# 2. Haikei-style Section Dividers and Blobs
SECTION_DIVIDERS: dict[str, str] = {
    "wave_smooth": """<div class="clair-divider no-print" style="overflow: hidden; line-height: 0; width: 100%; margin: 1.5rem 0;">
  <svg viewBox="0 0 1200 90" preserveAspectRatio="none" style="position: relative; display: block; width: 100%; height: 42px;">
    <path d="M0,0 C200,60 400,10 600,40 C800,70 1000,20 1200,45 L1200,90 L0,90 Z" fill="{primary}" opacity="0.15"></path>
    <path d="M0,25 C300,75 500,25 800,65 C1000,35 1100,55 1200,50 L1200,90 L0,90 Z" fill="{accent}" opacity="0.10"></path>
  </svg>
</div>""",
    "wave_layered": """<div class="clair-divider no-print" style="overflow: hidden; line-height: 0; width: 100%; margin: 1.5rem 0;">
  <svg viewBox="0 0 1200 80" preserveAspectRatio="none" style="position: relative; display: block; width: 100%; height: 38px;">
    <path d="M0,30 Q300,75 600,35 T1200,40 L1200,80 L0,80 Z" fill="{primary}" opacity="0.18"></path>
  </svg>
</div>""",
}

# 3. Tabler-style Educational & Interface Icons
TABLER_ICONS: dict[str, str] = {
    "bulb": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-7 7c0 3.03 1.8 5.64 4.38 6.74A1 1 0 0 0 10 16.7V18h4v-1.3a1 1 0 0 0 .62-.96C17.2 14.64 19 12.03 19 9a7 7 0 0 0-7-7z"/></svg>',
    "target": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    "shield": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    "atom": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><circle cx="12" cy="12" r="2"/><path d="M12 21a9 9 0 0 0 9-9 9 9 0 0 0-9-9 9 9 0 0 0-9 9 9 9 0 0 0 9 9z" opacity="0.3"/><ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(30 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-30 12 12)"/></svg>',
    "book": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    "chart": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    "check": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    "zap": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="clair-icon"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
}


@lru_cache(maxsize=4096)
def _load_cached_svg_file(relative_path: str) -> str | None:
    """Reads an SVG file from the local assets directory with LRU caching."""
    try:
        target_path = (ASSETS_DIR / relative_path).resolve()
        if not target_path.is_relative_to(ASSETS_DIR.resolve()) or not target_path.is_file():
            return None

        raw = target_path.read_text(encoding="utf-8").strip()
        # Clean XML declaration or comments if present
        raw = re.sub(r"<\?xml[^>]*\?>", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw, flags=re.IGNORECASE).strip()

        # Add responsive class and styles if missing
        if "tabler" in relative_path:
            if "class=" in raw:
                raw = raw.replace('class="', 'class="clair-icon ')
            else:
                raw = raw.replace("<svg", '<svg class="clair-icon" width="20" height="20"')
        elif "undraw" in relative_path:
            # Ensure undraw is responsive and adapt tint
            if "class=" in raw:
                raw = raw.replace('class="', 'class="clair-illustration ')
            else:
                raw = raw.replace("<svg", '<svg class="clair-illustration" style="max-width: 100%; height: auto;"')
            # Adapt default accent / current color to primary placeholder
            raw = re.sub(r'fill="#6c63ff"', 'fill="{primary}"', raw, flags=re.IGNORECASE)
            raw = re.sub(r'stroke="#6c63ff"', 'stroke="{primary}"', raw, flags=re.IGNORECASE)
            raw = re.sub(r'fill="currentColor"', 'fill="{primary}"', raw, flags=re.IGNORECASE)

        return raw
    except Exception:
        return None


def render_svg_asset(name: str, primary: str = "var(--primary)", accent: str = "var(--accent)") -> str | None:
    """
    Render an SVG asset either from:
    1. Built-in inline bank (quick curated set)
    2. Local file banks (tabler/..., undraw/..., or plain name lookup)
    Dynamically substitutes {primary} and {accent} palette variables.
    """
    key = name.strip().lower().replace(":", "/")

    # 1. Quick in-memory checks
    if key in THEMATIC_ILLUSTRATIONS:
        raw = THEMATIC_ILLUSTRATIONS[key]["svg"]
        return raw.replace("{primary}", primary).replace("{accent}", accent)

    if key in SECTION_DIVIDERS:
        raw = SECTION_DIVIDERS[key]
        return raw.replace("{primary}", primary).replace("{accent}", accent)

    if key in TABLER_ICONS:
        return TABLER_ICONS[key]

    # 2. Check on-disk local libraries (Tabler Icons & unDraw collections)
    if not ASSETS_DIR.exists():
        return None

    candidate_files = []
    if "/" in key:
        # Explicit bank prefix: tabler/cpu or undraw/science
        candidate_files.append(f"{key}.svg")
    else:
        # Search in tabler first, then undraw
        candidate_files.append(f"tabler/{key}.svg")
        candidate_files.append(f"undraw/{key}.svg")

    for rel_file in candidate_files:
        svg_content = _load_cached_svg_file(rel_file)
        if svg_content:
            return svg_content.replace("{primary}", primary).replace("{accent}", accent)

    return None


def inject_svg_placeholders(html_content: str, primary: str = "var(--primary)", accent: str = "var(--accent)") -> str:
    """
    Scans HTML for <clair-svg name="..."> tags or <!-- clair-svg: ... --> comments
    and replaces them with the actual inline SVG code tinted with dynamic palette variables.
    Supports names like:
    - science_biology
    - tabler/cpu
    - tabler:database
    - undraw/science
    - bulb
    """
    def _replace_tag(match: re.Match) -> str:
        asset_name = match.group(1).strip()
        rendered = render_svg_asset(asset_name, primary=primary, accent=accent)
        if rendered:
            return rendered
        return match.group(0)

    # 1. Match <clair-svg name="..."/> or <clair-svg name="..."></clair-svg>
    content = re.sub(
        r'<clair-svg\s+name=["\']([a-zA-Z0-9_\-:/]+)["\']\s*(?:/>|>\s*</clair-svg>)',
        _replace_tag,
        html_content,
        flags=re.IGNORECASE,
    )

    # 2. Match <!-- clair-svg: ... -->
    content = re.sub(
        r'<!--\s*clair-svg:\s*([a-zA-Z0-9_\-:/]+)\s*-->',
        _replace_tag,
        content,
        flags=re.IGNORECASE,
    )

    return content


def ensure_svg_assets(force: bool = False) -> tuple[int, int]:
    """
    Ensures local SVG libraries (Tabler Icons & unDraw) are downloaded and unpacked.
    Downloads from official public registries (registry.npmjs.org) using standard Python library.
    Returns (tabler_count, undraw_count).
    """
    import io
    import logging
    import tarfile
    import urllib.request

    logger = logging.getLogger("uvicorn.error")
    tabler_dir = ASSETS_DIR / "tabler"
    undraw_dir = ASSETS_DIR / "undraw"
    tabler_dir.mkdir(parents=True, exist_ok=True)
    undraw_dir.mkdir(parents=True, exist_ok=True)

    tabler_existing = list(tabler_dir.glob("*.svg"))
    undraw_existing = list(undraw_dir.glob("*.svg"))

    if not force and len(tabler_existing) > 1000 and len(undraw_existing) > 500:
        return len(tabler_existing), len(undraw_existing)

    # 0. Check for local pre-packaged offline zip archive (e.g. backend/app/assets/svg_assets.zip)
    zip_candidates = [
        ASSETS_DIR.parent / "svg_assets.zip",
        ASSETS_DIR / "svg_assets.zip",
        Path(__file__).resolve().parent.parent.parent / "scripts" / "assets" / "svg_assets.zip",
    ]
    for zip_path in zip_candidates:
        if zip_path.is_file():
            logger.info("Extraction de l'archive locale autonome %s...", zip_path.name)
            import zipfile
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(ASSETS_DIR)
                tabler_existing = list(tabler_dir.glob("*.svg"))
                undraw_existing = list(undraw_dir.glob("*.svg"))
                if len(tabler_existing) > 1000 and len(undraw_existing) > 500:
                    logger.info("Banques extraites depuis le zip avec succès (%d Tabler, %d unDraw).", len(tabler_existing), len(undraw_existing))
                    return len(tabler_existing), len(undraw_existing)
            except Exception as exc:
                logger.warning("Erreur extraction zip %s: %s", zip_path, exc)

    # 1. Tabler Icons (outline collection, ~5.2k icons)
    if force or len(tabler_existing) < 1000:
        logger.info("Téléchargement de la bibliothèque Tabler Icons en local...")
        url = "https://registry.npmjs.org/@tabler/icons/-/icons-3.50.0.tgz"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cLAIr-Setup"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.startswith("package/icons/outline/") and member.name.endswith(".svg"):
                        filename = Path(member.name).name
                        f = tar.extractfile(member)
                        if f:
                            (tabler_dir / filename).write_bytes(f.read())
            logger.info("Tabler Icons installé avec succès.")
        except Exception as exc:
            logger.warning("Impossible de télécharger Tabler Icons (%s); fallback en mémoire actif.", exc)

    # 2. unDraw Illustrations (~1.7k scenes)
    if force or len(undraw_existing) < 500:
        logger.info("Téléchargement de la bibliothèque unDraw en local...")
        url = "https://registry.npmjs.org/undraw-svg/-/undraw-svg-2.0.0.tgz"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cLAIr-Setup"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.startswith("package/svgs/") and member.name.endswith(".svg"):
                        filename = Path(member.name).name
                        f = tar.extractfile(member)
                        if f:
                            (undraw_dir / filename).write_bytes(f.read())
            logger.info("unDraw installé avec succès.")
        except Exception as exc:
            logger.warning("Impossible de télécharger unDraw (%s); fallback en mémoire actif.", exc)

    return len(list(tabler_dir.glob("*.svg"))), len(list(undraw_dir.glob("*.svg")))


if __name__ == "__main__":
    import sys
    print("Vérification et installation des banques SVG...")
    t_cnt, u_cnt = ensure_svg_assets(force="--force" in sys.argv)
    print(f"Prêt : {t_cnt} icônes Tabler et {u_cnt} illustrations unDraw disponibles.")


