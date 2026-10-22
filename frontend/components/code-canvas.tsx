"use client";

import {
  Check, Code2, Copy, Download, Eye, FileCode2, FileJson, FilePlus2, FileText,
  FolderArchive, FolderTree, Globe, LoaderCircle, Maximize2, Minimize2, Play,
  RefreshCw, RotateCcw, Sparkles, Terminal, Trash2, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  buildCanvasPreviewHtml,
  createZipBlob,
  inferLanguageFromPath,
  sanitizeFilePath,
  triggerBlobDownload,
  type CanvasFile,
} from "@/lib/code-canvas";

type CodeCanvasProps = {
  title: string;
  aiFiles: CanvasFile[];
  streaming: boolean;
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  onClose: () => void;
  onQuickPrompt?: (prompt: string) => void;
};

const QUICK_CODE_PROMPTS = [
  {
    title: "App Web Kanban",
    description: "HTML, CSS & JS avec glisser-déposer et sauvegarde locale",
    prompt: "Crée une application web complète de tableau Kanban (À faire, En cours, Terminé) en plusieurs fichiers (index.html, styles.css, app.js, README.md) avec ajout/suppression de cartes, filtres et sauvegarde localStorage.",
  },
  {
    title: "API Python FastAPI",
    description: "Architecture multi-fichiers avec modèles, routes et tests",
    prompt: "Crée une API REST FastAPI proprement structurée en plusieurs fichiers (app/main.py, app/models.py, app/schemas.py, requirements.txt, README.md) pour gérer une bibliothèque de livres avec recherche et validation.",
  },
  {
    title: "Dashboard Interactif",
    description: "Interface analytique moderne avec graphiques SVG dynamiques",
    prompt: "Crée un tableau de bord analytique interactif en plusieurs fichiers (index.html, styles.css, charts.js, app.js) avec indicateurs clés, graphiques SVG animés et filtre par période.",
  },
];

function slugifyTitle(value: string): string {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized.slice(0, 48) || "projet-canvas";
}

function FileIcon({ path }: { path: string }) {
  const lower = path.toLowerCase();
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return <Globe size={14} className="canvas-icon-html" />;
  if (lower.endsWith(".json") || lower.endsWith(".yaml") || lower.endsWith(".yml") || lower.endsWith(".toml")) {
    return <FileJson size={14} className="canvas-icon-json" />;
  }
  if (lower.endsWith(".md") || lower.endsWith(".txt")) return <FileText size={14} className="canvas-icon-md" />;
  if (lower.endsWith(".sh") || lower.endsWith("dockerfile") || lower.endsWith("makefile")) {
    return <Terminal size={14} className="canvas-icon-sh" />;
  }
  return <FileCode2 size={14} className="canvas-icon-code" />;
}

export function CodeCanvas({
  title,
  aiFiles,
  streaming,
  selectedPath,
  onSelectPath,
  onClose,
  onQuickPrompt,
}: CodeCanvasProps) {
  // User overrides (edited content or custom added files) and deleted custom paths
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [customFiles, setCustomFiles] = useState<Record<string, CanvasFile>>({});
  const [viewMode, setViewMode] = useState<"code" | "preview">("code");
  const [expanded, setExpanded] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [zipDone, setZipDone] = useState(false);
  const [addingFile, setAddingFile] = useState(false);
  const [newFileName, setNewFileName] = useState("");
  const [previewNonce, setPreviewNonce] = useState(0);

  const editorRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);

  // Merge AI files with user edits and custom files
  const files = useMemo<CanvasFile[]>(() => {
    const map = new Map<string, CanvasFile>();
    for (const file of aiFiles) {
      const editedContent = overrides[file.path];
      map.set(file.path, {
        ...file,
        content: editedContent !== undefined && !file.streaming ? editedContent : file.content,
      });
    }
    for (const [path, custom] of Object.entries(customFiles)) {
      if (!map.has(path)) {
        map.set(path, {
          ...custom,
          content: overrides[path] ?? custom.content,
        });
      }
    }
    return Array.from(map.values());
  }, [aiFiles, overrides, customFiles]);

  const streamingFile = useMemo(() => files.find(file => file.streaming), [files]);

  // Keep active file in sync: follow streaming file while generating, else respect user selection
  const activeFile = useMemo<CanvasFile | null>(() => {
    if (!files.length) return null;
    if (streaming && streamingFile) return streamingFile;
    if (selectedPath) {
      const found = files.find(file => file.path === selectedPath);
      if (found) return found;
    }
    return files[0];
  }, [files, selectedPath, streaming, streamingFile]);

  const previewHtml = useMemo(() => buildCanvasPreviewHtml(files), [files]);
  const canPreview = previewHtml !== null;

  // Auto-scroll editor while active file is streaming
  useEffect(() => {
    if (activeFile?.streaming && editorRef.current) {
      editorRef.current.scrollTop = editorRef.current.scrollHeight;
      if (gutterRef.current) {
        gutterRef.current.scrollTop = editorRef.current.scrollHeight;
      }
    }
  }, [activeFile?.content, activeFile?.streaming]);

  const lineCount = useMemo(() => {
    if (!activeFile) return 1;
    return Math.max(1, activeFile.content.split("\n").length);
  }, [activeFile]);

  const aiOriginalContent = useMemo(() => {
    if (!activeFile) return undefined;
    return aiFiles.find(item => item.path === activeFile.path)?.content;
  }, [aiFiles, activeFile]);

  const isActiveModified =
    !!activeFile &&
    !activeFile.streaming &&
    overrides[activeFile.path] !== undefined &&
    aiOriginalContent !== undefined &&
    overrides[activeFile.path] !== aiOriginalContent;

  const isCustomOnly =
    !!activeFile &&
    customFiles[activeFile.path] !== undefined &&
    !aiFiles.some(item => item.path === activeFile.path);

  function updateActiveContent(value: string) {
    if (!activeFile || activeFile.streaming) return;
    setOverrides(old => ({ ...old, [activeFile.path]: value }));
  }

  function resetActiveFile() {
    if (!activeFile) return;
    setOverrides(old => {
      const next = { ...old };
      delete next[activeFile.path];
      return next;
    });
  }

  function removeCustomFile(path: string) {
    setCustomFiles(old => {
      const next = { ...old };
      delete next[path];
      return next;
    });
    setOverrides(old => {
      const next = { ...old };
      delete next[path];
      return next;
    });
  }

  function handleCreateFile() {
    const clean = sanitizeFilePath(newFileName);
    if (!clean) return;
    const lang = inferLanguageFromPath(clean, "text");
    setCustomFiles(old => ({
      ...old,
      [clean]: { path: clean, language: lang, content: "" },
    }));
    onSelectPath(clean);
    setViewMode("code");
    setNewFileName("");
    setAddingFile(false);
  }

  function handleEditorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Tab" && activeFile && !activeFile.streaming) {
      event.preventDefault();
      const target = event.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const nextValue = activeFile.content.slice(0, start) + "  " + activeFile.content.slice(end);
      updateActiveContent(nextValue);
      requestAnimationFrame(() => {
        target.selectionStart = target.selectionEnd = start + 2;
      });
    }
  }

  async function copyActiveFile() {
    if (!activeFile) return;
    try {
      await navigator.clipboard.writeText(activeFile.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  function downloadActiveFile() {
    if (!activeFile) return;
    const name = activeFile.path.split("/").pop() || "code.txt";
    const blob = new Blob([activeFile.content], { type: "text/plain;charset=utf-8" });
    triggerBlobDownload(blob, name);
  }

  function downloadZip() {
    if (!files.length) return;
    const zipBlob = createZipBlob(files.map(file => ({ path: file.path, content: file.content })));
    triggerBlobDownload(zipBlob, `${slugifyTitle(title)}.zip`);
    setZipDone(true);
    setTimeout(() => setZipDone(false), 2200);
  }

  return (
    <aside
      className={`code-canvas ${expanded ? "is-expanded" : ""}`}
      aria-label="Canvas de code multi-fichiers"
    >
      <header className="code-canvas-header">
        <div className="code-canvas-brand">
          <span className="code-canvas-badge" aria-hidden="true">
            <Code2 size={17} />
          </span>
          <div className="code-canvas-title-wrap">
            <div className="code-canvas-eyebrow">
              <span>CANVAS CODE</span>
              {files.length > 0 && (
                <span className="code-canvas-file-count">
                  {files.length} fichier{files.length > 1 ? "s" : ""}
                </span>
              )}
              {streaming && (
                <span className="code-canvas-streaming-pill">
                  <LoaderCircle size={11} className="spin" />
                  Écriture en direct…
                </span>
              )}
            </div>
            <h2>{title || "Nouveau projet Canvas"}</h2>
          </div>
        </div>

        <div className="code-canvas-actions">
          {files.length > 0 && (
            <div className="code-canvas-mode-switch" role="tablist" aria-label="Affichage du Canvas">
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "code"}
                className={viewMode === "code" ? "is-active" : ""}
                onClick={() => setViewMode("code")}
              >
                <Code2 size={13} />
                <span>Éditeur</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "preview"}
                className={viewMode === "preview" ? "is-active" : ""}
                disabled={!canPreview}
                title={canPreview ? "Exécuter l'aperçu web interactif" : "Ajoutez un fichier HTML pour activer l'aperçu web"}
                onClick={() => setViewMode("preview")}
              >
                <Play size={13} />
                <span>Aperçu</span>
              </button>
            </div>
          )}

          <button
            type="button"
            className="code-canvas-zip-button"
            disabled={!files.length}
            onClick={downloadZip}
            title="Télécharger tous les fichiers du projet dans une archive .zip"
          >
            {zipDone ? <Check size={14} /> : <FolderArchive size={14} />}
            <span>{zipDone ? "ZIP téléchargé" : "Télécharger .zip"}</span>
          </button>

          <button
            type="button"
            className="code-canvas-icon-btn"
            aria-label={expanded ? "Réduire la largeur du Canvas" : "Agrandir le Canvas"}
            title={expanded ? "Réduire la largeur du Canvas" : "Agrandir le Canvas"}
            onClick={() => setExpanded(old => !old)}
          >
            {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>

          <button
            type="button"
            className="code-canvas-icon-btn"
            aria-label="Fermer le Canvas"
            title="Fermer le Canvas"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>
      </header>

      {!files.length ? (
        <div className="code-canvas-empty">
          <div className="code-canvas-empty-orb">
            <Code2 size={30} strokeWidth={1.6} />
          </div>
          <h3>Votre espace Canvas multi-fichiers</h3>
          <p>
            Demandez une application, un site web, un script ou une architecture complète dans le tchat.
            Chaque fichier s’ouvrira ici en direct pour être édité, prévisualisé et téléchargé en <code>.zip</code>.
          </p>
          {onQuickPrompt && (
            <div className="code-canvas-quick-list">
              <span>Exemples de projets à générer :</span>
              {QUICK_CODE_PROMPTS.map(item => (
                <button
                  key={item.title}
                  type="button"
                  className="code-canvas-quick-card"
                  onClick={() => onQuickPrompt(item.prompt)}
                >
                  <div>
                    <strong>
                      <Sparkles size={13} />
                      {item.title}
                    </strong>
                    <small>{item.description}</small>
                  </div>
                  <span>Utiliser →</span>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : viewMode === "preview" && canPreview ? (
        <div className="code-canvas-preview-shell">
          <div className="code-canvas-preview-bar">
            <div className="code-canvas-preview-url">
              <Eye size={13} />
              <span>Aperçu interactif isolé (sandbox) · {files.find(f => /\.html?$/i.test(f.path))?.path ?? "index.html"}</span>
            </div>
            <div className="code-canvas-preview-tools">
              <button
                type="button"
                onClick={() => setPreviewNonce(n => n + 1)}
                title="Recharger l'aperçu"
              >
                <RefreshCw size={13} />
                <span>Relancer</span>
              </button>
              <button type="button" onClick={() => setViewMode("code")}>
                <Code2 size={13} />
                <span>Retour au code</span>
              </button>
            </div>
          </div>
          <iframe
            key={previewNonce}
            className="code-canvas-iframe"
            title="Aperçu de l'application Canvas"
            sandbox="allow-scripts allow-forms allow-modals"
            srcDoc={previewHtml ?? ""}
          />
        </div>
      ) : (
        <div className="code-canvas-workspace">
          {explorerOpen && (
            <nav className="code-canvas-explorer" aria-label="Fichiers du projet">
              <div className="code-canvas-explorer-header">
                <span>
                  <FolderTree size={13} />
                  FICHIERS ({files.length})
                </span>
                <button
                  type="button"
                  onClick={() => setAddingFile(old => !old)}
                  title="Ajouter un fichier au projet"
                  aria-label="Ajouter un fichier au projet"
                >
                  <FilePlus2 size={14} />
                </button>
              </div>

              {addingFile && (
                <div className="code-canvas-newfile">
                  <input
                    value={newFileName}
                    onChange={event => setNewFileName(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleCreateFile();
                      } else if (event.key === "Escape") {
                        setAddingFile(false);
                        setNewFileName("");
                      }
                    }}
                    placeholder="ex: src/utils.js"
                    aria-label="Chemin du nouveau fichier"
                    autoFocus
                  />
                  <button type="button" onClick={handleCreateFile} disabled={!sanitizeFilePath(newFileName)}>
                    Créer
                  </button>
                </div>
              )}

              <ul className="code-canvas-file-list">
                {files.map(file => {
                  const isSelected = activeFile?.path === file.path;
                  const isEdited = overrides[file.path] !== undefined;
                  return (
                    <li key={file.path}>
                      <button
                        type="button"
                        className={`code-canvas-file-item ${isSelected ? "is-active" : ""}`}
                        onClick={() => onSelectPath(file.path)}
                      >
                        <FileIcon path={file.path} />
                        <span className="code-canvas-file-path" title={file.path}>
                          {file.path}
                        </span>
                        {file.streaming ? (
                          <LoaderCircle size={12} className="spin canvas-file-spinner" />
                        ) : isEdited ? (
                          <span className="canvas-edited-dot" title="Modifié dans l'éditeur" />
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </nav>
          )}

          <div className="code-canvas-editor-pane">
            <div className="code-canvas-tabs">
              <button
                type="button"
                className={`code-canvas-explorer-toggle ${explorerOpen ? "is-active" : ""}`}
                onClick={() => setExplorerOpen(old => !old)}
                title={explorerOpen ? "Masquer l'arborescence" : "Afficher l'arborescence"}
                aria-label={explorerOpen ? "Masquer l'arborescence" : "Afficher l'arborescence"}
              >
                <FolderTree size={14} />
              </button>
              <div className="code-canvas-tab-scroll" role="tablist" aria-label="Onglets des fichiers">
                {files.map(file => {
                  const isSelected = activeFile?.path === file.path;
                  const baseName = file.path.split("/").pop() ?? file.path;
                  return (
                    <button
                      key={file.path}
                      type="button"
                      role="tab"
                      aria-selected={isSelected}
                      className={`code-canvas-tab ${isSelected ? "is-active" : ""}`}
                      onClick={() => onSelectPath(file.path)}
                      title={file.path}
                    >
                      <FileIcon path={file.path} />
                      <span>{baseName}</span>
                      {file.streaming && <LoaderCircle size={11} className="spin" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {activeFile && (
              <>
                <div className="code-canvas-filebar">
                  <div className="code-canvas-filebar-left">
                    <FileIcon path={activeFile.path} />
                    <strong className="code-canvas-filepath">{activeFile.path}</strong>
                    <span className="code-canvas-lang-badge">{activeFile.language}</span>
                    <span className="code-canvas-metrics">
                      {lineCount} ligne{lineCount > 1 ? "s" : ""} · {activeFile.content.length} car.
                    </span>
                    {isActiveModified && <span className="code-canvas-modified-pill">Modifié</span>}
                  </div>
                  <div className="code-canvas-filebar-right">
                    {isActiveModified && (
                      <button
                        type="button"
                        onClick={resetActiveFile}
                        title="Restaurer la version générée par l'IA"
                      >
                        <RotateCcw size={13} />
                        <span>Réinitialiser</span>
                      </button>
                    )}
                    {isCustomOnly && (
                      <button
                        type="button"
                        onClick={() => removeCustomFile(activeFile.path)}
                        title="Supprimer ce fichier ajouté"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                    <button type="button" onClick={() => void copyActiveFile()}>
                      {copied ? <Check size={13} /> : <Copy size={13} />}
                      <span>{copied ? "Copié" : "Copier"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={downloadActiveFile}
                      title="Télécharger uniquement ce fichier"
                    >
                      <Download size={13} />
                      <span>Fichier</span>
                    </button>
                  </div>
                </div>

                <div className="code-canvas-editor-body">
                  <div className="code-canvas-gutter" ref={gutterRef} aria-hidden="true">
                    {Array.from({ length: lineCount }, (_, idx) => (
                      <span key={idx + 1}>{idx + 1}</span>
                    ))}
                  </div>
                  <textarea
                    ref={editorRef}
                    className="code-canvas-textarea"
                    value={activeFile.content}
                    onChange={event => updateActiveContent(event.target.value)}
                    onKeyDown={handleEditorKeyDown}
                    onScroll={event => {
                      if (gutterRef.current) {
                        gutterRef.current.scrollTop = event.currentTarget.scrollTop;
                      }
                    }}
                    readOnly={Boolean(activeFile.streaming)}
                    spellCheck={false}
                    autoCapitalize="off"
                    autoComplete="off"
                    autoCorrect="off"
                    aria-label={`Éditeur de code pour ${activeFile.path}`}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

