import type { PageBrick } from "./canvas-bricks";

export type DiagramNodeKind = "ui_input" | "ai_brick" | "ui_output" | "ui_state";

export type DiagramNode = {
  id: string;
  kind: DiagramNodeKind;
  label: string;
  subtitle: string;
  x: number;
  y: number;
  brick?: PageBrick;
};

export type DiagramEdge = {
  id: string;
  from_node: string;
  to_node: string;
  label: string;
};

export type AppDiagram = {
  title: string;
  summary: string;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
};

export type DiagramPreset = {
  presetId: string;
  icon: string;
  label: string;
  description: string;
  diagram: AppDiagram;
};

export const DIAGRAM_PRESETS: DiagramPreset[] = [
  {
    presetId: "niaisbot_feynman",
    icon: "🤪",
    label: "Bot de l'App + Jauge & Score",
    description: "Ex. Le NiaisBot / Feynman : bulles intégrées, jauge de compréhension et score /100 pilotés par l'Agent IA",
    diagram: {
      title: "Le NiaisBot — Révision Interactive",
      summary: "L'utilisateur choisit un sujet et explique le concept dans le tchat de l'app. La brique IA génère la réplique du bot, la jauge de compréhension et le score /100.",
      nodes: [
        {
          id: "ui_sujet",
          kind: "ui_input",
          label: "Sélecteur de Sujet",
          subtitle: "Liste cliquable à gauche (Mitose, Révolution, Relativité…)",
          x: 36,
          y: 54,
        },
        {
          id: "ui_chat_input",
          kind: "ui_input",
          label: "Champ de Tchat de l'App",
          subtitle: "Zone de saisie intégrée + historique des échanges",
          x: 36,
          y: 236,
        },
        {
          id: "ai_niaisbot",
          kind: "ai_brick",
          label: "Cerveau NiaisBot (Agent IA)",
          subtitle: "Modèle + Prompt élève naïf + sorties JSON",
          x: 344,
          y: 138,
          brick: {
            id: "bot_moteur_app",
            name: "Le NiaisBot (Moteur IA)",
            type: "ai_agent",
            description: "Incarne un élève un peu naïf mais curieux qui pose des questions et progresse selon les explications de l'utilisateur.",
            model: "auto",
            system_prompt:
              "Tu incarnes « Le NiaisBot », un élève naïf, drôle mais de bonne foi qui essaie de comprendre le `sujet` grâce aux explications de l'utilisateur (`message` et l'historique). Au début tu comprends mal, puis au fil des explications claires de l'utilisateur tu progresses, poses des questions pertinentes et augmentes ton `score_comprehension` (0 à 100).",
            web_search_enabled: false,
            show_widget: false,
            widget_style: "auto",
            welcome_message: "",
            inputs: [
              {
                key: "sujet",
                label: "Sujet de révision",
                type: "text",
                required: true,
                placeholder: "Ex: La Mitose cellulaire",
                default_value: "La Mitose cellulaire",
                options: [],
              },
              {
                key: "message",
                label: "Explication de l'utilisateur",
                type: "textarea",
                required: true,
                placeholder: "Message saisi dans le tchat de l'app",
                default_value: "",
                options: [],
              },
            ],
            output_spec: {
              format: "json",
              description: "Réplique du NiaisBot + niveau de compréhension pour mettre à jour la jauge et le score de l'app",
              fields: [
                { key: "reponse_bot", type: "string", description: "Réplique du NiaisBot affichée dans la bulle de l'app" },
                { key: "score_comprehension", type: "number", description: "Score cumulé de compréhension de 0 à 100" },
                { key: "statut_jauge", type: "string", description: "Texte court sous la jauge (ex: En train de tout capter !)" },
              ],
            },
          },
        },
        {
          id: "ui_bulles",
          kind: "ui_output",
          label: "Fil de Discussion de l'App",
          subtitle: "Ajoute la bulle du NiaisBot avec `reponse_bot`",
          x: 660,
          y: 34,
        },
        {
          id: "ui_jauge",
          kind: "ui_output",
          label: "Jauge Compréhension",
          subtitle: "Met à jour la barre % et `statut_jauge`",
          x: 660,
          y: 192,
        },
        {
          id: "ui_score",
          kind: "ui_output",
          label: "Badge Score /100",
          subtitle: "Affiche `score_comprehension` dans l'en-tête",
          x: 660,
          y: 348,
        },
      ],
      edges: [
        { id: "e1", from_node: "ui_sujet", to_node: "ai_niaisbot", label: "sujet" },
        { id: "e2", from_node: "ui_chat_input", to_node: "ai_niaisbot", label: "message + _history" },
        { id: "e3", from_node: "ai_niaisbot", to_node: "ui_bulles", label: "reponse_bot" },
        { id: "e4", from_node: "ai_niaisbot", to_node: "ui_jauge", label: "score_comprehension + statut_jauge" },
        { id: "e5", from_node: "ai_niaisbot", to_node: "ui_score", label: "score_comprehension" },
      ],
    },
  },
  {
    presetId: "quiz_coach",
    icon: "🎯",
    label: "Quiz Adaptatif + Coach IA",
    description: "Génère un QCM sur mesure dans l'app puis analyse et corrige les réponses ouvertes",
    diagram: {
      title: "Studio Quiz & Coach IA",
      summary: "L'utilisateur saisit un thème : la brique Quiz produit un QCM interactif et le Coach IA corrige la synthèse.",
      nodes: [
        { id: "ui_theme", kind: "ui_input", label: "Sujet & Niveau", subtitle: "Sélecteur de thème et difficulté", x: 36, y: 120 },
        {
          id: "ai_quiz",
          kind: "ai_brick",
          label: "Générateur de Quiz (IA)",
          subtitle: "Produit 4 questions QCM JSON",
          x: 344,
          y: 120,
          brick: {
            id: "generateur_quiz",
            name: "Générateur de Quiz QCM",
            type: "ai_agent",
            description: "Crée des questions QCM structurées pour l'interface du quiz.",
            model: "auto",
            system_prompt:
              'Génère exactement 4 questions QCM dans `questions` au format exact : "Question ? | A) ... | B) ... | C) ... | D) ... | Réponse: A | Explication: ..."',
            web_search_enabled: false,
            show_widget: false,
            widget_style: "auto",
            welcome_message: "",
            inputs: [
              { key: "sujet", label: "Sujet", type: "text", required: true, placeholder: "Ex: Les volcans", default_value: "", options: [] },
              { key: "difficulte", label: "Niveau", type: "select", required: true, placeholder: "", default_value: "Moyen", options: ["Facile", "Moyen", "Avancé"] },
            ],
            output_spec: {
              format: "json",
              description: "Titre et liste de questions QCM",
              fields: [
                { key: "titre_quiz", type: "string", description: "Titre du quiz" },
                { key: "questions", type: "string[]", description: "Questions formatées QCM" },
              ],
            },
          },
        },
        { id: "ui_qcm", kind: "ui_output", label: "Grille QCM Interactive", subtitle: "Cartes cliquables + score en direct", x: 660, y: 120 },
      ],
      edges: [
        { id: "e1", from_node: "ui_theme", to_node: "ai_quiz", label: "sujet + difficulte" },
        { id: "e2", from_node: "ai_quiz", to_node: "ui_qcm", label: "titre_quiz + questions" },
      ],
    },
  },
  {
    presetId: "kpi_dashboard",
    icon: "📊",
    label: "Analyseur Texte → Dashboard KPI",
    description: "Transforme notes, articles ou emails collés dans l'app en KPI chiffrés et plan d'action",
    diagram: {
      title: "Dashboard d'Analyse IA",
      summary: "Une zone de texte alimente l'extracteur JSON pour afficher des KPI visuels et une checklist actionnable.",
      nodes: [
        { id: "ui_doc", kind: "ui_input", label: "Zone Texte / Notes", subtitle: "Document collé par l'utilisateur", x: 36, y: 135 },
        {
          id: "ai_extract",
          kind: "ai_brick",
          label: "Extracteur KPI (Agent IA)",
          subtitle: "Produit synthèse, score et actions JSON",
          x: 344,
          y: 135,
          brick: {
            id: "extracteur_json",
            name: "Extracteur KPI & Synthèse JSON",
            type: "ai_agent",
            description: "Extrait un résumé, un score /100, les points clés et les actions.",
            model: "auto",
            system_prompt: "Extrais les KPI, points essentiels et prochaines actions à partir du contenu fourni.",
            web_search_enabled: false,
            show_widget: false,
            widget_style: "auto",
            welcome_message: "",
            inputs: [
              { key: "contenu", label: "Contenu source", type: "textarea", required: true, placeholder: "Collez vos notes…", default_value: "", options: [] },
            ],
            output_spec: {
              format: "json",
              description: "Données structurées pour le dashboard",
              fields: [
                { key: "resume", type: "string", description: "Synthèse exécutive" },
                { key: "score_pertinence", type: "number", description: "Score sur 100" },
                { key: "points_cles", type: "string[]", description: "Points clés" },
                { key: "actions", type: "string[]", description: "Actions à cocher" },
              ],
            },
          },
        },
        { id: "ui_kpis", kind: "ui_output", label: "Cartes KPI & Résumé", subtitle: "Affiche `score_pertinence` et `resume`", x: 660, y: 60 },
        { id: "ui_actions", kind: "ui_output", label: "Checklist Actions", subtitle: "Affiche `actions` et `points_cles`", x: 660, y: 230 },
      ],
      edges: [
        { id: "e1", from_node: "ui_doc", to_node: "ai_extract", label: "contenu" },
        { id: "e2", from_node: "ai_extract", to_node: "ui_kpis", label: "resume + score_pertinence" },
        { id: "e3", from_node: "ai_extract", to_node: "ui_actions", label: "points_cles + actions" },
      ],
    },
  },
  {
    presetId: "finance_eod_cockpit",
    icon: "📈",
    label: "Cockpit Boursier EOD & Indicateurs",
    description: "Cotations EODHD/Yahoo réelles, RSI(14), SMA, MACD et score fondamental intégrés à l'app",
    diagram: {
      title: "Cockpit Boursier EOD & Indicateurs",
      summary: "L'utilisateur saisit un ticker ou une entreprise ; la brique EOD calcule les indicateurs techniques et l'analyste fondamental évalue l'action.",
      nodes: [
        { id: "ui_ticker", kind: "ui_input", label: "Recherche Action / Ticker", subtitle: "Champ ticker (AAPL, MC.PA…) + sélecteur horizon", x: 36, y: 135 },
        {
          id: "ai_eod_tech",
          kind: "ai_brick",
          label: "Cotation EOD & Indicateurs",
          subtitle: "Données EODHD/Yahoo + RSI14 / SMA / MACD",
          x: 344,
          y: 45,
          brick: {
            id: "finance_eod_indicateurs",
            name: "Cotation EOD & Indicateurs",
            type: "finance_eod_agent",
            description: "Analyse technique réelle basée sur EODHD et Yahoo Finance.",
            model: "auto",
            system_prompt:
              "Tu es un analyste technique quantitatif. Appuie-toi strictement sur les données EOD et indicateurs techniques calculés (SMA20, SMA50, RSI14, MACD) fournis dans le contexte.",
            web_search_enabled: false,
            finance_data_enabled: true,
            show_widget: false,
            widget_style: "scorecard",
            welcome_message: "",
            inputs: [
              { key: "symbole", label: "Ticker ou Entreprise", type: "text", required: true, placeholder: "Ex: AAPL, MC.PA", default_value: "AAPL", options: [] },
              { key: "horizon", label: "Horizon", type: "select", required: false, placeholder: "", default_value: "3 mois", options: ["1 mois", "3 mois", "6 mois", "1 an"] },
            ],
            output_spec: {
              format: "json",
              description: "Cours réel, RSI, tendance et niveaux clés",
              fields: [
                { key: "ticker", type: "string", description: "Symbole résolu" },
                { key: "prix_actuel", type: "number", description: "Dernier cours connu" },
                { key: "rsi_14", type: "number", description: "RSI 14 jours" },
                { key: "tendance_technique", type: "string", description: "Haussière / Neutre / Baissière" },
                { key: "niveaux_cles", type: "string[]", description: "Signaux SMA/MACD et supports/résistances" },
                { key: "synthese_eod", type: "string", description: "Synthèse technique" },
              ],
            },
          },
        },
        {
          id: "ai_fonda",
          kind: "ai_brick",
          label: "Analyste Fondamental",
          subtitle: "PER, marges, ROE & verdict valorisation",
          x: 344,
          y: 235,
          brick: {
            id: "finance_fondamentaux",
            name: "Analyste Fondamental Bourse",
            type: "finance_eod_agent",
            description: "Évalue la valorisation et la solidité bilancielle.",
            model: "auto",
            system_prompt:
              "Tu es un analyste financier fondamental. Évalue objectivement les ratios (PER, marges, ROE, dette) à partir des données boursières fournies.",
            web_search_enabled: false,
            finance_data_enabled: true,
            show_widget: false,
            widget_style: "scorecard",
            welcome_message: "",
            inputs: [
              { key: "symbole", label: "Ticker ou Entreprise", type: "text", required: true, placeholder: "Ex: AAPL, MC.PA", default_value: "AAPL", options: [] },
            ],
            output_spec: {
              format: "json",
              description: "Score fondamental /100 et forces/risques",
              fields: [
                { key: "score_fondamental", type: "number", description: "Score sur 100" },
                { key: "valorisation_verdict", type: "string", description: "Verdict valorisation" },
                { key: "forces", type: "string[]", description: "Points forts" },
                { key: "risques", type: "string[]", description: "Risques" },
              ],
            },
          },
        },
        { id: "ui_tech_cards", kind: "ui_output", label: "Cartes Cours & RSI/SMA", subtitle: "Affiche prix_actuel, rsi_14 et niveaux_cles", x: 660, y: 45 },
        { id: "ui_fonda_cards", kind: "ui_output", label: "Score Fondamental & Forces", subtitle: "Affiche score_fondamental, forces et risques", x: 660, y: 235 },
      ],
      edges: [
        { id: "e1", from_node: "ui_ticker", to_node: "ai_eod_tech", label: "symbole + horizon" },
        { id: "e2", from_node: "ui_ticker", to_node: "ai_fonda", label: "symbole" },
        { id: "e3", from_node: "ai_eod_tech", to_node: "ui_tech_cards", label: "prix_actuel + rsi_14 + niveaux_cles" },
        { id: "e4", from_node: "ai_fonda", to_node: "ui_fonda_cards", label: "score_fondamental + forces" },
      ],
    },
  },
];

export function createInitialDiagram(
  title = "Nouvelle Application IA",
  existingBricks: PageBrick[] = [],
): AppDiagram {
  if (existingBricks.length > 0) {
    const nodes: DiagramNode[] = [
      {
        id: "ui_entree",
        kind: "ui_input",
        label: "Interface Entrée de l'App",
        subtitle: "Champs de saisie et contrôles utilisateur",
        x: 36,
        y: 130,
      },
    ];
    const edges: DiagramEdge[] = [];
    existingBricks.forEach((b, idx) => {
      const nodeId = `ai_${b.id}`;
      nodes.push({
        id: nodeId,
        kind: "ai_brick",
        label: b.name,
        subtitle: `${b.inputs.length} entrée(s) → ${b.output_spec.format}`,
        x: 344,
        y: 50 + idx * 170,
        brick: { ...b, show_widget: false },
      });
      edges.push({
        id: `e_in_${idx}`,
        from_node: "ui_entree",
        to_node: nodeId,
        label: b.inputs.map(i => i.key).join(", ") || "inputs",
      });
      edges.push({
        id: `e_out_${idx}`,
        from_node: nodeId,
        to_node: "ui_sortie",
        label:
          b.output_spec.format === "json" && b.output_spec.fields.length
            ? b.output_spec.fields.map(f => f.key).join(" + ")
            : "output",
      });
    });
    nodes.push({
      id: "ui_sortie",
      kind: "ui_output",
      label: "Interface Résultat de l'App",
      subtitle: "Met à jour le DOM avec la sortie des briques",
      x: 660,
      y: 130,
    });
    return {
      title,
      summary: "Architecture de l'application connectée aux briques IA internes.",
      nodes,
      edges,
    };
  }
  return JSON.parse(JSON.stringify(DIAGRAM_PRESETS[0].diagram)) as AppDiagram;
}

export function extractBricksFromDiagram(diagram: AppDiagram): PageBrick[] {
  const seen = new Set<string>();
  const bricks: PageBrick[] = [];
  for (const node of diagram.nodes) {
    if (node.kind === "ai_brick" && node.brick) {
      if (seen.has(node.brick.id)) continue;
      seen.add(node.brick.id);
      bricks.push({ ...node.brick, show_widget: Boolean(node.brick.show_widget) });
    }
  }
  return bricks;
}

export function syncBricksIntoDiagram(diagram: AppDiagram, bricks: PageBrick[]): AppDiagram {
  const byId = new Map(bricks.map(b => [b.id, b]));
  const updatedNodes = diagram.nodes.map(node => {
    if (node.kind === "ai_brick" && node.brick && byId.has(node.brick.id)) {
      const updated = byId.get(node.brick.id)!;
      byId.delete(node.brick.id);
      return {
        ...node,
        label: updated.name,
        brick: updated,
      };
    }
    return node;
  });

  let offsetY = 45 + updatedNodes.filter(n => n.kind === "ai_brick").length * 165;
  for (const remaining of byId.values()) {
    updatedNodes.push({
      id: `ai_${remaining.id}`,
      kind: "ai_brick",
      label: remaining.name,
      subtitle: `${remaining.inputs.length} entrée(s) → ${remaining.output_spec.format}`,
      x: 344,
      y: offsetY,
      brick: remaining,
    });
    offsetY += 165;
  }

  return { ...diagram, nodes: updatedNodes };
}

export function buildAppPromptFromDiagram(
  diagram: AppDiagram,
  existingFilePaths: string[] = [],
): string {
  const inputsNodes = diagram.nodes.filter(n => n.kind === "ui_input");
  const aiNodes = diagram.nodes.filter(n => n.kind === "ai_brick" && n.brick);
  const outputNodes = diagram.nodes.filter(n => n.kind === "ui_output" || n.kind === "ui_state");

  const nodeById = new Map(diagram.nodes.map(n => [n.id, n]));

  const lines: string[] = [];
  if (existingFilePaths.length > 0) {
    lines.push(
      `Mets à jour l'application existante (${existingFilePaths.join(", ")}) pour appliquer STRICTEMENT le diagramme d'architecture « ${diagram.title} » ci-dessous.`,
      `SUPPRIME toute simulation statique ou réponse en dur dans app.js : l'application elle-même doit appeler le vrai moteur IA via \`await window.clair.runBrick(...)\`.`,
    );
  } else {
    lines.push(
      `Crée l'application web complète « ${diagram.title} » en plusieurs fichiers (\`index.html\`, \`styles.css\`, \`app.js\`) en suivant EXACTEMENT le diagramme d'architecture ci-dessous.`,
    );
  }

  if (diagram.summary) {
    lines.push(`Objectif & Architecture : ${diagram.summary}`);
  }

  if (inputsNodes.length) {
    lines.push(
      `1. COMPOSANTS UI D'ENTRÉE (à intégrer dans \`index.html\` / \`app.js\`) :\n` +
        inputsNodes.map(n => `- **${n.label}** (${n.id}) : ${n.subtitle || "Contrôle interactif utilisateur"}`).join("\n"),
    );
  }

  if (aiNodes.length) {
    const brickSpecs = aiNodes.map(n => {
      const b = n.brick!;
      const sampleArgs: Record<string, string> = {};
      for (const inp of b.inputs) {
        sampleArgs[inp.key] = inp.default_value || `<valeur_${inp.key}>`;
      }
      const hasHistory =
        b.widget_style === "chatbot" ||
        b.inputs.some(i => i.key === "message") ||
        diagram.edges.some(e => e.to_node === n.id && e.label.includes("_history"));
      if (hasHistory) {
        (sampleArgs as Record<string, unknown>)._history = "conversationHistory";
      }

      const outDesc =
        b.output_spec.format === "json" && b.output_spec.fields.length > 0
          ? b.output_spec.fields
              .map(f => `  - \`res.output.${f.key}\` (${f.type}) : ${f.description || f.key}`)
              .join("\n")
          : `  - \`res.output\` (${b.output_spec.format}) : ${b.output_spec.description || "Réponse"}`;

      return [
        `- **${n.label}** — brique \`id: "${b.id}"\` (moteur interne de l'app, ne pas recréer un autre widget flottant)`,
        `  Appel JavaScript exact dans \`app.js\` :`,
        `  \`const res = await window.clair.runBrick(${JSON.stringify(b.id)}, ${JSON.stringify(sampleArgs)});\``,
        `  Champs retournés à exploiter dans le DOM :\n${outDesc}`,
      ].join("\n");
    });
    lines.push(`2. BRIQUES AGENT IA CONNECTÉES (MOTEUR INTERNE DE L'APP) :\n${brickSpecs.join("\n\n")}`);
  }

  if (outputNodes.length) {
    lines.push(
      `3. COMPOSANTS UI DE SORTIE (mises à jour du DOM de l'app) :\n` +
        outputNodes.map(n => `- **${n.label}** (${n.id}) : ${n.subtitle || "Zone d'affichage dynamique"}`).join("\n"),
    );
  }

  if (diagram.edges.length) {
    const edgeLines = diagram.edges.map(e => {
      const src = nodeById.get(e.from_node)?.label || e.from_node;
      const dst = nodeById.get(e.to_node)?.label || e.to_node;
      return `- [${src}] --(${e.label})--> [${dst}]`;
    });
    lines.push(`4. FLUX DE DONNÉES À CÂBLER DANS \`app.js\` :\n${edgeLines.join("\n")}`);
  }

  lines.push(
    `RÈGLES IMPÉRATIVES :\n` +
      `- L'agent IA fait partie intégrante de l'interface de l'app (ses propres bulles, sa jauge, son score, ses boutons).\n` +
      `- N'écris JAMAIS de réponses simulées en dur, ni de \`setTimeout\` imitant une IA, et ne demande aucune clé API.\n` +
      `- Gère proprement l'état de chargement (indicateur "réflexion en cours…") et les erreurs éventuelles lors de \`await window.clair.runBrick(...)\`.`,
  );

  return lines.join("\n\n");
}
