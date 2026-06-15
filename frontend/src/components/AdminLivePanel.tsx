"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Clock3, Goal, Radio, Zap } from "lucide-react";
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
  polls?: { gratuito: number; api_football: number; thesportsdb: number; ia: number };
  goal_flow?: { score: string; stage: string } | null;
};

type GameEvent = NonNullable<WorldCupSyncStatus["game_events"]>[number];

type TlDisplay = {
  kind: string;
  api: string;
  result: string;
  detail: string;
  tone: string;
};

const API_LABEL: Record<string, string> = {
  "football-data": "API grátis",
  "API-Football": "API paga",
  "TheSportsDB": "SportsDB",
  "TheSportsDB+openfootball": "SportsDB+OF",
  "openfootball+API paga": "OF+API paga",
  "IA merge": "IA",
  pipeline: "Pipeline",
  calendário: "Sistema",
  openfootball: "openfootball",
  auto: "Sistema",
};

function formatApiLabel(apiKey: string): string {
  if (apiKey.startsWith("IA+")) return "IA";
  return API_LABEL[apiKey] ?? apiKey;
}

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

function cleanText(s: string) {
  return s
    .replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "")
    .replace(/[→↻⚠✓✗⏱⏸▶🏁🟢🤖🔁⚽]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function pickNames(raw: string) {
  const m = raw.match(/(?:achou|resultado|artilheiro|confirmou)[:\s]+(.+)/i);
  return m?.[1]?.split("(")[0]?.split("·")[0]?.trim() ?? "";
}

/** Remove spam de logs legados (failover em loop, aguardando 60s, etc.) */
function compactTimeline(evs: GameEvent[], retryMax: number): GameEvent[] {
  const out: GameEvent[] = [];
  let lastSig = "";
  for (const ev of chrono(evs)) {
    const raw = cleanText(ev.action);
    if (/aguardando consulta|próxima tentativa|failover thesportsdb.*sem cota/i.test(raw)) continue;
    if (/segue retry$/i.test(raw)) continue;
    const d = parseTimelineEvent(ev, retryMax);
    if (d.kind === "REGISTRO" && d.tone === "plain") continue;
    const sig = `${d.kind}|${d.api}|${d.result}|${d.detail}`;
    if (sig === lastSig) continue;
    lastSig = sig;
    out.push(ev);
  }
  return out;
}

function parseTimelineEvent(ev: GameEvent, retryMax: number): TlDisplay {
  const raw = cleanText(ev.action);
  const apiKey = ev.api ?? "";
  const isFim = ev.phase === "fim";
  const isReconf = ev.phase === "reconfirmacao";
  const tentativa = raw.match(/\((\d+)\/(\d+)\)/);

  if (/gol \d+-\d+ — fluxo do gol concluído/i.test(raw)) {
    const score = raw.match(/gol (\d+-\d+)/i)?.[1];
    return { kind: "GOL OK", api: "Pipeline", result: "Completo", detail: score ? `Gol ${score} finalizado` : "Fluxo OK", tone: "ok" };
  }
  if (/^gol \d+-\d+ —/i.test(raw)) {
    const score = raw.match(/^gol (\d+-\d+)/i)?.[1];
    const rest = raw.replace(/^gol \d+-\d+ —\s*/i, "");
    const inner = parseTimelineEvent({ ...ev, action: rest }, retryMax);
    return { ...inner, detail: score ? `Gol ${score} · ${inner.detail}` : inner.detail };
  }
  if (/início|começou/i.test(raw) || apiKey === "calendário") {
    return { kind: "INÍCIO", api: "Sistema", result: "OK", detail: "Jogo começou", tone: "milestone" };
  }
  if (/gol detectado|placar virou|gol ·/i.test(raw)) {
    const score = raw.match(/(\d+-\d+)/)?.[1];
    return { kind: "GOL", api: "API grátis", result: "Detectado", detail: score ? `Placar ${score}` : "Novo gol", tone: "gol" };
  }
  if (/^intervalo$/i.test(raw)) {
    return { kind: "INTERVALO", api: "API grátis", result: "—", detail: "Intervalo", tone: "milestone" };
  }
  if (/2º tempo/i.test(raw)) {
    return { kind: "2º TEMPO", api: "API grátis", result: "—", detail: "Volta do intervalo", tone: "milestone" };
  }
  if (/api paga — nova tentativa/i.test(raw)) {
    const score = raw.match(/^gol (\d+-\d+)/i)?.[1];
    const t = raw.match(/\((\d+)\/(\d+)\)/);
    return {
      kind: "CONSULTA GOL", api: "API paga", result: "Retry",
      detail: score ? `Gol ${score} · tentativa ${t?.[1]}/${t?.[2]}` : `Tentativa ${t?.[1]}/${t?.[2]}`,
      tone: "call",
    };
  }
  if (/api paga — consulta/i.test(raw)) {
    return { kind: "CONSULTA GOL", api: "API paga", result: "Chamou", detail: "Busca artilheiro", tone: "call" };
  }
  if (/api paga — achou/i.test(raw)) {
    return { kind: "CONSULTA GOL", api: "API paga", result: "Achou", detail: pickNames(raw) || "Artilheiro", tone: "ok" };
  }
  if (/api paga — fixture direto|api paga — jogo encerrou/i.test(raw)) {
    return {
      kind: "CONSULTA GOL", api: "API paga", result: "Jogo encerrou",
      detail: "Fora do ao vivo — confirmação no fim", tone: "milestone",
    };
  }
  if (/api paga — não achou/i.test(raw)) {
    return {
      kind: "CONSULTA GOL", api: "API paga", result: "Não achou",
      detail: tentativa ? `Tentativa ${tentativa[1]}/${tentativa[2]}` : "Sem artilheiro",
      tone: "retry",
    };
  }
  if (/api paga — sem cota/i.test(raw)) {
    return { kind: "CONSULTA GOL", api: "API paga", result: "Sem cota", detail: "Vai para SportsDB", tone: "warn" };
  }
  if (/api paga — erro/i.test(raw)) {
    return { kind: "CONSULTA GOL", api: "API paga", result: "Erro", detail: "Erro na resposta", tone: "err" };
  }
  if (/sportsdb fallback — motivo/i.test(raw)) {
    const motivo = raw.match(/motivo:\s*(.+)/i)?.[1] ?? "";
    return { kind: "FALLBACK", api: "SportsDB", result: "Chamou", detail: motivo, tone: "call" };
  }
  if (/sportsdb — achou/i.test(raw)) {
    return { kind: "FALLBACK", api: "SportsDB", result: "Achou", detail: pickNames(raw), tone: "ok" };
  }
  if (/sportsdb — não achou/i.test(raw)) {
    return {
      kind: "FALLBACK", api: "SportsDB", result: "Não achou",
      detail: tentativa ? `Tentativa ${tentativa[1]}/${tentativa[2]}` : "—",
      tone: "retry",
    };
  }
  if (/sportsdb — passou/i.test(raw)) {
    return { kind: "FALLBACK", api: "SportsDB", result: "Passou", detail: "Aguarda próximo gol", tone: "skip" };
  }
  if (/ia — consulta/i.test(raw)) {
    const src = raw.match(/\(([^)]+)\)/)?.[1] ?? "";
    return { kind: "IA", api: "IA", result: "Chamou", detail: src || "Cruza fontes", tone: "ia" };
  }
  if (/ia — resultado/i.test(raw)) {
    return { kind: "IA", api: "IA", result: "Salvou", detail: pickNames(raw) || "—", tone: "ok" };
  }
  if (/ia —/i.test(raw) && ev.ok === false) {
    return { kind: "IA", api: "IA", result: "Falhou", detail: raw.replace(/^ia —\s*/i, ""), tone: "err" };
  }
  if (/finalização|encerrado/i.test(raw) && !isReconf) {
    const score = raw.match(/(\d+-\d+)/)?.[1];
    return { kind: "FINALIZAÇÃO", api: "API grátis", result: "OK", detail: score ? `Placar ${score}` : "Jogo encerrou", tone: "milestone" };
  }
  if (/confirmação final|consulta api paga — confirmação/i.test(raw)) {
    return { kind: "CONFIRMAÇÃO", api: "API paga", result: "Chamou", detail: "Confirma no fim", tone: "call" };
  }
  if (isFim && /api paga — achou/i.test(raw)) {
    return { kind: "CONFIRMAÇÃO", api: "API paga", result: "Achou", detail: pickNames(raw), tone: "ok" };
  }
  if (/openfootball reconfirmação — achou/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "openfootball", result: "Achou", detail: pickNames(raw), tone: "ok" };
  }
  if (/reconfirmação — openfootball ok|reconfirmação — sportsdb ok/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "Pipeline", result: "Segue", detail: raw.replace(/^reconfirmação —\s*/i, ""), tone: "ok" };
  }
  if (/openfootball reconfirmação — sem dados/i.test(raw)) {
    return {
      kind: "RECONFIRMAÇÃO", api: "openfootball", result: "Não achou",
      detail: tentativa ? `Tentativa ${tentativa[1]}/${tentativa[2]}` : "Aguarda retry",
      tone: "retry",
    };
  }
  if (isReconf && /ia — consulta/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "IA", result: "Chamou", detail: "Cruza openfootball + SportsDB + API paga", tone: "ia" };
  }
  if (isReconf && /ia — resultado/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "IA", result: "Validou", detail: pickNames(raw), tone: "ok" };
  }
  if (/sportsdb reconfirmação — adiada/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "SportsDB", result: "Adiada", detail: "Cota do ciclo", tone: "retry" };
  }
  if (/sportsdb reconfirmação — achou/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "SportsDB", result: "Achou", detail: pickNames(raw), tone: "ok" };
  }
  if (/sportsdb reconfirmação — sem dados/i.test(raw)) {
    return {
      kind: "RECONFIRMAÇÃO", api: "SportsDB", result: "Não achou",
      detail: tentativa ? `Tentativa ${tentativa[1]}/${tentativa[2]}` : "Aguarda retry",
      tone: "retry",
    };
  }
  if (/reconfirmação — tentativa/i.test(raw)) {
    const t = raw.match(/\((\d+)\/(\d+)\)/);
    return {
      kind: "RECONFIRMAÇÃO", api: "Pipeline", result: "Tentativa",
      detail: t ? `${t[1]}/${t[2]}` : "—", tone: "call",
    };
  }
  if (/reconfirmação — aguardando|reconfirmação — ia sem|reconfirmação — artilheiros incompletos|reconfirmação — fontes não batem/i.test(raw)) {
    return { kind: "RECONFIRMAÇÃO", api: "Pipeline", result: "Retry", detail: raw.replace(/^reconfirmação —\s*/i, ""), tone: "retry" };
  }
  if (/reconfirmação — resultado/i.test(raw)) {
    return {
      kind: "RECONFIRMAÇÃO",
      api: formatApiLabel(apiKey),
      result: ev.ok === false ? "Incompleto" : "Confirmado",
      detail: pickNames(raw) || raw.replace(/^reconfirmação — resultado:?\s*/i, ""),
      tone: ev.ok === false ? "warn" : "ok",
    };
  }
  if (/reconfirmação/i.test(raw)) {
    return {
      kind: "RECONFIRMAÇÃO",
      api: formatApiLabel(apiKey),
      result: ev.ok === false ? "Incompleto" : "OK",
      detail: pickNames(raw) || raw.replace(/^reconfirmação[^:]*:?\s*/i, ""),
      tone: ev.ok === false ? "warn" : "ok",
    };
  }

  return {
    kind: "—",
    api: formatApiLabel(apiKey) || "—",
    result: ev.ok === true ? "OK" : ev.ok === false ? "Falhou" : "—",
    detail: raw.slice(0, 60) || "—",
    tone: ev.ok === false ? "err" : "plain",
  };
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

function buildConfirmSteps(evs: GameEvent[], game: GameRow, retryMax: number): ConfirmStep[] {
  const c = chrono(evs);

  const fimGratis = lastOf(c, (e) => {
    const d = parseTimelineEvent(e, retryMax);
    return d.kind === "FINALIZAÇÃO";
  });
  const fimPaga = lastOf(c, (e) => e.phase === "fim" && e.api === "API-Football" && e.ok === true);
  const fimPagaFail = lastOf(c, (e) => e.phase === "fim" && e.api === "API-Football" && e.ok === false);
  const fimIa = lastOf(c, (e) => e.phase === "fim" && e.api === "IA merge" && e.ok === true);
  const reconfResult = lastOf(c, (e) => e.phase === "reconfirmacao" && /reconfirmação — resultado/i.test(e.action) && e.ok === true);
  const reconfRetry = lastOf(c, (e) => e.phase === "reconfirmacao" && e.ok === false && /reconfirmação —/i.test(e.action));
  const reconfOfOk = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "openfootball" && e.ok === true);
  const reconfOfFail = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "openfootball" && e.ok === false);
  const reconfTsdOk = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "TheSportsDB" && e.ok === true);
  const reconfTsdFail = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "TheSportsDB" && e.ok === false);
  const reconfIa = lastOf(c, (e) => e.phase === "reconfirmacao" && e.api === "IA merge" && e.ok === true && /resultado/i.test(e.action));

  const steps: ConfirmStep[] = [];

  if (game.end_source || fimGratis) {
    steps.push({
      title: "Finalizou",
      status: "ok",
      when: (fimGratis ?? fimPaga)?.at ? timeFull((fimGratis ?? fimPaga)!.at) : undefined,
      who: "API grátis",
      detail: fimGratis ? parseTimelineEvent(fimGratis, retryMax).detail : undefined,
    });
  } else if (game.status === "live") {
    steps.push({ title: "Finalizou", status: "wait", detail: "Jogo ainda rolando" });
  } else {
    steps.push({ title: "Finalizou", status: "na", detail: "Aguardando" });
  }

  if (fimPaga) {
    const fimIaNames = fimIa ? pickNames(cleanText(fimIa.action)) : "";
    steps.push({
      title: "Confirmação",
      status: "ok",
      when: timeFull(fimPaga.at),
      who: "API paga + IA",
      detail: [pickNames(cleanText(fimPaga.action)), fimIaNames ? `IA: ${fimIaNames}` : ""]
        .filter(Boolean)
        .join(" · "),
    });
  } else if (fimPagaFail) {
    steps.push({
      title: "Confirmação",
      status: "err",
      when: timeFull(fimPagaFail.at),
      who: "API paga",
      detail: parseTimelineEvent(fimPagaFail, retryMax).detail,
    });
  } else if (game.status === "finished") {
    steps.push({ title: "Confirmação", status: "wait", detail: "Aguardando API paga no fim" });
  }

  if (reconfResult || game.reconfirmed) {
    const parts: string[] = [];
    if (reconfOfOk) parts.push(`openfootball: ${pickNames(cleanText(reconfOfOk.action))}`);
    else if (reconfOfFail) parts.push("openfootball: não achou");
    if (reconfTsdOk) parts.push(`SportsDB: ${pickNames(cleanText(reconfTsdOk.action))}`);
    else if (reconfTsdFail) parts.push("SportsDB: não achou");
    if (reconfIa) parts.push(`IA: ${pickNames(cleanText(reconfIa.action))}`);
    steps.push({
      title: "Reconfirmação",
      status: "ok",
      when: reconfResult ? timeFull(reconfResult.at) : undefined,
      who: "openfootball + SportsDB + API paga → IA",
      detail: parts.length ? parts.join(" · ") : "Artilheiros reconfirmados",
    });
  } else if (reconfRetry || (game.status === "finished" && game.scorers_final)) {
    const parts: string[] = [];
    if (reconfOfOk) parts.push(`openfootball: ${pickNames(cleanText(reconfOfOk.action))}`);
    if (reconfTsdFail) parts.push("SportsDB: aguardando");
    steps.push({
      title: "Reconfirmação",
      status: "wait",
      when: reconfRetry ? timeFull(reconfRetry.at) : undefined,
      who: "openfootball + SportsDB + API paga → IA",
      detail: parts.length
        ? `${parts.join(" · ")} · ${parseTimelineEvent(reconfRetry ?? reconfOfOk!, retryMax).detail}`
        : "Agendada +10min após o fim",
    });
  }

  return steps;
}

function FlowDiagram({ retryMax }: { retryMax: number }) {
  return (
    <div className="wc-flow-diagram">
      <div className="wc-flow-steps">
        <div className="wc-flow-step">
          <span className="wc-flow-kind">Início / Gol / Intervalo / Fim</span>
          <span className="wc-flow-api free">API grátis</span>
        </div>
        <div className="wc-flow-arrow-v">↓ gol detectado</div>
        <div className="wc-flow-step">
          <span className="wc-flow-kind">Consulta artilheiro</span>
          <span className="wc-flow-api paid">API paga</span>
          <span className="wc-flow-api ia">IA</span>
        </div>
        <div className="wc-flow-arrow-v">↓ não achou ({retryMax}x) ou sem cota</div>
        <div className="wc-flow-step">
          <span className="wc-flow-kind">Fallback</span>
          <span className="wc-flow-api tsd">SportsDB</span>
          <span className="wc-flow-api ia">IA</span>
        </div>
        <div className="wc-flow-arrow-v">↓ fim → API paga + IA → +10min reconf (openfootball + SportsDB + API paga → IA)</div>
      </div>
      <p className="wc-flow-note">
        Cota API paga reseta 00:00 UTC. Máx ~10 chamadas/jogo. IA sempre que acha artilheiro (paga ou fallback).
      </p>
    </div>
  );
}

function TimelineRow({ ev, retryMax }: { ev: GameEvent; retryMax: number }) {
  const d = parseTimelineEvent(ev, retryMax);
  return (
    <div className={`wc-tl-v3 tone-${d.tone}`}>
      <time className="wc-tl-v3-time">{timeFull(ev.at)}</time>
      <span className={`wc-tl-v3-kind k-${d.tone}`}>{d.kind}</span>
      <span className={`wc-tl-v3-api a-${d.api.replace(/\s+/g, "-").toLowerCase()}`}>{d.api}</span>
      <span className={`wc-tl-v3-result r-${d.tone}`}>{d.result}</span>
      <span className="wc-tl-v3-detail">{d.detail}</span>
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

function goalFlowLabel(flow?: GameRow["goal_flow"]): string | null {
  if (!flow || flow.stage === "done") return null;
  const step = { detected: "API paga", tsd: "SportsDB", ia: "IA" }[flow.stage] ?? flow.stage;
  return `Gol ${flow.score} → ${step}`;
}

/** Borda do card: vermelho = falha real; laranja = reconf pendente; verde = tudo confirmado */
function gameCardTone(evs: GameEvent[], game: GameRow, retryMax: number): "ok" | "warn" | "fail" {
  const steps = buildConfirmSteps(evs, game, retryMax);
  if (steps.some((s) => s.status === "err")) return "fail";
  if (game.status === "live" && game.goal_flow && game.goal_flow.stage !== "done") return "warn";
  if (game.status === "finished" && game.scorers_final && game.reconfirmed) return "ok";
  if (game.status === "finished" && game.scorers_final && !game.reconfirmed) return "warn";
  if (steps.some((s) => s.status === "wait")) return "warn";
  return "ok";
}

export function AdminLivePanel({ syncStatus, currentTime, error }: AdminLivePanelProps) {
  const [openTimeline, setOpenTimeline] = useState<number | string | null>(null);
  const [openConfirm, setOpenConfirm] = useState<number | string | null>(null);

  const cadence = syncStatus.cadence;
  const fast = Boolean(cadence?.live_now ?? syncStatus.live_now);
  const loopSec = cadence?.loop_seconds ?? syncStatus.interval_seconds ?? (fast ? 30 : 600);
  const retryMax = cadence?.live_retry_max ?? 2;

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
        goal_flow: g.goal_flow,
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
        goal_flow: h?.goal_flow,
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
        goal_flow: g.goal_flow,
      });
    }
    const order = { live: 0, finished: 1, scheduled: 2, postponed: 3 };
    return merged.sort((a, b) => {
      const sa = order[a.status as keyof typeof order] ?? 9;
      const sb = order[b.status as keyof typeof order] ?? 9;
      if (sa !== sb) return sa - sb;
      // Mais recente primeiro (jogo de hoje no topo)
      return new Date(b.kickoff_at ?? 0).getTime() - new Date(a.kickoff_at ?? 0).getTime();
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

  const apiPaid = syncStatus.requests_today?.api_football;
  const apiRem = apiPaid?.remaining ?? syncStatus.sources?.api_football_daily_remaining;
  const activeGames = games.filter((g) => g.status === "live" || g.status === "finished");
  const liveGame = games.find((g) => g.status === "live");
  const livePolls = liveGame?.polls;

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
            {cadence?.goal_pending && " · falta artilheiro"}
          </span>
        </div>
        <div className="wc-dash-hero-stats">
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k">API paga</span>
            <strong>{apiRem ?? "—"} rest.</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k">Ciclo</span>
            <strong>{fast ? "30s" : "10min"}</strong>
          </div>
          <div className="wc-dash-stat">
            <span className="wc-dash-stat-k">Artilheiro</span>
            <strong>{cadence?.goal_pending ? "Pendente" : "OK"}</strong>
          </div>
          {livePolls && (
            <>
              <div className="wc-dash-stat">
                <span className="wc-dash-stat-k">Gols</span>
                <strong>{livePolls.gratuito ?? 0}x</strong>
              </div>
              <div className="wc-dash-stat">
                <span className="wc-dash-stat-k">Paga</span>
                <strong>{livePolls.api_football ?? 0}x</strong>
              </div>
              <div className="wc-dash-stat">
                <span className="wc-dash-stat-k">DB</span>
                <strong>{livePolls.thesportsdb ?? 0}x</strong>
              </div>
              <div className="wc-dash-stat">
                <span className="wc-dash-stat-k">IA</span>
                <strong>{livePolls.ia ?? 0}x</strong>
              </div>
            </>
          )}
        </div>
      </div>

      <FlowDiagram retryMax={retryMax} />

      {activeGames.length > 0 && (
        <section className="wc-dash-games">
          <div className="wc-dash-section-title">Jogos</div>
          <div className="wc-dash-game-list">
            {activeGames.map((game) => {
              const key = eventKey(game);
              const evs = eventsByGame.get(game.match_number ?? `${game.home_team} x ${game.away_team}`) ?? [];
              const chronological = compactTimeline(evs, retryMax);
              const timelineOpen = openTimeline === key;
              const confirmOpen = openConfirm === key;
              const confirmSteps = buildConfirmSteps(evs, game, retryMax);
              const cardTone = gameCardTone(evs, game, retryMax);

              return (
                <article className={`wc-dash-game-card ${game.status}${cardTone === "fail" ? " has-fail" : cardTone === "warn" ? " has-warn" : cardTone === "ok" && game.status === "finished" && game.scorers_final && game.reconfirmed ? " confirmed" : ""}`} key={String(key)}>
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
                      <span className="wc-dash-chip gratis">Gols {game.polls?.gratuito ?? 0}x</span>
                      <span className="wc-dash-chip paid">Paga {game.polls?.api_football ?? 0}x</span>
                      <span className="wc-dash-chip tsd">DB {game.polls?.thesportsdb ?? 0}x</span>
                      <span className="wc-dash-chip ia">IA {game.polls?.ia ?? 0}x</span>
                      {goalFlowLabel(game.goal_flow) && (
                        <span className="wc-dash-chip flow">{goalFlowLabel(game.goal_flow)}</span>
                      )}
                    </div>
                    {game.scorers && (
                      <div className="wc-dash-game-scorers"><Goal size={12} /> {game.scorers}</div>
                    )}
                  </div>

                  <button
                    className={`wc-dash-drop confirm${confirmOpen ? " open" : ""}`}
                    onClick={() => setOpenConfirm(confirmOpen ? null : key)}
                    type="button"
                  >
                    <span>Confirmação</span>
                    <small>finalizou · paga · reconf</small>
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

                  <button
                    className={`wc-dash-drop${timelineOpen ? " open" : ""}`}
                    onClick={() => setOpenTimeline(timelineOpen ? null : key)}
                    type="button"
                  >
                    <span>Timeline</span>
                    <small>{chronological.length} eventos</small>
                    <ChevronDown size={15} className="wc-dash-drop-chevron" />
                  </button>
                  {timelineOpen && (
                    <div className="wc-dash-drop-body timeline-v3">
                      {chronological.length > 0 ? (
                        <>
                          <div className="wc-tl-v3-head">
                            <span>Hora</span>
                            <span>Etapa</span>
                            <span>Fonte</span>
                            <span>Resultado</span>
                            <span>Detalhe</span>
                          </div>
                          <div className="wc-tl-v3-list">
                            {chronological.map((ev, i) => (
                              <TimelineRow ev={ev} retryMax={retryMax} key={`${ev.at}-${i}`} />
                            ))}
                          </div>
                        </>
                      ) : (
                        <p className="wc-dash-empty">Sem eventos ainda.</p>
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
          <div className="wc-dash-section-title detail">Cotas hoje (reset 00:00 UTC)</div>
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
