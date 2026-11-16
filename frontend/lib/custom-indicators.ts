/**
 * Moteur d'évaluation sécurisé (parseur AST sans eval/new Function) pour indicateurs
 * techniques personnalisés inspirés de TradingView / Pine Script.
 */

import type { EodBar } from "@/lib/api";
import {
  adx,
  atr,
  bollinger,
  cci,
  ema,
  macd,
  obv,
  parabolicSar,
  roc,
  rsi,
  sma,
  stochastic,
  vwap,
  williamsR,
  type Num,
} from "@/lib/indicators";

export type CustomIndicatorPreset = {
  id: string;
  label: string;
  name: string;
  formula: string;
  pane: "overlay" | "oscillator";
  series_type: "line" | "histogram" | "dots";
  color: string;
  guide_lines: { value: number; color: string }[];
  description: string;
};

export const CUSTOM_INDICATOR_PRESETS: CustomIndicatorPreset[] = [
  {
    id: "ema9",
    label: "EMA 9",
    name: "EMA 9",
    formula: "ema(close, 9)",
    pane: "overlay",
    series_type: "line",
    color: "#0ea5e9",
    guide_lines: [],
    description: "Moyenne mobile exponentielle courte à 9 périodes",
  },
  {
    id: "smoothed_rsi",
    label: "RSI lissé (EMA 9)",
    name: "EMA(RSI 14, 9)",
    formula: "ema(rsi(close, 14), 9)",
    pane: "oscillator",
    series_type: "line",
    color: "#10b981",
    guide_lines: [
      { value: 70, color: "#f43f5e" },
      { value: 30, color: "#10b981" },
    ],
    description: "Lissage exponentiel (EMA 9) du RSI 14 pour filtrer le bruit",
  },
  {
    id: "keltner_upper",
    label: "Keltner Sup (20, 2)",
    name: "Keltner Sup",
    formula: "ema(close, 20) + 2 * atr(14)",
    pane: "overlay",
    series_type: "line",
    color: "#8b5cf6",
    guide_lines: [],
    description: "Bande haute du canal de Keltner (EMA 20 + 2×ATR 14)",
  },
  {
    id: "dist_sma50",
    label: "Écart SMA 50 (%)",
    name: "Écart SMA 50 (%)",
    formula: "((close - sma(close, 50)) / sma(close, 50)) * 100",
    pane: "oscillator",
    series_type: "histogram",
    color: "#10b981",
    guide_lines: [{ value: 0, color: "#94a3b8" }],
    description: "Distance en pourcentage entre le cours et sa SMA 50",
  },
  {
    id: "rsi_smoothed",
    label: "RSI Lissé (14, 5)",
    name: "RSI Lissé",
    formula: "ema(rsi(close, 14), 5)",
    pane: "oscillator",
    series_type: "line",
    color: "#f59e0b",
    guide_lines: [
      { value: 70, color: "#f43f5e" },
      { value: 30, color: "#10b981" },
    ],
    description: "RSI 14 lissé par une EMA 5 pour filtrer le bruit",
  },
  {
    id: "ema_spread",
    label: "Momentum EMA (12-26)",
    name: "Spread EMA 12/26",
    formula: "ema(close, 12) - ema(close, 26)",
    pane: "oscillator",
    series_type: "histogram",
    color: "#3b82f6",
    guide_lines: [{ value: 0, color: "#94a3b8" }],
    description: "Écart brut entre EMA rapide (12) et EMA lente (26)",
  },
  {
    id: "boll_pct",
    label: "%B Bollinger",
    name: "%B Bollinger",
    formula: "(close - boll_lower(close, 20, 2)) / (boll_upper(close, 20, 2) - boll_lower(close, 20, 2)) * 100",
    pane: "oscillator",
    series_type: "line",
    color: "#ec4899",
    guide_lines: [
      { value: 100, color: "#f43f5e" },
      { value: 50, color: "#94a3b8" },
      { value: 0, color: "#10b981" },
    ],
    description: "Position relative du cours dans les bandes de Bollinger (0 à 100 %)",
  },
];

type TokenType = "num" | "ident" | "op" | "lparen" | "rparen" | "lbracket" | "rbracket" | "comma";
type Token = { type: TokenType; value: string; pos: number };

const TWO_CHAR_OPS = new Set([">=", "<=", "==", "!=", "&&", "||"]);
const ONE_CHAR_OPS = new Set(["+", "-", "*", "/", "%", ">", "<", "!"]);

function tokenize(input: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (/\s/.test(ch)) {
      i++;
      continue;
    }
    if (/[0-9]/.test(ch) || (ch === "." && i + 1 < input.length && /[0-9]/.test(input[i + 1]))) {
      const start = i;
      let dotSeen = false;
      while (i < input.length && (/[0-9]/.test(input[i]) || (input[i] === "." && !dotSeen))) {
        if (input[i] === ".") dotSeen = true;
        i++;
      }
      tokens.push({ type: "num", value: input.slice(start, i), pos: start });
      continue;
    }
    if (/[a-zA-Z_]/.test(ch)) {
      const start = i;
      while (i < input.length && /[a-zA-Z0-9_]/.test(input[i])) {
        i++;
      }
      const ident = input.slice(start, i);
      const lower = ident.toLowerCase();
      if (lower === "and") {
        tokens.push({ type: "op", value: "&&", pos: start });
      } else if (lower === "or") {
        tokens.push({ type: "op", value: "||", pos: start });
      } else if (lower === "not") {
        tokens.push({ type: "op", value: "!", pos: start });
      } else {
        tokens.push({ type: "ident", value: lower, pos: start });
      }
      continue;
    }
    const pair = input.slice(i, i + 2);
    if (TWO_CHAR_OPS.has(pair)) {
      tokens.push({ type: "op", value: pair, pos: i });
      i += 2;
      continue;
    }
    if (ONE_CHAR_OPS.has(ch)) {
      tokens.push({ type: "op", value: ch, pos: i });
      i++;
      continue;
    }
    if (ch === "(") {
      tokens.push({ type: "lparen", value: ch, pos: i });
      i++;
      continue;
    }
    if (ch === ")") {
      tokens.push({ type: "rparen", value: ch, pos: i });
      i++;
      continue;
    }
    if (ch === "[") {
      tokens.push({ type: "lbracket", value: ch, pos: i });
      i++;
      continue;
    }
    if (ch === "]") {
      tokens.push({ type: "rbracket", value: ch, pos: i });
      i++;
      continue;
    }
    if (ch === ",") {
      tokens.push({ type: "comma", value: ch, pos: i });
      i++;
      continue;
    }
    throw new Error(`Caractère inattendu « ${ch} » à la position ${i + 1}.`);
  }
  return tokens;
}

type AstNode =
  | { kind: "number"; value: number }
  | { kind: "ident"; name: string }
  | { kind: "call"; name: string; args: AstNode[] }
  | { kind: "index"; target: AstNode; offset: AstNode }
  | { kind: "unary"; op: "+" | "-" | "!"; expr: AstNode }
  | { kind: "binary"; op: string; left: AstNode; right: AstNode };

class Parser {
  private pos = 0;
  constructor(private readonly tokens: Token[]) {}

  private peek(): Token | undefined {
    return this.tokens[this.pos];
  }

  private next(): Token {
    const t = this.tokens[this.pos];
    if (!t) throw new Error("Expression incomplète.");
    this.pos++;
    return t;
  }

  parse(): AstNode {
    if (this.tokens.length === 0) {
      throw new Error("La formule est vide.");
    }
    const expr = this.parseOr();
    if (this.pos < this.tokens.length) {
      const tok = this.tokens[this.pos];
      throw new Error(`Jeton inattendu « ${tok.value} » à la position ${tok.pos + 1}.`);
    }
    return expr;
  }

  private parseOr(): AstNode {
    let node = this.parseAnd();
    while (this.peek()?.type === "op" && this.peek()?.value === "||") {
      this.next();
      node = { kind: "binary", op: "||", left: node, right: this.parseAnd() };
    }
    return node;
  }

  private parseAnd(): AstNode {
    let node = this.parseComparison();
    while (this.peek()?.type === "op" && this.peek()?.value === "&&") {
      this.next();
      node = { kind: "binary", op: "&&", left: node, right: this.parseComparison() };
    }
    return node;
  }

  private parseComparison(): AstNode {
    let node = this.parseAdditive();
    while (
      this.peek()?.type === "op" &&
      ["<", "<=", ">", ">=", "==", "!="].includes(this.peek()!.value)
    ) {
      const op = this.next().value;
      node = { kind: "binary", op, left: node, right: this.parseAdditive() };
    }
    return node;
  }

  private parseAdditive(): AstNode {
    let node = this.parseMultiplicative();
    while (this.peek()?.type === "op" && (this.peek()?.value === "+" || this.peek()?.value === "-")) {
      const op = this.next().value;
      node = { kind: "binary", op, left: node, right: this.parseMultiplicative() };
    }
    return node;
  }

  private parseMultiplicative(): AstNode {
    let node = this.parseUnary();
    while (
      this.peek()?.type === "op" &&
      (this.peek()?.value === "*" || this.peek()?.value === "/" || this.peek()?.value === "%")
    ) {
      const op = this.next().value;
      node = { kind: "binary", op, left: node, right: this.parseUnary() };
    }
    return node;
  }

  private parseUnary(): AstNode {
    const tok = this.peek();
    if (tok?.type === "op" && (tok.value === "+" || tok.value === "-" || tok.value === "!")) {
      this.next();
      return { kind: "unary", op: tok.value, expr: this.parseUnary() };
    }
    return this.parsePostfix();
  }

  private parsePostfix(): AstNode {
    let node = this.parsePrimary();
    while (this.peek()?.type === "lbracket") {
      this.next();
      const offset = this.parseOr();
      const close = this.peek();
      if (close?.type !== "rbracket") {
        throw new Error("Crochet fermant « ] » attendu.");
      }
      this.next();
      node = { kind: "index", target: node, offset };
    }
    return node;
  }

  private parsePrimary(): AstNode {
    const tok = this.next();
    if (tok.type === "num") {
      const val = Number(tok.value);
      if (!Number.isFinite(val)) throw new Error(`Nombre invalide « ${tok.value} ».`);
      return { kind: "number", value: val };
    }
    if (tok.type === "ident") {
      if (this.peek()?.type === "lparen") {
        this.next();
        const args: AstNode[] = [];
        if (this.peek()?.type !== "rparen") {
          while (true) {
            args.push(this.parseOr());
            if (this.peek()?.type === "comma") {
              this.next();
              continue;
            }
            break;
          }
        }
        if (this.peek()?.type !== "rparen") {
          throw new Error(`Parenthèse fermante « ) » attendue pour ${tok.value}().`);
        }
        this.next();
        return { kind: "call", name: tok.value.toLowerCase(), args };
      }
      return { kind: "ident", name: tok.value.toLowerCase() };
    }
    if (tok.type === "lparen") {
      const inner = this.parseOr();
      if (this.peek()?.type !== "rparen") {
        throw new Error("Parenthèse fermante « ) » attendue.");
      }
      this.next();
      return inner;
    }
    throw new Error(`Expression inattendue près de « ${tok.value} ».`);
  }
}

/** Applique une fonction d'indicateur sur une série contenant potentiellement des `null` initiaux. */
function mapValidTail(series: Num[], calc: (valid: number[]) => Num[]): Num[] {
  const out: Num[] = new Array(series.length).fill(null);
  const firstValid = series.findIndex(v => v != null && Number.isFinite(v));
  if (firstValid === -1) return out;

  // Remplit les trous internes éventuels par propagation avant sur le tronçon utile
  const tail: number[] = [];
  let last = series[firstValid] as number;
  for (let i = firstValid; i < series.length; i++) {
    const v = series[i];
    if (v != null && Number.isFinite(v)) {
      last = v;
    }
    tail.push(last);
  }
  const computed = calc(tail);
  for (let i = 0; i < computed.length; i++) {
    out[firstValid + i] = computed[i];
  }
  return out;
}

function constantSeries(len: number, val: number): Num[] {
  return new Array(len).fill(Number.isFinite(val) ? val : null);
}

function asInteger(node: AstNode | undefined, fallback: number, min = 1, max = 500): number {
  if (!node) return fallback;
  if (node.kind === "number") {
    return Math.min(max, Math.max(min, Math.round(node.value)));
  }
  if (node.kind === "unary" && node.op === "-" && node.expr.kind === "number") {
    return Math.min(max, Math.max(min, Math.round(-node.expr.value)));
  }
  throw new Error("La période doit être un nombre constant (ex. 14, 20).");
}

function asNumber(node: AstNode | undefined, fallback: number): number {
  if (!node) return fallback;
  if (node.kind === "number") return node.value;
  if (node.kind === "unary" && node.op === "-" && node.expr.kind === "number") {
    return -node.expr.value;
  }
  throw new Error("Ce paramètre doit être un nombre constant.");
}

function shiftSeries(series: Num[], offset: number): Num[] {
  const n = series.length;
  if (offset <= 0) return [...series];
  const out: Num[] = new Array(n).fill(null);
  for (let i = offset; i < n; i++) {
    out[i] = series[i - offset];
  }
  return out;
}

function rollingWindow(series: Num[], period: number, reducer: (win: number[]) => number | null): Num[] {
  const out: Num[] = new Array(series.length).fill(null);
  for (let i = period - 1; i < series.length; i++) {
    const win: number[] = [];
    let ok = true;
    for (let j = i - period + 1; j <= i; j++) {
      const v = series[j];
      if (v == null || !Number.isFinite(v)) {
        ok = false;
        break;
      }
      win.push(v);
    }
    if (ok) out[i] = reducer(win);
  }
  return out;
}

function wmaSeries(series: Num[], period: number): Num[] {
  const denom = (period * (period + 1)) / 2;
  return rollingWindow(series, period, win => {
    let sum = 0;
    for (let i = 0; i < win.length; i++) sum += win[i] * (i + 1);
    return sum / denom;
  });
}

function rmaSeries(series: Num[], period: number): Num[] {
  return mapValidTail(series, vals => {
    const out: Num[] = new Array(vals.length).fill(null);
    if (vals.length < period) return out;
    let sum = 0;
    for (let i = 0; i < period; i++) sum += vals[i];
    let prev = sum / period;
    out[period - 1] = prev;
    const alpha = 1 / period;
    for (let i = period; i < vals.length; i++) {
      prev = alpha * vals[i] + (1 - alpha) * prev;
      out[i] = prev;
    }
    return out;
  });
}

function stdevSeries(series: Num[], period: number): Num[] {
  return rollingWindow(series, period, win => {
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    const variance = win.reduce((a, b) => a + (b - mean) ** 2, 0) / win.length;
    return Math.sqrt(variance);
  });
}

export function evaluateCustomIndicator(formula: string, bars: EodBar[]): Num[] {
  const tokens = tokenize(formula);
  const ast = new Parser(tokens).parse();

  const rows = bars.filter(b => b.close != null && b.open != null && b.high != null && b.low != null);
  const n = rows.length;
  if (n === 0) return [];

  const opens = rows.map(b => b.open as number);
  const highs = rows.map(b => b.high as number);
  const lows = rows.map(b => b.low as number);
  const closes = rows.map(b => b.close as number);
  const volumes = rows.map(b => b.volume ?? 0);
  const sessionKeys = rows.map(b => b.date.slice(0, 10));

  const sources: Record<string, Num[]> = {
    open: opens,
    high: highs,
    low: lows,
    close: closes,
    volume: volumes,
    hl2: highs.map((h, i) => (h + lows[i]) / 2),
    hlc3: highs.map((h, i) => (h + lows[i] + closes[i]) / 3),
    typical: highs.map((h, i) => (h + lows[i] + closes[i]) / 3),
    ohlc4: opens.map((o, i) => (o + highs[i] + lows[i] + closes[i]) / 4),
    pi: constantSeries(n, Math.PI),
    true: constantSeries(n, 1),
    false: constantSeries(n, 0),
  };

  function evalNode(node: AstNode): Num[] {
    switch (node.kind) {
      case "number":
        return constantSeries(n, node.value);
      case "ident": {
        const s = sources[node.name];
        if (!s) {
          throw new Error(
            `Série inconnue « ${node.name} ». Utilisez close, open, high, low, volume, hl2, hlc3 ou ohlc4.`,
          );
        }
        return s;
      }
      case "index": {
        const target = evalNode(node.target);
        const offset = asInteger(node.offset, 1, 0, 500);
        return shiftSeries(target, offset);
      }
      case "unary": {
        const inner = evalNode(node.expr);
        if (node.op === "+") return inner;
        if (node.op === "-") return inner.map(v => (v == null ? null : -v));
        return inner.map(v => (v == null ? null : v === 0 ? 1 : 0));
      }
      case "binary": {
        const left = evalNode(node.left);
        const right = evalNode(node.right);
        return left.map((a, i) => {
          const b = right[i];
          if (a == null || b == null) return null;
          switch (node.op) {
            case "+":
              return a + b;
            case "-":
              return a - b;
            case "*":
              return a * b;
            case "/":
              return b === 0 ? null : a / b;
            case "%":
              return b === 0 ? null : a % b;
            case ">":
              return a > b ? 1 : 0;
            case ">=":
              return a >= b ? 1 : 0;
            case "<":
              return a < b ? 1 : 0;
            case "<=":
              return a <= b ? 1 : 0;
            case "==":
              return a === b ? 1 : 0;
            case "!=":
              return a !== b ? 1 : 0;
            case "&&":
              return a !== 0 && b !== 0 ? 1 : 0;
            case "||":
              return a !== 0 || b !== 0 ? 1 : 0;
            default:
              return null;
          }
        });
      }
      case "call": {
        const args = node.args;
        const srcOrClose = (idx: number): Num[] => (args[idx] ? evalNode(args[idx]) : closes);
        switch (node.name) {
          case "sma": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            return mapValidTail(src, vals => sma(vals, period));
          }
          case "ema": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            return mapValidTail(src, vals => ema(vals, period));
          }
          case "wma": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            return wmaSeries(src, period);
          }
          case "rma":
          case "smma": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 14);
            return rmaSeries(src, period);
          }
          case "rsi": {
            const hasTwo = args.length >= 2;
            const src = hasTwo ? evalNode(args[0]) : args.length === 1 && args[0].kind !== "number" ? evalNode(args[0]) : closes;
            const period = hasTwo ? asInteger(args[1], 14) : args[0]?.kind === "number" ? asInteger(args[0], 14) : 14;
            return mapValidTail(src, vals => rsi(vals, period));
          }
          case "roc": {
            const hasTwo = args.length >= 2;
            const src = hasTwo ? evalNode(args[0]) : closes;
            const period = hasTwo ? asInteger(args[1], 12) : asInteger(args[0], 12);
            return mapValidTail(src, vals => roc(vals, period));
          }
          case "atr":
            return atr(highs, lows, closes, asInteger(args[0], 14));
          case "cci":
            return cci(highs, lows, closes, asInteger(args[0], 20));
          case "willr":
          case "williamsr":
            return williamsR(highs, lows, closes, asInteger(args[0], 14));
          case "adx":
            return adx(highs, lows, closes, asInteger(args[0], 14)).adx;
          case "plus_di":
          case "pdi":
            return adx(highs, lows, closes, asInteger(args[0], 14)).plusDi;
          case "minus_di":
          case "mdi":
            return adx(highs, lows, closes, asInteger(args[0], 14)).minusDi;
          case "obv":
            return obv(closes, volumes);
          case "vwap":
            return vwap(highs, lows, closes, volumes, sessionKeys);
          case "sar":
            return parabolicSar(highs, lows, asNumber(args[0], 0.02), asNumber(args[1], 0.2));
          case "boll_upper":
          case "bb_upper": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            const mult = asNumber(args[2], 2);
            return mapValidTail(src, vals => bollinger(vals, period, mult).upper);
          }
          case "boll_mid":
          case "bb_mid": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            const mult = asNumber(args[2], 2);
            return mapValidTail(src, vals => bollinger(vals, period, mult).mid);
          }
          case "boll_lower":
          case "bb_lower": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            const mult = asNumber(args[2], 2);
            return mapValidTail(src, vals => bollinger(vals, period, mult).lower);
          }
          case "boll_width":
          case "bb_width": {
            const src = srcOrClose(0);
            const period = asInteger(args[1], 20);
            const mult = asNumber(args[2], 2);
            return mapValidTail(src, vals => {
              const b = bollinger(vals, period, mult);
              return b.mid.map((m, i) =>
                m != null && m !== 0 && b.upper[i] != null && b.lower[i] != null
                  ? ((b.upper[i]! - b.lower[i]!) / m) * 100
                  : null,
              );
            });
          }
          case "macd":
          case "macd_line": {
            const src = srcOrClose(0);
            const fast = asInteger(args[1], 12);
            const slow = asInteger(args[2], 26);
            const sig = asInteger(args[3], 9);
            return mapValidTail(src, vals => macd(vals, fast, slow, sig).line);
          }
          case "macd_signal": {
            const src = srcOrClose(0);
            const fast = asInteger(args[1], 12);
            const slow = asInteger(args[2], 26);
            const sig = asInteger(args[3], 9);
            return mapValidTail(src, vals => macd(vals, fast, slow, sig).signal);
          }
          case "macd_hist": {
            const src = srcOrClose(0);
            const fast = asInteger(args[1], 12);
            const slow = asInteger(args[2], 26);
            const sig = asInteger(args[3], 9);
            return mapValidTail(src, vals => macd(vals, fast, slow, sig).hist);
          }
          case "stoch_k":
            return stochastic(highs, lows, closes, asInteger(args[0], 14), asInteger(args[1], 3)).k;
          case "stoch_d":
            return stochastic(highs, lows, closes, asInteger(args[0], 14), asInteger(args[1], 3)).d;
          case "stdev": {
            const src = srcOrClose(0);
            return stdevSeries(src, asInteger(args[1], 20));
          }
          case "highest": {
            const src = srcOrClose(0);
            return rollingWindow(src, asInteger(args[1], 20), win => Math.max(...win));
          }
          case "lowest": {
            const src = srcOrClose(0);
            return rollingWindow(src, asInteger(args[1], 20), win => Math.min(...win));
          }
          case "shift": {
            const src = srcOrClose(0);
            return shiftSeries(src, asInteger(args[1], 1, 0, 500));
          }
          case "change": {
            const src = srcOrClose(0);
            const offset = asInteger(args[1], 1, 1, 500);
            const prev = shiftSeries(src, offset);
            return src.map((v, i) => (v == null || prev[i] == null ? null : v - prev[i]!));
          }
          case "pct_change": {
            const src = srcOrClose(0);
            const offset = asInteger(args[1], 1, 1, 500);
            const prev = shiftSeries(src, offset);
            return src.map((v, i) =>
              v == null || prev[i] == null || prev[i] === 0 ? null : ((v - prev[i]!) / prev[i]!) * 100,
            );
          }
          case "abs":
            return srcOrClose(0).map(v => (v == null ? null : Math.abs(v)));
          case "sqrt":
            return srcOrClose(0).map(v => (v == null || v < 0 ? null : Math.sqrt(v)));
          case "log":
            return srcOrClose(0).map(v => (v == null || v <= 0 ? null : Math.log(v)));
          case "max": {
            const a = evalNode(args[0] ?? { kind: "number", value: 0 });
            const b = evalNode(args[1] ?? { kind: "number", value: 0 });
            return a.map((va, i) => (va == null || b[i] == null ? null : Math.max(va, b[i]!)));
          }
          case "min": {
            const a = evalNode(args[0] ?? { kind: "number", value: 0 });
            const b = evalNode(args[1] ?? { kind: "number", value: 0 });
            return a.map((va, i) => (va == null || b[i] == null ? null : Math.min(va, b[i]!)));
          }
          case "nz": {
            const a = srcOrClose(0);
            const fallback = asNumber(args[1], 0);
            return a.map(v => (v == null || !Number.isFinite(v) ? fallback : v));
          }
          case "iff": {
            if (args.length < 3) throw new Error("iff(condition, si_vrai, si_faux) attend 3 arguments.");
            const cond = evalNode(args[0]);
            const tVal = evalNode(args[1]);
            const fVal = evalNode(args[2]);
            return cond.map((c, i) => (c == null ? null : c !== 0 ? tVal[i] : fVal[i]));
          }
          default:
            throw new Error(`Fonction inconnue « ${node.name}() ».`);
        }
      }
    }
  }

  return evalNode(ast);
}

export function validateCustomFormula(
  formula: string,
  bars: EodBar[] = [],
): { ok: true; lastValues: number[] } | { ok: false; error: string } {
  try {
    const sampleBars: EodBar[] =
      bars.length >= 2
        ? bars
        : Array.from({ length: 60 }, (_, idx) => ({
            date: `2026-01-${String((idx % 28) + 1).padStart(2, "0")}`,
            open: 100 + idx * 0.4,
            high: 101.5 + idx * 0.4,
            low: 99 + idx * 0.4,
            close: 100.5 + idx * 0.4,
            volume: 100000 + idx * 1000,
          }));
    const series = evaluateCustomIndicator(formula, sampleBars);
    const finite = series.filter((v): v is number => v != null && Number.isFinite(v));
    return { ok: true, lastValues: finite.slice(-3) };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Formule invalide.",
    };
  }
}
