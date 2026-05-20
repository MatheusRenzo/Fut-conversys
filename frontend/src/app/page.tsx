"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { API_URL, api, setSession } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [microsoftEnabled, setMicrosoftEnabled] = useState(false);

  useEffect(() => {
    api.sessionMe().then(() => router.push("/dashboard")).catch(() => null);
    api.microsoftConfig().then((config) => setMicrosoftEnabled(config.enabled)).catch(() => null);
  }, [router]);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const data = await api.login(username, password);
      setSession(data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="landing-page">
      <section className="landing-copy">
        <div className="brand-mark hero-brand">
          <span className="hero-logo-shell">
            <Image src="/icons/fut-conversys-logo.png" alt="Fut Conversys" width={112} height={112} priority />
          </span>
          <span>
            <strong>Conversys Fut</strong>
            <small>Eventos esportivos internos</small>
          </span>
        </div>

        <h1>Fut Conversys</h1>
        <p>
          O app interno para organizar peladas, confirmar presença e guardar os melhores momentos
          da firma.
        </p>
      </section>

      <section className="login-card glass-panel">
        <div className="login-card-head">
          <span className="eyebrow">Acesso interno</span>
          <h2>Entre na sua conta</h2>
        </div>

        <form className="login-form" onSubmit={handleLogin}>
          <label>
            Usuário
            <input
              type="text"
              className="input-field"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              suppressHydrationWarning
              required
            />
          </label>

          <label>
            Senha
            <input
              type="password"
              className="input-field"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              suppressHydrationWarning
              required
            />
          </label>

          {error && <div className="error-box">{error}</div>}

          <button type="submit" className="btn-primary" disabled={loading}>
            <span>{loading ? "Entrando..." : "Entrar"}</span>
            <ArrowRight size={17} />
          </button>
        </form>

        {microsoftEnabled ? (
          <a className="btn-secondary microsoft-login" href={`${API_URL}/api/auth/microsoft/start`}>
            <ShieldCheck size={17} />
            <span>Entrar com Microsoft</span>
          </a>
        ) : null}
      </section>
    </main>
  );
}
