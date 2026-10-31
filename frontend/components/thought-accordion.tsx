"use client";

import { useState, useEffect, useRef } from "react";
import { Brain, ChevronDown, ChevronUp, Sparkles } from "lucide-react";

interface ThoughtAccordionProps {
  thought: string;
  isStreaming?: boolean;
  defaultExpanded?: boolean;
}

export function ThoughtAccordion({
  thought,
  isStreaming = false,
  defaultExpanded,
}: ThoughtAccordionProps) {
  // Par défaut : déplié pendant le streaming en direct pour que l'utilisateur voie toute la réflexion,
  // ou replié si le message est déjà terminé.
  const [expanded, setExpanded] = useState<boolean>(() => {
    if (defaultExpanded !== undefined) return defaultExpanded;
    return isStreaming;
  });

  const contentRef = useRef<HTMLDivElement>(null);
  const wasStreamingRef = useRef<boolean>(isStreaming);

  // Si le streaming commence, on s'assure qu'il est ouvert pour voir la réflexion
  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      setExpanded(true);
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Défilement automatique vers le bas pendant la génération
  useEffect(() => {
    if (isStreaming && expanded && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [thought, isStreaming, expanded]);

  if (!thought || !thought.trim()) {
    return null;
  }

  const cleanThought = thought.trim();
  const wordCount = cleanThought.split(/\s+/).filter(Boolean).length;

  return (
    <div
      className={`thought-accordion ${isStreaming ? "is-streaming" : ""} ${expanded ? "is-expanded" : "is-collapsed"}`}
      role="region"
      aria-label="Processus de réflexion et raisonnement du modèle"
    >
      <button
        type="button"
        className="thought-accordion-header"
        onClick={() => setExpanded(prev => !prev)}
        aria-expanded={expanded}
        title={expanded ? "Réduire la réflexion" : "Déplier la réflexion détaillée"}
      >
        <span className="thought-accordion-icon" aria-hidden="true">
          {isStreaming ? (
            <Sparkles size={14} className="thought-sparkle-spin" />
          ) : (
            <Brain size={14} />
          )}
        </span>
        <span className="thought-accordion-title">
          {isStreaming ? (
            <span className="thought-live-title">
              <strong>Raisonnement en direct</strong>
              <span className="thought-pulse-dots" aria-hidden="true">
                <i /><i /><i />
              </span>
            </span>
          ) : (
            <span>
              <strong>Réflexion du modèle</strong> · {wordCount} mot{wordCount > 1 ? "s" : ""}
            </span>
          )}
        </span>
        <span className="thought-accordion-chevron" aria-hidden="true">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {expanded && (
        <div
          ref={contentRef}
          className="thought-accordion-body"
          tabIndex={0}
          role="document"
          aria-label="Texte intégral de la réflexion"
        >
          <pre className="thought-text-content">{cleanThought}</pre>
        </div>
      )}
    </div>
  );
}

