"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [microsoftEnabled, setMicrosoftEnabled] = useState(false);
  const [configLoaded, setConfigLoaded] = useState(false);

  useEffect(() => {
    const mountTimer = window.setTimeout(() => setMounted(true), 0);
    api.sessionMe().then(() => router.push("/dashboard")).catch(() => null);
    api
      .microsoftConfig()
      .then((config) => setMicrosoftEnabled(config.enabled))
      .catch(() => setMicrosoftEnabled(false))
      .finally(() => setConfigLoaded(true));
    return () => window.clearTimeout(mountTimer);
  }, [router]);

  const startMicrosoftLogin = () => {
    window.location.href = "/api/backend/api/auth/microsoft/start";
  };

  return (
    <main className="landing-page">
      <section className="landing-copy">
        <div className="brand-mark hero-brand">
          <span className="hero-logo-shell">
            <Image src="/icons/fut-conversys-logo.png" alt="Fut Conversys" width={128} height={128} priority />
          </span>
        </div>
        <p>
          O app interno para organizar peladas, confirmar presença e guardar os melhores momentos
          da firma.
        </p>
      </section>

      <section className="login-card glass-panel" suppressHydrationWarning>
        {mounted ? (
          <>
            <div className="login-provider-mark" aria-hidden="true">
              <span className="microsoft-window-mark">
                <i />
                <i />
                <i />
                <i />
              </span>
              <span>Microsoft Entra</span>
            </div>

            <div className="login-card-head">
              <span className="eyebrow">Acesso restrito</span>
              <h2>Acesse o Fut Conversys</h2>
              <p>Entre com sua conta corporativa para ver eventos, publicações e perfis do time.</p>
            </div>

            <button
              className="btn-primary microsoft-login"
              disabled={!configLoaded || !microsoftEnabled}
              onClick={startMicrosoftLogin}
              type="button"
            >
              <span>
                {!configLoaded
                  ? "Preparando acesso..."
                  : microsoftEnabled
                    ? "Continuar com Microsoft"
                    : "Microsoft não configurado"}
              </span>
              <ArrowRight size={17} />
            </button>

            {microsoftEnabled ? (
              <p className="login-card-note">
                <ShieldCheck size={15} />
                Login protegido pela autenticação corporativa da Microsoft.
              </p>
            ) : configLoaded ? (
              <p className="login-card-note warning">Configure o Microsoft Entra no ambiente para liberar o acesso.</p>
            ) : null}
          </>
        ) : null}
      </section>
    </main>
  );
}
