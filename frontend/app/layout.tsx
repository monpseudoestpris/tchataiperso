import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import "./design-tokens.css";
import "./interface-themes.css";
import "./editorial-shell.css";
import "./editorial-modals.css";
import "./editorial-finance.css";
import { InterfaceThemeSync } from "@/components/interface-theme-sync";
import { interfaceThemeBootstrap } from "@/lib/interface-themes";

export const metadata: Metadata = {
  title: "clAIr — votre espace IA",
  description: "Un espace personnel pour discuter, explorer et garder le fil avec vos modèles IA.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <script dangerouslySetInnerHTML={{ __html: interfaceThemeBootstrap }} />
      </head>
      <body>
        <InterfaceThemeSync />
        {children}
      </body>
    </html>
  );
}
