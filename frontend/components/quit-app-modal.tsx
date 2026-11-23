"use client";

import {
  CheckCircle2,
  CircleAlert,
  Database,
  LoaderCircle,
  Power,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  errorMessage,
  fetchShutdownStatus,
  prepareAppShutdown,
  resumeAppAfterShutdown,
  type PrepareShutdownResult,
  type ShutdownStatus,
} from "@/lib/api";

export function QuitAppModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<ShutdownStatus | null>(null);
  const [result, setResult] = useState<PrepareShutdownResult | null>(null);
  const [busy, setBusy] = useState<"idle" | "preparing" | "stopping" | "resuming">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchShutdownStatus()
      .then((data) => {
        if (cancelled) return;
        setStatus(data);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && busy === "idle") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onClose]);

  if (!open) return null;

  async function handlePrepare(stopProcess: boolean) {
    setBusy(stopProcess ? "stopping" : "preparing");
    setError("");
    try {
      const res = await prepareAppShutdown(stopProcess);
      setResult(res);
      setStatus((old) =>
        old
          ? {
              ...old,
              shutting_down: true,
              finance_sync_running: false,
              active_chat_streams: res.active_chat_streams_remaining,
            }
          : null,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("idle");
    }
  }

  async function handleResume() {
    setBusy("resuming");
    setError("");
    try {
      await resumeAppAfterShutdown();
      setResult(null);
      setStatus((old) => (old ? { ...old, shutting_down: false } : null));
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("idle");
    }
  }

  const isQuiesced = Boolean(result?.shutting_down || status?.shutting_down);
  const inDocker = Boolean(result?.running_in_docker ?? status?.running_in_docker);

  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget && busy === "idle") onClose();
      }}
    >
      <section
        className="modal"
        style={{ width: "min(94vw, 500px)", maxWidth: 500 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="quit-app-dialog-title"
      >
        <div className="modal-header">
          <span
            className="modal-icon"
            style={{
              background: isQuiesced ? "#dcfce7" : "#fef2f2",
              color: isQuiesced ? "#15803d" : "#dc2626",
            }}
          >
            {isQuiesced ? <ShieldCheck size={20} /> : <Power size={20} />}
          </span>
          <button
            type="button"
            className="icon-button"
            aria-label="Fermer"
            title="Fermer"
            disabled={busy !== "idle"}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        <h2 id="quit-app-dialog-title">
          {isQuiesced ? "Application prête à être fermée" : "Quitter proprement cLAIr"}
        </h2>

        {!isQuiesced ? (
          <>
            <p>
              Cette action gèle les nouvelles écritures, attend la fin des opérations en cours, arrête
              proprement les synchronisations Finance et vide les journaux SQLite (WAL) pour éviter toute
              corruption ou verrou de base de données.
            </p>
            {status && (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 12px",
                  borderRadius: 10,
                  background: "#f8fafc",
                  border: "1px solid #e2e8f0",
                  fontSize: 12,
                  color: "#334155",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>Streams de tchat actifs</span>
                  <strong>{status.active_chat_streams}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>Synchro Finance en arrière-plan</span>
                  <strong>{status.finance_sync_running ? "En cours (sera arrêtée proprement)" : "Inactive"}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>Base principale / Entrepôt Finance</span>
                  <strong>{status.main_db_dialect} + SQLite WAL</strong>
                </div>
              </div>
            )}
          </>
        ) : (
          <div
            style={{
              marginTop: 10,
              padding: "12px 14px",
              borderRadius: 12,
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              color: "#166534",
              fontSize: 12.5,
              lineHeight: 1.55,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700 }}>
              <CheckCircle2 size={16} />
              <span>Toutes les écritures sont terminées et les BDDs sont sauvegardées.</span>
            </div>
            <div>
              <Database size={13} style={{ display: "inline", marginRight: 6 }} />
              {result?.process_stopping
                ? "Le serveur local s'arrête proprement maintenant. Vous pouvez fermer cet onglet."
                : inDocker
                  ? "Les nouvelles écritures sont gelées. Vous pouvez fermer cet onglet et exécuter ./scripts/compose.sh down (ou arrêter Docker) sans risque."
                  : "Les nouvelles écritures sont gelées. Vous pouvez couper le serveur local ou fermer cet onglet sans risque."}
            </div>
          </div>
        )}

        {error && (
          <div className="url-error-msg" role="alert">
            <CircleAlert size={14} />
            <span>{error}</span>
          </div>
        )}

        <div className="modal-actions">
          {!isQuiesced ? (
            <>
              <button
                type="button"
                className="secondary-button"
                disabled={busy !== "idle"}
                onClick={onClose}
              >
                Annuler
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={busy !== "idle"}
                style={{ background: "linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)" }}
                onClick={() => void handlePrepare(false)}
              >
                {busy === "preparing" ? <LoaderCircle size={15} className="spin" /> : <Power size={15} />}
                <span>{busy === "preparing" ? "Sauvegarde des BDDs…" : "Préparer l’arrêt sûr"}</span>
              </button>
            </>
          ) : (
            <>
              {!result?.process_stopping && (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy !== "idle"}
                  onClick={() => void handleResume()}
                >
                  {busy === "resuming" ? <LoaderCircle size={14} className="spin" /> : <RotateCcw size={14} />}
                  <span>Reprendre l’appli</span>
                </button>
              )}
              {!inDocker && !result?.process_stopping && (
                <button
                  type="button"
                  className="primary-button"
                  disabled={busy !== "idle"}
                  style={{ background: "linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)" }}
                  onClick={() => void handlePrepare(true)}
                >
                  {busy === "stopping" ? <LoaderCircle size={14} className="spin" /> : <Power size={14} />}
                  <span>Couper le serveur local</span>
                </button>
              )}
              <button
                type="button"
                className="primary-button"
                disabled={busy !== "idle"}
                onClick={onClose}
              >
                Fermer
              </button>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
