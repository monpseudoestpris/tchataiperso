import type { StatementPeriod, StatementRow } from "@/lib/api";

export type StructuredStatementFormat = "mln" | "pct" | "per_share" | "shares";

export type StructuredStatementRow = {
  key: string;
  label: string;
  format: StructuredStatementFormat;
  values: (number | null)[];
  deltas: (number | null)[];
  isKey?: boolean;
  isSub?: boolean;
  groupStart?: boolean;
};

function computeDeltas(values: (number | null)[]): (number | null)[] {
  return values.map((v, i) => {
    if (i === 0) return null;
    const prev = values[i - 1];
    if (v == null || prev == null || prev === 0) return null;
    return ((v - prev) / Math.abs(prev)) * 100;
  });
}

function rowMap(rows: StatementRow[]): Map<string, (number | null)[]> {
  const m = new Map<string, (number | null)[]>();
  for (const r of rows) {
    m.set(r.key, r.values);
  }
  return m;
}

function getVec(
  map: Map<string, (number | null)[]>,
  len: number,
  keys: string[],
): (number | null)[] {
  for (const k of keys) {
    const v = map.get(k);
    if (v && v.some(x => x != null)) return v.slice(0, len);
  }
  return Array.from({ length: len }, () => null);
}

function mkRow(
  key: string,
  label: string,
  values: (number | null)[],
  opts?: {
    format?: StructuredStatementFormat;
    isKey?: boolean;
    isSub?: boolean;
    groupStart?: boolean;
  },
): StructuredStatementRow {
  return {
    key,
    label,
    format: opts?.format || "mln",
    values,
    deltas: computeDeltas(values),
    isKey: opts?.isKey,
    isSub: opts?.isSub,
    groupStart: opts?.groupStart,
  };
}

/**
 * Formate les entêtes de variation entre exercices (`22-23` en annuel, `07-10/25` en trimestriel).
 */
export function buildStatementDeltaHeaders(dates: string[], annual: boolean): string[] {
  const out: string[] = [];
  for (let i = 1; i < dates.length; i++) {
    const prev = dates[i - 1];
    const cur = dates[i];
    if (annual) {
      out.push(`${prev.slice(2, 4)}-${cur.slice(2, 4)}`);
    } else {
      const pm = prev.slice(5, 7);
      const cm = cur.slice(5, 7);
      const cy = cur.slice(2, 4);
      out.push(`${pm}-${cm}/${cy}`);
    }
  }
  return out;
}

/**
 * Construit les 3 tableaux simplifiés (Résultat, Bilan, Flux de trésorerie)
 * dans l'ordre, la hiérarchie et le format des fiches institutionnelles.
 */
export function buildStructuredStatements(
  period: StatementPeriod,
  start: number,
): {
  income: StructuredStatementRow[];
  balance: StructuredStatementRow[];
  cashflow: StructuredStatementRow[];
} {
  const dates = period.dates.slice(start);
  const n = dates.length;
  const incMap = rowMap(period.income || []);
  const balMap = rowMap(period.balance || []);
  const cfMap = rowMap(period.cashflow || []);

  const sliceVec = (vec: (number | null)[]) => vec.slice(start);

  // Vecteurs partagés (calculs par action / NOPAT / taux d'imposition)
  const rawSharesBal = sliceVec(getVec(balMap, period.dates.length, ["CommonStockSharesOutstanding"]));
  const rawSharesInc = sliceVec(getVec(incMap, period.dates.length, ["DilutedAverageShares"]));
  const shares = Array.from({ length: n }, (_, i) => rawSharesBal[i] ?? rawSharesInc[i] ?? null);

  // --- 1. Compte de résultat simplifié ---
  const rev = sliceVec(getVec(incMap, period.dates.length, ["TotalRevenue"]));
  const costRev = sliceVec(getVec(incMap, period.dates.length, ["CostOfRevenue"]));
  const sga = sliceVec(getVec(incMap, period.dates.length, ["SellingGeneralAndAdministration"]));
  const opExpRaw = sliceVec(
    getVec(incMap, period.dates.length, ["eod_income_operatingExpenses", "OperatingExpense"]),
  );
  const opExp = Array.from({ length: n }, (_, i) => {
    if (opExpRaw[i] != null) return opExpRaw[i];
    if (costRev[i] != null || sga[i] != null) return -((Math.abs(costRev[i] ?? 0)) + Math.abs(sga[i] ?? 0));
    return null;
  });
  const opInc = sliceVec(getVec(incMap, period.dates.length, ["OperatingIncome", "EBIT"]));
  const pretax = sliceVec(getVec(incMap, period.dates.length, ["PretaxIncome"]));
  const intExp = sliceVec(getVec(incMap, period.dates.length, ["InterestExpense"]));
  const otherIncRaw = sliceVec(
    getVec(incMap, period.dates.length, [
      "eod_income_totalOtherIncomeExpenseNet",
      "eod_income_nonOperatingIncomeNetOther",
    ]),
  );
  const otherInc = Array.from({ length: n }, (_, i) => {
    if (otherIncRaw[i] != null) return otherIncRaw[i];
    if (pretax[i] != null && opInc[i] != null) {
      return pretax[i]! - opInc[i]! + Math.abs(intExp[i] ?? 0);
    }
    return null;
  });
  const tax = sliceVec(getVec(incMap, period.dates.length, ["TaxProvision"]));
  const ni = sliceVec(getVec(incMap, period.dates.length, ["NetIncome"]));
  const ebitda = sliceVec(getVec(incMap, period.dates.length, ["EBITDA"]));
  const epsRaw = sliceVec(getVec(incMap, period.dates.length, ["DilutedEPS", "BasicEPS"]));

  const taxRate = Array.from({ length: n }, (_, i) => {
    if (tax[i] == null || pretax[i] == null || pretax[i]! <= 0) return null;
    const rate = (Math.abs(tax[i]!) / pretax[i]!) * 100;
    return Math.max(0, Math.min(100, rate));
  });
  const nopat = Array.from({ length: n }, (_, i) => {
    if (opInc[i] == null) return null;
    const t = taxRate[i] != null ? taxRate[i]! / 100 : 0.15;
    return opInc[i]! * (1 - Math.min(0.6, Math.max(0, t)));
  });
  const revPerShare = Array.from({ length: n }, (_, i) =>
    rev[i] != null && shares[i] && shares[i]! > 0 ? rev[i]! / shares[i]! : null,
  );
  const ebitdaPerShare = Array.from({ length: n }, (_, i) =>
    ebitda[i] != null && shares[i] && shares[i]! > 0 ? ebitda[i]! / shares[i]! : null,
  );
  const epsPerShare = Array.from({ length: n }, (_, i) => {
    if (epsRaw[i] != null) return epsRaw[i];
    return ni[i] != null && shares[i] && shares[i]! > 0 ? ni[i]! / shares[i]! : null;
  });

  const incomeRows: StructuredStatementRow[] = [
    mkRow("inc_rev", "Chiffre d'affaires", rev, { isKey: true }),
    mkRow("inc_opexp", "Charges d'exploitation", opExp, { isKey: true }),
    mkRow("inc_cogs", "dont Coût des ventes", costRev, { isSub: true }),
    mkRow("inc_sga", "dont Frais généraux", sga, { isSub: true }),
    mkRow("inc_opinc", "Résultat opérationnel", opInc, { isKey: true }),
    mkRow("inc_other", "Autres revenus/frais nets", otherInc),
    mkRow("inc_int", "Charge d'intérêt", intExp),
    mkRow("inc_ebt", "Résultat avant impôts", pretax, { isKey: true }),
    mkRow("inc_tax", "Impôts sur les bénéfices", tax),
    mkRow("inc_ni", "Résultat net", ni, { isKey: true }),
    mkRow("inc_ebitda", "EBITDA", ebitda, { groupStart: true }),
    mkRow("inc_nopat", "RN d'exploitation (NOPAT)", nopat),
    mkRow("inc_taxrate", "Taux d'imposition", taxRate, { format: "pct" }),
    mkRow("inc_revps", "Chiffre d'affaires par action", revPerShare, { format: "per_share", groupStart: true }),
    mkRow("inc_ebitdaps", "EBITDA par action", ebitdaPerShare, { format: "per_share" }),
    mkRow("inc_eps", "Bénéfices par action", epsPerShare, { format: "per_share" }),
  ];

  // --- 2. Bilan simplifié ---
  const curAssets = sliceVec(getVec(balMap, period.dates.length, ["CurrentAssets"]));
  const cash = sliceVec(getVec(balMap, period.dates.length, ["CashAndCashEquivalents"]));
  const stInv = sliceVec(getVec(balMap, period.dates.length, ["eod_balance_shortTermInvestments"]));
  const rec = sliceVec(getVec(balMap, period.dates.length, ["AccountsReceivable"]));
  const inv = sliceVec(getVec(balMap, period.dates.length, ["Inventory"]));
  const ltInv = sliceVec(getVec(balMap, period.dates.length, ["eod_balance_longTermInvestments"]));
  const ppe = sliceVec(getVec(balMap, period.dates.length, ["NetPPE"]));
  const goodwill = sliceVec(getVec(balMap, period.dates.length, ["eod_balance_goodWill"]));
  const intang = sliceVec(
    getVec(balMap, period.dates.length, ["eod_balance_intangibleAssets", "GoodwillAndIntangibleAssets"]),
  );
  const totAssets = sliceVec(getVec(balMap, period.dates.length, ["TotalAssets"]));

  const curLiab = sliceVec(getVec(balMap, period.dates.length, ["CurrentLiabilities"]));
  const ap = sliceVec(getVec(balMap, period.dates.length, ["AccountsPayable"]));
  const stDebt = sliceVec(
    getVec(balMap, period.dates.length, ["ShortTermDebt", "eod_balance_shortLongTermDebt"]),
  );
  const ltDebt = sliceVec(
    getVec(balMap, period.dates.length, ["LongTermDebt", "eod_balance_longTermDebtTotal"]),
  );
  const totLiab = sliceVec(
    getVec(balMap, period.dates.length, ["TotalLiabilitiesNetMinorityInterest"]),
  );

  const commonStock = sliceVec(getVec(balMap, period.dates.length, ["eod_balance_commonStock"]));
  const retEarn = sliceVec(getVec(balMap, period.dates.length, ["RetainedEarnings"]));
  const equity = sliceVec(getVec(balMap, period.dates.length, ["StockholdersEquity"]));

  const totDebtRaw = sliceVec(getVec(balMap, period.dates.length, ["TotalDebt"]));
  const totDebt = Array.from({ length: n }, (_, i) => {
    if (totDebtRaw[i] != null) return totDebtRaw[i];
    if (stDebt[i] != null || ltDebt[i] != null) return (stDebt[i] ?? 0) + (ltDebt[i] ?? 0);
    return null;
  });
  const netDebtRaw = sliceVec(getVec(balMap, period.dates.length, ["NetDebt"]));
  const netDebt = Array.from({ length: n }, (_, i) => {
    if (netDebtRaw[i] != null) return netDebtRaw[i];
    if (totDebt[i] != null && cash[i] != null) return totDebt[i]! - cash[i]!;
    return null;
  });
  const wcRaw = sliceVec(getVec(balMap, period.dates.length, ["WorkingCapital"]));
  const wc = Array.from({ length: n }, (_, i) => {
    if (wcRaw[i] != null) return wcRaw[i];
    if (curAssets[i] != null && curLiab[i] != null) return curAssets[i]! - curLiab[i]!;
    return null;
  });

  const balanceRows: StructuredStatementRow[] = [
    mkRow("bal_ca", "Actifs courants", curAssets, { isKey: true }),
    mkRow("bal_cash", "dont Trésorerie", cash, { isSub: true }),
    mkRow("bal_stinv", "dont Placements à CT", stInv, { isSub: true }),
    mkRow("bal_rec", "dont Créances clients", rec, { isSub: true }),
    mkRow("bal_inv", "dont Stock", inv, { isSub: true }),
    mkRow("bal_ltinv", "Placements à long terme", ltInv),
    mkRow("bal_ppe", "Biens corporels", ppe),
    mkRow("bal_gw", "Écart d'acquisitions", goodwill),
    mkRow("bal_intang", "Biens incorporels", intang),
    mkRow("bal_ta", "Actifs totaux", totAssets, { isKey: true }),
    mkRow("bal_cl", "Passifs courants", curLiab, { isKey: true, groupStart: true }),
    mkRow("bal_ap", "dont Créances fournisseurs", ap, { isSub: true }),
    mkRow("bal_std", "dont Dette à court terme", stDebt, { isSub: true }),
    mkRow("bal_ltd", "Dette à long terme", ltDebt),
    mkRow("bal_tl", "Passifs totaux", totLiab, { isKey: true }),
    mkRow("bal_cs", "Action ordinaire", commonStock, { groupStart: true }),
    mkRow("bal_re", "Bénéfices non répartis", retEarn),
    mkRow("bal_eq", "Capitaux propres", equity, { isKey: true }),
    mkRow("bal_td", "Dette portant intérêts", totDebt, { groupStart: true }),
    mkRow("bal_nd", "Dette nette", netDebt),
    mkRow("bal_wc", "Fonds de roulement", wc),
    mkRow("bal_sh", "Actions en circulation (en Mlns)", shares, { format: "shares" }),
  ];

  // --- 3. Flux de trésorerie simplifié ---
  const cfNi = sliceVec(getVec(cfMap, period.dates.length, ["NetIncome"]));
  const effNi = Array.from({ length: n }, (_, i) => cfNi[i] ?? ni[i] ?? null);
  const da = sliceVec(getVec(cfMap, period.dates.length, ["DepreciationAndAmortization"]));
  const adjNi = sliceVec(
    getVec(cfMap, period.dates.length, ["eod_cashflow_changeToNetincome", "eod_cashflow_otherNonCashItems"]),
  );
  const adjRec = sliceVec(getVec(cfMap, period.dates.length, ["eod_cashflow_changeToAccountReceivables"]));
  const adjInv = sliceVec(getVec(cfMap, period.dates.length, ["eod_cashflow_changeToInventory"]));
  const adjOther = sliceVec(
    getVec(cfMap, period.dates.length, ["eod_cashflow_changeToOperatingActivities", "ChangeInWorkingCapital"]),
  );
  const ocf = sliceVec(getVec(cfMap, period.dates.length, ["OperatingCashFlow"]));
  const capex = sliceVec(getVec(cfMap, period.dates.length, ["CapitalExpenditure"]));
  const investments = sliceVec(getVec(cfMap, period.dates.length, ["eod_cashflow_investments"]));
  const icf = sliceVec(getVec(cfMap, period.dates.length, ["InvestingCashFlow"]));
  const divPaid = sliceVec(getVec(cfMap, period.dates.length, ["CashDividendsPaid"]));
  const debtIss = sliceVec(getVec(cfMap, period.dates.length, ["IssuanceOfDebt"]));
  const fcfFin = sliceVec(getVec(cfMap, period.dates.length, ["FinancingCashFlow"]));
  const chgCash = sliceVec(getVec(cfMap, period.dates.length, ["eod_cashflow_changeInCash"]));
  const fcfRaw = sliceVec(getVec(cfMap, period.dates.length, ["FreeCashFlow"]));
  const fcfPerShare = Array.from({ length: n }, (_, i) => {
    const val = fcfRaw[i] ?? (ocf[i] != null && capex[i] != null ? ocf[i]! - Math.abs(capex[i]!) : null);
    return val != null && shares[i] && shares[i]! > 0 ? val / shares[i]! : null;
  });

  const cashflowRows: StructuredStatementRow[] = [
    mkRow("cf_ni", "Bénéfices nets", effNi, { isKey: true }),
    mkRow("cf_da", "Dépréciation", da),
    mkRow("cf_adjni", "Ajustements des bénéfices nets", adjNi),
    mkRow("cf_adjrec", "Ajust. comptes débiteurs", adjRec),
    mkRow("cf_adjinv", "Ajust. des stocks", adjInv),
    mkRow("cf_otherop", "Autres flux opérationnels", adjOther),
    mkRow("cf_ocf", "Flux opérationnel", ocf, { isKey: true }),
    mkRow("cf_capex", "Dépenses d'investissement", capex, { groupStart: true }),
    mkRow("cf_inv", "Investissements", investments),
    mkRow("cf_icf", "Flux d'investissement", icf, { isKey: true }),
    mkRow("cf_div", "Dividendes payés", divPaid, { groupStart: true }),
    mkRow("cf_debt", "Emprunts nets", debtIss),
    mkRow("cf_fcf_fin", "Flux de financement", fcfFin, { isKey: true }),
    mkRow("cf_chgcash", "Variation nette de la trésorerie", chgCash, { groupStart: true }),
    mkRow("cf_fcfps", "Free Cash Flow par action", fcfPerShare, { format: "per_share" }),
  ];

  return { income: incomeRows, balance: balanceRows, cashflow: cashflowRows };
}
