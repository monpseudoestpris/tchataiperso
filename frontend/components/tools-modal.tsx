"use client";

import {
  BookOpen,
  Bot,
  Brain,
  Code2,
  Compass,
  Film,
  Globe,
  GraduationCap,
  ImagePlus,
  LayoutGrid,
  Newspaper,
  Pause,
  Play,
  Sparkles,
  TrendingUp,
  Users,
  Volume2,
  X,
  ArrowRight,
} from "lucide-react";
import styles from "./tools-modal.module.css";

export interface ToolsModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Triggers for specific tools
  onOpenDeepSearch: () => void;
  onOpenLearn: () => void;
  onOpenBlog: () => void;
  onOpenCanvas: () => void;
  onOpenImageStudio: () => void;
  onOpenSoundStudio: () => void;
  onOpenMultiAgent: () => void;
  onOpenStudy: () => void;
  onOpenFinance: () => void;
  onOpenWebPages?: () => void;
  onOpenHermes?: () => void;
  onOpenVisualDocs?: () => void;
  onOpenVideos?: () => void;
  // Tool state badges
  canvasFilesCount: number;
  visualDocsCount?: number;
  savedVideosCount?: number;
  isMultiAgentActive: boolean;
  // Memory toggle
  autoMemoryEnabled: boolean;
  onToggleAutoMemory: () => void;
}

export function ToolsModal({
  isOpen,
  onClose,
  onOpenDeepSearch,
  onOpenLearn,
  onOpenBlog,
  onOpenCanvas,
  onOpenImageStudio,
  onOpenSoundStudio,
  onOpenMultiAgent,
  onOpenStudy,
  onOpenFinance,
  onOpenWebPages,
  onOpenHermes,
  onOpenVisualDocs,
  onOpenVideos,
  canvasFilesCount,
  visualDocsCount = 0,
  savedVideosCount = 0,
  isMultiAgentActive,
  autoMemoryEnabled,
  onToggleAutoMemory,
}: ToolsModalProps) {
  if (!isOpen) return null;

  function handleSelect(action: () => void) {
    onClose();
    action();
  }

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tools-modal-title"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <LayoutGrid size={22} />
            </div>
            <div>
              <h2 id="tools-modal-title" className={styles.headerTitle}>
                Boîte à outils & Studios IA
              </h2>
              <p className={styles.headerSubtitle}>
                Accédez à tous vos studios de création, modes de recherche et outils d&apos;apprentissage.
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Fermer la boîte à outils"
            title="Fermer"
          >
            <X size={18} />
          </button>
        </header>

        <div className={styles.body}>
          {/* Carte Mémorisation continue */}
          <div className={`${styles.memoryCard} ${!autoMemoryEnabled ? styles.isPaused : ""}`}>
            <div className={styles.memoryCardLeft}>
              <div className={styles.memoryCardIcon}>
                <Brain size={20} />
              </div>
              <div className={styles.memoryCardContent}>
                <div className={styles.memoryCardTitleRow}>
                  <span className={styles.memoryCardTitle}>Mémorisation continue</span>
                  <span className={`${styles.memoryStatusBadge} ${!autoMemoryEnabled ? styles.paused : ""}`}>
                    <span className={styles.memoryStatusDot} />
                    {autoMemoryEnabled ? "Active" : "En pause"}
                  </span>
                </div>
                <p className={styles.memoryCardDesc}>
                  {autoMemoryEnabled
                    ? "L'assistant IA mémorise automatiquement vos préférences, compétences et informations clés au fil des échanges."
                    : "La capture de souvenirs est suspendue. Aucun nouveau fait ne sera enregistré dans votre mémoire."}
                </p>
              </div>
            </div>
            <button
              type="button"
              className={`${styles.memoryToggleButton} ${autoMemoryEnabled ? styles.btnActive : styles.btnPaused}`}
              onClick={onToggleAutoMemory}
              title={autoMemoryEnabled ? "Mettre la mémorisation en pause à la demande" : "Activer la mémorisation automatique"}
            >
              {autoMemoryEnabled ? (
                <>
                  <Pause size={14} />
                  <span>Désactiver</span>
                </>
              ) : (
                <>
                  <Play size={14} />
                  <span>Activer</span>
                </>
              )}
            </button>
          </div>

          <div>
            <h3 className={styles.sectionTitle}>Studios & Espaces Dédiés</h3>
            <div className={styles.grid}>
              {/* Mes Vidéos (YouTube · Transcripts & Résumés) */}
              {onOpenVideos && (
                <button
                  type="button"
                  className={styles.toolCard}
                  onClick={() => handleSelect(onOpenVideos)}
                  title="Ouvrir votre espace Mes Vidéos : liens YouTube, transcriptions intégrales et résumés IA"
                >
                  <div className={styles.toolCardHeader}>
                    <div className={`${styles.toolIconWrap} ${styles.toneCrimson}`}>
                      <Film size={19} />
                    </div>
                    {savedVideosCount > 0 ? (
                      <span className={`${styles.toolTag} ${styles.active}`}>
                        {savedVideosCount} vidéo{savedVideosCount > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span className={styles.toolTag}>YouTube · Transcript</span>
                    )}
                  </div>
                  <h4 className={styles.toolTitle}>Mes Vidéos</h4>
                  <p className={styles.toolDesc}>
                    Retrouvez toutes vos vidéos YouTube importées : titres, liens, transcriptions intégrales et résumés structurés.
                  </p>
                  <div className={styles.toolActionRow}>
                    <span>Ouvrir ma vidéothèque</span>
                    <ArrowRight size={14} />
                  </div>
                </button>
              )}

              {/* Documents Illustrés (Mistral OCR + Schémas WebP) */}
              {onOpenVisualDocs && (
                <button
                  type="button"
                  className={styles.toolCard}
                  onClick={() => handleSelect(onOpenVisualDocs)}
                  title="Ingérer un PDF ou une série d'images (règles de jeu, manuels) avec Mistral OCR et schémas WebP"
                >
                  <div className={styles.toolCardHeader}>
                    <div className={`${styles.toolIconWrap} ${styles.toneAccent}`}>
                      <BookOpen size={19} />
                    </div>
                    {visualDocsCount > 0 ? (
                      <span className={`${styles.toolTag} ${styles.active}`}>
                        {visualDocsCount} actif{visualDocsCount > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span className={styles.toolTag}>Mistral OCR · WebP</span>
                    )}
                  </div>
                  <h4 className={styles.toolTitle}>Documents Illustrés</h4>
                  <p className={styles.toolDesc}>
                    Ingérez un PDF ou des photos de livret (règles de jeu, manuels) : réponses illustrées en direct avec schémas et pages cliquables [p. X].
                  </p>
                  <div className={styles.toolActionRow}>
                    <span>Ingérer ou interroger</span>
                    <ArrowRight size={14} />
                  </div>
                </button>
              )}

              {/* Hermes Agent */}
              {onOpenHermes && (
                <button
                  type="button"
                  className={styles.toolCard}
                  onClick={() => handleSelect(onOpenHermes)}
                  title="Ouvrir Hermes Agent (Nous Research)"
                >
                  <div className={styles.toolCardHeader}>
                    <div className={`${styles.toolIconWrap} ${styles.toneAccent}`}>
                      <Bot size={19} />
                    </div>
                    <span className={styles.toolTag}>Nous Research · Agent</span>
                  </div>
                  <h4 className={styles.toolTitle}>Hermes Agent</h4>
                  <p className={styles.toolDesc}>
                    Agent autonome à boucle d&apos;outils, mémoire persistante USER.md et création de compétences.
                  </p>
                  <div className={styles.toolActionRow}>
                    <span>Lancer une mission</span>
                    <ArrowRight size={14} />
                  </div>
                </button>
              )}

              {/* cLAIr Pages */}
              {onOpenWebPages && (
                <button
                  type="button"
                  className={styles.toolCard}
                  onClick={() => handleSelect(onOpenWebPages)}
                  title="Ouvrir cLAIr Pages"
                >
                  <div className={styles.toolCardHeader}>
                    <div className={`${styles.toolIconWrap} ${styles.toneInfo}`}>
                      <Globe size={19} />
                    </div>
                    <span className={styles.toolTag}>HTML5 · Autonome</span>
                  </div>
                  <h4 className={styles.toolTitle}>cLAIr Pages</h4>
                  <p className={styles.toolDesc}>
                    Générateur de pages web interactives autonomes (HTML/CSS/SVG/JS) sans serveur ni compilation.
                  </p>
                  <div className={styles.toolActionRow}>
                    <span>Générer une page web</span>
                    <ArrowRight size={14} />
                  </div>
                </button>
              )}

              {/* DeepSearch */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenDeepSearch)}
                title="Ouvrir DeepSearch"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneInfo}`}>
                    <Compass size={19} />
                  </div>
                  <span className={styles.toolTag}>SearXNG</span>
                </div>
                <h4 className={styles.toolTitle}>DeepSearch</h4>
                <p className={styles.toolDesc}>
                  Recherche approfondie multi-sources, analyse critique et grands rapports HTML structurés.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Consulter les rapports</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Cours & Didactique */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenLearn)}
                title="Ouvrir mes cours et formations"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneEmerald}`}>
                    <GraduationCap size={19} />
                  </div>
                  <span className={styles.toolTag}>Apprentissage</span>
                </div>
                <h4 className={styles.toolTitle}>Cours & Formations</h4>
                <p className={styles.toolDesc}>
                  Conception de cours didactiques pas-à-pas, fiches de révision et exercices interactifs.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Accéder aux cours</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Mode Réviser */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenStudy)}
                title="Ouvrir le Mode Réviser"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneEmerald}`}>
                    <Sparkles size={19} />
                  </div>
                  <span className={styles.toolTag}>3D & Quiz</span>
                </div>
                <h4 className={styles.toolTitle}>Mode Réviser</h4>
                <p className={styles.toolDesc}>
                  Flashcards 3D animées, Quizz interactifs et textes à trous extraits de vos échanges.
                </p>
                <div className={styles.toolActionRow}>
                  <span>S&apos;entraîner</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Canvas Code */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenCanvas)}
                title="Ouvrir le Canvas Code"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneAccent}`}>
                    <Code2 size={19} />
                  </div>
                  {canvasFilesCount > 0 ? (
                    <span className={`${styles.toolTag} ${styles.active}`}>
                      {canvasFilesCount} fichier{canvasFilesCount > 1 ? "s" : ""}
                    </span>
                  ) : (
                    <span className={styles.toolTag}>Éditeur</span>
                  )}
                </div>
                <h4 className={styles.toolTitle}>Canvas Code</h4>
                <p className={styles.toolDesc}>
                  Éditeur multi-fichiers interactif avec aperçu en direct et téléchargement .zip.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Ouvrir le Canvas</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Studio Image */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenImageStudio)}
                title="Ouvrir le Studio Image"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneCrimson}`}>
                    <ImagePlus size={19} />
                  </div>
                  <span className={styles.toolTag}>Studio IA</span>
                </div>
                <h4 className={styles.toolTitle}>Studio Image</h4>
                <p className={styles.toolDesc}>
                  Génération et retouche d&apos;illustrations artistiques et visuels haute résolution.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Créer des images</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Sons & Musique */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenSoundStudio)}
                title="Ouvrir le Studio Son & Musique"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneAmber}`}>
                    <Volume2 size={19} />
                  </div>
                  <span className={styles.toolTag}>ElevenLabs</span>
                </div>
                <h4 className={styles.toolTitle}>Sons & Musique</h4>
                <p className={styles.toolDesc}>
                  Création d&apos;effets sonores immersifs et composition de pistes musicales via IA.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Composer de l&apos;audio</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Conseil Multi-Agents */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenMultiAgent)}
                title="Ouvrir le Conseil Multi-Agents"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneAccent}`}>
                    <Users size={19} />
                  </div>
                  {isMultiAgentActive ? (
                    <span className={`${styles.toolTag} ${styles.active}`}>Actif</span>
                  ) : (
                    <span className={styles.toolTag}>Délibération</span>
                  )}
                </div>
                <h4 className={styles.toolTitle}>Conseil IA</h4>
                <p className={styles.toolDesc}>
                  Débat contradictoire ou synthèse collaborative entre plusieurs modèles et experts IA.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Configurer le conseil</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Blogs d'actualité */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenBlog)}
                title="Ouvrir mes blogs"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneAmber}`}>
                    <Newspaper size={19} />
                  </div>
                  <span className={styles.toolTag}>Veille web</span>
                </div>
                <h4 className={styles.toolTitle}>Blogs d&apos;actualité</h4>
                <p className={styles.toolDesc}>
                  Synthèses d&apos;articles et veille d&apos;actualité générées automatiquement via SearXNG.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Lire les articles</span>
                  <ArrowRight size={14} />
                </div>
              </button>

              {/* Marchés & Bourse */}
              <button
                type="button"
                className={styles.toolCard}
                onClick={() => handleSelect(onOpenFinance)}
                title="Ouvrir le tableau de bord financier"
              >
                <div className={styles.toolCardHeader}>
                  <div className={`${styles.toolIconWrap} ${styles.toneEmerald}`}>
                    <TrendingUp size={19} />
                  </div>
                  <span className={styles.toolTag}>Cotations</span>
                </div>
                <h4 className={styles.toolTitle}>Marchés Financiers</h4>
                <p className={styles.toolDesc}>
                  Courbes de cours boursiers en direct, graphiques interactifs et bilans Yahoo Finance.
                </p>
                <div className={styles.toolActionRow}>
                  <span>Voir les cotations</span>
                  <ArrowRight size={14} />
                </div>
              </button>
            </div>
          </div>
        </div>

        <footer className={styles.footer}>
          <span className={styles.footerHint}>
            Astuce : vous pouvez aussi déclencher les modes de recherche directement depuis la barre de saisie.
          </span>
          <button type="button" className={styles.footerCloseBtn} onClick={onClose}>
            Fermer
          </button>
        </footer>
      </div>
    </div>
  );
}

