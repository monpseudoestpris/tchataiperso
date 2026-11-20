"""Nettoyage et préparation de texte Markdown pour la synthèse vocale (TTS).

Filtre tout ce qui ne doit pas être lu à voix haute : images Markdown/HTML,
références de pages [p. X], citations numériques [1], URLs, blocs de code,
tableaux bruts, blocs LaTeX et balises de mise en forme.
"""

from __future__ import annotations

import html
import re


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
_HTML_BLOCK_DROP_RE = re.compile(
    r"<(figure|figcaption|details|script|style|svg|table)\b[^>]*>.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_HTML_IMG_RE = re.compile(r"<img\b[^>]*>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")

# Blocs de code clôturés (```...``` ou ~~~...~~~)
_FENCED_CODE_RE = re.compile(r"(?:```|~~~)[^\n]*\n.*?(?:```|~~~)", flags=re.DOTALL)
_UNCLOSED_FENCED_CODE_RE = re.compile(r"(?:```|~~~)[^\n]*\n.*$", flags=re.DOTALL)

# Blocs LaTeX multi-lignes $$...$$ ou \[...\]
_LATEX_DISPLAY_RE = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", flags=re.DOTALL)
_LATEX_INLINE_RE = re.compile(r"(?<!\\)\$(?!\s)([^$\n]+?)(?<!\s)\$")

# Images Markdown ![alt](url) (y compris éventuel titre entre guillemets)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)\n]+\)")
# Image Markdown cassée/tronquée (ex: ![alt](/api/docs/... )
_MD_BROKEN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)\n]*")

# Liens Markdown [texte](url)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\n]+)\)")

# Définitions de notes de bas de page : [^1]: ...
_FOOTNOTE_DEF_RE = re.compile(r"(?m)^\s*\[\^[^\]]+\]:.*$")

# Citations & références entre crochets : [p. 12], [p. 3-4], [pp. 2-5], [1], [1, 2], [Source 1], [^1]
_CITATION_BRACKETS_RE = re.compile(
    r"\s*\[(?:"
    r"(?:p{1,2}\.?\s*|pages?\s*)\d+(?:\s*[-–,]\s*\d+)*"
    r"|\^?[\d]+(?:\s*[-–,]\s*\d+)*"
    r"|(?:sources?|réf\.?|ref\.?|fig\.?|figure)\s*[\d,;\s-]+"
    r")\]",
    flags=re.IGNORECASE,
)

# URLs nues et chemins d'API locaux (/api/docs/...)
_BARE_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()]+", flags=re.IGNORECASE)
_LOCAL_ASSET_PATH_RE = re.compile(r"/api/[a-zA-Z0-9_./-]+")

# Lignes de séparateur horizontal Markdown (---, ***, ___)
_HR_LINE_RE = re.compile(r"(?m)^\s*(?:[-*_]\s*){3,}$")

# Code inline `...`
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# Titres Markdown (# Titre)
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")

# Citations blockquote (> ...)
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>\s?")

# Puces de liste (-, *, +, •, ▪, ▸)
_BULLET_RE = re.compile(r"(?m)^\s*(?:[-*+•▪▸])\s+")

# Tableaux Markdown (au moins une ligne avec | et une ligne séparatrice |---|)
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$")

# Caractères décoratifs / tracés ASCII non parlés
_DECORATIVE_CHARS_RE = re.compile(r"[─━│┃┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬■□▪▫●○◆◇★☆✓✔✗✘]+")

# Élisions françaises dont l'apostrophe a pu être séparée par un espace (ex: "l' **écouteur**" -> "l' écouteur")
_FRENCH_ELISION_SPACE_RE = re.compile(
    r"\b([ldjmnstcLDJMNSTC]|[qQ]u|[jJ]usqu|[lL]orsqu|[pP]uisqu|[qQ]uoiqu|[aA]ujourd)\s*'\s+([A-Za-zÀ-ÿ0-9œŒæÆ])"
)


def _strip_markdown_tables(text: str) -> str:
    """Remplace les blocs de tableaux Markdown par une courte indication parlée."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if (
            i + 1 < n
            and "|" in lines[i]
            and _TABLE_SEP_RE.match(lines[i + 1])
        ):
            # Sauter toutes les lignes du tableau
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                i += 1
            if not out or out[-1] != "Voir le tableau affiché.":
                out.append("Voir le tableau affiché.")
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _clean_inline_latex(match: re.Match[str]) -> str:
    expr = match.group(1).strip()
    expr = expr.replace(r"\times", " fois ").replace(r"\cdot", " fois ")
    expr = expr.replace(r"\pm", " plus ou moins ").replace(r"\approx", " environ ")
    expr = expr.replace(r"\leq", " inférieur ou égal à ").replace(r"\geq", " supérieur ou égal à ")
    expr = expr.replace(r"\neq", " différent de ")
    expr = re.sub(r"\\[a-zA-Z]+", " ", expr)
    expr = expr.replace("{", "").replace("}", "").replace("^", " puissance ")
    return " ".join(expr.split())


def _clean_inline_code(match: re.Match[str]) -> str:
    content = match.group(1).strip()
    if not content:
        return ""
    # Ne pas prononcer les URLs ou chemins techniques de fichiers/assets
    if (
        content.startswith(("http://", "https://", "/api/", "./", "../"))
        or content.endswith((".webp", ".png", ".jpg", ".jpeg", ".svg", ".pdf"))
    ):
        return ""
    return content


def _clean_markdown_link(match: re.Match[str]) -> str:
    label = match.group(1).strip()
    if not label:
        return ""
    # Si le libellé du lien est lui-même une URL ou une référence numérique, ne pas le lire
    if _BARE_URL_RE.fullmatch(label) or re.fullmatch(r"[\d,;\s-]+", label):
        return ""
    return label


def prepare_text_for_speech(markdown: str, *, max_chars: int = 8000) -> str:
    """Transforme une réponse Markdown en texte naturel propre pour la synthèse vocale."""
    if not markdown or not markdown.strip():
        return ""

    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Supprimer commentaires HTML, figures, images HTML, balises details/tables HTML
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _HTML_BLOCK_DROP_RE.sub(" ", text)
    text = _HTML_IMG_RE.sub(" ", text)

    # 2. Remplacer les blocs de code clôturés (pour éviter de lire du code brut)
    text = _FENCED_CODE_RE.sub("\nLe bloc de code est affiché à l'écran.\n", text)
    text = _UNCLOSED_FENCED_CODE_RE.sub("\nLe bloc de code est affiché à l'écran.\n", text)

    # 3. Supprimer les images Markdown (y compris schémas /api/docs/.../pN_figM.webp)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_BROKEN_IMAGE_RE.sub(" ", text)

    # 4. Remplacer les tableaux Markdown
    text = _strip_markdown_tables(text)

    # 5. Nettoyer les formules LaTeX
    text = _LATEX_DISPLAY_RE.sub(" Voir la formule affichée. ", text)
    text = _LATEX_INLINE_RE.sub(_clean_inline_latex, text)

    # 6. Nettoyer les liens Markdown [label](url) -> label, puis supprimer URLs et chemins d'API
    text = _MD_LINK_RE.sub(_clean_markdown_link, text)
    text = _FOOTNOTE_DEF_RE.sub("", text)
    text = _CITATION_BRACKETS_RE.sub("", text)
    text = _BARE_URL_RE.sub("", text)
    text = _LOCAL_ASSET_PATH_RE.sub("", text)

    # 7. Supprimer les balises HTML résiduelles et décoder les entités (&amp;, &nbsp;, etc.)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)

    # 8. Nettoyer le formatage Markdown (titres, gras, italique, code inline, puces, quotes)
    text = _HR_LINE_RE.sub("\n", text)
    text = _INLINE_CODE_RE.sub(_clean_inline_code, text)
    # Supprimer tout backtick résiduel (évite que le TTS prononce "guillemet simple inversé")
    text = text.replace("`", "")

    def _heading_to_sentence(match: re.Match[str]) -> str:
        heading = match.group(1).strip()
        if not heading:
            return ""
        if heading[-1] not in ".!?:":
            heading += "."
        return f"\n{heading}\n"

    text = _HEADING_RE.sub(_heading_to_sentence, text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _BULLET_RE.sub("", text)

    # Retirer gras/italique/barré sans toucher aux apostrophes ou mots composés
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("~~", "")

    # Nettoyer parenthèses vides résiduelles (ex: "voir ()" après retrait d'un lien/image)
    text = re.sub(r"\(\s*[,;:\-–]*\s*\)", "", text)
    text = re.sub(r"\[\s*[,;:\-–]*\s*\]", "", text)

    # Caractères décoratifs, apostrophes typographiques, guillemets et symboles techniques non parlés
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'").replace("\u2032", "'")
    text = re.sub(r'[«»“”„‹›"]', " ", text)
    text = _DECORATIVE_CHARS_RE.sub(" ", text)
    text = text.replace("→", " vers ").replace("⇒", " donc ")
    text = re.sub(r"[#*_~|\\^<>\[\]{}]", " ", text)

    # Normaliser les lignes et paragraphes en phrases fluides
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        # Recoller les élisions françaises séparées par le nettoyage Markdown ("l' écouteur" -> "l'écouteur")
        line = _FRENCH_ELISION_SPACE_RE.sub(r"\1'\2", line)
        # Retirer les guillemets simples isolés ('mot' -> mot) tout en gardant les apostrophes intra-mots (l'écouteur)
        line = re.sub(r"(?<![A-Za-zÀ-ÿ0-9œŒæÆ])'|'(?![A-Za-zÀ-ÿ0-9œŒæÆ])", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        # Corriger les espaces avant ponctuation simple créée par les suppressions
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([,;:])\1+", r"\1", line)
        if not line:
            continue
        # Ignorer les lignes purement ponctuées
        if not re.search(r"[A-Za-zÀ-ÿ0-9]", line):
            continue
        if line[-1] not in ".!?:;…":
            line += "."
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    if max_chars > 0 and len(result) > max_chars:
        result = _truncate_at_sentence(result, max_chars)
    return result


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    snippet = text[:max_chars].rstrip()
    last_punct = max(snippet.rfind("."), snippet.rfind("!"), snippet.rfind("?"), snippet.rfind("\n"))
    if last_punct >= max_chars // 2:
        return snippet[: last_punct + 1].strip()
    last_space = snippet.rfind(" ")
    if last_space > 0:
        return snippet[:last_space].strip() + "…"
    return snippet + "…"


def split_speech_chunks(text: str, *, max_chunk_chars: int = 1600) -> list[str]:
    """Découpe un texte déjà nettoyé en segments de taille sûre sur des fins de phrases."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chunk_chars:
        return [cleaned]

    # Découper par paragraphes puis par phrases si un paragraphe dépasse max_chunk_chars
    units: list[str] = []
    for para in cleaned.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chunk_chars:
            units.append(para)
        else:
            sentences = re.split(r"(?<=[.!?…])\s+", para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) <= max_chunk_chars:
                    units.append(sent)
                else:
                    # Ultime repli sur les espaces si une phrase géante n'a aucune ponctuation
                    words = sent.split()
                    buf = ""
                    for w in words:
                        if buf and len(buf) + 1 + len(w) > max_chunk_chars:
                            units.append(buf)
                            buf = w
                        else:
                            buf = f"{buf} {w}".strip()
                    if buf:
                        units.append(buf)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 1 + len(unit) > max_chunk_chars:
            chunks.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}".strip() if current else unit
    if current:
        chunks.append(current)
    return chunks
