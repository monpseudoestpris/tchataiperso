export type FinanceTermDefinition = {
  title: string;
  summary: string;
  formula?: string;
  interpretation?: string;
};

/**
 * Dictionnaire centralisé des indicateurs financiers, boursiers, fondamentaux,
 * de risque, de valorisation intrinsèque et d'analyse technique.
 */
export const FINANCE_GLOSSARY: Record<string, FinanceTermDefinition> = {
  // === VALEURS INTRINSÈQUES & COÛT DU CAPITAL ===
  margin_of_safety: {
    title: "Marge de sécurité",
    summary:
      "Décote (ou surcote si négative) du cours actuel par rapport à la valeur intrinsèque estimée. C'est le coussin de protection cher à Benjamin Graham et Warren Buffett pour absorber les erreurs d'estimation ou les imprévus.",
    formula: "(1 − Cours / Valeur intrinsèque) × 100",
    interpretation:
      "Positif (ex. +25 %) = titre sous-évalué de 25 % sous sa valeur estimée ; Négatif = titre payé au-dessus de sa valeur intrinsèque.",
  },
  intrinsic_value: {
    title: "Valeur intrinsèque globale (VI)",
    summary:
      "Estimation de la valeur réelle d'une action indépendamment de son cours de bourse, calculée par moyenne pondérée de 12 méthodes indépendantes (ou 13 en mode fidèle Uncle Stock).",
    formula: "Σ (Poids_i × VI_i) / Σ Poids_i",
    interpretation:
      "À comparer directement au cours actuel via le ratio Cours / VI et la marge de sécurité.",
  },
  price_to_iv: {
    title: "Ratio Cours / Valeur intrinsèque (P/IV)",
    summary:
      "Rapport entre le prix de marché actuel et la valeur intrinsèque calculée par le modèle.",
    formula: "Cours actuel / Valeur intrinsèque",
    interpretation:
      "< 1,00× = décote (sous-évaluée) ; = 1,00× = juste prix ; > 1,00× = prime (surévaluée).",
  },
  wacc: {
    title: "WACC (Coût moyen pondéré du capital)",
    summary:
      "Taux d'actualisation représentant le rendement minimal exigé par l'ensemble des apporteurs de capitaux (actionnaires + créanciers) compte tenu du risque de l'entreprise.",
    formula: "WACC = wE × Ke + wD × Kd × (1 − T)",
    interpretation:
      "Un plancher prudentiel est appliqué dans le modèle. Plus le WACC est élevé, plus les flux futurs sont actualisés sévèrement.",
  },
  ke_capm: {
    title: "Ke (CAPM) — Coût des capitaux propres",
    summary:
      "Rendement annuel exigé par les actionnaires selon le modèle MEDAF (CAPM), combinant taux sans risque, bêta borné [0 ; 2] et prime de risque actions.",
    formula: "Ke = Rf + clamp(β, 0, 2) × ERP",
  },
  kd_net: {
    title: "Kd net — Coût de la dette après impôt",
    summary:
      "Taux d'intérêt effectif payé par l'entreprise sur sa dette financière après prise en compte de l'économie d'impôt sur les intérêts.",
    formula: "Kd net = (Charges d'intérêts / Dette totale) × (1 − Taux IS)",
  },
  equity_charge: {
    title: "Charge d'équité (Equity Charge)",
    summary:
      "Coût d'opportunité annuel des capitaux propres employés par l'entreprise. Sert à déterminer si la création de valeur dépasse le rendement minimum attendu par les actionnaires.",
    formula: "Capitaux propres (ou BVPS) × Ke",
  },
  total_owner_return: {
    title: "Total Owner Return",
    summary:
      "Rendement total annuel créé pour le propriétaire : variation de la valeur comptable nette (Common Book Value) augmentée des dividendes nets versés.",
    formula: "(CBV_t2 + Dividendes − CBV_t1) / CBV_t1",
    interpretation: "Mesure l'enrichissement fondamental avant coût du capital.",
  },
  net_owner_return: {
    title: "Net Owner Return (survaleur actionnaire)",
    summary:
      "Total Owner Return diminué de la charge d'équité : indique si l'entreprise crée véritablement de la richesse au-delà du coût de ses fonds propres.",
    formula: "(CBV_t2 + Dividendes − Equity Charge − CBV_t1) / CBV_t1",
    interpretation: "Positif = création nette de valeur économique pour l'actionnaire.",
  },
  buffett_irr: {
    title: "TRI Buffett implicite",
    summary:
      "Taux de rentabilité interne annualisé implicite sur 10 ans en projetant les capitaux propres (ou Owner Earnings) au rythme de croissance soutenable et en intégrant les dividendes.",
    interpretation: "À comparer au taux sans risque ou à votre objectif de rendement (ex. > 10-12 %).",
  },
  forward_return_yacktman: {
    title: "Rendement prospectif (Yacktman)",
    summary:
      "Estimation du rendement annuel futur combinant rendement du Free Cash Flow sur le prix payé (FCF Yield) et croissance organique attendue (ou inflation/CROIC).",
    formula: "FCF Yield + g",
    interpretation: "Plus il est élevé au-dessus du WACC ou des obligations d'État, plus le titre est attractif.",
  },
  payback_market: {
    title: "Payback marché estimé",
    summary:
      "Nombre d'années théoriques nécessaires pour que les Free Cash Flows cumulés et actualisés (ou croissants) remboursent le cours actuel de l'action.",
    interpretation: "Plus ce délai est court (ex. < 8 ans), plus le prix payé paraît raisonnable.",
  },
  rcagr_67: {
    title: "rCAGR 67% (croissance ajustée du risque)",
    summary:
      "Taux de croissance annuel composé issu d'une régression log-linéaire historique, pénalisé par la dispersion (écart-type) de la série afin de privilégier les croissances régulières.",
    formula: "CAGR_régression − 1 × σ_résidus (niveau ~67 %)",
  },

  // === LES 13 COMPOSANTES PONDÉRÉES + 6 MÉTHODES COMPLÉMENTAIRES ===
  dcf_fcf: {
    title: "DCF FCF (Flux de trésorerie actualisés — Poids 5)",
    summary:
      "Actualise au WACC les Free Cash Flows à la firme (FCFF) projetés sur 5 ans avec dégradation progressive de la croissance, puis ajoute la valeur terminale perpétuelle moins la dette nette.",
    formula: "Σ FCFF_t / (1 + WACC)^t + VT / (1 + WACC)^5 − Dette nette",
  },
  buffett: {
    title: "Méthode Buffett (Owner Earnings — Poids 4)",
    summary:
      "Actualise sur 10 ans les 'Owner Earnings' (résultat net + amortissements − CapEx de maintenance) au coût des capitaux propres Ke + valeur terminale.",
    formula: "Σ OE_t / (1 + Ke)^t + VT_10 / (1 + Ke)^10",
  },
  residual_income: {
    title: "Residual Income (Revenu résiduel — Poids 3)",
    summary:
      "Ajoute à la valeur comptable actuelle (BVPS) la somme actualisée des surprofits futurs générés au-delà du coût des capitaux propres Ke.",
    formula: "BVPS + Σ (BPA_t − Ke × BVPS_{t-1}) / (1 + Ke)^t",
  },
  graham_formula: {
    title: "Formule de Benjamin Graham (Poids 3)",
    summary:
      "Valorisation historique reliant le BPA normalisé, la croissance attendue g et le taux obligataire AAA (Y). Le mode corrigé corrige les parenthèses d'Uncle Stock.",
    formula: "V = BPA × (8,5 + 2g) × 4,4 / Y",
  },
  epv: {
    title: "EPV — Earnings Power Value (Poids 3)",
    summary:
      "Valeur de capacité bénéficiaire sans hypothèse de croissance : capitalise le NOPAT normalisé au WACC puis ajuste de la trésorerie et de la dette.",
    formula: "EPV_Equity = (EBIT × (1 − T)) / WACC + Trésorerie − Dette",
  },
  value_driver: {
    title: "Value Driver Formula (McKinsey — Poids 2)",
    summary:
      "Relie directement la valeur à la croissance g, au rendement sur capital investi (ROIC) et au WACC en modélisant le taux de réinvestissement nécessaire g / ROIC.",
    formula: "VE = NOPAT × (1 − g / ROIC) / (WACC − g)",
  },
  lynch: {
    title: "Méthode Peter Lynch (Poids 2)",
    summary:
      "Règle du juste prix fondée sur le ratio PEG = 1 : un multiple juste égal au taux de croissance des bénéfices augmenté du rendement du dividende.",
    formula: "VI = BPA × (Croissance % + Dividende %)",
  },
  graham_number: {
    title: "Nombre de Graham (Poids 2)",
    summary:
      "Plafond de valorisation défensif combinant BPA et valeur comptable par action, correspondant à un P/E max de 15 et un P/B max de 1,5 (15 × 1,5 = 22,5).",
    formula: "√(22,5 × BPA × BVPS)",
  },
  ebitda_7_5: {
    title: "Multiple 7,5× EBITDA (Poids 2)",
    summary:
      "Estime la valeur d'entreprise à 7,5 fois l'EBITDA moyen/courant, puis retranche la dette nette, les intérêts minoritaires et les actions préférentielles.",
    formula: "(7,5 × EBITDA − Dette nette − Minoritaires − Préf.) / Actions",
  },
  adjusted_lynch: {
    title: "Peter Lynch ajusté (Poids 1)",
    summary:
      "Variante de la formule de Lynch intégrant la solidité bilancielle (trésorerie nette par action ou ajustement du levier financier).",
  },
  price_ref: {
    title: "Cours actuel (référence Uncle Stock — Poids 1)",
    summary:
      "Uncle Stock intègre le cours du marché avec un poids de 1 dans la moyenne pondérée ; le Mode Corrigé l'exclut pour rester 100 % indépendant du marché.",
  },
  hold_5y: {
    title: "Hold 5 Years (Poids 1)",
    summary:
      "Valeur actuelle d'une détention à 5 ans fondée sur le BPA projeté à horizon 5 ans valorisé à un multiple cible, plus dividendes, actualisés au taux de rendement exigé.",
  },
  dcf_fcf_no_growth: {
    title: "DCF FCF sans croissance (Poids 1)",
    summary:
      "Valeur plancher d'un modèle DCF supposant zéro croissance perpétuelle (g = 0 %) : mesure ce que vaut l'entreprise sur ses seuls flux actuels.",
    formula: "FCFF_0 / WACC − Dette nette",
  },
  dcf_oe: {
    title: "DCF Owner Earnings (complémentaire)",
    summary:
      "Modèle DCF à 2 phases basé sur les Owner Earnings disponibles pour les actionnaires plutôt que sur le FCFF.",
  },
  linear_reg_100y: {
    title: "Régression linéaire 100 ans",
    summary:
      "Extrapole la tendance linéaire de très long terme du cours ou de la création de valeur fondamentale pour situer le prix par rapport à sa droite de tendance.",
  },
  quad_reg_100y: {
    title: "Régression quadratique 100 ans",
    summary:
      "Modèle polynomial d'ordre 2 capturant l'accélération ou décélération séculaire de la croissance sur longue période.",
  },
  omalley: {
    title: "Méthode O'Malley",
    summary:
      "Valorisation basée sur le flux de dividendes et la croissance du bénéfice sur un cycle long avec prise en compte de la marge de sécurité.",
  },
  payback_5y: {
    title: "Payback 5 ans",
    summary:
      "Somme des Free Cash Flows (ou bénéfices) cumulés sur les 5 prochaines années actualisés ou non, reflétant le prix qu'un acheteur privé récupère en 5 ans.",
  },
  payback_years: {
    title: "Années de Payback (solveur)",
    summary:
      "Horizon en années nécessaire pour que la somme des FCF futurs couvre la capitalisation boursière actuelle.",
  },

  // === KPI HEADER, VALORISATION & MARCHÉ ===
  market_cap: {
    title: "Capitalisation boursière",
    summary:
      "Valeur totale des capitaux propres de l'entreprise cotée en bourse, égale au nombre total d'actions multiplié par le cours actuel.",
    formula: "Cours × Nombre d'actions en circulation",
  },
  dividend_yield: {
    title: "Rendement du dividende",
    summary:
      "Revenu annuel versé sous forme de dividendes rapporté au cours actuel de l'action.",
    formula: "(Dividende annuel par action / Cours) × 100",
  },
  beta: {
    title: "Bêta (β)",
    summary:
      "Sensibilité statistique du titre aux variations de son indice de référence. Mesure le risque systématique (de marché).",
    interpretation:
      "β = 1,0 : évolue comme le marché ; β < 1 : action défensive ; β > 1 : titre plus volatil / offensif.",
  },
  price_dynamics: {
    title: "Dynamique du cours",
    summary:
      "Tendance technique synthétique du cours par rapport à ses moyennes mobiles clés (MMA 50 et MMA 200 jours).",
  },
  shares_outstanding: {
    title: "Nombre d'actions en circulation",
    summary:
      "Total des actions ordinaires détenues par l'ensemble des investisseurs (hors actions auto-détenues). Sert de dénominateur aux métriques par action.",
  },
  float_pct: {
    title: "Flottant (%)",
    summary:
      "Part du capital effectivement disponible à la négociation sur le marché public (hors participations de contrôle, fondateurs ou État).",
    interpretation: "Un flottant élevé améliore la liquidité du titre.",
  },
  insiders_pct: {
    title: "Détention des initiés (%)",
    summary:
      "Part du capital détenue par les dirigeants, administrateurs et fondateurs. Un alignement fort avec les actionnaires minoritaires est souvent positif.",
  },
  institutions_pct: {
    title: "Détention institutionnelle (%)",
    summary:
      "Part du capital détenue par les fonds de pension, ETF, banques, assureurs et sociétés de gestion.",
  },
  short_ratio: {
    title: "Short Ratio (Days to Cover)",
    summary:
      "Nombre de jours de volume moyen nécessaires aux vendeurs à découvert pour racheter l'ensemble de leurs positions courtes.",
    formula: "Actions vendues à découvert / Volume journalier moyen",
    interpretation: "Un ratio élevé (> 5-10 jours) signale un fort scepticisme ou un risque de short squeeze.",
  },
  short_pct_float: {
    title: "Flottant en VAD (% Short of Float)",
    summary:
      "Pourcentage du flottant actuellement vendu à découvert par des investisseurs pariant sur une baisse du cours.",
  },
  pe_ttm: {
    title: "PER TTM (Price / Earnings 12 mois glissants)",
    summary:
      "Multiple de valorisation indiquant combien d'années de bénéfices nets actuels le marché paie aujourd'hui.",
    formula: "Cours / BPA des 12 derniers mois",
    interpretation: "À comparer au secteur, au taux de croissance (PEG) et à la moyenne historique du titre.",
  },
  pe_forward: {
    title: "PER prévisionnel (Forward P/E)",
    summary:
      "Multiple cours/bénéfice basé sur le consensus des bénéfices par action attendus pour les 12 prochains mois.",
    formula: "Cours / BPA estimé (N+1)",
  },
  peg: {
    title: "Ratio PEG (Price / Earnings-to-Growth)",
    summary:
      "Rapporte le PER au taux de croissance attendu des bénéfices pour juger si une croissance élevée justifie un multiple élevé.",
    formula: "PER / Croissance annuelle du BPA (%)",
    interpretation: "< 1,0 : potentiellement sous-évalué au regard de la croissance ; > 2,0 : valorisation exigeante.",
  },
  pb: {
    title: "Price-to-Book (P/B)",
    summary:
      "Rapport entre la capitalisation boursière et la valeur comptable nette des capitaux propres (actif net comptable).",
    formula: "Cours / Valeur comptable par action",
  },
  ev_ebitda: {
    title: "VE / EBITDA (Enterprise Value / EBITDA)",
    summary:
      "Multiple comparant la valeur totale de l'entreprise (dette nette incluse) à son excédent brut d'exploitation. Permet de comparer des sociétés différemment endettées.",
    formula: "(Capitalisation + Dette nette) / EBITDA",
  },
  ev_revenue: {
    title: "VE / Chiffre d'affaires (EV / Sales)",
    summary:
      "Multiple rapportant la valeur d'entreprise au chiffre d'affaires annuel. Utile pour comparer des sociétés en forte croissance ou à marges temporairement comprimées.",
  },
  mma50: {
    title: "MMA 50 (Moyenne mobile arithmétique 50 jours)",
    summary: "Moyenne des 50 dernières clôtures, baromètre de la tendance boursière à moyen terme.",
  },
  mma200: {
    title: "MMA 200 (Moyenne mobile arithmétique 200 jours)",
    summary:
      "Moyenne des 200 dernières clôtures, référence majeure de la tendance de long terme (support/résistance institutionnelle).",
  },
  w52_range: {
    title: "Fourchette 52 semaines",
    summary:
      "Cours le plus bas et le plus haut atteints au cours des 52 dernières semaines glissantes.",
  },
  target_price: {
    title: "Objectif de cours moyen (Consensus)",
    summary:
      "Moyenne arithmétique des objectifs de cours à 12 mois publiés par les analystes financiers couvrant la valeur.",
  },

  // === MACRO & SENTIMENT ===
  sentiment_90j: {
    title: "Sentiment agrégé (90 jours)",
    summary:
      "Indice normalisé issu des flux d'actualités EODHD mesurant la tonalité médiatique (positive vs négative) sur les 90 derniers jours.",
    interpretation: "+0,10 et plus : tonalité haussière ; −0,10 et moins : tonalité négative.",
  },
  gdp_growth: {
    title: "Croissance du PIB",
    summary: "Variation annuelle réelle du Produit Intérieur Brut du pays de cotation/siège.",
  },
  inflation_cpi: {
    title: "Inflation IPC (CPI)",
    summary: "Variation annuelle de l'indice des prix à la consommation, influençant taux directeurs et pouvoir de prix.",
  },
  unemployment: {
    title: "Taux de chômage",
    summary: "Part de la population active sans emploi, indicateur avancé du cycle économique et des tensions salariales.",
  },
  tbill_4w: {
    title: "US T-Bill 4 semaines",
    summary: "Rendement annualisé des bons du Trésor américain à 1 mois (référence monétaire très court terme).",
  },
  tbill_13w: {
    title: "US T-Bill 13 semaines",
    summary: "Rendement annualisé des bons du Trésor américain à 3 mois.",
  },
  risk_free_rate: {
    title: "Taux sans risque (52 semaines / 10 ans)",
    summary:
      "Taux de référence souverain servant de socle au calcul du CAPM (Ke), du WACC et des ratios de Sharpe/Sortino.",
  },

  // === RISQUE & PERFORMANCE AJUSTÉE ===
  volatility: {
    title: "Volatilité historique (annualisée)",
    summary:
      "Écart-type annualisé des rendements quotidiens ajustés des dividendes : mesure l'amplitude moyenne des fluctuations du cours.",
    formula: "σ_quotidien × √252",
  },
  semi_volatility: {
    title: "Semi-volatilité (baissière)",
    summary:
      "Mesure uniquement la dispersion des rendements négatifs (sous zéro ou sous la cible), ignorant la volatilité 'positive' des fortes hausses.",
  },
  max_drawdown: {
    title: "Max Drawdown (perte maximale)",
    summary:
      "Baisse maximale en pourcentage subie entre un plus haut historique sur la période et le creux suivant avant un nouveau sommet.",
    interpretation: "Mesure le pire scénario historique subi par un investisseur entré au plus haut.",
  },
  max_dd_days: {
    title: "Durée maximale sous un sommet",
    summary:
      "Nombre maximal de jours écoulés avant que le titre ne retrouve et ne dépasse son précédent plus haut.",
  },
  var_95: {
    title: "VaR 95% (Value at Risk quotidienne)",
    summary:
      "Seuil de perte journalière qui n'est dépassé que dans 5 % des séances les plus défavorables (1 séance sur 20 environ).",
  },
  cvar_95: {
    title: "CVaR 95% (Conditional VaR / Expected Shortfall)",
    summary:
      "Perte moyenne constatée lors des 5 % pires séances (au-delà du seuil VaR 95 %) : capture mieux les krachs extrêmes ('queues épaisses').",
  },
  ulcer: {
    title: "Ulcer Index",
    summary:
      "Mesure l'intensité combinée de la profondeur et de la durée des replis (drawdowns) sur la période : plus il est faible, plus la trajectoire est confortable.",
    formula: "√( moyenne(Drawdown_i²) )",
  },
  sharpe: {
    title: "Ratio de Sharpe",
    summary:
      "Rendement excédentaire (au-dessus du taux sans risque) obtenu par unité de volatilité totale supportée.",
    formula: "(Rendement annualisé − Rf) / Volatilité",
    interpretation: "> 1,0 : très bon couple rendement/risque ; > 2,0 : exceptionnel ; < 0 : sous-performe le taux sans risque.",
  },
  sortino: {
    title: "Ratio de Sortino",
    summary:
      "Variante du ratio de Sharpe ne pénalisant que la volatilité baissière (semi-volatilité) plutôt que les hausses rapides.",
    formula: "(Rendement annualisé − Rf) / Semi-volatilité",
  },
  calmar: {
    title: "Ratio de Calmar",
    summary:
      "Rapporte le rendement annuel moyen au pire recul historique (Max Drawdown) sur la période.",
    formula: "Rendement annualisé / |Max Drawdown|",
  },
  excess_calmar: {
    title: "Excess Calmar",
    summary:
      "Ratio de Calmar calculé sur le rendement excédentaire au-dessus du taux sans risque divisé par le Max Drawdown.",
    formula: "(Rendement annualisé − Rf) / |Max Drawdown|",
  },
  martin: {
    title: "Ratio de Martin (Ulcer Performance Index)",
    summary:
      "Rapporte le rendement excédentaire à l'Ulcer Index, mesurant la rémunération obtenue par unité de stress de drawdown prolongé.",
    formula: "(Rendement annualisé − Rf) / Ulcer Index",
  },

  // === FONDAMENTAUX, MARGES, RENTABILITÉ & BILAN ===
  rev: {
    title: "Chiffre d'affaires (Total Revenue)",
    summary: "Somme totale des ventes de biens et services facturés par l'entreprise sur l'exercice.",
  },
  rev_growth: {
    title: "Croissance du chiffre d'affaires",
    summary: "Évolution en pourcentage des ventes d'une période à la période comparable précédente.",
  },
  gross_m: {
    title: "Marge brute (Gross Margin)",
    summary:
      "Part du chiffre d'affaires conservée après déduction des coûts directs de production ou d'achat (COGS). Reflète le pouvoir de prix et la structure de coûts directs.",
    formula: "(Marge brute / Chiffre d'affaires) × 100",
  },
  ebitda: {
    title: "EBITDA (Excédent brut d'exploitation)",
    summary:
      "Résultat opérationnel avant intérêts, impôts, dépréciations et amortissements : mesure la capacité de génération de cash brute de l'activité.",
  },
  ebitda_m: {
    title: "Marge d'EBITDA",
    summary: "EBITDA exprimé en pourcentage du chiffre d'affaires.",
    formula: "(EBITDA / CA) × 100",
  },
  opinc: {
    title: "Résultat opérationnel (EBIT)",
    summary:
      "Bénéfice généré par l'exploitation courante après dépréciations et amortissements, mais avant charges financières et impôts.",
  },
  op_m: {
    title: "Marge opérationnelle",
    summary: "Part du chiffre d'affaires convertie en bénéfice d'exploitation (EBIT). Indicateur clé de l'efficacité opérationnelle.",
    formula: "(EBIT / CA) × 100",
  },
  ni: {
    title: "Résultat net (Net Income)",
    summary: "Bénéfice final revenant aux actionnaires après l'ensemble des charges, intérêts et impôts.",
  },
  net_m: {
    title: "Marge nette",
    summary: "Pourcentage de chaque euro/dollar de chiffre d'affaires qui reste en bénéfice net final.",
    formula: "(Résultat net / CA) × 100",
  },
  ocf: {
    title: "Flux de trésorerie d'exploitation (CFO / Operating Cash Flow)",
    summary: "Liquidités réellement encaissées par l'activité courante après variation du besoin en fonds de roulement.",
  },
  fcf: {
    title: "Free Cash Flow (Flux de trésorerie disponible)",
    summary:
      "Trésorerie réelle générée par l'activité après financement des investissements (CapEx). Sert à verser les dividendes, racheter des actions ou désendetter.",
    formula: "CFO − |CapEx|",
  },
  fcf_m: {
    title: "Marge de Free Cash Flow",
    summary: "Part du chiffre d'affaires effectivement convertie en liquidités libres après CapEx.",
    formula: "(FCF / CA) × 100",
  },
  fcf_conversion: {
    title: "Conversion FCF / Résultat net",
    summary:
      "Vérifie la qualité des bénéfices comptables : un taux proche ou supérieur à 90-100 % confirme que les profits se transforment en vrai cash.",
    formula: "(FCF / Résultat net) × 100",
  },
  capex_to_revenue: {
    title: "Intensité capitalistique (CapEx / CA)",
    summary:
      "Part du chiffre d'affaires réinvestie chaque année dans l'outil productif. Plus elle est basse à rentabilité égale, plus le modèle est 'asset-light'.",
  },
  roa: {
    title: "ROA (Return on Assets — Rentabilité économique)",
    summary: "Efficacité globale avec laquelle l'ensemble des actifs au bilan génère du bénéfice net.",
    formula: "(Résultat net / Total actifs) × 100",
  },
  roe: {
    title: "ROE (Return on Equity — Rentabilité des capitaux propres)",
    summary:
      "Rendement comptable dégagé sur les fonds propres des actionnaires. Attention à vérifier qu'il ne vient pas d'un endettement excessif.",
    formula: "(Résultat net / Capitaux propres) × 100",
  },
  roic: {
    title: "ROIC (Return on Invested Capital)",
    summary:
      "Mesure maîtresse de création de valeur : compare le bénéfice opérationnel après impôts (NOPAT) à tout le capital immobilisé (dette + fonds propres).",
    formula: "NOPAT / Capital investi",
    interpretation: "Un ROIC durablement supérieur au WACC (> 12-15 %) est la signature d'un avantage concurrentiel (MOAT).",
  },
  croic: {
    title: "CROIC (Cash Return on Invested Capital)",
    summary:
      "Équivalent cash du ROIC : rapporte le Free Cash Flow généré au capital investi total, éliminant les biais comptables.",
    formula: "FCF / Capital investi",
  },
  tax_rate: {
    title: "Taux effectif d'imposition",
    summary: "Charge d'impôts rapportée au résultat avant impôts.",
    formula: "(Impôts / Résultat avant impôt) × 100",
  },
  cap_inv: {
    title: "Capital investi",
    summary: "Montant total des ressources financières engagées dans l'exploitation (Capitaux propres + Dette financière − Trésorerie excédentaire).",
  },
  ebitda_ps: {
    title: "EBITDA par action",
    summary: "EBITDA total divisé par le nombre d'actions diluées / en circulation.",
  },
  eps: {
    title: "BPA / EPS (Bénéfice par action)",
    summary: "Quote-part du bénéfice net consolidé revenant à chaque action. Base du PER et de la croissance par action.",
    formula: "Résultat net / Actions",
  },
  fcf_ps: {
    title: "Free Cash Flow par action",
    summary: "Liquidités disponibles générées par action après investissements.",
    formula: "FCF / Actions",
  },
  eq: {
    title: "Capitaux propres (Stockholders Equity)",
    summary: "Actif net comptable revenant aux actionnaires (Actifs − Total des passifs).",
  },

  // === SOLVABILITÉ & STRUCTURE FINANCIÈRE ===
  quick_r: {
    title: "Ratio de liquidité restreinte (Quick Ratio / Acid Test)",
    summary:
      "Capacité à couvrir les dettes à court terme avec les seuls actifs très liquides (sans compter les stocks).",
    formula: "(Actifs courants − Stocks) / Passifs courants",
    interpretation: "≥ 1,0× indique une bonne capacité à honorer les échéances immédiates sans brader les stocks.",
  },
  curr_r: {
    title: "Ratio de liquidité générale (Current Ratio)",
    summary: "Rapporte l'ensemble des actifs à court terme aux dettes exigibles à moins d'un an.",
    formula: "Actifs courants / Passifs courants",
    interpretation: "Idéalement entre 1,2× et 2,5× ; < 1,0× peut signaler une tension de trésorerie à court terme.",
  },
  nd_ebitda: {
    title: "Dette nette / EBITDA (Levier financier)",
    summary:
      "Nombre d'années d'EBITDA nécessaires pour rembourser intégralement la dette nette actuelle.",
    formula: "(Dette totale − Trésorerie) / EBITDA",
    interpretation: "< 0 : trésorerie nette positive ; 0 à 2× : levier sain ; > 3,5× : endettement élevé à surveiller.",
  },
  debt_assets: {
    title: "Dette sur actifs (%)",
    summary: "Part du bilan total financée par de la dette financière.",
    formula: "(Dette totale / Total actifs) × 100",
  },
  debt_eq: {
    title: "Dette / Capitaux propres (Gearing)",
    summary: "Mesure le poids de l'endettement financier par rapport aux fonds propres.",
    formula: "(Dette totale / Capitaux propres) × 100",
  },
  cov_ebitda: {
    title: "Couverture des intérêts par l'EBITDA",
    summary: "Nombre de fois où l'EBITDA couvre la charge annuelle d'intérêts de la dette.",
    formula: "EBITDA / Charges d'intérêts",
  },
  cov_ebit: {
    title: "Couverture des intérêts par l'EBIT (Interest Coverage)",
    summary: "Nombre de fois où le résultat opérationnel couvre les frais financiers.",
    formula: "EBIT / Charges d'intérêts",
    interpretation: "< 2× : zone fragile ; > 5× : très confortable.",
  },
  cov_ocf: {
    title: "Couverture des intérêts par le flux opérationnel",
    summary: "Nombre de fois où la trésorerie générée par l'exploitation couvre la charge d'intérêts.",
    formula: "CFO / Charges d'intérêts",
  },
  cost_debt: {
    title: "Coût apparent de la dette",
    summary: "Taux d'intérêt moyen payé sur la dette financière moyenne de la période.",
    formula: "Charges d'intérêts / Dette moyenne",
  },

  // === DISTRIBUTION ===
  div_paid: {
    title: "Dividendes versés",
    summary: "Montant total en numéraire distribué aux actionnaires au cours de l'exercice.",
  },
  payout_ni: {
    title: "Payout Ratio sur résultat net",
    summary: "Proportion du bénéfice net reversée sous forme de dividendes.",
    formula: "(Dividendes versés / Résultat net) × 100",
    interpretation: "< 60 % : dividende généralement bien couvert ; > 90 % : marge de manœuvre réduite.",
  },
  payout_fcf: {
    title: "Cash Payout Ratio (sur FCF)",
    summary:
      "Proportion du Free Cash Flow absorbée par le dividende : meilleur indicateur que le Payout comptable pour juger la pérennité du dividende.",
    formula: "(Dividendes versés / FCF) × 100",
  },

  // === CYCLE DE CONVERSION & EFFICACITÉ ===
  dsi: {
    title: "DSI — Nombre de jours en stock",
    summary: "Durée moyenne pendant laquelle les marchandises restent en stock avant d'être vendues.",
    formula: "(Stocks / Coût des ventes) × 365",
  },
  dso: {
    title: "DSO — Délai moyen de paiement clients",
    summary: "Nombre de jours moyen entre une vente et l'encaissement effectif auprès des clients.",
    formula: "(Créances clients / CA) × 365",
  },
  dpo: {
    title: "DPO — Délai moyen de paiement fournisseurs",
    summary: "Nombre de jours moyen dont bénéficie l'entreprise avant de régler ses fournisseurs.",
    formula: "(Dettes fournisseurs / Achats ou COGS) × 365",
  },
  ccc: {
    title: "CCC — Cycle de conversion de l'encaisse",
    summary:
      "Nombre de jours durant lesquels la trésorerie est immobilisée entre le paiement des fournisseurs et l'encaissement des clients.",
    formula: "DSI + DSO − DPO",
    interpretation: "Plus il est bas (voire négatif), plus l'entreprise finance sa croissance par son BFR.",
  },
  asset_turn: {
    title: "Rotation des actifs (Asset Turnover)",
    summary: "Chiffre d'affaires généré par chaque euro/dollar d'actif engagé au bilan.",
    formula: "Chiffre d'affaires / Total actifs",
  },
  sga_eq: {
    title: "Frais généraux / Capitaux propres",
    summary: "Poids des frais commerciaux et administratifs (SG&A) rapporté aux fonds propres.",
  },
  sga_rev: {
    title: "Frais généraux / CA (SG&A Margin)",
    summary: "Part du chiffre d'affaires absorbée par les frais commerciaux, administratifs et généraux.",
  },

  // === SCORES QUALITATIFS ===
  ih_score: {
    title: "IH Score (Investisseur Heureux /9)",
    summary:
      "Score qualité fondamental sur 9 points évaluant croissance, rentabilité (ROIC, marges), génération de cash (FCF), faible dilution et solidité du bilan + tendance sur les derniers exercices.",
    interpretation: "≥ 7/9 : qualité exceptionnelle ; 5–6,9 : solide ; < 4 : fragilités fondamentales.",
  },
  piotroski: {
    title: "F-Score de Piotroski (/9)",
    summary:
      "Score académique (Joseph Piotroski) sur 9 critères binaires mesurant l'amélioration annuelle de la profitabilité, de l'endettement/liquidité et de l'efficacité opérationnelle.",
    interpretation: "7 à 9 : santé financière robuste en amélioration ; 0 à 3 : signaux de détérioration.",
  },
  altman: {
    title: "Z-Score d'Altman",
    summary:
      "Modèle multifactoriel (Edward Altman) combinant 5 ratios pondérés (X1 à X5) pour estimer la solidité bilancielle et la probabilité de défaillance.",
    formula: "1,2·X1 + 1,4·X2 + 3,3·X3 + 0,6·X4 + 1,0·X5",
    interpretation: "> 3,0 : zone saine ; 1,8 à 3,0 : zone grise ; < 1,8 : zone de tension financière (hors banques/assurances).",
  },
  altman_x1: {
    title: "Altman X1 (BFR / Total actifs)",
    summary: "Mesure la liquidité nette à court terme rapportée à la taille du bilan.",
  },
  altman_x2: {
    title: "Altman X2 (Résultats non distribués / Actifs)",
    summary: "Reflète l'accumulation historique de profits réinvestis dans l'entreprise sans recourir à la dette.",
  },
  altman_x3: {
    title: "Altman X3 (EBIT / Total actifs)",
    summary: "Productivité opérationnelle pure des actifs indépendamment de la fiscalité et du levier financier.",
  },
  altman_x4: {
    title: "Altman X4 (Capitalisation / Total passifs)",
    summary: "Coussin de valeur de marché disponible avant que les passifs n'excèdent les actifs.",
  },
  altman_x5: {
    title: "Altman X5 (Chiffre d'affaires / Total actifs)",
    summary: "Capacité commerciale des actifs à générer du volume de ventes.",
  },

  // === INDICATEURS TECHNIQUES (GRAPHIQUE TRADINGVIEW) ===
  sma20: {
    title: "SMA 20 — Moyenne mobile simple 20 périodes",
    summary: "Moyenne arithmétique des 20 dernières clôtures. Suit la tendance court terme.",
  },
  sma50: {
    title: "SMA 50 — Moyenne mobile simple 50 périodes",
    summary: "Moyenne des 50 dernières clôtures. Repère classique de tendance intermédiaire.",
  },
  sma200: {
    title: "SMA 200 — Moyenne mobile simple 200 périodes",
    summary: "Moyenne des 200 dernières clôtures. Frontière de tendance haussière/baissière de long terme.",
  },
  ema20: {
    title: "EMA 20 — Moyenne mobile exponentielle",
    summary: "Accorde un poids plus important aux séances récentes pour réagir plus vite aux retournements.",
  },
  ema50: {
    title: "EMA 50 — Moyenne mobile exponentielle 50",
    summary: "Moyenne exponentielle intermédiaire, plus réactive que la SMA 50 lors des accélérations.",
  },
  boll: {
    title: "Bandes de Bollinger",
    summary: "Enveloppe dynamique tracée à ±2 écarts-types autour d'une moyenne mobile : s'élargit avec la volatilité et se resserre avant les cassures.",
  },
  supertrend: {
    title: "Supertrend (ATR)",
    summary: "Indicateur suiveur de tendance basé sur l'ATR : affiche un support vert en phase haussière et une résistance rouge en phase baissière.",
  },
  vwap: {
    title: "VWAP — Prix moyen pondéré par le volume",
    summary: "Prix d'équilibre moyen pondéré par les volumes échangés : référence clé des ordres institutionnels.",
  },
  sar: {
    title: "Parabolic SAR (Stop And Reverse)",
    summary: "Points paraboliques suivant le prix pour matérialiser des stops suiveurs et détecter les inversions de tendance.",
  },
  volume: {
    title: "Volume d'échanges",
    summary: "Nombre de titres échangés par barre : valide la conviction derrière une cassure ou un retournement.",
  },
  rsi: {
    title: "RSI — Relative Strength Index",
    summary: "Oscillateur de momentum borné entre 0 et 100 mesurant la vitesse des hausses vs baisses récentes.",
    interpretation: "> 70 : zone de surachat ; < 30 : zone de survente (ou divergence avec le cours).",
  },
  macd: {
    title: "MACD (Moving Average Convergence Divergence)",
    summary: "Différence entre deux moyennes exponentielles (12 et 26) accompagnée de sa ligne de signal (9) et d'un histogramme de momentum.",
  },
  rex: {
    title: "REX — Rex Oscillator",
    summary: "Mesure la 'vraie' valeur comportementale des bougies (TVB : position de clôture vs haut/bas/ouverture) lissée par sa ligne de signal.",
  },
  isopressure: {
    title: "IsoPressure (Isostock Pressure Backtested)",
    summary:
      "Oscillateur composite combinant RSI, Stochastique, CCI et MFI (volume) avec plusieurs moyennes mobiles de lissage pour capter la pression acheteuse/vendeuse.",
  },
  stoch: {
    title: "Stochastique (%K / %D)",
    summary: "Compare la clôture actuelle à la fourchette haut-bas des N dernières périodes pour repérer l'essoufflement d'un mouvement.",
    interpretation: "> 80 : surachat ; < 20 : survente.",
  },
  willr: {
    title: "Williams %R",
    summary: "Oscillateur borné entre 0 et −100 mesurant la proximité de la clôture par rapport au plus haut récent.",
    interpretation: "Entre 0 et −20 : surachat ; entre −80 et −100 : survente.",
  },
  cci: {
    title: "CCI — Commodity Channel Index",
    summary: "Mesure l'écart du prix typique par rapport à sa moyenne mobile statistique.",
    interpretation: "> +100 : forte impulsion / surachat ; < −100 : pression baissière / survente.",
  },
  roc: {
    title: "ROC — Rate of Change",
    summary: "Variation en pourcentage du cours par rapport à N périodes plus tôt : mesure pure de la vitesse de progression.",
  },
  atr: {
    title: "ATR — Average True Range",
    summary: "Amplitude moyenne réelle des séances (incluant les gaps). Sert à dimensionner stops et volatilité courante.",
  },
  adx: {
    title: "ADX — Average Directional Index",
    summary: "Mesure la force d'une tendance (sans indiquer son sens) : faible en range (< 20), fort en tendance marquée (> 25).",
  },
  obv: {
    title: "OBV — On-Balance Volume",
    summary: "Cumul directionnel des volumes (ajoutés les jours de hausse, retranchés les jours de baisse) pour repérer l'accumulation ou la distribution.",
  },

  // === WATCHLIST / SÉANCES / ÉTATS ===
  open_adj: {
    title: "Ouverture ajustée",
    summary: "Cours d'ouverture ajusté rétroactivement des dividendes détachés et divisions d'actions (splits) pour rester cohérent dans le temps.",
  },
  high_adj: {
    title: "Plus haut ajusté",
    summary: "Plus haut de séance ajusté des dividendes et splits.",
  },
  low_adj: {
    title: "Plus bas ajusté",
    summary: "Plus bas de séance ajusté des dividendes et splits.",
  },
  close_adj: {
    title: "Clôture ajustée",
    summary: "Cours de clôture ajusté des dividendes et splits : base recommandée pour comparer la performance réelle et calculer les indicateurs.",
  },
  var_day: {
    title: "Variation journalière",
    summary: "Évolution en pourcentage par rapport à la clôture ajustée de la séance précédente.",
  },
  perf_horizon: {
    title: "Performance sur horizon",
    summary: "Rendement total ajusté des dividendes réinvestis sur la période sélectionnée.",
  },
  eps_surprise: {
    title: "Surprise BPA",
    summary: "Écart en pourcentage entre le bénéfice par action réellement publié et le consensus moyen des analystes.",
    formula: "((BPA publié − BPA estimé) / |BPA estimé|) × 100",
  },
  moat_signal: {
    title: "Avantage concurrentiel durable (MOAT)",
    summary:
      "Barrière économique structurelle (marque, effets de réseau, coûts de changement, brevets, avantage coût, échelle) protégeant les marges et le ROIC contre la concurrence.",
  },
  // Scores & Indicateurs Uncle Stock (31)
  advice: {
    title: "Advice (Verdict Uncle Stock)",
    summary:
      "Synthèse décisionnelle classant le titre (Strong Buy, Buy, Hold, Sell, Strong Sell, Caution) selon l'Uncle Stock Score, la décote intrinsèque, le Trap Score, Quality, Value et Health.",
    interpretation: "Strong Buy/Buy exigent une décote (is_undervalued) et aucun signal critique de Value Trap.",
  },
  categories: {
    title: "Categories (Étiquettes factorielles)",
    summary:
      "Liste des profils stratégiques remplis par l'action : Value, Quality, Growth, Safe, Dividend, Momentum, Magic Formula, Conservative, etc.",
  },
  is_undervalued: {
    title: "Sous-évaluation intrinsèque (is_undervalued)",
    summary:
      "Indicateur booléen vérifiant si le cours actuel offre une décote suffisante par rapport à la valeur intrinsèque calculée.",
    formula: "Cours actuel < Valeur intrinsèque × (1 − Marge de sécurité requise)",
  },
  trap_score: {
    title: "Trap Score (Risque de Value Trap)",
    summary:
      "Détecte les titres apparemment bon marché mais fragiles (Altman Z faible, baisse des ventes/marges, effet de levier excessif ou qualité comptable dégradée).",
    interpretation: "Plus le Trap Score est bas (proche de 0), plus le risque de piège à valeur est faible.",
  },
  uncle_stock_score: {
    title: "Uncle Stock Score (Score global)",
    summary:
      "Note composite globale de 0 à 100 combinant Qualité, Valeur, Rendement actionnaire, Équilibre financier, Santé financière, Croissance et Prévisibilité.",
    interpretation: "Mode Documenté divise par 1420 ; mode Vérifié aligne le dénominateur sur 1540 avec étirement sigmoïde (k = 4).",
  },
  quality_score: {
    title: "Quality Score",
    summary:
      "Mesure de 0 à 100 la rentabilité du capital (ROIC, ROE), la solidité des marges (brute et opérationnelle) et l'absence de dilution ou d'endettement excessif.",
  },
  value_score: {
    title: "Value Score",
    summary:
      "Évalue de 0 à 100 le caractère attractif de la valorisation (P/E, P/B, P/FCF, EV/EBITDA, rendement des flux et décote sur valeur intrinsèque).",
  },
  yield_score: {
    title: "Yield Score (Rendement total actionnaire)",
    summary:
      "Agrège dividende, couverture du dividende, croissance du dividende, rachats d'actions nets (Buyback Yield) et rendement FCF.",
    interpretation: "Mode Documenté divise par 1810 ; mode Vérifié corrige le dénominateur à 2170.",
  },
  balance_score: {
    title: "Balance Score (Solidité du bilan)",
    summary:
      "Mesure de 0 à 100 la structure financière : liquidité générale/immédiate, levier Dette/Fonds propres, Dette Nette/EBITDA et couverture des intérêts.",
  },
  balance_value_score: {
    title: "Balance Value Score (Valeur d'actif net)",
    summary:
      "Évalue le coussin patrimonial (Price-to-Book, Tangible Book, NCAV de Graham et actifs liquides nets rapportés à la capitalisation).",
  },
  financial_health_score: {
    title: "Financial Health Score (Santé financière)",
    summary:
      "Score composite de robustesse et de solvabilité combinant Altman Z-Score, Ohlson O-Score, couverture de la dette et génération de cash-flow libre.",
  },
  growth_rate: {
    title: "Growth Rate (Score de croissance)",
    summary:
      "Agrège les taux de croissance historiques (CA, BPA, FCF, Capitaux propres) sur 3 à 7 ans en privilégiant la régularité (RCAGR).",
  },
  predictability_score: {
    title: "Predictability Score (Prévisibilité)",
    summary:
      "Mesure la régularité et la faible volatilité des résultats, du chiffre d'affaires et des marges sur l'historique disponible.",
  },
  mohanram_g_score: {
    title: "Mohanram G-Score (0 à 8)",
    summary:
      "Score académique conçu pour les valeurs de croissance (P/B élevé), notant 8 critères sur la profitabilité, la stabilité du ROA/CA et les investissements (R&D, CapEx).",
    interpretation: "≥ 6 : valeur de croissance solide ; ≤ 2 : croissance fragile.",
  },
  montier_c_score: {
    title: "Montier C-Score (0 à 6 — Risque créatif)",
    summary:
      "Score d'alerte comptable créé par James Montier détectant 6 signaux typiques de comptabilité agressive (croissance créances/stocks > ventes, divergence FCF/résultat net, etc.).",
    interpretation: "0–1 : comptabilité saine ; ≥ 4 : signaux d'alerte comptable importants.",
  },
  levermann_score: {
    title: "Score Levermann (−13 à +13)",
    summary:
      "Méthode quantitative allemande de Susan Levermann attribuant +1, 0 ou −1 à 13 critères (ROE, marge EBIT, ratio de fonds propres, PER 5 ans, PER courant, momentum, révisions).",
    interpretation: "≥ 4 (ou ≥ 7 pour Small/Mid Caps) : signal d'achat selon Levermann.",
  },
  company_score: {
    title: "Company Score",
    summary:
      "Synthèse interne focalisée sur l'entreprise seule (hors prix de marché) : Qualité opérationnelle, Santé du bilan, Croissance et Prévisibilité.",
  },
  oshaughnessy_vc3: {
    title: "O'Shaughnessy Value Composite 3 (VC3)",
    summary:
      "Score multifactoriel de James O'Shaughnessy combinant Price/Book, Price/Sales, EV/EBITDA, Price/Cash Flow et rendement actionnaire.",
  },
  greenblatt_score: {
    title: "Magic Formula de Joel Greenblatt",
    summary:
      "Classement combinant l'Earnings Yield (EBIT / Enterprise Value) et le Return on Capital (EBIT / (BFR + Actifs immobilisés nets)).",
    formula: "Score combiné de Earnings Yield + ROC",
  },
  pim_van_vliet_score: {
    title: "Score Conservateur Pim van Vliet",
    summary:
      "Approche Low-Volatility Factor combinant faible volatilité historique, rendement actionnaire (dividende + rachats) et momentum de cours à 12 mois.",
  },
  erp5_score: {
    title: "Rank ERP5 (Value & Rentabilité)",
    summary:
      "Indicateur associant Earnings Yield, ROIC, Price-to-Book et Price-to-Book × P/E (5-factor value & profitability).",
  },
  slater_score: {
    title: "Score Jim Slater (Zulu Principle)",
    summary:
      "Évalue les valeurs de croissance à prix raisonnable (PEG < 1, forte croissance du BPA, flux de trésorerie positifs, faible endettement et taille maîtrisée).",
  },
  ohlson_o_score: {
    title: "Ohlson O-Score (Probabilité de défaut)",
    summary:
      "Modèle logistique à 9 variables comptables (taille, levier, liquidité, fonds de roulement, rentabilité, variations de résultat) estimant la probabilité de faillite à 1 an.",
    formula: "P(défaut) = 1 / (1 + e^(−O))",
    interpretation: "O < −0,5 (P < 38 %) : risque faible ; O > +0,5 (P > 62 %) : zone de détresse.",
  },
  beneish_m_score: {
    title: "Beneish M-Score (Manipulation des bénéfices)",
    summary:
      "Modèle probabiliste à 8 ratios financiers (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA) détectant la manipulation à la hausse des résultats.",
    interpretation: "M > −1,78 : forte probabilité de manipulation comptable ; M ≤ −2,22 : profil sain.",
  },
  dechow_f_score: {
    title: "Dechow F-Score (Risque d'anomalie comptable)",
    summary:
      "Score issu de Dechow et al. (2011) estimant la probabilité relative d'inexactitude comptable (RSST accruals, variations créances/stocks, actifs non monétaires, marge, émission de titres).",
    interpretation: "F ≈ 1,0 : risque moyen de marché ; F > 1,85 : risque élevé de retraitement comptable.",
  },
  esg_score: {
    title: "Score ESG global",
    summary:
      "Note consolidée Environnement, Social et Gouvernance (lorsque publiée par le fournisseur de données).",
  },
  environment_score: {
    title: "Score Environnement (E)",
    summary:
      "Pilier environnemental mesurant l'empreinte carbone, l'énergie, les ressources et les risques climatiques.",
  },
  social_score: {
    title: "Score Social (S)",
    summary:
      "Pilier social évaluant les conditions de travail, le capital humain, la sécurité et l'impact sociétal.",
  },
  governance_score: {
    title: "Score Gouvernance (G)",
    summary:
      "Pilier gouvernance mesurant l'indépendance du conseil, la rémunération des dirigeants, l'éthique et les droits des actionnaires.",
  },
};

const ALIAS_MAP: Record<string, string> = {
  // Intrinsic method IDs & labels
  "margin_of_safety": "margin_of_safety",
  "marge de securite": "margin_of_safety",
  "marge de sécurité": "margin_of_safety",
  "marge sec.": "margin_of_safety",
  "marge séc.": "margin_of_safety",
  "marge sécurité": "margin_of_safety",
  "vi globale": "intrinsic_value",
  "valeur intrinsèque": "intrinsic_value",
  "valeur intrinseque": "intrinsic_value",
  "ratio cours / vi": "price_to_iv",
  "cours / vi": "price_to_iv",
  "wacc": "wacc",
  "ke (capm) / kd net": "ke_capm",
  "ke (capm)": "ke_capm",
  "kd net": "kd_net",
  "charge d’équité / act.": "equity_charge",
  "charge d'equite / act.": "equity_charge",
  "total owner return": "total_owner_return",
  "net owner return": "net_owner_return",
  "tri buffett (implicite)": "buffett_irr",
  "tri buffett": "buffett_irr",
  "rdt prospectif yacktman": "forward_return_yacktman",
  "payback marché estimé": "payback_market",
  "rcagr": "rcagr_67",
  "rcagr 67%": "rcagr_67",
  // Capital & valuation labels
  "capitalisation boursière": "market_cap",
  "capitalisation boursiere": "market_cap",
  "rendement": "dividend_yield",
  "rendement du dividende": "dividend_yield",
  "bêta": "beta",
  "beta": "beta",
  "bêta (volatilité)": "beta",
  "ih score": "ih_score",
  "ih_score": "ih_score",
  "dynamique du cours": "price_dynamics",
  "nbr d’actions": "shares_outstanding",
  "nbr d'actions": "shares_outstanding",
  "actions en circulation": "shares_outstanding",
  "flottant": "float_pct",
  "initiés": "insiders_pct",
  "institutionnels": "institutions_pct",
  "short ratio": "short_ratio",
  "flottant en vad": "short_pct_float",
  "per ttm": "pe_ttm",
  "ratio c/b actuel (trailing p/e)": "pe_ttm",
  "per prévi.": "pe_forward",
  "ratio c/b prévisionnel (forward p/e)": "pe_forward",
  "ratio peg (price/earnings-to-growth)": "peg",
  "peg": "peg",
  "price-to-book (p/b)": "pb",
  "p/b": "pb",
  "p/b (cours / capitaux propres)": "pb",
  "ve/ebitda ttm": "ev_ebitda",
  "valeur d'entreprise / ebitda (ev/ebitda)": "ev_ebitda",
  "ve/ca ttm": "ev_revenue",
  "marge opé. ttm": "op_m",
  "marge nette ttm": "net_m",
  "roe ttm": "roe",
  "roa ttm": "roa",
  "Δ ca trim. yoy": "rev_growth",
  "Δ rn trim. yoy": "eps",
  "mma50": "mma50",
  "mma200": "mma200",
  "+ bas 52 s.": "w52_range",
  "+ haut 52 s.": "w52_range",
  "fourchette 52 semaines": "w52_range",
  "cible": "target_price",
  "cible moyenne": "target_price",
  "objectif moyen": "target_price",
  // Macro & sentiment
  "sentiment moyen (90j)": "sentiment_90j",
  "croissance pib": "gdp_growth",
  "inflation ipc": "inflation_cpi",
  "chômage": "unemployment",
  "us t-bill 4 sem.": "tbill_4w",
  "us t-bill 13 sem.": "tbill_13w",
  "taux sans risque 52 s.": "risk_free_rate",
  // Annual matrix & statements keys
  "mcap": "market_cap",
  "per": "pe_ttm",
  "shares": "shares_outstanding",
  "revenue_growth": "rev_growth",
  "gross_margin": "gross_m",
  "operating_margin": "op_m",
  "ebitda_margin": "ebitda_m",
  "net_margin": "net_m",
  "fcf_margin": "fcf_m",
  "debt_to_equity": "debt_eq",
  "net_debt_to_ebitda": "nd_ebitda",
  "current_ratio": "curr_r",
  "interest_coverage": "cov_ebit",
  "totalrevenue": "rev",
  "grossprofit": "gross_m",
  "operatingincome": "opinc",
  "ebit": "opinc",
  "netincome": "ni",
  "dilutedeps": "eps",
  "basiceps": "eps",
  "stockholdersequity": "eq",
  "operatingcashflow": "ocf",
  "freecashflow": "fcf",
  "capitalexpenditure": "capex_to_revenue",
  "cashdividendspaid": "div_paid",
  "piotroski": "piotroski",
  "f-score piotroski": "piotroski",
  "z-score altman": "altman",
  "x1": "altman_x1",
  "x2": "altman_x2",
  "x3": "altman_x3",
  "x4": "altman_x4",
  "x5": "altman_x5",
  // Watchlist & modal tabs
  "jour": "var_day",
  "semaine": "perf_horizon",
  "mois": "perf_horizon",
  "3 mois": "perf_horizon",
  "année": "perf_horizon",
  "clôture aj.": "close_adj",
  "ouverture aj.": "open_adj",
  "haut aj.": "high_adj",
  "bas aj.": "low_adj",
  "surprise": "eps_surprise",
  // Moat signal labels
  "roic / rentabilité": "roic",
  "marge brute": "gross_m",
  "marge opérationnelle": "op_m",
  "levier financier": "nd_ebitda",
  "génération fcf": "fcf_m",
  "flux de trésorerie disponible (free cash flow)": "fcf",
  "flux de trésorerie d'exploitation": "ocf",
  "ratio dette / fonds propres (debt-to-equity)": "debt_eq",
  "ratio de liquidité générale (current ratio)": "curr_r",
  "rentabilité des capitaux propres (roe)": "roe",
  "bénéfice par action (bpa trailing / forward)": "eps",
  "taux de distribution (payout ratio)": "payout_ni",
  "chiffre d'affaires (total revenue)": "rev",
  "croissance du chiffre d'affaires": "rev_growth",
  "marge brute (gross margin)": "gross_m",
  "marge opérationnelle (operating margin)": "op_m",
  "marge nette (profit margin)": "net_m",
  "ebitda (résultat opérationnel brut)": "ebitda",
  "bénéfice net attribuable (net income)": "ni",
};

function normalizeLookup(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s*\([^)]*\)\s*$/g, "")
    .replace(/\s+/g, " ");
}

/** Recherche tolérante d'une définition dans le glossaire (clé technique ou libellé UI). */
export function findFinanceTerm(keyOrLabel?: string | null): FinanceTermDefinition | null {
  if (!keyOrLabel) return null;
  const trimmed = keyOrLabel.trim();
  if (!trimmed) return null;

  if (FINANCE_GLOSSARY[trimmed]) return FINANCE_GLOSSARY[trimmed];

  const lower = trimmed.toLowerCase();
  if (FINANCE_GLOSSARY[lower]) return FINANCE_GLOSSARY[lower];
  if (ALIAS_MAP[lower] && FINANCE_GLOSSARY[ALIAS_MAP[lower]]) {
    return FINANCE_GLOSSARY[ALIAS_MAP[lower]];
  }

  const normalized = normalizeLookup(trimmed);
  if (FINANCE_GLOSSARY[normalized]) return FINANCE_GLOSSARY[normalized];
  if (ALIAS_MAP[normalized] && FINANCE_GLOSSARY[ALIAS_MAP[normalized]]) {
    return FINANCE_GLOSSARY[ALIAS_MAP[normalized]];
  }

  return null;
}
