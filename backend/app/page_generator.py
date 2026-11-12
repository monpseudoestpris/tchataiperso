import html
import json
import logging
import re
import secrets
import unicodedata
from typing import Any

import httpx

from .config import Settings
from .providers import ProviderError, _check_response, _json, _key
from .motion_fx import MOTION_FX_CSS, MOTION_FX_JS, inject_motion_fx
from .page_runtime import CLAIR_PAGE_RUNTIME_JS, sanitize_and_enhance_html
from .svg_assets import inject_svg_placeholders, render_svg_asset
from .text_fx import TEXT_FX_CSS, TEXT_FX_JS, inject_text_fx_placeholders, render_curved_text

_logger = logging.getLogger("uvicorn.error")

_TIMEOUT = httpx.Timeout(180.0, connect=15.0, pool=15.0)


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
    """Extract full HTML document from LLM output, stripping markdown fencing if present.
    Robust to truncated responses where closing ``` or </html> was cut off."""
    text = raw.strip()

    # Search for markdown fenced block containing HTML document (with or without closing fence)
    code_block = re.search(r"```(?:html)?\s*(<!DOCTYPE[\s\S]*?</html>)\s*```?", text, re.IGNORECASE)
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

    # Fenced block starting with <!DOCTYPE or <html but without closing </html> (truncated response)
    truncated_fenced = re.search(r"```(?:html)?\s*(<!DOCTYPE[\s\S]*|<html[\s\S]*)", text, re.IGNORECASE)
    if truncated_fenced:
        doc = truncated_fenced.group(1).strip()
        # Strip trailing backticks if any
        doc = re.sub(r"\s*```+\s*$", "", doc)
        return doc

    # If already starting with doctype
    if text.lower().startswith("<!doctype html"):
        return re.sub(r"\s*```+\s*$", "", text).strip()

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

RÈGLES D'OR ABSOLUES D'AUTONOMIE ET D'ESTHÉTIQUE (TRÈS STRICT) :
1. FICHIER UNIQUE : Tout doit être dans un seul document HTML5 : <!DOCTYPE html><html lang="fr"><head>...<style>...</style></head><body>...<script>...</script></body></html>.
2. POLICES WEB, RESSOURCES ET DÉPENDANCES :
   - Strictement AUCUN <script src="http..."> externe (pas de React, pas de jQuery, pas de bibliothèques tierces js : utilise exclusivement du JavaScript vanilla moderne, propre et autonome dans <script>).
   - Strictement AUCUNE image externe <img src="http..."> (les URLs externes cassent facilement et ne chargent pas hors-ligne : utilise exclusivement des illustrations et icônes en SVG inline ou balises locales <clair-svg name="..." />).
   - LIENS, ANCRES ET SÉCURITÉ DU DOCUMENT :
     * Tout lien externe <a href="https://..."> DOIT impérativement comporter target="_blank" rel="noopener noreferrer" pour ne JAMAIS remplacer la page ni sortir l'utilisateur de l'application.
     * Si tu crées des liens d'ancres (<a href="#section-id">), chaque ancre DOIT correspondre à un élément existant avec le même id exact (id="section-id").
     * Ne JAMAIS utiliser location.reload() dans les boutons d'interaction : réinitialise l'état en JavaScript sans recharger la page.
   - POLICES WEB FUN, EXPRESSIVES ET MODERNES (Google Fonts) :
     Utilise impérativement de superbes polices web via Google Fonts (<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=...&display=swap" rel="stylesheet"> ou @import dans <style>) avec une police pleine de fraîcheur ou de personnalité pour les titres et une typographie fluide pour le corps :
     * Moderne / Pop / SaaS : 'Outfit', 'Poppins', 'Plus Jakarta Sans', 'Space Grotesk'
     * Fun / BD / Ludique / Enfants : 'Fredoka', 'Quicksand', 'Baloo 2', 'Patrick Hand', 'Comic Neue'
     * Rétro / 80s / Synthwave : 'Righteous', 'Orbitron', 'Syne', 'Bungee'
     * Presse / Journal / Littéraire : 'Playfair Display', 'Lora', 'Merriweather'
     * Cahier / Fiches révision : 'Caveat', 'Patrick Hand', 'Indie Flower'
     Associe toujours une pile de repli propre dans le CSS : font-family: 'NomDePolice', system-ui, -apple-system, sans-serif;
3. DÉTECTION INTELLIGENTE DES COMPOSANTS (N'ajoute que ce qui apporte une réelle valeur didactique) :
   Analyse le sujet et insère prioritairement les éléments pertinents :
   - Événements historiques ou chronologiques -> Frise chronologique SVG soignée.
   - Comparaison de notions, produits ou thèses -> Cartes comparatives côte à côte, tableau récapitulatif.
   - Sujet scientifique, biologique ou technique -> Schéma conceptuel SVG explicatif légendé, voire simulation interactive.
   - Démarche par étapes ou tutoriel -> Timeline d'étapes numérotées, blocs de code ou points de vigilance.
   - Données chiffrées ou statistiques -> Graphique vectoriel SVG (barres, courbes, anneaux) ou métriques clés en grands chiffres.
   - Révisions scolaires ou pédagogie active -> Encadrés "À retenir", définitions clés, tableaux mémo.
   - Vulgarisation ou essai -> Citations marquantes, encadrés "Le saviez-vous ?", analogies visuelles.
   - STRICTEMENT AUCUN QUIZ SUPERFICIEL : Ne génère aucun mini-quiz de fin de page, QCM ou bouton de validation de réponse. Consacre 100% de l'espace au contenu substantiel, aux explications détaillées et aux analyses approfondies.
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
     * Simulateur/calculateur interactif avec curseurs <input type="range"> selon le sujet.
     * Bouton "Copier le résumé" ou filtres dynamiques.
   - Le JavaScript doit être propre, robuste, sans erreur console et sans bibliothèque externe.
7. TYPOGRAPHIE EXPRESSIVE & TEXTE QUI PREND FORME (Inspirations Charming.js, Pretext, xsvg) :
   Ne laisse pas le texte uniquement plat et statique ! C'est TOI qui choisis judicieusement l'effet selon la tonalité du sujet :
   * EFFETS CHARMING.JS (Lettre-par-lettre, cinétique & micro-interactions) :
     - <h1 class="charming" data-fx="wave">Titre Ondulant</h1> : ondulation sinusoïdale fluide au fil des lettres.
     - <h1 class="charming" data-fx="gradient">Titre Lumineux</h1> : dégradé chromatique animé le long des lettres.
     - <span class="charming" data-fx="glow">Mot Clé</span> : halo lumineux doux sur une notion centrale.
     - <span class="charming" data-fx="bounce">Survolez-moi</span> : micro-interaction pop au survol des lettres.
     - <h2 class="charming" data-fx="stagger">Sous-titre en cascade</h2> : apparition séquentielle dynamique des lettres.
   * EFFET PRETEXT (Titres monumentaux auto-ajustés sans reflow) :
     - <h1 class="pretext-fit">TITRE MAJESTUEUX</h1> : calcule géométriquement la taille idéale de police pour remplir exactement 100% de la largeur du conteneur façon titre de magazine ou affiche d'exposition.
   * EFFET XSVG (Texte vectoriel qui épouse une forme ou une courbe) :
     - <clair-curved-text text="Une citation qui prend la forme d'une onde" curve="wave" />
     - <clair-curved-text text="Comprendre pour mieux agir" curve="arc" />
     - Épouse harmonieusement des trajectoires SVG courbes avec dégradé lié aux couleurs de la page.
   * CRITÈRES DE DÉCISION DU LLM :
     - *Sujet Scientifique / Technique* : Typographie rigoureuse, effet 'gradient' ou 'glow' subtil sur les équations ou mots-clés, cartouches précis.
     - *Fiche de Révision / Scolaire* : Titre 'stagger' ou 'wave', notions importantes avec 'bounce' au survol pour stimuler l'interaction.
     - *Article de Presse / Éditorial* : Grand titre avec 'pretext-fit' monumental, devises avec 'clair-curved-text'.
     - *Créativité Élevée* : Utilise pleinement 'wave', 'gradient' et 'clair-curved-text' pour rompre avec la rigidité des pages web classiques.
     - *Lisibilité absolue* : Ne transforme JAMAIS un paragraphe de lecture entier en texte cinétique. Réserve ces effets aux titres (h1, h2), aux mots-clés ou aux bandeaux d'accroche !
8. ANIMATIONS AU DÉFILEMENT (AOS) & CHORÉGRAPHIES GSAP (Moteur autonome 100% hors-ligne intégré) :
   La page dispose d'un moteur autonome ultra-léger compatible AOS et GSAP (aucun CDN ni réseau requis) :
   * EFFETS DÉCLARATIFS AOS (Animate On Scroll via attributs HTML) :
     Anime l'arrivée des éléments au fil du défilement avec `data-aos` et `data-aos-delay` :
     - `data-aos="fade-up"` (ou `fade-down`, `fade-left`, `fade-right`, `zoom-in`, `flip-up`).
     - `data-aos-delay="100"` (décalage progressif en cascade sur les cartes d'une même grille : 0, 100, 200, 300...).
     - Exemple : `<div class="card" data-aos="fade-up" data-aos-delay="150">...</div>`.
     - Applique ces attributs sur les cartes de contenu, frises chronologiques, diagrammes SVG et blocs clés.
   * MICRO-ANIMATIONS ET COMPTEURS GSAP (dans ton bloc <script>) :
     Tu as accès aux API standards `gsap.from()`, `gsap.to()`, `gsap.timeline()` et `ScrollTrigger` :
     - Compteur chiffré animé automatique : ajoute simplement `data-gsap-counter="1500"` ou `<span class="stat-num" data-gsap-counter="98">98</span> %` pour faire défiler les chiffres à l'arrivée dans l'écran.
     - Entrée progressive du Hero ou d'un tracé SVG :
       `gsap.from('.hero-badge', { opacity: 0, y: -15, duration: 0.6 });`
     - Règle de sobriété : les animations doivent sublimer le contenu et la lisibilité, sans surcharger inutilement la page.
9. RÈGLE DE DÉVELOPPEMENT EXHAUSTIF ET ZÉRO BRIDE DE LONGUEUR :
   - AUCUNE LIMITE DE TAILLE EN SORTIE : Seule compte la richesse, la précision et la profondeur du contenu.
   - Ne résume JAMAIS à la va-vite en quelques puces ou 2 ou 3 phrases télégraphiques.
   - sur chaque thème abordé comporte toi en expert du domaine
   - Chaque thème, sous-partie ou concept doit être développé de manière détaillée (minimum 20 à 30 lignes complètes par thème traité avec explications de fond, contextualisation, exemples décortiqués, méthodes et citations).
10. FORMAT DE SORTIE :
   - Retourne UNIQUEMENT le document HTML5 complet, sans texte d'introduction ni de conclusion, sans backticks markdown si possible.
"""

REFINE_SYSTEM_PROMPT = """Tu es un expert web perfectionnant une page HTML5 autonome existante.
Tu reçois le code HTML complet actuel d'une page et une consigne d'amélioration demandée par l'utilisateur.

RÈGLES IMPÉRATIVES :
1. Applique fidèlement les demandes (modification de contenu, ajout/modification de graphiques SVG, changement de palette CSS, ajout de quiz ou d'interactions JS, etc.).
2. Conserve impérativement le caractère autonome et la qualité graphique du document :
   - Strictement aucun script JS externe ni images externes risquant d'être brisées : tout le JS vanilla dans <script>, illustrations et icônes en SVG inline ou <clair-svg>.
   - Tout lien externe <a href="https://..."> doit impérativement comporter target="_blank" rel="noopener noreferrer".
   - Ne jamais utiliser location.reload() dans les boutons d'interaction : réinitialise l'état en JS.
   - Polices web expressives et fun encouragées via Google Fonts (<link> ou @import).
   - Animations fluides au scroll : tu peux enrichir ou ajouter des attributs `data-aos="fade-up"` (ou fade-left, fade-right, zoom-in) et `data-aos-delay="..."` sur les cartes et sections, ainsi que des animations et compteurs `gsap` dans `<script>`.
3. Conserve la cohérence globale de la page et les interactions existantes non concernées par la demande.
4. Retourne UNIQUEMENT le document HTML5 complet mis à jour, impérativement terminé par </body></html>.
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
        "font": "'Outfit', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "google_font": "Outfit:wght@400;600;700;800",
        "radius": "14px",
        "border_light": "1px solid #e2e8f0",
        "border_dark": "1px solid #334155",
        "shadow": "0 8px 24px -4px rgba(0, 0, 0, 0.08)",
        "prompt_directive": "STYLE MODERNE & ÉPURÉ : Interface claire et professionnelle, cartes blanches aux ombres douces et diffuses, bordures fines 1px, typographie moderne et soignée via Google Font 'Outfit' (<link href=\"https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&display=swap\" rel=\"stylesheet\">), badges soignés et icônes SVG fines.",
    },
    "neobrutalism": {
        "name": "Néobrutalisme Pop",
        "icon": "⚡",
        "description": "Bordures noires épaisses (2.5px), ombres franches décalées sans flou, couleurs vives.",
        "font": "'Space Grotesk', 'Plus Jakarta Sans', system-ui, sans-serif",
        "google_font": "Space+Grotesk:wght@500;700;800&family=Plus+Jakarta+Sans:wght@700;800",
        "radius": "8px",
        "border_light": "2.5px solid #111827",
        "border_dark": "2.5px solid #f8fafc",
        "shadow": "4px 4px 0px #111827",
        "prompt_directive": "STYLE NÉOBRUTALISME POP : Bordures noires épaisses (2.5px solid #111), ombres franches décalées sans flou (ex: box-shadow: 4px 4px 0 #111), typographie percutante et audacieuse via Google Fonts 'Space Grotesk' & 'Plus Jakarta Sans' (<link href=\"https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700;800&family=Space+Grotesk:wght@500;700;800&display=swap\" rel=\"stylesheet\">), couleurs pop contrastées et boutons très lisibles.",
    },
    "glassmorphism": {
        "name": "Glassmorphism & Glow",
        "icon": "💎",
        "description": "Cartes translucides avec verre dépoli, reflets lumineux et dégradés d'arrière-plan.",
        "font": "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
        "google_font": "Plus+Jakarta+Sans:wght@400;600;700;800",
        "radius": "18px",
        "border_light": "1px solid rgba(255, 255, 255, 0.35)",
        "border_dark": "1px solid rgba(255, 255, 255, 0.12)",
        "shadow": "0 8px 32px 0 rgba(0, 0, 0, 0.25)",
        "prompt_directive": "STYLE GLASSMORPHISM : Cartes translucides avec effet verre dépoli (backdrop-filter: blur(14px); background: rgba(255,255,255,0.12);), bordures lumineuses semi-transparentes, typographie ciselée via Google Font 'Plus Jakarta Sans' (<link href=\"https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap\" rel=\"stylesheet\">), dégradés d'arrière-plan riches et diffus, icônes SVG luminescentes.",
    },
    "notebook": {
        "name": "Cahier d'écolier & Fiches",
        "icon": "📓",
        "description": "Fond papier quadrillé/ligné, surlignages stabilo, post-it de synthèse et fiches de révision.",
        "font": "'Patrick Hand', 'Caveat', 'Segoe UI', cursive, sans-serif",
        "google_font": "Patrick+Hand&family=Caveat:wght@600;700",
        "radius": "10px",
        "border_light": "1px dashed #cbd5e1",
        "border_dark": "1px dashed #475569",
        "shadow": "0 4px 12px rgba(0, 0, 0, 0.06)",
        "prompt_directive": "STYLE CAHIER D'ÉCOLIER : Ambiance prise de notes et fiches bristol : fond papier réglé/quadrillé discret, typographie manuscrite fun et chaleureuse via Google Fonts 'Patrick Hand' et 'Caveat' (<link href=\"https://fonts.googleapis.com/css2?family=Caveat:wght@600;700&family=Patrick+Hand&display=swap\" rel=\"stylesheet\">), titres surlignés au feutre fluo (effet stabilo), cartes type post-it avec punaise ou trombone SVG.",
    },
    "cyberpunk": {
        "name": "Cyberpunk & Terminal",
        "icon": "🔮",
        "description": "Fond sombre OLED, néons cyan/magenta éclatants, typographie monospace futuriste.",
        "font": "'JetBrains Mono', 'Space Grotesk', monospace",
        "google_font": "JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@600;800",
        "radius": "6px",
        "border_light": "1px solid #0284c7",
        "border_dark": "1px solid #38bdf8",
        "shadow": "0 0 16px rgba(56, 189, 248, 0.35)",
        "prompt_directive": "STYLE CYBERPUNK & TERMINAL : Fond noir spatial/OLED (#0a0b14), accents néon cyan éclatant (#00f0ff) et magenta (#ff007f), typographie cybernétique via Google Fonts 'Space Grotesk' & 'JetBrains Mono' (<link href=\"https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@600;800&display=swap\" rel=\"stylesheet\">), bordures luminescentes avec halos glow.",
    },
    "editorial_newspaper": {
        "name": "Journal & Presse Éditoriale",
        "icon": "📰",
        "description": "Typographie Serif prestigieuse (Georgia/Garamond), mise en colonnes, lettrines et filets.",
        "font": "'Playfair Display', 'Lora', Georgia, serif",
        "google_font": "Playfair+Display:ital,wght@0,600;0,700;0,900;1,400&family=Lora:ital,wght@0,400;0,500;1,400",
        "radius": "4px",
        "border_light": "1px solid #d4c5b9",
        "border_dark": "1px solid #44403c",
        "shadow": "0 2px 6px rgba(0, 0, 0, 0.05)",
        "prompt_directive": "STYLE JOURNAL & ÉDITORIAL ANCIEN : Typographie à empattement prestigieuse via Google Fonts 'Playfair Display' (titres) & 'Lora' (corps) (<link href=\"https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;1,400&family=Playfair+Display:ital,wght@0,600;0,700;0,900;1,400&display=swap\" rel=\"stylesheet\">), lettrines majuscules en début de partie, filets horizontaux doubles, ton papier ivoire/sépia raffiné.",
    },
    "pastel_infographic": {
        "name": "Infographie Pastel Didactique",
        "icon": "🎨",
        "description": "Teintes douces (pêche, menthe, lavande), grands angles arrondis et chiffres géants.",
        "font": "'Quicksand', 'Outfit', system-ui, sans-serif",
        "google_font": "Quicksand:wght@500;600;700&family=Outfit:wght@600;700",
        "radius": "22px",
        "border_light": "1px solid #e0e7ff",
        "border_dark": "1px solid #312e81",
        "shadow": "0 8px 20px rgba(99, 102, 241, 0.1)",
        "prompt_directive": "STYLE INFOGRAPHIE PASTEL : Couleurs douces (menthe, pêche, lilas, vanille), typographie ronde et chaleureuse via Google Fonts 'Quicksand' & 'Outfit' (<link href=\"https://fonts.googleapis.com/css2?family=Outfit:wght@600;700&family=Quicksand:wght@500;600;700&display=swap\" rel=\"stylesheet\">), grands blocs arrondis (border-radius: 22px), chiffres clés géants en médaillons, format magazine de vulgarisation scientifique.",
    },
    "minimal_mono": {
        "name": "Minimaliste Suisse & Mono",
        "icon": "📐",
        "description": "Noir, blanc et gris neutre, grille suisse stricte, géométrie pure et zéro distraction.",
        "font": "'Space Grotesk', 'Helvetica Neue', Helvetica, Arial, sans-serif",
        "google_font": "Space+Grotesk:wght@400;600;700",
        "radius": "0px",
        "border_light": "1px solid #0f172a",
        "border_dark": "1px solid #f8fafc",
        "shadow": "none",
        "prompt_directive": "STYLE MINIMALISTE SUISSE : Noir et blanc pur avec nuances de gris neutre, aucune ombre inutile, grille géométrique impeccable, typographie percutante via Google Font 'Space Grotesk' (<link href=\"https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap\" rel=\"stylesheet\">) et espacements très généreux.",
    },
    "synthwave_retro": {
        "name": "Rétro 80s Synthwave",
        "icon": "🌆",
        "description": "Coucher de soleil violet/fuchsia, perspective filaire en arrière-plan, néons chauds.",
        "font": "'Righteous', 'Space Grotesk', system-ui, sans-serif",
        "google_font": "Righteous&family=Space+Grotesk:wght@500;700",
        "radius": "10px",
        "border_light": "1px solid #ec4899",
        "border_dark": "1px solid #f43f5e",
        "shadow": "0 0 24px rgba(236, 72, 153, 0.35)",
        "prompt_directive": "STYLE RÉTRO 80s & SYNTHWAVE : Teintes néon coucher de soleil (violet, rose fuchsia, orange ambré), arrière-plan sombre avec grille filaire, typographie rétro-futuriste via Google Fonts 'Righteous' (titres) & 'Space Grotesk' (texte) (<link href=\"https://fonts.googleapis.com/css2?family=Righteous&family=Space+Grotesk:wght@500;700&display=swap\" rel=\"stylesheet\">), touches lumineuses d'ambre et néon.",
    },
    "nature_botanic": {
        "name": "Nature & Botanique",
        "icon": "🌿",
        "description": "Vert sauge, lin naturel, teintes terreuses, ambiance herbier et carnet naturaliste.",
        "font": "'Plus Jakarta Sans', 'Lora', system-ui, serif",
        "google_font": "Plus+Jakarta+Sans:wght@400;600;700&family=Lora:ital,wght@0,500;1,400",
        "radius": "16px",
        "border_light": "1px solid #cbd5be",
        "border_dark": "1px solid #3f4e38",
        "shadow": "0 6px 16px rgba(46, 78, 40, 0.08)",
        "prompt_directive": "STYLE NATURE & BOTANIQUE : Palette terreuse et végétale (vert sauge, mousse, beige lin, argile), typographie élégante via Google Fonts 'Plus Jakarta Sans' et 'Lora' (<link href=\"https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;1,400&family=Plus+Jakarta+Sans:wght@400;600;700&display=swap\" rel=\"stylesheet\">), cartes façon herbier avec coins arrondis et textures douces, schémas végétaux ou naturalistes.",
    },
    "playful_cartoon": {
        "name": "BD & Cartoon Illustré",
        "icon": "🎈",
        "description": "Bulles de texte façon BD, contrastes joyeux, badges expressifs et dynamisme visuel.",
        "font": "'Fredoka', 'Baloo 2', system-ui, cursive, sans-serif",
        "google_font": "Fredoka:wght@500;600;700&family=Baloo+2:wght@600;800",
        "radius": "20px",
        "border_light": "2.5px solid #0284c7",
        "border_dark": "2.5px solid #38bdf8",
        "shadow": "4px 4px 0px rgba(2, 132, 199, 0.35)",
        "prompt_directive": "STYLE BD & CARTOON : Éléments façon bande dessinée, typographie fun, ronde et joyeuse via Google Fonts 'Fredoka' et 'Baloo 2' (<link href=\"https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;800&family=Fredoka:wght@500;600;700&display=swap\" rel=\"stylesheet\">), bulles de dialogue expressives, bordures rondes bien définies (radius 20px), contrastes colorés éclatants et touches ludiques avec icônes SVG animées.",
    },


}


FONT_FAMILIES: dict[str, dict[str, str]] = {
    "outfit": {
        "name": "Outfit & Plus Jakarta",
        "description": "Géométrique, moderne et net (Tech / SaaS)",
        "font": "'Outfit', 'Plus Jakarta Sans', system-ui, sans-serif",
        "google_font": "Outfit:wght@400;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700",
    },
    "playfair": {
        "name": "Playfair Display & Lora",
        "description": "Éditorial prestigieux, lettrines et élégance (Serif)",
        "font": "'Playfair Display', 'Lora', Georgia, serif",
        "google_font": "Playfair+Display:ital,wght@0,600;0,700;0,900;1,400&family=Lora:ital,wght@0,400;0,500;1,400",
    },
    "space_grotesk": {
        "name": "Space Grotesk & Syne",
        "description": "Brutaliste, design percutant & avant-garde",
        "font": "'Space Grotesk', 'Syne', system-ui, sans-serif",
        "google_font": "Space+Grotesk:wght@500;700;800&family=Syne:wght@700;800",
    },
    "fredoka": {
        "name": "Fredoka & Baloo 2",
        "description": "Formes très douces, ludique et pédagogique",
        "font": "'Fredoka', 'Baloo 2', 'Quicksand', cursive, sans-serif",
        "google_font": "Fredoka:wght@500;600;700&family=Baloo+2:wght@600;700",
    },
    "caveat": {
        "name": "Caveat & Patrick Hand",
        "description": "Manuscrit naturel, esprit carnet de notes & croquis",
        "font": "'Caveat', 'Patrick Hand', 'Comic Sans MS', cursive",
        "google_font": "Caveat:wght@600;700&family=Patrick+Hand",
    },
    "jetbrains": {
        "name": "JetBrains Mono & Fira Code",
        "description": "Terminal de code, console et rigueur d'ingénierie",
        "font": "'JetBrains Mono', 'Fira Code', monospace",
        "google_font": "JetBrains+Mono:wght@400;600;700",
    },
    "righteous": {
        "name": "Righteous & Orbitron",
        "description": "Titres rétro-futuristes, Synthwave & grand affichage",
        "font": "'Righteous', 'Orbitron', 'Space Grotesk', sans-serif",
        "google_font": "Righteous&family=Orbitron:wght@600;800",
    },
}

def generate_fallback_page(
    title: str,
    topic: str,
    layout_style: str = "tabs",
    text_density: int = 5,
    include_quiz: bool = False,
    include_svg: bool = True,
    theme_palette: str = "ocean",
    visual_style: str = "modern_clean",
    orientation: str = "portrait",
    creative_freedom: str = "medium",
    animation_engine: str = "auto",
    font_family_choice: str = "auto",
    text_effects: list[str] | None = None,
    selected_topics: list[dict[str, Any]] | None = None,
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
    google_font = vstyle.get("google_font", "")

    # Override font if explicitly selected
    if font_family_choice != "auto" and font_family_choice in FONT_FAMILIES:
        chosen_font = FONT_FAMILIES[font_family_choice]
        font_family = chosen_font["font"]
        google_font = chosen_font["google_font"]

    font_link = ""
    if google_font:
        font_link = (
            f'  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
            f'  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'  <link href="https://fonts.googleapis.com/css2?family={google_font}&display=swap" rel="stylesheet">\n'
        )

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
          <text x="660" y="140" fill="rgba(255,255,255,0.85)" font-size="12" text-anchor="middle" font-family="system-ui">Analyse Approfondie</text>
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

    # Dynamic tabs and cards based on selected_topics if provided
    tabs_html = ""
    if selected_topics and len(selected_topics) > 0:
        tab_buttons = []
        tab_contents = []
        for idx, top in enumerate(selected_topics):
            top_title = html.escape(str(top.get("title", f"Thème {idx+1}")))
            top_desc = html.escape(str(top.get("description", "")))
            top_cat = html.escape(str(top.get("category", "Thème")))
            detail_lvl = int(top.get("detail_level", 5) or 5)
            is_active = "active" if idx == 0 else ""
            tab_id = f"topic-tab-{idx+1}"
            tab_buttons.append(
                f'<button class="tab-btn {is_active}" data-tab="{tab_id}">{top_title}</button>'
            )

            # Generate deep multi-paragraph development matching at least 20 lines
            tab_contents.append(
                f'<div class="tab-content {is_active}" id="{tab_id}">\n'
                f'  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">\n'
                f'    <span style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--primary); font-weight:700;">{top_cat}</span>\n'
                f'    <span style="font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:999px; background:rgba(2,132,199,0.15); color:var(--primary); font-weight:600;">Niveau de détail : {detail_lvl}/10</span>\n'
                f'  </div>\n'
                f'  <h4 style="margin-bottom: 0.85rem; color: var(--text); font-size:1.2rem; font-weight:700;">{top_title}</h4>\n'
                f'  <p style="margin-bottom:1rem; line-height:1.7; font-size:0.95rem;">{top_desc} Cette composante constitue un pilier déterminant du sujet, reliant les principes conceptuels à leurs applications opérationnelles directes.</p>\n'
                f'  <div style="background:var(--surface-hover); border-left:4px solid var(--primary); padding:0.85rem 1.1rem; border-radius:0 10px 10px 0; margin-bottom:1.25rem;">\n'
                f'    <strong style="color:var(--primary); display:block; margin-bottom:0.35rem; font-size:0.88rem;">Éléments fondamentaux & Définition de référence</strong>\n'
                f'    <p style="font-size:0.88rem; line-height:1.65; color:var(--text-muted); margin:0;">L\'étude approfondie de ce volet requiert d\'en maîtriser les notions pivot, les distinctions terminologiques indispensables et les mécanismes sous-jacents qui évitent toute ambiguïté d\'interprétation.</p>\n'
                f'  </div>\n'
                f'  <h5 style="color:var(--text); font-size:0.98rem; font-weight:600; margin:1rem 0 0.5rem;">Démarche d\'analyse & Mécanismes d\'application :</h5>\n'
                f'  <ul style="padding-left:1.4rem; display:flex; flex-direction:column; gap:0.5rem; line-height:1.6; font-size:0.92rem; margin-bottom:1.25rem;">\n'
                f'    <li><strong>Identification et repérage systématique :</strong> Observer précisément les indices concrets, les manifestations tangibles et les régularités caractéristiques.</li>\n'
                f'    <li><strong>Interprétation et mise en perspective :</strong> Relier chaque observation à son effet ciblé, à sa portée globale et aux intentions sous-jacentes.</li>\n'
                f'    <li><strong>Articulation logique avec l\'ensemble du sujet :</strong> Mettre en regard ce point avec les autres axes pour construire une démonstration cohérente et progressive.</li>\n'
                f'    <li><strong>Vérification critique et points de vigilance :</strong> Éviter les simplifications hâtives, les contresens fréquents et la simple paraphrase passive.</li>\n'
                f'  </ul>\n'
                f'  <div style="background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:0.85rem 1rem; font-size:0.88rem; line-height:1.6; color:var(--text-muted);">\n'
                f'    <span style="font-weight:600; color:var(--primary);">Synthèse d\'action :</span> L\'intégration rigoureuse de « {top_title} » assure la solidité de votre analyse, en conjuguant rigueur technique et vision d\'ensemble.\n'
                f'  </div>\n'
                f'</div>'
            )
        tabs_html = f"""
    <!-- Topics Sections (Sélectionnés sur-mesure) -->
    <div class="tabs" data-aos="fade-up" data-aos-delay="100">
      <div class="tab-header" style="overflow-x: auto; flex-wrap: nowrap; scrollbar-width: thin;">
        {" ".join(tab_buttons)}
      </div>
      {"".join(tab_contents)}
    </div>
"""
    else:
        tabs_html = """
    <!-- Content Sections -->
    <div class="tabs" data-aos="fade-up" data-aos-delay="100">
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
"""

    print_badge = '<span class="brand-badge" style="background:rgba(234,88,12,0.15);color:#ea580c;">Format Fiche Impression A4</span>' if is_print else '<span class="brand-badge">Autonome & Hors-ligne</span>'

    full_page = f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
{font_link}  <style>
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
    {TEXT_FX_CSS}
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
      <h1 class="charming" data-fx="wave">{safe_title}</h1>
      <p>{safe_topic}</p>
      <clair-curved-text text="Synthèse didactique & exploration visuelle" curve="wave" />
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
      <div class="card" data-aos="fade-up" data-aos-delay="50">
        <h3>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-7 7c0 3.03 1.8 5.64 4.38 6.74A1 1 0 0 0 10 16.7V18h4v-1.3a1 1 0 0 0 .62-.96C17.2 14.64 19 12.03 19 9a7 7 0 0 0-7-7z"/></svg>
          <span>Clé de voûte</span>
        </h3>
        <p>Ce document est 100 % autonome : tout le code CSS, JavaScript, animations AOS/GSAP et illustrations vectorielles SVG sont incorporés sans aucune ressource externe.</p>
      </div>
      <div class="card" data-aos="fade-up" data-aos-delay="150">
        <h3>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
          <span>Réactivité & fluidité</span>
        </h3>
        <p>Le document s'adapte immédiatement à votre taille d'écran, vos préférences de contraste et fonctionne intégralement hors ligne avec chorégraphie de défilement fluide.</p>
      </div>
    </div>

    <!-- Content Sections -->
    {tabs_html}

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
        if (window.AOS) window.AOS.refresh();
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
    {TEXT_FX_JS}
    {MOTION_FX_JS}
  </script>
</body>
</html>"""
    rendered = inject_text_fx_placeholders(inject_svg_placeholders(full_page))
    if animation_engine != "none":
        rendered = inject_motion_fx(rendered)
    return rendered


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
    include_quiz: bool = False,
    include_svg: bool = True,
    theme_palette: str = "ocean",
    visual_style: str = "auto",
    animation_engine: str = "auto",
    font_family: str = "auto",
    text_effects: list[str] | None = None,
    selected_topics: list[dict[str, Any]] | None = None,
    raise_on_failure: bool = False,
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
        design_options.append(
            "- STYLE GRAPHIQUE & TYPOGRAPHIE : Direction artistique soignée et captivante, "
            "avec importation obligatoire d'une belle police Google Font expressive ou fun (ex: 'Outfit', 'Poppins', 'Fredoka', 'Space Grotesk', 'Quicksand') "
            "dans <head> via <link href=\"https://fonts.googleapis.com/css2?family=...&display=swap\" rel=\"stylesheet\"> et styles CSS travaillés."
        )
    # 10. Typographie et police personnalisée
    if font_family != "auto" and font_family in FONT_FAMILIES:
        chosen_font = FONT_FAMILIES[font_family]
        design_options.append(
            f"- POLICE D'ÉCRITURE OBLIGATOIRE ({chosen_font['name']}) : "
            f"Importe impérativement dans <head> la police via <link href=\"https://fonts.googleapis.com/css2?family={chosen_font['google_font']}&display=swap\" rel=\"stylesheet\"> "
            f"et applique 'font-family: {chosen_font['font']};' sur body et les titres."
        )

    # 11. Moteur d'animation (AOS / GSAP / Les deux / Aucun)
    if animation_engine == "none":
        design_options.append("- ANIMATIONS DÉSACTIVÉES : N'utilise pas d'animations de défilement (AOS) ni de timeline GSAP. Document stable et statique.")
    elif animation_engine == "aos":
        design_options.append("- MOTEUR D'ANIMATION AOS PRIORITAIRE : Enrichis abondamment les cartes, grilles et sections avec des attributs data-aos=\"fade-up\" (ou fade-left, fade-right, zoom-in) et data-aos-delay pour une arrivée progressive rythmée au scroll.")
    elif animation_engine == "gsap":
        design_options.append("- MOTEUR D'ANIMATION GSAP PRIORITAIRE : Crée des chorégraphies GSAP dans <script> (gsap.from, gsap.timeline, compteurs animés via data-gsap-counter et tracé progressif SVG).")
    elif animation_engine == "both":
        design_options.append("- ANIMATIONS COMPLÈTES AOS & GSAP : Combine les deux moteurs : utilise data-aos sur les blocs de contenu pour les révélations au scroll ET des scripts GSAP pour animer le hero, les compteurs chiffrés (data-gsap-counter) et les diagrammes.")

    # 12. Effets typographiques et visuels sélectionnés
    if text_effects:
        eff_directives = []
        if "charming_wave" in text_effects:
            eff_directives.append("l'ondulation cinétique de lettres sur le titre principal (<h1 class=\"charming\" data-fx=\"wave\">Titre</h1>)")
        if "charming_gradient" in text_effects:
            eff_directives.append("le dégradé chromatique animé sur les termes clés (<span class=\"charming\" data-fx=\"gradient\">Mot-clé</span>)")
        if "charming_bounce" in text_effects:
            eff_directives.append("le pop/rebond dynamique au survol des sous-titres (<span class=\"charming\" data-fx=\"bounce\">Sous-titre</span>)")
        if "pretext_fit" in text_effects:
            eff_directives.append("un titre monumental pleine largeur auto-ajusté sans reflow (<div class=\"pretext-fit\">TITRE PLEIN CADRE</div>)")
        if "curved_text" in text_effects:
            eff_directives.append("un bandeau de texte courbé le long d'un tracé SVG organique (<clair-curved-text text=\"Votre devise ici\" curve=\"wave\" />)")
        if "gsap_counters" in text_effects:
            eff_directives.append("des compteurs numériques animés au scroll sur les métriques clés (<span class=\"stat-num\" data-gsap-counter=\"1500\">1500</span>)")
        if eff_directives:
            design_options.append(f"- EFFETS VISUELS ET TYPOGRAPHIQUES OBLIGATOIRES : Intègre impérativement : {', '.join(eff_directives)}.")


    # 13. Thèmes et sous-sujets sélectionnés par l'utilisateur avec niveau de détail requis
    if selected_topics and len(selected_topics) > 0:
        topics_summary = []
        for idx, t in enumerate(selected_topics, 1):
            t_title = t.get("title", f"Thème {idx}")
            t_desc = t.get("description", "")
            d_lvl = int(t.get("detail_level", 5) or 5)
            # Contract of lines based on detail level
            if d_lvl <= 3:
                lines_req = "minimum 12 à 18 lignes denses"
            elif d_lvl <= 6:
                lines_req = "MINIMUM 20 À 28 LIGNES DÉTAILLÉES (OBLIGATOIRE)"
            elif d_lvl <= 8:
                lines_req = "MINIMUM 35 À 45 LIGNES APPROFONDIES (OBLIGATOIRE)"
            else:
                lines_req = "MINIMUM 55+ LIGNES EXHAUSTIVES / COURS MAGISTRAL (OBLIGATOIRE)"

            item_str = f"Thème {idx} : « {t_title} » [Niveau de détail : {d_lvl}/10 — Contrat de volume : {lines_req}]"
            if t_desc:
                item_str += f"\n   Périmètre attendu : {t_desc}"
            topics_summary.append(item_str)

        joined_topics = "\n\n".join(topics_summary)
        design_options.append(
            "- THÈMES ET SOUS-THÈMES SÉLECTIONNÉS PAR L'UTILISATEUR (IMPÉRATIF ET STRICT) :\n"
            "L'utilisateur a explicitement validé la liste suivante de thèmes et leur niveau d'approfondissement respectif.\n"
            "Tu DOIS impérativement consacrer une section, un onglet ou un bloc d'analyse substantiel à CHACUN de ces thèmes sans en omettre aucun :\n\n"
            f"{joined_topics}\n\n"
            "RÈGLE D'OR DE DÉTAIL POUR CHAQUE THÈME (TRÈS STRICT) :\n"
            "* Ne résume JAMAIS un thème en 2 ou 3 lignes ou en quelques puces rapides.\n"
            "* Respecte scrupuleusement le contrat de volume par thème : dès le niveau 5/10 (défaut), rédige MINIMUM 20 LIGNES SUBSTANTIELLES par thème (définitions rigoureuses, développement en plusieurs paragraphes rédigés, mécanismes étape par étape, exemples réels décortiqués, méthodes d'application concrètes et encadrés d'analyse).\n"
            "* Ne te bride jamais sur la longueur : seule compte la complétude, la rigueur et l'exhaustivité de la rédaction."
        )

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
        if raise_on_failure:
            raise ProviderError("La création de page nécessite un fournisseur IA actif.")
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
            animation_engine=animation_engine,
            font_family_choice=font_family,
            text_effects=text_effects,
            selected_topics=selected_topics,
        )

    # Temperature adapted to creative freedom
    temp = 0.2 if creative_freedom == "low" else (0.75 if creative_freedom == "high" else 0.45)

    key = _key(settings, "llm_api_key", "du fournisseur IA")
    messages = [
        {"role": "system", "content": PAGE_SYSTEM_PROMPT},
        {"role": "user", "content": full_user_prompt},
    ]

    try:
        request_payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "temperature": temp,
            "max_tokens": 32768,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            # Retry incomplete documents once, regenerating from the original input.
            # Never append closing tags to a response whose content may be truncated.
            for attempt in range(2):
                response = await client.post(
                    settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=request_payload,
                )
                # Follow the existing presentation fallback for unsupported page models.
                fallback_model = getattr(settings, "default_model", "")
                if (response.status_code in (400, 404, 422)
                        and fallback_model and fallback_model != request_payload["model"]):
                    request_payload = {**request_payload, "model": fallback_model}
                    response = await client.post(
                        settings.llm_base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json=request_payload,
                    )
                _check_response(response, "Fournisseur IA")
                payload = _json(response, "Fournisseur IA")
                choice = payload["choices"][0]
                html_code = extract_html(choice["message"]["content"])
                incomplete = choice.get("finish_reason") == "length" or "</html>" not in html_code.lower()
                if not incomplete:
                    break
                if attempt == 1:
                    if raise_on_failure:
                        raise ProviderError("La page générée reste incomplète après une seconde tentative compacte. Réessayez.")
                    break
                if selected_topics:
                    compact_instruction = (
                        "La précédente réponse a été coupée par la limite de contexte. "
                        "Régénère le document HTML COMPLET en optimisant le code CSS et JavaScript pour laisser "
                        "le maximum d'espace au contenu rédigé détaillé de chaque thème sans le brider, et termine impérativement par </body></html>."
                    )
                else:
                    compact_instruction = (
                        "La précédente tentative était incomplète. Régénère depuis les données "
                        "initiales un document HTML COMPLET, plus compact : 4 sections maximum, "
                        "600 mots maximum, CSS concis et un seul SVG simple (40 éléments maximum). "
                        "Conserve les informations essentielles, nuances et sources utiles. "
                        "Aucune transcription des échanges, aucun script ni animation complexe. "
                        "Vise moins de 6000 tokens pour tout le fichier et termine impérativement "
                        "par </body></html>. Renvoie uniquement le document complet."
                    )
                request_payload = {
                    **request_payload,
                    "messages": [*messages, {"role": "user", "content": compact_instruction}],
                    "temperature": 0.2,
                }

        if not html_code or "<html" not in html_code.lower():
            if raise_on_failure:
                raise ProviderError("Le fournisseur a renvoyé une page invalide.")
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
                animation_engine=animation_engine,
                font_family_choice=font_family,
                text_effects=text_effects,
                selected_topics=selected_topics,
            )

        html_code = inject_text_fx_placeholders(inject_svg_placeholders(html_code))
        if animation_engine != "none":
            html_code = inject_motion_fx(html_code)
        resolved_title = title or extract_title_from_html(html_code, fallback=clean_prompt[:60])
        html_code = sanitize_and_enhance_html(html_code, title=resolved_title)
        return resolved_title, html_code

    except Exception as exc:
        if raise_on_failure:
            if isinstance(exc, ProviderError):
                raise
            if isinstance(exc, httpx.TimeoutException):
                raise ProviderError("La génération de la page a dépassé le délai autorisé. Réessayez.") from None
            if isinstance(exc, httpx.HTTPError):
                raise ProviderError("Impossible de joindre le fournisseur IA pour créer la page.") from None
            raise ProviderError("Le fournisseur IA a renvoyé une page illisible ou invalide.") from None
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
            animation_engine=animation_engine,
            font_family_choice=font_family,
            text_effects=text_effects,
            selected_topics=selected_topics,
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
        request_payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 32768,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            for attempt in range(2):
                response = await client.post(
                    settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=request_payload,
                )
                _check_response(response, "Fournisseur IA")
                payload = _json(response, "Fournisseur IA")
                raw_content = payload["choices"][0]["message"]["content"]
                choice = payload["choices"][0]
                updated_html = extract_html(raw_content)
                incomplete = choice.get("finish_reason") == "length" or "</html>" not in updated_html.lower()
                if not incomplete:
                    break
                if attempt == 1:
                    break
                compact_instruction = (
                    f"Consigne d'amélioration précédente : {clean_instruction}\n\n"
                    "Attention : la réponse précédente a été tronquée par la limite de longueur. "
                    "Génère le document HTML COMPLET en optimisant le code CSS et JavaScript pour laisser "
                    "le maximum d'espace au contenu rédigé, et termine impérativement par </body></html>."
                )
                request_payload = {
                    **request_payload,
                    "messages": [*messages, {"role": "user", "content": compact_instruction}],
                    "temperature": 0.2,
                }

        if not updated_html or "<html" not in updated_html.lower():
            return current_html

        enhanced = inject_motion_fx(inject_text_fx_placeholders(inject_svg_placeholders(updated_html)))
        return sanitize_and_enhance_html(enhanced)

    except Exception as exc:
        _logger.warning("Erreur lors de l'affinage de page HTML par IA: %s", exc)
        return current_html





def _generate_fallback_topics(prompt: str, title: str | None = None) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Deterministically generates a rich, broad list of topics/themes
    when the AI provider is offline or in demo mode, adapting to literary / analytical / scientific topics.
    """
    clean_topic = (title or prompt or "Sujet d'exploration").strip()
    suggested_title = clean_topic if len(clean_topic) <= 60 else clean_topic[:57] + "..."
    lowered = clean_topic.lower()
    summary = f"Panorama granulaire à 360° pour explorer « {suggested_title} » sous tous ses angles (méthode, outils, composantes et applications)."

    # Domain adaptation: Commentaire composé / analyse littéraire / français
    if any(k in lowered for k in ["commentaire", "texte", "littér", "poés", "roman", "théâtre", "dissert"]):
        topics: list[dict[str, Any]] = [
            {
                "id": "figures_style",
                "title": "Figures de style & Procédés rhétoriques",
                "description": "Métaphores, métonymies, oxymores, chiasmes, hyperboles et leur portée expressive dans le texte.",
                "category": "Stylistique",
                "recommended": True,
            },
            {
                "id": "ponctuation_rythme",
                "title": "Ponctuation, Rythme, Coupes & Typographie",
                "description": "Rôle des points de suspension, tirets, exclamations, coupes ternaires, asyndètes et ruptures syntaxiques.",
                "category": "Syntaxe",
                "recommended": True,
            },
            {
                "id": "champs_lexicaux",
                "title": "Champs lexicaux & Réseaux de sens",
                "description": "Réseaux lexicaux dominants, isotopies, oppositions lexicales et connotations mélioratives/péjoratives.",
                "category": "Lexique",
                "recommended": True,
            },
            {
                "id": "registres_tonalites",
                "title": "Registres littéraires & Tonalités",
                "description": "Identification des registres lyrique, pathétique, tragique, comique, satirique, polémique ou épique.",
                "category": "Tonalités",
                "recommended": True,
            },
            {
                "id": "versification_prosodie",
                "title": "Versification, Métrique & Musicalité",
                "description": "Alexandrins, hémistiches, césures, enjambements, rejets/contre-rejets, allitérations et assonances.",
                "category": "Poésie",
                "recommended": False,
            },
            {
                "id": "temps_modes_verbes",
                "title": "Temps et modes verbaux & Énonciation",
                "description": "Valeur du présent de narration, imparfait descriptif, subjonctif du doute et indices de subjectivité.",
                "category": "Grammaire",
                "recommended": False,
            },
            {
                "id": "focalisation_narrateur",
                "title": "Point de vue & Focalisation du récit",
                "description": "Focalisation zéro (omnisciente), interne ou externe, statut du narrateur et distance énonciative.",
                "category": "Narration",
                "recommended": False,
            },
            {
                "id": "structure_plan_axes",
                "title": "Construction des axes & du plan détaillé",
                "description": "Définition de 2 ou 3 grands axes directeurs, subdivisions ordonnées et transitions logiques.",
                "category": "Méthode",
                "recommended": True,
            },
            {
                "id": "intro_conclusion",
                "title": "Introduction & Conclusion parfaites",
                "description": "Accroche, situation du texte, problématique centrale, annonce de plan, bilan et ouverture soignée.",
                "category": "Structure",
                "recommended": True,
            },
            {
                "id": "citations_analyses",
                "title": "Technique de citation & Micro-analyses",
                "description": "Formule canonique : Procédé formel + Citation exacte + Effet de sens produit sur le lecteur.",
                "category": "Outils",
                "recommended": True,
            },
            {
                "id": "pieges_paraphrase",
                "title": "Erreurs fatales & Pièges à éviter",
                "description": "Éviter la paraphrase, le contresens historique, le catalogue étiqueté sans analyse et le plan hors-sol.",
                "category": "Vigilance",
                "recommended": True,
            },
            {
                "id": "vocabulaire_analyse",
                "title": "Lexique critique & Verbes d'analyse",
                "description": "Enrichir ses transitions : « suggère », « souligne », « cristallise », « donne à voir », « accentue ».",
                "category": "Rédaction",
                "recommended": False,
            },
            {
                "id": "genre_specificites",
                "title": "Spécificités par genre (Théâtre, Roman, Poésie, Essai)",
                "description": "Didaskalies et double énonciation au théâtre, ellipses et descriptions dans le roman, formes poétiques.",
                "category": "Genres",
                "recommended": False,
            },
            {
                "id": "exemple_complet",
                "title": "Exemple d'axe rédigé & Décorticage pas-à-pas",
                "description": "Modèle d'un paragraphe complet rédigé avec citation, repérage stylistique et interprétation philosophique.",
                "category": "Pratique",
                "recommended": True,
            },
            {
                "id": "bareme_attentes",
                "title": "Critères d'évaluation & Barème officiel",
                "description": "Ce que les correcteurs valorisent en priorité : rigueur du plan, finesse de l'analyse et fluidité du style.",
                "category": "Examen",
                "recommended": False,
            },
            {
                "id": "fiches_recap",
                "title": "Fiches mémo & Grille d'autocorrection",
                "description": "Checklist finale avant de rendre la copie pour vérifier l'orthographe, les transitions et les alinéas.",
                "category": "Synthèse",
                "recommended": False,
            },
        ]
        return suggested_title, summary, topics

    # General topics list (extended with operational subtopics)
    topics: list[dict[str, Any]] = [
        {
            "id": "foundations",
            "title": f"Fondamentaux & Définitions de {suggested_title}",
            "description": "Les principes fondateurs, le vocabulaire indispensable et le périmètre exact du sujet.",
            "category": "Fondements",
            "recommended": True,
        },
        {
            "id": "mechanisms",
            "title": "Fonctionnement interne & Mécanismes clés",
            "description": "Comment cela fonctionne en pratique, les rouages essentiels et la dynamique étape par étape.",
            "category": "Technique",
            "recommended": True,
        },
        {
            "id": "history",
            "title": "Origines, Histoire & Évolution chronologique",
            "description": "La genèse du concept, les dates pivots, les pionniers et les grandes ruptures historiques.",
            "category": "Histoire",
            "recommended": False,
        },
        {
            "id": "applications",
            "title": "Cas d'usage concrets & Applications pratiques",
            "description": "Exemples vécus sur le terrain, études de cas réelles et mise en application directe.",
            "category": "Pratique",
            "recommended": True,
        },
        {
            "id": "metrics",
            "title": "Chiffres clés, Ordres de grandeur & Statistiques",
            "description": "Repères quantitatifs majeurs, graphiques d'impact et métriques indispensables à retenir.",
            "category": "Données",
            "recommended": True,
        },
        {
            "id": "challenges",
            "title": "Enjeux contemporains, Débats & Controverses",
            "description": "Les dilemmes éthiques, tensions économiques, impacts sociétaux ou environnementaux.",
            "category": "Enjeux",
            "recommended": True,
        },
        {
            "id": "myths",
            "title": "Idées reçues, Mythes & Pièges fréquents",
            "description": "Démystification des contre-vérités courantes et des erreurs d'interprétation classiques.",
            "category": "Analyse",
            "recommended": False,
        },
        {
            "id": "comparisons",
            "title": "Comparaisons, Alternatives & Benchmarks",
            "description": "Mise en miroir avec les solutions ou approches concurrentes, avantages et inconvénients.",
            "category": "Comparatif",
            "recommended": False,
        },
        {
            "id": "best_practices",
            "title": "Guide de bonnes pratiques & Méthodologie",
            "description": "Recommandations concrètes, checklist actionnable et écueils majeurs à éviter.",
            "category": "Méthode",
            "recommended": True,
        },
        {
            "id": "future_horizons",
            "title": "Perspectives futures & Innovations émergentes",
            "description": "Ce qui se prépare pour les 5 à 10 prochaines années : ruptures technologiques et tendances.",
            "category": "Futur",
            "recommended": False,
        },
        {
            "id": "regulations",
            "title": "Cadre légal, Normes & Régulations",
            "description": "Standards internationaux, directives officielles et contraintes de conformité.",
            "category": "Cadre",
            "recommended": False,
        },
        {
            "id": "summary_takeaways",
            "title": "Synthèse mémotechnique & Synthèse visuelle",
            "description": "Résumé exécutif sous forme de points d'ancrage et schéma mental récapitulatif.",
            "category": "Synthèse",
            "recommended": True,
        },
    ]

    return suggested_title, summary, topics



TOPICS_PROPOSAL_SYSTEM_PROMPT = """Tu es un directeur de recherche, pédagogue et stratège éditorial d'élite.
L'utilisateur te fournit un sujet pour lequel il souhaite concevoir une page web interactive extrêmement riche, didactique et complète.
Ton rôle est d'effectuer un brainstorming PANORAMIQUE ET DÉTAILLÉ, SANS TE LIMITER, EN RATISSANT AU PLUS LARGE POSSIBLE.

RÈGLE D'OR : EXPLORATION EN PROFONDEUR, THÈMES INCLUS, PROCHES ET SOUS-THÈMES TECHNIQUES/MÉTHODOLOGIQUES :
- Ne reste JAMAIS à la surface ni sur des généralités vagues !
- Pour un sujet donné (ex: "Commentaire composé" en français), tu DOIS explorer tous les outils indispensables, sous-thèmes concrets et thématiques connexes qui font la réussite du sujet :
  * Les figures de style indispensables (métaphore, métonymie, oxymore, hyperbole, chiasme, etc.) et leur interprétation
  * Le rôle de la ponctuation, du rythme, des coupes et de la typographie dans le texte
  * Les champs lexicaux, connotations et registres littéraires (pathétique, lyrique, polémique, etc.)
  * La versification et prosodie (césure, enjambement, rejets, sonorités allitérations/assonances)
  * L'étude des temps et modes verbaux, énonciation et points de vue
  * La méthode de construction du plan détaillé (axes, sous-parties, transition logique)
  * La structure de l'introduction et de la conclusion (accroche, problématique, annonce)
  * Les erreurs fatales et contresens classiques (paraphrase, absence de citations analysées, plan thématique hors-sol)
  * Des exemples réels d'analyses appliquées sur un poème, un roman ou un texte de théâtre
- Ne te limite pas en nombre : propose entre 18 et 26 thèmes et sous-thèmes concrets, précis et stimulants.
- Couvre les thèmes inclus, les techniques précises, les composantes sous-jacentes, les applications directes et les pièges.
- Marque environ 6 à 8 thèmes fondamentaux avec "recommended": true (les piliers indispensables) et tous les autres à "recommended": false pour laisser l'utilisateur piocher librement selon ses besoins.

Format de sortie STRICT : JSON pur valide, SANS AUCUN COMMENTAIRE NI MARKDOWN AUTOUR :
{
  "suggested_title": "Titre percutant et complet",
  "summary": "Résumé panoramique en 1 ou 2 phrases des composantes clés et des sous-thèmes explorés",
  "topics": [
    {
      "id": "identifiant_slug",
      "title": "Titre précis du thème ou sous-thème",
      "description": "Explication concrète de ce qui est analysé et mis en pratique",
      "category": "Catégorie claire (ex: Outils d'analyse, Méthode, Stylistique, Pièges, Structure...)",
      "recommended": true
    }
  ]
}
"""


async def propose_page_topics(
    settings: Settings,
    prompt: str,
    chat_transcript: str | None = None,
    title: str | None = None,
    page_type: str = "auto",
    target_audience: str = "general",
    model: str | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Brainstorms a wide, comprehensive list of 10-14 thematic angles for the given subject.
    Returns (suggested_title, summary, topics_list).
    """
    clean_prompt = prompt.strip()
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "google/gemini-2.5-flash"

    has_llm_key = False
    try:
        if not getattr(settings, "demo_mode", False):
            _key(settings, "llm_api_key", "du fournisseur IA")
            has_llm_key = True
    except ProviderError:
        has_llm_key = False

    if not has_llm_key or getattr(settings, "demo_mode", False):
        return _generate_fallback_topics(clean_prompt, title)

    key = _key(settings, "llm_api_key", "du fournisseur IA")

    user_query_parts = []
    if chat_transcript:
        user_query_parts.append(
            "Contexte de la conversation :\n"
            f"```\n{chat_transcript[:8000]}\n```"
        )
    if clean_prompt:
        user_query_parts.append(f"Sujet de recherche ou consigne : {clean_prompt}")
    if title:
        user_query_parts.append(f"Titre indicatif : {title}")
    if page_type and page_type != "auto":
        user_query_parts.append(f"Type de page envisagée : {page_type}")
    if target_audience and target_audience != "general":
        user_query_parts.append(f"Public cible : {target_audience}")

    user_query_parts.append(
        "Fais un brainstorming extrêmement large, approfondi et granulaire. "
        "Génère entre 18 et 26 thèmes, sous-thèmes concrets, outils techniques, figures clés, méthodes et thématiques connexes sous forme de liste JSON complète sans te brider."
    )

    full_user_prompt = "\n\n".join(user_query_parts)

    messages = [
        {"role": "system", "content": TOPICS_PROPOSAL_SYSTEM_PROMPT},
        {"role": "user", "content": full_user_prompt},
    ]

    try:
        request_payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "temperature": 0.45,
            "max_tokens": 8192,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=request_payload,
            )
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_content = payload["choices"][0]["message"]["content"].strip()

            # Strip markdown json code fences if present
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.IGNORECASE)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json).strip()

            parsed = json.loads(cleaned_json)
            s_title = str(parsed.get("suggested_title") or title or clean_prompt[:60] or "Page Web").strip()
            s_summary = str(parsed.get("summary") or "").strip()
            raw_topics = parsed.get("topics") or []

            topics: list[dict[str, Any]] = []
            for idx, item in enumerate(raw_topics):
                if not isinstance(item, dict):
                    continue
                t_title = str(item.get("title") or "").strip()
                if not t_title:
                    continue
                t_id = str(item.get("id") or slugify(t_title) or f"topic-{idx+1}").strip()
                t_desc = str(item.get("description") or "").strip()
                t_cat = str(item.get("category") or "Général").strip()
                t_rec = bool(item.get("recommended", True))
                t_det = int(item.get("detail_level", 5) or 5)
                if t_det < 1 or t_det > 10:
                    t_det = 5
                topics.append({
                    "id": t_id,
                    "title": t_title,
                    "description": t_desc,
                    "category": t_cat,
                    "recommended": t_rec,
                    "detail_level": t_det,
                })

            if len(topics) >= 4:
                return s_title, s_summary, topics

    except Exception as exc:
        _logger.warning("Erreur lors de la proposition de thèmes par IA: %s; utilisation du fallback.", exc)

    return _generate_fallback_topics(clean_prompt, title)

