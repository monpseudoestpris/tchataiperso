"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Brain, Check, LoaderCircle, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { api, errorMessage, skillToSlug, type Config, type Conversation, type Skill } from "@/lib/api";

type SkillsPanelProps = {
  conversation: Conversation | null;
  model: string;
  config: Config | null;
  onClose: () => void;
  onConversationChange: (conversation: Conversation) => void;
  onRefreshConversations: () => Promise<void>;
  onSkillsChange?: (skills: Skill[]) => void;
};

const STARTER_TEMPLATES = [
  {
    name: "Professeur",
    slug: "prof",
    prompt: "Tu es un professeur pédagogue, structuré et bienveillant. Explique pas à pas avec des exemples concrets et vérifie la bonne compréhension.",
  },
  {
    name: "Richard Feynman",
    slug: "feynman",
    prompt: "Tu adoptes la méthode Feynman : explique chaque concept avec une clarté absolue, des analogies simples du quotidien et aucun jargon inutile.",
  },
  {
    name: "Revue de code",
    slug: "code",
    prompt: "Tu es un relecteur de code expérimenté. Analyse la rigueur, les performances, les cas limites et propose des améliorations précises.",
  },
];

export function SkillsPanel({ conversation, model, config, onClose, onConversationChange, onRefreshConversations, onSkillsChange }: SkillsPanelProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<Skill[]>("/skills", { signal: controller.signal })
      .then(items => {
        setSkills(items);
        onSkillsChange?.(items);
      })
      .catch(err => { if (!controller.signal.aborted) setError(errorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [onSkillsChange]);

  const activeIds = conversation?.skills?.map(skill => skill.id) ?? [];

  function clearEditor() {
    setEditingId(null);
    setName("");
    setPrompt("");
  }

  function applyTemplate(tpl: { name: string; prompt: string }) {
    setEditingId(null);
    setName(tpl.name);
    setPrompt(tpl.prompt);
    setError("");
  }

  async function saveSkill(event: FormEvent) {
    event.preventDefault();
    if (busy || !name.trim() || !prompt.trim()) return;
    setBusy("save"); setError("");
    try {
      const saved = await api<Skill>(editingId ? `/skills/${editingId}` : "/skills", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({ name: name.trim(), prompt: prompt.trim() }),
      });
      setSkills(current => {
        const next = editingId ? current.map(item => item.id === saved.id ? saved : item) : [...current, saved];
        onSkillsChange?.(next);
        return next;
      });
      if (editingId && conversation?.skills?.some(item => item.id === saved.id)) {
        onConversationChange({ ...conversation, skills: conversation.skills.map(item => item.id === saved.id ? saved : item) });
      }
      clearEditor();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(""); }
  }

  async function improvePrompt() {
    if (busy || !prompt.trim() || !config?.features.chat || config.demo_mode) return;
    setBusy("improve"); setError("");
    try {
      const result = await api<{ prompt: string }>("/skills/improve", {
        method: "POST", body: JSON.stringify({ prompt: prompt.trim() }),
      });
      setPrompt(result.prompt);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(""); }
  }

  async function toggleSkill(skill: Skill) {
    if (busy) return;
    const skillIds = activeIds.includes(skill.id) ? activeIds.filter(id => id !== skill.id) : [...activeIds, skill.id];
    if (skillIds.length > 8 || skillIds.reduce((total, id) => total + (skills.find(item => item.id === id)?.prompt.length ?? 0), 0) > 12000) {
      setError("Les compétences sélectionnées dépassent la limite de contexte.");
      return;
    }
    setBusy("selection"); setError("");
    try {
      const target = conversation ?? await api<Conversation>("/conversations", {
        method: "POST", body: JSON.stringify({ model }),
      });
      const selected = await api<Skill[]>(`/conversations/${target.id}/skills`, {
        method: "PATCH", body: JSON.stringify({ skill_ids: skillIds }),
      });
      onConversationChange({ ...target, skills: selected });
      await onRefreshConversations();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(""); }
  }

  function editSkill(skill: Skill) {
    setEditingId(skill.id);
    setName(skill.name);
    setPrompt(skill.prompt);
    setError("");
  }

  async function deleteSkill(skill: Skill) {
    if (busy || !window.confirm(`Supprimer la compétence « ${skill.name} » ?`)) return;
    setBusy("delete"); setError("");
    try {
      await api(`/skills/${skill.id}`, { method: "DELETE" });
      setSkills(current => {
        const next = current.filter(item => item.id !== skill.id);
        onSkillsChange?.(next);
        return next;
      });
      if (conversation?.skills?.some(item => item.id === skill.id)) {
        onConversationChange({ ...conversation, skills: conversation.skills.filter(item => item.id !== skill.id) });
      }
      if (editingId === skill.id) clearEditor();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(""); }
  }

  return <aside className="skills-panel" aria-label="Compétences">
    <div className="skills-panel-heading">
      <div><span className="eyebrow">CONSIGNES PERSONNELLES</span><h2>Compétences</h2></div>
      <button type="button" className="icon-button" aria-label="Fermer les compétences" title="Fermer" onClick={onClose}><X size={18} /></button>
    </div>
    <div className="skills-panel-body">
      <section className="skills-selection">
        <div className="skills-section-heading"><Brain size={17} /><h3>{conversation ? "Dans ce tchat" : "Pour ce tchat"}</h3><span>{activeIds.length}</span></div>
        <p>{conversation ? "Cochez les consignes à appliquer aux prochains messages." : "Choisir une compétence créera ce tchat et enregistrera la sélection."}</p>
        <div className="skills-mention-hint">
          <Sparkles size={13} />
          <span>Accès direct : tapez <code>@nom</code> (ex. <code>@prof</code> ou <code>@feynman</code>) dans n’importe quel message pour l’utiliser individuellement.</span>
        </div>
      </section>

      {error && <p className="skills-error" role="alert">{error}</p>}
      {loading ? <div className="skills-loading"><LoaderCircle className="spin" size={16} />Chargement…</div> : skills.length ? <ul className="skill-list">
        {skills.map(skill => <li key={skill.id}>
          <div className="skill-list-heading">
            <label>
              <input type="checkbox" checked={activeIds.includes(skill.id)} disabled={!!busy} onChange={() => void toggleSkill(skill)} />
              <span>{skill.name}</span>
              <span className="skill-mention-badge" title={`Mentionnez cette compétence avec @${skillToSlug(skill.name)}`}>@{skillToSlug(skill.name)}</span>
            </label>
            <div><button type="button" className="icon-button" aria-label={`Modifier ${skill.name}`} title="Modifier" disabled={!!busy} onClick={() => editSkill(skill)}><Pencil size={14} /></button><button type="button" className="icon-button" aria-label={`Supprimer ${skill.name}`} title="Supprimer" disabled={!!busy} onClick={() => void deleteSkill(skill)}><Trash2 size={14} /></button></div>
          </div>
          <p>{skill.prompt}</p>
        </li>)}
      </ul> : <div className="skills-empty">
        <Brain size={21} />
        <p>Aucune compétence enregistrée.</p>
        <div className="skill-starter-templates">
          <p className="starter-label">Modèles prêts à l’emploi :</p>
          <div className="starter-chips">
            {STARTER_TEMPLATES.map(tpl => (
              <button key={tpl.slug} type="button" className="starter-chip" onClick={() => applyTemplate(tpl)}>
                <Plus size={12} /><span>{tpl.name} (<code>@{tpl.slug}</code>)</span>
              </button>
            ))}
          </div>
        </div>
      </div>}

      <form className="skill-editor" onSubmit={event => void saveSkill(event)}>
        <h3>{editingId ? "Modifier la compétence" : "Nouvelle compétence"}</h3>
        <label htmlFor="skill-name">Nom</label>
        <input id="skill-name" value={name} onChange={event => setName(event.target.value)} maxLength={100} placeholder="Ex. Rédaction concise" disabled={!!busy} />
        <label htmlFor="skill-prompt">Prompt</label>
        <textarea id="skill-prompt" value={prompt} onChange={event => setPrompt(event.target.value)} maxLength={5000} rows={5} placeholder="Décrivez la manière de travailler que l’assistant doit suivre…" disabled={!!busy} />
        <div className="skill-editor-actions">
          <button type="button" className="skill-improve" disabled={!!busy || !prompt.trim() || !config?.features.chat || !!config.demo_mode} onClick={() => void improvePrompt()}>{busy === "improve" ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />}Améliorer avec l’IA</button>
          <span>{prompt.length}/5000</span>
        </div>
        <div className="skill-save-actions">
          {editingId && <button type="button" className="skill-cancel" disabled={!!busy} onClick={clearEditor}>Annuler</button>}
          <button type="submit" disabled={!!busy || !name.trim() || !prompt.trim()}>{busy === "save" ? <LoaderCircle className="spin" size={14} /> : editingId ? <Check size={14} /> : <Plus size={14} />}{editingId ? "Enregistrer" : "Créer"}</button>
        </div>
      </form>
    </div>
  </aside>;
}