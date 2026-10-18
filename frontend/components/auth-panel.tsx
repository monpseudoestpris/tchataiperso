"use client";

import { useState, type FormEvent } from "react";
import { KeyRound, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";
import { api, errorMessage, type AuthUser } from "@/lib/api";

export function AuthPanel({ invitationToken, serviceError, onAuthenticated, onRegistration }: {
  invitationToken: string;
  serviceError: string;
  onAuthenticated: (user: AuthUser) => Promise<void>;
  onRegistration: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const registering = !!invitationToken;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      if (registering) {
        await api("/auth/register", { method: "POST", body: JSON.stringify({ token: invitationToken, username, password }) });
        setPassword(""); setNotice("Compte créé. Connectez-vous pour continuer.");
        onRegistration();
      }
      const user = await api<AuthUser>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      await onAuthenticated(user);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <main className="auth-shell">
    <section className="auth-panel" aria-labelledby="auth-title">
      <div className="auth-brand"><span className="brand-mark small"><Sparkles strokeWidth={1.5} /></span><span>cLAIr<span className="brand-dot">.</span></span></div>
      <span className="auth-eyebrow"><ShieldCheck size={14} /> ESPACE PERSONNEL</span>
      <h1 id="auth-title">{registering ? "Créer votre espace" : "Retrouver votre espace"}</h1>
      <p className="auth-intro">{registering ? "Choisissez un identifiant et un mot de passe pour activer votre invitation." : "Connectez-vous avec les identifiants de votre compte."}</p>
      <form className="auth-form" onSubmit={event => void submit(event)}>
        <label htmlFor="auth-username">Identifiant</label>
        <input id="auth-username" name="username" autoComplete="username" minLength={3} maxLength={48} required value={username} onChange={event => setUsername(event.target.value)} disabled={busy} />
        <label htmlFor="auth-password">Mot de passe</label>
        <input id="auth-password" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={12} maxLength={128} required value={password} onChange={event => setPassword(event.target.value)} disabled={busy} />
        {(error || serviceError) && <p className="auth-message is-error" role="alert">{error || serviceError}</p>}
        {notice && <p className="auth-message" role="status">{notice}</p>}
        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <KeyRound size={17} />}
          {registering ? "Créer le compte" : "Se connecter"}
        </button>
      </form>
      {!invitationToken && <p className="auth-footnote">Accès réservé aux comptes créés par un administrateur.</p>}
    </section>
  </main>;
}
