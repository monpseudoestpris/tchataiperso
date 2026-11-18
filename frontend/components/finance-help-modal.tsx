"use client";

import { BookOpen, ExternalLink, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { FinanceThemeSwitcher, useInterfaceTheme } from "@/components/finance-theme-switcher";

export type FinanceHelpGuideId = "intrinsic" | "scores" | "ratios";

const GUIDES: Record<FinanceHelpGuideId, { tabLabel: string; title: string; src: string }> = {
  intrinsic: {
    tabLabel: "Valeurs intrinsèques (20 chapitres)",
    title: "Guide de calcul — Valeurs intrinsèques (20 chapitres)",
    src: "/guides/intrinsic-values-guide.html",
  },
  scores: {
    tabLabel: "Scores Uncle Stock (36 chapitres)",
    title: "Guide détaillé — 31 Scores Uncle Stock (36 chapitres)",
    src: "/guides/uncle-stock-scores-guide.html",
  },
  ratios: {
    tabLabel: "Référentiel Ratios & Calculs (508)",
    title: "Référentiel complet — 508 métriques & calculs Uncle Stock",
    src: "/guides/uncle-stock-ratios-guide.html",
  },
};

type FinanceHelpModalProps = {
  isOpen: boolean;
  initialGuide?: FinanceHelpGuideId;
  onClose: () => void;
};

/** Fenêtre d'aide à onglets affichant les guides complets (Valeurs intrinsèques & Scores Uncle Stock). */
export function FinanceHelpModal({ isOpen, initialGuide = "intrinsic", onClose }: FinanceHelpModalProps) {
  const theme = useInterfaceTheme();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [tabState, setTabState] = useState<{ initial: FinanceHelpGuideId; current: FinanceHelpGuideId }>({
    initial: initialGuide,
    current: initialGuide,
  });

  const selectedGuide: FinanceHelpGuideId =
    !isOpen || tabState.initial !== initialGuide ? initialGuide : tabState.current;

  const syncIframeTheme = useCallback((mode: "light" | "dark") => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    doc.documentElement.dataset.theme = mode;
    doc.body?.classList.toggle("dark", mode === "dark");
    const toggleBtn = doc.getElementById("theme-toggle");
    if (toggleBtn) {
      toggleBtn.textContent = mode === "dark" ? "◐ \u00a0 Thème clair" : "◐ \u00a0 Thème sombre";
    }
    const darkBtn = doc.getElementById("dark");
    if (darkBtn) {
      darkBtn.textContent = mode === "dark" ? "☀ Mode clair" : "☾ Mode sombre";
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    syncIframeTheme(theme.mode);
  }, [isOpen, theme.mode, selectedGuide, syncIframeTheme]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const meta = GUIDES[selectedGuide];

  return (
    <div
      className="finance-submodal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={meta.title}
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="finance-help-submodal">
        <div className="finance-help-submodal-head">
          <div className="finance-help-submodal-title">
            <BookOpen size={17} />
            <strong>{meta.title}</strong>
          </div>
          <div className="finance-help-submodal-tabs" role="tablist" aria-label="Guides financiers">
            {(["intrinsic", "scores", "ratios"] as FinanceHelpGuideId[]).map(gid => (
              <button
                key={gid}
                type="button"
                role="tab"
                aria-selected={selectedGuide === gid}
                className={`finance-tf-btn ${selectedGuide === gid ? "active" : ""}`}
                onClick={() => setTabState({ initial: initialGuide, current: gid })}
              >
                {GUIDES[gid].tabLabel}
              </button>
            ))}
          </div>
          <div className="finance-help-submodal-actions">
            <FinanceThemeSwitcher compact />
            <a
              href={meta.src}
              target="_blank"
              rel="noopener noreferrer"
              className="finance-help-ext-link"
            >
              <span>Ouvrir dans un onglet</span>
              <ExternalLink size={13} />
            </a>
            <button
              type="button"
              className="finance-modal-close-btn"
              onClick={onClose}
              aria-label="Fermer le guide"
              title="Fermer (Échap)"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <iframe
          ref={iframeRef}
          key={meta.src}
          src={meta.src}
          title={meta.title}
          className="finance-help-iframe"
          onLoad={() => syncIframeTheme(theme.mode)}
        />
      </div>
    </div>
  );
}
