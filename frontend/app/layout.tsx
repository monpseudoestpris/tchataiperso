import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import "./interface-themes.css";
import { InterfaceThemeSync } from "@/components/interface-theme-sync";
import { interfaceThemeBootstrap } from "@/lib/interface-themes";

export const metadata: Metadata = {
  title: "clAIr — votre espace IA",
  description: "Un espace personnel pour discuter, explorer et garder le fil avec vos modèles IA.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fr" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: interfaceThemeBootstrap }} /></head><body><InterfaceThemeSync />{children}</body></html>;
}
