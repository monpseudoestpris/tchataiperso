"use client";

import { useEffect, useId, useMemo, useRef } from "react";
import { Check, CircleAlert, Compass, ExternalLink, Globe2, LoaderCircle, Search, X } from "lucide-react";
import { collectResearchSites, type ResearchRun } from "@/lib/research-activity";
import styles from "./research-activity-modal.module.css";

type Props = {
  run?: ResearchRun;
  sources: { title: string; url: string }[];
  onClose: () => void;
};

const siteLabels = { found: "Trouvé", selected: "Retenu", read: "Page lue", unavailable: "Extrait seulement" };
const runLabels = { running: "En cours", completed: "Terminée", interrupted: "Interrompue", failed: "Échec" };

export function ResearchActivityModal({ run, sources, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  const events = run?.events;
  const sites = useMemo(() => collectResearchSites(events ?? [], sources), [events, sources]);
  const queries = new Set(events?.filter(event => event.kind === "query" && event.query).map(event => event.query));
  const readingCount = sites.filter(site => site.state === "read").length;
  const running = run?.state === "running";

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return <dialog ref={dialogRef} className={styles.dialog} aria-labelledby={headingId}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={styles.panel}>
      <header className={styles.header}>
        <div><div className={styles.title}><Compass size={20} /><h2 id={headingId}>Activité DeepSearch</h2></div>
          <p>Recherches, documents et contrôles effectués.</p></div>
        <button className={styles.close} type="button" onClick={onClose} aria-label="Fermer le suivi DeepSearch"><X size={20} /></button>
      </header>
      <div className={styles.summary}>
        <span className={styles.state}>{running ? <LoaderCircle size={14} className="spin" /> : run?.state === "failed" || run?.state === "interrupted" ? <CircleAlert size={14} /> : <Check size={14} />}{run ? runLabels[run.state] : "Sources enregistrées"}</span>
        {run && <span><Search size={14} />{queries.size} requête{queries.size > 1 ? "s" : ""}</span>}
        <span><Globe2 size={14} />{sites.length} document{sites.length > 1 ? "s" : ""}</span>
        {!!readingCount && <span>{readingCount} page{readingCount > 1 ? "s lues" : " lue"}</span>}
      </div>
      <div className={styles.columns}>
        <section className={styles.section} aria-label="Étapes de la recherche">
          <h3>Dernières étapes et requêtes</h3>
          {!events?.length && <p className={styles.empty}>{running ? "La recherche démarre…" : "Le journal détaillé de cette recherche n’est pas disponible. Ses sources enregistrées figurent dans la liste des documents."}</p>}
          <ol className={styles.timeline}>{events?.slice().reverse().map((event, index) => <li key={index}>
            <time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
            <div><p>{event.message}</p>{event.query && <blockquote>{event.query}</blockquote>}</div>
          </li>)}</ol>
        </section>
        <section className={styles.section} aria-label="Documents trouvés et consultés">
          <h3>Sites et documents</h3>
          <p className={styles.hint}>« Trouvé » correspond à un résultat de recherche. « Page lue » indique qu’un contenu textuel a été récupéré depuis la page.</p>
          {!sites.length && <p className={styles.empty}>{running ? "Les premiers documents apparaîtront ici dès leur découverte." : "Aucun document exploitable n’a été reçu."}</p>}
          <ul className={styles.sites}>{sites.map(site => <li key={site.url}>
            <a href={site.url} target="_blank" rel="noopener noreferrer"><span>{site.title}</span><ExternalLink size={13} /></a>
            <div><span>{new URL(site.url).hostname}</span><span className={styles.siteState} data-state={site.state}>{siteLabels[site.state]}</span></div>
          </li>)}</ul>
        </section>
      </div>
    </div>
  </dialog>;
}
