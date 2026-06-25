"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ChevronRight,
  Crown,
  Flame,
  Goal,
  Lock,
  Medal,
  Pencil,
  Radio,
  Save,
  Sparkles,
  Target,
  Ticket,
  Trophy,
  Users,
  X,
  Zap,
} from "lucide-react";
import { AdminLivePanel } from "@/components/AdminLivePanel";
import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { TeamFlag } from "@/components/TeamFlag";
import { api } from "@/lib/api";
import { squadTeamKey, teamLabel } from "@/lib/teams";
import { formatEventDate, formatShortDate } from "@/lib/format";
import type {
  Event as AppEvent,
  Leaderboard,
  UserProfile,
  WorldCupBoard,
  WorldCupGame,
  WorldCupLeaderboardEntry,
  WorldCupPrediction,
  WorldCupSquads,
  WorldCupSyncStatus,
} from "@/types";

type PredictionDraft = {
  home: string;
  away: string;
  scorer: string;
};

type ResultDraft = {
  home: string;
  away: string;
  scorers: string;
};


type RankingTab = "geral" | "exatos" | "resultados" | "artilheiro";
type QuickFilter = "today" | "open" | "live" | "finished" | "all";


const stageLabels: Record<string, string> = {
  "group-stage": "Fase de grupos",
  "round-of-32": "32 avos",
  "round-of-16": "Oitavas",
  "quarter-finals": "Quartas",
  "semi-finals": "Semis",
  "third-place": "Terceiro lugar",
  final: "Final",
};

const statusLabels: Record<WorldCupGame["status"], string> = {
  scheduled: "Aberto",
  live: "Ao vivo",
  finished: "Encerrado",
  postponed: "Adiado",
};

function liveGameStatusLabel(game: WorldCupGame): string {
  if (game.status === "live" && game.halftime) return "Intervalo";
  return statusLabels[game.status];
}

const quickFilters: Array<{ key: QuickFilter; label: string }> = [
  { key: "open", label: "Abertos" },
  { key: "live", label: "Ao vivo" },
  { key: "today", label: "Hoje" },
];

const rankingTabs: Array<{ key: RankingTab; label: string }> = [
  { key: "geral", label: "Geral" },
  { key: "exatos", label: "Exatos" },
  { key: "resultados", label: "Vencedor" },
  { key: "artilheiro", label: "Artilheiro" },
];

function sortGames(games: WorldCupGame[]) {
  return [...games].sort((first, second) => new Date(first.kickoff_at).getTime() - new Date(second.kickoff_at).getTime());
}

function replaceGame(games: WorldCupGame[], updated: WorldCupGame) {
  return sortGames(games.map((game) => (game.id === updated.id ? updated : game)));
}

function scoreValue(value: string) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(30, Math.round(parsed)));
}

// Palpites fecham 1 hora antes do início do jogo (mesma regra do backend)
const BET_CUTOFF_MS = 60 * 60 * 1000;

function betCloseAt(game: WorldCupGame) {
  return new Date(game.kickoff_at).getTime() - BET_CUTOFF_MS;
}

function isGameLocked(game: WorldCupGame, now: number) {
  return game.status !== "scheduled" || betCloseAt(game) <= now;
}

function isUpcomingGame(game: WorldCupGame, now: number) {
  return !isGameLocked(game, now);
}

function isSameDay(iso: string, now: number) {
  const date = new Date(iso);
  const today = new Date(now);
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

function countdownParts(targetIso: string, now: number) {
  const distance = Math.max(0, new Date(targetIso).getTime() - now);
  const days = Math.floor(distance / 86_400_000);
  const hours = Math.floor((distance % 86_400_000) / 3_600_000);
  const minutes = Math.floor((distance % 3_600_000) / 60_000);
  const seconds = Math.floor((distance % 60_000) / 1000);
  return { days, hours, minutes, seconds };
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function minutesUntilBetClose(game: WorldCupGame, now: number) {
  return Math.max(0, Math.floor((betCloseAt(game) - now) / 60_000));
}

function urgencyLabel(minutes: number) {
  if (minutes <= 0) return "Fechando agora";
  if (minutes < 60) return `Fecha em ${minutes} min`;
  if (minutes < 1440) return `Fecha em ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  const days = Math.floor(minutes / 1440);
  return `Fecha em ${days}d ${Math.floor((minutes % 1440) / 60)}h`;
}

function maxPoints(rules: WorldCupBoard["rules"] | undefined) {
  return (rules?.exact_score ?? 3) + (rules?.scorer_bonus ?? 1);
}

function rankingValue(entry: WorldCupLeaderboardEntry, tab: RankingTab) {
  if (tab === "exatos") return entry.exact_scores;
  if (tab === "resultados") return entry.outcome_hits;
  if (tab === "artilheiro") return entry.scorer_hits;
  return entry.points;
}

function rankingUnit(tab: RankingTab) {
  if (tab === "exatos") return "exatos";
  if (tab === "resultados") return "certos";
  if (tab === "artilheiro") return "gols";
  return "pts";
}

type BolaoRankingPanelProps = {
  board: WorldCupBoard | null;
  rankingTab: RankingTab;
  onTabChange: (tab: RankingTab) => void;
  sortedRanking: WorldCupLeaderboardEntry[];
  highlights?: WorldCupBoard["highlights"];
  limit?: number;
  compact?: boolean;
  onShowAll?: () => void;
  onSelectEntry?: (entry: WorldCupLeaderboardEntry) => void;
  rankDelta?: Record<number, number>;
  liveMoves?: Record<number, number>;
  glowUserId?: number;
  rankGlow?: { delta: number; pulse: number; mode: "main" | "modal" } | null;
  fxSurface?: "main" | "modal";
};

function RankGlowSparkles() {
  return (
    <span className="bolao-rank-sparkles" aria-hidden="true">
      {Array.from({ length: 4 }, (_, i) => (
        <i className={`bolao-rank-spark s-${i}`} key={i} />
      ))}
    </span>
  );
}

const MODAL_SPIN_MS = 2400;
const MODAL_POINTS_DELAY_MS = MODAL_SPIN_MS;
const MAIN_SCROLL_TO_SPIN_MS = 450;
const MAIN_LEADER_DELAY_MS = 320;

function bolaoFxShownKey(kind: "pts" | "main" | "modal", userId: number, token: string) {
  return `bolao-fx-${kind}-${userId}-${token}`;
}

function scrollToRankCard(userId: number) {
  const padTop = 88;
  const scrollToY = (y: number) => window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });

  const ranking = document.getElementById("bolao-ranking");
  const rankingVisible = ranking && ranking.offsetParent !== null;

  if (rankingVisible && ranking) {
    const target =
      (ranking.querySelector(`[data-rank-user="${userId}"]`) as HTMLElement | null)
      ?? ranking;
    const rect = target.getBoundingClientRect();
    const centerOffset = target === ranking ? 12 : (window.innerHeight - rect.height) / 2;
    scrollToY(rect.top + window.scrollY - padTop - centerOffset);
    return;
  }

  const stat = document.getElementById("bolao-my-rank-stat");
  if (stat) {
    const rect = stat.getBoundingClientRect();
    scrollToY(rect.top + window.scrollY - padTop);
  }
}

function bolaoFxWasShown(key: string) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function bolaoFxMarkShown(key: string) {
  try {
    localStorage.setItem(key, "1");
  } catch {
    /* localStorage indisponível */
  }
}

function MoveBadge({ delta }: { delta?: number }) {
  if (delta === undefined) return <span className="bolao-move stagnant" title="Sem mudança" aria-hidden="true">—</span>;
  if (delta > 0) return <span className="bolao-move up" title={`Subiu ${delta} posição(ões)`}>▲ {delta}</span>;
  if (delta < 0) return <span className="bolao-move down" title={`Caiu ${-delta} posição(ões)`}>▼ {-delta}</span>;
  return <span className="bolao-move stagnant" title="Manteve a posição" aria-hidden="true">—</span>;
}

function BolaoRankingPanel({
  board,
  rankingTab,
  onTabChange,
  sortedRanking,
  highlights,
  limit,
  compact = false,
  onShowAll,
  onSelectEntry,
  rankDelta,
  liveMoves,
  glowUserId,
  rankGlow,
  fxSurface = "main",
}: BolaoRankingPanelProps) {
  const entries = limit ? sortedRanking.slice(0, limit) : sortedRanking;
  const podium = entries.slice(0, 3);
  const listEntries = entries.slice(podium.length);
  const activeGlow = rankGlow?.mode === fxSurface ? rankGlow : null;
  const glowDelta = activeGlow?.delta;

  return (
    <>
      {!compact && (
        <div className="bolao-rules2">
          <span className="eyebrow">Como pontuar</span>
          <div className="bolao-rules2-grid">
            <div className="bolao-rule-card exact">
              <span className="bolao-rule-pts">{board?.rules.exact_score ?? 3}<small>pts</small></span>
              <span className="bolao-rule-ico"><Target size={18} /></span>
              <strong>Placar exato</strong>
              <span>Cravou o resultado certinho (2x1 e terminou 2x1).</span>
            </div>
            <div className="bolao-rule-card outcome">
              <span className="bolao-rule-pts">{board?.rules.correct_outcome ?? 1}<small>pt</small></span>
              <span className="bolao-rule-ico"><CheckCircle2 size={18} /></span>
              <strong>Vencedor certo</strong>
              <span>Acertou quem ganha (ou empate), errou o placar.</span>
            </div>
            <div className="bolao-rule-card scorer">
              <span className="bolao-rule-pts">+{board?.rules.scorer_bonus ?? 1}<small>pt</small></span>
              <span className="bolao-rule-ico"><Goal size={18} /></span>
              <strong>Artilheiro</strong>
              <span>Seu jogador marcou. Soma com os pontos acima.</span>
            </div>
            <div className="bolao-rule-card champion">
              <span className="bolao-rule-pts">{board?.rules.champion ?? 10}<small>pts</small></span>
              <span className="bolao-rule-ico"><Crown size={18} /></span>
              <strong>Campeã da Copa</strong>
              <span>Palpite único de quem leva a taça.</span>
            </div>
          </div>
          <p className="bolao-rules2-note">
            Até <strong>{maxPoints(board?.rules)} pts</strong> por jogo (exato + artilheiro). Palpites fecham 1h antes da
            bola rolar — a pontuação entra sozinha quando o jogo acaba.
          </p>
        </div>
      )}

      <div className="segmented-control bolao-ranking-tabs">
        {rankingTabs.map((tab) => (
          <button
            className={rankingTab === tab.key ? "active" : ""}
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {podium.length > 0 && (
        <div className="bolao-podium2">
          {[podium[1], podium[0], podium[2]].map((entry, column) => {
            const place = column === 1 ? 1 : column === 0 ? 2 : 3;
            if (!entry) return <span className="bolao-podium2-step empty" key={`empty-${column}`} />;
            const pLive = rankingTab === "geral" ? liveMoves?.[entry.user.id] : undefined;
            const pGlow = rankingTab === "geral" && glowUserId === entry.user.id && glowDelta != null;
            const pMoveClass = pGlow
              ? (activeGlow!.mode === "main" && glowDelta > 0
                ? " rank-glow-gold"
                : activeGlow!.mode === "modal"
                  ? " rank-glow-modal"
                  : "")
              : pLive && pLive > 0 ? " moved-up" : pLive && pLive < 0 ? " moved-down" : "";
            return (
              <button
                className={`bolao-podium2-step place-${place}${pMoveClass}`}
                id={glowUserId === entry.user.id ? `bolao-rank-user-${entry.user.id}` : undefined}
                data-rank-user={glowUserId === entry.user.id ? entry.user.id : undefined}
                key={glowUserId === entry.user.id ? `podium-${entry.user.id}-${activeGlow?.pulse ?? 0}` : entry.user.id}
                onClick={() => onSelectEntry?.(entry)}
                type="button"
              >
                {pGlow && (activeGlow?.mode === "main" || activeGlow?.mode === "modal") ? <RankGlowSparkles /> : null}
                {place === 1 && <span className="bolao-podium2-crown" aria-hidden="true">👑</span>}
                <span className="bolao-podium2-avatar">
                  <Avatar user={entry.user} size={place === 1 ? "lg" : "md"} />
                  <span className={`bolao-podium2-medal m-${place}`}>{place}</span>
                </span>
                <span className="bolao-podium2-name">{entry.user.name.split(" ")[0]}</span>
                <span className="bolao-podium2-pts">
                  {rankingValue(entry, rankingTab)}
                  <i>{rankingUnit(rankingTab)}</i>
                </span>
                <span className="bolao-podium2-sub">
                  {entry.exact_scores} exatos · {entry.scorer_hits} ⚽
                  {entry.champion_team && (
                    <span className="bolao-pick-chip" title={`Campeã: ${teamLabel(entry.champion_team)}`}>
                      <TeamFlag team={entry.champion_team} />
                    </span>
                  )}
                </span>
                {rankingTab === "geral" && (entry.round_gain ?? 0) > 0 ? (
                  <span className="bolao-gain">+{entry.round_gain} na rodada 🔥</span>
                ) : null}
                {rankingTab === "geral" && !pGlow && rankDelta?.[entry.user.id] ? (
                  <span className={`bolao-podium2-move ${rankDelta[entry.user.id] > 0 ? "up" : "down"}`}>
                    {rankDelta[entry.user.id] > 0 ? `▲ subiu ${rankDelta[entry.user.id]}` : `▼ caiu ${-rankDelta[entry.user.id]}`}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      )}

      {sortedRanking.length > 0 && (
        <p className="bolao-ranking-hint">Toca em alguém pra ver os palpites jogo a jogo.</p>
      )}

      <div className="bolao-ranking-list">
        {listEntries.map((entry, index) => {
          const live = rankingTab === "geral" ? liveMoves?.[entry.user.id] : undefined;
          const isGlow = rankingTab === "geral" && glowUserId === entry.user.id && glowDelta != null;
          const moveClass = isGlow
            ? (activeGlow!.mode === "main" && glowDelta > 0
              ? " rank-glow-gold"
              : activeGlow!.mode === "modal"
                ? " rank-glow-modal"
                : "")
            : live && live > 0 ? " moved-up" : live && live < 0 ? " moved-down" : "";
          return (
          <button
            className={`bolao-rank-row clickable${moveClass}`}
            id={glowUserId === entry.user.id ? `bolao-rank-user-${entry.user.id}` : undefined}
            data-rank-user={glowUserId === entry.user.id ? entry.user.id : undefined}
            key={glowUserId === entry.user.id ? `row-${entry.user.id}-${activeGlow?.pulse ?? 0}` : entry.user.id}
            onClick={() => onSelectEntry?.(entry)}
            type="button"
          >
            {isGlow && (activeGlow?.mode === "main" || activeGlow?.mode === "modal") ? <RankGlowSparkles /> : null}
            <span className="bolao-rank-pos">
              <strong>{rankingTab === "geral" ? entry.rank : index + podium.length + 1}º</strong>
              {rankingTab === "geral" && !isGlow ? <MoveBadge delta={rankDelta?.[entry.user.id]} /> : null}
            </span>
            <Avatar user={entry.user} size="sm" />
            <span className="bolao-rank-main">
              <span className="bolao-rank-name">
                <span className="bolao-rank-fullname">{entry.user.name}</span>
                {entry.champion_team && (
                  <span className="bolao-pick-chip" title={`Palpite de campeã: ${teamLabel(entry.champion_team)}`}>
                    <TeamFlag team={entry.champion_team} />
                  </span>
                )}
              </span>
              <small>
                {entry.exact_scores} exatos · {entry.scorer_hits} artilheiros · {entry.predictions} palpites
                {rankingTab === "geral" && (entry.round_gain ?? 0) > 0 && (
                  <span className="bolao-gain mini"> · +{entry.round_gain} na rodada 🔥</span>
                )}
              </small>
            </span>
            <b>
              {rankingValue(entry, rankingTab)} <i>{rankingUnit(rankingTab)}</i>
            </b>
            <ChevronRight className="bolao-rank-chevron" size={15} />
          </button>
          );
        })}
        {sortedRanking.length === 0 && <p>Ninguém pontuou ainda. O ranking nasce no primeiro jogo encerrado.</p>}
      </div>

      {compact && onShowAll && sortedRanking.length > entries.length && (
        <button className="wc-ranking-show-more" onClick={onShowAll} type="button">
          <span className="wc-ranking-show-more-copy">
            <Medal size={16} />
            <span>Ver ranking completo</span>
          </span>
          <span className="wc-ranking-show-more-count">
            {sortedRanking.length} participantes <ChevronRight size={15} />
          </span>
        </button>
      )}

      {!compact && highlights?.last_game && (
        <div className="wc-last-game">
          <span className="eyebrow">Último jogo</span>
          <strong>
            <TeamFlag team={highlights.last_game.home_team} /> {teamLabel(highlights.last_game.home_team)}{" "}
            {highlights.last_game.home_score} x {highlights.last_game.away_score}{" "}
            {teamLabel(highlights.last_game.away_team)} <TeamFlag team={highlights.last_game.away_team} />
          </strong>
          {highlights.last_game_winners.length > 0 ? (
            <div className="bolao-ranking-list">
              {highlights.last_game_winners.map((prediction) => (
                <div className="bolao-rank-row" key={prediction.id}>
                  <strong>+{prediction.points}</strong>
                  <Avatar user={prediction.user} size="sm" />
                  <span>{prediction.user.name}</span>
                  <small>
                    {prediction.home_score}x{prediction.away_score}
                    {prediction.scorer_hit ? " ⚽" : ""}
                  </small>
                  <b />
                </div>
              ))}
            </div>
          ) : (
            <p className="bolao-highlight-empty">Ninguém pontuou nesse jogo.</p>
          )}
        </div>
      )}
    </>
  );
}

function BolaoPersonModal({
  entry,
  board,
  onClose,
}: {
  entry: WorldCupLeaderboardEntry;
  board: WorldCupBoard | null;
  onClose: () => void;
}) {
  const games = board?.games ?? [];
  const revealed = games
    .map((game) => ({
      game,
      prediction: (game.predictions ?? []).find((prediction) => prediction.user.id === entry.user.id) ?? null,
    }))
    .filter((item): item is { game: WorldCupGame; prediction: WorldCupPrediction } => item.prediction !== null)
    .sort((a, b) => new Date(b.game.kickoff_at).getTime() - new Date(a.game.kickoff_at).getTime());
  const hidden = games.filter(
    (game) =>
      !game.lock_passed &&
      (game.bettors ?? []).some((bettor) => bettor.id === entry.user.id) &&
      !(game.predictions ?? []).some((prediction) => prediction.user.id === entry.user.id),
  );

  return (
    <div className="event-modal-backdrop wc-person-backdrop" onClick={onClose}>
      <div className="event-modal glass-panel wc-modal wc-person-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div className="wc-person-head">
            <span className={`wc-person-rank rank-${entry.rank <= 3 ? entry.rank : "x"}`}>
              {entry.rank <= 3 ? ["🥇", "🥈", "🥉"][entry.rank - 1] : `${entry.rank}º`}
            </span>
            <Avatar user={entry.user} size="lg" />
            <div>
              <span className="eyebrow">{entry.rank}º no bolão</span>
              <h2>{entry.user.name}</h2>
              <p className="wc-person-stats">
                <strong>{entry.points} pts</strong> · {entry.exact_scores} placares exatos · {entry.scorer_hits}{" "}
                artilheiros · {entry.predictions} palpites
              </p>
            </div>
          </div>
          <button className="modal-close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>

        {entry.champion_team && (
          <div className="wc-person-champion">
            <Crown size={15} />
            <span>
              Campeã: <TeamFlag team={entry.champion_team} /> <strong>{teamLabel(entry.champion_team)}</strong>
              {entry.champion_points > 0 ? ` (+${entry.champion_points} pts)` : ""}
            </span>
          </div>
        )}

        <div className="wc-person-section">
          <span className="eyebrow">Palpites revelados</span>
          {revealed.length > 0 ? (
            <div className="wc-person-bets">
              {revealed.map(({ game, prediction }) => {
                const finished = game.status === "finished" && game.home_score !== null && game.away_score !== null;
                const exact =
                  finished && prediction.home_score === game.home_score && prediction.away_score === game.away_score;
                return (
                  <div className={exact ? "wc-person-bet exact" : "wc-person-bet"} key={game.id}>
                    <div className="wc-person-bet-match">
                      <span>
                        <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)} x {teamLabel(game.away_team)}{" "}
                        <TeamFlag team={game.away_team} />
                      </span>
                      <small>
                        {finished
                          ? `Placar real ${game.home_score} x ${game.away_score}`
                          : statusLabels[game.status]}
                        {" · "}
                        {formatShortDate(game.kickoff_at)}
                      </small>
                    </div>
                    <div className="wc-person-bet-pick">
                      <strong>
                        {prediction.home_score}x{prediction.away_score}
                      </strong>
                      {prediction.scorer_guess && (
                        <span className={prediction.scorer_hit ? "wc-person-scorer hit" : "wc-person-scorer"}>
                          ⚽ {prediction.scorer_guess}
                          {prediction.scorer_hit ? " ✓" : finished ? " ✗" : ""}
                        </span>
                      )}
                      {exact && (
                        <span className="wc-person-exact-badge">
                          <Target size={12} /> placar exato
                        </span>
                      )}
                      {prediction.status === "scored" ? (
                        <b className={prediction.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>
                          {prediction.points > 0 ? `+${prediction.points}` : "0"} pts
                        </b>
                      ) : (
                        <b className="wc-points-badge pending">Aguardando</b>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="rail-empty-copy">
              Nenhum palpite revelado ainda — os palpites aparecem quando o jogo fecha (1h antes da bola rolar).
            </p>
          )}
        </div>

        {hidden.length > 0 && (
          <div className="wc-person-section">
            <span className="eyebrow">Já palpitou (ainda em segredo)</span>
            <div className="wc-person-hidden">
              {hidden.map((game) => (
                <span className="wc-person-hidden-chip" key={game.id}>
                  <Lock size={12} /> <TeamFlag team={game.home_team} /> x <TeamFlag team={game.away_team} />{" "}
                  {formatShortDate(game.kickoff_at)}
                </span>
              ))}
            </div>
            <p className="wc-person-hidden-note">Palpites ficam ocultos até 1 hora antes de cada jogo.</p>
          </div>
        )}
      </div>
    </div>
  );
}

type ScorerPlayer = { id: number; name: string; team: string; number?: number | null; position?: string | null; club?: string | null };

// Atacantes primeiro (quem mais marca), depois meio, defesa e goleiro
const POSITION_ORDER: Record<string, number> = { FW: 0, MF: 1, DF: 2, GK: 3 };
function positionRank(pos?: string | null) {
  const key = (pos || "").toUpperCase().slice(0, 2);
  return POSITION_ORDER[key] ?? 1.5;
}
function positionLabel(pos?: string | null) {
  const key = (pos || "").toUpperCase().slice(0, 2);
  return { FW: "Atacante", MF: "Meia", DF: "Defesa", GK: "Goleiro" }[key] ?? (pos || "");
}

function ScorerPicker({
  game,
  players,
  value,
  onChange,
}: {
  game: WorldCupGame;
  players: ScorerPlayer[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  if (players.length === 0) {
    return (
      <input
        className="input-field wc-scorer-select"
        maxLength={80}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Quem marca? +1 pt bônus"
        value={value}
      />
    );
  }

  const normalizedQuery = query.trim().toLowerCase();
  const matches = (player: ScorerPlayer) => !normalizedQuery || player.name.toLowerCase().includes(normalizedQuery);
  const byPosition = (a: ScorerPlayer, b: ScorerPlayer) =>
    positionRank(a.position) - positionRank(b.position) || (a.number ?? 99) - (b.number ?? 99);
  const groups = [
    { team: game.home_team, players: players.filter((player) => player.team === game.home_team && matches(player)).sort(byPosition) },
    { team: game.away_team, players: players.filter((player) => player.team === game.away_team && matches(player)).sort(byPosition) },
  ].filter((group) => group.players.length > 0);

  const pick = (name: string) => {
    onChange(name);
    setOpen(false);
    setQuery("");
  };

  return (
    <>
      <button
        className={value ? "wc-scorer-trigger picked" : "wc-scorer-trigger"}
        onClick={() => setOpen(true)}
        type="button"
      >
        <span>{value || "Artilheiro (opcional, +1 pt)"}</span>
        {value ? <CheckCircle2 size={15} /> : <Users size={15} />}
      </button>

      {open && typeof document !== "undefined" && createPortal(
        <div className="event-modal-backdrop wc-scorer-backdrop" onClick={() => setOpen(false)}>
          <div className="event-modal glass-panel wc-modal wc-scorer-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Palpite de artilheiro (+1 pt)</span>
                <h2>
                  {teamLabel(game.home_team)} x {teamLabel(game.away_team)}
                </h2>
              </div>
              <button className="modal-close" onClick={() => setOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            <input
              className="input-field wc-scorer-search"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar jogador..."
              type="search"
              value={query}
            />

            <div className="wc-scorer-list">
              {value && (
                <button className="wc-scorer-option clear" onClick={() => pick("")} type="button">
                  <X size={15} />
                  <span>Remover palpite de artilheiro</span>
                </button>
              )}
              {groups.map((group) => (
                <div className="wc-scorer-group" key={group.team}>
                  <span className="wc-scorer-group-label">
                    <TeamFlag team={group.team} /> {teamLabel(group.team)}
                  </span>
                  {group.players.map((player) => (
                    <button
                      className={value === player.name ? "wc-scorer-option active" : "wc-scorer-option"}
                      key={`${player.team}-${player.id}`}
                      onClick={() => pick(player.name)}
                      type="button"
                    >
                      <span className={`wc-scorer-num pos-${(player.position || "").toUpperCase().slice(0, 2) || "NA"}`}>
                        {player.number ?? "–"}
                      </span>
                      <span className="wc-scorer-option-body">
                        <span className="wc-scorer-option-name">{player.name}</span>
                        <small>{[positionLabel(player.position), player.club].filter(Boolean).join(" · ")}</small>
                      </span>
                      {value === player.name && <CheckCircle2 className="wc-scorer-check" size={16} />}
                    </button>
                  ))}
                </div>
              ))}
              {groups.length === 0 && <p className="rail-empty-copy">Nenhum jogador encontrado com esse nome.</p>}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

function FinishedGameCard({ game, viewerId }: { game: WorldCupGame; viewerId?: number }) {
  const [open, setOpen] = useState(false);
  const preds = game.predictions ?? [];
  const mine = viewerId ? preds.find((p) => p.user.id === viewerId) : undefined;
  const others = preds.filter((p) => p.user.id !== mine?.user.id);
  const exactCount = preds.filter((p) => p.home_score === game.home_score && p.away_score === game.away_score).length;
  const scorerCount = preds.filter((p) => p.scorer_hit).length;
  const finished = game.status === "finished";
  const hasPens = game.home_penalties != null && game.away_penalties != null;
  const penWinner = hasPens
    ? (game.home_penalties! > game.away_penalties! ? game.home_team : game.away_team)
    : null;
  const livePeriodLabel =
    game.live_period === "penalties" ? "PÊNALTIS" : game.live_period === "extra-time" ? "PRORROGAÇÃO" : null;

  return (
    <article className={`wc-fcard${finished ? "" : " live"}${game.is_knockout ? " wc-fcard-gold" : ""}`}>
      {game.is_knockout && (
        <div className="wc-ko-banner" aria-hidden="true">
          <Crown size={12} />
          <span>{(stageLabels[game.stage] ?? "Mata-mata").toUpperCase()}</span>
          <span className="wc-ko-banner-sub">✦ MATA-MATA ✦</span>
        </div>
      )}
      <div className="wc-fcard-top">
        <span className="wc-game-stage">
          {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
        </span>
        <span className={`wc-fcard-status ${game.status}${game.halftime ? " halftime" : ""}`}>
          {game.status === "live" && !game.halftime && <span className="wc-live-dot small" />}
          {!finished && livePeriodLabel ? livePeriodLabel : liveGameStatusLabel(game)}
        </span>
        <span className="wc-game-date">{formatEventDate(game.kickoff_at)}</span>
      </div>

      <div className="wc-fcard-score">
        <span className="wc-fcard-team">
          <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}
        </span>
        <strong>{game.home_score ?? "–"}<i>x</i>{game.away_score ?? "–"}</strong>
        <span className="wc-fcard-team away">
          {teamLabel(game.away_team)} <TeamFlag team={game.away_team} />
        </span>
      </div>

      {hasPens && (
        <div className="wc-fcard-pens">
          <span className="wc-fcard-pens-tag">Pênaltis</span>
          <strong>{game.home_penalties} x {game.away_penalties}</strong>
          <span className="wc-fcard-pens-win">🏆 {teamLabel(penWinner!)} avança</span>
        </div>
      )}

      {game.scorers ? (
        <div className="wc-fcard-scorers"><Goal size={13} /> <span>{game.scorers}</span></div>
      ) : finished ? (
        <div className="wc-fcard-scorers muted">Artilheiros ainda não publicados.</div>
      ) : null}

      {mine && (
        <div className={`wc-fcard-mine${(mine.points ?? 0) > 0 ? " won" : ""}`}>
          <span className="wc-fcard-mine-tag">Seu palpite</span>
          <strong>{mine.home_score}x{mine.away_score}</strong>
          {mine.scorer_guess && (
            <span className={mine.scorer_hit ? "wc-fcard-mine-scorer hit" : "wc-fcard-mine-scorer"}>
              ⚽ {mine.scorer_guess}{mine.scorer_hit ? " ✓" : ""}
            </span>
          )}
          <b className={(mine.points ?? 0) > 0 ? "wc-points-badge won" : "wc-points-badge"}>
            {finished ? ((mine.points ?? 0) > 0 ? `+${mine.points} pts` : "0 pts") : "aguardando"}
          </b>
        </div>
      )}

      {preds.length > 0 && (
        <button className="wc-fcard-toggle" onClick={() => setOpen((v) => !v)} type="button">
          <Users size={13} />
          <span>{preds.length} palpitaram · {exactCount} cravaram o placar · {scorerCount} ⚽</span>
          <ChevronRight className={open ? "wc-fcard-chevron open" : "wc-fcard-chevron"} size={15} />
        </button>
      )}

      {open && (
        <div className="wc-fcard-preds">
          {others.map((p) => (
            <div className={p.points > 0 ? "wc-fcard-pred scored" : "wc-fcard-pred"} key={p.id}>
              <Avatar user={p.user} size="sm" />
              <span>{p.user.name.split(" ")[0]}</span>
              <small>
                {p.home_score}x{p.away_score}
                {p.scorer_guess ? ` · ⚽ ${p.scorer_guess}${p.scorer_hit ? " ✓" : ""}` : ""}
              </small>
              <b className={p.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>{p.points > 0 ? `+${p.points}` : "0"}</b>
            </div>
          ))}
          {others.length === 0 && <p className="rail-empty-copy">Só você palpitou nesse jogo.</p>}
        </div>
      )}
    </article>
  );
}

export default function BolaoPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [board, setBoard] = useState<WorldCupBoard | null>(null);
  const [squads, setSquads] = useState<WorldCupSquads>({});
  const [loading, setLoading] = useState(true);
  const [predictionDrafts, setPredictionDrafts] = useState<Record<number, PredictionDraft>>({});
  const [savingPrediction, setSavingPrediction] = useState<number | null>(null);
  const [savedFlash, setSavedFlash] = useState<number | null>(null);
  const [resultModalGame, setResultModalGame] = useState<WorldCupGame | null>(null);
  const [resultDraft, setResultDraft] = useState<ResultDraft>({ home: "0", away: "0", scorers: "" });
  const [savingResult, setSavingResult] = useState(false);
  const [liveModalOpen, setLiveModalOpen] = useState(false);
  const [rankingModalOpen, setRankingModalOpen] = useState(false);
  const [myBetsModalOpen, setMyBetsModalOpen] = useState(false);
  const [championQuery, setChampionQuery] = useState("");
  const [championDraft, setChampionDraft] = useState("");
  const [savingChampion, setSavingChampion] = useState(false);
  const [rankingTab, setRankingTab] = useState<RankingTab>("geral");
  const [selectedEntry, setSelectedEntry] = useState<WorldCupLeaderboardEntry | null>(null);
  // Acordeão dos jogos abertos: null = só o próximo jogo fica expandido; 0 = todos fechados
  const [expandedGameId, setExpandedGameId] = useState<number | null>(null);
  const [editingGameIds, setEditingGameIds] = useState<Record<number, boolean>>({});
  const [syncStatus, setSyncStatus] = useState<WorldCupSyncStatus | null>(null);
  const [aiInsight, setAiInsight] = useState<string | null>(null);
  const [syncStatusError, setSyncStatusError] = useState("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("open");
  const [stageFilter, setStageFilter] = useState("all");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(() => Date.now());

  const refreshBoard = useCallback(async () => {
    try {
      const bolao = await api.worldCupBoard();
      setBoard({ ...bolao, games: sortGames(bolao.games) });
    } catch {
      // mantém o estado atual se a atualização falhar
    }
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const [me, eventList, ranking, bolao] = await Promise.all([
          api.me(),
          api.events(),
          api.leaderboard(),
          api.worldCupBoard(),
        ]);
        setProfile(me);
        setEvents(eventList.events);
        setLeaderboard(ranking);
        setBoard({ ...bolao, games: sortGames(bolao.games) });
      } catch {
        router.push("/");
        return;
      } finally {
        setLoading(false);
      }

      api
        .worldCupPlayers()
        .then((response) => setSquads(response.players))
        .catch(() => null);

      api
        .worldCupInsight()
        .then((res) => setAiInsight(res.available ? res.text ?? null : null))
        .catch(() => null);
    }

    load();
  }, [router]);

  useEffect(() => {
    if (!liveModalOpen) return;
    let active = true;
    const load = () =>
      api
        .worldCupSyncStatus()
        .then((status) => {
          if (!active) return;
          setSyncStatus(status);
          setSyncStatusError("");
        })
        .catch((nextError) => {
          if (active) setSyncStatusError(nextError instanceof Error ? nextError.message : "Não foi possível carregar o status");
        });
    load();
    const poll = window.setInterval(load, 15_000);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [liveModalOpen]);

  const hasLiveGame = useMemo(
    () => (board?.games ?? []).some((game) => game.status === "live"),
    [board?.games],
  );

  // Efeitos: tela inicial (#1 → scroll+ouro) | ver mais (todos → rodinha sem scroll)
  const [rankGlow, setRankGlow] = useState<{ delta: number; pulse: number; mode: "main" | "modal" } | null>(null);
  const [pointsFlash, setPointsFlash] = useState<number | null>(null);
  const rankGlowTimerRef = useRef<number | null>(null);
  const pointsFlashTimerRef = useRef<number | null>(null);
  const rankGlowPulseRef = useRef(0);
  const mainFxTimerRef = useRef<number | null>(null);
  const modalFxTimerRef = useRef<number | null>(null);
  const mainFxScheduledKeyRef = useRef<string | null>(null);
  const modalFxScheduledKeyRef = useRef<string | null>(null);
  const rankingModalOpenRef = useRef(rankingModalOpen);

  useEffect(() => {
    rankingModalOpenRef.current = rankingModalOpen;
  }, [rankingModalOpen]);

  const visiblePointsFlash = rankingModalOpen ? pointsFlash : null;

  const triggerRankGlow = useCallback((delta: number, mode: "main" | "modal") => {
    rankGlowPulseRef.current += 1;
    setRankGlow({ delta, pulse: rankGlowPulseRef.current, mode });
    if (rankGlowTimerRef.current) window.clearTimeout(rankGlowTimerRef.current);
    rankGlowTimerRef.current = window.setTimeout(() => {
      setRankGlow(null);
      rankGlowTimerRef.current = null;
    }, 6500);
  }, []);

  // —— Tela inicial: só 2º→1º — scroll rápido → giro dourado (sem popup verde) ——
  useEffect(() => {
    if (loading || !profile?.id || rankingModalOpen) return;
    const mine = board?.leaderboard.find((e) => e.user.id === profile.id);
    if (!mine) return;

    const movement = mine.movement ?? 0;
    if (mine.rank !== 1 || movement !== 1) return;

    const finishedGames = board?.games?.filter((g) => g.status === "finished").length ?? 0;
    const mainToken = `g${finishedGames}-mv1-r1`;
    const mainKey = bolaoFxShownKey("main", profile.id, mainToken);
    if (bolaoFxWasShown(mainKey) || mainFxScheduledKeyRef.current === mainKey) return;

    mainFxScheduledKeyRef.current = mainKey;
    if (mainFxTimerRef.current) window.clearTimeout(mainFxTimerRef.current);
    mainFxTimerRef.current = window.setTimeout(() => {
      if (rankingModalOpenRef.current || bolaoFxWasShown(mainKey)) return;
      scrollToRankCard(profile.id);
      mainFxTimerRef.current = window.setTimeout(() => {
        if (rankingModalOpenRef.current || bolaoFxWasShown(mainKey)) return;
        bolaoFxMarkShown(mainKey);
        triggerRankGlow(movement, "main");
      }, MAIN_SCROLL_TO_SPIN_MS);
    }, MAIN_LEADER_DELAY_MS);
  }, [loading, profile?.id, board?.leaderboard, board?.games, rankingModalOpen, triggerRankGlow]);

  // Console: __bolaoFxTest.clear() | __bolaoFxTest.leader() | __bolaoFxTest.scroll()
  useEffect(() => {
    if (!profile?.id) return;
    const uid = profile.id;
    const w = window as Window & {
      __bolaoFxTest?: {
        clear: () => void;
        leader: (movement?: number) => void;
        scroll: () => void;
      };
    };
    w.__bolaoFxTest = {
      clear() {
        Object.keys(localStorage).filter((k) => k.startsWith("bolao-fx-")).forEach((k) => localStorage.removeItem(k));
        console.log("[bolao] FX limpos. Recarregue com location.reload() para o fluxo real da API.");
      },
      leader(movement = 1) {
        Object.keys(localStorage)
          .filter((k) => k.startsWith(`bolao-fx-main-${uid}-`) || k.startsWith(`bolao-fx-pts-${uid}-`))
          .forEach((k) => localStorage.removeItem(k));
        mainFxScheduledKeyRef.current = null;
        window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
        window.setTimeout(() => {
          scrollToRankCard(uid);
          window.setTimeout(() => {
            triggerRankGlow(movement, "main");
            console.log("[bolao] Efeito 1º lugar simulado (scroll + dourado).");
          }, MAIN_SCROLL_TO_SPIN_MS);
        }, 200);
      },
      scroll() {
        scrollToRankCard(uid);
        console.log("[bolao] Scroll até seu card no ranking.");
      },
    };
    return () => {
      delete w.__bolaoFxTest;
    };
  }, [profile?.id, triggerRankGlow]);

  // —— Ver mais: giro no card → ao terminar sobe o verde (+N pts), 1× por usuário/rodada ——
  useEffect(() => {
    if (!rankingModalOpen) {
      modalFxScheduledKeyRef.current = null;
      return;
    }
    if (loading || !profile?.id) return;
    const mine = board?.leaderboard.find((e) => e.user.id === profile.id);
    if (!mine) return;

    const roundGain = mine.round_gain ?? 0;
    if (roundGain <= 0) return;

    const modalToken = `p${mine.points}-g${roundGain}`;
    const modalKey = bolaoFxShownKey("modal", profile.id, modalToken);
    const ptsKey = bolaoFxShownKey("pts", profile.id, modalToken);
    if (bolaoFxWasShown(modalKey) && bolaoFxWasShown(ptsKey)) return;
    if (modalFxScheduledKeyRef.current === modalToken) return;

    modalFxScheduledKeyRef.current = modalToken;
    if (modalFxTimerRef.current) window.clearTimeout(modalFxTimerRef.current);
    modalFxTimerRef.current = window.setTimeout(() => {
      if (!rankingModalOpenRef.current) return;
      if (!bolaoFxWasShown(modalKey)) {
        bolaoFxMarkShown(modalKey);
        triggerRankGlow(Math.max(1, roundGain), "modal");
      }
      if (bolaoFxWasShown(ptsKey)) return;
      modalFxTimerRef.current = window.setTimeout(() => {
        if (!rankingModalOpenRef.current || bolaoFxWasShown(ptsKey)) return;
        bolaoFxMarkShown(ptsKey);
        if (pointsFlashTimerRef.current) window.clearTimeout(pointsFlashTimerRef.current);
        setPointsFlash(roundGain);
        pointsFlashTimerRef.current = window.setTimeout(() => {
          setPointsFlash(null);
          pointsFlashTimerRef.current = null;
        }, 3000);
      }, MODAL_POINTS_DELAY_MS);
    }, 380);
  }, [rankingModalOpen, loading, profile?.id, board?.leaderboard, triggerRankGlow]);

  useEffect(() => {
    if (rankingModalOpen) return;
    modalFxScheduledKeyRef.current = null;
    if (modalFxTimerRef.current) {
      window.clearTimeout(modalFxTimerRef.current);
      modalFxTimerRef.current = null;
    }
    if (pointsFlashTimerRef.current) {
      window.clearTimeout(pointsFlashTimerRef.current);
      pointsFlashTimerRef.current = null;
    }
  }, [rankingModalOpen]);

  useEffect(() => () => {
    if (rankGlowTimerRef.current) window.clearTimeout(rankGlowTimerRef.current);
    if (pointsFlashTimerRef.current) window.clearTimeout(pointsFlashTimerRef.current);
    if (mainFxTimerRef.current) window.clearTimeout(mainFxTimerRef.current);
    if (modalFxTimerRef.current) window.clearTimeout(modalFxTimerRef.current);
  }, []);

  // Movimentação AO VIVO: aura leve nas linhas do ranking (sem popup — popup usa saldo visto acima)
  const [liveMovements, setLiveMovements] = useState<Record<number, number>>({});
  const prevRanksRef = useRef<Record<number, number> | null>(null);
  useEffect(() => {
    const lb = board?.leaderboard ?? [];
    if (lb.length === 0) return;
    const curr: Record<number, number> = {};
    lb.forEach((e) => { curr[e.user.id] = e.rank; });
    const prev = prevRanksRef.current;
    prevRanksRef.current = curr;
    if (!prev) return; // primeira carga: sem efeito
    const moves: Record<number, number> = {};
    lb.forEach((e) => {
      const p = prev[e.user.id];
      if (p != null && p !== e.rank) moves[e.user.id] = p - e.rank; // + = subiu
    });
    if (Object.keys(moves).length === 0) return;
    setLiveMovements(moves);
    const t = window.setTimeout(() => setLiveMovements({}), 6000);
    return () => window.clearTimeout(t);
  }, [board?.leaderboard]);

  // Quem cravou campeã vs quem não votou — voadores primeiro, ordenados por nome
  const championVoters = useMemo(() => {
    const rows = (board?.leaderboard ?? []).map((entry) => ({
      user: entry.user,
      team: entry.champion_team ?? null,
    }));
    return rows.sort((a, b) => {
      if (Boolean(a.team) !== Boolean(b.team)) return a.team ? -1 : 1;
      return a.user.name.localeCompare(b.user.name, "pt-BR");
    });
  }, [board?.leaderboard]);

  useEffect(() => {
    const clock = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    // Atualiza o placar bem mais rápido quando tem jogo rolando (sensação ao vivo)
    const poller = window.setInterval(() => {
      refreshBoard();
    }, hasLiveGame ? 10_000 : 60_000);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(poller);
    };
  }, [refreshBoard, hasLiveGame]);

  const games = useMemo(() => (board?.games ?? []).filter((game) => game.bettable !== false), [board?.games]);
  // Filtros/locks só mudam na virada de minuto (cutoff é de 1h). Derivando um tempo
  // arredondado ao minuto, as listas pesadas (sort/filter de todos os jogos) param de
  // recalcular a cada segundo — só o countdown ao vivo continua usando o relógio de 1s.
  const currentMinute = useMemo(() => Math.floor(currentTime / 60_000) * 60_000, [currentTime]);
  const myEntry = board?.leaderboard.find((entry) => entry.user.id === profile?.id);
  const champion = board?.champion;
  const highlights = board?.highlights;

  const teams = useMemo(() => {
    const names = new Set<string>();
    for (const game of games) {
      if (game.home_team) names.add(game.home_team);
      if (game.away_team) names.add(game.away_team);
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [games]);

  const stageOptions = useMemo(
    () =>
      Array.from(new Set(games.map((game) => game.stage)))
        .filter(Boolean)
        .sort(),
    [games],
  );

  const nextGame = useMemo(
    () => sortGames(games).find((game) => isUpcomingGame(game, currentMinute)) ?? null,
    [currentMinute, games],
  );

  const liveGames = useMemo(() => games.filter((game) => game.status === "live"), [games]);

  const filteredGames = useMemo(() => {
    return games.filter((game) => {
      if (stageFilter !== "all" && game.stage !== stageFilter) return false;
      if (quickFilter === "today") return isSameDay(game.kickoff_at, currentMinute);
      if (quickFilter === "open") return isUpcomingGame(game, currentMinute);
      if (quickFilter === "live") return game.status === "live";
      if (quickFilter === "finished") return game.status === "finished";
      return true;
    });
  }, [currentMinute, games, quickFilter, stageFilter]);

  const myBetGames = useMemo(
    () => games.filter((game) => game.viewer_prediction).sort((a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime()),
    [games],
  );

  const upcomingGames = useMemo(
    () => sortGames(filteredGames.filter((game) => isUpcomingGame(game, currentMinute))),
    [currentMinute, filteredGames],
  );

  const openBetGames = useMemo(
    () => upcomingGames.filter((game) => !game.viewer_prediction),
    [upcomingGames],
  );

  // Lista da grade respeita o filtro escolhido (abertos, ao vivo, encerrados...)
  const gridGames = useMemo(() => sortGames(filteredGames), [filteredGames]);

  const championTeams = useMemo(() => {
    const names = new Set(Object.keys(squads));
    for (const team of teams) names.add(team);
    return Array.from(names).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [squads, teams]);

  const filteredChampionTeams = useMemo(() => {
    const query = championQuery.trim().toLowerCase();
    if (!query) return championTeams;
    return championTeams.filter(
      (team) => team.toLowerCase().includes(query) || teamLabel(team).toLowerCase().includes(query),
    );
  }, [championQuery, championTeams]);

  const summary = useMemo(() => {
    const open = games.filter((game) => isUpcomingGame(game, currentMinute)).length;
    const predicted = games.filter((game) => game.viewer_prediction).length;
    return {
      open,
      predicted,
      points: myEntry?.points ?? 0,
      rank: myEntry?.rank ?? null,
    };
  }, [currentMinute, games, myEntry?.points, myEntry?.rank]);

  const countdown = nextGame ? countdownParts(nextGame.kickoff_at, currentTime) : null;

  const unpickedOpen = openBetGames.length;

  const recentResults = useMemo(
    () =>
      games
        .filter((game) => game.status === "finished" && game.home_score !== null && game.away_score !== null)
        .sort((a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime()),
    [games],
  );
  const [resultsExpanded, setResultsExpanded] = useState(false);
  const [championExpanded, setChampionExpanded] = useState(false);

  const scrollToGame = (gameId: number) => {
    setExpandedGameId(gameId);
    document.getElementById(`game-${gameId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const openGameForEditing = (game: WorldCupGame) => {
    setPredictionDrafts((current) => {
      const next = { ...current };
      delete next[game.id];
      return next;
    });
    setEditingGameIds((current) => ({ ...current, [game.id]: true }));
    scrollToGame(game.id);
  };

  const cancelEditingGame = (game: WorldCupGame) => {
    setEditingGameIds((current) => {
      const next = { ...current };
      delete next[game.id];
      return next;
    });
    setPredictionDrafts((current) => {
      const next = { ...current };
      delete next[game.id];
      return next;
    });
  };

  const sortedRanking = useMemo(() => {
    const entries = [...(board?.leaderboard ?? [])];
    if (rankingTab === "geral") return entries;
    return entries.sort((a, b) => rankingValue(b, rankingTab) - rankingValue(a, rankingTab));
  }, [board?.leaderboard, rankingTab]);

  // Movimentação vem pronta do servidor (subiu/caiu desde o último jogo pontuado)
  const rankDelta = useMemo(() => {
    const map: Record<number, number> = {};
    (board?.leaderboard ?? []).forEach((entry) => {
      if (entry.movement) map[entry.user.id] = entry.movement;
    });
    return map;
  }, [board?.leaderboard]);

  const gamePlayers = useCallback(
    (game: WorldCupGame) => {
      const homeTeam = squadTeamKey(game.home_team);
      const awayTeam = squadTeamKey(game.away_team);
      const home = squads[homeTeam] ?? squads[game.home_team] ?? [];
      const away = squads[awayTeam] ?? squads[game.away_team] ?? [];
      return [...home.map((p) => ({ ...p, team: game.home_team })), ...away.map((p) => ({ ...p, team: game.away_team }))];
    },
    [squads],
  );

  const predictionDraftFor = useCallback(
    (game: WorldCupGame): PredictionDraft =>
      predictionDrafts[game.id] ?? {
        home: String(game.viewer_prediction?.home_score ?? 0),
        away: String(game.viewer_prediction?.away_score ?? 0),
        scorer: game.viewer_prediction?.scorer_guess ?? "",
      },
    [predictionDrafts],
  );

  const updatePredictionDraft = (game: WorldCupGame, field: keyof PredictionDraft, value: string) => {
    const base = predictionDraftFor(game);
    setPredictionDrafts((current) => ({
      ...current,
      [game.id]: { ...base, ...current[game.id], [field]: value },
    }));
  };


  const handlePrediction = async (game: WorldCupGame) => {
    if (isGameLocked(game, currentTime)) return;
    const draft = predictionDraftFor(game);
    const isUpdate = Boolean(game.viewer_prediction);
    setSavingPrediction(game.id);
    setError("");
    setMessage("");
    try {
      const updated = await api.submitWorldCupPrediction(game.id, {
        home_score: scoreValue(draft.home),
        away_score: scoreValue(draft.away),
        scorer_guess: draft.scorer.trim() || null,
      });
      setBoard((current) => (current ? { ...current, games: replaceGame(current.games, updated) } : current));
      setEditingGameIds((current) => {
        const next = { ...current };
        delete next[game.id];
        return next;
      });
      setPredictionDrafts((current) => {
        const next = { ...current };
        delete next[game.id];
        return next;
      });
      setSavedFlash(game.id);
      window.setTimeout(() => setSavedFlash((id) => (id === game.id ? null : id)), 2400);
      setMessage(
        isUpdate
          ? "Palpite atualizado. Você pode alterar de novo até 1 hora antes do jogo."
          : "Palpite cravado. Você pode alterar até 1 hora antes do jogo.",
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível salvar o palpite");
    } finally {
      setSavingPrediction(null);
    }
  };

  const handleResult = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!resultModalGame) return;
    setSavingResult(true);
    setError("");
    setMessage("");
    try {
      const response = await api.setWorldCupGameResult(resultModalGame.id, {
        home_score: scoreValue(resultDraft.home),
        away_score: scoreValue(resultDraft.away),
        status: "finished",
        scorers: resultDraft.scorers.trim() || null,
      });
      setBoard((current) =>
        current
          ? {
              ...current,
              games: replaceGame(current.games, response.game),
              leaderboard: response.leaderboard,
            }
          : current,
      );
      setMessage("Resultado lançado e ranking atualizado.");
      setResultModalGame(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível lançar o resultado");
    } finally {
      setSavingResult(false);
    }
  };

  const handleChampionPick = async (team: string) => {
    if (!team.trim() || champion?.viewer_pick || champion?.locked) return;
    setSavingChampion(true);
    setError("");
    setMessage("");
    try {
      const updated = await api.submitWorldCupChampionPick(team.trim());
      setBoard((current) => (current ? { ...current, champion: updated } : current));
      setMessage("Palpite de campeão cravado. Boa sorte!");
      setChampionDraft("");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível salvar o palpite de campeão");
    } finally {
      setSavingChampion(false);
    }
  };




  if (loading) {
    return <div className="empty-state">Carregando bolão...</div>;
  }

  return (
    <AppShell hideRightRail user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      {visiblePointsFlash != null && (
        <div className="bolao-flash-stack bolao-flash-stack--modal" role="status" aria-live="polite">
          <div className="bolao-points-flash">
            <small className="bolao-flash-tag">Pontos</small>
            <span>
              🔥 +{visiblePointsFlash} {visiblePointsFlash === 1 ? "ponto" : "pontos"}!
            </span>
          </div>
        </div>
      )}
      <div className="wc-page">
      <section className="wc-hero2">
        <span className="wc-hero2-aurora" aria-hidden="true" />
        <span className="wc-hero2-pitch" aria-hidden="true" />

        <div className="wc-hero2-head">
          <div className="wc-hero2-title">
            <span className="wc-hero2-eyebrow">
              <Trophy size={13} />
              Bolão da Copa 2026
            </span>
            <h1>
              Crave. Torça. <em>Domine.</em>
            </h1>
            <p className="wc-hero2-sub">
              Placar exato + artilheiro valem <strong>{maxPoints(board?.rules)} pts</strong> por jogo. Fecha 1h antes da
              bola rolar.
            </p>
          </div>
          <div className="wc-hero2-actions">
            <button className="wc-hero2-btn" onClick={() => setMyBetsModalOpen(true)} type="button">
              <Ticket size={15} />
              <span>Minhas apostas</span>
              <b>{summary.predicted}</b>
            </button>
            <button className="wc-hero2-btn" onClick={() => setRankingModalOpen(true)} type="button">
              <Medal size={15} />
              <span>Ranking</span>
            </button>
            <button
              className={`wc-hero2-btn wc-admin-live-btn${hasLiveGame ? " pulsing" : ""}`}
              onClick={() => setLiveModalOpen(true)}
              type="button"
            >
              <Radio size={15} />
              <span>Ao vivo</span>
            </button>
          </div>
        </div>

        <div className="wc-hero2-prizes" aria-label="Premiação do bolão">
          <span className="wc-hero2-prize gold">
            <i>🥇</i>
            <span>
              <small>Campeão</small>
              <strong>R$ 1.000</strong>
            </span>
          </span>
          <span className="wc-hero2-prize silver">
            <i>🥈</i>
            <span>
              <small>2º lugar</small>
              <strong>R$ 500</strong>
            </span>
          </span>
          <span className="wc-hero2-prize bronze">
            <i>🥉</i>
            <span>
              <small>3º lugar</small>
              <strong>R$ 200</strong>
            </span>
          </span>
        </div>

        {liveGames.length > 0 ? (
          <div className={`wc-hero2-stage live${liveGames[0].halftime ? " halftime" : ""}`}>
            <span className="wc-hero2-stage-label">
              {liveGames[0].halftime ? (
                <>⏸ Intervalo</>
              ) : (
                <>
                  <span className="wc-live-dot" />
                  Rolando agora{liveGames.length > 1 ? ` · +${liveGames.length - 1} jogos` : ""}
                </>
              )}
            </span>
            <div className="wc-hero2-faceoff">
              <span className="wc-hero2-team">
                <span className="wc-hero2-flag"><TeamFlag team={liveGames[0].home_team} /></span>
                <strong>{teamLabel(liveGames[0].home_team)}</strong>
              </span>
              <span className="wc-hero2-score">
                {liveGames[0].home_score ?? 0}<small>x</small>{liveGames[0].away_score ?? 0}
              </span>
              <span className="wc-hero2-team">
                <span className="wc-hero2-flag"><TeamFlag team={liveGames[0].away_team} /></span>
                <strong>{teamLabel(liveGames[0].away_team)}</strong>
              </span>
            </div>
            {liveGames[0].scorers && (
              <span className="wc-hero2-live-scorers">
                <Goal size={13} /> {liveGames[0].scorers}
              </span>
            )}
          </div>
        ) : (
          nextGame &&
          countdown && (
            <div className="wc-hero2-stage">
              <span className="wc-hero2-stage-label">Próximo jogo · {formatEventDate(nextGame.kickoff_at)}</span>
              <div className="wc-hero2-faceoff">
                <span className="wc-hero2-team">
                  <span className="wc-hero2-flag"><TeamFlag team={nextGame.home_team} /></span>
                  <strong>{teamLabel(nextGame.home_team)}</strong>
                </span>
                <span className="wc-hero2-vs">vs</span>
                <span className="wc-hero2-team">
                  <span className="wc-hero2-flag"><TeamFlag team={nextGame.away_team} /></span>
                  <strong>{teamLabel(nextGame.away_team)}</strong>
                </span>
              </div>
              <div className="wc-hero2-clock" aria-label="Contagem regressiva para o próximo jogo">
                {countdown.days > 0 && (
                  <>
                    <span className="wc-hero2-cell">
                      <strong>{countdown.days}</strong>
                      <small>dias</small>
                    </span>
                    <span className="wc-hero2-colon">:</span>
                  </>
                )}
                <span className="wc-hero2-cell">
                  <strong>{pad(countdown.hours)}</strong>
                  <small>hrs</small>
                </span>
                <span className="wc-hero2-colon">:</span>
                <span className="wc-hero2-cell">
                  <strong>{pad(countdown.minutes)}</strong>
                  <small>min</small>
                </span>
                <span className="wc-hero2-colon">:</span>
                <span className="wc-hero2-cell">
                  <strong>{pad(countdown.seconds)}</strong>
                  <small>seg</small>
                </span>
              </div>
              {!nextGame.viewer_prediction ? (
                <button className="wc-hero2-cta" onClick={() => scrollToGame(nextGame.id)} type="button">
                  <Zap size={16} />
                  <span>Cravar meu palpite</span>
                </button>
              ) : (
                <button className="wc-hero2-cta wc-hero2-cta-edit" onClick={() => openGameForEditing(nextGame)} type="button">
                  <Pencil size={15} />
                  <span>Alterar meu palpite</span>
                </button>
              )}
            </div>
          )
        )}

        <div className="wc-hero2-statbar">
          <span className="wc-hero2-stat">
            <Sparkles size={14} />
            <strong>{summary.points}</strong> pts
          </span>
          <i />
          <span className={`wc-hero2-stat${rankGlow?.mode === "main" && rankGlow.delta > 0 && summary.rank === 1 ? " rank-glow-gold" : ""}`} id="bolao-my-rank-stat">
            <Medal size={14} />
            <strong>{summary.rank ? `${summary.rank}º` : "—"}</strong> posição
          </span>
          <i />
          <span className="wc-hero2-stat">
            <Zap size={14} />
            <strong>{summary.predicted}</strong> palpites
          </span>
          <i />
          <span className="wc-hero2-stat">
            <Flame size={14} />
            <strong>{summary.open}</strong> abertos
          </span>
        </div>
      </section>

      <section className="wc-ranking-inline glass-panel wc-ranking-mobile-only" id="bolao-ranking">
        <div className="wc-section-head wc-ranking-inline-head">
          <div>
            <span className="eyebrow">Classificação</span>
            <h2>Ranking do bolão</h2>
          </div>
        </div>
        <BolaoRankingPanel
          board={board}
          glowUserId={profile?.id}
          highlights={highlights}
          compact
          limit={8}
          onSelectEntry={setSelectedEntry}
          onShowAll={() => setRankingModalOpen(true)}
          onTabChange={setRankingTab}
          rankDelta={rankDelta}
          rankGlow={rankGlow}
          fxSurface="main"
          liveMoves={liveMovements}
          rankingTab={rankingTab}
          sortedRanking={sortedRanking}
        />
      </section>

      {unpickedOpen > 0 && (
        <section className="wc-urgency-bar glass-panel" role="status">
          <Flame size={18} />
          <div>
            <strong>
              {unpickedOpen} jogo{unpickedOpen > 1 ? "s" : ""} aberto{unpickedOpen > 1 ? "s" : ""} sem teu palpite
            </strong>
            <span>Palpites fecham 1 hora antes da bola rolar. Não fica de fora.</span>
          </div>
          {nextGame && !nextGame.viewer_prediction && (
            <button className="wc-urgency-action" onClick={() => scrollToGame(nextGame.id)} type="button">
              <Zap size={15} />
              <span>Palpitar agora</span>
            </button>
          )}
        </section>
      )}

      {(message || error) && (
        <section className={error ? "bolao-feedback error" : "bolao-feedback"}>
          <span>{error || message}</span>
        </section>
      )}

      <section className="wc-champion-arena glass-panel">
        <div className="wc-champion-head">
          <div>
            <span className="eyebrow">Palpite especial</span>
            <h2>Quem leva a taça?</h2>
            <p className="wc-champion-copy">
              Vale <strong>{champion?.points_award ?? 10} pts</strong>. Escolhe uma vez — depois não dá pra trocar.
              {!champion?.locked && champion?.lock_at && (
                <> Fecha {formatEventDate(champion.lock_at)} (fim da 1ª rodada da fase de grupos).</>
              )}
            </p>
          </div>
          <span className="wc-champion-trophy" aria-hidden="true">
            🏆
          </span>
        </div>

        {champion?.team ? (
          <div className="wc-champion-result">
            <span className="wc-champion-result-flag"><TeamFlag team={champion.team} /></span>
            <div>
              <strong>Campeã: {teamLabel(champion.team)}</strong>
              <span>A Copa acabou — confere os pontos no ranking.</span>
            </div>
          </div>
        ) : champion?.viewer_pick ? (
          <div className="wc-champion-result locked">
            <span className="wc-champion-result-flag"><TeamFlag team={champion.viewer_pick.team} /></span>
            <div>
              <strong>{teamLabel(champion.viewer_pick.team)}</strong>
              <span>Palpite cravado. Não dá pra mudar.</span>
            </div>
            <span className="wc-champion-seal">Cravado</span>
          </div>
        ) : champion?.locked ? (
          <p className="wc-champion-closed">Palpites de campeão fechados.</p>
        ) : (
          <>
            <input
              className="input-field wc-champion-search"
              onChange={(event) => setChampionQuery(event.target.value)}
              placeholder="Buscar seleção..."
              value={championQuery}
            />
            <div className="wc-champion-grid">
              {filteredChampionTeams.map((team) => (
                <button
                  className={championDraft === team ? "wc-champion-team active" : "wc-champion-team"}
                  disabled={savingChampion}
                  key={team}
                  onClick={() => setChampionDraft(team)}
                  type="button"
                >
                  <span className="wc-champion-team-flag"><TeamFlag team={team} /></span>
                  <span>{teamLabel(team)}</span>
                </button>
              ))}
            </div>
            <button
              className="wc-bet-button wc-champion-submit"
              disabled={savingChampion || !championDraft}
              onClick={() => handleChampionPick(championDraft)}
              type="button"
            >
              <Crown size={16} />
              <span>
                {savingChampion ? (
                  "Cravando..."
                ) : championDraft ? (
                  <>
                    Cravar <TeamFlag team={championDraft} /> {teamLabel(championDraft)}
                  </>
                ) : (
                  "Escolha uma seleção"
                )}
              </span>
            </button>
          </>
        )}

        {champion?.locked && championVoters.length > 0 && (
          <div className="wc-champ-voters">
            <div className="wc-champ-voters-head">
              <span className="eyebrow">Quem cravou a campeã</span>
              <span className="wc-champ-voters-count">
                {championVoters.filter((v) => v.team).length}/{championVoters.length} votaram
              </span>
            </div>
            <div className="wc-champ-voters-grid">
              {(championExpanded ? championVoters : championVoters.slice(0, 8)).map((voter) => (
                <div
                  className={voter.team ? "wc-champ-voter voted" : "wc-champ-voter missed"}
                  key={voter.user.id}
                  title={voter.team ? `${voter.user.name} → ${teamLabel(voter.team)}` : `${voter.user.name} não votou`}
                >
                  <span className="wc-champ-voter-avatar">
                    <Avatar user={voter.user} size="sm" />
                    <span className={voter.team ? "wc-champ-voter-flag" : "wc-champ-voter-x"}>
                      {voter.team ? <TeamFlag team={voter.team} /> : <X size={12} strokeWidth={3.2} />}
                    </span>
                  </span>
                  <strong>{voter.user.name.split(" ")[0]}</strong>
                  <small>{voter.team ? teamLabel(voter.team) : "não votou"}</small>
                </div>
              ))}
            </div>
            {championVoters.length > 8 && (
              <button className="wc-champ-voters-more" onClick={() => setChampionExpanded((v) => !v)} type="button">
                {championExpanded ? "Mostrar menos" : `Ver todos (${championVoters.length})`}
                <ChevronRight size={14} className={championExpanded ? "wc-fcard-chevron open" : "wc-fcard-chevron"} />
              </button>
            )}
          </div>
        )}
      </section>

      {recentResults.length > 0 && (
        <section className="wc-results-panel glass-panel">
          <div className="wc-section-head">
            <div>
              <span className="eyebrow">Já rolou</span>
              <h2>Resultados, gols e palpites</h2>
              <p className="wc-section-copy">
                Placar, quem fez o gol e o que a galera cravou — tudo junto. Atualiza sozinho e a pontuação entra na hora.
              </p>
            </div>
            <span className="wc-section-count">{recentResults.length} jogos</span>
          </div>
          <div className="wc-fcard-list">
            {(resultsExpanded ? recentResults : recentResults.slice(0, 3)).map((game) => (
              <FinishedGameCard game={game} key={game.id} viewerId={profile?.id} />
            ))}
          </div>
          {recentResults.length > 3 && (
            <button className="wc-ranking-show-more" onClick={() => setResultsExpanded((v) => !v)} type="button">
              <span className="wc-ranking-show-more-copy">
                <Medal size={16} />
                <span>{resultsExpanded ? "Mostrar menos" : `Ver mais ${recentResults.length - 3} jogos`}</span>
              </span>
              <ChevronRight size={15} className={resultsExpanded ? "wc-fcard-chevron open" : "wc-fcard-chevron"} />
            </button>
          )}
        </section>
      )}

      <section className="wc-filters">
        <div className="wc-filter-chips">
          {quickFilters.map((filter) => (
            <button
              className={quickFilter === filter.key ? "wc-chip active" : "wc-chip"}
              key={filter.key}
              onClick={() => setQuickFilter(filter.key)}
              type="button"
            >
              {filter.key === "live" && liveGames.length > 0 && <span className="wc-live-dot small" />}
              {filter.label}
            </button>
          ))}
        </div>
        <select className="input-field wc-stage-select" onChange={(event) => setStageFilter(event.target.value)} value={stageFilter}>
          <option value="all">Todas as fases</option>
          {stageOptions.map((stage) => (
            <option key={stage} value={stage}>
              {stageLabels[stage] ?? stage}
            </option>
          ))}
        </select>
      </section>

      <section className="wc-section-head">
        <div>
          <span className="eyebrow">
            {quickFilter === "finished"
              ? "Encerrados"
              : quickFilter === "live"
                ? "Ao vivo"
                : quickFilter === "today"
                  ? "Hoje"
                  : quickFilter === "all"
                    ? "Calendário completo"
                    : "Próximos jogos"}
          </span>
          <h2>
            {quickFilter === "finished"
              ? "Jogos encerrados e palpites"
              : quickFilter === "live"
                ? "Rolando agora"
                : quickFilter === "today"
                  ? "Jogos de hoje"
                  : quickFilter === "all"
                    ? "Todos os jogos da Copa"
                    : "Ordem do calendário da Copa"}
          </h2>
          {quickFilter === "open" && (
            <p className="wc-section-copy">A fila segue o horário oficial. Apostar não tira o jogo da lista — ele só sai quando começar ou finalizar.</p>
          )}
        </div>
        <span className="wc-section-count">
          {gridGames.length} jogo{gridGames.length === 1 ? "" : "s"}
          {quickFilter === "open" && unpickedOpen > 0 ? ` · ${unpickedOpen} sem palpite` : ""}
        </span>
      </section>

      {gridGames.length > 0 ? (
        <section className="wc-game-grid">
          {gridGames.map((game) => {
            // Jogo fechado/ao vivo/encerrado: card compacto unificado (resultado + gols + seu palpite + galera)
            if (isGameLocked(game, currentTime)) {
              return <FinishedGameCard game={game} key={game.id} viewerId={profile?.id} />;
            }

            const draft = predictionDraftFor(game);
            const players = gamePlayers(game);
            const lockMinutes = minutesUntilBetClose(game, currentTime);
            const justSaved = savedFlash === game.id;
            const hasBet = Boolean(game.viewer_prediction);
            const isEditing = Boolean(editingGameIds[game.id]);
            const isNextScheduled = nextGame?.id === game.id;
            const isExpanded = (expandedGameId ?? nextGame?.id ?? -1) === game.id;

            return (
              <article
                className={[
                  "wc-game-card glass-panel",
                  justSaved ? "just-saved" : "",
                  hasBet ? "has-bet" : "needs-bet",
                  isNextScheduled ? "is-next" : "",
                  isExpanded ? "expanded" : "collapsed",
                  game.is_knockout ? "wc-knockout-gold" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                id={`game-${game.id}`}
                key={game.id}
              >
                {game.is_knockout && (
                  <div className="wc-ko-banner" aria-hidden="true">
                    <Crown size={13} />
                    <span>{(stageLabels[game.stage] ?? "Mata-mata").toUpperCase()}</span>
                    <span className="wc-ko-banner-sub">✦ MATA-MATA ✦</span>
                  </div>
                )}
                <button
                  aria-expanded={isExpanded}
                  className="wc-game-summary"
                  onClick={() => setExpandedGameId(isExpanded ? 0 : game.id)}
                  type="button"
                >
                  <div className="wc-game-top">
                    <span className="wc-game-stage">
                      {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                    </span>
                    {isNextScheduled && <span className="wc-next-badge">Próximo jogo</span>}
                    <span className="wc-game-date">{formatEventDate(game.kickoff_at)}</span>
                    <div className="wc-game-top-actions">
                      <span className={hasBet ? "wc-game-status finished" : "wc-game-status scheduled"}>
                        {hasBet ? "Palpite feito" : "Aberto"}
                      </span>
                      {!hasBet && <span className="wc-points-teaser">Até +{maxPoints(board?.rules)} pts</span>}
                    </div>
                  </div>
                  {!isExpanded && (
                    <div className="wc-game-summary-row">
                      <span className="wc-game-summary-team">
                        <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}
                      </span>
                      <strong className="wc-game-summary-score">
                        {hasBet && game.viewer_prediction
                          ? `${game.viewer_prediction.home_score} x ${game.viewer_prediction.away_score}`
                          : "x"}
                      </strong>
                      <span className="wc-game-summary-team away">
                        {teamLabel(game.away_team)} <TeamFlag team={game.away_team} />
                      </span>
                      <ChevronRight className="wc-game-summary-chevron" size={17} />
                    </div>
                  )}
                  {!isExpanded && (
                    <div className={lockMinutes < 120 ? "wc-lock-timer urgent compactado" : "wc-lock-timer compactado"}>
                      <span>{urgencyLabel(lockMinutes)}</span>
                      {!hasBet ? (
                        <span className="wc-summary-cta">Toca pra palpitar</span>
                      ) : (
                        <span className="wc-summary-cta">Toca pra ver ou alterar</span>
                      )}
                    </div>
                  )}
                </button>

                {isExpanded && (
                  <>
                <div className={lockMinutes < 120 ? "wc-lock-timer urgent" : "wc-lock-timer"}>
                  <span>{urgencyLabel(lockMinutes)}</span>
                </div>

                {isNextScheduled && aiInsight && (
                  <div className="wc-ai-insight wc-ai-insight-card">
                    <span className="wc-ai-insight-tag"><Sparkles size={12} /> Resenha da IA</span>
                    <p>{aiInsight}</p>
                  </div>
                )}

                {hasBet && game.viewer_prediction && !isEditing ? (
                  <>
                    <div className="wc-matchup readonly">
                      <div className="wc-team">
                        <span className="wc-team-flag"><TeamFlag team={game.home_team} /></span>
                        <span className="wc-team-name">{teamLabel(game.home_team)}</span>
                      </div>
                      <div className="wc-score readonly-score">
                        <strong>
                          {game.viewer_prediction.home_score} x {game.viewer_prediction.away_score}
                        </strong>
                      </div>
                      <div className="wc-team away">
                        <span className="wc-team-flag"><TeamFlag team={game.away_team} /></span>
                        <span className="wc-team-name">{teamLabel(game.away_team)}</span>
                      </div>
                    </div>
                    {game.viewer_prediction.scorer_guess && (
                      <div className="wc-scorer-row readonly">
                        <Goal size={15} />
                        <span>{game.viewer_prediction.scorer_guess}</span>
                      </div>
                    )}
                    <div className="wc-bet-locked-note">
                      <CheckCircle2 size={16} />
                      <span>Palpite cravado. Você pode alterar até 1 hora antes do jogo.</span>
                    </div>
                    <button className="wc-bet-button secondary" onClick={() => openGameForEditing(game)} type="button">
                      <Pencil size={16} />
                      <span>Alterar palpite</span>
                    </button>
                  </>
                ) : (
                  <>
                    <div className="wc-matchup">
                      <div className="wc-team">
                        <span className="wc-team-flag"><TeamFlag team={game.home_team} /></span>
                        <span className="wc-team-name">{teamLabel(game.home_team)}</span>
                      </div>
                      <div className="wc-score">
                        <div className="wc-score-inputs">
                          <input
                            aria-label={`Gols de ${teamLabel(game.home_team)}`}
                            inputMode="numeric"
                            min={0}
                            onChange={(event) => updatePredictionDraft(game, "home", event.target.value)}
                            type="number"
                            value={draft.home}
                          />
                          <small>x</small>
                          <input
                            aria-label={`Gols de ${teamLabel(game.away_team)}`}
                            inputMode="numeric"
                            min={0}
                            onChange={(event) => updatePredictionDraft(game, "away", event.target.value)}
                            type="number"
                            value={draft.away}
                          />
                        </div>
                      </div>
                      <div className="wc-team away">
                        <span className="wc-team-flag"><TeamFlag team={game.away_team} /></span>
                        <span className="wc-team-name">{teamLabel(game.away_team)}</span>
                      </div>
                    </div>

                    <div className="wc-scorer-row">
                      <Goal size={15} />
                      <ScorerPicker
                        game={game}
                        onChange={(scorer) => updatePredictionDraft(game, "scorer", scorer)}
                        players={players}
                        value={draft.scorer}
                      />
                    </div>
                    <div className="wc-bet-edit-actions">
                      <button
                        className={justSaved ? "wc-bet-button saved" : "wc-bet-button"}
                        disabled={savingPrediction === game.id}
                        onClick={() => handlePrediction(game)}
                        type="button"
                      >
                        {justSaved ? (
                          <>
                            <Trophy size={16} />
                            <span>{hasBet ? "Palpite atualizado!" : "Palpite cravado!"}</span>
                          </>
                        ) : (
                          <>
                            {hasBet ? <Save size={16} /> : <Zap size={16} />}
                            <span>
                              {savingPrediction === game.id
                                ? hasBet
                                  ? "Salvando..."
                                  : "Cravando..."
                                : hasBet
                                  ? "Salvar alteração"
                                  : "Cravar palpite"}
                            </span>
                          </>
                        )}
                      </button>
                      {hasBet && (
                        <button className="wc-bet-edit-cancel" onClick={() => cancelEditingGame(game)} type="button">
                          Cancelar
                        </button>
                      )}
                    </div>
                  </>
                )}

                <div className="wc-game-foot">
                  <span>{game.venue || "Local a confirmar"}</span>
                  {(game.bettors ?? []).length > 0 ? (
                    <span
                      className="wc-bettor-stack"
                      title={`Já palpitaram: ${(game.bettors ?? []).map((bettor) => bettor.name).join(", ")}`}
                    >
                      <span className="wc-bettor-avatars">
                        {(game.bettors ?? []).slice(0, 5).map((bettor) => (
                          <Avatar key={bettor.id} user={bettor} size="sm" />
                        ))}
                      </span>
                      {game.predictions_count > 5 && <small>+{game.predictions_count - 5}</small>}
                      <small className="wc-bettor-label">já palpitaram</small>
                    </span>
                  ) : (
                    <span>
                      <Users size={12} /> Ninguém palpitou ainda
                    </span>
                  )}
                </div>
                  </>
                )}
              </article>
            );
          })}
        </section>
      ) : (
        <section className="empty-state bolao-empty">
          <Trophy size={24} />
          <strong>Nenhum jogo nesse filtro</strong>
          <span>
            {quickFilter === "live"
              ? "Nenhum jogo rolando agora. Confere os próximos em Abertos."
              : quickFilter === "today"
                ? "Nenhum jogo hoje. Confere os próximos em Abertos."
                : summary.predicted > 0
                  ? "Seus palpites fechados estão em Minhas apostas."
                  : "Tenta outro filtro ou aguarda a próxima rodada."}
          </span>
          {summary.predicted > 0 && (
            <button className="wc-urgency-action" onClick={() => setMyBetsModalOpen(true)} type="button">
              <Ticket size={15} />
              <span>Ver minhas apostas</span>
            </button>
          )}
        </section>
      )}

      {myBetsModalOpen && (
        <div className="event-modal-backdrop" onClick={() => setMyBetsModalOpen(false)}>
          <div className="event-modal glass-panel wc-modal wc-bets-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Seus palpites</span>
                <h2>Minhas apostas</h2>
              </div>
              <button className="modal-close" onClick={() => setMyBetsModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            {myBetGames.length > 0 ? (
              <div className="wc-bets-list">
                {myBetGames.map((game) => {
                  const prediction = game.viewer_prediction!;
                  const scored = prediction.status === "scored";
                  const showScore = (game.status === "finished" || game.status === "live") && game.home_score !== null;
                  const canEdit = isUpcomingGame(game, currentTime);

                  return (
                    <article className={["wc-bet-slip", scored && prediction.points > 0 ? "won" : ""].filter(Boolean).join(" ")} key={game.id}>
                      <div className="wc-bet-slip-top">
                        <span className="wc-game-stage">
                          {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                        </span>
                        <span className={`wc-game-status ${game.status}${game.halftime ? " halftime" : ""}`}>
                          {liveGameStatusLabel(game)}
                        </span>
                      </div>
                      <div className="wc-bet-slip-match">
                        <span>
                          <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}
                        </span>
                        <strong className={game.status === "live" ? "wc-live-score" : ""}>
                          {game.status === "live" && <span className="wc-live-dot small" />}
                          {showScore ? `${game.home_score} x ${game.away_score}` : `${prediction.home_score} x ${prediction.away_score}`}
                        </strong>
                        <span>
                          {teamLabel(game.away_team)} <TeamFlag team={game.away_team} />
                        </span>
                      </div>
                      <div className="wc-bet-slip-meta">
                        <span>{formatEventDate(game.kickoff_at)}</span>
                        <span>{game.venue || "Local a confirmar"}</span>
                      </div>
                      <div className="wc-bet-slip-pick">
                        <span>
                          Seu palpite: <strong>{prediction.home_score}x{prediction.away_score}</strong>
                          {prediction.scorer_guess ? (
                            <>
                              {" · "}
                              <strong className={prediction.scorer_hit ? "hit" : ""}>⚽ {prediction.scorer_guess}</strong>
                            </>
                          ) : null}
                        </span>
                        {scored ? (
                          <b className={prediction.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>
                            {prediction.points > 0 ? `+${prediction.points} pts` : "0 pts"}
                          </b>
                        ) : (
                          <b className="wc-points-badge pending">Aguardando</b>
                        )}
                      </div>
                      {game.status === "finished" && game.scorers && (
                        <div className="wc-game-scorers">
                          <Goal size={13} />
                          <span>{game.scorers}</span>
                        </div>
                      )}
                      {canEdit && (
                        <button
                          className="wc-bet-button secondary compact"
                          onClick={() => {
                            setMyBetsModalOpen(false);
                            openGameForEditing(game);
                          }}
                          type="button"
                        >
                          <Pencil size={15} />
                          <span>Alterar palpite</span>
                        </button>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="rail-empty-copy">Você ainda não cravou nenhum palpite.</p>
            )}
          </div>
        </div>
      )}

      {selectedEntry && <BolaoPersonModal board={board} entry={selectedEntry} onClose={() => setSelectedEntry(null)} />}

      {rankingModalOpen && (
        <div className="event-modal-backdrop" onClick={() => setRankingModalOpen(false)}>
          <div className="event-modal glass-panel wc-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Bolão da Copa</span>
                <h2>Ranking</h2>
              </div>
              <button className="modal-close" onClick={() => setRankingModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            <BolaoRankingPanel
              board={board}
              glowUserId={profile?.id}
              highlights={highlights}
              onSelectEntry={setSelectedEntry}
              onTabChange={setRankingTab}
              rankDelta={rankDelta}
              rankGlow={rankGlow}
              fxSurface="modal"
              liveMoves={liveMovements}
              rankingTab={rankingTab}
              sortedRanking={sortedRanking}
            />
          </div>
        </div>
      )}

      {resultModalGame && (
        <div className="event-modal-backdrop" onClick={() => setResultModalGame(null)}>
          <div className="event-modal glass-panel wc-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Resultado oficial</span>
                <h2>
                  <TeamFlag team={resultModalGame.home_team} /> {teamLabel(resultModalGame.home_team)} x {teamLabel(resultModalGame.away_team)}{" "}
                  <TeamFlag team={resultModalGame.away_team} />
                </h2>
              </div>
              <button className="modal-close" onClick={() => setResultModalGame(null)} type="button">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleResult}>
              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="result-home">{teamLabel(resultModalGame.home_team)}</label>
                  <input
                    className="input-field"
                    id="result-home"
                    inputMode="numeric"
                    min={0}
                    onChange={(event) => setResultDraft((current) => ({ ...current, home: event.target.value }))}
                    type="number"
                    value={resultDraft.home}
                  />
                </div>
                <div className="modal-field">
                  <label htmlFor="result-away">{teamLabel(resultModalGame.away_team)}</label>
                  <input
                    className="input-field"
                    id="result-away"
                    inputMode="numeric"
                    min={0}
                    onChange={(event) => setResultDraft((current) => ({ ...current, away: event.target.value }))}
                    type="number"
                    value={resultDraft.away}
                  />
                </div>
              </div>
              <div className="modal-field">
                <label htmlFor="result-scorers">Quem marcou (separa por vírgula)</label>
                <input
                  className="input-field"
                  id="result-scorers"
                  onChange={(event) => setResultDraft((current) => ({ ...current, scorers: event.target.value }))}
                  placeholder="Ex: Vini Jr, Mbappé"
                  value={resultDraft.scorers}
                />
              </div>
              <button className="btn-primary" disabled={savingResult} type="submit">
                <Save size={16} />
                <span>{savingResult ? "Lançando..." : "Finalizar jogo"}</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {liveModalOpen && (
        <div className="event-modal-backdrop wc-admin-backdrop" onClick={() => setLiveModalOpen(false)}>
          <div className="event-modal glass-panel wc-modal wc-admin-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Transparência</span>
                <h2>Painel ao vivo</h2>
              </div>
              <button className="modal-close" onClick={() => setLiveModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            {syncStatus ? (
              <AdminLivePanel currentTime={currentTime} error={syncStatusError} syncStatus={syncStatus} />
            ) : (
              !syncStatusError && <p className="bolao-sync-info">Carregando status das fontes...</p>
            )}

          </div>
        </div>
      )}

      {nextGame && !nextGame.viewer_prediction && !isGameLocked(nextGame, currentTime) && (
        <div className="wc-sticky-bet">
          <div className="wc-sticky-bet-copy">
            <span className="wc-sticky-flags">
              <TeamFlag team={nextGame.home_team} /> x <TeamFlag team={nextGame.away_team} />
            </span>
            <strong>{urgencyLabel(minutesUntilBetClose(nextGame, currentTime))}</strong>
          </div>
          <button className="wc-sticky-bet-button" onClick={() => scrollToGame(nextGame.id)} type="button">
            <Zap size={16} />
            <span>Cravar palpite</span>
          </button>
        </div>
      )}
      </div>
    </AppShell>
  );
}
