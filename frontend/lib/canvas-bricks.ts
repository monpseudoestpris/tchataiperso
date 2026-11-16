export type BrickInputType = "text" | "textarea" | "number" | "select" | "json";
export type BrickOutputFormat = "markdown" | "text" | "json" | "list";
export type BrickOutputFieldType = "string" | "number" | "boolean" | "string[]";
export type BrickWidgetStyle = "auto" | "chatbot" | "scorecard" | "quiz" | "rewriter" | "cards";

export type BrickInputField = {
  key: string;
  label: string;
  type: BrickInputType;
  required: boolean;
  placeholder: string;
  default_value: string;
  options: string[];
};

export type BrickOutputField = {
  key: string;
  type: BrickOutputFieldType;
  description: string;
};

export type BrickOutputSpec = {
  format: BrickOutputFormat;
  description: string;
  fields: BrickOutputField[];
};

export type PageBrick = {
  id: string;
  name: string;
  type: "ai_agent" | "web_search_agent" | "finance_eod_agent";
  description: string;
  model: string;
  system_prompt: string;
  web_search_enabled: boolean;
  finance_data_enabled?: boolean;
  show_widget: boolean;
  widget_style?: BrickWidgetStyle;
  welcome_message?: string;
  inputs: BrickInputField[];
  output_spec: BrickOutputSpec;
};

export type BrickExecutionResult = {
  brick_id: string;
  brick_name: string;
  model_used: string;
  format: BrickOutputFormat;
  output: unknown;
  raw_text: string;
  sources: { title?: string; url?: string; snippet?: string }[];
};

export type PremadeBrickTemplate = {
  templateId: string;
  icon: string;
  category:
    | "Bot & Chat"
    | "Finance & Bourse"
    | "Texte & Traduction"
    | "Analyse & JSON"
    | "Pédagogie & Code";
  tagline: string;
  brick: PageBrick;
};

export const PREMADE_BRICK_TEMPLATES: PremadeBrickTemplate[] = [
  {
    templateId: "bot_ia_chat",
    icon: "💬",
    category: "Bot & Chat",
    tagline: "Bot IA conversationnel prêt à l'emploi avec mémoire des échanges",
    brick: {
      id: "bot_ia_chat",
      name: "Bot IA Conversationnel",
      type: "ai_agent",
      description: "Chatbot multi-tours avec historique, message d'accueil et persona configurable.",
      model: "auto",
      system_prompt:
        "Tu es un assistant conversationnel chaleureux, précis et concis intégré à l'application. Réponds en français de manière claire et utile en tenant compte de l'historique.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "chatbot",
      welcome_message: "Bonjour ! Je suis votre Bot IA intégré. Posez-moi n'importe quelle question.",
      inputs: [
        {
          key: "message",
          label: "Message",
          type: "textarea",
          required: true,
          placeholder: "Écrivez votre message au bot…",
          default_value: "",
          options: [],
        },
        {
          key: "style_reponse",
          label: "Ton",
          type: "select",
          required: false,
          placeholder: "",
          default_value: "Clair & concis",
          options: ["Clair & concis", "Expert détaillé", "Pédagogique", "Créatif"],
        },
      ],
      output_spec: {
        format: "markdown",
        description: "Réponse conversationnelle naturelle tenant compte des messages précédents.",
        fields: [],
      },
    },
  },
  {
    templateId: "simulateur_roleplay",
    icon: "🎭",
    category: "Bot & Chat",
    tagline: "Simulateur d'entretien, pitch client ou négociation en jeu de rôle",
    brick: {
      id: "simulateur_roleplay",
      name: "Simulateur Entretien & Roleplay",
      type: "ai_agent",
      description: "Bot de mise en situation qui incarne un recruteur, client ou examinateur et coache vos réponses.",
      model: "auto",
      system_prompt:
        "Tu es un simulateur de jeu de rôle réaliste. Reste dans le rôle choisi dans `scenario`, réagis naturellement à l'utilisateur, puis termine par une courte ligne `💡 Conseil coach : ...`.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "chatbot",
      welcome_message: "Choisissez un scénario ci-dessus et lancez la conversation pour commencer la simulation !",
      inputs: [
        {
          key: "message",
          label: "Votre réplique",
          type: "textarea",
          required: true,
          placeholder: "Ex: Bonjour, je suis ravi de vous présenter notre solution…",
          default_value: "",
          options: [],
        },
        {
          key: "scenario",
          label: "Scénario",
          type: "select",
          required: true,
          placeholder: "",
          default_value: "Entretien d'embauche",
          options: ["Entretien d'embauche", "Pitch client / vente", "Oral d'examen", "Négociation commerciale"],
        },
      ],
      output_spec: {
        format: "markdown",
        description: "Réplique immersive du personnage + mini-conseil de coaching.",
        fields: [],
      },
    },
  },
  {
    templateId: "web_research_agent",
    icon: "🌐",
    category: "Bot & Chat",
    tagline: "Veille web en direct via SearXNG + synthèse sourcée",
    brick: {
      id: "agent_veille_web",
      name: "Veille & Fact-Checker Web",
      type: "web_search_agent",
      description: "Interroge le web en temps réel via SearXNG puis synthétise la réponse avec le modèle choisi.",
      model: "auto",
      system_prompt:
        "Tu es un analyste de veille. Appuie-toi uniquement sur les sources web collectées pour produire une synthèse factuelle, datée et sourcée.",
      web_search_enabled: true,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "requete",
          label: "Sujet ou affirmation à vérifier",
          type: "text",
          required: true,
          placeholder: "Ex: Dernières avancées batteries solides 2026",
          default_value: "",
          options: [],
        },
      ],
      output_spec: {
        format: "markdown",
        description: "Synthèse factuelle avec références issues de la recherche web.",
        fields: [],
      },
    },
  },
  {
    templateId: "studio_reecriture",
    icon: "✍️",
    category: "Texte & Traduction",
    tagline: "Corrige, reformule ou adapte le ton avec copie en 1 clic",
    brick: {
      id: "studio_reecriture",
      name: "Studio Réécriture & Correction",
      type: "ai_agent",
      description: "Corrige orthographe/syntaxe et adapte le style selon l'objectif choisi.",
      model: "auto",
      system_prompt:
        "Tu es un éditeur professionnel. Réécris le texte en atteignant précisément l'objectif demandé sans trahir le sens original.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "rewriter",
      inputs: [
        {
          key: "texte",
          label: "Texte à réécrire",
          type: "textarea",
          required: true,
          placeholder: "Collez votre brouillon, email ou paragraphe…",
          default_value: "",
          options: [],
        },
        {
          key: "objectif",
          label: "Objectif",
          type: "select",
          required: true,
          placeholder: "",
          default_value: "Ton professionnel",
          options: [
            "Corriger les fautes uniquement",
            "Ton professionnel",
            "Raccourcir & synthétiser",
            "Ton persuasif",
            "Simplifier pour tout public",
          ],
        },
      ],
      output_spec: {
        format: "json",
        description: "Texte prêt à copier accompagné des corrections apportées.",
        fields: [
          { key: "version_corrigee", type: "string", description: "Texte final réécrit" },
          { key: "ton_applique", type: "string", description: "Style retenu" },
          { key: "ameliorations", type: "string[]", description: "Principales améliorations effectuées" },
        ],
      },
    },
  },
  {
    templateId: "traducteur_ia",
    icon: "🌍",
    category: "Texte & Traduction",
    tagline: "Traduction idiomatique multilingue avec notes de nuance",
    brick: {
      id: "traducteur_ia",
      name: "Traducteur Contextuel Polyglotte",
      type: "ai_agent",
      description: "Traduit naturellement dans la langue et le registre souhaités avec expressions clés.",
      model: "auto",
      system_prompt:
        "Tu es un traducteur littéraire et technique bilingue. Produis une traduction naturelle et fidèle dans la langue et le registre cibles.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "rewriter",
      inputs: [
        {
          key: "texte",
          label: "Texte source",
          type: "textarea",
          required: true,
          placeholder: "Saisissez le texte à traduire…",
          default_value: "",
          options: [],
        },
        {
          key: "langue_cible",
          label: "Langue cible",
          type: "select",
          required: true,
          placeholder: "",
          default_value: "Anglais",
          options: ["Anglais", "Espagnol", "Allemand", "Italien", "Portugais", "Japonais", "Français"],
        },
        {
          key: "registre",
          label: "Registre",
          type: "select",
          required: false,
          placeholder: "",
          default_value: "Courant naturel",
          options: ["Courant naturel", "Soutenu / Affaires", "Technique", "Familier"],
        },
      ],
      output_spec: {
        format: "json",
        description: "Traduction fluide et vocabulaire remarquable.",
        fields: [
          { key: "traduction", type: "string", description: "Traduction finale dans la langue cible" },
          { key: "notes_nuances", type: "string[]", description: "Choix de traduction et nuances culturelles" },
          { key: "expressions_cles", type: "string[]", description: "Expressions idiomatiques utiles" },
        ],
      },
    },
  },
  {
    templateId: "extracteur_json",
    icon: "📊",
    category: "Analyse & JSON",
    tagline: "Extrait résumé, score et actions structurées d'un texte",
    brick: {
      id: "extracteur_json",
      name: "Extracteur KPI & Synthèse JSON",
      type: "ai_agent",
      description: "Transforme un texte brut en objet JSON structuré (résumé, score, points clés, actions).",
      model: "auto",
      system_prompt:
        "Tu es un moteur d'extraction structurée. Extrais fidèlement les informations clés du texte fourni et respecte strictement le schéma JSON demandé.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "contenu",
          label: "Texte ou document à analyser",
          type: "textarea",
          required: true,
          placeholder: "Collez ici le texte, les notes ou les données…",
          default_value: "",
          options: [],
        },
        {
          key: "objectif",
          label: "Angle d'analyse",
          type: "text",
          required: false,
          placeholder: "Ex: Décisions et risques prioritaires",
          default_value: "Synthèse opérationnelle",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Objet JSON structuré prêt pour alimenter graphiques, cartes ou tableaux.",
        fields: [
          { key: "resume", type: "string", description: "Synthèse concise en 2-3 phrases" },
          { key: "score_pertinence", type: "number", description: "Score estimé de 0 à 100" },
          { key: "points_cles", type: "string[]", description: "Liste des points essentiels extraits" },
          { key: "actions", type: "string[]", description: "Prochaines actions recommandées" },
        ],
      },
    },
  },
  {
    templateId: "synthese_reunion",
    icon: "📋",
    category: "Analyse & JSON",
    tagline: "Transforme des notes en vrac en compte-rendu + plan d'action",
    brick: {
      id: "synthese_reunion",
      name: "Synthétiseur de Réunion",
      type: "ai_agent",
      description: "Structuration automatique des décisions, responsables et prochaines étapes.",
      model: "auto",
      system_prompt:
        "Tu es un chef de projet rigoureux. Transforme ces notes de réunion brutes en compte-rendu clair, décisions actées et plan d'action concret.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "notes_brutes",
          label: "Notes ou transcription brute",
          type: "textarea",
          required: true,
          placeholder: "Collez vos notes de réunion ou points discutés…",
          default_value: "",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Compte-rendu structuré actionnable.",
        fields: [
          { key: "compte_rendu", type: "string", description: "Résumé exécutif de la réunion" },
          { key: "decisions", type: "string[]", description: "Décisions validées" },
          { key: "plan_actions", type: "string[]", description: "Actions concrètes (Quoi / Qui / Quand)" },
          { key: "points_ouverts", type: "string[]", description: "Questions restant à trancher" },
        ],
      },
    },
  },
  {
    templateId: "brainstorm_idees",
    icon: "💡",
    category: "Analyse & JSON",
    tagline: "Génère des idées créatives sous contrainte avec première étape",
    brick: {
      id: "brainstorm_idees",
      name: "Fabrique à Idées & Stratégie",
      type: "ai_agent",
      description: "Explore des angles originaux et propose des pistes actionnables immédiatement.",
      model: "auto",
      system_prompt:
        "Tu es un directeur innovation et produit. Propose des idées concrètes, différenciantes et réalistes en respectant la contrainte donnée.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "problematique",
          label: "Problématique ou projet",
          type: "textarea",
          required: true,
          placeholder: "Ex: Fidéliser les utilisateurs d'une app éducative…",
          default_value: "",
          options: [],
        },
        {
          key: "contrainte",
          label: "Contrainte principale",
          type: "text",
          required: false,
          placeholder: "Ex: Budget zéro, réalisable en 1 semaine",
          default_value: "Simple et rapide à prototyper",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Pistes créatives structurées.",
        fields: [
          { key: "angle_strategique", type: "string", description: "Positionnement recommandé" },
          { key: "score_originalite", type: "number", description: "Indice d'originalité sur 100" },
          { key: "idees", type: "string[]", description: "5 idées concrètes et différenciantes" },
          { key: "premiere_etape", type: "string", description: "Action de test en moins de 24h" },
        ],
      },
    },
  },
  {
    templateId: "generateur_quiz",
    icon: "🎯",
    category: "Pédagogie & Code",
    tagline: "Génère un QCM interactif cliquable avec score en direct",
    brick: {
      id: "generateur_quiz",
      name: "Générateur de Quiz QCM",
      type: "ai_agent",
      description: "Crée un quiz interactif à choix multiples directement jouable dans l'application.",
      model: "auto",
      system_prompt:
        'Tu es un concepteur pédagogique. Génère exactement 4 questions QCM dans `questions`. Chaque élément de `questions` DOIT impérativement respecter le format exact sur une ligne : "Question ? | A) Option A | B) Option B | C) Option C | D) Option D | Réponse: A | Explication: Courte justification".',
      web_search_enabled: false,
      show_widget: false,
      widget_style: "quiz",
      inputs: [
        {
          key: "sujet",
          label: "Thème ou leçon du quiz",
          type: "text",
          required: true,
          placeholder: "Ex: La photosynthèse, JavaScript async/await…",
          default_value: "",
          options: [],
        },
        {
          key: "difficulte",
          label: "Niveau",
          type: "select",
          required: true,
          placeholder: "",
          default_value: "Moyen",
          options: ["Facile", "Moyen", "Avancé"],
        },
      ],
      output_spec: {
        format: "json",
        description: "Quiz QCM prêt à afficher en interface cliquable.",
        fields: [
          { key: "titre_quiz", type: "string", description: "Titre accrocheur du quiz" },
          {
            key: "questions",
            type: "string[]",
            description: "4 questions au format 'Question | A) ... | B) ... | C) ... | D) ... | Réponse: X | Explication: ...'",
          },
          { key: "conseil_revision", type: "string", description: "Conseil clé pour progresser sur ce thème" },
        ],
      },
    },
  },
  {
    templateId: "coach_evaluateur",
    icon: "🧑‍🏫",
    category: "Pédagogie & Code",
    tagline: "Évalue une réponse utilisateur avec note /20 et axes de progrès",
    brick: {
      id: "coach_evaluateur",
      name: "Coach & Évaluateur Noté",
      type: "ai_agent",
      description: "Corrige une production utilisateur avec note /20, validation et conseils ciblés.",
      model: "auto",
      system_prompt:
        "Tu es un coach exigeant et bienveillant. Évalue la réponse fournie au regard de l'énoncé et donne une note juste sur 20 ainsi qu'un retour constructif.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "scorecard",
      inputs: [
        {
          key: "enonce",
          label: "Consigne ou question",
          type: "text",
          required: true,
          placeholder: "Ex: Expliquer le principe de la photosynthèse",
          default_value: "",
          options: [],
        },
        {
          key: "reponse",
          label: "Réponse de l'utilisateur",
          type: "textarea",
          required: true,
          placeholder: "Réponse soumise dans l'application…",
          default_value: "",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Verdict structuré avec score /20 et conseils.",
        fields: [
          { key: "note_sur_20", type: "number", description: "Note attribuée sur 20" },
          { key: "valide", type: "boolean", description: "Vrai si l'objectif est atteint (>= 10/20)" },
          { key: "feedback", type: "string", description: "Commentaire pédagogique détaillé" },
          { key: "axes_progres", type: "string[]", description: "Conseils concrets d'amélioration" },
        ],
      },
    },
  },
  {
    templateId: "expliqueur_feynman",
    icon: "🧠",
    category: "Pédagogie & Code",
    tagline: "Vulgarise n'importe quel concept avec analogie et piège à éviter",
    brick: {
      id: "expliqueur_feynman",
      name: "Vulgarisateur Feynman",
      type: "ai_agent",
      description: "Rend limpide un concept complexe grâce à une analogie du quotidien adaptée au public.",
      model: "auto",
      system_prompt:
        "Tu appliques la méthode Feynman : explique simplement sans jargon inutile, trouve une analogie mémorable et signale l'erreur classique à éviter.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "concept",
          label: "Concept à expliquer",
          type: "text",
          required: true,
          placeholder: "Ex: Les transformeurs en IA, l'entropie, les promesses JS…",
          default_value: "",
          options: [],
        },
        {
          key: "public_cible",
          label: "Public cible",
          type: "select",
          required: true,
          placeholder: "",
          default_value: "Lycéen / Étudiant",
          options: ["Enfant de 10 ans", "Lycéen / Étudiant", "Décideur pressé", "Ingénieur"],
        },
      ],
      output_spec: {
        format: "json",
        description: "Explication claire, analogie concrète et étapes clés.",
        fields: [
          { key: "explication_simple", type: "string", description: "Explication limpide adaptée au public" },
          { key: "analogie_concrete", type: "string", description: "Comparaison parlante du quotidien" },
          { key: "etapes_cles", type: "string[]", description: "Mécanisme découpé en 3-4 étapes" },
          { key: "piege_a_eviter", type: "string", description: "Idée reçue ou confusion fréquente" },
        ],
      },
    },
  },
  {
    templateId: "auditeur_code",
    icon: "🛡️",
    category: "Pédagogie & Code",
    tagline: "Audite un extrait de code (bugs, sécurité, version corrigée)",
    brick: {
      id: "auditeur_code",
      name: "Auditeur Code & Sécurité",
      type: "ai_agent",
      description: "Détecte les failles (XSS, injection, edge-cases), note la qualité /100 et propose un correctif.",
      model: "auto",
      system_prompt:
        "Tu es un ingénieur AppSec senior. Inspecte le code fourni, repère les bugs et vulnérabilités, attribue un score qualité/sécurité sur 100 et fournis la version corrigée.",
      web_search_enabled: false,
      show_widget: false,
      widget_style: "scorecard",
      inputs: [
        {
          key: "code",
          label: "Extrait de code à auditer",
          type: "textarea",
          required: true,
          placeholder: "Collez la fonction, requête SQL ou composant…",
          default_value: "",
          options: [],
        },
        {
          key: "langage",
          label: "Langage",
          type: "select",
          required: false,
          placeholder: "",
          default_value: "Auto",
          options: ["Auto", "JavaScript / TypeScript", "Python", "SQL", "HTML / CSS", "Autre"],
        },
      ],
      output_spec: {
        format: "json",
        description: "Rapport d'audit sécurité + code corrigé.",
        fields: [
          { key: "score_qualite", type: "number", description: "Score qualité et sécurité de 0 à 100" },
          { key: "securise", type: "boolean", description: "Vrai si aucune faille critique n'est présente" },
          { key: "problemes_detectes", type: "string[]", description: "Bugs, risques ou mauvaises pratiques" },
          { key: "code_corrige", type: "string", description: "Version durcie et corrigée du code" },
        ],
      },
    },
  },
  {
    templateId: "finance_eod_indicateurs",
    icon: "📈",
    category: "Finance & Bourse",
    tagline: "Cours EODHD/Yahoo en direct + RSI(14), SMA(20/50), MACD & niveaux",
    brick: {
      id: "finance_eod_indicateurs",
      name: "Cotation EOD & Indicateurs",
      type: "finance_eod_agent",
      description: "Récupère les cotations EODHD/Yahoo Finance réelles, calcule RSI, SMA20/50 et MACD puis synthétise la tendance.",
      model: "auto",
      system_prompt:
        "Tu es un analyste technique quantitatif. Appuie-toi strictement sur les données EOD et indicateurs techniques calculés (SMA20, SMA50, RSI14, MACD, variation) fournis dans le contexte.",
      web_search_enabled: false,
      finance_data_enabled: true,
      show_widget: false,
      widget_style: "scorecard",
      inputs: [
        {
          key: "symbole",
          label: "Ticker ou Entreprise",
          type: "text",
          required: true,
          placeholder: "Ex: AAPL, MC.PA, Stellantis, MSFT",
          default_value: "AAPL",
          options: [],
        },
        {
          key: "horizon",
          label: "Horizon graphique",
          type: "select",
          required: false,
          placeholder: "",
          default_value: "3 mois",
          options: ["1 mois", "3 mois", "6 mois", "1 an"],
        },
      ],
      output_spec: {
        format: "json",
        description: "Cours réel, indicateurs techniques et niveaux clés",
        fields: [
          { key: "ticker", type: "string", description: "Symbole boursier résolu" },
          { key: "prix_actuel", type: "number", description: "Dernier cours connu" },
          { key: "variation_pct", type: "number", description: "Variation en % sur la période" },
          { key: "rsi_14", type: "number", description: "Valeur RSI 14 jours" },
          { key: "tendance_technique", type: "string", description: "Haussière, Neutre ou Baissière" },
          { key: "niveaux_cles", type: "string[]", description: "Signaux SMA/MACD et supports/résistances" },
          { key: "synthese_eod", type: "string", description: "Lecture technique synthétique" },
        ],
      },
    },
  },
  {
    templateId: "finance_fondamentaux",
    icon: "🏦",
    category: "Finance & Bourse",
    tagline: "Analyse fondamentale (PER, marges, ROE, dette, valorisation)",
    brick: {
      id: "finance_fondamentaux",
      name: "Analyste Fondamental Bourse",
      type: "finance_eod_agent",
      description: "Évalue la valorisation, la rentabilité et la solidité bilancielle à partir des stats Yahoo/EODHD.",
      model: "auto",
      system_prompt:
        "Tu es un analyste financier fondamental. Évalue objectivement les ratios (PER, EV/EBITDA, marges, ROE, dette/capitaux propres) à partir des données boursières fournies.",
      web_search_enabled: false,
      finance_data_enabled: true,
      show_widget: false,
      widget_style: "scorecard",
      inputs: [
        {
          key: "symbole",
          label: "Ticker ou Entreprise",
          type: "text",
          required: true,
          placeholder: "Ex: LVMH, NVDA, AIR.PA",
          default_value: "MSFT",
          options: [],
        },
        {
          key: "angle",
          label: "Angle d'analyse",
          type: "select",
          required: false,
          placeholder: "",
          default_value: "Analyse complète",
          options: [
            "Analyse complète",
            "Valorisation & Ratios",
            "Qualité & Rentabilité",
            "Santé financière & Dette",
          ],
        },
      ],
      output_spec: {
        format: "json",
        description: "Score fondamental /100, verdict et ratios clés",
        fields: [
          { key: "score_fondamental", type: "number", description: "Score de solidité fondamentale sur 100" },
          { key: "valorisation_verdict", type: "string", description: "Sous-évaluée / Juste prix / Chère" },
          { key: "ratios_cles", type: "string[]", description: "Principaux ratios chiffrés observés" },
          { key: "forces", type: "string[]", description: "Atouts financiers majeurs" },
          { key: "risques", type: "string[]", description: "Points de fragilité ou vigilance" },
        ],
      },
    },
  },
  {
    templateId: "finance_moat_ia",
    icon: "🏰",
    category: "Finance & Bourse",
    tagline: "Évalue le MOAT (avantage concurrentiel durable) & signaux chiffrés",
    brick: {
      id: "finance_moat_ia",
      name: "Évaluateur MOAT Boursier",
      type: "finance_eod_agent",
      description: "Croise les signaux quantitatifs de MOAT (marges, ROE) avec une analyse stratégique Buffett/McKinsey.",
      model: "auto",
      system_prompt:
        "Tu es un analyste stratégique inspiré de Warren Buffett. À partir des signaux MOAT quantitatifs et fondamentaux fournis, évalue la durabilité de l'avantage concurrentiel (Wide / Narrow / None).",
      web_search_enabled: false,
      finance_data_enabled: true,
      show_widget: false,
      widget_style: "scorecard",
      inputs: [
        {
          key: "symbole",
          label: "Ticker ou Entreprise",
          type: "text",
          required: true,
          placeholder: "Ex: ASML, MC.PA, AAPL",
          default_value: "ASML",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Notation MOAT, score /100 et thèse d'investissement",
        fields: [
          { key: "moat_rating", type: "string", description: "Wide, Narrow ou None" },
          { key: "score_moat", type: "number", description: "Score MOAT de 0 à 100" },
          { key: "piliers_forts", type: "string[]", description: "Sources d'avantage concurrentiel" },
          { key: "menaces_competitives", type: "string[]", description: "Risques d'érosion du MOAT" },
          { key: "these_investissement", type: "string", description: "Synthèse stratégique long terme" },
        ],
      },
    },
  },
  {
    templateId: "finance_actualites_ia",
    icon: "📰",
    category: "Finance & Bourse",
    tagline: "Veille boursière temps réel (SearXNG + EOD) & sentiment marché",
    brick: {
      id: "finance_actualites_ia",
      name: "Veille Boursière & Catalyseurs",
      type: "finance_eod_agent",
      description: "Combine les données de marché EODHD/Yahoo avec la recherche web SearXNG pour détecter les catalyseurs récents.",
      model: "auto",
      system_prompt:
        "Tu es un stratégiste marché. Croise le contexte boursier fourni et les actualités web collectées pour résumer le sentiment de marché et les catalyseurs à court/moyen terme.",
      web_search_enabled: true,
      finance_data_enabled: true,
      show_widget: false,
      widget_style: "cards",
      inputs: [
        {
          key: "symbole",
          label: "Ticker, Indice ou Entreprise",
          type: "text",
          required: true,
          placeholder: "Ex: Stellantis, CAC 40, NVDA",
          default_value: "NVDA",
          options: [],
        },
      ],
      output_spec: {
        format: "json",
        description: "Sentiment de marché, catalyseurs et synthèse actualités",
        fields: [
          { key: "sentiment_marche", type: "string", description: "Positif, Neutre ou Prudent/Négatif" },
          { key: "score_sentiment", type: "number", description: "Indice de sentiment de 0 à 100" },
          { key: "catalyseurs", type: "string[]", description: "Événements et annonces clés récentes" },
          { key: "points_vigilance", type: "string[]", description: "Risques ou incertitudes signalés" },
          { key: "resume_actualites", type: "string", description: "Synthèse claire de l'actualité boursière" },
        ],
      },
    },
  },
];

export function slugifyBrickId(value: string, fallback = "agent_ia"): string {
  const cleaned = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned.slice(0, 50) || fallback;
}

export function createBrickFromTemplate(
  template: PremadeBrickTemplate,
  existingBricks: PageBrick[],
): PageBrick {
  const usedIds = new Set(existingBricks.map(b => b.id));
  const baseId = template.brick.id;
  let candidateId = baseId;
  let counter = 2;
  while (usedIds.has(candidateId)) {
    candidateId = `${baseId}_${counter}`;
    counter += 1;
  }
  const cloned = JSON.parse(JSON.stringify(template.brick)) as PageBrick;
  cloned.id = candidateId;
  if (candidateId !== baseId) {
    cloned.name = `${cloned.name} ${counter - 1}`;
  }
  return cloned;
}

export function generateBrickUsageSnippet(brick: PageBrick): string {
  const sampleInputs: Record<string, string> = {};
  for (const field of brick.inputs) {
    sampleInputs[field.key] = field.default_value || field.placeholder || `valeur_${field.key}`;
  }
  const argsJson = JSON.stringify(sampleInputs, null, 2);
  return `// Appel de la brique "${brick.name}" (${brick.model || "auto"})
const result = await window.clair.runBrick(${JSON.stringify(brick.id)}, ${argsJson});
console.log("Sortie attendue (${brick.output_spec.format}):", result.output);`;
}

export function buildBrickWiringPrompt(brick: PageBrick, filePaths: string[]): string {
  const inputLines = brick.inputs
    .map(
      f =>
        `  - \`${f.key}\` (${f.type}${f.required ? ", requis" : ""}) : ${f.label}${f.placeholder ? ` (ex: ${f.placeholder})` : ""}`,
    )
    .join("\n");

  const outSpec = brick.output_spec;
  const outputDesc =
    outSpec.format === "json" && outSpec.fields.length > 0
      ? `JSON structuré avec les propriétés :\n${outSpec.fields.map(o => `  - \`result.output.${o.key}\` (${o.type}) : ${o.description || o.key}`).join("\n")}`
      : `${outSpec.format}${outSpec.description ? ` — ${outSpec.description}` : ""}`;

  const filesHint = filePaths.length ? `dans le projet existant (${filePaths.join(", ")})` : "dans une application web multi-fichiers";

  return [
    `Intègre et câble directement la brique Agent IA « ${brick.name} » (\`id: "${brick.id}"\`) ${filesHint}.`,
    `Dans le code JavaScript de l'application, utilise l'API native \`await window.clair.runBrick("${brick.id}", inputs)\` (ne demande aucune clé API à l'utilisateur).`,
    inputLines ? `Entrées à collecter depuis l'interface et passer à la brique :\n${inputLines}` : "",
    `Sortie renvoyée par \`result.output\` à afficher élégamment dans l'interface :\n${outputDesc}`,
    `Ajoute les contrôles UI nécessaires (formulaire ou bouton d'action, état de chargement et affichage structuré du résultat) en mettant à jour les fichiers concernés avec \`path="..."\`.`,
  ]
    .filter(Boolean)
    .join("\n\n");
}

function escapeHtmlAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Inserts a turnkey `<div data-clair-brick="...">` widget into an existing Canvas `index.html`,
 * or generates a complete styled starter page when no HTML file exists yet.
 */
export function injectBrickIntoCanvasHtml(
  existingHtml: string | null | undefined,
  brick: PageBrick,
  appTitle = "Mon Application IA",
): string {
  const safeId = escapeHtmlAttr(brick.id);
  const safeName = escapeHtmlAttr(brick.name);
  const safeTitle = escapeHtmlAttr(appTitle || brick.name);

  if (!existingHtml || !existingHtml.trim()) {
    return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${safeTitle}</title>
  <style>
    :root {
      color-scheme: light;
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(135deg, #f8fafc 0%, #e0f2fe 100%);
      color: #0f172a;
      padding: 28px 16px;
      box-sizing: border-box;
    }
    .clair-app-shell {
      max-width: 820px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .clair-app-hero {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 16px;
      padding: 20px 24px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }
    .clair-app-hero h1 {
      margin: 0 0 6px;
      font-size: 1.45rem;
    }
    .clair-app-hero p {
      margin: 0;
      font-size: 0.92rem;
      color: #475569;
    }
  </style>
</head>
<body>
  <main class="clair-app-shell">
    <header class="clair-app-hero">
      <h1>${safeTitle}</h1>
      <p>Application propulsée par les briques IA cLAIr — prête à l'emploi et intégrable dans Mes Apps.</p>
    </header>
    <section data-clair-brick="${safeId}" aria-label="${safeName}"></section>
  </main>
</body>
</html>`;
  }

  // Already mounted? Keep existing container
  const alreadyPresent = new RegExp(`data-clair-brick=["']${brick.id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`, "i");
  if (alreadyPresent.test(existingHtml)) {
    return existingHtml;
  }

  const block = `\n  <section style="max-width:860px;margin:20px auto;padding:0 16px;" data-clair-brick="${safeId}" aria-label="${safeName}"></section>\n`;
  if (/<\/main>/i.test(existingHtml)) {
    return existingHtml.replace(/<\/main>/i, () => `${block}</main>`);
  }
  if (/<\/body>/i.test(existingHtml)) {
    return existingHtml.replace(/<\/body>/i, () => `${block}</body>`);
  }
  return `${existingHtml}\n${block}`;
}

/**
 * Generates the runtime script tag for CodeCanvas previews so `window.clair.runBrick(...)`
 * and turnkey specialized widgets (`chatbot`, `quiz`, `rewriter`, `scorecard`, `cards`)
 * work immediately before saving to cLAIr Pages.
 */
export function buildBricksClientRuntimeScript(bricks: PageBrick[]): string {
  const serialized = JSON.stringify(bricks || []).replace(/<\//g, "<\\/");
  return `<script id="clair-bricks-runtime-script">
(function() {
  if (typeof window === 'undefined') return;
  var BRICKS = ${serialized};
  window.__CLAIR_BRICKS__ = BRICKS;

  var pendingCalls = {};
  var seq = 0;

  if (!window.__clair_brick_listener__) {
    window.__clair_brick_listener__ = true;
    window.addEventListener('message', function(event) {
      var data = event && event.data;
      if (!data || data.type !== 'CLAIR_BRICK_RESULT') return;
      var entry = pendingCalls[data.requestId];
      if (!entry) return;
      delete pendingCalls[data.requestId];
      clearTimeout(entry.timer);
      if (data.ok) entry.resolve(data.result);
      else entry.reject(new Error(data.error || "Erreur lors de l'exécution de la brique IA"));
    });
  }

  function resolveBrick(brickIdOrName) {
    if (!BRICKS.length) return null;
    if (!brickIdOrName || brickIdOrName === 'default') return BRICKS[0];
    var needle = String(brickIdOrName).toLowerCase();
    for (var i = 0; i < BRICKS.length; i++) {
      if (String(BRICKS[i].id).toLowerCase() === needle || String(BRICKS[i].name).toLowerCase() === needle) {
        return BRICKS[i];
      }
    }
    return null;
  }

  function runBrick(brickId, inputs) {
    return new Promise(function(resolve, reject) {
      if (window.parent === window) {
        reject(new Error("Pont cLAIr indisponible hors iframe."));
        return;
      }
      var resolved = resolveBrick(brickId);
      var targetId = resolved ? resolved.id : String(brickId || 'default');
      var reqId = 'cb_' + (++seq) + '_' + Date.now();
      var timer = setTimeout(function() {
        if (pendingCalls[reqId]) {
          delete pendingCalls[reqId];
          reject(new Error("Délai d'attente dépassé pour la brique IA."));
        }
      }, 95000);
      pendingCalls[reqId] = { resolve: resolve, reject: reject, timer: timer };
      window.parent.postMessage({
        type: 'CLAIR_BRICK_CALL',
        requestId: reqId,
        brickId: targetId,
        inputs: inputs || {}
      }, '*');
    });
  }

  window.clair = window.clair || {};
  window.clair.listBricks = function() { return BRICKS.slice(); };
  window.clair.runBrick = runBrick;
  window.clair.askAgent = function(brickIdOrInputs, maybeInputs) {
    if (typeof brickIdOrInputs === 'string') return runBrick(brickIdOrInputs, maybeInputs || {});
    return runBrick('default', brickIdOrInputs || {});
  };

  function inferWidgetStyle(brick) {
    if (brick.widget_style && brick.widget_style !== 'auto') return brick.widget_style;
    var fields = (brick.output_spec && brick.output_spec.fields) || [];
    var keys = fields.map(function(f) { return String(f.key || '').toLowerCase(); });
    if (keys.indexOf('questions') !== -1 && keys.indexOf('titre_quiz') !== -1) return 'quiz';
    if (keys.some(function(k) { return k.indexOf('note_') === 0 || k.indexOf('score_qualite') === 0; })) return 'scorecard';
    if (keys.indexOf('version_corrigee') !== -1 || keys.indexOf('traduction') !== -1) return 'rewriter';
    if (brick.id && brick.id.indexOf('bot_ia') !== -1) return 'chatbot';
    return 'cards';
  }

  function appendMetaFooter(container, res) {
    if (res && res.model_used) {
      var meta = document.createElement('div');
      meta.style.cssText = 'margin-top:8px;font-size:11px;color:#64748b;';
      meta.textContent = 'Modèle : ' + res.model_used;
      container.appendChild(meta);
    }
  }

  function renderQuizOutput(container, out, res) {
    var titleText = out.titre_quiz ? String(out.titre_quiz) : 'Quiz Interactif';
    var header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;';
    var titleEl = document.createElement('strong');
    titleEl.style.cssText = 'font-size:14px;color:#0f172a;';
    titleEl.textContent = '🎯 ' + titleText;
    var scoreBadge = document.createElement('span');
    scoreBadge.style.cssText = 'font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;background:#e0f2fe;color:#0369a1;';
    var rawQuestions = Array.isArray(out.questions) ? out.questions : [];
    var score = 0;
    var answered = 0;
    scoreBadge.textContent = 'Score : 0 / ' + rawQuestions.length;
    header.appendChild(titleEl);
    header.appendChild(scoreBadge);
    container.appendChild(header);

    rawQuestions.forEach(function(rawLine, qIdx) {
      var parts = String(rawLine).split('|').map(function(s) { return s.trim(); });
      var qCard = document.createElement('div');
      qCard.style.cssText = 'margin-bottom:10px;padding:10px;border-radius:10px;background:#ffffff;border:1px solid #cbd5e1;';
      var qTitle = document.createElement('div');
      qTitle.style.cssText = 'font-size:13px;font-weight:700;color:#0f172a;margin-bottom:7px;';
      qTitle.textContent = (qIdx + 1) + '. ' + (parts[0] || String(rawLine));
      qCard.appendChild(qTitle);

      var ansPart = parts.find(function(p) { return /^r[eé]ponse\s*:/i.test(p); }) || '';
      var expPart = parts.find(function(p) { return /^explication\s*:/i.test(p); }) || '';
      var correctLetter = ansPart.replace(/^r[eé]ponse\s*:/i, '').trim().charAt(0).toUpperCase();
      var options = parts.filter(function(p) { return /^[A-D][\\)\\.:]/i.test(p); });

      var feedback = document.createElement('div');
      feedback.style.cssText = 'display:none;margin-top:6px;padding:6px 8px;border-radius:6px;font-size:12px;';

      if (options.length) {
        var optWrap = document.createElement('div');
        optWrap.style.cssText = 'display:grid;grid-template-columns:1fr;gap:5px;';
        var done = false;
        options.forEach(function(opt) {
          var letter = opt.trim().charAt(0).toUpperCase();
          var optBtn = document.createElement('button');
          optBtn.type = 'button';
          optBtn.textContent = opt;
          optBtn.style.cssText = 'text-align:left;padding:6px 9px;border-radius:7px;border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;font-size:12.5px;cursor:pointer;';
          optBtn.onclick = function() {
            if (done) return;
            done = true;
            answered += 1;
            var ok = !correctLetter || letter === correctLetter;
            if (ok) score += 1;
            scoreBadge.textContent = 'Score : ' + score + ' / ' + rawQuestions.length + ' (' + answered + ' rép.)';
            optBtn.style.background = ok ? '#dcfce7' : '#fee2e2';
            optBtn.style.borderColor = ok ? '#16a34a' : '#dc2626';
            optBtn.style.color = ok ? '#14532d' : '#7f1d1d';
            feedback.style.display = 'block';
            feedback.style.background = ok ? '#f0fdf4' : '#fef2f2';
            feedback.style.color = ok ? '#166534' : '#991b1b';
            feedback.textContent = (ok ? '✓ Bonne réponse ! ' : '✗ Réponse attendue : ' + (correctLetter || '?') + '. ') + expPart.replace(/^explication\\s*:/i, '').trim();
          };
          optWrap.appendChild(optBtn);
        });
        qCard.appendChild(optWrap);
      }
      qCard.appendChild(feedback);
      container.appendChild(qCard);
    });

    if (out.conseil_revision) {
      var tip = document.createElement('div');
      tip.style.cssText = 'padding:8px;border-radius:8px;background:#fefce8;border:1px solid #fde047;font-size:12px;color:#713f12;';
      tip.textContent = '💡 ' + String(out.conseil_revision);
      container.appendChild(tip);
    }
    appendMetaFooter(container, res);
  }

  function renderRewriterOutput(container, out, res) {
    var mainKey = out.version_corrigee !== undefined ? 'version_corrigee' : (out.traduction !== undefined ? 'traduction' : Object.keys(out)[0]);
    var mainVal = mainKey ? String(out[mainKey] || '') : '';
    var box = document.createElement('div');
    box.style.cssText = 'padding:10px 12px;border-radius:10px;background:#ffffff;border:1px solid #93c5fd;margin-bottom:8px;';
    var top = document.createElement('div');
    top.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;';
    var lbl = document.createElement('strong');
    lbl.style.cssText = 'font-size:12px;text-transform:uppercase;color:#0284c7;';
    lbl.textContent = mainKey || 'Résultat';
    var copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.textContent = '📋 Copier';
    copyBtn.style.cssText = 'padding:3px 9px;border-radius:6px;border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;font-size:11.5px;font-weight:600;cursor:pointer;';
    copyBtn.onclick = function() {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(mainVal).then(function() {
          copyBtn.textContent = '✓ Copié !';
          setTimeout(function() { copyBtn.textContent = '📋 Copier'; }, 1600);
        }).catch(function() {});
      }
    };
    top.appendChild(lbl);
    top.appendChild(copyBtn);
    var textBody = document.createElement('div');
    textBody.style.cssText = 'white-space:pre-wrap;font-size:13.5px;line-height:1.55;color:#0f172a;';
    textBody.textContent = mainVal;
    box.appendChild(top);
    box.appendChild(textBody);
    container.appendChild(box);

    Object.keys(out).forEach(function(k) {
      if (k === mainKey) return;
      var row = document.createElement('div');
      row.style.cssText = 'margin-bottom:6px;padding:7px 9px;border-radius:8px;background:rgba(15,23,42,0.04);';
      var keyEl = document.createElement('div');
      keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:2px;';
      keyEl.textContent = k;
      var valEl = document.createElement('div');
      valEl.style.cssText = 'font-size:12.5px;white-space:pre-wrap;';
      var v = out[k];
      valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\\n') : String(v);
      row.appendChild(keyEl);
      row.appendChild(valEl);
      container.appendChild(row);
    });
    appendMetaFooter(container, res);
  }

  function renderScorecardOutput(container, out, res) {
    var scoreKey = Object.keys(out).find(function(k) { return typeof out[k] === 'number'; });
    var boolKey = Object.keys(out).find(function(k) { return typeof out[k] === 'boolean'; });
    if (scoreKey || boolKey) {
      var banner = document.createElement('div');
      banner.style.cssText = 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:10px;background:#ffffff;border:1px solid #cbd5e1;margin-bottom:8px;';
      if (scoreKey) {
        var denom = scoreKey.indexOf('20') !== -1 ? '/20' : '/100';
        var pill = document.createElement('span');
        pill.style.cssText = 'font-size:18px;font-weight:800;color:#0284c7;';
        pill.textContent = String(out[scoreKey]) + denom;
        banner.appendChild(pill);
      }
      if (boolKey) {
        var ok = Boolean(out[boolKey]);
        var statusPill = document.createElement('span');
        statusPill.style.cssText = 'padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;' + (ok ? 'background:#dcfce7;color:#166534;' : 'background:#fee2e2;color:#991b1b;');
        statusPill.textContent = ok ? '✓ Validé' : '⚠ À améliorer';
        banner.appendChild(statusPill);
      }
      container.appendChild(banner);
    }
    Object.keys(out).forEach(function(k) {
      if (k === scoreKey || k === boolKey) return;
      var row = document.createElement('div');
      row.style.cssText = 'margin-bottom:7px;padding:8px;border-radius:8px;background:rgba(15,23,42,0.04);';
      var keyEl = document.createElement('div');
      keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:3px;';
      keyEl.textContent = k;
      var valEl = document.createElement('div');
      valEl.style.cssText = 'font-size:13px;white-space:pre-wrap;line-height:1.45;';
      var v = out[k];
      valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
      row.appendChild(keyEl);
      row.appendChild(valEl);
      container.appendChild(row);
    });
    appendMetaFooter(container, res);
  }

  function renderOutputInto(container, res, brick) {
    while (container.firstChild) container.removeChild(container.firstChild);
    var out = res && res.output !== undefined ? res.output : res;
    var styleMode = brick ? inferWidgetStyle(brick) : 'cards';

    if (out && typeof out === 'object' && !Array.isArray(out)) {
      if (styleMode === 'quiz' && Array.isArray(out.questions)) {
        renderQuizOutput(container, out, res);
        return;
      }
      if (styleMode === 'rewriter') {
        renderRewriterOutput(container, out, res);
        return;
      }
      if (styleMode === 'scorecard') {
        renderScorecardOutput(container, out, res);
        return;
      }
    }

    if (Array.isArray(out)) {
      var ul = document.createElement('ul');
      ul.style.cssText = 'margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;';
      out.forEach(function(item) {
        var li = document.createElement('li');
        li.textContent = typeof item === 'string' ? item : JSON.stringify(item);
        ul.appendChild(li);
      });
      container.appendChild(ul);
    } else if (out && typeof out === 'object') {
      Object.keys(out).forEach(function(k) {
        var row = document.createElement('div');
        row.style.cssText = 'margin-bottom:8px;padding:8px;border-radius:8px;background:rgba(15,23,42,0.04);';
        var keyEl = document.createElement('div');
        keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:3px;';
        keyEl.textContent = k;
        var valEl = document.createElement('div');
        valEl.style.cssText = 'font-size:13px;white-space:pre-wrap;line-height:1.45;';
        var v = out[k];
        valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
        row.appendChild(keyEl);
        row.appendChild(valEl);
        container.appendChild(row);
      });
    } else {
      var pre = document.createElement('div');
      pre.style.cssText = 'white-space:pre-wrap;font-size:13px;line-height:1.5;';
      pre.textContent = String(out || '');
      container.appendChild(pre);
    }
    appendMetaFooter(container, res);
  }

  function buildChatbotPanel(brick, embedded) {
    var card = document.createElement('div');
    card.style.cssText = embedded
      ? 'border:1px solid rgba(148,163,184,0.35);border-radius:14px;padding:14px;background:#ffffff;color:#0f172a;font-family:system-ui,-apple-system,sans-serif;box-shadow:0 6px 22px rgba(15,23,42,0.07);display:flex;flex-direction:column;gap:10px;'
      : 'padding:12px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;margin-bottom:10px;display:flex;flex-direction:column;gap:8px;';

    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;';
    var h = document.createElement('strong');
    h.style.cssText = 'font-size:14px;color:#0f172a;';
    h.textContent = '💬 ' + brick.name;
    var rightWrap = document.createElement('div');
    rightWrap.style.cssText = 'display:flex;align-items:center;gap:6px;';
    var badge = document.createElement('span');
    badge.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:999px;background:#e0f2fe;color:#0369a1;font-weight:600;';
    badge.textContent = brick.model && brick.model !== 'auto' ? brick.model.split('/').pop() : 'Modèle auto';
    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = 'Effacer';
    clearBtn.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;color:#475569;cursor:pointer;';
    rightWrap.appendChild(badge);
    rightWrap.appendChild(clearBtn);
    titleRow.appendChild(h);
    titleRow.appendChild(rightWrap);
    card.appendChild(titleRow);

    var extraControls = {};
    var inputs = brick.inputs || [];
    var primaryField = inputs.find(function(inp) { return inp.type === 'textarea' || inp.type === 'text'; }) || inputs[0];
    var extraFields = inputs.filter(function(inp) { return !primaryField || inp.key !== primaryField.key; });

    if (extraFields.length) {
      var extraBar = document.createElement('div');
      extraBar.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
      extraFields.forEach(function(inp) {
        var lbl = document.createElement('label');
        lbl.style.cssText = 'display:flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:#475569;';
        lbl.textContent = inp.label + ':';
        var el;
        if (inp.type === 'select' && Array.isArray(inp.options) && inp.options.length) {
          el = document.createElement('select');
          inp.options.forEach(function(opt) {
            var o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            el.appendChild(o);
          });
        } else {
          el = document.createElement('input');
          el.type = 'text';
        }
        el.style.cssText = 'padding:4px 7px;border-radius:6px;border:1px solid #cbd5e1;font-size:12px;background:#fff;color:#0f172a;';
        if (inp.default_value) el.value = inp.default_value;
        extraControls[inp.key] = el;
        lbl.appendChild(el);
        extraBar.appendChild(lbl);
      });
      card.appendChild(extraBar);
    }

    var history = [];
    var log = document.createElement('div');
    log.style.cssText = 'min-height:150px;max-height:300px;overflow-y:auto;padding:10px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;display:flex;flex-direction:column;gap:8px;';

    function appendBubble(role, text) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;' + (role === 'user' ? 'justify-content:flex-end;' : 'justify-content:flex-start;');
      var bubble = document.createElement('div');
      bubble.style.cssText = role === 'user'
        ? 'max-width:82%;padding:8px 11px;border-radius:12px 12px 2px 12px;background:linear-gradient(135deg,#0284c7,#4f46e5);color:#fff;font-size:13px;line-height:1.45;white-space:pre-wrap;'
        : 'max-width:86%;padding:8px 11px;border-radius:12px 12px 12px 2px;background:#ffffff;border:1px solid #e2e8f0;color:#0f172a;font-size:13px;line-height:1.5;white-space:pre-wrap;';
      bubble.textContent = text;
      row.appendChild(bubble);
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function resetChat() {
      history = [];
      while (log.firstChild) log.removeChild(log.firstChild);
      appendBubble('assistant', brick.welcome_message || ('Bonjour ! Je suis ' + brick.name + '. Comment puis-je vous aider ?'));
    }
    clearBtn.onclick = resetChat;
    resetChat();

    var form = document.createElement('form');
    form.style.cssText = 'display:flex;gap:6px;align-items:flex-end;';
    var inputEl = document.createElement('textarea');
    inputEl.rows = 2;
    inputEl.placeholder = (primaryField && primaryField.placeholder) || 'Écrivez votre message…';
    inputEl.style.cssText = 'flex:1;padding:8px 10px;border-radius:9px;border:1px solid #cbd5e1;font-size:13px;font-family:inherit;resize:none;background:#fff;color:#0f172a;';
    var sendBtn = document.createElement('button');
    sendBtn.type = 'submit';
    sendBtn.textContent = 'Envoyer';
    sendBtn.style.cssText = 'padding:9px 14px;border:none;border-radius:9px;background:#0284c7;color:#fff;font-weight:700;font-size:12.5px;cursor:pointer;';
    form.appendChild(inputEl);
    form.appendChild(sendBtn);

    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var text = inputEl.value.trim();
      if (!text || sendBtn.disabled) return;
      inputEl.value = '';
      appendBubble('user', text);
      var pendingBubble = appendBubble('assistant', 'Réflexion en cours…');
      sendBtn.disabled = true;

      var payload = { _history: history.slice() };
      Object.keys(extraControls).forEach(function(k) { payload[k] = extraControls[k].value; });
      if (primaryField) payload[primaryField.key] = text;
      else payload.message = text;

      runBrick(brick.id, payload).then(function(res) {
        var reply = typeof res.output === 'string' ? res.output : (res.raw_text || JSON.stringify(res.output, null, 2));
        pendingBubble.textContent = reply;
        history.push({ role: 'user', content: text });
        history.push({ role: 'assistant', content: reply });
      }).catch(function(err) {
        pendingBubble.textContent = 'Erreur : ' + (err && err.message ? err.message : String(err));
      }).finally(function() {
        sendBtn.disabled = false;
        log.scrollTop = log.scrollHeight;
      });
    });

    card.appendChild(log);
    card.appendChild(form);
    return card;
  }

  function buildBrickPanel(brick, embedded) {
    if (inferWidgetStyle(brick) === 'chatbot') {
      return buildChatbotPanel(brick, embedded);
    }

    var card = document.createElement('div');
    card.style.cssText = embedded
      ? 'border:1px solid rgba(148,163,184,0.35);border-radius:12px;padding:14px;background:#ffffff;color:#0f172a;font-family:system-ui,-apple-system,sans-serif;box-shadow:0 4px 16px rgba(15,23,42,0.06);'
      : 'padding:12px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;margin-bottom:10px;';

    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;';
    var h = document.createElement('strong');
    h.style.cssText = 'font-size:14px;color:#0f172a;';
    h.textContent = '🤖 ' + brick.name;
    var badge = document.createElement('span');
    badge.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:999px;background:#e0f2fe;color:#0369a1;font-weight:600;';
    badge.textContent = brick.model && brick.model !== 'auto' ? brick.model.split('/').pop() : 'Modèle auto';
    titleRow.appendChild(h);
    titleRow.appendChild(badge);
    card.appendChild(titleRow);

    if (brick.description) {
      var desc = document.createElement('p');
      desc.style.cssText = 'margin:0 0 10px;font-size:12px;color:#475569;';
      desc.textContent = brick.description;
      card.appendChild(desc);
    }

    var form = document.createElement('form');
    form.style.cssText = 'display:flex;flex-direction:column;gap:8px;';
    var controls = {};

    (brick.inputs || []).forEach(function(inp) {
      var wrap = document.createElement('label');
      wrap.style.cssText = 'display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:600;color:#334155;';
      wrap.textContent = inp.label + (inp.required ? ' *' : '');
      var el;
      if (inp.type === 'textarea' || inp.type === 'json') {
        el = document.createElement('textarea');
        el.rows = 3;
      } else if (inp.type === 'select' && Array.isArray(inp.options) && inp.options.length) {
        el = document.createElement('select');
        inp.options.forEach(function(opt) {
          var o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          el.appendChild(o);
        });
      } else {
        el = document.createElement('input');
        el.type = inp.type === 'number' ? 'number' : 'text';
      }
      el.style.cssText = 'width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid #cbd5e1;border-radius:7px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a;';
      if (inp.placeholder && 'placeholder' in el) el.placeholder = inp.placeholder;
      if (inp.default_value) el.value = inp.default_value;
      controls[inp.key] = el;
      wrap.appendChild(el);
      form.appendChild(wrap);
    });

    var btn = document.createElement('button');
    btn.type = 'submit';
    btn.textContent = "Exécuter l'agent IA";
    btn.style.cssText = 'align-self:flex-start;padding:8px 14px;border:none;border-radius:8px;background:#0284c7;color:#fff;font-weight:600;font-size:12.5px;cursor:pointer;';
    form.appendChild(btn);

    var outBox = document.createElement('div');
    outBox.style.cssText = 'display:none;margin-top:10px;padding:10px;border-radius:8px;border:1px solid #bae6fd;background:#f0f9ff;color:#0f172a;';

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var payload = {};
      Object.keys(controls).forEach(function(k) { payload[k] = controls[k].value; });
      btn.disabled = true;
      btn.textContent = 'Exécution en cours…';
      outBox.style.display = 'block';
      outBox.textContent = 'Analyse par ' + brick.name + '…';
      runBrick(brick.id, payload).then(function(res) {
        renderOutputInto(outBox, res, brick);
      }).catch(function(err) {
        outBox.textContent = 'Erreur : ' + (err && err.message ? err.message : String(err));
      }).finally(function() {
        btn.disabled = false;
        btn.textContent = "Exécuter l'agent IA";
      });
    });

    card.appendChild(form);
    card.appendChild(outBox);
    return card;
  }

  function mountBrickWidgets() {
    if (!BRICKS.length || !document.body) return;

    var explicitIds = {};
    document.querySelectorAll('[data-clair-brick]').forEach(function(host) {
      var bid = host.getAttribute('data-clair-brick');
      var brick = resolveBrick(bid);
      if (brick && !host.getAttribute('data-clair-mounted')) {
        host.setAttribute('data-clair-mounted', '1');
        explicitIds[brick.id] = true;
        host.appendChild(buildBrickPanel(brick, true));
      }
    });

    if (document.getElementById('clair-bricks-dock')) return;

    var dockBricks = BRICKS.filter(function(b) {
      return b.show_widget !== false && !explicitIds[b.id];
    });
    if (!dockBricks.length) return;

    var dock = document.createElement('div');
    dock.id = 'clair-bricks-dock';
    dock.className = 'no-print';
    dock.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483000;font-family:system-ui,-apple-system,sans-serif;';

    var panel = document.createElement('div');
    panel.style.cssText = 'display:none;width:min(410px, calc(100vw - 32px));max-height:74vh;overflow-y:auto;background:#ffffff;color:#0f172a;border:1px solid #cbd5e1;border-radius:14px;box-shadow:0 20px 45px rgba(15,23,42,0.25);padding:14px;margin-bottom:10px;';

    var header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;';
    var hTitle = document.createElement('strong');
    hTitle.style.cssText = 'font-size:13.5px;color:#0f172a;';
    hTitle.textContent = '🧩 Briques IA connectées (' + dockBricks.length + ')';
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'border:none;background:transparent;font-size:15px;cursor:pointer;color:#64748b;';
    closeBtn.onclick = function() { panel.style.display = 'none'; };
    header.appendChild(hTitle);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    dockBricks.forEach(function(b) {
      panel.appendChild(buildBrickPanel(b, false));
    });

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.textContent = '🧩 Briques IA (' + dockBricks.length + ')';
    toggle.style.cssText = 'padding:9px 14px;border:none;border-radius:999px;background:linear-gradient(135deg,#0284c7,#4f46e5);color:#fff;font-weight:700;font-size:12.5px;cursor:pointer;box-shadow:0 8px 24px rgba(2,132,199,0.35);';
    toggle.onclick = function() {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    };

    dock.appendChild(panel);
    dock.appendChild(toggle);
    document.body.appendChild(dock);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountBrickWidgets);
  } else {
    mountBrickWidgets();
  }
})();
</script>`;
}
