"use client";

import { Suspense, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Mail, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "@/lib/api";

const ADMIN_CONTACT = "redacted@example.com";

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  const [microsoftEnabled, setMicrosoftEnabled] = useState(false);
  const [configLoaded, setConfigLoaded] = useState(false);

  const isDomainBlocked = error === "domain_not_allowed";

  useEffect(() => {
    api.sessionMe().then(() => router.push("/dashboard")).catch(() => null);
    api
      .microsoftConfig()
      .then((config) => setMicrosoftEnabled(config.enabled))
      .catch(() => setMicrosoftEnabled(false))
      .finally(() => setConfigLoaded(true));
  }, [router]);

  const startMicrosoftLogin = () => {
    window.location.href = "/api/backend/api/auth/microsoft/start";
  };

  if (isDomainBlocked) {
    return (
      <main className="landing-page">
        <section className="landing-copy">
          <div className="brand-mark hero-brand">
            <span className="hero-logo-shell">
              <Image src="/icons/fut-conversys-logo.png" alt="Fut Conversys" width={128} height={128} priority />
            </span>
          </div>
          <p>O app interno para organizar peladas, confirmar presença e guardar os melhores momentos da firma.</p>
        </section>

        <section className="login-card glass-panel">
          <div className="login-card-head">
            <ShieldX size={36} style={{ color: "var(--color-warning, #f59e0b)", marginBottom: "0.5rem" }} />
            <span className="eyebrow">Acesso não liberado</span>
            <h2>Sua conta não tem acesso</h2>
            <p>
              O Fut Conversys é exclusivo para colaboradores com e-mail <strong>@conversys.global</strong>.
              Se você é da Conversys e não consegue entrar, solicite acesso ao administrador.
            </p>
          </div>

          <a
            href={`mailto:${ADMIN_CONTACT}?subject=Solicita%C3%A7%C3%A3o%20de%20acesso%20%E2%80%94%20Fut%20Conversys&body=Ol%C3%A1%2C%0A%0AGostaria%20de%20solicitar%20acesso%20ao%20Fut%20Conversys.%0A%0ANome%3A%20%0AE-mail%20corporativo%3A%20%0A`}
            className="btn-primary"
          >
            <Mail size={17} />
            <span>Solicitar acesso por e-mail</span>
          </a>

          <p className="login-card-note">
            Contato do administrador: <strong>{ADMIN_CONTACT}</strong>
          </p>

          <button
            className="btn-ghost"
            style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}
            onClick={() => router.replace("/")}
            type="button"
          >
            Tentar com outra conta
          </button>
        </section>
      </main>
    );
  }

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

      <section className="login-card glass-panel">
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
          <span className="eyebrow">Acesso exclusivo Conversys</span>
          <h2>Acesse o Fut Conversys</h2>
          <p>
            Entre com sua conta corporativa <strong>@conversys.global</strong> para ver eventos,
            publicações e perfis do time.
          </p>
        </div>

        {error === "microsoft_login" && (
          <p className="login-card-note warning" style={{ marginBottom: "0.5rem" }}>
            Falha no login. Tente novamente.
          </p>
        )}

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
          <p className="login-card-note warning">
            Configure o Microsoft Entra no servidor para liberar o acesso.
            <br />
            Contato: <strong>{ADMIN_CONTACT}</strong>
          </p>
        ) : null}
      </section>
    </main>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="empty-state">Carregando...</div>}>
      <HomeContent />
    </Suspense>
  );
}
