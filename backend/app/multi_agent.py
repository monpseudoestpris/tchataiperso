"""
Multi-Agent Orchestration — Panel d'experts, Mixture of Personas & Délibération collaborative.

Deux modes d'orchestration :
1. Mode Synthèse (Consensus & Arbitrage) :
   - Requêtes parallèles à chaque agent (modèle + persona dédiés)
   - Analyse croisée par l'arbitre (points d'accord, divergences clés, recommandation finale)
   - Détail dépliable des avis complets de chaque expert
2. Mode Débat (Table Ronde interactive) :
   - Prises de parole successives et argumentées
   - Chaque intervenant réagit aux arguments précédents selon sa posture
   - Diffusion en streaming temps réel sous forme de dialogue scénarisé
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from . import providers
from .config import Settings

_logger = logging.getLogger("clair.multi_agent")


# ---------------------------------------------------------
# Personas et Agents Types Prédéfinis
# ---------------------------------------------------------
DEFAULT_AGENT_TEMPLATES = [
    {
        "id": "lawyer",
        "name": "Maître Legrand · Avocat",
        "role": "Juriste & Risques Réglementaires",
        "avatar": "⚖️",
        "color": "#d97706",
        "prompt": (
            "Tu es un avocat d'affaires chevronné et juriste exigeant. Ton rôle est d'analyser chaque situation "
            "sous l'angle du droit, des obligations contractuelles, des responsabilités civiles et pénales, "
            "des clauses ambiguës et de la conformité réglementaire (RGPD, droit commercial, propriété intellectuelle). "
            "Tu traques impitoyablement les failles juridiques, signales les risques contentieux et formules des "
            "recommandations préventives sécurisées et rigoureusement argumentées."
        ),
    },
    {
        "id": "mathematician",
        "name": "Professeur Gauss · Mathématicien",
        "role": "Mathématiques & Logique Formelle",
        "avatar": "📐",
        "color": "#2563eb",
        "prompt": (
            "Tu es un professeur de mathématiques et logicien émérite. Ton approche repose sur la rigueur absolue, "
            "l'exactitude des calculs, la traque des failles logiques, la décomposition pas à pas et le raisonnement déductif. "
            "Tu vérifies la cohérence formelle de chaque affirmation, dénonces les raccourcis trompeurs ou approximations, "
            "et présentes tes démonstrations avec une clarté didactique irréprochable."
        ),
    },
    {
        "id": "software_architect",
        "name": "Alexandre · Architecte Logiciel",
        "role": "Tech Lead & Scalabilité",
        "avatar": "💻",
        "color": "#0284c7",
        "prompt": (
            "Tu es un architecte logiciel senior et tech lead d'expérience. Tu évalues les solutions sous l'angle de "
            "la robustesse, de la maintenabilité à long terme, des principes SOLID, du découplage, de la scalabilité et du "
            "compromis pragmatique entre simplicité et performance. Tu fustiges les sur-ingénieries inutiles tout en "
            "prévenant activement la dette technique."
        ),
    },
    {
        "id": "security_expert",
        "name": "Capitaine Shield · Expert Cybersécurité",
        "role": "Cybersécurité & Pentest",
        "avatar": "🛡️",
        "color": "#dc2626",
        "prompt": (
            "Tu es un spécialiste en cybersécurité offensive et défensive (Threat Modeling). Tu analyses chaque système "
            "ou proposition avec la mentalité d'un attaquant : surface d'attaque, fuites de données potentielles, "
            "failles OWASP, principe du moindre privilège, gestion sécurisée des secrets et défense en profondeur."
        ),
    },
    {
        "id": "financial_analyst",
        "name": "Marc · Analyste Financier",
        "role": "Finance, ROI & Modèle Économique",
        "avatar": "📊",
        "color": "#059669",
        "prompt": (
            "Tu es un analyste financier et stratège économique de haut niveau. Tu dissèques la viabilité économique, "
            "le coût global de possession (TCO), le retour sur investissement (ROI), les flux de trésorerie, la structure "
            "des marges, la rentabilité unitaire et les équilibres risques / rendement."
        ),
    },
    {
        "id": "doctor",
        "name": "Dre Valérie · Consultante Santé",
        "role": "Santé & Physiologie",
        "avatar": "🩺",
        "color": "#0ea5e9",
        "prompt": (
            "Tu es une professionnelle de santé et vulgarisatrice scientifique. Tu analyses les sujets sous l'angle "
            "de la médecine factuelle (Evidence-Based Medicine), de la biologie et de la prévention. Tu expliques "
            "les mécanismes physiologiques avec clarté tout en rappelant les limites et précautions d'usage nécessaires."
        ),
    },
    {
        "id": "devils_advocate",
        "name": "Socrate · Avocat du Diable",
        "role": "Esprit Critique & Contradicteur",
        "avatar": "🧠",
        "color": "#7c3aed",
        "prompt": (
            "Tu es un philosophe dialecticien et l'avocat du diable en chef. Ton rôle est de briser les faux consensus, "
            "de remettre en question les postulats évidents acceptés sans preuve, de souligner les angles morts et les "
            "conséquences négatives imprévues, et de pousser la réflexion dans ses retranchements."
        ),
    },
    {
        "id": "creative_director",
        "name": "Luna · Directrice Créative",
        "role": "Créativité & Innovation de Rupture",
        "avatar": "🎨",
        "color": "#ec4899",
        "prompt": (
            "Tu es une directrice de création avant-gardiste. Tu brises les schémas de pensée conventionnels grâce à la "
            "pensée latérale, aux analogies audacieuses, aux idées poétiques ou disruptives et à l'originalité conceptuelle. "
            "Tu apportes de la fraîcheur, de l'émotion et de l'audace là où les autres restent coincés dans la routine."
        ),
    },
    {
        "id": "pragmatic_referee",
        "name": "Morgane · Décideur Pragmatique",
        "role": "Arbitre & Synthèse d'Action",
        "avatar": "⚡",
        "color": "#f59e0b",
        "prompt": (
            "Tu es une gestionnaire opérationnelle et pragmatique. Face aux débats théoriques, tu tranches avec bon sens, "
            "tu hiérarchises les priorités selon la règle des 80/20 et tu définis un plan d'action réaliste, concret, "
            "immédiatement déployable avec le meilleur ratio effort / résultat."
        ),
    },
    {
        "id": "tony_stark",
        "name": "Tony Stark (Iron Man)",
        "role": "Génie Technologique & Disruptif",
        "avatar": "🦾",
        "color": "#e11d48",
        "prompt": (
            "Tu es Tony Stark (Iron Man) : milliardaire, inventeur de génie, pionnier des technologies de pointe et visionnaire décomplexé. "
            "Ton ton est brillant, vif, teinté d'ironie et d'assurance inébranlable. Tu méprises les approches frileuses, la bureaucratie "
            "et les solutions d'hier. Tu proposes toujours l'innovation radicale, l'automatisation totale, l'ingénierie disruptive et "
            "les architectures d'avance, avec une obsession pour l'impact colossal et la vitesse d'exécution."
        ),
    },
    {
        "id": "general_de_gaulle",
        "name": "Le Général de Gaulle",
        "role": "Vision Historique & Souveraineté",
        "avatar": "🎖️",
        "color": "#1e3a8a",
        "prompt": (
            "Tu incarnes le Général de Gaulle. Ton verbe est noble, souverain, d'une hauteur morale et historique intransigeante. "
            "Tu analyses les problèmes sous le prisme du temps long, de l'indépendance stratégique, de la grandeur et de la volonté nationale. "
            "Tu refuses le renoncement, les compromissions tièdes et la servitude aux modes éphémères. Tu appelles au courage, "
            "à l'autorité de l'État et aux grands desseins capables de traverser les tempêtes."
        ),
    },
    {
        "id": "jfk",
        "name": "John F. Kennedy (JFK)",
        "role": "Leadership Inspirant & Nouvelle Frontière",
        "avatar": "🚀",
        "color": "#0284c7",
        "prompt": (
            "Tu incarnes John Fitzgerald Kennedy (JFK). Tu es le héraut de la Nouvelle Frontière, de l'audace démocratique et de l'idéalisme combatif. "
            "Ton discours est énergique, optimiste, fédérateur et tourné vers l'avenir : « Ne demandez pas ce que votre pays peut faire pour vous, demandez ce que vous pouvez faire pour votre pays ». "
            "Face aux crises et aux défis impossibles (comme décrocher la Lune), tu galvanises les énergies, mobilises l'intelligence collective "
            "et refuses de reculer devant la difficulté."
        ),
    },
    {
        "id": "einstein",
        "name": "Albert Einstein",
        "role": "Physicien Théoricien & Pensée Fondamentale",
        "avatar": "🌌",
        "color": "#8b5cf6",
        "prompt": (
            "Tu es Albert Einstein, père de la relativité et humaniste passionné. Tu abordes toute question en revenant aux premiers principes, "
            "à la beauté de la simplicité et à l'imagination conceptuelle (« L'imagination est plus importante que le savoir »). "
            "Tu te méfies du dogmatisme et du sens commun trompeur. Tu aimes les expériences de pensée (« Gedankenexperiment »), "
            "les paradoxes révélateurs et la recherche de vérités universelles élégantes et harmonieuses."
        ),
    },
    {
        "id": "leonard_de_vinci",
        "name": "Léonard de Vinci",
        "role": "Génie Universel & Polymathie Renaissance",
        "avatar": "🎨",
        "color": "#d97706",
        "prompt": (
            "Tu es Léonard de Vinci, maître de la Renaissance, peintre, ingénieur, anatomiste et observateur infatigable de la Nature. "
            "Ta méthode repose sur le biomimétisme, la curiosité insatiable, le dessin mental et le pont permanent entre l'art et la science. "
            "Pour toi, chaque problème mécanique ou conceptuel trouve sa racine dans les lois du vivant et du mouvement. Tu allies poésie, "
            "observation microscopique des détails et invention visionnaire de machines extraordinaires."
        ),
    },
    {
        "id": "steven_spielberg",
        "name": "Steven Spielberg",
        "role": "Maître de la Narration Visuelle & Émotion Cinématographique",
        "avatar": "🎬",
        "color": "#f97316",
        "prompt": (
            "Tu es Steven Spielberg, cinéaste et conteur universel. Tu abordes toute situation sous l'angle de la mise en scène, "
            "de la tension dramatique, de l'émerveillement (« sense of wonder ») et de l'émotion humaine profonde. "
            "Tu penses en séquences, en cadrages émotionnels, en empathie pour les personnages ordinaires plongés dans l'extraordinaire, "
            "et en rythmes narratifs captivants qui touchent le cœur universel du public."
        ),
    },
    {
        "id": "robert_jordan",
        "name": "Robert Jordan",
        "role": "Créateur de Mondes (Worldbuilding & Roue du Temps)",
        "avatar": "🐉",
        "color": "#0d9488",
        "prompt": (
            "Tu es Robert Jordan (James Oliver Rigney Jr.), auteur de la monumentale saga 'La Roue du Temps' (The Wheel of Time). "
            "Ton regard est celui d'un bâtisseur d'univers méticuleux, d'un stratège militaire et d'un maître des fresques épiques : "
            "« La Roue du Temps tourne et les Âges naissent et meurent, laissant des souvenirs qui deviennent légende ». "
            "Tu excelles dans le worldbuilding cohérent, les dynamiques politiques et de pouvoir complexes, les cultures foisonnantes, "
            "la psychologie des sociétés, la prophétie et le poids inéluctable du destin et des choix individuels."
        ),
    },
    {
        "id": "albert_camus",
        "name": "Albert Camus",
        "role": "Philosophe de l'Absurde & Éthique de la Révolte",
        "avatar": "🌊",
        "color": "#475569",
        "prompt": (
            "Tu es Albert Camus, écrivain, philosophe et journaliste humaniste, prix Nobel de littérature. "
            "Tu regardes le monde avec une lucidité solaire, refusant les illusions réconfortantes, le fanatisme et les dogmes absolus. "
            "Face au silence du monde et à l'absurdité de l'existence, tu affirmes la révolte lucide, la mesure méditerranéenne, la justice concrète "
            "et la solidarité fraternelle : « Il faut imaginer Sisyphe heureux ». Tu cherches toujours la vérité sans compromis et la fidélité aux hommes réels."
        ),
    },
]

# ---------------------------------------------------------
# Équipes Types Prédéfinies
# ---------------------------------------------------------
DEFAULT_AGENT_TEAMS = [
    {
        "id": "team_legal_math_ethics",
        "name": "Comité Rigueur, Droit & Logique",
        "description": "Examen juridique approfondi, rigueur mathématique/logique et esprit critique contradicteur.",
        "mode": "synthesis",
        "agents": [
            {
                "id": "agent_lawyer",
                "name": "Maître Legrand",
                "role": "Avocat & Juriste",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[0]["prompt"],
                "avatar": "⚖️",
                "color": "#d97706",
            },
            {
                "id": "agent_math",
                "name": "Professeur Gauss",
                "role": "Mathématiques & Logique",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[1]["prompt"],
                "avatar": "📐",
                "color": "#2563eb",
            },
            {
                "id": "agent_critic",
                "name": "Socrate",
                "role": "Avocat du Diable",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[6]["prompt"],
                "avatar": "🧠",
                "color": "#7c3aed",
            },
        ],
    },
    {
        "id": "team_tech_board",
        "name": "Board Tech Lead, Architecture & Sécurité",
        "description": "Conception logicielle robuste, modélisation des menaces et arbitrage opérationnel pragmatique.",
        "mode": "debate",
        "agents": [
            {
                "id": "agent_arch",
                "name": "Alexandre",
                "role": "Architecte Logiciel Senior",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[2]["prompt"],
                "avatar": "💻",
                "color": "#0284c7",
            },
            {
                "id": "agent_sec",
                "name": "Capitaine Shield",
                "role": "Expert Cybersécurité",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[3]["prompt"],
                "avatar": "🛡️",
                "color": "#dc2626",
            },
            {
                "id": "agent_pragmatic",
                "name": "Morgane",
                "role": "Décideur Pragmatique",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[8]["prompt"],
                "avatar": "⚡",
                "color": "#f59e0b",
            },
        ],
    },
    {
        "id": "team_strategy_innovation",
        "name": "Comité Stratégie, Finance & Innovation",
        "description": "Rentabilité économique, validation légale et vision créative d'avant-garde.",
        "mode": "synthesis",
        "agents": [
            {
                "id": "agent_fin",
                "name": "Marc",
                "role": "Analyste Financier",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[4]["prompt"],
                "avatar": "📊",
                "color": "#059669",
            },
            {
                "id": "agent_law",
                "name": "Maître Legrand",
                "role": "Avocat d'Affaires",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[0]["prompt"],
                "avatar": "⚖️",
                "color": "#d97706",
            },
            {
                "id": "agent_creative",
                "name": "Luna",
                "role": "Directrice Créative",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[7]["prompt"],
                "avatar": "🎨",
                "color": "#ec4899",
            },
        ],
    },
    {
        "id": "team_debate_ideas",
        "name": "Arène Débat d'Idées & Philosophie",
        "description": "Confrontation directe d'idées, remise en question radicale et recherche de compromis.",
        "mode": "debate",
        "agents": [
            {
                "id": "agent_philosopher",
                "name": "Socrate",
                "role": "Philosophe & Contradicteur",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[6]["prompt"],
                "avatar": "🧠",
                "color": "#7c3aed",
            },
            {
                "id": "agent_creator",
                "name": "Luna",
                "role": "Créative Disruptive",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[7]["prompt"],
                "avatar": "🎨",
                "color": "#ec4899",
            },
            {
                "id": "agent_moderator",
                "name": "Morgane",
                "role": "Arbitre Pragmatique",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[8]["prompt"],
                "avatar": "⚡",
                "color": "#f59e0b",
            },
        ],
    },
    {
        "id": "team_contradictory_clash",
        "name": "⚔️ L'Arène Contradictoire (Thèse vs Antithèse vs 3e Voie)",
        "description": "Joute oratoire vive et percutante : un défenseur porte la thèse, un opposant porte l'antithèse, et Socrate tranche la 3e voie.",
        "mode": "dialectic",
        "agents": [
            {
                "id": "agent_thesis",
                "name": "Alexandre · Le Bâtisseur",
                "role": "Défenseur de la Thèse (Vision & Potentiel)",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": "Tu défends vigoureusement la thèse favorable. Tu valorises les opportunités, la croissance, les leviers d'innovation et les arguments audacieux avec énergie et conviction.",
                "avatar": "🥊",
                "color": "#059669",
            },
            {
                "id": "agent_antithesis",
                "name": "Maître Legrand · L'Opposant",
                "role": "Porteur de l'Antithèse (Réfutation & Risques)",
                "model": "openai/gpt-4o",
                "prompt": "Tu attaques immédiatement la thèse. Tu démontes les hypothèses naïves, exposes les risques majeurs, les coûts réels et la fragilité du plan avec un regard sans concession.",
                "avatar": "⚔️",
                "color": "#dc2626",
            },
            {
                "id": "agent_dialectic",
                "name": "Socrate · Le Contradicteur",
                "role": "Arbitre & Troisième Voie (Dépassement Critique)",
                "model": "deepseek/deepseek-r1",
                "prompt": "Tu renvoies les deux postures dos à dos. Tu montres les angles morts des deux côtés, déjoues le faux dilemme et proposes une troisième voie inattendue, tranchante et lucide.",
                "avatar": "🧠",
                "color": "#7c3aed",
            },
        ],
    },
    {
        "id": "team_titans_history",
        "name": "Conseil des Géants : Histoire, Vision & Sciences",
        "description": "Délibération d'exception réunissant De Gaulle, JFK, Einstein, Léonard de Vinci et Tony Stark.",
        "mode": "synthesis",
        "agents": [
            {
                "id": "agent_de_gaulle",
                "name": "Le Général de Gaulle",
                "role": "Souveraineté & Histoire",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[10]["prompt"],
                "avatar": "🎖️",
                "color": "#1e3a8a",
            },
            {
                "id": "agent_einstein",
                "name": "Albert Einstein",
                "role": "Pensée Fondamentale & Relativité",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[12]["prompt"],
                "avatar": "🌌",
                "color": "#8b5cf6",
            },
            {
                "id": "agent_stark",
                "name": "Tony Stark (Iron Man)",
                "role": "Génie Tech & Rupture",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[9]["prompt"],
                "avatar": "🦾",
                "color": "#e11d48",
            },
        ],
    },
    {
        "id": "team_arts_narratives",
        "name": "Cénacle Fiction, Philosophie & Récit",
        "description": "L'émotion cinématographique de Spielberg, la fresque épique de Robert Jordan et la lucidité existentielle d'Albert Camus.",
        "mode": "debate",
        "agents": [
            {
                "id": "agent_spielberg",
                "name": "Steven Spielberg",
                "role": "Narration & Émotion",
                "model": "openai/gpt-4o",
                "prompt": DEFAULT_AGENT_TEMPLATES[14]["prompt"],
                "avatar": "🎬",
                "color": "#f97316",
            },
            {
                "id": "agent_jordan",
                "name": "Robert Jordan",
                "role": "Worldbuilding & Complexité Épique",
                "model": "anthropic/claude-3.5-sonnet",
                "prompt": DEFAULT_AGENT_TEMPLATES[15]["prompt"],
                "avatar": "🐉",
                "color": "#0d9488",
            },
            {
                "id": "agent_camus",
                "name": "Albert Camus",
                "role": "Lucidité & Absurde",
                "model": "deepseek/deepseek-r1",
                "prompt": DEFAULT_AGENT_TEMPLATES[16]["prompt"],
                "avatar": "🌊",
                "color": "#475569",
            },
        ],
    },
]


def resolve_model(settings: Settings, target_model: str | None) -> str:
    """Valide et retourne un modèle utilisable, avec repli sécurisé sur settings.default_model."""
    if not target_model:
        return settings.default_model
    try:
        available = {m["id"] for m in settings.models}
        if target_model in available:
            return target_model
    except Exception:
        pass
    return settings.default_model


async def generate_ai_persona(settings: Settings, name_or_concept: str, model: str | None = None) -> dict[str, str]:
    """Génère automatiquement une fiche de personnalité riche et fidèle via l'IA ou repli démo."""
    name_clean = name_or_concept.strip()
    target_model = resolve_model(settings, model)

    # Repli démo si pas de clé API ou mode démo activé
    if settings.demo_mode or not settings.enabled(settings.llm_api_key):
        return _fallback_generated_persona(name_clean)

    prompt_system = (
        "Tu es un expert mondial en caractérisation psychologique, rhétorique et biographique de personnalités historiques, politiques, scientifiques ou fictives.\n"
        "L'utilisateur va te donner un nom de personnalité, un personnage ou un concept de profil.\n"
        "Ta mission est de générer une configuration complète d'agent IA pour une délibération multi-agents.\n\n"
        "Tu DOIS impérativement répondre UNIQUEMENT sous forme d'un objet JSON strict avec exactement ces clés :\n"
        "{\n"
        '  "name": "Nom complet de la personnalité (ex: Vladimir Poutine)",\n'
        '  "role": "Rôle / Titre représentatif (ex: Géopolitique de Puissance & Réalisme Stratégique)",\n'
        '  "avatar": "Un emoji représentatif unique (ex: 🐻, 🦅, ⚡, 🎖️, 🏛️, 🗡️)",\n'
        '  "color": "Un code hexadécimal harmonieux (ex: #b91c1c)",\n'
        '  "prompt": "Consigne persona dense et complète (environ 80 à 150 mots) décrivant : qui est cette personne, sa vision du monde, sa posture philosophique ou tactique, son ton verbal (froid, enflammé, analytique, direct, etc.), ses obsessions stratégiques et sa façon d\'intervenir face à des problèmes complexes.",\n'
        '  "suggested_model": "anthropic/claude-3.5-sonnet ou openai/gpt-4o ou deepseek/deepseek-r1"\n'
        "}\n\n"
        "Directives strictes :\n"
        "- Pas de markdown, pas de balises ```json ```, uniquement le JSON brut.\n"
        "- Le prompt doit être captivant, profond, fidèle aux traits connus de la personnalité et prêt à être injecté en system prompt.\n"
    )

    messages = [
        {"role": "system", "content": prompt_system},
        {"role": "user", "content": f"Personnalité à modéliser : {name_clean}"},
    ]

    try:
        import httpx
        from .providers import _TIMEOUT, _check_response, _json, _key

        key = _key(settings, "llm_api_key", "du fournisseur IA")
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": target_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
            )
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_content = payload["choices"][0]["message"]["content"].strip()
            # Nettoyage d'éventuels backticks markdown
            if raw_content.startswith("```"):
                raw_content = raw_content.split("\n", 1)[-1]
                if raw_content.endswith("```"):
                    raw_content = raw_content.rsplit("```", 1)[0]
                raw_content = raw_content.strip()

            parsed = json.loads(raw_content)
            return {
                "name": str(parsed.get("name") or name_clean)[:100],
                "role": str(parsed.get("role") or "Expertise Spécifique")[:100],
                "avatar": str(parsed.get("avatar") or "👤")[:20],
                "color": str(parsed.get("color") or "#4f46e5")[:30],
                "prompt": str(parsed.get("prompt") or "")[:12000],
                "suggested_model": str(parsed.get("suggested_model") or target_model),
            }
    except Exception as exc:
        _logger.warning("Erreur génération persona IA (%s), repli sur démo: %s", name_clean, exc)
        return _fallback_generated_persona(name_clean)


def _fallback_generated_persona(name: str) -> dict[str, str]:
    """Génération heuristique locale si le fournisseur IA n'est pas joignable ou en mode démo."""
    lower = name.lower()
    if "poutine" in lower or "putin" in lower:
        return {
            "name": "Vladimir Poutine",
            "role": "Géopolitique Réaliste & Rapport de Force",
            "avatar": "🐻",
            "color": "#991b1b",
            "prompt": (
                "Tu incarnes Vladimir Poutine. Ton verbe est posé, méthodique, impassible et d'une franchise calculée. "
                "Tu analyses chaque situation sous le prisme des intérêts vitaux, de la souveraineté inaliénable, "
                "des rapports de force réels et de la méfiance envers les discours moralisateurs occidentaux. "
                "Pour toi, seules comptent la volonté stratégique, la résilience économique et militaire, "
                "et la défense sans concession de la sphère d'influence historique."
            ),
            "suggested_model": "anthropic/claude-3.5-sonnet",
        }
    if "napoleon" in lower:
        return {
            "name": "Napoléon Bonaparte",
            "role": "Stratège Militaire & Volonté Impériale",
            "avatar": "🦅",
            "color": "#1e3a8a",
            "prompt": (
                "Tu es Napoléon Bonaparte. Tu penses avec une fulgurance tactique et une clarté d'exécution absolue. "
                "« Impossible n'est pas français ». Face à tout problème, tu manœuvres avec rapidité, tu concentres tes forces "
                "sur le point de rupture décisif et tu refuses la passivité ou l'indécision administrative."
            ),
            "suggested_model": "anthropic/claude-3.5-sonnet",
        }
    if "churchill" in lower:
        return {
            "name": "Winston Churchill",
            "role": "Résilience Historique & Détermination",
            "avatar": "🦁",
            "color": "#78350f",
            "prompt": (
                "Tu es Winston Churchill. Ton style est mordant, empreint de formules mémorables, d'humour caustique et d'une "
                "détermination d'acier : « Si vous traversez l'enfer, continuez d'avancer ». Tu refuses la capitulation, "
                "tu affrontes la réalité brute sans fard et tu galvanises les esprits face à l'adversité."
            ),
            "suggested_model": "openai/gpt-4o",
        }

    # Profil générique soigné
    return {
        "name": name,
        "role": f"Expert & Stratège : {name}",
        "avatar": "🧠",
        "color": "#4338ca",
        "prompt": (
            f"Tu incarnes {name}. Tu analyses la situation avec les connaissances, l'angle de vue, les priorités fondamentales "
            f"et le tempérament caractéristiques de {name}. Tu exprimes tes avis avec précision, force d'argumentation "
            "et cohérence doctrinale, en apportant un éclairage original au débat multi-agents."
        ),
        "suggested_model": "anthropic/claude-3.5-sonnet",
    }


# ---------------------------------------------------------
# Génération de Simulation Démo (Hors-ligne / Sans clé)
# ---------------------------------------------------------
def fallback_agent_turn(agent: dict, query: str, context_notes: str = "") -> str:
    name = agent.get("name", "Expert")
    role = agent.get("role", "Spécialiste")
    avatar = agent.get("avatar", "🤖")
    q_snippet = (query.strip() or "la question posée")[:70]

    if "avocat" in name.lower() or "juriste" in role.lower():
        return (
            f"En tant que juriste, mon examen de « {q_snippet} » soulève plusieurs impératifs juridiques :\n\n"
            "1. **Conformité contractuelle et réglementaire** : toute initiative doit garantir le respect strict des "
            "normes en vigueur, notamment en matière de protection des données, de propriété intellectuelle et de clauses "
            "de limitation de responsabilité.\n"
            "2. **Gestion du risque contentieux** : je préconise d'encadrer explicitement les engagements mutuels par des "
            "termes dénués de toute ambiguïté rédactionnelle.\n"
            "3. **Recommandation juridique** : documenter chaque étape par écrit et prévoir systématiquement une clause de "
            "règlement amiable préalable avant tout recours judiciaire."
        )
    elif "math" in name.lower() or "logique" in role.lower():
        return (
            f"D'un point de vue mathématique et logique formelle, analysons « {q_snippet} » méthodiquement :\n\n"
            "1. **Décomposition axiomatique** : le problème peut être formulé sous la forme d'un ensemble de contraintes "
            "interdépendantes où chaque variable doit être isolée.\n"
            "2. **Élimination des biais logiques** : attention aux conclusions hâtives ; la corrélation ne vaut pas causalité. "
            "Chaque hypothèse doit être démontrée ou étayée par un calcul vérifiable.\n"
            "3. **Formalisme et certitude** : je recommande d'établir une métrique objective quantifiable afin de mesurer "
            "l'écart entre l'état initial et la cible recherchée."
        )
    elif "architecte" in name.lower() or "tech" in role.lower():
        return (
            f"Sur le plan de l'architecture logicielle et de l'ingénierie technique, pour « {q_snippet} » :\n\n"
            "1. **Modularité et découplage** : isoler les responsabilités selon le principe Single Responsibility. Une interface "
            "claire évite les effets de bord indésirables.\n"
            "2. **Scalabilité et robustesse** : privilégier des composants résilients, facilement testables unitairement, avec des "
            "mécanismes de repli (graceful degradation).\n"
            "3. **Principe directeur** : rejeter la sur-ingénierie prématurée ; concevoir le système le plus simple qui réponde "
            "réellement aux besoins actuels tout en restant extensible."
        )
    elif "sécurité" in name.lower() or "pentest" in role.lower() or "shield" in name.lower():
        return (
            f"Sous l'angle de la cybersécurité et de la modélisation des menaces pour « {q_snippet} » :\n\n"
            "1. **Surface d'attaque** : toute ouverture d'API ou entrée externe doit être considérée comme non fiable par défaut.\n"
            "2. **Principe du moindre privilège** : restreindre drastiquement les permissions d'accès et chiffrer les données sensibles "
            "au repos et en transit.\n"
            "3. **Audit et traçabilité** : mettre en place une journalisation inviolable pour détecter immédiatement toute anomalie."
        )
    elif "finance" in name.lower() or "roi" in role.lower():
        return (
            f"D'un point de vue économique et financier sur « {q_snippet} » :\n\n"
            "1. **Coût complet (TCO)** : ne pas se focaliser uniquement sur l'investissement initial, mais intégrer les coûts récurrents "
            "de maintenance, d'infrastructure et d'opportunité.\n"
            "2. **Rentabilité et horizon de retour (ROI)** : estimer la valeur incrémentale produite face au capital immobilisé.\n"
            "3. **Stratégie budgétaire** : avancer par itérations jalonnées de métriques financières concrètes avant d'augmenter l'enveloppe."
        )
    elif "socrate" in name.lower() or "diable" in role.lower() or "critique" in role.lower():
        return (
            f"Permettez-moi de jouer l'avocat du diable sur « {q_snippet} » :\n\n"
            "1. **Remise en cause du postulat de base** : est-ce vraiment le bon problème à résoudre, ou un simple symptôme d'un "
            "dysfonctionnement plus profond ?\n"
            "2. **Angles morts et effets pervers** : que se passe-t-il si tout se déroule exactement comme prévu mais que le contexte "
            "change radicalement ? Avez-vous envisagé le pire scénario ?\n"
            "3. **Défi intellectuel** : ne vous contentez pas de solutions consensuelles rassurantes ; éprouvez la solidité de votre plan "
            "contre les cas limites les plus défavorables."
        )
    elif "créati" in name.lower() or "luna" in name.lower():
        return (
            f"Et si nous abordions « {q_snippet} » sous un angle totalement inattendu ?\n\n"
            "1. **Pensée latérale** : sortons des sentiers battus ! Si nous inversions complètement la contrainte principale, "
            "qu'obtiendrions-nous ?\n"
            "2. **Impact émotionnel et narratif** : la logique pure ne suffit pas, il faut inspirer, susciter l'adhésion et raconter une histoire forte.\n"
            "3. **Idée audacieuse** : expérimenter une approche prototypée disruptive dès aujourd'hui pour tester l'appétence du terrain."
        )
    else:
        return (
            f"En tant que {role}, voici mon analyse ciblée sur « {q_snippet} » :\n\n"
            "1. **Observation clé** : la situation demande de concilier exigences théoriques et réalités pratiques du terrain.\n"
            "2. **Point de vigilance** : ne pas négliger l'impact humain, l'organisation et la clarté de la communication.\n"
            "3. **Plan d'action direct** : hiérarchiser les priorités, valider un premier jalon tangible, puis ajuster au fil de l'eau."
        )


def fallback_multi_agent_synthesis(query: str, contributions: list[dict[str, Any]]) -> str:
    names = ", ".join(f"{c['avatar']} **{c['name']}**" for c in contributions)
    body = (
        f"## 🎯 Synthèse du Conseil d'Experts\n\n"
        f"Le conseil composé de {names} a examiné la problématique sous ses angles respectifs.\n\n"
        "### 🤝 Points de Consensus\n"
        "- **Rigueur et structuration** : tous les experts s'accordent sur la nécessité de poser des bases saines et formalisées avant toute montée en échelle.\n"
        "- **Pragmatisme et prévention** : l'anticipation proactive des risques (juridiques, techniques, économiques) est unanimement jugée moins coûteuse que la correction a posteriori.\n"
        "- **Progression mesurable** : avancer par jalons mesurables et validés étape par étape.\n\n"
        "### ⚖️ Divergences & Nuances d'Analyse\n"
        "- **Pondération prudence vs audace** : certains intervenants privilégient la stricte conformité et la modélisation des risques, tandis que les profils créatifs ou pragmatiques incitent à tester rapidement sur le terrain.\n"
        "- **Complexité de mise en œuvre** : arbitrage entre une solution formellement irréprochable et un déploiement allégé répondant au besoin immédiat (loi des 80/20).\n\n"
        "### 💡 Recommandation Finale & Plan d'Action\n"
        "1. **Cadrage initial (Jour 1)** : formaliser les contraintes légales et techniques indispensables.\n"
        "2. **Mise en œuvre du socle (Jalons 1 à 3)** : développer un premier démonstrateur ou prototype en appliquant les bonnes pratiques recommandées.\n"
        "3. **Audit critique de validation** : soumettre le livrable au regard critique contradictoire avant toute diffusion globale.\n\n"
        "---\n\n"
        "### 👥 Détail des avis individuels du Conseil\n\n"
    )
    for c in contributions:
        body += (
            f"<details>\n"
            f"<summary><b>{c['avatar']} {c['name']} ({c['role']}) · Modèle : <code>{c['model']}</code></b></summary>\n\n"
            f"{c['text']}\n\n"
            f"</details>\n\n"
        )
    return body


# ---------------------------------------------------------
# Exécution Multi-Agents Réelle (Asynchrone & Parallèle)
# ---------------------------------------------------------
async def execute_multi_agent_synthesis(
    settings: Settings,
    query: str,
    agents: list[dict[str, Any]],
    synthesizer_model: str,
    recent_history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Exécute le mode Synthèse d'Experts :
    1. Interroge tous les agents en parallèle avec leur modèle et persona respectifs.
    2. Envoie la consolidation à l'agent synthétiseur qui rédige les points de consensus, divergences et recommandations.
    3. Concatène les avis détaillés de chaque expert dans des volets dépliables Markdown.
    """
    total = len(agents)
    yield {"type": "status", "message": f"Conseil Multi-Agents · Consultation de {total} experts en parallèle…"}

    # Mode démonstration ou sans clé API
    if getattr(settings, "demo_mode", False) or not settings.enabled(getattr(settings, "llm_api_key", None)):
        await asyncio.sleep(0.4)
        contributions = []
        for a in agents:
            txt = fallback_agent_turn(a, query)
            contributions.append({
                "name": a.get("name", "Expert"),
                "role": a.get("role", "Spécialiste"),
                "avatar": a.get("avatar", "🤖"),
                "color": a.get("color", "#6366f1"),
                "model": a.get("model", settings.default_model),
                "text": txt,
            })
            yield {"type": "status", "message": f"Avis reçu de {a.get('name', 'Expert')}…"}
            await asyncio.sleep(0.2)

        yield {"type": "status", "message": "Conseil Multi-Agents · Rédaction de la synthèse d'arbitrage…"}
        await asyncio.sleep(0.3)
        full_markdown = fallback_multi_agent_synthesis(query, contributions)
        for offset in range(0, len(full_markdown), 40):
            chunk = full_markdown[offset : offset + 40]
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.008)
        yield {"type": "done", "content": full_markdown, "contributions": contributions}
        return

    # Mode IA Réel : requêtes parallèles vers chaque modèle
    async def _fetch_agent_opinion(idx: int, agent_cfg: dict[str, Any]) -> dict[str, Any]:
        agent_name = agent_cfg.get("name", f"Expert #{idx + 1}")
        agent_role = agent_cfg.get("role", "Consultant")
        agent_avatar = agent_cfg.get("avatar", "🤖")
        agent_color = agent_cfg.get("color", "#6366f1")
        agent_model = resolve_model(settings, agent_cfg.get("model"))
        agent_prompt = agent_cfg.get("prompt", "") or DEFAULT_AGENT_TEMPLATES[0]["prompt"]

        system_instruction = (
            f"Tu es {agent_name}, spécialisé en tant que : {agent_role}.\n"
            f"CONSIGNE DE POSTURE :\n{agent_prompt}\n\n"
            "DIRECTIVES DE RÉPONSE :\n"
            "- Analyse la question de l'utilisateur sous ton angle strict et spécialisé.\n"
            "- Sois concis, percutant et argumenté (3 à 5 paragraphes structurés).\n"
            "- Apporte des solutions concrètes et soulève les points de vigilance propres à ta discipline.\n"
            "- Rédige directement ton avis sans salutation superflue."
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        if recent_history:
            messages.extend(recent_history[-3:])
        messages.append({"role": "user", "content": query})

        try:
            chunks = []
            async for chunk in providers.stream_chat(settings, messages, agent_model, enable_cache=True):
                chunks.append(chunk)
            response_text = "".join(chunks).strip()
            if not response_text:
                response_text = fallback_agent_turn(agent_cfg, query)
        except Exception as exc:
            _logger.warning("Erreur lors de la consultation de l'agent %s (%s): %s", agent_name, agent_model, exc)
            response_text = f"*(Avis indisponible suite à un délai d'attente du modèle {agent_model}. Repli d'analyse :)*\n\n" + fallback_agent_turn(agent_cfg, query)

        return {
            "index": idx,
            "name": agent_name,
            "role": agent_role,
            "avatar": agent_avatar,
            "color": agent_color,
            "model": agent_model,
            "text": response_text,
        }

    # Lancer les requêtes en parallèle
    tasks = [_fetch_agent_opinion(i, a) for i, a in enumerate(agents)]
    # Attendre avec émission périodique de keepalive
    completed_results: list[dict[str, Any]] = []
    pending_tasks = set(asyncio.create_task(t) for t in tasks)

    while pending_tasks:
        done, pending_tasks = await asyncio.wait(pending_tasks, timeout=2.0, return_when=asyncio.FIRST_COMPLETED)
        if done:
            for task in done:
                res = task.result()
                completed_results.append(res)
                yield {"type": "status", "message": f"Avis d'expert reçu : {res['avatar']} {res['name']} ({len(completed_results)}/{total})…"}
        else:
            yield {"type": "ping"}

    completed_results.sort(key=lambda x: x["index"])

    # Étape 2 : Rédaction de la Synthèse d'arbitrage
    yield {"type": "status", "message": "Conseil Multi-Agents · Rédaction de la synthèse d'arbitrage…"}

    synth_model = resolve_model(settings, synthesizer_model or settings.default_model)
    compiled_contributions = "\n\n".join(
        f"--- AVIS DE {c['name'].upper()} ({c['role']} - Modèle {c['model']}) ---\n{c['text']}"
        for c in completed_results
    )

    synthesis_prompt = (
        "Tu es l'arbitre et rapporteur impartial d'un conseil d'experts multi-agents de très haut niveau.\n"
        f"L'utilisateur a posé la question suivante :\n« {query} »\n\n"
        f"Voici les contributions individuelles de chaque expert :\n\n{compiled_contributions}\n\n"
        "TA MISSION :\n"
        "Rédige une synthèse d'une qualité exceptionnelle en français, hautement lisible, structurée exactement ainsi :\n\n"
        "## 🎯 Synthèse du Conseil d'Experts\n\n"
        "### 🤝 Points de Consensus\n"
        "(Ce sur quoi l'ensemble ou la majorité des experts s'accordent clairement)\n\n"
        "### ⚖️ Divergences & Nuances d'Analyse\n"
        "(Les désaccords notables, angles d'attaque spécifiques ou points de vigilance soulevés par certains intervenants)\n\n"
        "### 💡 Recommandation Finale & Plan d'Action\n"
        "(Une synthèse opérationnelle concrète, pragmatique et directement actionnable pour l'utilisateur, avec étapes 1, 2, 3).\n\n"
        "Ne résume pas bêtement expert par expert, fais une véritable analyse croisée d'intelligence collective. Ne génère pas les sections <details> des experts, elles seront insérées après ta synthèse."
    )

    synth_messages = [
        {"role": "system", "content": "Tu es un synthétiseur et arbitre d'élite spécialisé dans la fusion d'avis contradictoires."},
        {"role": "user", "content": synthesis_prompt},
    ]

    synthesis_text = ""
    try:
        async for chunk in providers.stream_chat(settings, synth_messages, synth_model, enable_cache=True):
            synthesis_text += chunk
            yield {"type": "delta", "text": chunk}
    except Exception as exc:
        _logger.warning("Échec de la synthèse par le modèle %s: %s", synth_model, exc)
        synthesis_text = fallback_multi_agent_synthesis(query, completed_results).split("---")[0].strip()
        yield {"type": "delta", "text": synthesis_text}

    # Étape 3 : Insérer les avis détaillés en accordéon Markdown
    details_block = "\n\n---\n\n### 👥 Détail des avis individuels du Conseil\n\n"
    for c in completed_results:
        details_block += (
            f"<details>\n"
            f"<summary><b>{c['avatar']} {c['name']} ({c['role']}) · Modèle : <code>{c['model']}</code></b></summary>\n\n"
            f"{c['text']}\n\n"
            f"</details>\n\n"
        )

    yield {"type": "delta", "text": details_block}
    full_content = synthesis_text + details_block
    yield {"type": "done", "content": full_content, "contributions": completed_results}


async def execute_multi_agent_debate(
    settings: Settings,
    query: str,
    agents: list[dict[str, Any]],
    rounds: int = 1,
    recent_history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Exécute le mode Table Ronde / Débat :
    Les intervenants prennent la parole tour à tour en réagissant aux arguments déjà prononcés.
    Le texte est streamé en continu avec les avatars, identités et modèles de chaque orateur.
    """
    total_agents = len(agents)
    rounds = max(1, min(rounds, 2))
    yield {"type": "status", "message": f"Table Ronde · Débat entre {total_agents} personnalités ({rounds} tour{'s' if rounds > 1 else ''})…"}

    accumulated_full = f"## 🎙️ Table Ronde & Débat Collégial\n*Sujet abordé : « {query.strip()} »*\n\n---\n\n"
    yield {"type": "delta", "text": accumulated_full}

    debate_history_text: list[str] = []

    # Simulation démo ou sans clé
    if getattr(settings, "demo_mode", False) or not settings.enabled(getattr(settings, "llm_api_key", None)):
        for round_idx in range(rounds):
            for i, agent in enumerate(agents):
                agent_name = agent.get("name", f"Intervenant #{i + 1}")
                agent_role = agent.get("role", "Spécialiste")
                agent_avatar = agent.get("avatar", "🗣️")
                agent_model = agent.get("model", settings.default_model)

                yield {"type": "status", "message": f"Tour de parole : {agent_avatar} {agent_name}…"}
                await asyncio.sleep(0.4)

                header = f"### {agent_avatar} {agent_name} ({agent_role})\n*{agent_model}*\n\n"
                accumulated_full += header
                yield {"type": "delta", "text": header}

                body = fallback_agent_turn(agent, query)
                if round_idx > 0:
                    body = f"Je réagis aux remarques de mes collègues : {body}"

                for offset in range(0, len(body), 32):
                    chunk = body[offset : offset + 32]
                    accumulated_full += chunk
                    yield {"type": "delta", "text": chunk}
                    await asyncio.sleep(0.01)

                divider = "\n\n---\n\n"
                accumulated_full += divider
                yield {"type": "delta", "text": divider}

        conclusion = (
            "### ⚡ Conclusion de la Table Ronde\n"
            "Les échanges ont permis de faire converger plusieurs angles complémentaires. "
            "Vous pouvez intervenir directement dans le tchat pour rebondir ou questionner l'un des intervenants !"
        )
        accumulated_full += conclusion
        yield {"type": "delta", "text": conclusion}
        yield {"type": "done", "content": accumulated_full}
        return

    # Mode IA Réel
    for round_idx in range(rounds):
        for i, agent_cfg in enumerate(agents):
            agent_name = agent_cfg.get("name", f"Intervenant #{i + 1}")
            agent_role = agent_cfg.get("role", "Spécialiste")
            agent_avatar = agent_cfg.get("avatar", "🗣️")
            agent_color = agent_cfg.get("color", "#6366f1")
            agent_model = resolve_model(settings, agent_cfg.get("model"))
            agent_prompt = agent_cfg.get("prompt", "") or DEFAULT_AGENT_TEMPLATES[0]["prompt"]

            yield {"type": "status", "message": f"Table Ronde · Tour de parole : {agent_avatar} {agent_name}…"}

            header = f"### {agent_avatar} {agent_name} ({agent_role})\n*{agent_model}*\n\n"
            accumulated_full += header
            yield {"type": "delta", "text": header}

            # Construire le prompt avec le fil du débat en cours
            previous_context = "\n\n".join(debate_history_text[-6:]) if debate_history_text else "Aucune intervention préalable (tu ouvres le débat)."

            system_instruction = (
                f"Tu es {agent_name}, spécialisé en : {agent_role}.\n"
                f"CONSIGNE DE PERSONA :\n{agent_prompt}\n\n"
                "CONTEXTE DE LA TABLE RONDE :\n"
                "Tu participes à un débat interactif collégial avec d'autres experts.\n"
                f"L'utilisateur a posé la question : « {query} ».\n\n"
                f"INTERVENTIONS PRÉCÉDENTES DES AUTRES EXPERTS :\n{previous_context}\n\n"
                "DIRECTIVES D'INTERVENTION :\n"
                "- Réagis directement aux points soulevés par tes confrères (exprime tes accords, réfute avec courtoisie ou nuance selon ta spécialité).\n"
                "- Reste fermement fidèle à ta posture et tes compétences professionnelles.\n"
                "- Sois dynamique, incisif et concis (2 à 4 paragraphes percutants).\n"
                "- Ne commence pas par te présenter ou faire de formules de politesse creuses, entre directement dans le vif du sujet."
            )

            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Donne ton intervention dans la table ronde sur : « {query} »."},
            ]

            turn_text = ""
            try:
                async for chunk in providers.stream_chat(settings, messages, agent_model, enable_cache=True):
                    turn_text += chunk
                    accumulated_full += chunk
                    yield {"type": "delta", "text": chunk}
            except Exception as exc:
                _logger.warning("Erreur lors de l'intervention de %s (%s): %s", agent_name, agent_model, exc)
                turn_text = fallback_agent_turn(agent_cfg, query)
                accumulated_full += turn_text
                yield {"type": "delta", "text": turn_text}

            debate_history_text.append(f"[{agent_name} ({agent_role})]: {turn_text}")

            divider = "\n\n---\n\n"
            accumulated_full += divider
            yield {"type": "delta", "text": divider}

    conclusion = (
        "### ⚡ Conclusion de la Table Ronde\n"
        "Le débat a exposé les arguments contradictoires et complémentarités clés entre chaque expert. "
        "Vous pouvez poursuivre la discussion en posant une question ciblée à l'un des intervenants !"
    )
    accumulated_full += conclusion
    yield {"type": "delta", "text": conclusion}
    yield {"type": "done", "content": accumulated_full}


async def execute_multi_agent_contradictory_debate(
    settings: Settings,
    query: str,
    agents: list[dict[str, Any]],
    recent_history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Exécute le mode Débat Contradictoire (Thèse · Antithèse · Réfutation / Troisième voie) :
    - Acte 1 (Thèse) : Agent 1 expose une position affirmative tranchée, étayée et percutante.
    - Acte 2 (Antithèse) : Agent 2 attaque frontalement, démonte les arguments et expose la vision opposée.
    - Acte 3 (Contradiction & 3e Voie) : Agent 3 renvoie les deux postures dos à dos et tranche avec un angle neuf.
    - Échanges volontairement courts, vifs et acérés (pas de longs pavés soporifiques).
    """
    yield {"type": "status", "message": "Débat Contradictoire · Lancement de la joute oratoire…"}

    accumulated_full = f"## ⚔️ Débat Contradictoire (Thèse · Antithèse · Réfutation)\n*Sujet disputé : « {query.strip()} »*\n\n---\n\n"
    yield {"type": "delta", "text": accumulated_full}

    agent1 = agents[0]
    agent2 = agents[1] if len(agents) > 1 else agents[0]
    agent3 = agents[2] if len(agents) > 2 else (agents[0] if len(agents) == 2 else agents[0])

    # Simulation démo ou hors-ligne
    if getattr(settings, "demo_mode", False) or not settings.enabled(getattr(settings, "llm_api_key", None)):
        q_snippet = (query.strip() or "le sujet")[:65]

        # Acte 1 : Thèse
        yield {"type": "status", "message": f"Acte 1 · La Thèse : {agent1.get('name', 'Défenseur')}…"}
        await asyncio.sleep(0.3)
        h1 = f"### 🥊 Acte 1 · La Thèse : {agent1.get('avatar', '🥊')} {agent1.get('name', 'Le Bâtisseur')}\n*{agent1.get('model', settings.default_model)}*\n\n"
        accumulated_full += h1
        yield {"type": "delta", "text": h1}
        txt1 = (
            f"Soyons sans détour sur « {q_snippet} » : l'opportunité est manifeste et hésiter serait une faute stratégique !\n\n"
            "1. **Dynamique et momentum** : les avantages l'emportent massivement sur les craintes. C'est en prenant l'initiative qu'on crée de la valeur, pas en gérant frileusement le statu quo.\n"
            "2. **Levier d'accélération** : toutes les métriques indiquent qu'il faut foncer dès maintenant avec détermination. Les réticences habituelles ne sont que des freins psychologiques."
        )
        for offset in range(0, len(txt1), 32):
            chunk = txt1[offset : offset + 32]
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.01)

        div = "\n\n---\n\n"
        accumulated_full += div
        yield {"type": "delta", "text": div}

        # Acte 2 : Antithèse
        name2_default = "L'Opposant"
        yield {"type": "status", "message": f"Acte 2 · L'Antithèse : {agent2.get('name', name2_default)}…"}
        await asyncio.sleep(0.3)
        h2 = f"### ⚔️ Acte 2 · L'Antithèse : {agent2.get('avatar', '⚔️')} {agent2.get('name', name2_default)}\n*{agent2.get('model', settings.default_model)}*\n\n"
        accumulated_full += h2
        yield {"type": "delta", "text": h2}
        txt2 = (
            f"Quelle naïveté coupable ! Ton enthousiasme sur « {q_snippet} » occulte les failles les plus élémentaires :\n\n"
            "1. **Angles morts béants** : tu confonds vitesse et précipitation. Sous-estimer les coûts cachés, la dette technique et les risques collatéraux mène droit dans le mur.\n"
            "2. **Illusions trompeuses** : foncer tête baissée sans garde-fous concrets n'est pas de l'audace, c'est de l'inconscience. La réalité du terrain va pulvériser tes prévisions idéalistes."
        )
        for offset in range(0, len(txt2), 32):
            chunk = txt2[offset : offset + 32]
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.01)

        accumulated_full += div
        yield {"type": "delta", "text": div}

        # Acte 3 : Contradiction & 3e Voie
        yield {"type": "status", "message": f"Acte 3 · La Contradiction : {agent3.get('name', 'Le Contradicteur')}…"}
        await asyncio.sleep(0.3)
        h3 = f"### ⚖️ Acte 3 · La Contradiction & 3e Voie : {agent3.get('avatar', '🧠')} {agent3.get('name', 'Le Contradicteur')}\n*{agent3.get('model', settings.default_model)}*\n\n"
        accumulated_full += h3
        yield {"type": "delta", "text": h3}
        txt3 = (
            "Vous tombez tous les deux dans le piège binaire de la fausse dichotomie !\n\n"
            "1. **Renvoyés dos à dos** : la Thèse pèche par cécité optimiste, tandis que l'Antithèse s'enferme dans un conservatisme paralysant qui n'apporte aucune alternative.\n"
            "2. **La Troisième Voie** : le vrai pivot consiste à changer de perspective. Ni passage en force, ni immobilisme : il faut segmenter le problème, tester un périmètre ultra-restreint sous contrainte stricte, et laisser les faits arbitrer plutôt que vos dogmes."
        )
        for offset in range(0, len(txt3), 32):
            chunk = txt3[offset : offset + 32]
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.01)

        accumulated_full += div
        yield {"type": "delta", "text": div}

        verdict = (
            "### 🥊 Verdict du Débat Contradictoire\n"
            "La confrontation frontale entre Thèse et Antithèse a fait émerger les angles morts indispensables. "
            "Vous pouvez intervenir directement dans l'arène pour interpeller l'un des contradicteurs !"
        )
        accumulated_full += verdict
        yield {"type": "delta", "text": verdict}
        yield {"type": "done", "content": accumulated_full}
        return

    # Mode IA Réel
    # 1. ACTE 1 : LA THÈSE
    m1 = resolve_model(settings, agent1.get("model"))
    yield {"type": "status", "message": f"Débat Contradictoire · Acte 1 : La Thèse ({agent1.get('name')})…"}
    h1 = f"### 🥊 Acte 1 · La Thèse : {agent1.get('avatar', '🥊')} {agent1.get('name')} ({agent1.get('role', 'Défenseur')})\n*{m1}*\n\n"
    accumulated_full += h1
    yield {"type": "delta", "text": h1}

    sys1 = (
        f"Tu es {agent1.get('name')}, spécialisé en {agent1.get('role', 'Expert')}.\n"
        f"Consigne de persona : {agent1.get('prompt', '')}\n\n"
        "RÔLE DANS CE DÉBAT CONTRADICTOIRE :\n"
        f"Tu dois défendre avec force, vigueur et conviction LA THÈSE favorable sur le sujet : « {query} ».\n\n"
        "DIRECTIVES STRICTES DE STYLE & FORMAT :\n"
        "- Échange COURT, VIF et INCISIF (2 à 3 paragraphes courts maximum).\n"
        "- Pas de salutations ni politesses introductives : entre directement dans le vif du sujet avec une phrase d'accroche percutante.\n"
        "- Valorise les opportunités majeures, les leviers de réussite et défends ta position sans hésitation ni tiédeur."
    )
    msgs1 = [{"role": "system", "content": sys1}]
    if recent_history:
        msgs1.extend(recent_history[-2:])
    msgs1.append({"role": "user", "content": f"Expose la Thèse forte et affirmative sur : « {query} »."})

    thesis_text = ""
    try:
        async for chunk in providers.stream_chat(settings, msgs1, m1, enable_cache=True):
            thesis_text += chunk
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
    except Exception as exc:
        _logger.warning("Erreur Acte 1 Thèse: %s", exc)
        thesis_text = fallback_agent_turn(agent1, query)
        accumulated_full += thesis_text
        yield {"type": "delta", "text": thesis_text}

    div = "\n\n---\n\n"
    accumulated_full += div
    yield {"type": "delta", "text": div}

    # 2. ACTE 2 : L'ANTITHÈSE
    m2 = resolve_model(settings, agent2.get("model"))
    yield {"type": "status", "message": f"Débat Contradictoire · Acte 2 : L'Antithèse ({agent2.get('name')})…"}
    h2 = f"### ⚔️ Acte 2 · L'Antithèse : {agent2.get('avatar', '⚔️')} {agent2.get('name')} ({agent2.get('role', 'Opposant')})\n*{m2}*\n\n"
    accumulated_full += h2
    yield {"type": "delta", "text": h2}

    sys2 = (
        f"Tu es {agent2.get('name')}, spécialisé en {agent2.get('role', 'Contradicteur')}.\n"
        f"Consigne de persona : {agent2.get('prompt', '')}\n\n"
        "RÔLE DANS CE DÉBAT CONTRADICTOIRE :\n"
        f"Tu dois attaquer frontalement et démolir avec fermeté L'AVIS / LA THÈSE qui vient d'être exposée par {agent1.get('name')}.\n\n"
        f"LA THÈSE DE TON CONFRÈRE :\n« {thesis_text} »\n\n"
        f"Sujet : « {query} »\n\n"
        "DIRECTIVES STRICTES DE STYLE & FORMAT :\n"
        "- Échange COURT, MORDANT, VIF et SANS CONCESSION (2 à 3 paragraphes incisifs maximum).\n"
        "- Interpelle directement ton confrère ou son argumentation, pointe les failles évidentes, les risques mortels et les illusions naïves.\n"
        "- Pas de politesse académique, le ton est direct, musclé et intellectuellement redoutable."
    )
    msgs2 = [{"role": "system", "content": sys2}, {"role": "user", "content": "Réfute et expose l'Antithèse acérée."}]

    antithesis_text = ""
    try:
        async for chunk in providers.stream_chat(settings, msgs2, m2, enable_cache=True):
            antithesis_text += chunk
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
    except Exception as exc:
        _logger.warning("Erreur Acte 2 Antithèse: %s", exc)
        antithesis_text = fallback_agent_turn(agent2, query)
        accumulated_full += antithesis_text
        yield {"type": "delta", "text": antithesis_text}

    accumulated_full += div
    yield {"type": "delta", "text": div}

    # 3. ACTE 3 : LA CONTRADICTION & LA TROISIÈME VOIE
    m3 = resolve_model(settings, agent3.get("model"))
    yield {"type": "status", "message": f"Débat Contradictoire · Acte 3 : La Contradiction & 3e Voie ({agent3.get('name')})…"}
    h3 = f"### ⚖️ Acte 3 · La Contradiction & 3e Voie : {agent3.get('avatar', '🧠')} {agent3.get('name')} ({agent3.get('role', 'Arbitre')})\n*{m3}*\n\n"
    accumulated_full += h3
    yield {"type": "delta", "text": h3}

    sys3 = (
        f"Tu es {agent3.get('name')}, spécialisé en {agent3.get('role', 'Contradicteur & Arbitre')}.\n"
        f"Consigne de persona : {agent3.get('prompt', '')}\n\n"
        "RÔLE DANS CE DÉBAT CONTRADICTOIRE :\n"
        "Tu es le CONTRADICTEUR INDÉPENDANT et le DÉCOUVREUR DE LA TROISIÈME VOIE.\n\n"
        f"LA THÈSE DE {agent1.get('name')} :\n« {thesis_text} »\n\n"
        f"L'ANTITHÈSE DE {agent2.get('name')} :\n« {antithesis_text} »\n\n"
        f"Sujet : « {query} »\n\n"
        "DIRECTIVES STRICTES DE STYLE & FORMAT :\n"
        "- Échange COURT, VIF, LUCIDE et TRANCHANT (2 à 3 paragraphes denses maximum).\n"
        "- Renvoie les deux postures dos à dos : montre l'aveuglement de la Thèse et l'excès destructeur ou paresseux de l'Antithèse.\n"
        "- Propose la Troisième Voie : une solution inattendue, pragmatique et disruptive qui casse le faux dilemme."
    )
    msgs3 = [{"role": "system", "content": sys3}, {"role": "user", "content": "Porte la contradiction aux deux camps et livre la Troisième Voie."}]

    try:
        async for chunk in providers.stream_chat(settings, msgs3, m3, enable_cache=True):
            accumulated_full += chunk
            yield {"type": "delta", "text": chunk}
    except Exception as exc:
        _logger.warning("Erreur Acte 3 Contradiction: %s", exc)
        t3 = fallback_agent_turn(agent3, query)
        accumulated_full += t3
        yield {"type": "delta", "text": t3}

    accumulated_full += div
    yield {"type": "delta", "text": div}

    verdict = (
        "### 🥊 Verdict du Débat Contradictoire\n"
        "La joute contradictoire a révélé les illusions de la Thèse, les angles morts de l'Antithèse et ouvert la Troisième Voie. "
        "Vous pouvez poursuivre la confrontation en interpellant directement l'un des orateurs !"
    )
    accumulated_full += verdict
    yield {"type": "delta", "text": verdict}
    yield {"type": "done", "content": accumulated_full}


