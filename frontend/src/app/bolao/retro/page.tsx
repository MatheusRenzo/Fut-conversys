"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Crown, Goal, Sparkles, Target, Trophy, Users, Zap } from "lucide-react";
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

export default function BolaoRetroPage() {
  const router = useRouter();
  const [data, setData] = useState<RetroData | null>(null);

  useEffect(() => {
    api
      .worldCupRetro()
      .then(setData)
      .catch(() => router.push("/"));
  }, [router]);

  if (!data) {
    return (
      <div className="retro-page">
        <p className="retro-loading">Carregando a retrospectiva…</p>
      </div>
    );
  }

  const { stats, api_calls: calls } = data;
  const iaCalls = (calls.ai_insight ?? 0) + (calls.ai_reconcile ?? 0);
  const totalCalls = (calls.football_data ?? 0) + (calls.api_football ?? 0) + (calls.thesportsdb ?? 0) + iaCalls;

  return (
    <div className="retro-page">
      <header className="retro-hero">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img alt="Fut Conversys" className="retro-logo" src="/icons/fut-conversys-logo.png" />
        <h1 className="retro-title">Bolão da Copa 2026</h1>
        <p className="retro-subtitle">Uma jornada <strong>Conversys</strong> · IT Solutions</p>
        <p className="retro-thanks">
          Obrigado a todos que participaram, palpitaram, torceram e brincaram com a gente.
          Do primeiro apito à grande final — esse bolão é de vocês. 💚⚽
        </p>
      </header>

      {data.cup_champion && data.top3[0] && (
        <section className="retro-champs">
          <div className="retro-champ-card cup">
            <span className="retro-champ-tag">Campeã da Copa</span>
            <TeamFlag team={data.cup_champion} />
            <strong>{teamLabel(data.cup_champion)}</strong>
          </div>
          <div className="retro-champ-card winner">
            <Crown size={20} />
            <span className="retro-champ-tag">Campeão do Bolão</span>
            <Avatar size="md" user={data.top3[0].user} />
            <strong>{data.top3[0].user.name}</strong>
            <span className="retro-champ-pts">{data.top3[0].points} pts</span>
          </div>
        </section>
      )}

      <section className="retro-grid">
        <div className="retro-stat">
          <Users size={20} />
          <strong>{fmt(stats.participants)}</strong>
          <span>participantes</span>
        </div>
        <div className="retro-stat">
          <Target size={20} />
          <strong>{fmt(stats.predictions)}</strong>
          <span>palpites registrados</span>
        </div>
        <div className="retro-stat">
          <Goal size={20} />
          <strong>{fmt(stats.goals)}</strong>
          <span>gols acompanhados ao vivo</span>
        </div>
        <div className="retro-stat">
          <Trophy size={20} />
          <strong>{fmt(stats.games_finished)}</strong>
          <span>jogos disputados</span>
        </div>
        <div className="retro-stat">
          <Zap size={20} />
          <strong>{fmt(stats.exact_scores)}</strong>
          <span>placares exatos cravados</span>
        </div>
        <div className="retro-stat">
          <Sparkles size={20} />
          <strong>{fmt(stats.scorer_hits)}</strong>
          <span>artilheiros cravados</span>
        </div>
      </section>

      <section className="retro-engine">
        <h2>O motor por trás do bolão</h2>
        <p className="retro-engine-copy">
          {fmt(totalCalls)} chamadas de dados pra manter placar, gols e artilheiros em tempo real:
        </p>
        <div className="retro-engine-grid">
          <div><strong>{fmt(calls.football_data ?? 0)}</strong><span>placar ao vivo (football-data)</span></div>
          <div><strong>{fmt(calls.api_football ?? 0)}</strong><span>artilheiros (API-Football)</span></div>
          <div><strong>{fmt(calls.thesportsdb ?? 0)}</strong><span>confirmações (TheSportsDB)</span></div>
          <div><strong>{fmt(iaCalls)}</strong><span>consultas de IA (reconciliação + resenhas)</span></div>
        </div>
      </section>

      {data.top3.length > 0 && (
        <section className="retro-podium">
          <h2>O pódio até aqui</h2>
          <div className="retro-podium-row">
            {data.top3.map((entry) => (
              <div className={`retro-podium-step place-${entry.rank}`} key={entry.user.id}>
                {entry.rank === 1 && <Crown className="retro-podium-crown" size={22} />}
                <Avatar size="lg" user={entry.user} />
                <strong>{entry.user.name.split(" ")[0]}</strong>
                <span>{entry.points} pts</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="retro-wall">
        <h2>Quem fez essa jornada acontecer</h2>
        <div className="retro-wall-grid">
          {data.participants.map((p) => (
            <figure className="retro-wall-item" key={p.id}>
              <Avatar size="md" user={p} />
              <figcaption>{p.name.split(" ")[0]}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <footer className="retro-footer">
        <p>
          Feito com ⚽ e 💚 pela <strong>Conversys IT Solutions</strong> — rumo à grande final!
        </p>
      </footer>
    </div>
  );
}
