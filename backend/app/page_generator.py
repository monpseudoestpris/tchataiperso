import html
import logging
import re
import secrets
import unicodedata
from typing import Any

import httpx

from .config import Settings
from .providers import ProviderError, _check_response, _json, _key
from .svg_assets import inject_svg_placeholders, render_svg_asset

_logger = logging.getLogger("uvicorn.error")

_TIMEOUT = httpx.Timeout(90.0, connect=10.0, pool=10.0)


def short_token() -> str:
    """Generate a URL-safe unguessable token for public sharing."""
    return secrets.token_urlsafe(12)


def slugify(value: str) -> str:
    """Generate a clean URL slug from a title."""
    normalized = unicodedata.normalize("NFKD", value)
    cleaned = "".join(c for c in normalized if not unicodedata.combining(c)).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned[:60] or "page-web"


def extract_html(raw: str) -> str:
    """Extract full HTML document from LLM output, stripping markdown fencing if present."""
    text = raw.strip()

    # Search for markdown fenced block containing HTML document
    code_block = re.search(r"```(?:html)?\s*(<!DOCTYPE[\s\S]*?</html>)\s*```", text, re.IGNORECASE)
    if code_block:
        return code_block.group(1).strip()

    # Direct <!DOCTYPE html> ... </html>
    full_doc = re.search(r"(<!DOCTYPE[\s\S]*?</html>)", text, re.IGNORECASE)
    if full_doc:
        return full_doc.group(1).strip()

    # <html ... </html>
    html_tag = re.search(r"(<html[\s\S]*?</html>)", text, re.IGNORECASE)
    if html_tag:
        return f"<!DOCTYPE html>\n{html_tag.group(1).strip()}"

    # If already starting with doctype
    if text.lower().startswith("<!doctype html"):
        return text

    return text


def extract_title_from_html(html_code: str, fallback: str = "Page Web") -> str:
    """Extract <title>...</title> content from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_code, re.IGNORECASE | re.DOTALL)
    if match:
        title = html.unescape(match.group(1).strip())
        if title:
            # Clean possible suffix like " - cLAIr" or " | cLAIr Pages"
            cleaned = re.sub(r"\s*[-|]\s*cLAIr.*$", "", title, flags=re.IGNORECASE).strip()
            return cleaned or title
    # Fallback to first h1
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_code, re.IGNORECASE | re.DOTALL)
    if h1_match:
        stripped = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
        if stripped:
            return html.unescape(stripped[:100])
    return fallback[:100]


PAGE_SYSTEM_PROMPT = """Tu es un concepteur et développeur web expert en création de pages web didactiques, modernes et entièrement autonomes.
Ton objectif est de générer un document web unique (HTML5 + CSS3 + SVG inline + JavaScript vanilla) sur le sujet demandé par l'utilisateur.

RÈGLES D'OR ABSOLUES D'AUTONOMIE (TRÈS STRICT) :
1. FICHIER UNIQUE : Tout doit être dans un seul document HTML5 : <!DOCTYPE html><html lang="fr"><head>...<style>...</style></head><body>...<script>...</script></body></html>.
2. ZÉRO DÉPENDANCE EXTERNE :
   - Strictement AUCUN <link href="http..."> (pas de Google Fonts, pas de Tailwind CDN, pas de Bootstrap).
   - Strictement AUCUN <script src="http..."> (pas de React, pas de jQuery, pas de bibliothèques tierces).
   - Strictement AUCUNE image externe <img src="http...">.
   - Utilise EXCLUSIVEMENT les polices système via un system-ui stack moderne :
     font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
     (ou Serif / Monospace selon le style demandé).
3. DÉTECTION INTELLIGENTE DES COMPOSANTS (N'ajoute que ce qui apporte une réelle valeur didactique) :
   Analyse le sujet et insère prioritairement les éléments pertinents :
   - Événements historiques ou chronologiques -> Frise chronologique SVG soignée.
   - Comparaison de notions, produits ou thèses -> Cartes comparatives côte à côte, tableau récapitulatif.
   - Sujet scientifique, biologique ou technique -> Schéma conceptuel SVG explicatif légendé, voire simulation interactive.
   - Démarche par étapes ou tutoriel -> Timeline d'étapes numérotées, blocs de code ou points de vigilance.
   - Données chiffrées ou statistiques -> Graphique vectoriel SVG (barres, courbes, anneaux) ou métriques clés en grands chiffres.
   - Révisions scolaires ou pédagogie active -> Encadrés "À retenir", définitions clés, mini-quiz interactif immédiat.
   - Vulgarisation ou essai -> Citations marquantes, encadrés "Le saviez-vous ?", analogies visuelles.
   Ne force jamais de composants superflus si le sujet ne s'y prête pas.
4. ILLUSTRATIONS, GRAPHISME ET ICÔNES EN SVG INLINE (Banques locales : Tabler Icons + unDraw + Haikei) :
   - IMMENSE BANQUE LOCALE AUTONOME INTÉGRÉE (Zéro externe, +7 000 ressources disponibles) :
     Pour une qualité graphique irréprochable et un rendu instantané, tu peux insérer des balises autonomes <clair-svg name="..." /> substituées automatiquement par le code SVG avec harmonisation de la palette CSS active :
     * Plus de 5 000 icônes didactiques & techniques Tabler Icons (trait fin 2px, stroke="currentColor") :
       Exemples : <clair-svg name="tabler/cpu" />, <clair-svg name="tabler/database" />, <clair-svg name="tabler/calendar" />, <clair-svg name="tabler/flask" />, <clair-svg name="tabler/chart-line" />, <clair-svg name="tabler/device-laptop" />, <clair-svg name="tabler/dna" />, <clair-svg name="tabler/brain" />, etc. (ou raccourcis : <clair-svg name="bulb" />, <clair-svg name="atom" />, <clair-svg name="shield" />, <clair-svg name="book" />, <clair-svg name="zap" />, <clair-svg name="check" />, etc.).
     * Plus de 1 700 scènes conceptuelles unDraw (illustrations thématiques complètes adaptées aux couleurs var(--primary)) :
       Exemples : <clair-svg name="undraw/science" />, <clair-svg name="undraw/education" />, <clair-svg name="undraw/developer-activity" />, <clair-svg name="undraw/data-report" />, <clair-svg name="undraw/mindfulness" />, <clair-svg name="undraw/studying" />, etc. (ou raccourcis thématiques : <clair-svg name="science_biology" />, <clair-svg name="education_learning" />, <clair-svg name="tech_coding" />, <clair-svg name="analytics_growth" />, <clair-svg name="nature_ecology" />, <clair-svg name="ideas_brainstorm" />).
     * Séparateurs de vagues fluides (style Haikei) :
       - <clair-svg name="wave_smooth" /> ou <clair-svg name="wave_layered" /> : transitions douces entre les blocs ou sous l'en-tête hero.
   - CRÉATION SUR-MESURE : Tu peux également dessiner tes propres diagrammes SVG inline spécifiques au sujet (ex: frise chronologique historique avec repères d'années, schéma anatomique ou circuit logique) en respectant les bonnes pratiques SVG responsive (width="100%", height="auto", viewBox).
   - Rends tous les SVG responsive, modernes, sans dépendance externe et sans pixellisation.
5. CSS3 MODERNE ET RESPONSIVE :
   - Définis des variables CSS dans :root pour les couleurs, rayons de courbure, ombres.
   - Prise en charge du thème clair et du thème sombre (via prefers-color-scheme ou un sélecteur [data-theme="dark"]).
   - Mise en page aérée : Flexbox, Grid, cartes (cards) élégantes, badges colorés, typographie hiérarchisée.
   - Transitions fluides au survol (hover) et animations douces (@keyframes).
6. INTERACTIVITÉ VANILLA ÉLÉGANTE DANS <script> :
   - Inclus des composants interactifs pertinents pour le sujet lorsque l'interactivité est activée :
     * Bouton bascule de thème Clair / Sombre.
     * Système d'onglets pour explorer différents aspects du sujet.
     * Accordéons interactifs pour les détails et questions fréquentes.
     * Quiz interactif ou simulation/calculateur interactif avec curseurs <input type="range"> selon le sujet.
     * Bouton "Copier le résumé" ou calcul de score immédiat.
   - Le JavaScript doit être propre, robuste, sans erreur console et sans bibliothèque externe.
7. FORMAT DE SORTIE :
   - Retourne UNIQUEMENT le document HTML5 complet, sans texte d'introduction ni de conclusion, sans backticks markdown si possible.
"""

REFINE_SYSTEM_PROMPT = """Tu es un expert web perfectionnant une page HTML5 autonome existante.
Tu reçois le code HTML complet actuel d'une page et une consigne d'amélioration demandée par l'utilisateur.

RÈGLES IMPÉRATIVES :
1. Applique fidèlement les demandes (modification de contenu, ajout/modification de graphiques SVG, changement de palette CSS, ajout de quiz ou d'interactions JS, etc.).
2. Conserve impérativement le caractère AUTONOME du document :
   - Strictement aucune ressource externe (pas de polices CDN, pas de scripts externes, pas d'images distantes).
   - Tout le CSS dans <style>, tout le JS dans <script>, illustrations en SVG inline.
3. Conserve la cohérence globale de la page et les interactions existantes non concernées par la demande.
4. Retourne UNIQUEMENT le document HTML5 complet mis à jour.
"""


PALETTES = {
    "ocean": {"primary": "#38bdf8", "primary_light": "#0284c7", "accent": "#a855f7"},
    "emerald": {"primary": "#34d399", "primary_light": "#059669", "accent": "#06b6d4"},
    "sunset": {"primary": "#fb923c", "primary_light": "#ea580c", "accent": "#f43f5e"},
    "violet": {"primary": "#c084fc", "primary_light": "#7c3aed", "accent": "#ec4899"},
    "slate": {"primary": "#94a3b8", "primary_light": "#475569", "accent": "#38bdf8"},
}

VISUAL_STYLES: dict[str, dict[str, str]] = {
    "modern_clean": {
        "name": "Moderne Épuré",
        "icon": "✨",
        "description": "Style SaaS contemporain, cartes blanches, ombres douces et bordures fines.",
        "font": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "radius": "12px",
        "border_light": "1px solid #e2e8f0",
        "border_dark": "1px solid #334155",
        "shadow": "0 4px 20px -2px rgba(0, 0, 0, 0.08)",
        "prompt_directive": "STYLE MODERNE & ÉPURÉ : Interface claire et professionnelle, cartes blanches aux ombres douces et diffuses, bordures fines 1px, typographie sans-serif contemporaine (system-ui), badges discrets.",
    },
    "neobrutalism": {
        "name": "Néobrutalisme Pop",
        "icon": "⚡",
        "description": "Bordures noires épaisses (2.5px), ombres franches décalées sans flou, couleurs vives.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "6px",
        "border_light": "2.5px solid #111827",
        "border_dark": "2.5px solid #f8fafc",
        "shadow": "4px 4px 0px #111827",
        "prompt_directive": "STYLE NÉOBRUTALISME POP : Bordures noires épaisses (2.5px solid #111), ombres franches décalées sans flou (ex: box-shadow: 4px 4px 0 #111), couleurs pop et contrastées, pastilles aux coins nets, boutons très lisibles.",
    },
    "glassmorphism": {
        "name": "Glassmorphism & Glow",
        "icon": "💎",
        "description": "Cartes translucides avec verre dépoli, reflets lumineux et dégradés d'arrière-plan.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "16px",
        "border_light": "1px solid rgba(255, 255, 255, 0.35)",
        "border_dark": "1px solid rgba(255, 255, 255, 0.12)",
        "shadow": "0 8px 32px 0 rgba(0, 0, 0, 0.25)",
        "prompt_directive": "STYLE GLASSMORPHISM : Cartes translucides avec effet verre dépoli (backdrop-filter: blur(14px); background: rgba(255,255,255,0.12);), bordures lumineuses semi-transparentes, dégradés d'arrière-plan riches et diffus.",
    },
    "notebook": {
        "name": "Cahier d'écolier & Fiches",
        "icon": "📓",
        "description": "Fond papier quadrillé/ligné, surlignages stabilo, post-it de synthèse et fiches de révision.",
        "font": "'Segoe UI', -apple-system, system-ui, cursive, sans-serif",
        "radius": "8px",
        "border_light": "1px dashed #cbd5e1",
        "border_dark": "1px dashed #475569",
        "shadow": "0 2px 8px rgba(0, 0, 0, 0.06)",
        "prompt_directive": "STYLE CAHIER D'ÉCOLIER : Ambiance prise de notes et fiches bristol : fond papier réglé/quadrillé discret, titres surlignés au feutre fluo (effet stabilo), cartes type post-it avec punaise ou trombone SVG.",
    },
    "cyberpunk": {
        "name": "Cyberpunk & Terminal",
        "icon": "🔮",
        "description": "Fond sombre OLED, néons cyan/magenta éclatants, typographie monospace futuriste.",
        "font": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        "radius": "4px",
        "border_light": "1px solid #0284c7",
        "border_dark": "1px solid #38bdf8",
        "shadow": "0 0 16px rgba(56, 189, 248, 0.35)",
        "prompt_directive": "STYLE CYBERPUNK & TERMINAL : Fond noir spatial/OLED (#0a0b14), accents néon cyan éclatant (#00f0ff) et magenta (#ff007f), typographie monospace pour les badges et chiffres, bordures luminescentes avec halos glow.",
    },
    "editorial_newspaper": {
        "name": "Journal & Presse Éditoriale",
        "icon": "📰",
        "description": "Typographie Serif prestigieuse (Georgia/Garamond), mise en colonnes, lettrines et filets.",
        "font": "Georgia, Cambria, 'Times New Roman', serif",
        "radius": "2px",
        "border_light": "1px solid #d4c5b9",
        "border_dark": "1px solid #44403c",
        "shadow": "0 1px 4px rgba(0, 0, 0, 0.05)",
        "prompt_directive": "STYLE JOURNAL & ÉDITORIAL ANCIEN : Typographie à empattement digne des grands journaux (Georgia, Garamond, serif), lettrines majuscules en début de partie, filets horizontaux doubles, ton papier ivoire/sépia raffiné.",
    },
    "pastel_infographic": {
        "name": "Infographie Pastel Didactique",
        "icon": "🎨",
        "description": "Teintes douces (pêche, menthe, lavande), grands angles arrondis et chiffres géants.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "20px",
        "border_light": "1px solid #e0e7ff",
        "border_dark": "1px solid #312e81",
        "shadow": "0 6px 16px rgba(99, 102, 241, 0.08)",
        "prompt_directive": "STYLE INFOGRAPHIE PASTEL : Couleurs douces (menthe, pêche, lilas, vanille), grands blocs arrondis (border-radius: 20px), chiffres clés géants en médaillons, format magazine de vulgarisation scientifique.",
    },
    "minimal_mono": {
        "name": "Minimaliste Suisse & Mono",
        "icon": "📐",
        "description": "Noir, blanc et gris neutre, grille suisse stricte, géométrie pure et zéro distraction.",
        "font": "'Helvetica Neue', Helvetica, Arial, sans-serif",
        "radius": "0px",
        "border_light": "1px solid #0f172a",
        "border_dark": "1px solid #f8fafc",
        "shadow": "none",
        "prompt_directive": "STYLE MINIMALISTE SUISSE : Noir et blanc pur avec nuances de gris neutre, aucune ombre inutile, grille géométrique impeccable, typographie Helvetica puissante et espacements très généreux.",
    },
    "synthwave_retro": {
        "name": "Rétro 80s Synthwave",
        "icon": "🌆",
        "description": "Coucher de soleil violet/fuchsia, perspective filaire en arrière-plan, néons chauds.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "8px",
        "border_light": "1px solid #ec4899",
        "border_dark": "1px solid #f43f5e",
        "shadow": "0 0 20px rgba(236, 72, 153, 0.35)",
        "prompt_directive": "STYLE RÉTRO 80s & SYNTHWAVE : Teintes néon coucher de soleil (violet, rose fuchsia, orange ambré), arrière-plan sombre avec grille filaire, titres stylisés rétro-futuristes et touches d'ambre.",
    },
    "nature_botanic": {
        "name": "Nature & Botanique",
        "icon": "🌿",
        "description": "Vert sauge, lin naturel, teintes terreuses, ambiance herbier et carnet naturaliste.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "14px",
        "border_light": "1px solid #cbd5be",
        "border_dark": "1px solid #3f4e38",
        "shadow": "0 4px 12px rgba(46, 78, 40, 0.08)",
        "prompt_directive": "STYLE NATURE & BOTANIQUE : Palette terreuse et végétale (vert sauge, mousse, beige lin, argile), cartes façon herbier avec coins arrondis et textures douces, schémas végétaux ou naturalistes.",
    },
    "playful_cartoon": {
        "name": "BD & Cartoon Illustré",
        "icon": "🎈",
        "description": "Bulles de texte façon BD, contrastes joyeux, badges expressifs et dynamisme visuel.",
        "font": "system-ui, -apple-system, sans-serif",
        "radius": "18px",
        "border_light": "2px solid #0284c7",
        "border_dark": "2px solid #38bdf8",
        "shadow": "3px 3px 0px rgba(2, 132, 199, 0.3)",
        "prompt_directive": "STYLE BD & CARTOON : Éléments façon bande dessinée, bulles de dialogue expressives, bordures rondes bien définies (radius 18px), contrastes joyeux et touches ludiques.",
    },
}


def generate_fallback_page(
    title: str,
    topic: str,
    layout_style: str = "tabs",
    text_density: int = 5,
    include_quiz: bool = True,
    include_svg: bool = True,
    theme_palette: str = "ocean",
    visual_style: str = "modern_clean",
    orientation: str = "portrait",
    creative_freedom: str = "medium",
) -> str:
    """Generate a rich, responsive, completely self-contained fallback HTML page with custom options."""
    safe_title = html.escape(title or "cLAIr Pages — Guide interactif")
    safe_topic = html.escape(topic or "Présentation et synthèse interactive")

    palette = PALETTES.get(theme_palette, PALETTES["ocean"])
    dark_primary = palette["primary"]
    light_primary = palette["primary_light"]
    accent = palette["accent"]

    vstyle = VISUAL_STYLES.get(visual_style, VISUAL_STYLES["modern_clean"])
    font_family = vstyle["font"]
    border_radius = vstyle["radius"]
    box_shadow = vstyle["shadow"]
    border_light = vstyle["border_light"]
    border_dark = vstyle["border_dark"]

    is_print = layout_style == "print_sheet"
    container_max_w = "1280px" if orientation == "landscape" else "960px"

    svg_section = ""
    if include_svg:
        svg_section = f"""
    <!-- Didactic SVG Diagram -->
    <div class="diagram-card">
      <h3 style="margin-bottom: 1rem; color: var(--primary);">Schéma conceptuel interactif</h3>
      <svg viewBox="0 0 800 240" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="{dark_primary}" />
            <stop offset="100%" stop-color="{light_primary}" />
          </linearGradient>
          <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="{accent}" />
            <stop offset="100%" stop-color="#7e22ce" />
          </linearGradient>
          <linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#10b981" />
            <stop offset="100%" stop-color="#047857" />
          </linearGradient>
          <filter id="shadow" x="-5%" y="-10%" width="110%" height="130%">
            <feDropShadow dx="0" dy="4" stdDeviation="6" flood-opacity="0.25" />
          </filter>
        </defs>
        <g filter="url(#shadow)">
          <rect x="40" y="60" width="200" height="120" rx="14" fill="url(#g1)" />
          <text x="140" y="115" fill="#ffffff" font-size="16" font-weight="700" text-anchor="middle" font-family="system-ui">1. Exploration</text>
          <text x="140" y="140" fill="rgba(255,255,255,0.85)" font-size="12" text-anchor="middle" font-family="system-ui">Compréhension globale</text>
        </g>
        <path d="M 240 120 L 300 120" stroke="var(--primary)" stroke-width="3" stroke-dasharray="6 4" />
        <polygon points="300,120 290,114 290,126" fill="var(--primary)" />
        <g filter="url(#shadow)">
          <rect x="300" y="60" width="200" height="120" rx="14" fill="url(#g2)" />
          <text x="400" y="115" fill="#ffffff" font-size="16" font-weight="700" text-anchor="middle" font-family="system-ui">2. Synthèse</text>
          <text x="400" y="140" fill="rgba(255,255,255,0.85)" font-size="12" text-anchor="middle" font-family="system-ui">Mise en perspective</text>
        </g>
        <path d="M 500 120 L 560 120" stroke="var(--accent)" stroke-width="3" stroke-dasharray="6 4" />
        <polygon points="560,120 550,114 550,126" fill="var(--accent)" />
        <g filter="url(#shadow)">
          <rect x="560" y="60" width="200" height="120" rx="14" fill="url(#g3)" />
          <text x="660" y="115" fill="#ffffff" font-size="16" font-weight="700" text-anchor="middle" font-family="system-ui">3. Maîtrise</text>
          <text x="660" y="140" fill="rgba(255,255,255,0.85)" font-size="12" text-anchor="middle" font-family="system-ui">Validation & Quiz</text>
        </g>
      </svg>
    </div>
"""

    quiz_section = ""
    if include_quiz:
        quiz_section = """
    <!-- Interactive Quiz -->
    <div class="quiz-box no-print">
      <div class="quiz-question">🎯 Mini-Quiz de vérification : Quelle est la particularité d'un document HTML autonome ?</div>
      <div class="quiz-options">
        <button class="quiz-option" data-correct="false">Il nécessite une connexion à Internet pour charger des polices externes.</button>
        <button class="quiz-option" data-correct="true">Il intègre tout son CSS, JS et SVG et s'ouvre hors-ligne sur n'importe quel appareil.</button>
        <button class="quiz-option" data-correct="false">Il doit impérativement être compilé avec un outil de build comme Webpack.</button>
      </div>
      <div class="quiz-feedback" id="quizFeedback"></div>
    </div>
"""

    print_badge = '<span class="brand-badge" style="background:rgba(234,88,12,0.15);color:#ea580c;">Format Fiche Impression A4</span>' if is_print else '<span class="brand-badge">Autonome & Hors-ligne</span>'

    full_page = f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --surface: #1e293b;
      --surface-hover: #334155;
      --border: {border_dark};
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: {dark_primary};
      --primary-hover: {light_primary};
      --primary-rgb: 56, 189, 248;
      --accent: {accent};
      --success: #10b981;
      --warning: #f59e0b;
      --radius: {border_radius};
      --shadow: {box_shadow};
      --font: {font_family};
    }}
    [data-theme="light"] {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-hover: #f1f5f9;
      --border: {border_light};
      --text: #0f172a;
      --text-muted: #64748b;
      --primary: {light_primary};
      --primary-hover: {dark_primary};
      --primary-rgb: 2, 132, 199;
      --accent: {accent};
      --success: #059669;
      --warning: #d97706;
      --shadow: {box_shadow};
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: var(--font);
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      transition: background-color 0.25s ease, color 0.25s ease;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1rem 1.5rem;
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(8px);
    }}
    .nav-container {{
      max-width: {container_max_w};
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-weight: 700;
      font-size: 1.1rem;
      color: var(--primary);
    }}
    .brand-badge {{
      font-size: 0.72rem;
      background: rgba(2, 132, 199, 0.15);
      color: var(--primary);
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      font-weight: 600;
    }}
    .actions-row {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .action-btn {{
      background: var(--surface-hover);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.45rem 0.8rem;
      border-radius: 8px;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.8rem;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s;
    }}
    .action-btn:hover {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}
    main {{
      max-width: {container_max_w};
      margin: 0 auto;
      padding: 2rem 1.25rem;
      flex: 1;
      width: 100%;
    }}
    .hero {{
      text-align: center;
      padding: 1rem 0 2rem;
    }}
    .hero h1 {{
      font-size: 2.2rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      margin-bottom: 0.6rem;
      background: linear-gradient(135deg, var(--primary), var(--accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .hero p {{
      font-size: 1.05rem;
      color: var(--text-muted);
      max-width: 650px;
      margin: 0 auto;
    }}
    .diagram-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem;
      margin-bottom: 2rem;
      box-shadow: var(--shadow);
      text-align: center;
    }}
    .diagram-card svg {{
      max-width: 100%;
      height: auto;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem;
      box-shadow: var(--shadow);
    }}
    .card h3 {{
      font-size: 1.1rem;
      margin-bottom: 0.5rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      color: var(--primary);
    }}
    .tabs {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      margin-bottom: 2rem;
      box-shadow: var(--shadow);
    }}
    .tab-header {{
      display: flex;
      border-bottom: 1px solid var(--border);
      background: var(--surface-hover);
    }}
    .tab-btn {{
      padding: 0.75rem 1.25rem;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-family: inherit;
      font-weight: 600;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }}
    .tab-btn.active {{
      color: var(--primary);
      border-bottom-color: var(--primary);
      background: var(--surface);
    }}
    .tab-content {{
      padding: 1.5rem;
      display: none;
    }}
    .tab-content.active {{
      display: block;
    }}
    .quiz-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.5rem;
      margin-bottom: 2rem;
      box-shadow: var(--shadow);
    }}
    .quiz-question {{
      font-weight: 600;
      margin-bottom: 0.85rem;
      font-size: 1rem;
    }}
    .quiz-options {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-bottom: 0.85rem;
    }}
    .quiz-option {{
      padding: 0.65rem 0.85rem;
      background: var(--surface-hover);
      border: 1px solid var(--border);
      border-radius: 8px;
      cursor: pointer;
      text-align: left;
      font-family: inherit;
      color: var(--text);
      transition: all 0.2s;
    }}
    .quiz-option:hover {{
      border-color: var(--primary);
    }}
    .quiz-option.correct {{
      background: rgba(16, 185, 129, 0.2);
      border-color: var(--success);
      color: var(--success);
      font-weight: 600;
    }}
    .quiz-option.incorrect {{
      background: rgba(239, 68, 68, 0.2);
      border-color: #ef4444;
      color: #ef4444;
    }}
    .quiz-feedback {{
      font-size: 0.9rem;
      min-height: 1.25rem;
      font-weight: 500;
    }}
    footer {{
      border-top: 1px solid var(--border);
      background: var(--surface);
      padding: 1.25rem;
      text-align: center;
      color: var(--text-muted);
      font-size: 0.8rem;
    }}
    @media print {{
      @page {{
        margin: 1cm;
        size: A4;
      }}
      body {{
        background: #ffffff !important;
        color: #0f172a !important;
      }}
      .no-print, header, footer {{
        display: none !important;
      }}
      main {{
        max-width: 100% !important;
        padding: 0 !important;
      }}
      .card, .diagram-card, .tabs {{
        box-shadow: none !important;
        border: 1px solid #cbd5e1 !important;
        break-inside: avoid;
      }}
      .tab-content {{
        display: block !important;
        padding: 0.75rem 0 !important;
      }}
      .tab-header {{
        display: none !important;
      }}
    }}
  </style>
</head>
<body>
  <header class="no-print">
    <div class="nav-container">
      <div class="brand">
        <span>cLAIr Pages</span>
        {print_badge}
      </div>
      <div class="actions-row">
        {f'<button class="action-btn" onclick="window.print()" title="Imprimer la fiche A4">🖨️ Imprimer</button>' if is_print else ''}
        <button class="action-btn" id="themeBtn" aria-label="Changer de thème">
          <span id="themeIcon">☀️</span> Thème
        </button>
      </div>
    </div>
  </header>

  <main>
    <section class="hero">
      <h1>{safe_title}</h1>
      <p>{safe_topic}</p>
    </section>

    <!-- Haikei-inspired organic wave transition -->
    <div style="margin: -0.5rem auto 1.5rem; max-width: 100%; overflow: hidden; opacity: 0.65;" class="no-print">
      <svg viewBox="0 0 1200 48" fill="none" xmlns="http://www.w3.org/2000/svg" style="width: 100%; height: 28px; display: block;">
        <path d="M0,20 C180,45 360,5 540,25 C720,45 900,10 1080,30 L1200,20 L1200,48 L0,48 Z" fill="var(--primary)" opacity="0.18" />
        <path d="M0,28 C200,8 400,38 600,18 C800,40 1000,15 1200,25 L1200,48 L0,48 Z" fill="var(--accent)" opacity="0.12" />
      </svg>
    </div>

    {svg_section}

    <!-- Cards Grid with Tabler-inspired SVG Icons -->
    <div class="grid-2">
      <div class="card">
        <h3>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-7 7c0 3.03 1.8 5.64 4.38 6.74A1 1 0 0 0 10 16.7V18h4v-1.3a1 1 0 0 0 .62-.96C17.2 14.64 19 12.03 19 9a7 7 0 0 0-7-7z"/></svg>
          <span>Clé de voûte</span>
        </h3>
        <p>Ce document est 100 % autonome : tout le code CSS, JavaScript et les illustrations vectorielles SVG sont incorporés sans aucune ressource externe.</p>
      </div>
      <div class="card">
        <h3>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
          <span>Réactivité & fluidité</span>
        </h3>
        <p>Le document s'adapte immédiatement à votre taille d'écran, vos préférences de contraste et fonctionne intégralement hors ligne.</p>
      </div>
    </div>

    <!-- Content Sections -->
    <div class="tabs">
      <div class="tab-header">
        <button class="tab-btn active" data-tab="tab-1">Aperçu didactique</button>
        <button class="tab-btn" data-tab="tab-2">Méthodologie</button>
        <button class="tab-btn" data-tab="tab-3">À retenir</button>
      </div>
      <div class="tab-content active" id="tab-1">
        <h4 style="margin-bottom: 0.5rem; color: var(--primary);">Fondements du sujet</h4>
        <p>Une approche structurée permet de décomposer des concepts complexes en unités élémentaires intuitives. En combinant texte, supports visuels et interactivité, la mémorisation est renforcée.</p>
      </div>
      <div class="tab-content" id="tab-2">
        <h4 style="margin-bottom: 0.5rem; color: var(--primary);">Démarche active</h4>
        <p>L'interaction active avec des curseurs, des questions de validation et des schémas dynamiques renforce l'ancrage mémoriel bien au-delà de la simple lecture passive.</p>
      </div>
      <div class="tab-content" id="tab-3">
        <h4 style="margin-bottom: 0.5rem; color: var(--primary);">Points cardinaux</h4>
        <ul style="padding-left: 1.5rem; display: flex; flex-direction: column; gap: 0.3rem;">
          <li>Fichier autonome conservable à vie au format standard HTML5.</li>
          <li>Portabilité universelle sur smartphone, tablette ou ordinateur.</li>
          <li>Zéro serveur requis pour l'exécution et la consultation.</li>
        </ul>
      </div>
    </div>

    {quiz_section}
  </main>

  <footer class="no-print">
    Document généré par <strong>cLAIr Pages</strong> — Moteur web autonome sans dépendance.
  </footer>

  <script>
    const themeBtn = document.getElementById('themeBtn');
    const themeIcon = document.getElementById('themeIcon');
    let currentTheme = 'dark';

    if (themeBtn) {{
      themeBtn.addEventListener('click', () => {{
        currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', currentTheme);
        themeIcon.textContent = currentTheme === 'dark' ? '☀️' : '🌙';
      }});
    }}

    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        const target = document.getElementById(btn.dataset.tab);
        if (target) target.classList.add('active');
      }});
    }});

    const feedback = document.getElementById('quizFeedback');
    document.querySelectorAll('.quiz-option').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const isCorrect = btn.dataset.correct === 'true';
        document.querySelectorAll('.quiz-option').forEach(b => {{
          b.disabled = true;
          if (b.dataset.correct === 'true') b.classList.add('correct');
        }});
        if (isCorrect) {{
          btn.classList.add('correct');
          if (feedback) {{
            feedback.textContent = '🎉 Exact ! Aucun serveur ni dépendance externe n\\'est requis.';
            feedback.style.color = 'var(--success)';
          }}
        }} else {{
          btn.classList.add('incorrect');
          if (feedback) {{
            feedback.textContent = '❌ Pas tout à fait. La bonne réponse était l\\'intégration totale en fichier unique.';
            feedback.style.color = '#ef4444';
          }}
        }}
      }});
    }});
  </script>
</body>
</html>"""
    return inject_svg_placeholders(full_page)


async def generate_page_html(
    settings: Settings,
    prompt: str,
    chat_transcript: str | None = None,
    title: str | None = None,
    model: str | None = None,
    page_type: str = "auto",
    target_audience: str = "general",
    creative_freedom: str = "medium",
    orientation: str = "portrait",
    layout_style: str = "auto",
    text_density: int = 5,
    interactivity: str = "auto",
    include_quiz: bool = True,
    include_svg: bool = True,
    theme_palette: str = "ocean",
    visual_style: str = "auto",
) -> tuple[str, str]:
    """
    Generates a full standalone HTML5 document from a prompt or chat transcript.
    Returns (resolved_title, html_content).
    """
    clean_prompt = prompt.strip()
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "google/gemini-2.5-flash"

    # Context construction
    user_query_parts = []
    if chat_transcript:
        user_query_parts.append(
            "Voici la conversation cLAIr à synthétiser sous forme de page web interactive didactique :\n"
            f"```\n{chat_transcript[:24000]}\n```\n"
        )
    if clean_prompt:
        user_query_parts.append(f"Instructions et sujet de la page : {clean_prompt}")
    if title:
        user_query_parts.append(f"Titre souhaité : {title}")

    # Explicit layout and design guidelines
    design_options = ["=== OPTIONS ET DIRECTIVES DE CONCEPTION ==="]

    # 1. Type de page
    if page_type == "revision":
        design_options.append("- TYPE DE PAGE : Fiche de révision pédagogique axée sur la mémorisation et l'apprentissage actif (synthèses, définitions clés, pièges à éviter, mémo).")
    elif page_type == "didactic_sheet":
        design_options.append("- TYPE DE PAGE : Fiche didactique claire et structurée avec schémas conceptuels et repères méthodologiques.")
    elif page_type == "article":
        design_options.append("- TYPE DE PAGE : Article de fond / format magazine éditorial avec mise en page élégante, citations et lecture immersive.")
    elif page_type == "dashboard":
        design_options.append("- TYPE DE PAGE : Tableau de bord visuel structuré avec indicateurs clés, cartes récapitulatives et grille modulaire.")
    elif page_type == "report":
        design_options.append("- TYPE DE PAGE : Rapport formel structuré avec synthèse exécutive, analyse approfondie et recommandations.")

    # 2. Public cible
    if target_audience == "school":
        design_options.append("- PUBLIC CIBLE : Élèves, débutants ou révisions scolaires. Utilise un vocabulaire accessible, des analogies concrètes et des repères visuels stimulants.")
    elif target_audience == "academic":
        design_options.append("- PUBLIC CIBLE : Étudiants ou universitaires. Rigueur conceptuelle, terminologie exacte et profondeur d'analyse.")
    elif target_audience == "professional":
        design_options.append("- PUBLIC CIBLE : Professionnels et décideurs. Style concis, vision stratégique, chiffres et synthèse exécutive percutante.")
    elif target_audience == "general":
        design_options.append("- PUBLIC CIBLE : Grand public curieux. Didactique, vivant, captivant et accessible sans jargon excessif.")

    # 3. Liberté créative
    if creative_freedom == "low":
        design_options.append("- LIBERTÉ CRÉATIVE FAIBLE : Sections classiques, typographie sobre, disposition prévisible, grilles calmes et régulières. Idéal pour documents formels et rapports techniques.")
    elif creative_freedom == "high":
        design_options.append("- LIBERTÉ CRÉATIVE ÉLEVÉE : Formes organiques, compositions asymétriques audacieuses, dégradés riches, animations subtiles et schémas SVG expressifs, tout en garantissant une excellente lisibilité.")
    else:
        design_options.append("- LIBERTÉ CRÉATIVE MOYENNE : Compositions travaillées, couleurs harmonieuses, schémas SVG équilibrés, cartes contrastées et variations de mise en page.")

    # 4. Orientation
    if orientation == "landscape":
        design_options.append("- ORIENTATION PAYSAGE (ÉCRAN LARGE) : Conçois une mise en page panoramique large (max-width: 1280px ou 1400px) tirant parti de la largeur de l'écran avec 2 à 3 colonnes horizontales côte à côte, idéale pour écrans larges, présentations ou dashboards.")
    else:
        design_options.append("- ORIENTATION PORTRAIT (LECTURE VERTICALE) : Conçois une mise en page centrée (max-width: 900px), optimisée pour le défilement vertical naturel et la lecture sur smartphone/tablette ou fiche classique.")

    # 5. Format et Mise en page
    if layout_style == "print_sheet":
        design_options.append(
            "- FORMAT IMPRESSION / FICHE UNIQUE : Conçois cette page sous la forme d'une fiche mémo compacte "
            "optimisée pour tenir sur une feuille d'impression (recto ou recto-verso A4). Intègre des règles CSS "
            "@media print { @page { margin: 1cm; size: A4; } body { background: #fff !important; color: #000 !important; } .no-print { display: none !important; } }. "
            "Utilise des grilles denses, des cartes de synthèse et un bouton d'impression <button class=\"no-print\" onclick=\"window.print()\">🖨️ Imprimer</button>."
        )
    elif layout_style == "single_page":
        design_options.append(
            "- MISE EN PAGE CONTINUE : Présente l'intégralité du contenu en une seule page continue déroulante avec des sections "
            "bien délimitées et un sommaire d'ancres en haut. Ne masque pas de parties derrière des onglets."
        )
    elif layout_style == "tabs":
        design_options.append(
            "- MISE EN PAGE AVEC ONGLETS : Découpe les grandes parties du sujet dans un composant à onglets interactif (<div class=\"tabs\">) "
            "avec boutons d'onglets pour passer d'un aspect à l'autre."
        )
    else:
        design_options.append(
            "- MISE EN PAGE LIBRE & HARMONIEUSE : Choisis librement la disposition (onglets ou défilement continu ou cartes modulaires) "
            "la plus naturelle et percutante pour ce sujet."
        )

    # 6. Densité du texte
    if text_density <= 3:
        design_options.append(
            f"- DENSITÉ DU TEXTE ({text_density}/10 - Très synthétique & aéré) : "
            "Sois concis et percutant. Privilégie les points clés, chiffres en grand, puces courtes et tableaux. Évite les longs paragraphes."
        )
    elif text_density <= 7:
        design_options.append(
            f"- DENSITÉ DU TEXTE ({text_density}/10 - Équilibré & didactique) : "
            "Offre un bon équilibre entre clarté explicative, exemples et synthèse visuelle."
        )
    else:
        design_options.append(
            f"- DENSITÉ DU TEXTE ({text_density}/10 - Dense & approfondi) : "
            "Contenu riche et exhaustif. Détaille en profondeur chaque notion, définitions rigoureuses, nuances et études de cas."
        )

    # 7. Interactivité
    if interactivity == "none":
        design_options.append("- INTERACTIVITÉ STATIQUE : Pas de JavaScript superflu. Document 100% lisible et exploitable au repos sans interaction requise.")
    elif interactivity == "high":
        design_options.append("- INTERACTIVITÉ FORTE : Exploite JavaScript vanilla au maximum : onglets, simulateurs avec curseurs dynamiques, quiz avec score en direct, accordéons et basculeurs.")
    else:
        design_options.append("- INTERACTIVITÉ INTELLIGENTE : Inclus du JavaScript léger uniquement là où il apporte une valeur concrète (onglets, quiz, accordéons).")

    # 8. Quiz et SVG
    if include_quiz and interactivity != "none":
        design_options.append("- QUIZ INTERACTIF : Inclus impérativement un mini-quiz (3 questions) avec validation immédiate et feedback.")
    else:
        design_options.append("- SANS QUIZ : Ne pas inclure de module de quiz.")

    if include_svg:
        design_options.append("- ILLUSTRATION SVG : Inclus au moins un schéma vectoriel SVG inline (<svg viewBox=...) soigné, coloré et didactique.")
    else:
        design_options.append("- SANS SVG (ZÉRO SVG) : N'inclus strictement AUCUN schéma vectoriel ni balise <svg>. Privilégie une mise en page typographique claire, des tableaux et des encadrés textuels.")

    # 9. Style graphique
    if visual_style != "auto" and visual_style in VISUAL_STYLES:
        vstyle = VISUAL_STYLES[visual_style]
        design_options.append(f"- STYLE GRAPHIQUE ET IDENTITÉ VISUELLE : {vstyle['prompt_directive']}")
    else:
        design_options.append("- STYLE GRAPHIQUE : Direction artistique élégante et cohérente, adaptée à la tonalité du sujet.")

    design_options.append(f"- AMBIANCE & COULEURS : Palette dominante '{theme_palette}' avec variables CSS claires et sombres.")
    user_query_parts.append("\n".join(design_options))

    full_user_prompt = "\n\n".join(user_query_parts)

    has_llm_key = False
    try:
        if not getattr(settings, "demo_mode", False):
            _key(settings, "llm_api_key", "du fournisseur IA")
            has_llm_key = True
    except ProviderError:
        has_llm_key = False

    if not has_llm_key or getattr(settings, "demo_mode", False):
        resolved_title = title or (clean_prompt[:60].strip() or "Synthèse de conversation")
        return resolved_title, generate_fallback_page(
            resolved_title,
            clean_prompt or "Page didactique interactive",
            layout_style=layout_style if layout_style != "auto" else "tabs",
            text_density=text_density,
            include_quiz=include_quiz,
            include_svg=include_svg,
            theme_palette=theme_palette,
            visual_style=visual_style if visual_style != "auto" else "modern_clean",
            orientation=orientation,
            creative_freedom=creative_freedom,
        )

    # Temperature adapted to creative freedom
    temp = 0.2 if creative_freedom == "low" else (0.75 if creative_freedom == "high" else 0.45)

    key = _key(settings, "llm_api_key", "du fournisseur IA")
    messages = [
        {"role": "system", "content": PAGE_SYSTEM_PROMPT},
        {"role": "user", "content": full_user_prompt},
    ]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": target_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": temp,
                    "max_tokens": 12000,
                },
            )
        _check_response(response, "Fournisseur IA")
        payload = _json(response, "Fournisseur IA")
        raw_content = payload["choices"][0]["message"]["content"]
        html_code = extract_html(raw_content)

        if not html_code or "<html" not in html_code.lower():
            resolved_title = title or clean_prompt[:60]
            return resolved_title, generate_fallback_page(
                resolved_title,
                clean_prompt,
                layout_style=layout_style if layout_style != "auto" else "tabs",
                text_density=text_density,
                include_quiz=include_quiz,
                include_svg=include_svg,
                theme_palette=theme_palette,
                visual_style=visual_style if visual_style != "auto" else "modern_clean",
                orientation=orientation,
                creative_freedom=creative_freedom,
            )

        html_code = inject_svg_placeholders(html_code)
        resolved_title = title or extract_title_from_html(html_code, fallback=clean_prompt[:60])
        return resolved_title, html_code

    except Exception as exc:
        _logger.warning("Erreur lors de la génération de page HTML par IA: %s; utilisation du fallback.", exc)
        resolved_title = title or (clean_prompt[:60].strip() or "Page Web")
        return resolved_title, generate_fallback_page(
            resolved_title,
            clean_prompt,
            layout_style=layout_style if layout_style != "auto" else "tabs",
            text_density=text_density,
            include_quiz=include_quiz,
            include_svg=include_svg,
            theme_palette=theme_palette,
            visual_style=visual_style if visual_style != "auto" else "modern_clean",
            orientation=orientation,
            creative_freedom=creative_freedom,
        )


async def refine_page_html(
    settings: Settings,
    current_html: str,
    instruction: str,
    model: str | None = None,
) -> str:
    """
    Refines an existing HTML page given user instructions.
    Returns the new updated full HTML string.
    """
    clean_instruction = instruction.strip()
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "google/gemini-2.5-flash"

    has_llm_key = False
    try:
        if not getattr(settings, "demo_mode", False):
            _key(settings, "llm_api_key", "du fournisseur IA")
            has_llm_key = True
    except ProviderError:
        has_llm_key = False

    if not has_llm_key or getattr(settings, "demo_mode", False):
        # Demo fallback: simple substitution or append a banner note
        note = f"<!-- Modifié suite à la consigne : {html.escape(clean_instruction)} -->"
        if "</head>" in current_html:
            return current_html.replace("</head>", f"{note}\n</head>")
        return f"{note}\n{current_html}"

    key = _key(settings, "llm_api_key", "du fournisseur IA")
    user_prompt = (
        f"Consigne d'amélioration demandée par l'utilisateur :\n{clean_instruction}\n\n"
        f"Code HTML actuel de la page :\n```html\n{current_html}\n```"
    )

    messages = [
        {"role": "system", "content": REFINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": target_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 12000,
                },
            )
        _check_response(response, "Fournisseur IA")
        payload = _json(response, "Fournisseur IA")
        raw_content = payload["choices"][0]["message"]["content"]
        updated_html = extract_html(raw_content)

        if not updated_html or "<html" not in updated_html.lower():
            return current_html

        return inject_svg_placeholders(updated_html)

    except Exception as exc:
        _logger.warning("Erreur lors de l'affinage de page HTML par IA: %s", exc)
        return current_html

