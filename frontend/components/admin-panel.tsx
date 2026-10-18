"use client";

import { useEffect, useState } from "react";
import { Check, Copy, LoaderCircle, Plus, Shield, UserRound, X } from "lucide-react";
import { api, errorMessage, type AdminUser, type AuthUser } from "@/lib/api";

export function AdminPanel({ currentUser, onClose }: { currentUser: AuthUser; onClose: () => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invitationUrl, setInvitationUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<AdminUser[]>("/admin/users").then(result => { if (active) setUsers(result); })
      .catch(reason => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, []);

  async function createInvitation() {
    setBusy(true); setError(""); setCopied(false);
    try {
      const invitation = await api<{ token: string; expires_at: string }>("/admin/invitations", { method: "POST" });
      setInvitationUrl(`${window.location.origin}/#invite=${encodeURIComponent(invitation.token)}`);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  async function copyInvitation() {
    try {
      await navigator.clipboard.writeText(invitationUrl);
      setCopied(true);
    } catch (reason) { setError(errorMessage(reason)); }
  }

  async function toggleUser(user: AdminUser) {
    setBusy(true); setError("");
    try {
      const updated = await api<AdminUser>(`/admin/users/${user.id}`, {
        method: "PATCH", body: JSON.stringify({ active: !user.active }),
      });
      setUsers(old => old.map(item => item.id === updated.id ? updated : item));
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <div className="modal-backdrop admin-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="admin-panel" role="dialog" aria-modal="true" aria-labelledby="admin-title">
      <header className="admin-heading"><div><span className="eyebrow">GESTION DU COMPTE</span><h2 id="admin-title">Utilisateurs</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Fermer"><X size={18} /></button></header>
      <button type="button" className="admin-invite" onClick={() => void createInvitation()} disabled={busy}><Plus size={16} />Créer une invitation</button>
      {invitationUrl && <div className="invitation-output"><label htmlFor="invitation-url">Lien à transmettre (usage unique)</label><div><input id="invitation-url" readOnly value={invitationUrl} /><button type="button" className="icon-button" onClick={() => void copyInvitation()} aria-label="Copier le lien d’invitation" title="Copier le lien">{copied ? <Check size={16} /> : <Copy size={16} />}</button></div></div>}
      {error && <p className="auth-message is-error" role="alert">{error}</p>}
      <div className="admin-list-heading"><span>Comptes</span><span>{users.length}</span></div>
      <ul className="admin-users">{users.map(user => <li key={user.id}>
        <span className="admin-user-icon">{user.is_admin ? <Shield size={16} /> : <UserRound size={16} />}</span>
        <span className="admin-user-name"><strong>{user.username}</strong><small>{user.is_admin ? "Administrateur" : "Utilisateur"}{!user.active ? " · suspendu" : ""}</small></span>
        {user.id !== currentUser.id && <button type="button" className="admin-user-action" disabled={busy} onClick={() => void toggleUser(user)}>{user.active ? "Suspendre" : "Réactiver"}</button>}
      </li>)}</ul>
      {busy && <p className="admin-loading"><LoaderCircle className="spin" size={14} />Mise à jour…</p>}
    </section>
  </div>;
}
