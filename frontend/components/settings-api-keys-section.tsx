"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Cloud,
  Cpu,
  Eye,
  EyeOff,
  FileText,
  Globe,
  ImagePlus,
  KeyRound,
  LoaderCircle,
  Lock,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Volume2,
} from "lucide-react";
import {
  errorMessage,
  fetchAdminApiKeys,
  testAdminApiKey,
  updateAdminApiKeys,
  type AdminApiKeyItem,
} from "@/lib/api";
import styles from "./settings-api-keys-section.module.css";

type SettingsApiKeysSectionProps = {
  onApiKeysUpdated?: () => void;
};

type ProbeState = {
  valid: boolean;
  detail: string;
};

function providerIconFor(keyName: string) {
  switch (keyName) {
    case "llm_api_key":
      return <Cpu size={15} />;
    case "google_api_key":
      return <Sparkles size={15} />;
    case "vertex_api_key":
      return <Cloud size={15} />;
    case "mistral_api_key":
      return <FileText size={15} />;
    case "ideogram_api_key":
      return <ImagePlus size={15} />;
    case "eleven_labs_key":
      return <Volume2 size={15} />;
    case "eod_historical_data_key":
      return <TrendingUp size={15} />;
    case "brave_api_key":
      return <Globe size={15} />;
    default:
      return <KeyRound size={15} />;
  }
}

function formatUpdatedAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function SettingsApiKeysSection({ onApiKeysUpdated }: SettingsApiKeysSectionProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [items, setItems] = useState<AdminApiKeyItem[]>([]);
  const [demoMode, setDemoMode] = useState(false);
  const [baselineDemoMode, setBaselineDemoMode] = useState(false);

  // États strictement transitoires en mémoire vive (zéro persistance navigateur)
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>({});
  const [pendingClears, setPendingClears] = useState<Record<string, boolean>>({});
  const [visibleDrafts, setVisibleDrafts] = useState<Record<string, boolean>>({});
  const [adminPassword, setAdminPassword] = useState("");

  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    fetchAdminApiKeys(controller.signal)
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setDemoMode(res.demo_mode);
        setBaselineDemoMode(res.baseline_demo_mode);
        setError(null);
      })
      .catch((err) => {
        if (!active || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(`Impossible de charger le coffre-fort des clés API : ${errorMessage(err)}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
      setDraftKeys({});
      setVisibleDrafts({});
      setAdminPassword("");
    };
  }, [reloadTick]);

  const nonEmptyDraftEntries = useMemo(
    () =>
      Object.entries(draftKeys)
        .map(([k, v]) => [k, v.trim()] as const)
        .filter(([k, v]) => v.length > 0 && !pendingClears[k]),
    [draftKeys, pendingClears],
  );

  const clearKeysList = useMemo(
    () => Object.keys(pendingClears).filter((k) => pendingClears[k]),
    [pendingClears],
  );

  const hasPendingChanges = nonEmptyDraftEntries.length > 0 || clearKeysList.length > 0;

  const activeTotal = useMemo(
    () => items.filter((item) => item.status !== "missing").length,
    [items],
  );

  function handleRetryLoad() {
    setLoading(true);
    setError(null);
    setReloadTick((n) => n + 1);
  }

  function handleDraftChange(keyName: string, value: string) {
    setDraftKeys((prev) => ({ ...prev, [keyName]: value }));
    if (value.trim()) {
      setPendingClears((prev) => {
        if (!prev[keyName]) return prev;
        const next = { ...prev };
        delete next[keyName];
        return next;
      });
    }
    setProbes((prev) => {
      if (!prev[keyName]) return prev;
      const next = { ...prev };
      delete next[keyName];
      return next;
    });
  }

  function handleToggleClear(keyName: string) {
    setPendingClears((prev) => {
      const nextVal = !prev[keyName];
      const next = { ...prev };
      if (nextVal) {
        next[keyName] = true;
      } else {
        delete next[keyName];
      }
      return next;
    });
    setDraftKeys((prev) => {
      if (!prev[keyName]) return prev;
      const next = { ...prev };
      delete next[keyName];
      return next;
    });
    setVisibleDrafts((prev) => {
      if (!prev[keyName]) return prev;
      const next = { ...prev };
      delete next[keyName];
      return next;
    });
  }

  function handleDiscardPending() {
    setDraftKeys({});
    setPendingClears({});
    setVisibleDrafts({});
    setAdminPassword("");
    setError(null);
  }

  async function handleTestProvider(item: AdminApiKeyItem) {
    if (testingKey || saving) return;
    setTestingKey(item.key_name);
    setError(null);
    const candidate = draftKeys[item.key_name]?.trim() || null;
    try {
      const res = await testAdminApiKey({
        key_name: item.key_name,
        candidate_value: candidate,
      });
      setProbes((prev) => ({
        ...prev,
        [item.key_name]: { valid: res.valid, detail: res.detail },
      }));
    } catch (err) {
      setProbes((prev) => ({
        ...prev,
        [item.key_name]: { valid: false, detail: errorMessage(err) },
      }));
    } finally {
      setTestingKey(null);
    }
  }

  async function handleApplyChanges(e: FormEvent) {
    e.preventDefault();
    if (!hasPendingChanges || saving || !adminPassword.trim()) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    const payloadKeys: Record<string, string> = {};
    for (const [k, v] of nonEmptyDraftEntries) {
      payloadKeys[k] = v;
    }

    try {
      const updated = await updateAdminApiKeys({
        current_password: adminPassword,
        keys: payloadKeys,
        clear_keys: clearKeysList,
      });

      // Purge immédiate des secrets en mémoire vive côté navigateur
      setDraftKeys({});
      setPendingClears({});
      setVisibleDrafts({});
      setAdminPassword("");
      setProbes({});

      setItems(updated.items);
      setDemoMode(updated.demo_mode);
      setBaselineDemoMode(updated.baseline_demo_mode);
      setSuccess("Coffre-fort mis à jour : vos clés sont chiffrées côté serveur et actives immédiatement.");
      onApiKeysUpdated?.();
    } catch (err) {
      setAdminPassword("");
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.section} aria-labelledby="settings-vault-title">
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.iconBadge} aria-hidden="true">
            <KeyRound size={18} />
          </span>
          <div className={styles.titleGroup}>
            <div className={styles.titleRow}>
              <h3 id="settings-vault-title" className={styles.title}>
                Coffre-fort Clés API (Prioritaires sur .env)
              </h3>
              <span className={styles.adminPill}>
                <ShieldCheck size={12} />
                <span>Administration</span>
              </span>
            </div>
            <p className={styles.subtitle}>
              Toute clé enregistrée ici est chiffrée côté serveur (<code>AES-256-GCM</code>) et prend immédiatement le relais du fichier <code>.env</code> pour toute l&apos;instance et les synchronisations de fond.
            </p>
          </div>
        </div>

        {!loading && items.length > 0 && (
          <div className={styles.headerMeta}>
            <span className={styles.countPill}>
              <span>{activeTotal} / {items.length} actives</span>
            </span>
            {baselineDemoMode && !demoMode && (
              <span className={`${styles.demoPill} ${styles.demoPillBypassed}`}>
                <CheckCircle2 size={12} />
                <span>Mode réel actif (coffre-fort)</span>
              </span>
            )}
            {demoMode && (
              <span className={`${styles.demoPill} ${styles.demoPillActive}`}>
                <AlertCircle size={12} />
                <span>Mode Démo actif (.env)</span>
              </span>
            )}
          </div>
        )}
      </div>

      <div className={styles.securityNote}>
        <Lock size={15} className={styles.securityNoteIcon} aria-hidden="true" />
        <span>
          <strong>Protection Write-Only :</strong> aucune clé n&apos;est conservée dans le navigateur ni renvoyée par le serveur après enregistrement (zéro caractère affiché, même partiel).
        </span>
      </div>

      {error && (
        <div className={`${styles.banner} ${styles.bannerError}`} role="alert">
          <div className={styles.bannerLeft}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
          {items.length === 0 && !loading && (
            <button type="button" className={styles.retryBtn} onClick={handleRetryLoad}>
              Réessayer
            </button>
          )}
        </div>
      )}

      {success && (
        <div className={`${styles.banner} ${styles.bannerSuccess}`} role="status">
          <div className={styles.bannerLeft}>
            <CheckCircle2 size={16} />
            <span>{success}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div className={styles.loadingGrid} aria-busy="true" aria-label="Chargement de l'état des clés API">
          <div className={styles.skeletonCard} />
          <div className={styles.skeletonCard} />
          <div className={styles.skeletonCard} />
          <div className={styles.skeletonCard} />
        </div>
      ) : (
        <form onSubmit={(e) => void handleApplyChanges(e)}>
          <div className={styles.grid}>
            {items.map((item) => {
              const draftVal = draftKeys[item.key_name] ?? "";
              const isMarkedClear = Boolean(pendingClears[item.key_name]);
              const isDirty = draftVal.trim().length > 0 && !isMarkedClear;
              const isVisible = Boolean(visibleDrafts[item.key_name]);
              const canTest = isDirty || (!isMarkedClear && item.status !== "missing");
              const probe = probes[item.key_name];
              const formattedDate = formatUpdatedAt(item.updated_at);

              let statusClass = styles.statusMissing;
              let statusLabel = "Non configurée";
              if (item.status === "active_vault") {
                statusClass = styles.statusVault;
                statusLabel = "Active · Paramètres";
              } else if (item.status === "active_env") {
                statusClass = styles.statusEnv;
                statusLabel = "Active · .env";
              }

              const placeholder = isMarkedClear
                ? item.has_env_fallback
                  ? "Bascule vers la clé .env en attente…"
                  : "Suppression de la clé en attente…"
                : item.status === "active_vault"
                  ? "Saisir une nouvelle clé pour remplacer…"
                  : item.status === "active_env"
                    ? "Saisir une clé pour surcharger le .env…"
                    : `Coller la clé ${item.env_name}…`;

              return (
                <div
                  key={item.key_name}
                  className={`${styles.card} ${isDirty ? styles.cardDirty : ""} ${isMarkedClear ? styles.cardPendingClear : ""}`}
                >
                  <div className={styles.cardTop}>
                    <div className={styles.cardIdentity}>
                      <span className={styles.providerIcon} aria-hidden="true">
                        {providerIconFor(item.key_name)}
                      </span>
                      <div className={styles.providerTexts}>
                        <span className={styles.providerLabel} title={item.label}>
                          {item.label}
                        </span>
                        <code className={styles.envCode}>{item.env_name}</code>
                      </div>
                    </div>
                    <span className={`${styles.statusBadge} ${statusClass}`}>
                      {statusLabel}
                    </span>
                  </div>

                  <p className={styles.cardDesc}>{item.description}</p>

                  <div className={styles.inputRow}>
                    <div className={styles.inputWrap}>
                      <input
                        type={isVisible ? "text" : "password"}
                        className={styles.secretInput}
                        value={draftVal}
                        onChange={(e) => handleDraftChange(item.key_name, e.target.value)}
                        placeholder={placeholder}
                        disabled={saving || isMarkedClear}
                        autoComplete="new-password"
                        spellCheck={false}
                        autoCapitalize="off"
                        autoCorrect="off"
                        data-1p-ignore="true"
                        data-lpignore="true"
                        aria-label={`Nouvelle clé pour ${item.label}`}
                      />
                      {draftVal.length > 0 && !isMarkedClear && (
                        <button
                          type="button"
                          className={styles.eyeBtn}
                          onClick={() =>
                            setVisibleDrafts((prev) => ({
                              ...prev,
                              [item.key_name]: !prev[item.key_name],
                            }))
                          }
                          aria-label={
                            isVisible
                              ? `Masquer la saisie pour ${item.label}`
                              : `Afficher temporairement la saisie pour ${item.label}`
                          }
                          title={isVisible ? "Masquer la saisie" : "Vérifier la saisie avant envoi"}
                        >
                          {isVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      )}
                    </div>

                    <button
                      type="button"
                      className={styles.testBtn}
                      disabled={!canTest || saving || testingKey !== null}
                      onClick={() => void handleTestProvider(item)}
                      title={
                        isDirty
                          ? "Tester la clé saisie en mémoire sans l'enregistrer"
                          : "Tester la clé actuellement active côté serveur"
                      }
                    >
                      {testingKey === item.key_name ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <Activity size={13} />
                      )}
                      <span>{isDirty ? "Tester saisie" : "Tester"}</span>
                    </button>
                  </div>

                  {probe && (
                    <div
                      className={`${styles.probeNotice} ${probe.valid ? styles.probeOk : styles.probeFail}`}
                      role="status"
                    >
                      {probe.valid ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                      <span>{probe.detail}</span>
                    </div>
                  )}

                  <div className={styles.cardFooter}>
                    <span className={styles.metaText}>
                      {item.status === "active_vault"
                        ? `${formattedDate ? `Modifiée le ${formattedDate}` : "Surcharge active"}${item.has_env_fallback ? " · Secours .env présent" : ""}`
                        : item.status === "active_env"
                          ? "Fournie par l'environnement serveur (.env)"
                          : "Aucune clé détectée"}
                    </span>

                    {item.status === "active_vault" && (
                      <button
                        type="button"
                        className={`${styles.resetLink} ${isMarkedClear ? styles.resetLinkActive : ""}`}
                        disabled={saving}
                        onClick={() => handleToggleClear(item.key_name)}
                      >
                        <RotateCcw size={12} />
                        <span>
                          {isMarkedClear
                            ? "Annuler le retrait"
                            : item.has_env_fallback
                              ? "Revenir au .env"
                              : "Supprimer la clé"}
                        </span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {hasPendingChanges && (
            <div className={styles.sudoBar}>
              <div className={styles.sudoInfo}>
                <span className={styles.sudoIcon} aria-hidden="true">
                  <Lock size={16} />
                </span>
                <div className={styles.sudoSummary}>
                  <strong>
                    Confirmation Administrateur requise (
                    {nonEmptyDraftEntries.length > 0
                      ? `${nonEmptyDraftEntries.length} clé${nonEmptyDraftEntries.length > 1 ? "s" : ""} à chiffrer`
                      : ""}
                    {nonEmptyDraftEntries.length > 0 && clearKeysList.length > 0 ? " · " : ""}
                    {clearKeysList.length > 0
                      ? `${clearKeysList.length} retrait${clearKeysList.length > 1 ? "s" : ""}`
                      : ""}
                    )
                  </strong>
                  <span>
                    Entrez le mot de passe de votre compte administrateur pour valider l&apos;opération.
                  </span>
                </div>
              </div>

              <div className={styles.sudoControls}>
                <input
                  type="password"
                  className={styles.sudoPasswordInput}
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="Mot de passe administrateur…"
                  autoComplete="current-password"
                  disabled={saving}
                  aria-label="Mot de passe administrateur pour confirmer les clés API"
                  required
                />
                <button
                  type="button"
                  className={styles.cancelChangesBtn}
                  onClick={handleDiscardPending}
                  disabled={saving}
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  className={styles.applyBtn}
                  disabled={saving || !adminPassword.trim()}
                >
                  {saving ? (
                    <>
                      <LoaderCircle size={14} className="spin" />
                      <span>Chiffrement…</span>
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={15} />
                      <span>Chiffrer &amp; Appliquer</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
