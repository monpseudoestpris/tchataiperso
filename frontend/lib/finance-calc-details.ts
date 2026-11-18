import type {
  DossierMetricRow,
  FinancialDossier,
  IntrinsicMethodResult,
  IntrinsicValuationPayload,
  StatementPeriod,
  UncleStockScoreItem,
} from "@/lib/api";
import type { FinanceCalcDetail, MetricCalcStep } from "@/components/finance-info-tip";

function fmtM(v: number | null | undefined, suffix = " M"): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${Math.round(v / 1e6).toLocaleString("fr-FR")}${suffix}`;
}

function fmtN(v: number | null | undefined, digits = 2, suffix = ""): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`;
}

function fmtInt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return Math.round(v).toLocaleString("fr-FR");
}

function fmtAny(v: number | string | boolean | null | undefined): string {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "Oui" : "Non";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} Md`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M`;
    return v.toLocaleString("fr-FR", { maximumFractionDigits: 3 });
  }
  return String(v);
}

function lastNonNull(vals: (number | null | undefined)[] | undefined): number | null {
  if (!vals || vals.length === 0) return null;
  for (let i = vals.length - 1; i >= 0; i--) {
    const v = vals[i];
    if (v != null && Number.isFinite(v)) return v;
  }
  return null;
}

function lastStmtPair(
  period: StatementPeriod | undefined,
  ...keys: string[]
): { latest: number | null; prev: number | null; year: string; prevYear: string } {
  if (!period) return { latest: null, prev: null, year: "", prevYear: "" };
  const allRows = [...(period.income || []), ...(period.balance || []), ...(period.cashflow || []), ...(period.ratios || [])];
  for (const key of keys) {
    const row = allRows.find(r => r.key === key);
    if (row && row.values && row.values.length > 0 && row.values.some(v => v != null)) {
      const n = row.values.length;
      return {
        latest: row.values[n - 1] ?? null,
        prev: n >= 2 ? row.values[n - 2] ?? null : null,
        year: period.dates?.[n - 1]?.slice(0, 4) || "",
        prevYear: n >= 2 ? period.dates?.[n - 2]?.slice(0, 4) || "" : "",
      };
    }
  }
  return { latest: null, prev: null, year: "", prevYear: "" };
}

function findAnnualRow(dossier: FinancialDossier, key: string): DossierMetricRow | undefined {
  const t = dossier.annual_tables;
  return [...t.summary, ...t.profitability, ...t.solvency, ...t.distribution, ...t.efficiency].find(
    r => r.key === key,
  );
}

function latestAnnualRowVal(dossier: FinancialDossier, key: string): { latest: number | null; prev: number | null } {
  const row = findAnnualRow(dossier, key);
  if (!row || !row.values || row.values.length === 0) return { latest: null, prev: null };
  const n = row.values.length;
  return {
    latest: row.values[n - 1] ?? null,
    prev: n >= 2 ? row.values[n - 2] ?? null : null,
  };
}

function extractFundamentalSnapshot(dossier: FinancialDossier) {
  const ann = dossier.statements?.annual;
  const cur = dossier.currency || "USD";
  const years = dossier.annual_tables?.years || [];
  const lastYr = years[years.length - 1] || ann?.dates?.[ann.dates.length - 1]?.slice(0, 4) || "";
  const prevYr = years.length >= 2 ? years[years.length - 2] : ann?.dates && ann.dates.length >= 2 ? ann.dates[ann.dates.length - 2].slice(0, 4) : "";

  const stmt = (...k: string[]) => lastStmtPair(ann, ...k);
  const tbl = (k: string) => latestAnnualRowVal(dossier, k);

  const rev = stmt("TotalRevenue");
  const costRev = stmt("CostOfRevenue");
  const gp = stmt("GrossProfit");
  const rd = stmt("ResearchAndDevelopment");
  const sga = stmt("SellingGeneralAndAdministration");
  const opinc = stmt("OperatingIncome");
  const ebitda = stmt("EBITDA");
  const ebit = stmt("EBIT", "OperatingIncome");
  const intExp = stmt("InterestExpense");
  const pretax = stmt("PretaxIncome");
  const tax = stmt("TaxProvision");
  const ni = stmt("NetIncome");
  const eps = stmt("DilutedEPS", "BasicEPS");

  const assets = stmt("TotalAssets");
  const ca = stmt("CurrentAssets");
  const cashPure = stmt("CashAndCashEquivalents");
  const cash = stmt("CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents");
  const rec = stmt("AccountsReceivable");
  const inv = stmt("Inventory");
  const liab = stmt("TotalLiabilitiesNetMinorityInterest");
  const cl = stmt("CurrentLiabilities");
  const ap = stmt("AccountsPayable");
  const totDebt = stmt("TotalDebt");
  const ltDebt = stmt("LongTermDebt");
  const netDebt = stmt("NetDebt");
  const eq = stmt("StockholdersEquity");
  const retEarn = stmt("RetainedEarnings");
  const wc = stmt("WorkingCapital");
  const shares = stmt("CommonStockSharesOutstanding", "DilutedAverageShares");

  const ocf = stmt("OperatingCashFlow");
  const capex = stmt("CapitalExpenditure");
  const fcf = stmt("FreeCashFlow");
  const da = stmt("DepreciationAndAmortization");
  const divPaid = stmt("CashDividendsPaid");
  const buyback = stmt("RepurchaseOfCapitalStock");

  const hdr = dossier.header;
  const cap = dossier.capital_valuation;

  const avg = (p: { latest: number | null; prev: number | null }) =>
    p.latest != null && p.prev != null ? (p.latest + p.prev) / 2 : p.latest;

  const yrTag = lastYr ? ` (${lastYr})` : "";
  const stepM = (label: string, v: number | null | undefined, note?: string): MetricCalcStep | null =>
    v == null || !Number.isFinite(v)
      ? null
      : { label: `${label}${yrTag}`, value: fmtM(v, ` M ${cur}`), note };

  const stepPairM = (label: string, p: { latest: number | null; prev: number | null }): MetricCalcStep | null => {
    if (p.latest == null) return null;
    const avgV = avg(p);
    const note =
      p.prev != null && prevYr
        ? `${prevYr} : ${fmtM(p.prev, ` M ${cur}`)} · Moyenne : ${fmtM(avgV, ` M ${cur}`)}`
        : undefined;
    return { label: `${label}${yrTag}`, value: fmtM(p.latest, ` M ${cur}`), note };
  };

  const roaEndLatest = ni.latest != null && assets.latest != null && assets.latest > 0 ? (ni.latest / assets.latest) * 100 : null;
  const roaEndPrev = ni.prev != null && assets.prev != null && assets.prev > 0 ? (ni.prev / assets.prev) * 100 : null;
  const roaEndDeltaPts = roaEndLatest != null && roaEndPrev != null ? roaEndLatest - roaEndPrev : null;
  const roaEndYoyPct =
    roaEndLatest != null && roaEndPrev != null && roaEndPrev !== 0
      ? ((roaEndLatest - roaEndPrev) / Math.abs(roaEndPrev)) * 100
      : null;
  const cashRoaLatest = ocf.latest != null && assets.latest != null && assets.latest > 0 ? (ocf.latest / assets.latest) * 100 : null;

  return {
    cur,
    lastYr,
    prevYr,
    hdr,
    cap,
    rev,
    costRev,
    gp,
    rd,
    sga,
    opinc,
    ebitda,
    ebit,
    intExp,
    pretax,
    tax,
    ni,
    eps,
    assets,
    ca,
    cashPure,
    cash,
    rec,
    inv,
    liab,
    cl,
    ap,
    totDebt,
    ltDebt,
    netDebt,
    eq,
    retEarn,
    wc,
    shares,
    ocf,
    capex,
    fcf,
    da,
    divPaid,
    buyback,
    roaEnd: { latest: roaEndLatest, prev: roaEndPrev, deltaPts: roaEndDeltaPts, yoyPct: roaEndYoyPct },
    cashRoaLatest,
    tbl,
    avg,
    stepM,
    stepPairM,
  };
}

type FundamentalSnapshot = ReturnType<typeof extractFundamentalSnapshot>;

function buildRoaMetricSteps(f: FundamentalSnapshot): (MetricCalcStep | null)[] {
  const yr = f.lastYr || "N";
  const prev = f.prevYr || "N-1";
  const roaTbl = f.tbl("roa");
  const tblDelta = roaTbl.latest != null && roaTbl.prev != null ? roaTbl.latest - roaTbl.prev : null;
  const steps: (MetricCalcStep | null)[] = [];

  if (f.roaEnd.latest != null) {
    const parts: string[] = [];
    if (f.roaEnd.prev != null) parts.push(`${prev} : ${fmtN(f.roaEnd.prev, 2, "%")}`);
    if (f.roaEnd.deltaPts != null) {
      parts.push(`ΔROA : ${f.roaEnd.deltaPts >= 0 ? "+" : ""}${fmtN(f.roaEnd.deltaPts, 2, " pt")}`);
    }
    if (f.roaEnd.yoyPct != null) {
      parts.push(`Croiss. 1A : ${f.roaEnd.yoyPct >= 0 ? "+" : ""}${fmtN(f.roaEnd.yoyPct, 1, "%")}`);
    }
    steps.push({
      label: `ROA fin d'exercice (RN / Actifs, ${yr})`,
      value: fmtN(f.roaEnd.latest, 2, "%"),
      note: parts.length > 0 ? parts.join(" · ") : undefined,
    });
  }

  if (roaTbl.latest != null) {
    const parts: string[] = [];
    if (roaTbl.prev != null) parts.push(`${prev} : ${fmtN(roaTbl.prev, 1, "%")}`);
    if (tblDelta != null) parts.push(`ΔROA : ${tblDelta >= 0 ? "+" : ""}${fmtN(tblDelta, 1, " pt")}`);
    steps.push({
      label: `ROA actifs moyens (tableau annuel, ${yr})`,
      value: fmtN(roaTbl.latest, 1, "%"),
      note: parts.length > 0 ? parts.join(" · ") : undefined,
    });
  }

  if (f.cashRoaLatest != null) {
    steps.push({
      label: `Cash ROA (CFO / Actifs, ${yr})`,
      value: fmtN(f.cashRoaLatest, 2, "%"),
    });
  }
  return steps;
}

function buildPiotroskiBinarySteps(dossier: FinancialDossier, f: FundamentalSnapshot | null): MetricCalcStep[] {
  const p = dossier.annual_tables?.piotroski;
  if (!p || !p.criteria || p.criteria.length === 0) return [];
  const yr = p.years[p.years.length - 1] || f?.lastYr || "N";
  const prev = p.years.length >= 2 ? p.years[p.years.length - 2] : f?.prevYr || "N-1";
  const roaTbl = f?.tbl("roa");
  const opm = f?.tbl("op_m");
  const turn = f?.tbl("asset_turn");
  const debtA = f?.tbl("debt_assets");
  const currR = f?.tbl("curr_r");
  const shTbl = f?.tbl("shares");

  const noteFor = (key: string): string | undefined => {
    if (!f) return undefined;
    switch (key) {
      case "roa_pos": {
        const parts: string[] = [];
        if (roaTbl?.latest != null) parts.push(`ROA moy. (${yr}) = ${fmtN(roaTbl.latest, 1, "%")}`);
        if (f.roaEnd.latest != null) parts.push(`RN/Actifs (${yr}) = ${fmtN(f.roaEnd.latest, 2, "%")}`);
        return parts.length > 0 ? parts.join(" · ") : undefined;
      }
      case "roa_up": {
        const parts: string[] = [];
        if (roaTbl?.latest != null && roaTbl?.prev != null) {
          const d = roaTbl.latest - roaTbl.prev;
          parts.push(`ROA moy. : ${fmtN(roaTbl.latest, 1, "%")} vs ${fmtN(roaTbl.prev, 1, "%")} (Δ ${d >= 0 ? "+" : ""}${fmtN(d, 1, " pt")})`);
        }
        if (f.roaEnd.latest != null && f.roaEnd.prev != null && f.roaEnd.deltaPts != null) {
          parts.push(
            `RN/Actifs : ${fmtN(f.roaEnd.latest, 2, "%")} vs ${fmtN(f.roaEnd.prev, 2, "%")} (Δ ${f.roaEnd.deltaPts >= 0 ? "+" : ""}${fmtN(f.roaEnd.deltaPts, 2, " pt")}${f.roaEnd.yoyPct != null ? ` / ${f.roaEnd.yoyPct >= 0 ? "+" : ""}${fmtN(f.roaEnd.yoyPct, 1, "%")}` : ""})`,
          );
        }
        return parts.length > 0 ? parts.join(" · ") : undefined;
      }
      case "cfo_pos":
        return f.ocf.latest != null ? `CFO (${yr}) = ${fmtM(f.ocf.latest, ` M ${f.cur}`)}` : undefined;
      case "cfo_gt_ni":
        return f.ocf.latest != null && f.ni.latest != null
          ? `CFO = ${fmtM(f.ocf.latest, ` M ${f.cur}`)} vs RN = ${fmtM(f.ni.latest, ` M ${f.cur}`)}`
          : undefined;
      case "opm_up":
        return opm?.latest != null && opm?.prev != null
          ? `Marge opé. (${yr} vs ${prev}) : ${fmtN(opm.latest, 1, "%")} vs ${fmtN(opm.prev, 1, "%")}`
          : undefined;
      case "turn_up":
        return turn?.latest != null && turn?.prev != null
          ? `Rotation actifs (${yr} vs ${prev}) : ${fmtN(turn.latest, 2, "×")} vs ${fmtN(turn.prev, 2, "×")}`
          : undefined;
      case "debt_down":
        return debtA?.latest != null && debtA?.prev != null
          ? `Dette/Actifs (${yr} vs ${prev}) : ${fmtN(debtA.latest, 1, "%")} vs ${fmtN(debtA.prev, 1, "%")}`
          : undefined;
      case "liq_up":
        return currR?.latest != null && currR?.prev != null
          ? `Liquidité gén. (${yr} vs ${prev}) : ${fmtN(currR.latest, 2, "×")} vs ${fmtN(currR.prev, 2, "×")}`
          : undefined;
      case "shares_down":
        return shTbl?.latest != null && shTbl?.prev != null
          ? `Actions (${yr} vs ${prev}) : ${(shTbl.latest / 1e6).toFixed(1)} M vs ${(shTbl.prev / 1e6).toFixed(1)} M`
          : undefined;
      default:
        return undefined;
    }
  };

  return p.criteria.map((c, idx) => ({
    label: `[${idx + 1}/9] ${c.label}`,
    value: c.values[c.values.length - 1] === 1 ? "1 pt ✓" : "0 pt",
    note: noteFor(c.key),
  }));
}

function buildPiotroskiFundamentals(f: FundamentalSnapshot): MetricCalcStep[] {
  const yr = f.lastYr || "N";
  const prevLbl = f.prevYr || "N-1";
  return compactFundamentals([
    ...buildRoaMetricSteps(f),
    f.stepPairM("Résultat net (RN)", f.ni),
    f.stepPairM("Actifs totaux", f.assets),
    f.stepPairM("Flux d'exploitation (CFO)", f.ocf),
    f.tbl("op_m").latest != null
      ? {
          label: `Marge opé. (${yr} vs ${prevLbl})`,
          value: `${fmtN(f.tbl("op_m").latest, 1, "%")} vs ${fmtN(f.tbl("op_m").prev, 1, "%")}`,
        }
      : null,
    f.tbl("asset_turn").latest != null
      ? {
          label: `Rotation actifs (${yr} vs ${prevLbl})`,
          value: `${fmtN(f.tbl("asset_turn").latest, 2, "×")} vs ${fmtN(f.tbl("asset_turn").prev, 2, "×")}`,
        }
      : null,
    f.tbl("debt_assets").latest != null
      ? {
          label: `Dette/Actifs (${yr} vs ${prevLbl})`,
          value: `${fmtN(f.tbl("debt_assets").latest, 1, "%")} vs ${fmtN(f.tbl("debt_assets").prev, 1, "%")}`,
        }
      : null,
    f.stepPairM("Dette long terme", f.ltDebt),
    f.tbl("curr_r").latest != null
      ? {
          label: `Liquidité gén. (${yr} vs ${prevLbl})`,
          value: `${fmtN(f.tbl("curr_r").latest, 2, "×")} vs ${fmtN(f.tbl("curr_r").prev, 2, "×")}`,
        }
      : null,
    f.tbl("shares").latest != null
      ? {
          label: `Actions (${yr} vs ${prevLbl})`,
          value: `${(f.tbl("shares").latest! / 1e6).toFixed(1)}M vs ${f.tbl("shares").prev != null ? `${(f.tbl("shares").prev! / 1e6).toFixed(1)}M` : "—"}`,
        }
      : null,
  ]);
}

function compactFundamentals(list: (MetricCalcStep | null | undefined)[]): MetricCalcStep[] {
  const seen = new Set<string>();
  const out: MetricCalcStep[] = [];
  for (const item of list) {
    if (!item || item.value === "—" || seen.has(item.label)) continue;
    seen.add(item.label);
    out.push(item);
  }
  return out;
}

function selectUncleStockFundamentals(scoreId: string, dossier: FinancialDossier): MetricCalcStep[] {
  const f = extractFundamentalSnapshot(dossier);
  const baseMarket: (MetricCalcStep | null)[] = [
    f.cap.price != null ? { label: "Cours actuel", value: fmtN(f.cap.price, 2, ` ${f.cur}`) } : null,
    f.stepM("Capitalisation boursière", f.hdr.market_cap),
    f.shares.latest != null
      ? { label: `Actions (${f.lastYr || "bilan"})`, value: `${(f.shares.latest / 1e6).toFixed(1)} M` }
      : null,
  ];

  const low = scoreId.toLowerCase();
  if (low.includes("piotroski")) {
    return buildPiotroskiFundamentals(f);
  }
  if (low.includes("quality") || low.includes("predict") || low.includes("growth") || low.includes("company")) {
    return compactFundamentals([
      ...buildRoaMetricSteps(f),
      f.tbl("roic").latest != null ? { label: `ROIC (${f.lastYr || "N"})`, value: fmtN(f.tbl("roic").latest, 1, "%") } : null,
      f.tbl("croic").latest != null ? { label: `CROIC (${f.lastYr || "N"})`, value: fmtN(f.tbl("croic").latest, 1, "%") } : null,
      f.tbl("roe").latest != null ? { label: `ROE (${f.lastYr || "N"})`, value: fmtN(f.tbl("roe").latest, 1, "%") } : null,
      f.stepM("Chiffre d'affaires", f.rev.latest, f.rev.prev != null ? `${f.prevYr} : ${fmtM(f.rev.prev, ` M ${f.cur}`)}` : undefined),
      f.stepM("Bénéfice brut", f.gp.latest),
      f.stepM("Résultat opé. (EBIT)", f.opinc.latest),
      f.stepM("Résultat net", f.ni.latest),
      f.stepM("Flux d'exploitation", f.ocf.latest),
      f.stepM("Investissements (CapEx)", f.capex.latest),
      f.stepM("Free Cash Flow", f.fcf.latest),
      f.stepPairM("Capitaux propres", f.eq),
      f.stepM("Dette nette", f.netDebt.latest),
    ]);
  }
  if (low.includes("yield")) {
    return compactFundamentals([
      ...baseMarket,
      f.hdr.dividend_yield_pct != null ? { label: "Rendement dividende", value: fmtN(f.hdr.dividend_yield_pct, 2, "%") } : null,
      f.stepM("Dividendes versés", f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : null),
      f.stepM("Rachats d'actions", f.buyback.latest != null ? Math.abs(f.buyback.latest) : null),
      f.stepM("Free Cash Flow", f.fcf.latest),
      f.stepM("Résultat net", f.ni.latest),
    ]);
  }
  if (
    low.includes("value") ||
    low.includes("greenblatt") ||
    low.includes("oshaughnessy") ||
    low.includes("erp5") ||
    low.includes("slater")
  ) {
    return compactFundamentals([
      ...baseMarket,
      f.stepM("EBITDA", f.ebitda.latest),
      f.stepM("EBIT / Résultat opé.", f.ebit.latest),
      f.stepM("Résultat net", f.ni.latest),
      f.stepM("Free Cash Flow", f.fcf.latest),
      f.stepM("Capitaux propres", f.eq.latest),
      f.stepM("Dette nette", f.netDebt.latest),
      f.cap.pe_ttm != null ? { label: "PER TTM", value: fmtN(f.cap.pe_ttm, 1, "×") } : null,
      f.cap.ev_ebitda != null ? { label: "VE / EBITDA TTM", value: fmtN(f.cap.ev_ebitda, 1, "×") } : null,
    ]);
  }
  if (
    low.includes("balance") ||
    low.includes("health") ||
    low.includes("trap") ||
    low.includes("altman") ||
    low.includes("ohlson") ||
    low.includes("beneish") ||
    low.includes("dechow") ||
    low.includes("mohanram") ||
    low.includes("montier")
  ) {
    const wcVal =
      f.wc.latest ?? (f.ca.latest != null && f.cl.latest != null ? f.ca.latest - f.cl.latest : null);
    return compactFundamentals([
      ...buildRoaMetricSteps(f),
      f.stepPairM("Actifs totaux", f.assets),
      f.stepM("Actifs courants", f.ca.latest),
      f.stepM("Trésorerie & placements CT", f.cash.latest),
      f.stepM("Créances clients", f.rec.latest),
      f.stepM("Stocks", f.inv.latest),
      f.stepM("Passifs courants", f.cl.latest),
      f.stepM("Passifs totaux", f.liab.latest),
      f.stepM("Fonds de roulement (BFR)", wcVal),
      f.stepM("Résultats non distribués", f.retEarn.latest),
      f.stepPairM("Dette totale", f.totDebt),
      f.stepPairM("Dette long terme", f.ltDebt),
      f.stepM("Capitaux propres", f.eq.latest),
      f.stepM("Chiffre d'affaires", f.rev.latest),
      f.stepPairM("Résultat net", f.ni),
      f.stepM("Flux d'exploitation", f.ocf.latest),
    ]);
  }
  return compactFundamentals([
    ...baseMarket,
    f.stepM("Chiffre d'affaires", f.rev.latest),
    f.stepM("EBITDA", f.ebitda.latest),
    f.stepM("Résultat net", f.ni.latest),
    f.stepM("Free Cash Flow", f.fcf.latest),
    f.stepM("Capitaux propres", f.eq.latest),
    f.stepM("Dette nette", f.netDebt.latest),
    f.hdr.beta != null ? { label: "Bêta", value: fmtN(f.hdr.beta, 2) } : null,
  ]);
}

const FULL_SCORE_FORMULAS: Record<string, { verified: string; documented?: string }> = {
  uncle_stock_score: {
    verified:
      "Score = (clamp(330·Q + 210·V − 160·ln±(Cours/VI) + 330·(1−H)·(1,5·V² − 1) − 10·Rec + 50·ln±(rCAGR_prix) + 30·ln±(Croiss_att) + 75·ln±(Rdt_1A) + 25·ln±(ΔMMA50) + 40·ln±(LT_Rev) + 100·%Initiés − Pénalités[Ohlson,Beneish,Dechow,Montier,Perte] ; −890 ; 650) + 890) / 1540 × 100",
    documented:
      "Score = (clamp(∑ termes pondérés GARP ; −890 ; 650) + 890) / 1420 × 100 (amplitude 1540 dans le guide)",
  },
  quality_score: {
    verified:
      "S = clamp(∑ w_i × ln±(x_i ; cible_i) sur 19 critères [ROIC, CROIC, ROE, Marges, Croissance CA/FCF/BPA/CBV, Stabilité] ; −47 ; 45) ; Norm = (S + 47) / 92 ; Final = σ_4(Norm) = 1 / (1 + exp(−4·(Norm − 0,5))) × 100",
  },
  value_score: {
    verified: "Score = clamp(1,9 × ln±(YieldScore) + 0,3 × ln±(BalanceValueScore) ; 0 ; 2,2) / 2,2 × 100",
  },
  yield_score: {
    verified:
      "S = clamp(∑ w_i × ln±(rendement_i ; cible_i) [Earnings Yield, FCF Yield, EBITDA/EV, Sales/EV, Operating/EV, Div. Yield, Shareholder Yield] ; −1160 ; 1010) ; Norm = (S + 1160) / 2170 ; Final = σ_4(Norm) × 100",
    documented:
      "Norm = (clamp(S ; −1160 ; 1010) + 1160) / 1810 × 100 (sans sigmoïde finale)",
  },
  balance_value_score: {
    verified:
      "S = clamp(150·ln±(B/M) − 40·ln±(P/TBV) − 10·ln±(P/NonCash) − 25·ln±(P/NNWC) − 15·ln±(P/NCAV) − 5·ln±(P/Fixed) ; −450 ; 620) ; Norm = (S + 450) / 1070 ; Final = σ_4(Norm) × 100",
    documented:
      "Norm = (clamp(S ; −450 ; 620) + 450) / 1080 × 100",
  },
  balance_score: {
    verified:
      "S = 2,1 × ln±(FinancialHealthScore) + 0,9 × ln±(BalanceValueScore) ; Score = clamp(S ; 0 ; 3,0) / 3,0 × 100",
  },
  financial_health_score: {
    verified:
      "S = clamp(700·(σ(7·(Quick−1))−0,5) − 40·(σ(1,5·(Quick−2))−0,5) + 250·(σ(7·(Curr−1))−0,5) + 140·(σ(5·(BFR/Act))−0,5) − 40·(σ(1,5·(Curr−2))−0,5) + 200·ln±(CFO/Passifs) + 100·ln±(FCFF/DetteLT) − 60·ln±(Passifs/Actifs) − 40·ln±(Passifs/FP) − 40·ln±(DN/FP) − 30·ln±(DN/EBITDA) − 20·ln±(Passifs/TBV) − 200·ln±(|Sloan|) − 1200·ln±(Ohlson) ; −2200 ; 840) ; Norm = (S + 2200) / 3040 ; Final = σ_4(Norm) × 100",
    documented:
      "Norm = (clamp(S ; −2200 ; 840) + 2150) / 2990 × 100",
  },
  growth_rate: {
    verified: "g = Médiane des 16 taux de croissance disponibles (CA rCAGR 15A/67%/CAGR 5A-3A, EBITDA, OI, CFO, FCFF, RN 5A, Fwd CA/BPA, BPA 1A, TBV rCAGR, NOR 5A)",
  },
  predictability_score: {
    verified: "S = 22×R²(OperatingIncome) + 12×R²(Revenue) + 4×R²(GrossMargin) ; Score = (clamp(S ; −13 ; 48) + 13) / 61 × 100",
  },
  piotroski_f_score: {
    verified:
      "F = F_entier + F_fraction ; F_entier = I(ROA>0) + I(ΔROA>0) + I(CFO>0) + I(CFO>RN) + I(ΔMargeOp>0) + I(ΔRotationActifs>0) + I(ΔDette≤0) + I(ΔLiquiditéGén>0) + I(ΔActions≤0) ∈ [0 ; 9] ; F_fraction = σ_0,35(∑ w_i·ln±(x_i)) ∈ [0 ; 1]",
  },
  mohanram_g_score: {
    verified:
      "G = I(ROA>8%) + I(CFO/Act>10%) + I(Accruals/Act<0) + I(σ_ROA<5%) + I(σ_CA<15%) + I(R&D/Act>2%) + I(CapEx/Act>3%) ∈ [0 ; 7]",
  },
  montier_c_score: {
    verified:
      "C = I(CFO/RN↘) + I(DSO↗) + I(DIO↗) + I(AutresActCour/CA↗) + I(TauxAmort↘) + I(CroissActifs>10%) ∈ [0 ; 6]",
  },
  levermann_score: {
    verified:
      "Somme algébrique (+1 / 0 / −1) sur critères [ROE, Marge EBIT, Capitaux propres/Actifs, PER actuel, Croissance BPA fwd, Perf 6M, Perf 12M]",
  },
  company_score: {
    verified:
      "F_int ∈ [0 ; 5] (MargeNette>10%, CA rCAGR67>10%, ROE>15%, EquityRatio>40%, CFO/Passifs>33%) + σ_0,5(1·ln±(NM) + 1·ln±(gCA) + 1,5·ln±(ROE) + 0,75·ln±(EqR) + 0,75·ln±(CFCov))",
  },
  oshaughnessy_vc3: {
    verified:
      "S = 1·ln±(B/M) + 7·ln±(BPA/Cours) + 1·ln±(CA/Capi) + 3,5·ln±(EBITDA/VE) + 3,5·ln±(CFO/Capi) + 20·ln±(BuybackRatio) ; Score = σ_0,35(S) × 100",
  },
  greenblatt_score: {
    verified:
      "S = Moyenne( ln±(7 × EBIT/VE ; ±5) , ln±(EBIT / CE_Greenblatt.moy ; −1..2) ) ; Score = σ_1,2(S) × 100",
  },
  pim_van_vliet_score: {
    verified:
      "S = 1·ln±(Perf_1A ; −0,9..3) + 3·ln±(NetPayoutYield ; −0,5..1) − 0,25·ln±(Volatilité_252j ; 0..2) ; Score = σ_1,1(S) × 100",
  },
  erp5_score: {
    verified:
      "S = Moyenne( ln±(7·EBIT/VE) , ln±(ROCE_Greenblatt) , ln±(ROCE_5A) , ln±(0,07·B/M) ) ; Score = σ_1,3(S) × 100",
  },
  slater_score: {
    verified:
      "S = ∑ w_i·ln±(x_i) [0,75·BPA/Cours, 0,75·BPA_rCAGR67, 2·ROCE, −40·PEG, 10·DivYield, 0,75·MargeBrute, −1·Passifs/FP, 20·CurrentRatio, 0,5·Perf1A, −7·(3·Capi/10⁹)] ; Score = σ_0,05(S) × 100",
    documented: "Expression littérale source « 3 ÷ 109 × MarketCap » sans facteur 10⁹",
  },
  altman_z_score: {
    verified: "Z = 1,2×(BFR/Actifs) + 1,4×(RésNonDist/Actifs) + 3,3×(EBIT/Actifs) + 0,6×(Capi/Passifs) + 0,999×(CA/Actifs moy.)",
  },
  ohlson_o_score: {
    verified:
      "O = −1,32 − 0,407·ln(Actifs_M/500) + 6,03·(Passifs/Actifs) − 1,43·(BFR/Actifs) + 0,0757/(ActCour/PassCour) − 1,72·I(Pass>Act) − 2,37·ROA − 1,83·(CFO/Passifs) + 0,285·I(2_ans_pertes) − 0,521·(RN_t−RN_{t−1})/(|RN_t|+|RN_{t−1}|) ; P_défaut = 1 / (1 + e^{−O})",
  },
  beneish_m_score: {
    verified:
      "M = −4,84 + 0,920·DSRI + 0,528·GMI + 0,404·AQI + 0,892·SGI + 0,115·DEPI − 0,172·SGAI + 4,679·TATA − 0,327·LVGI (Seuil manipulation : > −2,22)",
  },
  dechow_f_score: {
    verified:
      "PV = −7,893 + 0,790·RSST_acc + 2,518·ΔRec + 1,191·ΔInv + 1,979·SoftAssets + 0,171·ΔCashSales + 0,932·ΔROA + 1,029·Issue ; F = σ(PV) / 0,0037",
    documented: "Utilise σ(−PV) / 0,0037 selon l'expression brute publiée",
  },
  esg_score: {
    verified: "ESG = Score TotalEsg issu du fournisseur fondamental (non estimé si absent) / 100",
  },
  environment_score: {
    verified: "Score pilier Environnement issu du fournisseur fondamental / 100",
  },
  social_score: {
    verified: "Score pilier Social issu du fournisseur fondamental / 100",
  },
  governance_score: {
    verified: "Score pilier Gouvernance issu du fournisseur fondamental / 100",
  },
  trap_score: {
    verified:
      "Trap Score = ∑ indicateurs d'alerte [PER<10, CA↘, Quick<0,5, FP<0, ROE<10%, |Sloan|>25%, ExtFin>25%, C-Score>5, M-Score>−1,78, EPV/Actifs<75%, + règle sectorielle Ind./Serv./Fin.] ∈ [0 ; 12]",
  },
  is_undervalued: {
    verified: "Sous-évalué = Vrai si Price / Book < 1 ou Cours / Valeur Intrinsèque < 1",
  },
  categories: {
    verified: "Classification croisant Qualité (Quality > 60%), Valeur (Value > 60%), Croissance (rCAGR) et Risque (Trap < 40%)",
  },
  advice: {
    verified: "Verdict synthétique croisant Uncle Stock Score, Value/Quality/Health Scores, Marge de sécurité VI et Trap Score",
  },
};

const FULL_INTRINSIC_FORMULAS: Record<string, string> = {
  dcf_fcf:
    "VI = [ Σ(t=1..5) (FCFF₀ × (1 + g)^t / (1 + WACC)^t) + (FCFF₅ / WACC) / (1 + WACC)^5 − Dette nette ] / Actions",
  buffett:
    "VI = Σ(t=1..10) (Div₀ × (1 + g_div)^t / (1 + Ke)^t) + [CBV/act₀ × (1 + g_cbv)^10] / (1 + Ke)^10",
  residual_income:
    "VI = CBV/act₀ + Σ(t=1..5) (RI₀ × (1 + g_RI)^t / (1 + Ke)^t) + (RI₅ / Ke) / (1 + Ke)^5  avec RI₀ = BPA − Ke × CBV/act",
  graham_formula:
    "Corrigée : VI = BPA × (7,0 + 100·ln(1 + g_cap)) × (4,4 / Y_corp20A)  |  Uncle Stock littérale : BPA × (7,0 + 100·ln(1 + g_cap) × 4,4 / Y)",
  epv:
    "Corrigée : VI = (NOPAT_norm / WACC − Dette nette) / Actions  |  Uncle Stock : ((CA × Marge_Opé_Aj_10A) / WACC − Dette nette) / Actions",
  value_driver:
    "VE = Cash_NOPAT × (1 + g_vd) × (1 − g_vd / CROIC_5A) / (WACC − g_vd) ; VI_corrigée = (VE − Dette nette) / Actions",
  lynch:
    "VI = BPA × (min(g_EBITDA ; 25%) × 100) en mode corrigé (ou BPA × g_EBITDA × 100 brut)",
  graham_number:
    "VI = √(22,5 × BPA × Actif net tangible par action)",
  ebitda_7_5x:
    "VI = (7,5 × EBITDA − Dette nette) / Actions",
  hold_5y:
    "OE₅ = OE₀/act × (1 + g_OE)^5 ; Cours₅ = OE₅ / Rdt_moy_OE_5A ; VI = Cours₅ / (1 + Ke)^5 + Σ(t=1..5) (OE_t × Payout_OE / (1 + Ke)^t)",
  dcf_fcf_no_growth:
    "VI = (FCFF₀ / WACC − Dette nette) / Actions",
  adjusted_lynch:
    "fairPEG = min(3,0 ; 0,5 × (10·g − 1,5)² + 1,98) ; VI = fairPEG × (BPA × g × 100)",
  current_price:
    "Référence de marché = Dernier cours de clôture (poids 1 en mode Uncle Stock, exclu du mode indépendant corrigé)",
  dcf_oe:
    "VI = [ Σ(t=1..5) (OE₀ × (1 + g_OE)^t / (1 + Ke)^t) + (OE₅ / Ke) / (1 + Ke)^5 ] / Actions",
  dcf_oe_linear:
    "OE(t) = a·(t − 1900) + b (OLS sur 10 ans) ; VI = [ Σ(t=1..100) OE(t) / (1 + Rf30A + 5%)^t ] / Actions",
  dcf_oe_quadratic:
    "OE(t) = a·(t − 1900)² + b·(t − 1900) + c (OLS historique complet) ; VI = [ Σ(t=1..100) OE(t) / (1 + Rf30A + 5%)^t ] / Actions",
  dcf_oe_regression:
    "VI = min(DCF OE Linéaire ; DCF OE Quadratique)",
  omalley:
    "VI = OE_prédit/act × (15 + 10 × max(−0,2 ; g_OE)) × (4,4 / Y_corp20A)",
  payback_x_years:
    "VI = [ CBV₀ + Σ(t=1..x) OIAI_lin(t) × (1 − Taux_IS) ] / Actions (sans actualisation)",
};

/** Détail chiffré complet pour l'un des 31 scores Uncle Stock (mode vérifié ou documenté). */
export function buildUncleStockScoreCalc(
  item: UncleStockScoreItem,
  mode: "verified" | "documented",
  dossier?: FinancialDossier,
): FinanceCalcDetail {
  const res = mode === "verified" ? item.verified : item.documented;
  const snap = dossier ? extractFundamentalSnapshot(dossier) : null;
  const isPiotroski = item.id === "piotroski_f_score";
  const binaryPioSteps = isPiotroski && dossier ? buildPiotroskiBinarySteps(dossier, snap) : [];

  const componentSteps: MetricCalcStep[] = res.components.map(c => {
    const valUsed = c.transformed_input != null ? c.transformed_input : c.input;
    const hasTransform =
      typeof c.transformed_input === "number" &&
      typeof c.input === "number" &&
      Math.abs(c.transformed_input - c.input) > 1e-6;

    const noteParts: string[] = [];
    if (c.input != null) noteParts.push(`Entrée brute : ${fmtAny(c.input)}`);
    if (hasTransform) noteParts.push(`Transf. : ${fmtAny(c.transformed_input)}`);
    if (c.weight != null) noteParts.push(`Poids : ×${fmtAny(c.weight)}`);
    if (c.contribution != null && c.weight != null && valUsed != null) {
      noteParts.push(`Produit : ${fmtAny(c.weight)} × (${fmtAny(valUsed)}) = ${c.contribution.toFixed(2)}`);
    } else if (c.contribution == null && c.input == null) {
      noteParts.push("Donnée absente");
    }

    return {
      label: isPiotroski ? `[Fraction] ${c.name}` : c.name,
      value:
        c.contribution != null
          ? `${c.contribution >= 0 ? "+" : ""}${c.contribution.toFixed(2)} pts`
          : fmtAny(c.input),
      note: noteParts.length > 0 ? noteParts.join(" · ") : undefined,
    };
  });
  const steps: MetricCalcStep[] = [...binaryPioSteps, ...componentSteps];

  const contribComps = res.components.filter(c => c.contribution != null);
  const weightedParts = contribComps.map(c => {
    const valUsed =
      c.transformed_input != null
        ? c.transformed_input
        : c.input != null
          ? c.input
          : c.contribution!;
    const valStr = fmtAny(valUsed);
    if (c.weight != null && c.weight !== 1) {
      return `${fmtAny(c.weight)}×(${valStr})`;
    }
    return typeof valUsed === "number" && valUsed < 0 ? `(${valStr})` : valStr;
  });

  const formulaDef = FULL_SCORE_FORMULAS[item.id];
  const fullFormula =
    mode === "documented" && formulaDef?.documented
      ? formulaDef.documented
      : formulaDef?.verified || res.summary || undefined;

  const contribSum = contribComps.reduce((s, c) => s + (c.contribution ?? 0), 0);
  const rawScoreNum = typeof res.raw_score === "number" ? res.raw_score : null;
  const matchesRawSum =
    rawScoreNum != null &&
    Math.abs(contribSum - rawScoreNum) <= Math.max(0.05, Math.abs(rawScoreNum) * 0.02);

  const rawExpr = weightedParts.join(" + ").replace(/\s\+\s-/g, " - ");
  const pipelineTail = `${
    res.clamped_score != null ? ` → borné = ${fmtAny(res.clamped_score)}` : ""
  }${
    res.normalized_score != null ? ` → normalisé = ${res.normalized_score.toFixed(1)}%` : ""
  } → final = ${res.display_value}`;

  const binaryBits =
    isPiotroski && dossier?.annual_tables?.piotroski?.criteria?.length
      ? dossier.annual_tables.piotroski.criteria.map(c => c.values[c.values.length - 1] ?? 0).join(" + ")
      : null;

  const fullSub =
    isPiotroski && res.raw_score != null
      ? `${
          binaryBits ? `F_entier = ${binaryBits} = ${fmtAny(res.raw_score)}/9` : `F_entier = ${fmtAny(res.raw_score)}/9`
        }${
          weightedParts.length > 0
            ? ` · F_fraction : Termes (${weightedParts.join(" ; ")}) → σ = ${
                res.normalized_score != null ? `${res.normalized_score.toFixed(1)}% (+${(res.normalized_score / 100).toFixed(2)})` : "—"
              }`
            : ""
        } → final = ${res.display_value}`
      : weightedParts.length > 0 && matchesRawSum
        ? `${rawExpr} = ${fmtAny(res.raw_score)} (brut)${pipelineTail}`
        : weightedParts.length > 0 && res.raw_score != null
          ? `Termes (${weightedParts.join(" ; ")}) → brut = ${fmtAny(res.raw_score)}${pipelineTail}`
          : res.raw_score != null
            ? `Score brut = ${fmtAny(res.raw_score)}${pipelineTail}`
            : res.summary || undefined;

  return {
    title: `${item.name} (${mode === "verified" ? "Vérifié" : "Documenté"})`,
    formula: fullFormula,
    substitution: fullSub,
    result:
      res.normalized_score != null
        ? `${res.display_value} (normalisé : ${res.normalized_score.toFixed(1)}/100)`
        : res.display_value || "—",
    steps,
    fundamentals: dossier ? selectUncleStockFundamentals(item.id, dossier) : undefined,
    notes: res.warnings.length > 0 ? res.warnings : undefined,
    source: res.source_version ? `Modèle ${res.source_version}` : undefined,
  };
}

function buildIntrinsicBaseFundamentals(data: IntrinsicValuationPayload, dossier?: FinancialDossier, currency = "USD"): MetricCalcStep[] {
  const f = dossier ? extractFundamentalSnapshot(dossier) : null;
  const coc = data.cost_of_capital || {};
  return compactFundamentals([
    data.current_price != null ? { label: "Cours actuel", value: fmtN(data.current_price, 2, ` ${currency}`) } : null,
    data.shares != null ? { label: "Actions retenues", value: `${(data.shares / 1e6).toFixed(1)} M` } : null,
    f?.stepM("Capitalisation boursière", f.hdr.market_cap),
    f?.stepM("Chiffre d'affaires", f.rev.latest),
    f?.stepM("EBITDA", f.ebitda.latest),
    f?.stepM("EBIT / Résultat opé.", f.ebit.latest),
    f?.stepM("Résultat net", f.ni.latest),
    f?.stepM("Flux d'exploitation", f.ocf.latest),
    f?.stepM("Investissements (CapEx)", f.capex.latest),
    f?.stepM("Free Cash Flow (FCF)", f.fcf.latest),
    f?.stepM("Trésorerie & placements CT", f.cash.latest),
    f?.stepM("Dette totale", f.totDebt.latest),
    f?.stepM("Dette nette", f.netDebt.latest),
    f?.stepPairM("Capitaux propres", f.eq),
    coc.marginal_tax_rate_pct != null ? { label: "Taux d'IS marginal", value: fmtN(coc.marginal_tax_rate_pct, 1, "%") } : null,
  ]);
}

/** Détail chiffré de la synthèse globale Valeur Intrinsèque / Cours-VI / Marge de sécurité. */
export function buildIntrinsicSummaryCalc(
  kind: "iv" | "price_to_iv" | "mos",
  data: IntrinsicValuationPayload,
  mode: "unclestock" | "corrected",
  currency: string,
  dossier?: FinancialDossier,
): FinanceCalcDetail | null {
  const agg = data.summary[mode];
  if (!agg) return null;
  const valField = mode === "unclestock" ? "unclestock_value" : "corrected_value";
  const stField = mode === "unclestock" ? "status_unclestock" : "status_corrected";
  const validWeighted = data.methods.filter(
    m => m.category === "weighted" && m.weight > 0 && m[stField] === "valid" && m[valField] != null,
  );
  const fundamentals = buildIntrinsicBaseFundamentals(data, dossier, currency);

  if (kind === "iv") {
    const numTerms = validWeighted.map(m => `${m.weight}×${m[valField]!.toFixed(2)}`);
    return {
      title: `Valeur intrinsèque globale (${mode === "corrected" ? "Mode Corrigé" : "Mode Uncle Stock"})`,
      formula: "VI = Σ(Poids_i × Méthode_i) / Σ(Poids_i) sur toutes les méthodes valides",
      substitution:
        numTerms.length > 0
          ? `(${numTerms.join(" + ")}) / ${agg.weight_used} = ${agg.intrinsic_value.toFixed(2)} ${currency}`
          : undefined,
      result: `${agg.intrinsic_value.toFixed(2)} ${currency} (${agg.methods_used}/${agg.methods_total} méthodes)`,
      steps: validWeighted.map(m => ({
        label: m.name,
        value: `${m[valField]!.toFixed(2)} ${currency}`,
        note: `Poids ${m.weight}/${agg.weight_used} · contrib. ${((m.weight * m[valField]!) / agg.weight_used).toFixed(2)} ${currency}`,
      })),
      fundamentals,
    };
  }

  const priceTxt = data.current_price != null ? `${data.current_price.toFixed(2)} ${currency}` : "—";
  if (kind === "price_to_iv") {
    return {
      title: "Ratio Cours / Valeur Intrinsèque",
      formula: "Cours / VI",
      substitution: `${priceTxt} / ${agg.intrinsic_value.toFixed(2)} ${currency} = ${agg.price_to_iv?.toFixed(3) ?? "—"}×`,
      result: agg.price_to_iv != null ? `${agg.price_to_iv.toFixed(2)}×` : "—",
      steps: [
        { label: "Cours actuel", value: priceTxt },
        { label: "VI retenue", value: `${agg.intrinsic_value.toFixed(2)} ${currency}` },
      ],
      fundamentals,
    };
  }

  return {
    title: "Marge de sécurité",
    formula: "(1 − Cours / VI) × 100",
    substitution: `(1 − ${priceTxt} / ${agg.intrinsic_value.toFixed(2)} ${currency}) × 100 = ${agg.margin_of_safety_pct != null ? `${agg.margin_of_safety_pct.toFixed(1)}%` : "—"}`,
    result: agg.margin_of_safety_pct != null ? `${agg.margin_of_safety_pct >= 0 ? "+" : ""}${agg.margin_of_safety_pct.toFixed(1)}%` : "—",
    steps: [
      { label: "Cours actuel", value: priceTxt },
      { label: "Valeur intrinsèque", value: `${agg.intrinsic_value.toFixed(2)} ${currency}` },
    ],
    fundamentals,
  };
}

/** Détail chiffré du Coût du capital, WACC et Retours aux propriétaires. */
export function buildCostOfCapitalCalc(
  key:
    | "ke_capm"
    | "ke_ddm"
    | "kd_after_tax"
    | "wacc"
    | "equity_charge"
    | "rcagr_67"
    | "total_owner_return"
    | "net_owner_return"
    | "buffett_irr"
    | "forward_return_yacktman"
    | "payback_market",
  data: IntrinsicValuationPayload,
  currency: string,
  dossier?: FinancialDossier,
): FinanceCalcDetail {
  const coc = data.cost_of_capital || {};
  const owr = data.owner_returns || {};
  const gi = data.growth_inputs || {};
  const f = dossier ? extractFundamentalSnapshot(dossier) : null;
  const shM = data.shares ? data.shares / 1e6 : null;
  const eqPs = f?.eq.latest != null && data.shares && data.shares > 0 ? f.eq.latest / data.shares : null;
  const fcfPs = f?.fcf.latest != null && data.shares && data.shares > 0 ? f.fcf.latest / data.shares : null;

  switch (key) {
    case "ke_capm":
      return {
        title: "Coût des fonds propres (Ke CAPM)",
        formula: "Ke = Rf + β_borné × ERP",
        substitution: `${fmtN(coc.risk_free_rate_pct, 2, "%")} + ${fmtN(coc.beta_clamped, 2)} × ${fmtN(coc.erp_pct, 2, "%")} = ${fmtN(coc.cost_of_equity_capm_pct, 2, "%")}`,
        result: fmtN(coc.cost_of_equity_capm_pct, 2, "%"),
        steps: [
          { label: "Taux sans risque (Rf)", value: fmtN(coc.risk_free_rate_pct, 2, "%") },
          { label: "Bêta brut / borné [0 ; 2]", value: `${fmtN(coc.beta_raw, 2)} → ${fmtN(coc.beta_clamped, 2)}` },
          { label: "Prime de risque marché (ERP)", value: fmtN(coc.erp_pct, 2, "%") },
        ],
        fundamentals: compactFundamentals([
          f?.hdr.market_cap != null ? { label: "Capitalisation boursière", value: fmtM(f.hdr.market_cap, ` M ${currency}`) } : null,
          f?.stepM("Capitaux propres", f.eq.latest),
        ]),
      };
    case "ke_ddm":
      return {
        title: "Coût des fonds propres (Ke DDM)",
        formula: "Ke_DDM = Rendement dividende + Croissance dividendes (rCAGR 67%)",
        substitution: `${fmtN(f?.hdr.dividend_yield_pct, 2, "%")} + ${fmtN(gi.div_rcagr_67_pct, 2, "%")} = ${fmtN(coc.cost_of_equity_ddm_pct, 2, "%")}`,
        result: fmtN(coc.cost_of_equity_ddm_pct, 2, "%"),
        steps: [
          { label: "Rendement dividende", value: fmtN(f?.hdr.dividend_yield_pct, 2, "%") },
          { label: "Croissance dividendes (rCAGR 67%)", value: fmtN(gi.div_rcagr_67_pct, 2, "%") },
        ],
        fundamentals: compactFundamentals([
          data.current_price != null ? { label: "Cours actuel", value: fmtN(data.current_price, 2, ` ${currency}`) } : null,
          f?.stepM("Dividendes versés", f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : null),
        ]),
      };
    case "kd_after_tax":
      return {
        title: "Coût de la dette après impôts (Kd)",
        formula: "Kd = (Rf + Spread crédit [Santé 0..4]) × (1 − Taux IS marginal)",
        substitution: `Spread(santé ${coc.financial_health_score_0_4 ?? "—"}/4) · IS ${fmtN(coc.marginal_tax_rate_pct, 1, "%")} → ${fmtN(coc.after_tax_cost_of_debt_pct, 2, "%")}`,
        result: fmtN(coc.after_tax_cost_of_debt_pct, 2, "%"),
        steps: [
          { label: "Taux sans risque (Rf)", value: fmtN(coc.risk_free_rate_pct, 2, "%") },
          { label: "Obligations corp. 20A", value: fmtN(coc.corporate_bond_20y_pct, 2, "%") },
          { label: "Score santé financière", value: `${coc.financial_health_score_0_4 ?? "—"} / 4` },
          { label: "Taux d'imposition marginal", value: fmtN(coc.marginal_tax_rate_pct, 1, "%") },
        ],
        fundamentals: compactFundamentals([
          f?.stepM("Dette totale", f.totDebt.latest),
          f?.stepM("Charges d'intérêts", f.intExp.latest != null ? Math.abs(f.intExp.latest) : null),
          f?.stepM("Résultat avant impôt", f.pretax.latest),
          f?.stepM("Impôts", f.tax.latest),
        ]),
      };
    case "wacc":
      return {
        title: "WACC retenu (Coût Moyen Pondéré du Capital)",
        formula: "WACC = max(Plancher ; %FP × Ke + %Dette × Kd_après_IS)",
        substitution: `${fmtN(coc.equity_financing_pct, 1, "%")} × ${fmtN(coc.cost_of_equity_capm_pct, 2, "%")} + ${fmtN(coc.debt_financing_pct, 1, "%")} × ${fmtN(coc.after_tax_cost_of_debt_pct, 2, "%")} = ${fmtN(coc.wacc_raw_pct, 2, "%")} (retenu : ${fmtN(coc.wacc_pct, 2, "%")})`,
        result: fmtN(coc.wacc_pct, 2, "%"),
        steps: [
          { label: "Poids Capitaux Propres (E / (E+D))", value: fmtN(coc.equity_financing_pct, 1, "%") },
          { label: "Poids Dette (D / (E+D))", value: fmtN(coc.debt_financing_pct, 1, "%") },
          { label: "WACC brut calculé", value: fmtN(coc.wacc_raw_pct, 2, "%") },
          { label: "Plancher prudentiel", value: fmtN(coc.wacc_floor_pct, 2, "%") },
        ],
        fundamentals: compactFundamentals([
          f?.stepM("Capitalisation boursière (E)", f.hdr.market_cap),
          f?.stepM("Dette financière totale (D)", f.totDebt.latest),
          f?.stepM("Trésorerie", f.cash.latest),
          f?.hdr.beta != null ? { label: "Bêta", value: fmtN(f.hdr.beta, 2) } : null,
        ]),
      };
    case "equity_charge":
      return {
        title: "Charge d’équité par action",
        formula: "Charge d'équité = Ke_CAPM × (Capitaux propres / Actions)",
        substitution: `${fmtN(coc.cost_of_equity_capm_pct, 2, "%")} × ${fmtN(eqPs, 2, ` ${currency}`)} = ${fmtN(coc.equity_charge_ps, 2, ` ${currency}`)}`,
        result: fmtN(coc.equity_charge_ps, 2, ` ${currency}`),
        steps: [
          { label: "Ke CAPM", value: fmtN(coc.cost_of_equity_capm_pct, 2, "%") },
          { label: "Charge totale", value: fmtM(coc.equity_charge_total, ` M ${currency}`) },
        ],
        fundamentals: compactFundamentals([
          f?.stepM("Capitaux propres", f.eq.latest),
          shM != null ? { label: "Actions en circulation", value: `${shM.toFixed(1)} M` } : null,
          eqPs != null ? { label: "Capitaux propres / action", value: fmtN(eqPs, 2, ` ${currency}`) } : null,
        ]),
      };
    case "rcagr_67":
      return {
        title: "Croissance FCFF (rCAGR 67%)",
        formula: "CAGR ajusté par régression log-linéaire pénalisé à 67% selon la dispersion",
        substitution: `CAGR brut = ${fmtN(gi.fcff_rcagr_raw_pct, 2, "%")} → rCAGR 67% = ${fmtN(gi.fcff_rcagr_67_pct, 2, "%")}`,
        result: fmtN(gi.fcff_rcagr_67_pct, 2, "%"),
        steps: [
          { label: "FCFF rCAGR 67%", value: fmtN(gi.fcff_rcagr_67_pct, 2, "%") },
          { label: "Owner Earnings rCAGR 67%", value: fmtN(gi.oe_rcagr_67_pct, 2, "%") },
          { label: "EBITDA rCAGR 67%", value: fmtN(gi.ebitda_rcagr_67_pct, 2, "%") },
          { label: "BPA rCAGR 67%", value: fmtN(gi.eps_rcagr_67_pct, 2, "%") },
          { label: "Capitaux propres rCAGR 67%", value: fmtN(gi.cbv_rcagr_67_pct, 2, "%") },
        ],
        fundamentals: f ? compactFundamentals([f.stepM("Free Cash Flow", f.fcf.latest), f.stepM("Flux d'exploitation", f.ocf.latest), f.stepM("CapEx", f.capex.latest)]) : undefined,
      };
    case "total_owner_return":
      return {
        title: "Total Owner Return",
        formula: "(Capitaux propres_N + Dividendes versés_N − Capitaux propres_N-1) / Capitaux propres_N-1",
        substitution:
          f?.eq.latest != null && f.eq.prev != null
            ? `(${fmtM(f.eq.latest)} + ${fmtM(f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : 0)} − ${fmtM(f.eq.prev)}) / ${fmtM(f.eq.prev)} = ${fmtN(owr.total_owner_return_pct, 1, "%")}`
            : undefined,
        result: fmtN(owr.total_owner_return_pct, 1, "%"),
        steps: [{ label: "Croissance capitaux propres (rCAGR 67%)", value: fmtN(gi.cbv_rcagr_67_pct, 2, "%") }],
        fundamentals: compactFundamentals([
          f?.stepPairM("Capitaux propres", f.eq),
          f?.stepM("Dividendes versés", f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : null),
        ]),
      };
    case "net_owner_return":
      return {
        title: "Net Owner Return (Création de valeur nette)",
        formula: "(Capitaux propres_N + Dividendes_N − Charge d'équité_N-1 − Capitaux propres_N-1) / Capitaux propres_N-1",
        substitution: `Total Owner Return (${fmtN(owr.total_owner_return_pct, 1, "%")}) − Charge d'équité (${fmtN(coc.cost_of_equity_capm_pct, 2, "%")}) = ${fmtN(owr.net_owner_return_pct, 1, "%")}`,
        result: fmtN(owr.net_owner_return_pct, 1, "%"),
        fundamentals: compactFundamentals([
          f?.stepPairM("Capitaux propres", f.eq),
          f?.stepM("Dividendes versés", f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : null),
          { label: "Ke CAPM appliqué", value: fmtN(coc.cost_of_equity_capm_pct, 2, "%") },
        ]),
      };
    case "buffett_irr":
      return {
        title: "TRI implicite Buffett",
        formula: "Taux de rendement interne annualisé sur 10 ans égalisant Cours actuel et flux (Dividendes + CBV final)",
        result: fmtN(owr.buffett_rate_of_return_pct, 2, "%"),
        steps: [
          { label: "Croissance CBV retenue", value: fmtN(gi.cbv_rcagr_67_pct, 2, "%") },
          { label: "Croissance dividendes", value: fmtN(gi.div_rcagr_67_pct, 2, "%") },
        ],
        fundamentals: compactFundamentals([
          data.current_price != null ? { label: "Cours actuel", value: fmtN(data.current_price, 2, ` ${currency}`) } : null,
          eqPs != null ? { label: "Capitaux propres / action", value: fmtN(eqPs, 2, ` ${currency}`) } : null,
          f?.stepM("Capitaux propres totaux", f.eq.latest),
          f?.stepM("Dividendes versés", f.divPaid.latest != null ? Math.abs(f.divPaid.latest) : null),
        ]),
      };
    case "forward_return_yacktman": {
      const fcfYield = fcfPs != null && data.current_price ? (fcfPs / data.current_price) * 100 : null;
      return {
        title: "Rendement prospectif (Donald Yacktman)",
        formula: "Rendement FCF (FCF / action ÷ Cours) + Croissance EBITDA 6A + Inflation",
        substitution:
          fcfYield != null
            ? `${fcfYield.toFixed(2)}% + ${fmtN(gi.ebitda_rcagr_67_pct, 2, "%")} + Inflation = ${fmtN(owr.forward_rate_of_return_pct, 2, "%")}`
            : undefined,
        result: fmtN(owr.forward_rate_of_return_pct, 2, "%"),
        steps: [
          fcfYield != null ? { label: "Rendement FCF sur cours", value: `${fcfYield.toFixed(2)}%` } : { label: "FCF / action", value: fmtN(fcfPs, 2, ` ${currency}`) },
          { label: "Croissance EBITDA (rCAGR)", value: fmtN(gi.ebitda_rcagr_67_pct, 2, "%") },
        ],
        fundamentals: compactFundamentals([
          data.current_price != null ? { label: "Cours actuel", value: fmtN(data.current_price, 2, ` ${currency}`) } : null,
          f?.stepM("Free Cash Flow", f.fcf.latest),
          f?.stepM("EBITDA", f.ebitda.latest),
          shM != null ? { label: "Actions en circulation", value: `${shM.toFixed(1)} M` } : null,
        ]),
      };
    }
    case "payback_market":
      return {
        title: "Payback marché estimé",
        formula: "Durée (années) nécessaire pour que les bénéfices après impôts cumulés atteignent (Cours − Trésorerie nette / act.)",
        result: owr.payback_years_market != null ? `${owr.payback_years_market.toFixed(1)} ans` : "—",
        fundamentals: compactFundamentals([
          data.current_price != null ? { label: "Cours actuel", value: fmtN(data.current_price, 2, ` ${currency}`) } : null,
          f?.stepM("Résultat avant impôt", f.pretax.latest),
          f?.stepM("Trésorerie & placements CT", f.cash.latest),
          f?.stepM("Dette totale", f.totDebt.latest),
        ]),
      };
  }
}

/** Détail chiffré d'une méthode de valorisation intrinsèque. */
export function buildIntrinsicMethodCalc(
  method: IntrinsicMethodResult,
  mode: "unclestock" | "corrected",
  currency: string,
  dossier?: FinancialDossier,
): FinanceCalcDetail {
  const val = mode === "unclestock" ? method.unclestock_value : method.corrected_value;
  const mos = mode === "unclestock" ? method.margin_of_safety_unclestock_pct : method.margin_of_safety_corrected_pct;
  const steps: MetricCalcStep[] = [
    ...method.assumptions.map((a, idx) => ({ label: `Hypothèse ${idx + 1}`, value: a })),
    ...Object.entries(method.intermediates || {}).map(([k, v]) => ({
      label: k,
      value: fmtAny(v),
    })),
  ];
  const interPairs = Object.entries(method.intermediates || {})
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${k}=${fmtAny(v)}`);
  const substitution =
    interPairs.length > 0
      ? `${interPairs.join(" · ")} → VI = ${val != null ? `${val.toFixed(2)} ${currency}` : "—"}`
      : method.assumptions.join(" · ") || undefined;
  const f = dossier ? extractFundamentalSnapshot(dossier) : null;
  const fundamentals = f
    ? compactFundamentals([
        f.cap.price != null ? { label: "Cours actuel", value: fmtN(f.cap.price, 2, ` ${currency}`) } : null,
        f.shares.latest != null ? { label: `Actions (${f.lastYr || "bilan"})`, value: `${(f.shares.latest / 1e6).toFixed(1)} M` } : null,
        f.stepM("Free Cash Flow", f.fcf.latest),
        f.stepM("Flux d'exploitation", f.ocf.latest),
        f.stepM("CapEx", f.capex.latest),
        f.stepM("EBITDA", f.ebitda.latest),
        f.stepM("EBIT", f.ebit.latest),
        f.stepM("Résultat net", f.ni.latest),
        f.eps.latest != null ? { label: "BPA dilué", value: fmtN(f.eps.latest, 2, ` ${currency}`) } : null,
        f.stepM("Capitaux propres", f.eq.latest),
        f.stepM("Dette nette", f.netDebt.latest),
      ])
    : undefined;

  return {
    title: `${method.name} (poids ${method.weight})`,
    formula: FULL_INTRINSIC_FORMULAS[method.id] || method.assumptions.join(" · ") || undefined,
    substitution,
    result:
      val != null
        ? `${val.toFixed(2)} ${currency}${mos != null ? ` (MoS : ${mos >= 0 ? "+" : ""}${mos.toFixed(1)}%)` : ""}`
        : method.exclusion_reason || "Indisponible",
    steps,
    fundamentals,
    notes: [
      ...(method.exclusion_reason ? [method.exclusion_reason] : []),
      ...(method.warnings || []),
    ],
  };
}

const RISK_FORMULAS: Record<string, { formula: string; note: string }> = {
  volatility: { formula: "σ = Écart-type(rendements journaliers) × √252", note: "Annualisée sur séances ajustées des dividendes" },
  semi_volatility: { formula: "σ₋ = √(Moyenne(min(r − r̄ ; 0)²)) × √252", note: "Ne pénalise que les rendements inférieurs à la moyenne" },
  max_drawdown: { formula: "MaxDD = min_t((Cours_t − Pic_précédent_t) / Pic_précédent_t)", note: "Pire baisse pic-à-creux sur la fenêtre" },
  max_drawdown_duration: { formula: "Durée maximale (jours) entre un sommet historique et sa récupération", note: "Temps d'immobilisation sous l'eau" },
  var_95: { formula: "VaR 95% = Quantile 5% des pertes mensuelles (21 j) × √12", note: "Perte seuil non dépassée dans 95% des cas" },
  cvar_95: { formula: "CVaR 95% = Moyenne des 5% pires pertes", note: "Perte moyenne au-delà de la VaR 95%" },
  ulcer_index: { formula: "UI = √(Moyenne((Drawdown_t %)²))", note: "Mesure combinée de profondeur et durée des baisses" },
  sharpe: { formula: "Sharpe = (R_annualisé − Rf) / Volatilité annualisée", note: "Rendement excédentaire par unité de risque total" },
  sortino: { formula: "Sortino = (R_annualisé − Rf) / Semi-volatilité annualisée", note: "Rendement excédentaire par unité de risque baissier" },
  calmar: { formula: "Calmar = R_annualisé / |Max Drawdown|", note: "Ratio gain annuel sur perte maximale historique" },
  excess_calmar: { formula: "Excess Calmar = (R_annualisé − Rf) / |Max Drawdown|", note: "Calmar net du taux sans risque" },
  martin: { formula: "Martin (Ulcer Perf. Index) = (R_annualisé − Rf) / Ulcer Index", note: "Rendement excédentaire rapporté au stress de baisse" },
};

/** Détail chiffré d'un indicateur de gestion du risque (1A..5A). */
export function buildRiskMetricCalc(
  metric: { key: string; label: string; format: string; values: (number | null)[] },
  dossier: FinancialDossier,
): FinanceCalcDetail {
  const meta = RISK_FORMULAS[metric.key] || { formula: metric.label, note: "Calculé sur l'historique EOD ajusté" };
  const horizons = dossier.risk.horizons || [];
  const rfs = dossier.risk.rf_rates_pct || [];
  const fmtV = (v: number | null | undefined) =>
    v == null ? "—" : metric.format === "pct" ? `${v.toFixed(1)}%` : metric.format === "days" ? `${Math.round(v)} j` : v.toFixed(2);
  const perfMap = Object.fromEntries(
    (dossier.performance?.horizons || []).map(p => [p.label.toLowerCase(), p.pct]),
  );
  const firstChart = dossier.performance_chart?.[0];
  const lastChart = dossier.performance_chart?.[dossier.performance_chart.length - 1];

  return {
    title: metric.label,
    formula: meta.formula,
    steps: horizons.map((h, idx) => ({
      label: `Fenêtre ${h}`,
      value: fmtV(metric.values[idx]),
      note: rfs[idx] != null ? `Rf = ${rfs[idx].toFixed(1)}%` : undefined,
    })),
    fundamentals: compactFundamentals([
      dossier.capital_valuation.price != null
        ? { label: "Dernier cours", value: fmtN(dossier.capital_valuation.price, 2, ` ${dossier.currency}`) }
        : null,
      lastChart && firstChart
        ? { label: "Plage de cours ajustée", value: `${firstChart.adj_price.toFixed(2)} → ${lastChart.adj_price.toFixed(2)} ${dossier.currency}`, note: `${firstChart.date} → ${lastChart.date}` }
        : null,
      perfMap["1 an"] != null ? { label: "Perf. ajustée 1 an", value: `${perfMap["1 an"] >= 0 ? "+" : ""}${perfMap["1 an"].toFixed(1)}%` } : null,
      perfMap["5 ans"] != null ? { label: "Perf. ajustée 5 ans", value: `${perfMap["5 ans"] >= 0 ? "+" : ""}${perfMap["5 ans"].toFixed(1)}%` } : null,
    ]),
    notes: [meta.note],
    source: `Série EOD ajustée (${dossier.currency}) · ${dossier.performance_chart.length} points mensuels`,
  };
}

/** Détail chiffré des scores qualitatifs IH Score, Piotroski F-Score et Altman Z-Score. */
export function buildQualitativeScoreCalc(
  kind: "ih_score" | "piotroski" | "altman",
  annualTables: FinancialDossier["annual_tables"],
  dossier?: FinancialDossier,
): FinanceCalcDetail {
  const f = dossier ? extractFundamentalSnapshot(dossier) : null;

  if (kind === "ih_score") {
    const ih = annualTables.ih_score;
    const critAvgs = ih.criteria.filter(c => c.avg != null).map(c => c.avg!.toFixed(2));
    return {
      title: "IH Score (Qualité & Régularité / 9)",
      formula: "IH_Score = Moyenne des 7 critères annuels notés [0 ; 9] (Croissance CA, Croissance EBIT, Croissance EBT, ROIC, CROIC, Couverture EBITDA, Coût de la dette) ; Tendance = Moyenne des critères de tendance récente",
      substitution:
        critAvgs.length > 0
          ? `(${critAvgs.join(" + ")}) / ${critAvgs.length} = ${ih.latest_score?.toFixed(2) ?? "—"} / 9 (${ih.quality_label || ih.trend})`
          : undefined,
      result: ih.latest_score != null ? `${ih.latest_score.toFixed(1)} / 9 (${ih.quality_label || ih.trend})` : "—",
      steps: [
        ...ih.criteria.map(c => ({
          label: c.label,
          value: c.avg != null ? c.avg.toFixed(2) : "—",
          note: `Dernière année : ${lastNonNull(c.values) ?? "—"}`,
        })),
        ...ih.trend_criteria.map(c => ({
          label: `Tendance · ${c.label}`,
          value: c.avg != null ? c.avg.toFixed(2) : "—",
        })),
      ],
      fundamentals: f
        ? compactFundamentals([
            f.stepM("Chiffre d'affaires", f.rev.latest),
            f.stepM("EBIT", f.ebit.latest),
            f.stepM("Résultat avant impôt", f.pretax.latest),
            f.stepM("EBITDA", f.ebitda.latest),
            f.stepM("Free Cash Flow", f.fcf.latest),
            f.tbl("roic").latest != null ? { label: `ROIC (${f.lastYr})`, value: fmtN(f.tbl("roic").latest, 1, "%") } : null,
            f.tbl("croic").latest != null ? { label: `CROIC (${f.lastYr})`, value: fmtN(f.tbl("croic").latest, 1, "%") } : null,
            f.hdr.beta != null ? { label: "Bêta", value: fmtN(f.hdr.beta, 2) } : null,
          ])
        : undefined,
    };
  }

  if (kind === "piotroski") {
    const p = annualTables.piotroski;
    const yr = p.years[p.years.length - 1] || "";
    const passedList = dossier
      ? buildPiotroskiBinarySteps(dossier, f)
      : p.criteria.map((c, idx) => ({
          label: `[${idx + 1}/9] ${c.label}`,
          value: c.values[c.values.length - 1] === 1 ? "1 pt ✓" : "0 pt",
        }));
    return {
      title: `F-Score de Piotroski (${yr})`,
      formula:
        "F = I(ROA>0) + I(ΔROA>0) + I(CFO>0) + I(CFO>RN) + I(ΔMargeOp>0) + I(ΔRotationActifs>0) + I(ΔDette/Actifs≤0) + I(ΔLiquiditéGén>0) + I(ΔActions≤0)",
      substitution: `${p.criteria.map(c => c.values[c.values.length - 1] ?? 0).join(" + ")} = ${p.latest_score ?? "—"} / 9`,
      result: p.latest_score != null ? `${p.latest_score} / 9` : "—",
      steps: passedList,
      fundamentals: f ? buildPiotroskiFundamentals(f) : undefined,
    };
  }

  const a = annualTables.altman;
  const yr = a.years[a.years.length - 1] || "";
  const vals = a.criteria.map(c => c.values[c.values.length - 1]);
  const wcVal = f ? (f.wc.latest ?? (f.ca.latest != null && f.cl.latest != null ? f.ca.latest - f.cl.latest : null)) : null;
  const mcapLatest = f ? (f.tbl("mcap").latest ?? f.hdr.market_cap) : null;
  const fullAltmanSub =
    f && f.assets.latest && f.liab.latest
      ? `1,2×(${fmtM(wcVal)}/${fmtM(f.assets.latest)}) + 1,4×(${fmtM(f.retEarn.latest)}/${fmtM(f.assets.latest)}) + 3,3×(${fmtM(f.ebit.latest)}/${fmtM(f.assets.latest)}) + 0,6×(${fmtM(mcapLatest)}/${fmtM(f.liab.latest)}) + (${fmtM(f.rev.latest)}/${fmtM(f.assets.latest)}) = ${vals.map(v => (v != null ? v.toFixed(2) : "0")).join(" + ")} = ${a.latest_score?.toFixed(2) ?? "—"}`
      : vals.some(v => v != null)
        ? `${vals.map(v => (v != null ? v.toFixed(2) : "0")).join(" + ")} = ${a.latest_score?.toFixed(2) ?? "—"}`
        : undefined;
  return {
    title: `Z-Score d'Altman (${yr})`,
    formula: "Z = 1,2·(BFR/Actifs) + 1,4·(Résultats non dist./Actifs) + 3,3·(EBIT/Actifs) + 0,6·(Capi./Passifs) + 1,0·(CA/Actifs)",
    substitution: fullAltmanSub,
    result: a.latest_score != null ? `${a.latest_score.toFixed(2)}` : "—",
    steps: a.criteria.map(c => ({
      label: c.label,
      value: fmtN(c.values[c.values.length - 1], 2),
    })),
    fundamentals: f
      ? compactFundamentals([
          f.stepM("Fonds de roulement (BFR)", wcVal, f.ca.latest != null && f.cl.latest != null ? `${fmtM(f.ca.latest)} − ${fmtM(f.cl.latest)}` : undefined),
          f.stepM("Résultats non distribués", f.retEarn.latest),
          f.stepM("EBIT", f.ebit.latest),
          f.stepM("Capitalisation boursière", mcapLatest),
          f.stepM("Passifs totaux", f.liab.latest),
          f.stepM("Chiffre d'affaires", f.rev.latest),
          f.stepM("Total actifs", f.assets.latest),
        ])
      : undefined,
    notes: ["Z > 2,99 : Zone sûre · 1,81 à 2,99 : Zone grise · < 1,81 : Risque financier"],
  };
}

/** Détail chiffré de chaque ratio financier calculé dans les tableaux annuels. */
export function buildAnnualRatioCalc(row: DossierMetricRow, dossier: FinancialDossier): FinanceCalcDetail | null {
  const f = extractFundamentalSnapshot(dossier);
  const cur = f.cur;
  const lastYr = f.lastYr;
  const prevYr = f.prevYr;
  const val = lastNonNull(row.values);

  const rev = f.tbl("rev").latest ?? f.rev.latest;
  const gp = f.gp.latest;
  const ebitda = f.tbl("ebitda").latest ?? f.ebitda.latest;
  const opinc = f.tbl("opinc").latest ?? f.opinc.latest;
  const ni = f.tbl("ni").latest ?? f.ni.latest;
  const fcf = f.tbl("fcf").latest ?? f.fcf.latest;
  const eq = { latest: f.tbl("eq").latest ?? f.eq.latest, prev: f.tbl("eq").prev ?? f.eq.prev };
  const capInv = f.tbl("cap_inv");
  const sh = f.tbl("shares").latest ?? f.shares.latest;
  const mcap = f.tbl("mcap").latest ?? f.hdr.market_cap;
  const eps = f.tbl("eps").latest ?? f.eps.latest;
  const divPaid = f.tbl("div_paid").latest ?? f.divPaid.latest;
  const intExp = f.intExp.latest;
  const ocf = f.ocf.latest;
  const capex = f.capex.latest;
  const netDebt = f.netDebt.latest ?? (f.totDebt.latest != null && f.cash.latest != null ? f.totDebt.latest - f.cash.latest : null);

  switch (row.key) {
    case "rev":
      return {
        title: `Chiffre d'affaires (${lastYr})`,
        formula: "Revenus nets comptabilisés sur l'exercice",
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepPairM("Chiffre d'affaires", f.rev),
          f.stepM("Coût des ventes", f.costRev.latest != null ? Math.abs(f.costRev.latest) : null),
          f.stepM("Bénéfice brut", gp),
        ]),
      };
    case "ebitda":
      return {
        title: `EBITDA (${lastYr})`,
        formula: "EBITDA ≈ Résultat opérationnel (EBIT) + Amortissements & dépréciations",
        substitution:
          opinc != null && f.da.latest != null
            ? `${fmtM(opinc)} + ${fmtM(Math.abs(f.da.latest))} ≈ ${fmtM(val, ` M ${cur}`)}`
            : undefined,
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Résultat opérationnel (EBIT)", opinc),
          f.stepM("Amortissements & dépréciations", f.da.latest != null ? Math.abs(f.da.latest) : null),
          f.stepM("Chiffre d'affaires", rev),
        ]),
      };
    case "opinc":
      return {
        title: `Résultat opérationnel (${lastYr})`,
        formula: "Bénéfice brut − Charges opérationnelles (R&D + SG&A + autres)",
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Chiffre d'affaires", rev),
          f.stepM("Bénéfice brut", gp),
          f.stepM("R&D", f.rd.latest != null ? Math.abs(f.rd.latest) : null),
          f.stepM("SG&A", f.sga.latest != null ? Math.abs(f.sga.latest) : null),
        ]),
      };
    case "ni":
      return {
        title: `Résultat net (${lastYr})`,
        formula: "Résultat avant impôts − Impôts sur les bénéfices",
        substitution:
          f.pretax.latest != null && f.tax.latest != null
            ? `${fmtM(f.pretax.latest)} − ${fmtM(f.tax.latest)} = ${fmtM(val, ` M ${cur}`)}`
            : undefined,
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Résultat opérationnel", opinc),
          f.stepM("Charges d'intérêts", intExp != null ? Math.abs(intExp) : null),
          f.stepM("Résultat avant impôt", f.pretax.latest),
          f.stepM("Impôts", f.tax.latest),
        ]),
      };
    case "fcf":
      return {
        title: `Flux de trésorerie libre — FCF (${lastYr})`,
        formula: "Flux opérationnel − |Investissements (CapEx)|",
        substitution:
          ocf != null && capex != null
            ? `${fmtM(ocf)} − ${fmtM(Math.abs(capex))} = ${fmtM(val, ` M ${cur}`)}`
            : undefined,
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Flux d'exploitation (OCF)", ocf),
          f.stepM("Investissements (CapEx)", capex != null ? Math.abs(capex) : null),
          f.stepM("Résultat net", ni),
        ]),
      };
    case "eq":
      return {
        title: `Capitaux propres (${lastYr})`,
        formula: "Total Actifs − Total Passifs",
        substitution:
          f.assets.latest != null && f.liab.latest != null
            ? `${fmtM(f.assets.latest)} − ${fmtM(f.liab.latest)} ≈ ${fmtM(val, ` M ${cur}`)}`
            : undefined,
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepPairM("Capitaux propres", eq),
          f.stepM("Total actifs", f.assets.latest),
          f.stepM("Total passifs", f.liab.latest),
          f.stepM("Résultats non distribués", f.retEarn.latest),
        ]),
      };
    case "mcap":
      return {
        title: `Capitalisation boursière fin d'exercice (${lastYr})`,
        formula: "Cours clôture exercice × Actions en circulation",
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          sh != null ? { label: `Actions (${lastYr})`, value: `${(sh / 1e6).toFixed(1)} M` } : null,
          f.stepM("Capitaux propres", eq.latest),
          f.stepM("Dette nette", netDebt),
        ]),
      };
    case "div_paid":
      return {
        title: `Dividendes payés (${lastYr})`,
        formula: "Flux de trésorerie versés en dividendes aux actionnaires",
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", ni),
          f.stepM("Free Cash Flow", fcf),
          f.stepM("Rachats d'actions", f.buyback.latest != null ? Math.abs(f.buyback.latest) : null),
        ]),
      };
    case "gross_m":
      return {
        title: `Marge brute (${lastYr})`,
        formula: "(Bénéfice brut / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(gp)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Chiffre d'affaires", rev),
          f.stepM("Coût des ventes", f.costRev.latest != null ? Math.abs(f.costRev.latest) : null),
          f.stepM("Bénéfice brut", gp),
        ]),
      };
    case "ebitda_m":
      return {
        title: `Marge d'EBITDA (${lastYr})`,
        formula: "(EBITDA / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(ebitda)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("EBITDA", ebitda),
          f.stepM("Chiffre d'affaires", rev),
          f.stepM("Résultat opérationnel", opinc),
          f.stepM("Amortissements & dépréciations", f.da.latest != null ? Math.abs(f.da.latest) : null),
        ]),
      };
    case "op_m":
      return {
        title: `Marge opérationnelle (${lastYr})`,
        formula: "(Résultat opérationnel / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(opinc)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat opérationnel (EBIT)", opinc),
          f.stepM("Chiffre d'affaires", rev),
          f.stepM("Bénéfice brut", gp),
        ]),
      };
    case "net_m":
      return {
        title: `Marge nette (${lastYr})`,
        formula: "(Résultat net / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", ni),
          f.stepM("Résultat avant impôt", f.pretax.latest),
          f.stepM("Impôts", f.tax.latest),
          f.stepM("Chiffre d'affaires", rev),
        ]),
      };
    case "fcf_m":
      return {
        title: `Marge de FCF (${lastYr})`,
        formula: "(Free Cash Flow / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(fcf)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Flux d'exploitation", ocf),
          f.stepM("Investissements (CapEx)", capex != null ? Math.abs(capex) : null),
          f.stepM("Free Cash Flow", fcf),
          f.stepM("Chiffre d'affaires", rev),
        ]),
      };
    case "roa":
      return {
        title: `ROA — Rentabilité économique (${lastYr})`,
        formula: "(Résultat net / Moyenne des Actifs totaux) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(f.avg(f.assets))}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", ni),
          f.stepPairM("Actifs totaux", f.assets),
        ]),
        notes: [
          "Convention tableau IH : Résultat net / Actifs totaux moyens. Le référentiel Uncle Stock calcule également ROA = NOPAT / Actifs totaux moyens (visible dans l'explorateur complet ci-dessous).",
        ],
      };
    case "roe":
      return {
        title: `ROE — Rentabilité financière (${lastYr})`,
        formula: "(Résultat net / Capitaux propres moyens) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(f.avg(eq))}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", ni),
          f.stepPairM("Capitaux propres", eq),
          prevYr ? { label: `Actifs totaux (${lastYr})`, value: fmtM(f.assets.latest, ` M ${cur}`) } : null,
        ]),
        notes: [
          "Le référentiel Uncle Stock précise ROE = (Résultat net − Dividende préférentiel) / Common Book Value moyen (Capitaux propres − Actions préférentielles).",
        ],
      };
    case "roic": {
      const tr = f.tbl("tax_rate").latest;
      const nopat = opinc != null && tr != null ? opinc * (1 - tr / 100) : opinc;
      return {
        title: `ROIC (${lastYr})`,
        formula: "(NOPAT / Capital investi moyen) × 100",
        substitution: `(${fmtM(nopat)} / ${fmtM(f.avg(capInv))}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("EBIT / Résultat opé.", opinc),
          tr != null ? { label: `Taux d'IS effectif (${lastYr})`, value: fmtN(tr, 1, "%") } : null,
          f.stepM("NOPAT calculé", nopat),
          f.stepPairM("Capital investi (FP + Dette)", capInv),
          f.stepM("Capitaux propres", eq.latest),
          f.stepM("Dette totale", f.totDebt.latest),
        ]),
        notes: [
          "Convention IH : Capital investi = FP + Dette. La variante Uncle Stock (Actifs − NIBCL − Excess Cash') est calculée dans le référentiel complet ci-dessous.",
        ],
      };
    }
    case "croic":
      return {
        title: `CROIC — Cash Return on Invested Capital (${lastYr})`,
        formula: "(Free Cash Flow / Capital investi moyen) × 100",
        substitution: `(${fmtM(fcf)} / ${fmtM(f.avg(capInv))}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Free Cash Flow", fcf),
          f.stepM("Flux d'exploitation", ocf),
          f.stepM("Investissements (CapEx)", capex != null ? Math.abs(capex) : null),
          f.stepPairM("Capital investi (FP + Dette)", capInv),
        ]),
        notes: [
          "Convention IH : FCF / Capital investi moyen. La définition stricte Uncle Stock (Cash-NOPAT / Invested Capital moy.) est disponible dans l'explorateur complet ci-dessous.",
        ],
      };
    case "tax_rate":
      return {
        title: `Taux d'imposition effectif (${lastYr})`,
        formula: "(Charge d'impôts / Résultat avant impôts) × 100",
        substitution: `(${fmtM(f.tax.latest)} / ${fmtM(f.pretax.latest)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Charge d'impôts", f.tax.latest),
          f.stepM("Résultat avant impôts", f.pretax.latest),
          f.stepM("Résultat net", ni),
        ]),
      };
    case "cap_inv":
      return {
        title: `Capital investi (${lastYr})`,
        formula: "Capitaux propres + Dette financière totale",
        substitution: `${fmtM(eq.latest)} + ${fmtM(f.totDebt.latest)} = ${fmtM(val, ` M ${cur}`)}`,
        result: fmtM(val, ` M ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Capitaux propres", eq.latest),
          f.stepM("Dette financière totale", f.totDebt.latest),
          f.stepM("Trésorerie", f.cash.latest),
        ]),
        notes: [
          "Convention IH : Capitaux propres + Dette. Le Capital Investi Uncle Stock (Actifs − NIBCL − Excess Cash') figure dans le référentiel complet ci-dessous.",
        ],
      };
    case "ebitda_ps":
      return {
        title: `EBITDA par action (${lastYr})`,
        formula: "EBITDA / Actions en circulation",
        substitution: `${fmtM(ebitda)} / ${sh ? (sh / 1e6).toFixed(1) : "—"} M = ${fmtN(val, 2, ` ${cur}`)}`,
        result: fmtN(val, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("EBITDA", ebitda),
          sh != null ? { label: `Actions (${lastYr})`, value: `${(sh / 1e6).toFixed(1)} M` } : null,
        ]),
      };
    case "eps":
      return {
        title: `Bénéfice net par action (${lastYr})`,
        formula: "Résultat net / Actions diluées",
        substitution: `${fmtM(ni)} / ${sh ? (sh / 1e6).toFixed(1) : "—"} M = ${fmtN(val, 2, ` ${cur}`)}`,
        result: fmtN(val, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", ni),
          sh != null ? { label: `Actions diluées (${lastYr})`, value: `${(sh / 1e6).toFixed(1)} M` } : null,
        ]),
      };
    case "fcf_ps":
      return {
        title: `Free Cash Flow par action (${lastYr})`,
        formula: "Free Cash Flow / Actions en circulation",
        substitution: `${fmtM(fcf)} / ${sh ? (sh / 1e6).toFixed(1) : "—"} M = ${fmtN(val, 2, ` ${cur}`)}`,
        result: fmtN(val, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          f.stepM("Free Cash Flow", fcf),
          f.stepM("Flux d'exploitation", ocf),
          f.stepM("CapEx", capex != null ? Math.abs(capex) : null),
          sh != null ? { label: `Actions (${lastYr})`, value: `${(sh / 1e6).toFixed(1)} M` } : null,
        ]),
      };
    case "per":
      return {
        title: `PER fin d'exercice (${lastYr})`,
        formula: "Cours clôture exercice / BPA",
        substitution: `Cours(${lastYr}) / ${fmtN(eps, 2, ` ${cur}`)} = ${fmtN(val, 1, "×")}`,
        result: fmtN(val, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Capitalisation boursière", mcap),
          f.stepM("Résultat net", ni),
          eps != null ? { label: `BPA (${lastYr})`, value: fmtN(eps, 2, ` ${cur}`) } : null,
        ]),
      };
    case "pb":
      return {
        title: `Price-to-Book fin d'exercice (${lastYr})`,
        formula: "Capitalisation fin d'exercice / Capitaux propres",
        substitution: `${fmtM(mcap)} / ${fmtM(eq.latest)} = ${fmtN(val, 1, "×")}`,
        result: fmtN(val, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Capitalisation boursière", mcap),
          f.stepM("Capitaux propres", eq.latest),
        ]),
      };
    case "quick_r": {
      const cashQ = f.cashPure.latest ?? f.cash.latest;
      const usesReceivables = cashQ != null && f.rec.latest != null;
      return {
        title: `Liquidité restreinte (${lastYr})`,
        formula: usesReceivables
          ? "(Trésorerie & équivalents + Créances clients) / Passifs courants"
          : "(Actifs courants − Stocks) / Passifs courants",
        substitution: usesReceivables
          ? `(${fmtM(cashQ)} + ${fmtM(f.rec.latest)}) / ${fmtM(f.cl.latest)} = ${fmtN(val, 2, "×")}`
          : `(${fmtM(f.ca.latest)} − ${fmtM(f.inv.latest ?? 0)}) / ${fmtM(f.cl.latest)} = ${fmtN(val, 2, "×")}`,
        result: fmtN(val, 2, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Trésorerie & équivalents", f.cashPure.latest),
          f.stepM("Trésorerie & placements CT", f.cash.latest),
          f.stepM("Créances clients", f.rec.latest),
          f.stepM("Actifs courants", f.ca.latest),
          f.stepM("Stocks", f.inv.latest),
          f.stepM("Passifs courants", f.cl.latest),
        ]),
      };
    }
    case "curr_r":
      return {
        title: `Liquidité générale (${lastYr})`,
        formula: "Actifs courants / Passifs courants",
        substitution: `${fmtM(f.ca.latest)} / ${fmtM(f.cl.latest)} = ${fmtN(val, 2, "×")}`,
        result: fmtN(val, 2, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Actifs courants", f.ca.latest),
          f.stepM("Passifs courants", f.cl.latest),
        ]),
      };
    case "nd_ebitda":
      return {
        title: `Dette nette / EBITDA (${lastYr})`,
        formula: "(Dette totale − Trésorerie) / EBITDA",
        substitution: `${fmtM(netDebt)} / ${fmtM(ebitda)} = ${fmtN(val, 2, "×")}`,
        result: fmtN(val, 2, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Dette totale", f.totDebt.latest),
          f.stepM("Trésorerie & placements CT", f.cash.latest),
          f.stepM("Dette nette", netDebt),
          f.stepM("EBITDA", ebitda),
        ]),
      };
    case "debt_assets":
      return {
        title: `Dette / Actifs (${lastYr})`,
        formula: "(Dette totale / Actifs totaux) × 100",
        substitution: `(${fmtM(f.totDebt.latest)} / ${fmtM(f.assets.latest)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Dette totale", f.totDebt.latest),
          f.stepM("Total actifs", f.assets.latest),
        ]),
      };
    case "debt_eq":
      return {
        title: `Dette / Capitaux propres — Gearing (${lastYr})`,
        formula: "(Dette totale / Capitaux propres) × 100",
        substitution: `(${fmtM(f.totDebt.latest)} / ${fmtM(eq.latest)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Dette totale", f.totDebt.latest),
          f.stepM("Capitaux propres", eq.latest),
        ]),
      };
    case "cov_ebitda":
      return {
        title: `Couverture des intérêts par l'EBITDA (${lastYr})`,
        formula: "EBITDA / Charges d'intérêts",
        substitution: `${fmtM(ebitda)} / ${fmtM(intExp != null ? Math.abs(intExp) : null)} = ${fmtN(val, 1, "×")}`,
        result: fmtN(val, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("EBITDA", ebitda),
          f.stepM("Charges d'intérêts", intExp != null ? Math.abs(intExp) : null),
        ]),
      };
    case "cov_ebit":
      return {
        title: `Couverture des intérêts par l'EBIT (${lastYr})`,
        formula: "Résultat opérationnel / Charges d'intérêts",
        substitution: `${fmtM(opinc)} / ${fmtM(intExp != null ? Math.abs(intExp) : null)} = ${fmtN(val, 1, "×")}`,
        result: fmtN(val, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat opérationnel", opinc),
          f.stepM("Charges d'intérêts", intExp != null ? Math.abs(intExp) : null),
        ]),
      };
    case "cov_ocf":
      return {
        title: `Couverture par le flux opérationnel (${lastYr})`,
        formula: "Flux opérationnel / Charges d'intérêts",
        substitution: `${fmtM(ocf)} / ${fmtM(intExp != null ? Math.abs(intExp) : null)} = ${fmtN(val, 1, "×")}`,
        result: fmtN(val, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Flux d'exploitation", ocf),
          f.stepM("Charges d'intérêts", intExp != null ? Math.abs(intExp) : null),
        ]),
      };
    case "cost_debt":
      return {
        title: `Coût apparent de la dette (${lastYr})`,
        formula: "(Charges d'intérêts / Dette totale moyenne) × 100",
        substitution: `(${fmtM(intExp != null ? Math.abs(intExp) : null)} / ${fmtM(f.avg(f.totDebt))}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Charges d'intérêts", intExp != null ? Math.abs(intExp) : null),
          f.stepPairM("Dette totale", f.totDebt),
        ]),
      };
    case "payout_ni":
      return {
        title: `Payout Ratio sur résultat net (${lastYr})`,
        formula: "(Dividendes payés / Résultat net) × 100",
        substitution: `(${fmtM(divPaid != null ? Math.abs(divPaid) : null)} / ${fmtM(ni)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Dividendes payés", divPaid != null ? Math.abs(divPaid) : null),
          f.stepM("Résultat net", ni),
        ]),
      };
    case "payout_fcf":
      return {
        title: `Cash Payout sur FCF (${lastYr})`,
        formula: "(Dividendes payés / Free Cash Flow) × 100",
        substitution: `(${fmtM(divPaid != null ? Math.abs(divPaid) : null)} / ${fmtM(fcf)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Dividendes payés", divPaid != null ? Math.abs(divPaid) : null),
          f.stepM("Free Cash Flow", fcf),
        ]),
      };
    case "dsi":
      return {
        title: `Jours de stock — DSI (${lastYr})`,
        formula: "(Stocks moyens / Coût des ventes) × 365",
        substitution: `(${fmtM(f.avg(f.inv))} / ${fmtM(f.costRev.latest != null ? Math.abs(f.costRev.latest) : null)}) × 365 = ${fmtInt(val)} j`,
        result: val != null ? `${Math.round(val)} j` : "—",
        fundamentals: compactFundamentals([
          f.stepPairM("Stocks", f.inv),
          f.stepM("Coût des ventes", f.costRev.latest != null ? Math.abs(f.costRev.latest) : null),
        ]),
      };
    case "dso":
      return {
        title: `Délai clients — DSO (${lastYr})`,
        formula: "(Créances clients moyennes / Chiffre d'affaires) × 365",
        substitution: `(${fmtM(f.avg(f.rec))} / ${fmtM(rev)}) × 365 = ${fmtInt(val)} j`,
        result: val != null ? `${Math.round(val)} j` : "—",
        fundamentals: compactFundamentals([
          f.stepPairM("Créances clients", f.rec),
          f.stepM("Chiffre d'affaires", rev),
        ]),
      };
    case "dpo": {
      const costAbs = f.costRev.latest != null ? Math.abs(f.costRev.latest) : null;
      return {
        title: `Délai fournisseurs — DPO (${lastYr})`,
        formula: "(Dettes fournisseurs moyennes / Coût des ventes) × 365",
        substitution: `(${fmtM(f.avg(f.ap))} / ${fmtM(costAbs)}) × 365 = ${fmtInt(val)} j`,
        result: val != null ? `${Math.round(val)} j` : "—",
        fundamentals: compactFundamentals([
          f.stepPairM("Dettes fournisseurs", f.ap),
          f.stepM("Coût des ventes", costAbs),
        ]),
      };
    }
    case "ccc":
      return {
        title: `Cycle de conversion de l'encaisse — CCC (${lastYr})`,
        formula: "CCC = DSI + DSO − DPO (− Jours de produits constatés d'avance si applicable)",
        substitution: `${fmtInt(f.tbl("dsi").latest)} + ${fmtInt(f.tbl("dso").latest)} − ${fmtInt(f.tbl("dpo").latest)} = ${fmtInt(val)} j`,
        result: val != null ? `${Math.round(val)} j` : "—",
        fundamentals: compactFundamentals([
          f.stepPairM("Stocks", f.inv),
          f.stepPairM("Créances clients", f.rec),
          f.stepPairM("Dettes fournisseurs", f.ap),
          f.stepM("Chiffre d'affaires", rev),
          f.stepM("Coût des ventes", f.costRev.latest != null ? Math.abs(f.costRev.latest) : null),
        ]),
      };
    case "asset_turn":
      return {
        title: `Rotation des actifs (${lastYr})`,
        formula: "Chiffre d'affaires / Actifs totaux moyens",
        substitution: `${fmtM(rev)} / ${fmtM(f.avg(f.assets))} = ${fmtN(val, 2, "×")}`,
        result: fmtN(val, 2, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Chiffre d'affaires", rev),
          f.stepPairM("Total actifs", f.assets),
        ]),
      };
    case "sga_eq":
      return {
        title: `Frais généraux / Capitaux propres (${lastYr})`,
        formula: "(SG&A / Capitaux propres) × 100",
        substitution: `(${fmtM(f.sga.latest != null ? Math.abs(f.sga.latest) : null)} / ${fmtM(eq.latest)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Frais commerciaux & admin. (SG&A)", f.sga.latest != null ? Math.abs(f.sga.latest) : null),
          f.stepM("Capitaux propres", eq.latest),
        ]),
      };
    case "sga_rev":
      return {
        title: `Frais généraux / CA (${lastYr})`,
        formula: "(SG&A / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(f.sga.latest != null ? Math.abs(f.sga.latest) : null)} / ${fmtM(rev)}) × 100 = ${fmtN(val, 1, "%")}`,
        result: fmtN(val, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Frais commerciaux & admin. (SG&A)", f.sga.latest != null ? Math.abs(f.sga.latest) : null),
          f.stepM("Chiffre d'affaires", rev),
        ]),
      };
    default:
      return null;
  }
}

/** Détail chiffré des indicateurs TTM & Capital de l'action. */
export function buildCapitalMetricCalc(
  key:
    | "shares_outstanding"
    | "float_pct"
    | "insiders_pct"
    | "institutions_pct"
    | "short_ratio"
    | "short_pct_float"
    | "pe_ttm"
    | "pe_forward"
    | "peg"
    | "pb"
    | "ev_ebitda"
    | "ev_revenue"
    | "op_margin_ttm"
    | "net_margin_ttm"
    | "roe_ttm"
    | "roa_ttm"
    | "rev_growth_q_yoy"
    | "eps_growth_q_yoy"
    | "target_price"
    | "mma50"
    | "mma200",
  dossier: FinancialDossier,
): FinanceCalcDetail | null {
  const f = extractFundamentalSnapshot(dossier);
  const cap = f.cap;
  const hdr = f.hdr;
  const cur = f.cur;
  const netDebt = f.netDebt.latest ?? (f.totDebt.latest != null && f.cash.latest != null ? f.totDebt.latest - f.cash.latest : null);
  const evEst = hdr.market_cap != null && netDebt != null ? hdr.market_cap + netDebt : null;

  switch (key) {
    case "shares_outstanding":
      return {
        title: "Nombre d'actions en circulation",
        formula: "Actions ordinaires émises hors autodétention",
        result: fmtInt(cap.shares_outstanding),
        fundamentals: compactFundamentals([
          hdr.market_cap != null ? { label: "Capitalisation boursière", value: fmtM(hdr.market_cap, ` M ${cur}`) } : null,
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          f.shares.latest != null ? { label: `Actions bilan (${f.lastYr})`, value: `${(f.shares.latest / 1e6).toFixed(1)} M` } : null,
        ]),
      };
    case "float_pct": {
      const floatEst =
        cap.float_pct != null && cap.shares_outstanding != null
          ? (cap.float_pct / 100) * cap.shares_outstanding
          : null;
      return {
        title: "Part du flottant",
        formula: "(Actions flottantes / Actions totales) × 100",
        substitution: `(~${fmtInt(floatEst)} / ${fmtInt(cap.shares_outstanding)}) × 100 = ${fmtN(cap.float_pct, 1, "%")}`,
        result: fmtN(cap.float_pct, 1, "%"),
        fundamentals: compactFundamentals([
          cap.shares_outstanding != null ? { label: "Actions totales", value: fmtInt(cap.shares_outstanding) } : null,
          floatEst != null ? { label: "Actions flottantes estimées", value: fmtInt(floatEst) } : null,
        ]),
      };
    }
    case "pe_ttm":
      return {
        title: "PER TTM (Cours / BPA 12 mois)",
        formula: "Cours actuel / BPA TTM (ou Capitalisation / Résultat net)",
        substitution: `${fmtN(cap.price, 2, ` ${cur}`)} / BPA TTM = ${fmtN(cap.pe_ttm, 1, "×")}`,
        result: fmtN(cap.pe_ttm, 1, "×"),
        fundamentals: compactFundamentals([
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          f.stepM("Capitalisation boursière", hdr.market_cap),
          f.stepM("Résultat net", f.ni.latest),
          f.eps.latest != null ? { label: `BPA (${f.lastYr})`, value: fmtN(f.eps.latest, 2, ` ${cur}`) } : null,
        ]),
      };
    case "pe_forward":
      return {
        title: "PER prévisionnel (Forward P/E)",
        formula: "Cours actuel / BPA estimé sur les 12 prochains mois",
        result: fmtN(cap.pe_forward, 1, "×"),
        fundamentals: compactFundamentals([
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          f.eps.latest != null ? { label: `BPA historique (${f.lastYr})`, value: fmtN(f.eps.latest, 2, ` ${cur}`) } : null,
        ]),
      };
    case "peg":
      return {
        title: "Ratio PEG",
        formula: "PER / Taux de croissance annuel estimé du BPA (%)",
        result: fmtN(cap.peg, 2, "×"),
        fundamentals: compactFundamentals([
          cap.pe_ttm != null ? { label: "PER TTM", value: fmtN(cap.pe_ttm, 1, "×") } : null,
          cap.eps_growth_q_yoy != null ? { label: "Croissance BPA trim. YoY", value: fmtN(cap.eps_growth_q_yoy, 1, "%") } : null,
        ]),
      };
    case "ev_ebitda":
      return {
        title: "VE / EBITDA TTM",
        formula: "(Capitalisation + Dette nette) / EBITDA TTM",
        substitution: `${fmtM(evEst)} / ${fmtM(f.ebitda.latest)} = ${fmtN(cap.ev_ebitda, 1, "×")}`,
        result: fmtN(cap.ev_ebitda, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Capitalisation boursière", hdr.market_cap),
          f.stepM("Dette totale", f.totDebt.latest),
          f.stepM("Trésorerie & placements CT", f.cash.latest),
          f.stepM("Dette nette", netDebt),
          f.stepM("EBITDA", f.ebitda.latest),
        ]),
      };
    case "ev_revenue":
      return {
        title: "VE / Chiffre d'affaires TTM",
        formula: "(Capitalisation + Dette nette) / CA TTM",
        substitution: `${fmtM(evEst)} / ${fmtM(f.rev.latest)} = ${fmtN(cap.ev_revenue, 1, "×")}`,
        result: fmtN(cap.ev_revenue, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Capitalisation boursière", hdr.market_cap),
          f.stepM("Dette nette", netDebt),
          f.stepM("Chiffre d'affaires", f.rev.latest),
        ]),
      };
    case "pb":
      return {
        title: "Price-to-Book TTM",
        formula: "Capitalisation boursière / Capitaux propres",
        substitution: `${fmtM(hdr.market_cap)} / ${fmtM(f.eq.latest)} = ${fmtN(cap.pb, 1, "×")}`,
        result: fmtN(cap.pb, 1, "×"),
        fundamentals: compactFundamentals([
          f.stepM("Capitalisation boursière", hdr.market_cap),
          f.stepM("Capitaux propres", f.eq.latest),
        ]),
      };
    case "op_margin_ttm":
      return {
        title: "Marge opérationnelle TTM",
        formula: "(Résultat opérationnel TTM / Chiffre d'affaires TTM) × 100",
        result: fmtN(cap.op_margin_ttm, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat opérationnel", f.opinc.latest),
          f.stepM("Chiffre d'affaires", f.rev.latest),
        ]),
      };
    case "net_margin_ttm":
      return {
        title: "Marge nette TTM",
        formula: "(Résultat net TTM / Chiffre d'affaires TTM) × 100",
        result: fmtN(cap.net_margin_ttm, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", f.ni.latest),
          f.stepM("Chiffre d'affaires", f.rev.latest),
        ]),
      };
    case "roe_ttm":
      return {
        title: "ROE TTM",
        formula: "(Résultat net TTM / Capitaux propres) × 100",
        result: fmtN(cap.roe_ttm, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", f.ni.latest),
          f.stepPairM("Capitaux propres", f.eq),
        ]),
      };
    case "roa_ttm":
      return {
        title: "ROA TTM",
        formula: "(Résultat net TTM / Total actifs) × 100",
        result: fmtN(cap.roa_ttm, 1, "%"),
        fundamentals: compactFundamentals([
          f.stepM("Résultat net", f.ni.latest),
          f.stepPairM("Total actifs", f.assets),
        ]),
      };
    case "target_price": {
      const upside = cap.price && cap.target_price ? ((cap.target_price - cap.price) / cap.price) * 100 : null;
      return {
        title: "Objectif de cours du consensus",
        formula: "Moyenne des objectifs publiés · Potentiel = (Cible − Cours) / Cours",
        substitution:
          upside != null
            ? `(${fmtN(cap.target_price, 2)} − ${fmtN(cap.price, 2)}) / ${fmtN(cap.price, 2)} = ${upside >= 0 ? "+" : ""}${upside.toFixed(1)}%`
            : undefined,
        result: fmtN(cap.target_price, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          { label: "Analystes suivis", value: `${dossier.stakeholders.analysts.total}` },
        ]),
      };
    }
    case "mma50":
      return {
        title: "Moyenne mobile 50 séances (MMA50)",
        formula: "Moyenne arithmétique des 50 derniers cours de clôture",
        substitution:
          cap.price && cap.mma50
            ? `Cours ${fmtN(cap.price, 2)} vs MMA50 ${fmtN(cap.mma50, 2)} (${(((cap.price - cap.mma50) / cap.mma50) * 100).toFixed(1)}%)`
            : undefined,
        result: fmtN(cap.mma50, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          cap.low_52w != null && cap.high_52w != null
            ? { label: "Plus bas / Plus haut 52 sem.", value: `${fmtN(cap.low_52w, 2)} – ${fmtN(cap.high_52w, 2)} ${cur}` }
            : null,
        ]),
      };
    case "mma200":
      return {
        title: "Moyenne mobile 200 séances (MMA200)",
        formula: "Moyenne arithmétique des 200 derniers cours de clôture",
        substitution:
          cap.price && cap.mma200
            ? `Cours ${fmtN(cap.price, 2)} vs MMA200 ${fmtN(cap.mma200, 2)} (${(((cap.price - cap.mma200) / cap.mma200) * 100).toFixed(1)}%)`
            : undefined,
        result: fmtN(cap.mma200, 2, ` ${cur}`),
        fundamentals: compactFundamentals([
          cap.price != null ? { label: "Cours actuel", value: fmtN(cap.price, 2, ` ${cur}`) } : null,
          cap.mma50 != null ? { label: "MMA50", value: fmtN(cap.mma50, 2, ` ${cur}`) } : null,
        ]),
      };
    default:
      return null;
  }
}

/** Détail chiffré d'un ratio dans l'explorateur Fondamentaux (Historique). */
export function buildStatementRatioCalc(
  rowKey: string,
  rowLabel: string,
  latestVal: number | null,
  period: StatementPeriod,
  currency: string,
): FinanceCalcDetail | null {
  const s = (...k: string[]) => lastStmtPair(period, ...k).latest;
  const rev = s("TotalRevenue");
  const gp = s("GrossProfit");
  const opinc = s("OperatingIncome");
  const ni = s("NetIncome");
  const fcf = s("FreeCashFlow");
  const eq = s("StockholdersEquity");
  const assets = s("TotalAssets");
  const debt = s("TotalDebt");
  const cash = s("CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents");
  const netDebt = s("NetDebt") ?? (debt != null && cash != null ? debt - cash : null);
  const ebitda = s("EBITDA");
  const da = s("DepreciationAndAmortization");
  const ca = s("CurrentAssets");
  const cl = s("CurrentLiabilities");
  const ocf = s("OperatingCashFlow");
  const capex = s("CapitalExpenditure");
  const lastDate = period.dates[period.dates.length - 1]?.slice(0, 7) || "";

  const mStep = (lbl: string, v: number | null): MetricCalcStep | null =>
    v == null || !Number.isFinite(v) ? null : { label: `${lbl} (${lastDate})`, value: fmtM(v, ` M ${currency}`) };

  switch (rowKey) {
    case "GrossMarginPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Bénéfice brut / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(gp)} / ${fmtM(rev)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([mStep("Bénéfice brut", gp), mStep("Chiffre d'affaires", rev)]),
      };
    case "OperatingMarginPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Résultat opérationnel / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(opinc)} / ${fmtM(rev)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([mStep("Résultat opérationnel", opinc), mStep("Chiffre d'affaires", rev)]),
      };
    case "NetMarginPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Résultat net / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(rev)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([mStep("Résultat net", ni), mStep("Chiffre d'affaires", rev)]),
      };
    case "FCFMarginPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Free Cash Flow / Chiffre d'affaires) × 100",
        substitution: `(${fmtM(fcf)} / ${fmtM(rev)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([
          mStep("Flux d'exploitation", ocf),
          mStep("CapEx", capex != null ? Math.abs(capex) : null),
          mStep("Free Cash Flow", fcf),
          mStep("Chiffre d'affaires", rev),
        ]),
      };
    case "ROEPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Résultat net / Capitaux propres) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(eq)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([mStep("Résultat net", ni), mStep("Capitaux propres", eq)]),
      };
    case "ROAPct":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Résultat net / Actifs totaux) × 100",
        substitution: `(${fmtM(ni)} / ${fmtM(assets)}) × 100 = ${fmtN(latestVal, 1, "%")}`,
        result: fmtN(latestVal, 1, "%"),
        fundamentals: compactFundamentals([mStep("Résultat net", ni), mStep("Total actifs", assets)]),
      };
    case "DebtToEquity":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "Dette totale / Capitaux propres",
        substitution: `${fmtM(debt)} / ${fmtM(eq)} = ${fmtN(latestVal, 2, "×")}`,
        result: fmtN(latestVal, 2, "×"),
        fundamentals: compactFundamentals([mStep("Dette totale", debt), mStep("Capitaux propres", eq)]),
      };
    case "CurrentRatio":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "Actifs courants / Passifs courants",
        substitution: `${fmtM(ca)} / ${fmtM(cl)} = ${fmtN(latestVal, 2, "×")}`,
        result: fmtN(latestVal, 2, "×"),
        fundamentals: compactFundamentals([mStep("Actifs courants", ca), mStep("Passifs courants", cl)]),
      };
    case "NetDebtToEBITDA":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "(Dette totale − Trésorerie) / EBITDA",
        substitution: `${fmtM(netDebt)} / ${fmtM(ebitda)} = ${fmtN(latestVal, 2, "×")}`,
        result: fmtN(latestVal, 2, "×"),
        fundamentals: compactFundamentals([
          mStep("Dette totale", debt),
          mStep("Trésorerie & placements CT", cash),
          mStep("Dette nette", netDebt),
          mStep("EBITDA", ebitda),
        ]),
      };
    case "FreeCashFlow":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "Flux opérationnel − |CapEx|",
        substitution: `${fmtM(ocf)} − ${fmtM(capex != null ? Math.abs(capex) : null)} = ${fmtM(latestVal, ` M ${currency}`)}`,
        result: fmtM(latestVal, ` M ${currency}`),
        fundamentals: compactFundamentals([
          mStep("Flux d'exploitation", ocf),
          mStep("Investissements (CapEx)", capex != null ? Math.abs(capex) : null),
        ]),
      };
    case "NetDebt":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "Dette totale − Trésorerie et équivalents",
        substitution: `${fmtM(debt)} − ${fmtM(cash)} = ${fmtM(latestVal, ` M ${currency}`)}`,
        result: fmtM(latestVal, ` M ${currency}`),
        fundamentals: compactFundamentals([mStep("Dette totale", debt), mStep("Trésorerie & placements CT", cash)]),
      };
    case "EBITDA":
      return {
        title: `${rowLabel} (${lastDate})`,
        formula: "Résultat opérationnel + Amortissements & dépréciations",
        substitution:
          opinc != null && da != null
            ? `${fmtM(opinc)} + ${fmtM(Math.abs(da))} = ${fmtM(latestVal, ` M ${currency}`)}`
            : undefined,
        result: fmtM(latestVal, ` M ${currency}`),
        fundamentals: compactFundamentals([
          mStep("Résultat opérationnel", opinc),
          mStep("Amortissements & dépréciations", da != null ? Math.abs(da) : null),
        ]),
      };
    default:
      return null;
  }
}
