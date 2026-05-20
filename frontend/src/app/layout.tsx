import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import { PwaRegister } from "@/components/PwaRegister";
import "./globals.css";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  applicationName: "Fut Conversys",
  title: "Conversys Fut | Marque sua presença",
  description: "O aplicativo de futebol da Conversys. Perfil, escalação, gols e muita resenha.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Fut Conversys",
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    "apple-mobile-web-app-capable": "yes",
  },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/fut-conversys-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/fut-conversys-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#041E42",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className={`${manrope.variable}`}>
      <body>
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
