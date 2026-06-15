"use client";

import { useMemo, useState } from "react";
import { Activity, Bot, ChevronDown, Clock3, Database, Goal, Radio, Zap } from "lucide-react";
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
  confirmation_sources?: string | null;
  end_source?: string | null;
  reconfirmed?: boolean;
  polls?: { api_football: number; thesportsdb: number };
};

type GameEvent = NonNullable<WorldCupSyncStatus["game_events"]>[number];

const PHASE_LABEL: Record<string, string> = {
  ao_vivo: "AO VIVO",
  ao_vivo_failover: "FAILOVER",
  fim: "FIM",
  reconfirmacao: "RECONF",
  gratuito: "GRÁTIS",
};

function timeFull(iso: string) {
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "America/Sao_Paulo",
  });
}

function timeHM(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  });
}

function inLabel(lastIso: string | null | undefined, gapSeconds: number | undefined, now: number) {
  if (!gapSeconds) return "—";
  const base = lastIso ? new Date(lastIso).getTime() : now;
  const remaining = Math.max(0, Math.round((base + gapSeconds * 1000 - now) / 1000));
  if (remaining <= 0) return "agora";
  if (remaining < 60) return `em ${remaining}s`;
  return `em ${Math.floor(remaining / 60)}min`;
}

function eventKey(game: GameRow) {
  return game.match_number ?? `${game.home_team}-${game.away_team}`;
}

function rowTone(ev: GameEvent): string {
  if (ev.ok === false) return "err";
  if (ev.ok === true) return "ok";
  if (ev.action.startsWith("↻") || ev.action.includes("retry")) return "retry";
  if (ev.action.startsWith("⚠") || ev.action.includes("failover")) return "warn";
  if (ev.api === "IA merge") return "ia";
  if (ev.action.includes("GOL") || ev.action.includes("gol")) return "goal";
  if (ev.action.includes("intervalo") || ev.action.includes("2º tempo")) return "ht";
  if (ev.phase === "fim" || ev.action.includes("🏁")) return "end";
  return "plain";
}

function TimelineRow({ ev }: { ev: GameEvent }) {
  const tone = rowTone(ev);
  const phase = ev.phase ? PHASE_LABEL[ev.phase] ?? ev.phase.toUpperCase() : null;
  const status =
    ev.ok === true ? "✓" : ev.ok === false ? "✗" : ev.action.startsWith("→") ? "…" : "·";

  return (
    <div className={`wc-tl-v2 tone-${tone}`}>
      <div className="wc-tl-v2-rail">
        <span className={`wc-tl-v2-status s-${tone}`}>{status}</span>
        <span className="wc-tl-v2-line" aria-hidden="true" />
      </div>
      <div className="wc-tl-v2-body">
        <div className="wc-tl-v2-meta">
          <time className="wc-tl-v2-time">{timeFull(ev.at)}</time>
          {phase && <span className={`wc-tl-v2-phase p-${ev.phase}`}>{phase}</span>}
          {ev.api && <span className="wc-tl-v2-api">{ev.api}</span>}
        </div>
        <p className="wc-tl-v2-text">{ev.action}</p>
      </div>
    </div>
  );
}


function countIaMerge(evs: GameEvent[]) {
  return evs.filter((e) => e.api === "IA merge" && (e.action.includes("→") || e.action.includes("✓") || e.action.includes("cache"))).length;
}

export function AdminLivePanel({ syncStatus, currentTime, error }: AdminLivePanelProps) {
  const [openTimeline, setOpenTimeline] = useState<number | string | null>(null);
  const [openConfirm, setOpenConfirm] = useState<number | string | null>(null);

  const cadence = syncStatus.cadence;
  const fast = Boolean(cadence?.live_now ?? syncStatus.live_now);
  const loopSec = cadence?.loop_seconds ?? syncStatus.interval_seconds ?? (fast ? 30 : 600);
  const goalGap = cadence?.live_poll_gap_seconds ?? 60;

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
      const h = healthMap.get(g.match_number ?? hk);
      return {
        match_number: g.match_number,
        home_team: g.home_team,
        away_team: g.away_team,
        kickoff_at: g.kickoff_at,
        status: g.status,
        score: g.score ?? h?.score,
        goals: h?.goals,
        scorers: g.scorers ?? h?.scorers,
        halftime: g.halftime ?? h?.halftime,
        scorers_complete: g.scorers_complete ?? h?.scorers_complete,
        scorers_final: h?.scorers_final,
        confirmation_sources: h?.confirmation_sources,
        end_source: g.end_source ?? h?.end_source,
        reconfirmed: h?.reconfirmed,
        polls: h?.polls,
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

  const iaToday = syncStatus.requests_today?.ai_reconcile?.calls ?? 0;
  const iaInsightToday = syncStatus.requests_today?.ai_insight?.calls ?? 0;
  const tsdToday = syncStatus.requests_today?.thesportsdb?.calls ?? 0;

  const activeGames = games.filter((g) => g.status === "live" || g.status === "finished");

  return (
    <div className="wc-dash">
      {error && <p className="bolao-feedback error">{error}</p>}

      <div className={`wc-dash-hero${fast ? " live" : ""}`}>
        <div className="wc-dash-hero-main">
          <span className={`wc-dash-pulse${fast ? " on" : ""}`}>
            <Radio size={13} /> Placar ao vivo
          </span>
          <strong className="wc-dash-mode">
            Modo: {fast ? "RÁPIDO" : "LENTO"}
            <span className={`wc-dash-mode-badge${fast ? " fast" : " slow"}`}>
              {fast ? <Zap size={12} /> : <Clock3 size={12} />}
              1 req / {fast ? "30s" : "10min"}
            </span>
          </strong>
          <span className="wc-dash-hero-sub">
            Próximo ciclo {inLabel(cadence?.last_sync_at ?? syncStatus.last_sync, loopSec, currentTime)}
            {cadence?.goal_pending && ` · gol pendente · paga ~${goalGap}s`}
          </span>
        </div>
        <div className="wc-dash-hero-stats">
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Activity size={11} /> Ao vivo</span>
            <strong>{syncStatus.totals.live_games ?? 0}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Database size={11} /> TSD hoje</span>
            <strong>{tsdToday}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Bot size={11} /> IA hoje</span>
            <strong>{iaToday + iaInsightToday}</strong>
          </div>
        </div>
      </div>

      {/* Regras TheSportsDB + IA */}
      <section className="wc-dash-rules">
        <div className="wc-dash-rule-card tsd">
          <strong>TheSportsDB — quando roda?</strong>
          <p><b>Não</b> fica ao vivo o tempo todo. Só 2 momentos:</p>
          <ul>
            <li><span className="wc-tl-v2-phase p-ao_vivo_failover">FAILOVER</span> ao vivo se API-Football sem cota</li>
            <li><span className="wc-tl-v2-phase p-reconfirmacao">RECONF</span> 1× +10min após o fim</li>
          </ul>
          <small>Placar · intervalo · fim ao vivo = <b>football-data</b> (grátis, todo ciclo)</small>
        </div>
        <div className="wc-dash-rule-card ia">
          <strong>IA — regras de uso</strong>
          <p>
            <b>Merge ({iaToday} hoje):</b> toda confirmação de artilheiro (ao vivo, fim, +10min).
            Cruza fontes + elenco. Cacheada — não repete se nada mudou.
          </p>
          <p>
            <b>Resenha ({iaInsightToday} hoje):</b> 1 frase no card do próximo jogo (mín. 4 palpites, cache 30min).
            Fala <em>intenção</em> de time e artilheiro — sem números nem pacoca.
          </p>
        </div>
      </section>

      {activeGames.length > 0 && (
        <section className="wc-dash-games">
          <div className="wc-dash-section-title">Jogos — timeline visual</div>
          <div className="wc-dash-game-list">
            {activeGames.map((game) => {
              const key = eventKey(game);
              const evs = eventsByGame.get(game.match_number ?? `${game.home_team} x ${game.away_team}`) ?? [];
              const chronological = [...evs].reverse();
              const timelineOpen = openTimeline === key;
              const confirmOpen = openConfirm === key;
              const af = game.polls?.api_football ?? 0;
              const tsd = game.polls?.thesportsdb ?? 0;
              const iaHere = countIaMerge(evs);
              const lastFail = evs.find((e) => e.ok === false);
              const lastOk = evs.find((e) => e.ok === true);

              return (
                <article className={`wc-dash-game-card ${game.status}${lastFail && !lastOk ? " has-fail" : ""}`} key={String(key)}>
                  <div className="wc-dash-game-head">
                    <div className="wc-dash-game-match">
                      <span><TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}</span>
                      <strong className="wc-dash-game-score">{game.score ?? "0-0"}</strong>
                      <span>{teamLabel(game.away_team)} <TeamFlag team={game.away_team} /></span>
                    </div>
                    <div className="wc-dash-game-chips">
                      <span className={`wc-today-badge ${game.status}`}>
                        {game.status === "live" && <span className="wc-live-dot small" />}
                        {game.halftime ? "Intervalo" : game.status === "live" ? "Ao vivo" : "Encerrado"}
                      </span>
                      {game.kickoff_at && <span className="wc-dash-chip">jogo {timeHM(game.kickoff_at)}</span>}
                      <span className="wc-dash-chip">AF×{af}</span>
                      <span className="wc-dash-chip">TSD×{tsd}</span>
                      <span className="wc-dash-chip ia">IA×{iaHere}</span>
                    </div>
                    {game.scorers && (
                      <div className="wc-dash-game-scorers"><Goal size={12} /> {game.scorers}</div>
                    )}
                  </div>

                  <button
                    className={`wc-dash-drop${timelineOpen ? " open" : ""}`}
                    onClick={() => setOpenTimeline(timelineOpen ? null : key)}
                    type="button"
                  >
                    <span>Timeline</span>
                    <small>{chronological.length} eventos · selo por fase/API</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {timelineOpen && (
                    <div className="wc-dash-drop-body timeline-v2">
                      {chronological.length > 0 ? (
                        <div className="wc-tl-v2-list">
                          {chronological.map((ev, i) => (
                            <TimelineRow ev={ev} key={`${ev.at}-${i}`} />
                          ))}
                        </div>
                      ) : (
                        <p className="wc-dash-empty">Aguardando eventos…</p>
                      )}
                      <div className="wc-tl-v2-legend">
                        <span className="s-ok">✓ achou</span>
                        <span className="s-err">✗ falhou / sem cota</span>
                        <span className="s-retry">↻ retry</span>
                        <span className="s-ia">🤖 IA merge</span>
                      </div>
                    </div>
                  )}

                  <button
                    className={`wc-dash-drop confirm${confirmOpen ? " open" : ""}`}
                    onClick={() => setOpenConfirm(confirmOpen ? null : key)}
                    type="button"
                  >
                    <span>Confirmação</span>
                    <small>quem achou no fim e na reconf</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {confirmOpen && (
                    <div className="wc-dash-drop-body confirm-v2">
                      {chronological
                        .filter((e) => e.phase === "fim" || e.phase === "reconfirmacao")
                        .map((ev, i) => (
                          <TimelineRow ev={ev} key={`c-${i}`} />
                        ))}
                      {chronological.filter((e) => e.phase === "fim" || e.phase === "reconfirmacao").length === 0 && (
                        <p className="wc-dash-empty">Fim e reconf ainda não rodaram.</p>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}

      {syncStatus.requests_today && (
        <section className="wc-dash-apis">
          <div className="wc-dash-section-title detail">Cotas do dia (UTC)</div>
          <div className="wc-dash-apis-grid">
            {Object.entries(syncStatus.requests_today).map(([key, r]) => (
              <div className="wc-api-card" key={key}>
                <div className="wc-api-card-head">
                  <strong>{key.replace("_", "-")}</strong>
                  <span className="wc-api-calls">{r.calls}{r.daily_cap ? `/${r.daily_cap}` : ""}</span>
                </div>
                {r.remaining != null && <span className="wc-api-rem">sobra {r.remaining}</span>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
