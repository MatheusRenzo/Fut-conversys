"use client";

import { useMemo, useState } from "react";
import { Activity, ChevronDown, Clock3, Goal, Radio, Zap } from "lucide-react";
import { TeamFlag } from "@/components/TeamFlag";
import { teamLabel } from "@/lib/teams";
import type { WorldCupSyncStatus } from "@/types";

type AdminLivePanelProps = {
  syncStatus: WorldCupSyncStatus;
  currentTime: number;
  error?: string;
};

type GameRow = {
  match_number?: number | null;
  home_team: string;
  away_team: string;
  kickoff_at?: string | null;
  status: string;
  score?: string | null;
  scorers?: string | null;
  halftime?: boolean;
  scorers_complete?: boolean;
  scorers_final?: boolean;
  scorers_confirmations?: number;
  confirmation_sources?: string | null;
  end_source?: string | null;
  reconfirmed?: boolean;
  polls?: { api_football: number; thesportsdb: number };
};

function agoLabel(iso: string | null | undefined, now: number) {
  if (!iso) return "—";
  const diff = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  if (diff < 60) return `há ${diff}s`;
  if (diff < 3600) return `há ${Math.floor(diff / 60)}min`;
  return `há ${Math.floor(diff / 3600)}h`;
}

function inLabel(lastIso: string | null | undefined, gapSeconds: number | undefined, now: number) {
  if (!gapSeconds) return "—";
  const base = lastIso ? new Date(lastIso).getTime() : now;
  const remaining = Math.max(0, Math.round((base + gapSeconds * 1000 - now) / 1000));
  if (remaining <= 0) return "agora";
  if (remaining < 60) return `em ${remaining}s`;
  if (remaining < 3600) return `em ${Math.floor(remaining / 60)}min`;
  return `em ${Math.floor(remaining / 60)}min`;
}

function timeHM(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  });
}

const API_LABELS: Record<string, { name: string; role: string }> = {
  football_data: { name: "football-data", role: "placar · intervalo · fim" },
  api_football: { name: "API-Football", role: "goleador (paga)" },
  thesportsdb: { name: "TheSportsDB", role: "failover + 2ª confirmação" },
  ai_reconcile: { name: "IA merge", role: "confirma goleadores" },
  ai_insight: { name: "IA resenha", role: "card de palpite" },
};

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Agendado",
  live: "Ao vivo",
  finished: "Encerrado",
  postponed: "Adiado",
};

function gameKey(g: GameRow) {
  return g.match_number ?? `${g.home_team}-${g.away_team}`;
}

export function AdminLivePanel({ syncStatus, currentTime, error }: AdminLivePanelProps) {
  const [openTimeline, setOpenTimeline] = useState<number | string | null>(null);
  const [openConfirm, setOpenConfirm] = useState<number | string | null>(null);

  const cadence = syncStatus.cadence;
  const fast = Boolean(cadence?.live_now ?? syncStatus.live_now);
  const loopSec = cadence?.loop_seconds ?? syncStatus.interval_seconds ?? (fast ? 30 : 600);

  const healthMap = useMemo(() => {
    const map = new Map<number | string, GameRow>();
    for (const g of syncStatus.games_health ?? []) {
      const parts = g.matchup.split(" x ");
      const row: GameRow = {
        match_number: g.match_number,
        home_team: parts[0] ?? "",
        away_team: parts[1] ?? "",
        status: g.status,
        score: g.score,
        scorers: g.scorers,
        halftime: g.halftime,
        scorers_complete: g.scorers_complete,
        scorers_final: g.scorers_final,
        scorers_confirmations: g.scorers_confirmations,
        confirmation_sources: g.confirmation_sources,
        end_source: g.end_source,
        reconfirmed: g.reconfirmed,
        polls: g.polls,
      };
      map.set(g.match_number ?? g.matchup, row);
    }
    return map;
  }, [syncStatus.games_health]);

  const games = useMemo(() => {
    const today = syncStatus.today_games ?? [];
    const merged: GameRow[] = today.map((g) => {
      const key = g.match_number ?? `${g.home_team} x ${g.away_team}`;
      const health = healthMap.get(g.match_number ?? key);
      return {
        match_number: g.match_number,
        home_team: g.home_team,
        away_team: g.away_team,
        kickoff_at: g.kickoff_at,
        status: g.status,
        score: g.score ?? health?.score,
        scorers: g.scorers ?? health?.scorers,
        halftime: g.halftime ?? health?.halftime,
        scorers_complete: g.scorers_complete ?? health?.scorers_complete,
        scorers_final: health?.scorers_final,
        scorers_confirmations: g.scorers_confirmations ?? health?.scorers_confirmations,
        confirmation_sources: health?.confirmation_sources,
        end_source: g.end_source ?? health?.end_source,
        reconfirmed: health?.reconfirmed,
        polls: health?.polls,
      };
    });

    // jogos ao vivo/encerrados de ontem que ainda aparecem no health mas não em today
    for (const g of syncStatus.games_health ?? []) {
      const key = g.match_number ?? g.matchup;
      if (merged.some((m) => (m.match_number ?? `${m.home_team}-${m.away_team}`) === key)) continue;
      const parts = g.matchup.split(" x ");
      merged.push({
        match_number: g.match_number,
        home_team: parts[0] ?? "",
        away_team: parts[1] ?? "",
        status: g.status,
        score: g.score,
        scorers: g.scorers,
        halftime: g.halftime,
        scorers_complete: g.scorers_complete,
        scorers_final: g.scorers_final,
        scorers_confirmations: g.scorers_confirmations,
        confirmation_sources: g.confirmation_sources,
        end_source: g.end_source,
        reconfirmed: g.reconfirmed,
        polls: g.polls,
      });
    }

    const order = { live: 0, finished: 1, scheduled: 2, postponed: 3 };
    return merged.sort((a, b) => {
      const sa = order[a.status as keyof typeof order] ?? 9;
      const sb = order[b.status as keyof typeof order] ?? 9;
      if (sa !== sb) return sa - sb;
      return new Date(a.kickoff_at ?? 0).getTime() - new Date(b.kickoff_at ?? 0).getTime();
    });
  }, [healthMap, syncStatus.games_health, syncStatus.today_games]);

  const eventsByGame = useMemo(() => {
    const map = new Map<number | string, typeof syncStatus.game_events>();
    for (const ev of syncStatus.game_events ?? []) {
      const key = ev.match_number ?? ev.game;
      const list = map.get(key) ?? [];
      list.push(ev);
      map.set(key, list);
    }
    return map;
  }, [syncStatus.game_events]);

  const lastOk = syncStatus.games_sync?.ok !== false;

  return (
    <div className="wc-dash">
      {error && <p className="bolao-feedback error">{error}</p>}

      {/* Placar ao vivo — modo + cadência */}
      <div className={`wc-dash-hero${fast ? " live" : ""}`}>
        <div className="wc-dash-hero-main">
          <span className={`wc-dash-pulse${fast ? " on" : ""}`}>
            <Radio size={13} />
            Placar ao vivo
          </span>
          <strong className="wc-dash-mode">
            Modo: {fast ? "RÁPIDO" : "LENTO"}
            <span className={`wc-dash-mode-badge${fast ? " fast" : " slow"}`}>
              {fast ? <Zap size={12} /> : <Clock3 size={12} />}
              1 req a cada {loopSec >= 60 ? `${Math.round(loopSec / 60)}min` : `${loopSec}s`}
            </span>
          </strong>
          <span className="wc-dash-hero-sub">
            Última sync {agoLabel(cadence?.last_sync_at ?? syncStatus.last_sync, currentTime)} · próxima{" "}
            {inLabel(cadence?.last_sync_at ?? syncStatus.last_sync, loopSec, currentTime)}
            {!lastOk && " · ⚠ último ciclo falhou"}
          </span>
        </div>
        <div className="wc-dash-hero-stats">
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Activity size={11} /> Ao vivo</span>
            <strong>{syncStatus.totals.live_games ?? 0}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Goal size={11} /> Encerrados</span>
            <strong>{syncStatus.totals.finished_games}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Zap size={11} /> Cota paga</span>
            <strong>
              {syncStatus.requests_today?.api_football?.calls ?? 0}
              {syncStatus.requests_today?.api_football?.daily_cap
                ? `/${syncStatus.requests_today.api_football.daily_cap}`
                : ""}
            </strong>
          </div>
        </div>
      </div>

      {/* Cards por jogo */}
      {games.length > 0 && (
        <section className="wc-dash-games">
          <div className="wc-dash-section-title">Jogos — timeline & confirmação</div>
          <div className="wc-dash-game-list">
            {games.map((game) => {
              const key = gameKey(game);
              const evs = eventsByGame.get(game.match_number ?? `${game.home_team} x ${game.away_team}`) ?? [];
              const timelineOpen = openTimeline === key;
              const confirmOpen = openConfirm === key;
              const srcs = (game.confirmation_sources ?? "").split(",").map((s) => s.trim()).filter(Boolean);
              const af = game.polls?.api_football ?? 0;
              const tsd = game.polls?.thesportsdb ?? 0;

              return (
                <article className={`wc-dash-game-card ${game.status}`} key={String(key)}>
                  <div className="wc-dash-game-head">
                    <div className="wc-dash-game-meta">
                      <span className={`wc-today-badge ${game.status}`}>
                        {game.status === "live" && <span className="wc-live-dot small" />}
                        {game.halftime && game.status === "live" ? "Intervalo" : STATUS_LABEL[game.status] ?? game.status}
                      </span>
                      {game.match_number && <span className="wc-dash-game-num">#{game.match_number}</span>}
                      {game.kickoff_at && <span className="wc-dash-game-time">{timeHM(game.kickoff_at)}</span>}
                    </div>
                    <div className="wc-dash-game-match">
                      <span><TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}</span>
                      <strong className="wc-dash-game-score">{game.score ?? "–"}</strong>
                      <span>{teamLabel(game.away_team)} <TeamFlag team={game.away_team} /></span>
                    </div>
                    {game.scorers && (
                      <div className="wc-dash-game-scorers"><Goal size={12} /> {game.scorers}</div>
                    )}
                    {game.status === "live" && !game.scorers && (
                      <div className="wc-dash-game-hint muted">Sem gol ainda · football-data monitora</div>
                    )}
                  </div>

                  <button
                    className={`wc-dash-drop${timelineOpen ? " open" : ""}`}
                    onClick={() => setOpenTimeline(timelineOpen ? null : key)}
                    type="button"
                  >
                    <span>Timeline</span>
                    <small>{evs.length} evento{evs.length !== 1 ? "s" : ""}</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {timelineOpen && (
                    <div className="wc-dash-drop-body">
                      {evs.length > 0 ? (
                        [...evs].reverse().map((ev, i) => (
                          <div className="wc-dash-event" key={i}>
                            <span className="wc-dash-event-time">{timeHM(ev.at)}</span>
                            <span className="wc-dash-event-text">{ev.action}</span>
                          </div>
                        ))
                      ) : (
                        <p className="wc-dash-empty">Nenhum evento registrado ainda.</p>
                      )}
                      {(af > 0 || tsd > 0) && (
                        <p className="wc-dash-polls">
                          Chamadas neste jogo: API-Football ×{af} · TheSportsDB ×{tsd}
                        </p>
                      )}
                    </div>
                  )}

                  {(game.status === "finished" || game.status === "live") && (
                    <>
                      <button
                        className={`wc-dash-drop confirm${confirmOpen ? " open" : ""}`}
                        onClick={() => setOpenConfirm(confirmOpen ? null : key)}
                        type="button"
                      >
                        <span>Confirmação</span>
                        <small>
                          {game.end_source ? `fim: ${game.end_source}` : "aguardando"}
                          {game.reconfirmed ? " · re-confirmado" : game.status === "finished" ? " · +10min pendente" : ""}
                        </small>
                        <ChevronDown size={15} className="wc-dash-drop-chevron" />
                      </button>
                      {confirmOpen && (
                        <div className="wc-dash-drop-body confirm">
                          <div className="wc-dash-confirm-step">
                            <span className="lbl">Finalizou</span>
                            <span className={game.end_source ? "ok" : "wait"}>
                              {game.end_source ?? "—"}
                            </span>
                          </div>
                          <div className="wc-dash-confirm-step">
                            <span className="lbl">API paga (fim)</span>
                            <span className={game.scorers_final ? "ok" : game.status === "live" ? "muted" : "wait"}>
                              {game.scorers_final
                                ? `API-Football ✓ · ${game.scorers || "sem goleador"}`
                                : game.status === "live"
                                  ? "aguarda o apito"
                                  : `API-Football ×${af} — aguardando`}
                            </span>
                          </div>
                          <div className="wc-dash-confirm-step">
                            <span className="lbl">Re-confirmação (+10min)</span>
                            <span className={game.reconfirmed ? "ok" : "wait"}>
                              {game.reconfirmed
                                ? `${srcs.join(" + ") || "TheSportsDB + openfootball"}${srcs.includes("IA") || syncStatus.sources.ai_configured ? " + IA" : ""}`
                                : "TheSportsDB + openfootball + IA (agendado)"}
                            </span>
                          </div>
                          {srcs.length > 0 && (
                            <div className="wc-dash-confirm-sources">
                              {srcs.map((s) => (
                                <span className="wc-dash-src-chip" key={s}>{s}</span>
                              ))}
                              {game.reconfirmed && syncStatus.sources.ai_configured && (
                                <span className="wc-dash-src-chip">IA</span>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}

      {/* Totais do dia por API */}
      {syncStatus.requests_today && (
        <section className="wc-dash-apis">
          <div className="wc-dash-section-title detail">Cotas do dia (UTC)</div>
          <div className="wc-dash-apis-grid">
            {Object.entries(syncStatus.requests_today).map(([key, r]) => {
              const meta = API_LABELS[key] ?? { name: key, role: "" };
              return (
                <div className="wc-api-card" key={key}>
                  <div className="wc-api-card-head">
                    <strong>{meta.name}</strong>
                    <span className="wc-api-calls">
                      {r.calls}
                      {r.daily_cap ? `/${r.daily_cap}` : ""}
                    </span>
                  </div>
                  <span className="wc-api-label">{meta.role}</span>
                  {r.remaining != null && <span className="wc-api-rem">sobra {r.remaining}</span>}
                  {!r.daily_cap && r.limit_per_min && (
                    <span className="wc-api-free">{r.limit_per_min}/min · ilimitada/dia</span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
