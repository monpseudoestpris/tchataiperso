export type CanvasFile = {
  path: string;
  language: string;
  content: string;
  streaming?: boolean;
};

const DEFAULT_EXT_BY_LANG: Record<string, { name: string; ext: string }> = {
  html: { name: "index.html", ext: "html" },
  htm: { name: "index.html", ext: "html" },
  css: { name: "styles.css", ext: "css" },
  scss: { name: "styles.scss", ext: "scss" },
  javascript: { name: "app.js", ext: "js" },
  js: { name: "app.js", ext: "js" },
  jsx: { name: "App.jsx", ext: "jsx" },
  typescript: { name: "app.ts", ext: "ts" },
  ts: { name: "app.ts", ext: "ts" },
  tsx: { name: "App.tsx", ext: "tsx" },
  python: { name: "main.py", ext: "py" },
  py: { name: "main.py", ext: "py" },
  json: { name: "package.json", ext: "json" },
  markdown: { name: "README.md", ext: "md" },
  md: { name: "README.md", ext: "md" },
  sql: { name: "schema.sql", ext: "sql" },
  bash: { name: "run.sh", ext: "sh" },
  sh: { name: "run.sh", ext: "sh" },
  shell: { name: "run.sh", ext: "sh" },
  yaml: { name: "config.yaml", ext: "yaml" },
  yml: { name: "config.yml", ext: "yml" },
  rust: { name: "main.rs", ext: "rs" },
  rs: { name: "main.rs", ext: "rs" },
  go: { name: "main.go", ext: "go" },
  java: { name: "Main.java", ext: "java" },
  c: { name: "main.c", ext: "c" },
  cpp: { name: "main.cpp", ext: "cpp" },
  csharp: { name: "Program.cs", ext: "cs" },
  cs: { name: "Program.cs", ext: "cs" },
  php: { name: "index.php", ext: "php" },
  ruby: { name: "app.rb", ext: "rb" },
  svg: { name: "icon.svg", ext: "svg" },
};

const LANG_BY_EXT: Record<string, string> = {
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  jsx: "jsx",
  ts: "typescript",
  tsx: "tsx",
  py: "python",
  json: "json",
  md: "markdown",
  sql: "sql",
  sh: "bash",
  yaml: "yaml",
  yml: "yaml",
  rs: "rust",
  go: "go",
  java: "java",
  c: "c",
  cpp: "cpp",
  cs: "csharp",
  php: "php",
  rb: "ruby",
  svg: "svg",
  toml: "toml",
  dockerfile: "dockerfile",
};

export function sanitizeFilePath(raw: string): string {
  const cleaned = raw
    .trim()
    .replace(/^['"`]+|['"`]+$/g, "")
    .replace(/\\/g, "/")
    .replace(/^\.\/+/, "")
    .replace(/^\/+/, "");
  const parts = cleaned
    .split("/")
    .map(segment => segment.trim())
    .filter(segment => segment.length > 0 && segment !== "." && segment !== "..");
  return parts.join("/").slice(0, 180);
}

function looksLikeFilePath(candidate: string): boolean {
  const cleaned = sanitizeFilePath(candidate);
  if (!cleaned || cleaned.includes(" ") || cleaned.length > 140) return false;
  if (/^(https?:|mailto:|ftp:)/i.test(cleaned)) return false;
  if (/^(Dockerfile|Makefile|\.env(?:\.example)?|\.gitignore)$/i.test(cleaned)) return true;
  return /^[a-zA-Z0-9_.-]+(?:\/[a-zA-Z0-9_.-]+)*\.[a-zA-Z0-9]{1,10}$/.test(cleaned);
}

export function inferLanguageFromPath(path: string, fallback = "text"): string {
  const base = path.split("/").pop()?.toLowerCase() ?? "";
  if (base === "dockerfile") return "dockerfile";
  const ext = base.includes(".") ? base.split(".").pop() ?? "" : "";
  return LANG_BY_EXT[ext] ?? (fallback || "text");
}

function parseFenceHeader(info: string, precedingText: string, firstCodeLine: string): {
  language: string;
  explicitPath: string | null;
  stripFirstLine: boolean;
} {
  const trimmedInfo = info.trim();
  let language = "";
  let explicitPath: string | null = null;
  let stripFirstLine = false;

  // 1. Attribute style: path="...", file="...", filename="...", title="..."
  const attrMatch = trimmedInfo.match(/(?:path|file|filename|title)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s"']+))/i);
  if (attrMatch) {
    const candidate = attrMatch[1] ?? attrMatch[2] ?? attrMatch[3] ?? "";
    if (looksLikeFilePath(candidate)) {
      explicitPath = sanitizeFilePath(candidate);
    }
  }

  const withoutAttrs = trimmedInfo
    .replace(/(?:path|file|filename|title)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"']+)/gi, "")
    .trim();
  const tokens = withoutAttrs.split(/\s+/).filter(Boolean);

  if (tokens.length > 0) {
    const first = tokens[0];
    // 2. Colon style: tsx:src/App.tsx or python:main.py
    if (first.includes(":")) {
      const [langPart, ...restParts] = first.split(":");
      const pathPart = restParts.join(":");
      language = langPart.toLowerCase();
      if (!explicitPath && looksLikeFilePath(pathPart)) {
        explicitPath = sanitizeFilePath(pathPart);
      }
    } else if (looksLikeFilePath(first) && !DEFAULT_EXT_BY_LANG[first.toLowerCase()]) {
      if (!explicitPath) explicitPath = sanitizeFilePath(first);
      language = inferLanguageFromPath(explicitPath, "");
    } else {
      language = first.toLowerCase();
    }

    if (!explicitPath && tokens.length > 1) {
      for (const token of tokens.slice(1)) {
        if (looksLikeFilePath(token)) {
          explicitPath = sanitizeFilePath(token);
          break;
        }
      }
    }
  }

  // 3. First line comment inside the code block: // filepath: src/app.js or # file: main.py
  if (!explicitPath && firstCodeLine) {
    const commentMatch = firstCodeLine.match(
      /^\s*(?:\/\/|#|<!--|\/\*+)\s*(?:filepath|file|path|filename|fichier)?\s*:?\s*([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]{1,10})\s*(?:-->|\*+\/)?\s*$/i,
    );
    if (commentMatch && looksLikeFilePath(commentMatch[1])) {
      explicitPath = sanitizeFilePath(commentMatch[1]);
      stripFirstLine = true;
    }
  }

  // 4. Preceding markdown line right before the code fence (e.g. ### `src/App.tsx` or **index.html**)
  if (!explicitPath && precedingText) {
    const lines = precedingText.trimEnd().split(/\r?\n/);
    const lastLine = (lines[lines.length - 1] ?? "").trim();
    const backtickMatch = lastLine.match(/`([^`\n]+)`/);
    if (backtickMatch && looksLikeFilePath(backtickMatch[1])) {
      explicitPath = sanitizeFilePath(backtickMatch[1]);
    } else {
      const headingMatch = lastLine.match(
        /^(?:#{1,6}|\*\*|[-*•])?\s*(?:fichier|file|path)?\s*:?\s*\*?\*?([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]{1,10})\*?\*?\s*:?\s*$/i,
      );
      if (headingMatch && looksLikeFilePath(headingMatch[1])) {
        explicitPath = sanitizeFilePath(headingMatch[1]);
      }
    }
  }

  if (explicitPath && !language) {
    language = inferLanguageFromPath(explicitPath, "text");
  }

  return { language: language || "text", explicitPath, stripFirstLine };
}

/**
 * Extracts code files from an assistant markdown response (including an unclosed streaming fence).
 */
export function extractCanvasFiles(
  markdown: string,
  options: { isStreaming?: boolean; includeUnnamed?: boolean } = {},
): CanvasFile[] {
  const { isStreaming = false, includeUnnamed = false } = options;
  if (!markdown) return [];

  const filesByPath = new Map<string, CanvasFile>();
  const unnamedCounts = new Map<string, number>();

  const lines = markdown.split(/\r?\n/);
  let inFence = false;
  let fenceChar = "";
  let fenceLen = 0;
  let fenceInfo = "";
  let fenceLines: string[] = [];
  let precedingBuffer: string[] = [];

  function commitBlock(streamingBlock: boolean) {
    const firstLine = fenceLines[0] ?? "";
    const precedingText = precedingBuffer.slice(-3).join("\n");
    const { language, explicitPath, stripFirstLine } = parseFenceHeader(fenceInfo, precedingText, firstLine);
    const bodyLines = stripFirstLine ? fenceLines.slice(1) : fenceLines;
    const content = bodyLines.join("\n").replace(/\n+$/, "");

    // Ignore tiny inline-like snippets when unnamed unless explicitly in code mode
    if (!explicitPath && !includeUnnamed) return;
    if (!explicitPath && content.trim().length < 20 && !streamingBlock) return;

    let finalPath = explicitPath;
    if (!finalPath) {
      const def = DEFAULT_EXT_BY_LANG[language] ?? { name: `snippet.${language === "text" ? "txt" : language}`, ext: "txt" };
      const count = (unnamedCounts.get(def.name) ?? 0) + 1;
      unnamedCounts.set(def.name, count);
      if (count === 1 && !filesByPath.has(def.name)) {
        finalPath = def.name;
      } else {
        const dotIndex = def.name.lastIndexOf(".");
        const stem = dotIndex > 0 ? def.name.slice(0, dotIndex) : def.name;
        finalPath = `${stem}-${count}.${def.ext}`;
      }
    }

    filesByPath.set(finalPath, {
      path: finalPath,
      language: inferLanguageFromPath(finalPath, language),
      content,
      streaming: streamingBlock,
    });
  }

  for (const line of lines) {
    if (!inFence) {
      const openMatch = line.match(/^[ \t]*(`{3,}|~{3,})(.*)$/);
      if (openMatch) {
        inFence = true;
        fenceChar = openMatch[1][0];
        fenceLen = openMatch[1].length;
        fenceInfo = openMatch[2] ?? "";
        fenceLines = [];
      } else {
        precedingBuffer.push(line);
      }
    } else {
      const closeRegex = new RegExp(`^[ \\t]*${fenceChar}{${fenceLen},}[ \\t]*$`);
      if (closeRegex.test(line)) {
        commitBlock(false);
        inFence = false;
        fenceChar = "";
        fenceLen = 0;
        fenceInfo = "";
        fenceLines = [];
        precedingBuffer = [];
      } else {
        fenceLines.push(line);
      }
    }
  }

  if (inFence) {
    commitBlock(isStreaming);
  }

  return Array.from(filesByPath.values());
}

/**
 * Checks whether a message explicitly uses Canvas file paths (`path="..."`, etc.).
 */
export function hasExplicitCanvasFiles(markdown: string): boolean {
  return extractCanvasFiles(markdown, { isStreaming: true, includeUnnamed: false }).length > 0;
}

/**
 * Collects the cumulative project files across a conversation up to a target message.
 */
export function collectConversationCanvasFiles(
  messages: { id: string; role: string; content: string }[],
  targetMessageId?: string | null,
  streamingId?: string | null,
  forceIncludeUnnamed = false,
): CanvasFile[] {
  const merged = new Map<string, CanvasFile>();
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    const isTarget = !targetMessageId || message.id === targetMessageId;
    const isStreaming = streamingId === message.id;
    const explicit = extractCanvasFiles(message.content, { isStreaming, includeUnnamed: false });
    const files =
      explicit.length > 0
        ? explicit
        : isTarget && forceIncludeUnnamed
          ? extractCanvasFiles(message.content, { isStreaming, includeUnnamed: true })
          : [];
    for (const file of files) {
      merged.set(file.path, file);
    }
    if (targetMessageId && message.id === targetMessageId) break;
  }
  return Array.from(merged.values());
}

/**
 * Builds a self-contained HTML preview document if the Canvas files contain HTML (or CSS/JS).
 */
export function buildCanvasPreviewHtml(files: CanvasFile[]): string | null {
  if (!files.length) return null;
  const htmlFile =
    files.find(file => /(?:^|\/)index\.html?$/i.test(file.path)) ??
    files.find(file => /\.html?$/i.test(file.path));

  const cssFiles = files.filter(file => /\.css$/i.test(file.path));
  const jsFiles = files.filter(file => /\.(?:js|mjs)$/i.test(file.path));

  if (!htmlFile) return null;

  let doc = htmlFile.content;

  // Replace linked local stylesheets or inject them before </head>
  const combinedCss = cssFiles.map(file => `/* ${file.path} */\n${file.content}`).join("\n\n");
  if (combinedCss) {
    doc = doc.replace(/<link\b[^>]*rel=["']stylesheet["'][^>]*>/gi, match => {
      const hrefMatch = match.match(/href=["']([^"']+)["']/i);
      if (!hrefMatch) return match;
      const href = sanitizeFilePath(hrefMatch[1]);
      const found = cssFiles.some(file => file.path === href || file.path.endsWith(`/${href}`));
      return found ? "" : match;
    });
    const styleTag = `<style data-canvas-styles>\n${combinedCss}\n</style>`;
    if (/<\/head>/i.test(doc)) {
      doc = doc.replace(/<\/head>/i, `${styleTag}\n</head>`);
    } else {
      doc = `${styleTag}\n${doc}`;
    }
  }

  // Replace linked local scripts or inject them before </body>
  const combinedJs = jsFiles.map(file => `// ${file.path}\n${file.content}`).join("\n\n");
  if (combinedJs) {
    doc = doc.replace(/<script\b[^>]*src=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (match, src: string) => {
      if (/^(?:https?:|\/\/)/i.test(src)) return match;
      const normalized = sanitizeFilePath(src);
      const found = jsFiles.some(file => file.path === normalized || file.path.endsWith(`/${normalized}`));
      return found ? "" : match;
    });
    const scriptTag = `<script>\n${combinedJs}\n</script>`;
    if (/<\/body>/i.test(doc)) {
      doc = doc.replace(/<\/body>/i, `${scriptTag}\n</body>`);
    } else {
      doc = `${doc}\n${scriptTag}`;
    }
  }

  return doc;
}

// --- Pure client-side PKZIP builder (UTF-8 paths, nested folders, zero external deps) ---

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC32_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function dosDateTime(date = new Date()): { dosTime: number; dosDate: number } {
  const year = Math.max(1980, date.getFullYear());
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const seconds = Math.floor(date.getSeconds() / 2);
  const dosTime = ((hours & 0x1f) << 11) | ((minutes & 0x3f) << 5) | (seconds & 0x1f);
  const dosDate = (((year - 1980) & 0x7f) << 9) | ((month & 0x0f) << 5) | (day & 0x1f);
  return { dosTime, dosDate };
}

export function createZipBlob(files: { path: string; content: string }[]): Blob {
  const encoder = new TextEncoder();
  const { dosTime, dosDate } = dosDateTime();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const cleanPath = sanitizeFilePath(file.path) || "file.txt";
    const nameBytes = encoder.encode(cleanPath);
    const dataBytes = encoder.encode(file.content);
    const checksum = crc32(dataBytes);

    // Local file header (30 bytes + filename)
    const localHeader = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(localHeader.buffer);
    localView.setUint32(0, 0x04034b50, true); // PK\x03\x04
    localView.setUint16(4, 20, true); // Version needed (2.0)
    localView.setUint16(6, 0x0800, true); // Bit 11 = UTF-8 filename
    localView.setUint16(8, 0, true); // Store method (0)
    localView.setUint16(10, dosTime, true);
    localView.setUint16(12, dosDate, true);
    localView.setUint32(14, checksum, true);
    localView.setUint32(18, dataBytes.length, true);
    localView.setUint32(22, dataBytes.length, true);
    localView.setUint16(26, nameBytes.length, true);
    localView.setUint16(28, 0, true);
    localHeader.set(nameBytes, 30);

    localParts.push(localHeader, dataBytes);

    // Central directory file header (46 bytes + filename)
    const centralHeader = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(centralHeader.buffer);
    centralView.setUint32(0, 0x02014b50, true); // PK\x01\x02
    centralView.setUint16(4, 20, true); // Version made by
    centralView.setUint16(6, 20, true); // Version needed
    centralView.setUint16(8, 0x0800, true); // UTF-8 flag
    centralView.setUint16(10, 0, true); // Store method
    centralView.setUint16(12, dosTime, true);
    centralView.setUint16(14, dosDate, true);
    centralView.setUint32(16, checksum, true);
    centralView.setUint32(20, dataBytes.length, true);
    centralView.setUint32(24, dataBytes.length, true);
    centralView.setUint16(28, nameBytes.length, true);
    centralView.setUint16(30, 0, true); // Extra field length
    centralView.setUint16(32, 0, true); // File comment length
    centralView.setUint16(34, 0, true); // Disk number
    centralView.setUint16(36, 0, true); // Internal attributes
    centralView.setUint32(38, 0, true); // External attributes
    centralView.setUint32(42, offset, true); // Relative offset of local header
    centralHeader.set(nameBytes, 46);

    centralParts.push(centralHeader);
    offset += localHeader.length + dataBytes.length;
  }

  const centralSize = centralParts.reduce((acc, part) => acc + part.length, 0);
  const eocd = new Uint8Array(22);
  const eocdView = new DataView(eocd.buffer);
  eocdView.setUint32(0, 0x06054b50, true); // PK\x05\x06
  eocdView.setUint16(4, 0, true);
  eocdView.setUint16(6, 0, true);
  eocdView.setUint16(8, files.length, true);
  eocdView.setUint16(10, files.length, true);
  eocdView.setUint32(12, centralSize, true);
  eocdView.setUint32(16, offset, true);
  eocdView.setUint16(20, 0, true);

  return new Blob([...localParts, ...centralParts, eocd] as BlobPart[], { type: "application/zip" });
}

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

