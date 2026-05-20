"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, ShieldCheck, UserPlus } from "lucide-react";
import { API_URL, api, setSession } from "@/lib/api";

type AuthMode = "login" | "register";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const passwordRules = [
  { id: "length", label: "8 caracteres", test: (value: string) => value.length >= 8 },
  { id: "case", label: "maiúscula e minúscula", test: (value: string) => /[A-Z]/.test(value) && /[a-z]/.test(value) },
  { id: "number", label: "número", test: (value: string) => /\d/.test(value) },
  { id: "symbol", label: "símbolo", test: (value: string) => /[^A-Za-z0-9]/.test(value) },
];

export default function Home() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [registerName, setRegisterName] = useState("");
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerConfirmPassword, setRegisterConfirmPassword] = useState("");
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

  const switchAuthMode = (mode: AuthMode) => {
    setAuthMode(mode);
    setError("");
  };

  const handleRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    const passwordIsStrong = passwordRules.every((rule) => rule.test(registerPassword));
    if (registerName.trim().length < 2) {
      setError("Informe seu nome.");
      setLoading(false);
      return;
    }
    if (!emailPattern.test(registerEmail.trim())) {
      setError("Informe um e-mail válido.");
      setLoading(false);
      return;
    }
    if (!passwordIsStrong) {
      setError("Crie uma senha mais forte para continuar.");
      setLoading(false);
      return;
    }
    if (registerPassword !== registerConfirmPassword) {
      setError("As senhas precisam ser iguais.");
      setLoading(false);
      return;
    }

    try {
      const data = await api.register({
        name: registerName,
        email: registerEmail,
        password: registerPassword,
      });
      setSession(data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Não foi possível criar sua conta");
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
          <span className="eyebrow">{authMode === "login" ? "Acesso interno" : "Novo jogador"}</span>
          <h2>{authMode === "login" ? "Entre na sua conta" : "Crie sua conta"}</h2>
          <p>
            {authMode === "login"
              ? "Use seu usuário, e-mail ou a conta Microsoft corporativa."
              : "Cadastre-se com e-mail e uma senha forte para entrar no Fut Conversys."}
          </p>
        </div>

        {authMode === "login" ? (
          <form className="login-form" onSubmit={handleLogin}>
            <label>
              Usuário ou e-mail
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
        ) : (
          <form className="login-form" onSubmit={handleRegister}>
            <label>
              Nome
              <input
                type="text"
                className="input-field"
                value={registerName}
                onChange={(event) => setRegisterName(event.target.value)}
                autoComplete="name"
                required
              />
            </label>

            <label>
              E-mail
              <input
                type="email"
                className="input-field"
                value={registerEmail}
                onChange={(event) => setRegisterEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>

            <label>
              Senha
              <input
                type="password"
                className="input-field"
                value={registerPassword}
                onChange={(event) => setRegisterPassword(event.target.value)}
                autoComplete="new-password"
                required
              />
            </label>

            <div className="password-rules" aria-label="Requisitos da senha">
              {passwordRules.map((rule) => {
                const passed = rule.test(registerPassword);
                return (
                  <span className={passed ? "active" : ""} key={rule.id}>
                    <Check size={13} />
                    {rule.label}
                  </span>
                );
              })}
            </div>

            <label>
              Confirmar senha
              <input
                type="password"
                className="input-field"
                value={registerConfirmPassword}
                onChange={(event) => setRegisterConfirmPassword(event.target.value)}
                autoComplete="new-password"
                required
              />
            </label>

            {error && <div className="error-box">{error}</div>}

            <button type="submit" className="btn-primary" disabled={loading}>
              <span>{loading ? "Criando conta..." : "Criar conta segura"}</span>
              <UserPlus size={17} />
            </button>
          </form>
        )}

        {microsoftEnabled ? (
          <a className="btn-secondary microsoft-login" href={`${API_URL}/api/auth/microsoft/start`}>
            <ShieldCheck size={17} />
            <span>Entrar com Microsoft</span>
          </a>
        ) : null}

        <button className="auth-switch-button" onClick={() => switchAuthMode(authMode === "login" ? "register" : "login")} type="button">
          {authMode === "login" ? "Criar conta com e-mail" : "Já tenho uma conta"}
        </button>
      </section>
    </main>
  );
}
