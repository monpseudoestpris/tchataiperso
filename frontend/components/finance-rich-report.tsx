"use client";

import { Check, Copy, Download, ExternalLink, FileCode2, MessageSquarePlus, Newspaper } from "lucide-react";
import { useMemo, useState, useSyncExternalStore } from "react";

import {
  buildStandaloneReportDocument,
  markdownToClassyReportHtml,
  sanitizeReportHtml,
  type ReportHtmlMeta,
} from "@/lib/safe-report-html";

type FinanceRichReportProps = {
  contentHtml?: string | null;
  markdown: string;
  meta: ReportHtmlMeta;
  newsArticles?: { title: string; url: string; source: string; published_at: string }[];
  onInsertIntoChat?: (text: string) => void;
  hideToolbar?: boolean;
};

const emptySubscribe = () => () => {};

/** Affiche un rapport financier en HTML coloré et assaini, avec export HTML / copie / envoi au tchat. */
export function FinanceRichReport({
  contentHtml,
  markdown,
  meta,
  newsArticles,
  onInsertIntoChat,
  hideToolbar = false,
}: FinanceRichReportProps) {
  const isClient = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
  const [copied, setCopied] = useState(false);

  const safeHtml = useMemo(() => {
    if (!isClient) return "";
    const raw = contentHtml && contentHtml.trim() ? contentHtml : markdownToClassyReportHtml(markdown, meta);
    return sanitizeReportHtml(raw);
  }, [isClient, contentHtml, markdown, meta]);

  function handleCopy() {
    if (!markdown) return;
    navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  function handleOpenHtmlTab() {
    if (!safeHtml) return;
    const doc = buildStandaloneReportDocument(safeHtml, meta.title);
    const blob = new Blob([doc], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function handleDownloadHtml() {
    if (!safeHtml) return;
    const doc = buildStandaloneReportDocument(safeHtml, meta.title);
    const blob = new Blob([doc], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const slug = `${meta.symbol || "rapport"}-${meta.title}`
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 64);
    a.href = url;
    a.download = `${slug || "analyse-finance"}.html`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5_000);
  }

  return (
    <div className="finance-rich-report">
      {!hideToolbar && (
        <div className="finance-rich-report-bar">
          <div className="finance-rich-report-actions">
            <button type="button" className="finance-tf-btn" onClick={handleOpenHtmlTab} title="Ouvrir ce rapport HTML dans un nouvel onglet">
              <FileCode2 size={12} />
              <span>Ouvrir HTML</span>
            </button>
            <button type="button" className="finance-tf-btn" onClick={handleDownloadHtml} title="Télécharger la fiche HTML complète">
              <Download size={12} />
              <span>Télécharger .html</span>
            </button>
            <button type="button" className="finance-tf-btn" onClick={handleCopy}>
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span>{copied ? "Copié" : "Copier"}</span>
            </button>
            {onInsertIntoChat && (
              <button
                type="button"
                className="finance-tf-btn active"
                onClick={() => onInsertIntoChat(markdown)}
              >
                <MessageSquarePlus size={12} />
                <span>Envoyer au tchat</span>
              </button>
            )}
          </div>
        </div>
      )}

      {newsArticles && newsArticles.length > 0 && (
        <details className="finance-expert-news-details">
          <summary>
            <Newspaper size={12} />
            <span>Voir les {newsArticles.length} actualité(s) fraîchement collectées et analysées</span>
          </summary>
          <ul>
            {newsArticles.map((art, idx) => (
              <li key={`${idx}-${art.url}`}>
                {/^https?:\/\//i.test(art.url) ? (
                  <a href={art.url} target="_blank" rel="noopener noreferrer">
                    {art.title} <ExternalLink size={11} />
                  </a>
                ) : (
                  <span>{art.title}</span>
                )}
                <small>
                  {art.source}
                  {art.published_at ? ` · ${art.published_at}` : ""}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="finance-rich-report-body" dangerouslySetInnerHTML={{ __html: safeHtml }} />
    </div>
  );
}
