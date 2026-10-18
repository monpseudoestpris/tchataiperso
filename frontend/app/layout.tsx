// @ts-nocheck
import type { Metadata } from "next";
// @ts-expect-error Next.js handles this global stylesheet import.
import "./globals.css";

export const metadata: Metadata = {
  title: "clAIr — votre espace IA",
  description: "Un espace personnel pour discuter, explorer et garder le fil avec vos modèles IA.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fr"><body>{children}</body></html>;
}
