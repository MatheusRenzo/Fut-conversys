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
  goals?: number;
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

type GameEvent = NonNullable<WorldCupSyncStatus["game_events"]>[number];

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

function eventKey(game: GameRow) {
  return game.match_number ?? `${game.home_team} x ${game.away_team}`;
}

/** Cor/ícone da linha da timeline conforme o log do backend */
function eventTone(action: string): "start" | "goal" | "call" | "ok" | "retry" | "warn" | "err" | "ht" | "end" | "reconf" | "plain" {
  if (action.includes("começou")) return "start";
  if (action.includes("gol!") || action.includes("gol ")) return "goal";
  if (action.startsWith("→")) return "call";
  if (action.includes("goleador:") && action.includes("respondeu")) return "ok";
  if (action.includes("failover") && action.includes("goleador:")) return "ok";
  if (action.startsWith("↻") || action.includes("retry")) return "retry";
  if (action.startsWith("⚠") || action.includes("failover")) return "warn";
  if (action.startsWith("✗")) return "err";
  if (action.includes("intervalo") || action.includes("2º tempo")) return "ht";
  if (action.includes("re-confirmado")) return "reconf";
  if (action.includes("encerrado") || action.includes("fim ")) return "end";
  return "plain";
}

/** Status ao vivo no card — o que está acontecendo AGORA */
function liveNowStatus(game: GameRow, evs: GameEvent[]) {
  const af = game.polls?.api_football ?? 0;
  const tsd = game.polls?.thesportsdb ?? 0;
  const goals = game.goals ?? 0;
  const latest = evs[0]?.action ?? "";

  if (game.status === "finished") {
    if (game.scorers_final && game.reconfirmed) {
      return { cls: "ok", text: `✓ Encerrado · re-confirmado · ${game.scorers || "sem goleador"}` };
    }
    if (game.scorers_final) {
      return { cls: "ok", text: `✓ Encerrado · API-Football confirmou · aguarda +10min` };
    }
    return { cls: "wait", text: `🏁 Encerrado · aguardando API-Football (fim) ×${af}` };
  }

  if (game.status !== "live") return null;

  if (game.halftime) {
    return { cls: "ht", text: "⏸ Intervalo · football-data (PAUSED)" };
  }

  if (goals === 0) {
    return { cls: "muted", text: "0-0 · football-data monitora (sem cota paga)" };
  }

  if (game.scorers_complete && game.scorers) {
    const via = latest.includes("TheSportsDB") ? "TheSportsDB (failover)" : "API-Football";
    return { cls: "ok", text: `✓ Goleadores: ${game.scorers} · ${via} ×${latest.includes("TheSportsDB") ? tsd : af}` };
  }

  if (latest.includes("paga sem cota") || latest.includes("failover TheSportsDB")) {
    if (latest.includes("sem goleador")) {
      return { cls: "retry", text: `⚠ Failover TheSportsDB · sem goleador ainda · retry ×${tsd}` };
    }
    return { cls: "warn", text: `⚠ Paga sem cota → failover TheSportsDB ×${tsd}` };
  }

  if (latest.startsWith("✗") || latest.includes("retry")) {
    return { cls: "retry", text: `⏳ Buscando goleador… retry API-Football ×${af}` };
  }

  if (latest.includes("buscando autor") || latest.includes("gol!")) {
    return { cls: "wait", text: `⚽ Gol detectado (football-data) → chamando API-Football ×${af}` };
  }

  return { cls: "wait", text: `⏳ Aguardando goleador · API-Football ×${af}` };
}

function startedAt(evs: GameEvent[]) {
  const start = [...evs].reverse().find((e) => e.action.includes("começou"));
  return start ? timeHM(start.at) : null;
}

const API_LABELS: Record<string, { name: string; role: string; limit?: string }> = {
  football_data: { name: "football-data", role: "placar · intervalo · fim", limit: "10/min · ilimitada" },
  api_football: { name: "API-Football", role: "goleador ao vivo + fim (paga)" },
  thesportsdb: { name: "TheSportsDB", role: "failover ao vivo + re-confirmação", limit: "30/min · ilimitada" },
  ai_reconcile: { name: "IA merge", role: "confirma/casa goleadores", limit: "≈2/jogo cacheado" },
  ai_insight: { name: "IA resenha", role: "texto do card de palpite", limit: "1/próximo jogo" },
};

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Agendado",
  live: "Ao vivo",
  finished: "Encerrado",
  postponed: "Adiado",
};

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
      map.set(g.match_number ?? g.matchup, {
        match_number: g.match_number,
        home_team: parts[0] ?? "",
        away_team: parts[1] ?? "",
        status: g.status,
        score: g.score,
        goals: g.goals,
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
    return map;
  }, [syncStatus.games_health]);

  const games = useMemo(() => {
    const today = syncStatus.today_games ?? [];
    const merged: GameRow[] = today.map((g) => {
      const hk = g.match_number ?? `${g.home_team} x ${g.away_team}`;
      const health = healthMap.get(g.match_number ?? hk);
      return {
        match_number: g.match_number,
        home_team: g.home_team,
        away_team: g.away_team,
        kickoff_at: g.kickoff_at,
        status: g.status,
        score: g.score ?? health?.score,
        goals: health?.goals,
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

    for (const g of syncStatus.games_health ?? []) {
      const key = g.match_number ?? g.matchup;
      if (merged.some((m) => eventKey(m) === key || m.match_number === g.match_number)) continue;
      const parts = g.matchup.split(" x ");
      merged.push({
        match_number: g.match_number,
        home_team: parts[0] ?? "",
        away_team: parts[1] ?? "",
        status: g.status,
        score: g.score,
        goals: g.goals,
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
    const map = new Map<number | string, GameEvent[]>();
    for (const ev of syncStatus.game_events ?? []) {
      const key = ev.match_number ?? ev.game;
      const list = map.get(key) ?? [];
      list.push(ev);
      map.set(key, list);
    }
    return map;
  }, [syncStatus.game_events]);

  const lastOk = syncStatus.games_sync?.ok !== false;
  const pendentes = (syncStatus.games_health ?? []).filter((g) => g.status === "finished" && !g.scorers_final);
  const verdictOk = lastOk && pendentes.length === 0;

  const activeGames = games.filter((g) => g.status === "live" || g.status === "finished");
  const scheduledGames = games.filter((g) => g.status === "scheduled");

  return (
    <div className="wc-dash">
      {error && <p className="bolao-feedback error">{error}</p>}

      {/* Veredito */}
      <div className={verdictOk ? "wc-dash-verdict ok" : "wc-dash-verdict warn"}>
        <strong>{verdictOk ? "✓ Rodando certinho" : "⚠ Verificar"}</strong>
        <span>
          {fast ? "janela ao vivo ativa" : "modo ocioso"} · sync {agoLabel(cadence?.last_sync_at ?? syncStatus.last_sync, currentTime)}
          {!lastOk && " · último ciclo falhou"}
          {pendentes.length > 0 && ` · ${pendentes.length} jogo(s) sem confirmação final`}
        </span>
      </div>

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
              1 req a cada {fast ? "30s" : "10min"}
            </span>
          </strong>
          <span className="wc-dash-hero-sub">
            Próximo ciclo {inLabel(cadence?.last_sync_at ?? syncStatus.last_sync, loopSec, currentTime)}
            {cadence?.goal_pending && " · gol pendente (disparando paga)"}
          </span>
        </div>
        <div className="wc-dash-hero-stats">
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Activity size={11} /> Ao vivo</span>
            <strong>{syncStatus.totals.live_games ?? 0}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Goal size={11} /> Hoje</span>
            <strong>{games.length}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Zap size={11} /> Paga hoje</span>
            <strong>
              {syncStatus.requests_today?.api_football?.calls ?? 0}
              {syncStatus.requests_today?.api_football?.daily_cap
                ? `/${syncStatus.requests_today.api_football.daily_cap}`
                : ""}
            </strong>
          </div>
        </div>
      </div>

      {/* Cards — ao vivo + encerrados */}
      {activeGames.length > 0 && (
        <section className="wc-dash-games">
          <div className="wc-dash-section-title">Ao vivo & encerrados</div>
          <div className="wc-dash-game-list">
            {activeGames.map((game) => {
              const key = eventKey(game);
              const evs = eventsByGame.get(game.match_number ?? `${game.home_team} x ${game.away_team}`) ?? [];
              const timelineOpen = openTimeline === key;
              const confirmOpen = openConfirm === key;
              const srcs = (game.confirmation_sources ?? "").split(",").map((s) => s.trim()).filter(Boolean);
              const af = game.polls?.api_football ?? 0;
              const tsd = game.polls?.thesportsdb ?? 0;
              const nowStatus = liveNowStatus(game, evs);
              const kick = startedAt(evs);

              return (
                <article className={`wc-dash-game-card ${game.status}`} key={String(key)}>
                  <div className="wc-dash-game-head">
                    <div className="wc-dash-game-meta">
                      <span className={`wc-today-badge ${game.status}`}>
                        {game.status === "live" && !game.halftime && <span className="wc-live-dot small" />}
                        {game.halftime && game.status === "live" ? "Intervalo" : STATUS_LABEL[game.status] ?? game.status}
                      </span>
                      {game.match_number != null && <span className="wc-dash-game-num">#{game.match_number}</span>}
                      {game.kickoff_at && (
                        <span className="wc-dash-game-time" title="Horário do jogo">
                          jogo {timeHM(game.kickoff_at)}
                        </span>
                      )}
                      {kick && (
                        <span className="wc-dash-game-time started" title="Sistema marcou ao vivo">
                          iniciou {kick}
                        </span>
                      )}
                    </div>
                    <div className="wc-dash-game-match">
                      <span><TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}</span>
                      <strong className="wc-dash-game-score">{game.score ?? "0-0"}</strong>
                      <span>{teamLabel(game.away_team)} <TeamFlag team={game.away_team} /></span>
                    </div>
                    {nowStatus && (
                      <div className={`wc-dash-live-now ${nowStatus.cls}`}>{nowStatus.text}</div>
                    )}
                  </div>

                  {/* Dropdown 1: Timeline */}
                  <button
                    className={`wc-dash-drop${timelineOpen ? " open" : ""}`}
                    onClick={() => setOpenTimeline(timelineOpen ? null : key)}
                    type="button"
                  >
                    <span>Timeline</span>
                    <small>gol · chamada · retry · intervalo · fim</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {timelineOpen && (
                    <div className="wc-dash-drop-body timeline">
                      {evs.length > 0 ? (
                        <div className="wc-dash-timeline">
                          {[...evs].reverse().map((ev, i) => (
                            <div className={`wc-dash-tl-row tone-${eventTone(ev.action)}`} key={i}>
                              <span className="wc-dash-tl-dot" aria-hidden="true" />
                              <div className="wc-dash-tl-content">
                                <span className="wc-dash-tl-time">{timeHM(ev.at)}</span>
                                <span className="wc-dash-tl-text">{ev.action}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="wc-dash-empty">Nenhum evento ainda — começa no horário ou quando football-data confirma IN_PLAY.</p>
                      )}
                      <p className="wc-dash-polls">
                        Neste jogo: API-Football ×{af} · TheSportsDB ×{tsd}
                      </p>
                    </div>
                  )}

                  {/* Dropdown 2: Confirmação */}
                  <button
                    className={`wc-dash-drop confirm${confirmOpen ? " open" : ""}`}
                    onClick={() => setOpenConfirm(confirmOpen ? null : key)}
                    type="button"
                  >
                    <span>Confirmação</span>
                    <small>fim · API paga · re-confirmação (+10min)</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {confirmOpen && (
                    <div className="wc-dash-drop-body confirm">
                      <div className="wc-dash-confirm-step">
                        <span className="lbl">1. Finalizou</span>
                        <span className={game.end_source ? "ok" : "wait"}>
                          {game.end_source
                            ? `${game.end_source} ✓`
                            : game.status === "live"
                              ? "aguardando apito (football-data)"
                              : "—"}
                        </span>
                      </div>
                      <div className="wc-dash-confirm-step">
                        <span className="lbl">2. API paga (fim)</span>
                        <span className={game.scorers_final ? "ok" : game.status === "live" ? "muted" : "wait"}>
                          {game.scorers_final
                            ? `API-Football ✓ · ${game.scorers || "sem goleador"}`
                            : game.status === "live"
                              ? "roda 1× no apito final"
                              : `API-Football ×${af} — aguardando resposta`}
                        </span>
                      </div>
                      <div className="wc-dash-confirm-step">
                        <span className="lbl">3. Re-confirmação</span>
                        <span className={game.reconfirmed ? "ok" : "wait"}>
                          {game.reconfirmed ? "rodou (+10min)" : "agendada (+10min após o fim)"}
                        </span>
                      </div>
                      <div className="wc-dash-confirm-checks">
                        <span className={srcs.some((s) => s.toLowerCase().includes("thesports")) ? "ok" : game.reconfirmed ? "err" : "pending"}>
                          TheSportsDB {srcs.some((s) => s.toLowerCase().includes("thesports")) ? "✓" : game.reconfirmed ? "✗" : "…"}
                        </span>
                        <span className={srcs.some((s) => s.toLowerCase().includes("openfootball")) ? "ok" : game.reconfirmed ? "err" : "pending"}>
                          openfootball {srcs.some((s) => s.toLowerCase().includes("openfootball")) ? "✓" : game.reconfirmed ? "✗" : "…"}
                        </span>
                        <span className={game.reconfirmed && syncStatus.sources.ai_configured ? "ok" : game.reconfirmed ? "muted" : "pending"}>
                          IA merge {game.reconfirmed && syncStatus.sources.ai_configured ? "✓" : game.reconfirmed ? "—" : "…"}
                        </span>
                      </div>
                      {srcs.length > 0 && (
                        <div className="wc-dash-confirm-sources">
                          {srcs.map((s) => (
                            <span className="wc-dash-src-chip" key={s}>{s}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}

      {scheduledGames.length > 0 && (
        <section className="wc-dash-games scheduled">
          <div className="wc-dash-section-title">Agendados hoje ({scheduledGames.length})</div>
          <div className="wc-dash-scheduled-list">
            {scheduledGames.map((game) => (
              <div className="wc-dash-scheduled-row" key={String(eventKey(game))}>
                <span className="wc-dash-game-time">{game.kickoff_at ? timeHM(game.kickoff_at) : "—"}</span>
                <span>
                  {game.match_number != null && `#${game.match_number} `}
                  {teamLabel(game.home_team)} x {teamLabel(game.away_team)}
                </span>
                <span className="wc-dash-scheduled-hint">{fast ? "entra em modo rápido ~5min antes" : "modo lento"}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Log geral */}
      {(syncStatus.game_events?.length ?? 0) > 0 && (
        <section className="wc-dash-log-section">
          <div className="wc-dash-section-title detail">Log geral — últimos eventos</div>
          <div className="wc-dash-log-list">
            {(syncStatus.game_events ?? []).slice(0, 20).map((ev, i) => (
              <div className={`wc-log-row tone-${eventTone(ev.action)}`} key={i}>
                <span className="wc-log-time">{timeHM(ev.at)}</span>
                <span className="wc-log-game">{ev.match_number ? `#${ev.match_number}` : ev.game}</span>
                <span className="wc-log-action">{ev.action}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Cotas do dia — cada API */}
      {syncStatus.requests_today && (
        <section className="wc-dash-apis">
          <div className="wc-dash-section-title detail">Cotas do dia — cada API (UTC)</div>
          <div className="wc-dash-apis-grid">
            {Object.entries(syncStatus.requests_today).map(([key, r]) => {
              const meta = API_LABELS[key] ?? { name: key, role: "" };
              const limitTxt = r.daily_cap
                ? `${r.limit_per_min ?? "?"}/min · ${r.daily_cap}/dia`
                : meta.limit ?? (r.limit_per_min ? `${r.limit_per_min}/min` : "ilimitada");
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
                  <span className="wc-api-limit">{limitTxt}</span>
                  {r.remaining != null && <span className="wc-api-rem">sobra {r.remaining} hoje</span>}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
