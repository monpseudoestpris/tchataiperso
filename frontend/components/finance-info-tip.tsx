"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { findFinanceTerm, type FinanceTermDefinition } from "@/lib/finance-glossary";

type TooltipCoords = {
  left: number;
  top: number;
  placement: "top" | "bottom";
};

function computeCoords(rect: DOMRect): TooltipCoords {
  const maxHalf = 180;
  const centerX = rect.left + rect.width / 2;
  const left = Math.max(maxHalf + 12, Math.min(window.innerWidth - maxHalf - 12, centerX));
  const preferTop = rect.top > 190;
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
 * Libellé d'indicateur accompagné d'une icône `?` : affiche la définition complète
 * en restant survolé, sur le `?`, au focus clavier ou au clic/tap (mobile).
 */
export function FinanceMetricLabel({
  termKey,
  label,
  definition,
  strong = false,
  delayMs = 160,
}: {
  termKey?: string;
  label: string;
  definition?: FinanceTermDefinition | null;
  strong?: boolean;
  delayMs?: number;
}) {
  const term = definition ?? findFinanceTerm(termKey) ?? findFinanceTerm(label);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const [pinned, setPinned] = useState(false);
  const tooltipId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => clearTimer, [clearTimer]);

  useEffect(() => {
    if (!pinned) return;
    const onDocDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setPinned(false);
        setCoords(null);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinned(false);
        setCoords(null);
      }
    };
    document.addEventListener("mousedown", onDocDown);
    window.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      window.removeEventListener("keydown", onEsc);
    };
  }, [pinned]);

  if (!term) {
    return strong ? <strong>{label}</strong> : <>{label}</>;
  }

  const openFromEl = () => {
    clearTimer();
    const el = wrapRef.current;
    if (el) setCoords(computeCoords(el.getBoundingClientRect()));
  };

  const scheduleOpen = (waitMs: number) => {
    clearTimer();
    if (waitMs <= 0) {
      openFromEl();
      return;
    }
    timerRef.current = window.setTimeout(openFromEl, waitMs);
  };

  const handleLeave = () => {
    clearTimer();
    if (!pinned) setCoords(null);
  };

  return (
    <span
      ref={wrapRef}
      className="finance-metric-tip-wrap"
      onMouseEnter={() => scheduleOpen(delayMs)}
      onMouseLeave={handleLeave}
    >
      {strong ? <strong>{label}</strong> : <span>{label}</span>}
      <span
        role="button"
        tabIndex={0}
        className={`finance-tip-badge${pinned ? " is-pinned" : ""}`}
        aria-label={`Définition : ${term.title}`}
        aria-describedby={coords ? tooltipId : undefined}
        onMouseEnter={() => scheduleOpen(0)}
        onFocus={openFromEl}
        onBlur={() => {
          if (!pinned) handleLeave();
        }}
        onClick={e => {
          e.stopPropagation();
          setPinned(prev => {
            const next = !prev;
            if (next) {
              openFromEl();
            } else {
              setCoords(null);
            }
            return next;
          });
        }}
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            setPinned(prev => {
              const next = !prev;
              if (next) openFromEl();
              else setCoords(null);
              return next;
            });
          }
        }}
      >
        ?
      </span>
      <FinanceTooltipPortal id={tooltipId} term={term} coords={coords} />
    </span>
  );
}
