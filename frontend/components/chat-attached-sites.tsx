"use client";

import { useEffect, useState } from "react";
import { Globe2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";

type AttachedSite = {
  id: string;
  title: string;
  scope: "turn" | "conversation";
  created_at: string;
  url: string;
};

/** Refresh on return from the generation tab; saved links never regenerate a page. */
export function ChatAttachedSites({ conversationId }: { conversationId: string }) {
  const [sites, setSites] = useState<AttachedSite[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let latestRequest = 0;
    async function refresh() {
      const request = ++latestRequest;
      try {
        const result = await api<AttachedSite[]>(`/conversations/${conversationId}/sites`);
        if (active && request === latestRequest) {
          setSites(result);
          setError(null);
        }
      } catch (cause) {
        if (active && request === latestRequest) setError(errorMessage(cause));
      }
    }
    function onVisible() {
      if (document.visibilityState === "visible") void refresh();
    }
    void refresh();
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [conversationId]);

  if (!sites.length && !error) return null;
  return (
    <section aria-label="Pages HTML attachées au tchat" style={{ margin: "12px 0 24px" }}>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Pages HTML attachées</p>
      {error && <p role="status">Impossible de charger les pages : {error}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {sites.map(site => (
          <a key={site.id} href={site.url} target="_blank" rel="noopener noreferrer"
            className="conversation-meta-btn" style={{ textDecoration: "none" }}>
            <Globe2 size={14} />
            <span>{site.title} · {site.scope === "turn" ? "Ce tour" : "Discussion"}</span>
            <time dateTime={site.created_at} style={{ opacity: 0.7 }}>
              {new Date(site.created_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
            </time>
          </a>
        ))}
      </div>
    </section>
  );
}
