"use client";

import { Calculator, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { findFinanceTerm, type FinanceTermDefinition } from "@/lib/finance-glossary";

export type MetricCalcStep = {
  label: string;
  value: string;
  note?: string;
};

export type FinanceCalcDetail = {
  title: string;
  formula?: string;
  substitution?: string;
  result?: string;
  steps?: MetricCalcStep[];
  fundamentals?: MetricCalcStep[];
  notes?: string[];
  source?: string;
};

type TooltipCoords = {
  left: number;
  top: number;
  placement: "top" | "bottom";
};

function computeCoords(rect: DOMRect, halfWidth = 180, topThreshold = 190): TooltipCoords {
  const centerX = rect.left + rect.width / 2;
  const left = Math.max(halfWidth + 12, Math.min(window.innerWidth - halfWidth - 12, centerX));
  const preferTop = rect.top > topThreshold;
  return {
    left,
    top: preferTop ? rect.top - 10 : rect.bottom + 10,
    placement: preferTop ? "top" : "bottom",
  };
}

function FinanceTooltipPortal({
  id,
  term,
  coords,
}: {
  id: string;
  term: FinanceTermDefinition;
  coords: TooltipCoords | null;
}) {
  if (!coords || typeof document === "undefined") return null;

  return createPortal(
    <div
      id={id}
      role="tooltip"
      className={`finance-info-popover is-${coords.placement}`}
      style={{ left: `${coords.left}px`, top: `${coords.top}px` }}
    >
      <div className="finance-info-popover-title">{term.title}</div>
      <p className="finance-info-popover-summary">{term.summary}</p>
      {term.formula && (
        <div className="finance-info-popover-meta">
          <span>Formule :</span> <code>{term.formula}</code>
        </div>
      )}
      {term.interpretation && (
        <div className="finance-info-popover-interp">{term.interpretation}</div>
      )}
    </div>,
    document.body,
  );
}

function FinanceCalcPortal({
  id,
  detail,
  coords,
  pinned,
  portalRef,
  onClose,
}: {
  id: string;
  detail: FinanceCalcDetail;
  coords: TooltipCoords | null;
  pinned: boolean;
  portalRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
}) {
  if (!coords || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={portalRef}
      id={id}
      role={pinned ? "dialog" : "tooltip"}
      className={`finance-info-popover finance-calc-popover is-${coords.placement}${pinned ? " is-interactive" : ""}`}
      style={{ left: `${coords.left}px`, top: `${coords.top}px` }}
      onMouseDown={e => e.stopPropagation()}
    >
      <div className="finance-calc-popover-head">
        <div>
          <span className="finance-calc-popover-tag">Détail du calcul</span>
          <div className="finance-calc-popover-title">{detail.title}</div>
        </div>
        {pinned && (
          <button
            type="button"
            className="finance-calc-popover-close"
            onClick={onClose}
            aria-label="Fermer le détail du calcul"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {detail.formula && (
        <div className="finance-calc-popover-block">
          <span className="finance-calc-popover-kicker">Formule</span>
          <code className="finance-calc-popover-formula">{detail.formula}</code>
        </div>
      )}

      {detail.substitution && (
        <div className="finance-calc-popover-block">
          <span className="finance-calc-popover-kicker">Application chiffrée</span>
          <code className="finance-calc-popover-sub">{detail.substitution}</code>
        </div>
      )}

      {detail.steps && detail.steps.length > 0 && (
        <div className="finance-calc-popover-steps">
          {detail.steps.map((st, idx) => (
            <div key={`${st.label}-${idx}`} className="finance-calc-step-row">
              <div className="finance-calc-step-main">
                <span className="finance-calc-step-lbl">{st.label}</span>
                <strong className="finance-calc-step-val">{st.value}</strong>
              </div>
              {st.note && <div className="finance-calc-step-note">{st.note}</div>}
            </div>
          ))}
        </div>
      )}

      {detail.fundamentals && detail.fundamentals.length > 0 && (
        <div className="finance-calc-popover-fundamentals">
          <span className="finance-calc-popover-kicker">Valeurs fondamentales utilisées</span>
          <div className="finance-calc-popover-steps">
            {detail.fundamentals.map((f, idx) => (
              <div key={`${f.label}-${idx}`} className="finance-calc-step-row">
                <div className="finance-calc-step-main">
                  <span className="finance-calc-step-lbl">{f.label}</span>
                  <strong className="finance-calc-step-val">{f.value}</strong>
                </div>
                {f.note && <div className="finance-calc-step-note">{f.note}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {detail.result && (
        <div className="finance-calc-popover-result">
          <span>Résultat</span>
          <strong>{detail.result}</strong>
        </div>
      )}

      {detail.notes && detail.notes.length > 0 && (
        <ul className="finance-calc-popover-notes">
          {detail.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}

      {detail.source && <div className="finance-calc-popover-source">{detail.source}</div>}
    </div>,
    document.body,
  );
}

/**
 * Enveloppe un élément existant (ex. bouton d'indicateur technique) pour afficher
 * sa définition au repos du survol ou au focus clavier, sans modifier la mise en page.
 */
export function FinanceHoverTip({
  termKey,
  definition,
  delayMs = 220,
  children,
  className,
}: {
  termKey?: string;
  definition?: FinanceTermDefinition | null;
  delayMs?: number;
  children: ReactNode;
  className?: string;
}) {
  const term = definition ?? findFinanceTerm(termKey);
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const tooltipId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => clearTimer, [clearTimer]);

  if (!term) return <>{children}</>;

  const showNow = () => {
    clearTimer();
    const el = triggerRef.current;
    if (el) setCoords(computeCoords(el.getBoundingClientRect()));
  };

  const scheduleShow = () => {
    clearTimer();
    if (delayMs <= 0) {
      showNow();
      return;
    }
    timerRef.current = window.setTimeout(showNow, delayMs);
  };

  const hide = () => {
    clearTimer();
    setCoords(null);
  };

  return (
    <span
      ref={triggerRef}
      className={className ? `finance-hover-tip-wrap ${className}` : "finance-hover-tip-wrap"}
      aria-describedby={coords ? tooltipId : undefined}
      onMouseEnter={scheduleShow}
      onMouseLeave={hide}
      onFocus={scheduleShow}
      onBlur={hide}
    >
      {children}
      <FinanceTooltipPortal id={tooltipId} term={term} coords={coords} />
    </span>
  );
}

/**
 * Libellé d'indicateur accompagné d'une icône `?` (explication) et,
 * lorsque disponible, d'un bouton `fx` (détail chiffré du calcul réel).
 */
export function FinanceMetricLabel({
  termKey,
  label,
  definition,
  calcDetail,
  strong = false,
  delayMs = 160,
}: {
  termKey?: string;
  label: string;
  definition?: FinanceTermDefinition | null;
  calcDetail?: FinanceCalcDetail | null;
  strong?: boolean;
  delayMs?: number;
}) {
  const term = definition ?? findFinanceTerm(termKey) ?? findFinanceTerm(label);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const calcBtnRef = useRef<HTMLSpanElement | null>(null);
  const calcPortalRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const [activeMode, setActiveMode] = useState<"info" | "calc" | null>(null);
  const [pinnedMode, setPinnedMode] = useState<"info" | "calc" | null>(null);
  const tooltipId = useId();
  const calcId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => clearTimer, [clearTimer]);

  useEffect(() => {
    if (!pinnedMode) return;
    const onDocDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        wrapRef.current &&
        !wrapRef.current.contains(target) &&
        (!calcPortalRef.current || !calcPortalRef.current.contains(target))
      ) {
        setPinnedMode(null);
        setActiveMode(null);
        setCoords(null);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinnedMode(null);
        setActiveMode(null);
        setCoords(null);
      }
    };
    document.addEventListener("mousedown", onDocDown);
    window.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      window.removeEventListener("keydown", onEsc);
    };
  }, [pinnedMode]);

  if (!term && !calcDetail) {
    return strong ? <strong>{label}</strong> : <>{label}</>;
  }

  const openPanel = (mode: "info" | "calc") => {
    clearTimer();
    const anchorEl = mode === "calc" ? (calcBtnRef.current ?? wrapRef.current) : wrapRef.current;
    if (anchorEl) {
      setCoords(
        computeCoords(
          anchorEl.getBoundingClientRect(),
          mode === "calc" ? 260 : 180,
          mode === "calc" ? 270 : 190,
        ),
      );
      setActiveMode(mode);
    }
  };

  const scheduleInfo = (waitMs: number) => {
    if (pinnedMode) return;
    clearTimer();
    if (!term) return;
    if (waitMs <= 0) {
      openPanel("info");
      return;
    }
    timerRef.current = window.setTimeout(() => openPanel("info"), waitMs);
  };

  const handleLeave = () => {
    clearTimer();
    if (!pinnedMode) {
      setActiveMode(null);
      setCoords(null);
    }
  };

  const togglePin = (mode: "info" | "calc") => {
    setPinnedMode(prev => {
      const next = prev === mode ? null : mode;
      if (next) {
        openPanel(next);
      } else {
        setActiveMode(null);
        setCoords(null);
      }
      return next;
    });
  };

  return (
    <span
      ref={wrapRef}
      className="finance-metric-tip-wrap"
      onMouseEnter={() => scheduleInfo(delayMs)}
      onMouseLeave={handleLeave}
    >
      {strong ? <strong>{label}</strong> : <span>{label}</span>}

      {term && (
        <span
          role="button"
          tabIndex={0}
          className={`finance-tip-badge${pinnedMode === "info" ? " is-pinned" : ""}`}
          title={`Explication : ${term.title}`}
          aria-label={`Définition : ${term.title}`}
          aria-describedby={activeMode === "info" && coords ? tooltipId : undefined}
          onMouseEnter={e => {
            e.stopPropagation();
            if (!pinnedMode) scheduleInfo(0);
          }}
          onFocus={() => {
            if (!pinnedMode) openPanel("info");
          }}
          onBlur={() => {
            if (!pinnedMode) handleLeave();
          }}
          onClick={e => {
            e.stopPropagation();
            togglePin("info");
          }}
          onKeyDown={e => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              togglePin("info");
            }
          }}
        >
          ?
        </span>
      )}

      {calcDetail && (
        <span
          ref={calcBtnRef}
          role="button"
          tabIndex={0}
          className={`finance-calc-badge${pinnedMode === "calc" ? " is-pinned" : ""}`}
          title="Voir le détail chiffré du calcul"
          aria-label={`Détail du calcul : ${calcDetail.title}`}
          aria-describedby={activeMode === "calc" && coords ? calcId : undefined}
          onMouseEnter={e => {
            e.stopPropagation();
            if (!pinnedMode) openPanel("calc");
          }}
          onFocus={() => {
            if (!pinnedMode) openPanel("calc");
          }}
          onBlur={() => {
            if (!pinnedMode) handleLeave();
          }}
          onClick={e => {
            e.stopPropagation();
            togglePin("calc");
          }}
          onKeyDown={e => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              togglePin("calc");
            }
          }}
        >
          <Calculator size={10} />
        </span>
      )}

      {term && activeMode === "info" && (
        <FinanceTooltipPortal id={tooltipId} term={term} coords={coords} />
      )}
      {calcDetail && activeMode === "calc" && (
        <FinanceCalcPortal
          id={calcId}
          detail={calcDetail}
          coords={coords}
          pinned={pinnedMode === "calc"}
          portalRef={calcPortalRef}
          onClose={() => {
            setPinnedMode(null);
            setActiveMode(null);
            setCoords(null);
          }}
        />
      )}
    </span>
  );
}
