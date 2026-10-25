"use client";

import { useState, type FormEvent } from "react";
import {
  ArrowRightLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Link2,
  LoaderCircle,
  Pencil,
  Plus,
  Shield,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { api, errorMessage, type AuthUser, type FamilyGroupInfo, type FamilyMember } from "@/lib/api";

export function FamilyModal({
  currentUser,
  familyInfo,
  onClose,
  onFamilyUpdated,
  onSwitchAccount,
}: {
  currentUser: AuthUser;
  familyInfo: FamilyGroupInfo | null;
  onClose: () => void;
  onFamilyUpdated: (info: FamilyGroupInfo) => void;
  onSwitchAccount: (targetUserId: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Initialisation / Renommage groupe
  const [isEditingName, setIsEditingName] = useState(false);
  const [familyName, setFamilyName] = useState(familyInfo?.name || `Famille ${currentUser.username}`);

  // Création nouveau membre
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  // Rattachement compte existant
  const [showLinkSection, setShowLinkSection] = useState(false);
  const [linkUsername, setLinkUsername] = useState("");
  const [linkPassword, setLinkPassword] = useState("");

  const members = familyInfo?.members || [];
  const hasFamily = Boolean(familyInfo?.id);

  async function handleCreateOrUpdateFamily(event?: FormEvent) {
    if (event) event.preventDefault();
    if (!familyName.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const endpoint = hasFamily ? "/family" : "/family";
      const method = hasFamily ? "PATCH" : "POST";
      const updated = await api<FamilyGroupInfo>(endpoint, {
        method,
        body: JSON.stringify({ name: familyName.trim() }),
      });
      onFamilyUpdated(updated);
      setIsEditingName(false);
      setNotice(hasFamily ? "Nom du groupe mis à jour." : "Groupe familial créé avec succès !");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateMember(event: FormEvent) {
    event.preventDefault();
    if (!newUsername.trim() || !newPassword) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<FamilyGroupInfo>("/family/members", {
        method: "POST",
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword,
        }),
      });
      onFamilyUpdated(updated);
      setNotice(`Compte « ${newUsername.trim()} » créé et rattaché au groupe familial !`);
      setNewUsername("");
      setNewPassword("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkMember(event: FormEvent) {
    event.preventDefault();
    if (!linkUsername.trim() || !linkPassword) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<FamilyGroupInfo>("/family/link", {
        method: "POST",
        body: JSON.stringify({
          username: linkUsername.trim(),
          password: linkPassword,
        }),
      });
      onFamilyUpdated(updated);
      setNotice(`Compte « ${linkUsername.trim()} » rattaché avec succès au groupe familial !`);
      setLinkUsername("");
      setLinkPassword("");
      setShowLinkSection(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(member: FamilyMember) {
    if (!confirm(`Détacher le compte « ${member.username} » du groupe familial ?`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<FamilyGroupInfo>(`/family/members/${member.id}`, {
        method: "DELETE",
      });
      onFamilyUpdated(updated);
      setNotice(`Compte « ${member.username} » détaché.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSwitch(targetUserId: string) {
    setBusy(true); setError("");
    try {
      await onSwitchAccount(targetUserId);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop family-backdrop"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="family-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="family-title"
      >
        <header className="family-modal-header">
          <div className="family-modal-heading">
            <span className="family-eyebrow">
              <Users size={15} /> GROUPE FAMILIAL
            </span>
            <h2 id="family-title">
              {hasFamily ? (familyInfo?.name || "Votre groupe familial") : "Créer un groupe familial"}
            </h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X size={18} />
          </button>
        </header>

        {notice && <p className="auth-message is-success" role="status">{notice}</p>}
        {error && <p className="auth-message is-error" role="alert">{error}</p>}

        {!hasFamily ? (
          <div className="family-init-card">
            <p className="family-init-intro">
              Créez un groupe familial pour réunir les comptes des membres de votre foyer.
              Chacun conserve son espace personnel et ses discussions privées, mais vous pouvez
              <strong> basculer instantanément d’un compte à l’autre</strong> sans retaper mot de passe ni identifiant.
            </p>
            <form onSubmit={handleCreateOrUpdateFamily} className="family-init-form">
              <label htmlFor="init-family-name">Nom du groupe familial</label>
              <div className="family-input-row">
                <input
                  id="init-family-name"
                  type="text"
                  required
                  value={familyName}
                  onChange={e => setFamilyName(e.target.value)}
                  placeholder="Ex : Famille Martin, Foyer..."
                  disabled={busy}
                />
                <button type="submit" className="family-primary-btn" disabled={busy || !familyName.trim()}>
                  {busy ? <LoaderCircle className="spin" size={16} /> : <Users size={16} />}
                  <span>Créer le groupe</span>
                </button>
              </div>
            </form>
          </div>
        ) : (
          <div className="family-modal-body">
            {/* Entête avec nom modifiable */}
            <div className="family-name-bar">
              {isEditingName ? (
                <form onSubmit={handleCreateOrUpdateFamily} className="family-rename-form">
                  <input
                    type="text"
                    value={familyName}
                    onChange={e => setFamilyName(e.target.value)}
                    required
                    disabled={busy}
                    placeholder="Nom du groupe"
                  />
                  <button type="submit" className="family-small-btn" disabled={busy}>
                    <Check size={14} /> Enregistrer
                  </button>
                  <button
                    type="button"
                    className="family-small-btn cancel"
                    onClick={() => {
                      setFamilyName(familyInfo?.name || "");
                      setIsEditingName(false);
                    }}
                  >
                    Annuler
                  </button>
                </form>
              ) : (
                <div className="family-name-display">
                  <span className="family-badge-tag">
                    <Users size={13} /> {members.length} membre{members.length > 1 ? "s" : ""}
                  </span>
                  <button
                    type="button"
                    className="family-rename-btn"
                    onClick={() => setIsEditingName(true)}
                    title="Renommer le groupe"
                  >
                    <Pencil size={13} /> Modifier le nom
                  </button>
                </div>
              )}
            </div>

            {/* Liste des membres */}
            <div className="family-section">
              <h3 className="family-section-title">Membres du foyer</h3>
              <p className="family-section-desc">
                Cliquez sur <strong>« Basculer »</strong> pour passer immédiatement sur le compte souhaité sans mot de passe.
              </p>
              <ul className="family-members-list">
                {members.map(member => {
                  const isCurrent = member.id === currentUser.id;
                  return (
                    <li key={member.id} className={`family-member-row ${isCurrent ? "is-current" : ""}`}>
                      <div className="family-member-identity">
                        <span className="family-avatar">
                          {member.username[0].toLocaleUpperCase("fr")}
                        </span>
                        <div className="family-member-info">
                          <span className="family-member-name">
                            <strong>{member.username}</strong>
                            {isCurrent && <span className="family-current-badge"><UserCheck size={12} /> Session active</span>}
                            {member.is_admin && <span className="family-role-badge"><Shield size={11} /> Admin</span>}
                          </span>
                          <span className="family-member-sub">
                            {isCurrent ? "Votre compte actuellement ouvert" : "Compte familial disponible"}
                          </span>
                        </div>
                      </div>

                      <div className="family-member-actions">
                        {!isCurrent ? (
                          <button
                            type="button"
                            className="family-switch-action-btn"
                            disabled={busy}
                            onClick={() => void handleSwitch(member.id)}
                            title={`Basculer immédiatement sur le compte ${member.username}`}
                          >
                            <ArrowRightLeft size={14} />
                            <span>Basculer</span>
                          </button>
                        ) : (
                          <span className="family-active-indicator" title="Vous utilisez ce compte">
                            Connecté
                          </span>
                        )}
                        {!isCurrent && (
                          <button
                            type="button"
                            className="family-remove-btn"
                            disabled={busy}
                            onClick={() => void handleRemoveMember(member)}
                            title="Détacher ce compte du groupe familial"
                            aria-label={`Détacher ${member.username}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>

            {/* Formulaire création nouveau compte direct */}
            <div className="family-section family-create-card">
              <h3 className="family-section-title">
                <UserPlus size={16} /> Créer un compte pour la famille
              </h3>
              <p className="family-section-desc">
                Créez directement un compte pour un membre de votre famille (conjoint, enfant...).
                Il sera automatiquement associé à ce groupe et accessible sans ressaisir le mot de passe.
              </p>
              <form onSubmit={handleCreateMember} className="family-add-form">
                <div className="family-form-grid">
                  <div className="family-field">
                    <label htmlFor="new-fam-username">Identifiant</label>
                    <input
                      id="new-fam-username"
                      type="text"
                      required
                      minLength={3}
                      maxLength={48}
                      placeholder="Ex : lucas, emma, maman..."
                      value={newUsername}
                      onChange={e => setNewUsername(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                  <div className="family-field">
                    <label htmlFor="new-fam-password">Mot de passe initial (min. 12 car.)</label>
                    <input
                      id="new-fam-password"
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      placeholder="Mot de passe sécurisé"
                      value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  className="family-primary-btn"
                  disabled={busy || !newUsername.trim() || newPassword.length < 12}
                >
                  {busy ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}
                  <span>Créer et ajouter au foyer</span>
                </button>
              </form>
            </div>

            {/* Section repliable : rattacher un compte existant */}
            <div className="family-link-toggle-wrap">
              <button
                type="button"
                className="family-toggle-link-btn"
                onClick={() => setShowLinkSection(prev => !prev)}
              >
                <Link2 size={14} />
                <span>Rattacher un compte déjà existant</span>
                {showLinkSection ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>

              {showLinkSection && (
                <form onSubmit={handleLinkMember} className="family-link-form">
                  <p className="family-section-desc">
                    Si un membre a déjà un compte distinct, renseignez ses identifiants une seule fois pour le joindre au groupe.
                  </p>
                  <div className="family-form-grid">
                    <div className="family-field">
                      <label htmlFor="link-fam-username">Identifiant existant</label>
                      <input
                        id="link-fam-username"
                        type="text"
                        required
                        placeholder="Identifiant du compte"
                        value={linkUsername}
                        onChange={e => setLinkUsername(e.target.value)}
                        disabled={busy}
                      />
                    </div>
                    <div className="family-field">
                      <label htmlFor="link-fam-password">Mot de passe du compte</label>
                      <input
                        id="link-fam-password"
                        type="password"
                        required
                        placeholder="Mot de passe"
                        value={linkPassword}
                        onChange={e => setLinkPassword(e.target.value)}
                        disabled={busy}
                      />
                    </div>
                  </div>
                  <button
                    type="submit"
                    className="family-secondary-btn"
                    disabled={busy || !linkUsername.trim() || !linkPassword}
                  >
                    {busy ? <LoaderCircle className="spin" size={16} /> : <Link2 size={16} />}
                    <span>Rattacher ce compte</span>
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

