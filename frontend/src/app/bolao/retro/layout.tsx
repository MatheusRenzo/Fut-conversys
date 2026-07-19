import type { Metadata } from "next";
import type { ReactNode } from "react";

const OG_IMAGE = "https://fut.conversys.global:9443/og-bolao-retro.png";

// Preview rico no WhatsApp/LinkedIn quando o link é compartilhado (Open Graph)
export const metadata: Metadata = {
  title: "Bolão da Copa 2026 — Retrospectiva | Conversys",
  description:
    "Espanha campeã e Igor Vieira campeão do bolão! 39 participantes, 2.110 palpites, 308 gols ao vivo e 104 jogos. Veja a retrospectiva completa da jornada Conversys IT Solutions. 🏆💙",
  openGraph: {
    title: "🏆 Bolão da Copa 2026 — A Retrospectiva",
    description:
      "Espanha campeã · Igor Vieira campeão do bolão (131 pts) · 39 participantes · 2.110 palpites · 308 gols ao vivo. A jornada completa da Conversys IT Solutions.",
    siteName: "Fut Conversys",
    type: "website",
    images: [{ url: OG_IMAGE, width: 1200, height: 630, alt: "Retrospectiva do Bolão da Copa 2026 — Conversys" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "🏆 Bolão da Copa 2026 — A Retrospectiva",
    description: "Espanha campeã · Igor Vieira campeão do bolão · 2.110 palpites · 308 gols ao vivo.",
    images: [OG_IMAGE],
  },
};

export default function RetroLayout({ children }: { children: ReactNode }) {
  return children;
}
