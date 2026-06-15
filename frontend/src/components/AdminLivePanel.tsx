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
  scorers?: string | null;
  halftime?: boolean;
  scorers_final?: boolean;
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

function chrono(evs: GameEvent[]) {
  return [...evs].reverse();
}

function rowTone(ev: GameEvent): string {
  if (ev.cached) return "ia-cache";
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

function lastOf(evs: GameEvent[], pred: (e: GameEvent) => boolean) {
  return evs.find(pred) ?? null;
}

type StepStatus = "ok" | "err" | "wait" | "na";

type ConfirmStep = {
  title: string;
  status: StepStatus;
  when?: string;
  who?: string;
  detail?: string;
};

function buildConfirmSteps(evs: GameEvent[], game: GameRow): ConfirmStep[] {
  const c = chrono(evs);

  const fimGratis = lastOf(c, (e) => e.action.includes("encerrado") || e.action.includes("🏁"));
  const fimPaga = lastOf(c, (e) => e.phase === "fim" && e.api === "API-Football" && e.ok === true);
  const fimPagaFail = lastOf(c, (e) => e.phase === "fim" && e.api === "API-Football" && e.ok === false);
  const fimIa = lastOf(c, (e) => e.phase === "fim" && e.api === "IA merge" && e.ok === true);
  const fimIaFail = lastOf(c, (e) => e.phase === "fim" && e.api === "IA merge" && e.ok === false);
  const reconf = lastOf(c, (e) => e.phase === "reconfirmacao");
  const reconfIa = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "IA merge");
  const reconfTsdOk = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "TheSportsDB" && e.ok === true);
  const reconfTsdFail = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "TheSportsDB" && e.ok === false);

  const steps: ConfirmStep[] = [];

  // 1. Finalizou
  if (game.end_source || fimGratis) {
    steps.push({
      title: "Finalizou",
      status: "ok",
      when: (fimGratis ?? fimPaga)?.at ? timeFull((fimGratis ?? fimPaga)!.at) : undefined,
      who: game.end_source ?? fimGratis?.api ?? "—",
      detail: fimGratis?.action.replace(/^🏁\s*/, ""),
    });
  } else if (game.status === "live") {
    steps.push({ title: "Finalizou", status: "wait", detail: "jogo ainda rolando" });
  } else {
    steps.push({ title: "Finalizou", status: "na", detail: "aguardando" });
  }

  // 2. Confirmação (paga + IA no fim)
  if (fimPaga) {
    const iaTxt = fimIa
      ? (fimIa.cached ? `IA cache: ${fimIa.action.split("—")[1]?.trim()}` : `IA: ${fimIa.action.split("—")[1]?.trim()}`)
      : fimIaFail
        ? "IA falhou"
        : undefined;
    steps.push({
      title: "Confirmação",
      status: "ok",
      when: timeFull(fimPaga.at),
      who: "API-Football",
      detail: [fimPaga.action.replace(/^✓\s*/, ""), iaTxt].filter(Boolean).join(" · "),
    });
  } else if (fimPagaFail) {
    steps.push({
      title: "Confirmação",
      status: "err",
      when: timeFull(fimPagaFail.at),
      who: "API-Football",
      detail: fimPagaFail.action.replace(/^✗\s*/, ""),
    });
  } else if (game.status === "finished") {
    steps.push({ title: "Confirmação", status: "wait", detail: "aguardando API paga no fim" });
  }

  // 3. Reconfirmação (+10min)
  if (reconf) {
    const ok = reconf.ok !== false && (reconfTsdOk || reconfIa?.ok);
    const parts: string[] = [];
    if (reconfTsdOk) parts.push(`TheSportsDB: ${reconfTsdOk.action.replace(/^✓\s*achou:\s*/, "")}`);
    if (reconfTsdFail) parts.push("TheSportsDB: não achou");
    if (reconfIa?.ok) parts.push(reconfIa.cached ? "IA (cache)" : `IA: ${reconfIa.action.split("—")[1]?.trim()}`);
    if (reconf.action.includes("divergência")) parts.push("⚠ divergência");
    steps.push({
      title: "Reconfirmação",
      status: ok ? "ok" : reconfTsdFail ? "err" : "wait",
      when: timeFull(reconf.at),
      who: "TheSportsDB + openfootball + IA",
      detail: parts.length ? parts.join(" · ") : reconf.action,
    });
  } else if (game.status === "finished" && game.scorers_final) {
    steps.push({ title: "Reconfirmação", status: "wait", detail: "agendada +10min após o fim" });
  }

  return steps;
}

function FlowDiagram() {
  return (
    <div className="wc-flow-diagram">
      <div className="wc-flow-row">
        <span className="wc-tl-v2-phase p-gratuito">GRÁTIS</span>
        <span className="wc-flow-arrow">→</span>
        <span>football-data (todo ciclo)</span>
      </div>
      <div className="wc-flow-row indent">
        <span className="wc-flow-arrow">↳ gol?</span>
        <span className="wc-tl-v2-phase p-ao_vivo">AO VIVO</span>
        <span>API-Football →</span>
        <span className="wc-tl-v2-api">IA merge</span>
      </div>
      <div className="wc-flow-row indent warn">
        <span className="wc-flow-arrow">↳ sem cota</span>
        <span className="wc-tl-v2-phase p-ao_vivo_failover">FAILOVER</span>
        <span>TheSportsDB →</span>
        <span className="wc-tl-v2-api">IA merge</span>
      </div>
      <div className="wc-flow-row">
        <span className="wc-tl-v2-phase p-fim">FIM</span>
        <span>API-Football 1× →</span>
        <span className="wc-tl-v2-api">IA merge</span>
      </div>
      <div className="wc-flow-row">
        <span className="wc-tl-v2-phase p-reconfirmacao">RECONF</span>
        <span>TheSportsDB + openfootball →</span>
        <span className="wc-tl-v2-api">IA merge</span>
      </div>
      <p className="wc-flow-note">
        <b>IA merge:</b> tenta cache primeiro (mesma assinatura = 0 chamada OpenAI). Timeline mostra CACHE vs chamada real.
      </p>
    </div>
  );
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
      </div>
      <div className="wc-tl-v2-body">
        <div className="wc-tl-v2-meta">
          <time className="wc-tl-v2-time">{timeFull(ev.at)}</time>
          {phase && <span className={`wc-tl-v2-phase p-${ev.phase}`}>{phase}</span>}
          {ev.api && <span className="wc-tl-v2-api">{ev.api}</span>}
          {ev.cached && <span className="wc-tl-v2-cache">CACHE</span>}
        </div>
        <p className="wc-tl-v2-text">{ev.action}</p>
      </div>
    </div>
  );
}

function ConfirmStepCard({ step }: { step: ConfirmStep }) {
  if (step.status === "na" && !step.detail) return null;
  return (
    <div className={`wc-confirm-step-card s-${step.status}`}>
      <div className="wc-confirm-step-head">
        <strong>{step.title}</strong>
        {step.when && step.when !== "—" && <time>{step.when}</time>}
      </div>
      {step.who && <span className="wc-confirm-who">{step.who}</span>}
      {step.detail && <p className="wc-confirm-detail">{step.detail}</p>}
    </div>
  );
}

function iaStats(evs: GameEvent[]) {
  const real = evs.filter((e) => e.api === "IA merge" && e.action.startsWith("→")).length;
  const cache = evs.filter((e) => e.api === "IA merge" && e.cached).length;
  const fail = evs.filter((e) => e.api === "IA merge" && e.ok === false).length;
  return { real, cache, fail };
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
        scorers: g.scorers,
        halftime: g.halftime,
        scorers_final: g.scorers_final,
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
        scorers: g.scorers ?? h?.scorers,
        halftime: g.halftime ?? h?.halftime,
        scorers_final: h?.scorers_final,
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
        scorers: g.scorers,
        halftime: g.halftime,
        scorers_final: g.scorers_final,
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
            <span className="wc-dash-stat-k"><Database size={11} /> TSD</span>
            <strong>{tsdToday}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k"><Bot size={11} /> IA real</span>
            <strong>{iaToday}</strong>
          </div>
        </div>
      </div>

      <FlowDiagram />

      {activeGames.length > 0 && (
        <section className="wc-dash-games">
          <div className="wc-dash-section-title">Jogos</div>
          <div className="wc-dash-game-list">
            {activeGames.map((game) => {
              const key = eventKey(game);
              const evs = eventsByGame.get(game.match_number ?? `${game.home_team} x ${game.away_team}`) ?? [];
              const chronological = chrono(evs);
              const timelineOpen = openTimeline === key;
              const confirmOpen = openConfirm === key;
              const ia = iaStats(evs);
              const confirmSteps = buildConfirmSteps(evs, game);
              const hasErr = evs.some((e) => e.ok === false);

              return (
                <article className={`wc-dash-game-card ${game.status}${hasErr ? " has-fail" : ""}`} key={String(key)}>
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
                      <span className="wc-dash-chip">AF×{game.polls?.api_football ?? 0}</span>
                      <span className="wc-dash-chip">TSD×{game.polls?.thesportsdb ?? 0}</span>
                      <span className="wc-dash-chip ia">IA {ia.real}r/{ia.cache}c</span>
                    </div>
                    {game.scorers && (
                      <div className="wc-dash-game-scorers"><Goal size={12} /> {game.scorers}</div>
                    )}
                  </div>

                  {/* Confirmação — 3 passos só */}
                  <button
                    className={`wc-dash-drop confirm${confirmOpen ? " open" : ""}`}
                    onClick={() => setOpenConfirm(confirmOpen ? null : key)}
                    type="button"
                  >
                    <span>Confirmação</span>
                    <small>finalizou · paga+IA · reconf</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {confirmOpen && (
                    <div className="wc-dash-drop-body confirm-v2">
                      {confirmSteps.length > 0 ? (
                        confirmSteps.map((step) => <ConfirmStepCard key={step.title} step={step} />)
                      ) : (
                        <p className="wc-dash-empty">Nada a confirmar ainda.</p>
                      )}
                    </div>
                  )}

                  {/* Timeline — histórico completo de requisições */}
                  <button
                    className={`wc-dash-drop${timelineOpen ? " open" : ""}`}
                    onClick={() => setOpenTimeline(timelineOpen ? null : key)}
                    type="button"
                  >
                    <span>Timeline</span>
                    <small>{chronological.length} reqs · histórico completo</small>
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
                        <p className="wc-dash-empty">Sem requisições ainda.</p>
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
          <div className="wc-dash-section-title detail">Cotas hoje · IA resenha: {iaInsightToday}</div>
          <div className="wc-dash-apis-grid">
            {Object.entries(syncStatus.requests_today).map(([key, r]) => (
              <div className="wc-api-card" key={key}>
                <strong>{key.replace(/_/g, "-")}</strong>
                <span className="wc-api-calls">{r.calls}{r.daily_cap ? `/${r.daily_cap}` : ""}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
