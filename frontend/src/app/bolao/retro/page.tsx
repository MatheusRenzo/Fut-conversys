"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BrainCircuit, Crown, Goal, Radio, Sparkles, Target, Trophy, Users, Zap } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { TeamFlag } from "@/components/TeamFlag";
import { api } from "@/lib/api";
import { teamLabel } from "@/lib/teams";
import type { UserProfile, WorldCupLeaderboardEntry } from "@/types";

type RetroData = {
  participants: UserProfile[];
  cup_champion?: string | null;
  top3: WorldCupLeaderboardEntry[];
  stats: {
    participants: number;
    predictions: number;
    champion_picks: number;
    games_finished: number;
    goals: number;
    exact_scores: number;
    scorer_hits: number;
    started_at?: string | null;
    ends_at?: string | null;
  };
  api_calls: Record<string, number>;
};

const fmt = (n: number) => n.toLocaleString("pt-BR");

// Número que sobe animado (efeito contagem) — dopamina nos dados
function useCountUp(target: number, duration = 2000) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
}

function StatCard({ icon, value, label, delay = 0 }: { icon: React.ReactNode; value: number; label: string; delay?: number }) {
  const n = useCountUp(value);
  return (
    <div className="retro2-stat" style={{ animationDelay: `${delay}ms` }}>
      <span className="retro2-stat-icon">{icon}</span>
      <strong>{fmt(n)}</strong>
      <span className="retro2-stat-label">{label}</span>
    </div>
  );
}

export default function BolaoRetroPage() {
  const router = useRouter();
  const [data, setData] = useState<RetroData | null>(null);

  useEffect(() => {
    api
      .worldCupRetro()
      .then(setData)
      .catch(() => router.push("/"));
  }, [router]);

  const startedAt = data?.stats.started_at ?? null;
  const endsAt = data?.stats.ends_at ?? null;
  const days = useMemo(() => {
    if (!startedAt || !endsAt) return null;
    const ms = new Date(endsAt).getTime() - new Date(startedAt).getTime();
    return Math.max(1, Math.round(ms / 86_400_000));
  }, [startedAt, endsAt]);

  if (!data) {
    return (
      <div className="retro2-page">
        <p className="retro2-loading">Carregando a retrospectiva…</p>
      </div>
    );
  }

  const { stats, api_calls: calls } = data;
  const iaCalls = (calls.ai_insight ?? 0) + (calls.ai_reconcile ?? 0);
  const totalCalls = (calls.football_data ?? 0) + (calls.api_football ?? 0) + (calls.thesportsdb ?? 0) + iaCalls;
  const winner = data.top3[0];

  return (
    <div className="retro2-page">
      <div aria-hidden="true" className="retro2-orbs">
        <span /><span /><span /><span /><span /><span />
      </div>

      <header className="retro2-hero">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img alt="Fut Conversys" className="retro2-logo" src="/icons/fut-conversys-logo.png" />
        <h1 className="retro2-title">Bolão da Copa 2026</h1>
        <p className="retro2-subtitle">A retrospectiva de uma jornada <strong>Conversys</strong> · IT Solutions</p>
        <p className="retro2-thanks">
          {days ? `Foram ${days} dias de Copa` : "Foi uma Copa inteira"} — do primeiro apito à grande final.
          Obrigado a cada um que palpitou, torceu, zoou no grupo e fez essa jornada valer a pena. Esse bolão é de vocês! 💙⚽
        </p>
      </header>

      {data.cup_champion && winner && (
        <section className="retro2-stage">
          <div className="retro2-cup-banner">
            <span className="retro2-cup-tag">Campeã da Copa</span>
            <TeamFlag team={data.cup_champion} />
            <strong>{teamLabel(data.cup_champion)}</strong>
          </div>

          <div className="retro2-arena">
            <div aria-hidden="true" className="retro2-spot" />
            <div aria-hidden="true" className="retro2-sparkles">
              <i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i><i>✦</i>
            </div>
            <div className="retro2-podium">
              {data.top3[1] && (
                <div className="retro2-step place-2">
                  <div className="retro2-step-avatar silver">
                    <Avatar size="lg" user={data.top3[1].user} />
                  </div>
                  <strong className="retro2-step-name">{data.top3[1].user.name.split(" ")[0]}</strong>
                  <span className="retro2-step-pts">{data.top3[1].points} pts</span>
                  <div className="retro2-step-block"><span>2º</span></div>
                </div>
              )}
              <div className="retro2-step place-1">
                <Crown className="retro2-crown" size={38} />
                <div className="retro2-ring">
                  <div className="retro2-step-avatar gold">
                    <Avatar size="lg" user={winner.user} />
                  </div>
                </div>
                <span className="retro2-champ-tag">Campeão do Bolão</span>
                <strong className="retro2-champ-name">{winner.user.name}</strong>
                <span className="retro2-step-pts gold">{winner.points} pts</span>
                <span className="retro2-champ-note">decidido no último jogo da Copa 🔥</span>
                <div className="retro2-step-block gold"><span>1º</span></div>
              </div>
              {data.top3[2] && (
                <div className="retro2-step place-3">
                  <div className="retro2-step-avatar bronze">
                    <Avatar size="lg" user={data.top3[2].user} />
                  </div>
                  <strong className="retro2-step-name">{data.top3[2].user.name.split(" ")[0]}</strong>
                  <span className="retro2-step-pts">{data.top3[2].points} pts</span>
                  <div className="retro2-step-block"><span>3º</span></div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="retro2-grid">
        <StatCard delay={0} icon={<Users size={22} />} label="participantes" value={stats.participants} />
        <StatCard delay={120} icon={<Target size={22} />} label="palpites registrados" value={stats.predictions} />
        <StatCard delay={240} icon={<Goal size={22} />} label="gols acompanhados ao vivo" value={stats.goals} />
        <StatCard delay={360} icon={<Trophy size={22} />} label="jogos disputados" value={stats.games_finished} />
        <StatCard delay={480} icon={<Zap size={22} />} label="placares exatos cravados" value={stats.exact_scores} />
        <StatCard delay={600} icon={<Sparkles size={22} />} label="artilheiros cravados" value={stats.scorer_hits} />
      </section>

      <section className="retro2-engine">
        <h2>Zero planilha. 100% ao vivo.</h2>
        <p className="retro2-engine-copy">
          Fugimos do bolão clássico de planilha: aqui o placar, os gols e os artilheiros entraram
          <strong> em tempo real</strong>, com <strong>{fmt(totalCalls)}</strong> chamadas de dados em{" "}
          <strong>4 APIs esportivas + IA generativa</strong> cruzando e validando cada lance — a pontuação
          caía sozinha, segundos depois do apito.
        </p>
        <div className="retro2-engine-grid">
          <div><Radio size={17} /><strong>{fmt(calls.football_data ?? 0)}</strong><span>placar ao vivo</span></div>
          <div><Goal size={17} /><strong>{fmt(calls.api_football ?? 0)}</strong><span>artilheiros (API oficial)</span></div>
          <div><Target size={17} /><strong>{fmt(calls.thesportsdb ?? 0)}</strong><span>confirmações cruzadas</span></div>
          <div><BrainCircuit size={17} /><strong>{fmt(iaCalls)}</strong><span>consultas de IA</span></div>
        </div>
      </section>

      <section className="retro2-wall">
        <h2>Quem fez essa jornada acontecer</h2>
        <div className="retro2-wall-grid">
          {data.participants.map((p, i) => (
            <figure className="retro2-wall-item" key={p.id} style={{ animationDelay: `${Math.min(i * 45, 1800)}ms` }}>
              <Avatar size="md" user={p} />
              <figcaption>{p.name.split(" ")[0]}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="retro2-ceo">
        <Trophy size={22} />
        <p>
          E um agradecimento especial ao nosso <strong>CEO</strong>, que abraçou a ideia e{" "}
          <strong>investiu nos prêmios</strong> — o combustível que fez todo mundo palpitar, zoar no grupo
          e disputar cada rodada até o último jogo da Copa. 🏆💙
        </p>
      </section>

      <footer className="retro2-footer">
        <p>Feito com ⚽ e 💙 pela <strong>Conversys IT Solutions</strong></p>
        <span>fut.conversys.global</span>
      </footer>
    </div>
  );
}
