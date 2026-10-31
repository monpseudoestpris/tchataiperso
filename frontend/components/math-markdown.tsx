"use client";

import React, { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

const CODE_SEGMENT_RE = /((?:^|\n)(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n(?:`{3,}|~{3,})(?=\n|$)|$)|`+[^`]*?`+)/g;

function formatDisplayMathBlock(indent: string, math: string) {
  const body = math
    .trim()
    .split("\n")
    .map((line) => (line.trim() ? `${indent}${line.trim()}` : ""))
    .join("\n");
  return `${indent}$$\n${body}\n${indent}$$`;
}

export function normalizeMathMarkdown(content: string): string {
  if (!content) return "";
  return content
    .split(CODE_SEGMENT_RE)
    .map((part, index) => {
      if (index % 2 === 1) return part;
      return part
        .replace(/(^|\n)([ \t]*)\\\[([\s\S]*?)\\\](?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
          `${prefix}${formatDisplayMathBlock(indent, math)}`
        )
        .replace(/\\\[([\s\S]*?)\\\]/g, (_, math: string) => `\n$$\n${math.trim()}\n$$\n`)
        .replace(/(^|\n)([ \t]*)\$\$([^\n$]+?)\$\$(?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
          `${prefix}${formatDisplayMathBlock(indent, math)}`
        )
        .replace(/(^|\n)([ \t]*)\[[ \t]*\n([\s\S]*?\\[a-zA-Z]+[\s\S]*?)\n[ \t]*\](?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
          `${prefix}${formatDisplayMathBlock(indent, math)}`
        )
        .replace(/\\\(([\s\S]*?)\\\)/g, (_, math: string) => `$${math.trim().replace(/\s*\n\s*/g, " ")}$`);
    })
    .join("");
}

const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins: NonNullable<React.ComponentProps<typeof ReactMarkdown>["rehypePlugins"]> = [
  [rehypeKatex, { throwOnError: false, strict: "ignore", errorColor: "#8b5cf6" }],
];

type MathMarkdownProps = {
  content: string;
  className?: string;
  inline?: boolean;
};

export const MathMarkdown = memo(function MathMarkdown({
  content,
  className = "",
  inline = false,
}: MathMarkdownProps) {
  if (!content) return null;
  const normalized = normalizeMathMarkdown(content);

  if (inline) {
    return (
      <span className={`math-markdown is-inline ${className}`.trim()}>
        <ReactMarkdown
          remarkPlugins={remarkPlugins}
          rehypePlugins={rehypePlugins}
          components={{
            p: ({ children }) => <>{children}</>,
          }}
        >
          {normalized}
        </ReactMarkdown>
      </span>
    );
  }

  return (
    <div className={`math-markdown ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          p: ({ children }) => <p className="math-markdown-p">{children}</p>,
        }}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
});

