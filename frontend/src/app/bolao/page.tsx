"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CalendarPlus,
  CheckCircle2,
  ChevronRight,
  Crown,
  DownloadCloud,
  Flame,
  Goal,
  Lock,
  Medal,
  RefreshCcw,
  Save,
  Settings2,
  Sparkles,
  Target,
  Ticket,
  Trophy,
  Users,
  X,
  Zap,
} from "lucide-react";
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

type GameDraft = {
  home_team: string;
  away_team: string;
  kickoff_at: string;
  group_label: string;
  stage: string;
  venue: string;
  match_number: string;
};

type RankingTab = "geral" | "exatos" | "resultados" | "artilheiro";
type QuickFilter = "today" | "open" | "live" | "finished" | "all";

const emptyGameDraft = (): GameDraft => ({
  home_team: "",
  away_team: "",
  kickoff_at: "",
  group_label: "",
  stage: "group-stage",
  venue: "",
  match_number: "",
});

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

const quickFilters: Array<{ key: QuickFilter; label: string }> = [
  { key: "today", label: "Hoje" },
  { key: "open", label: "Abertos" },
  { key: "live", label: "Ao vivo" },
  { key: "finished", label: "Encerrados" },
  { key: "all", label: "Todos" },
];

const rankingTabs: Array<{ key: RankingTab; label: string }> = [
  { key: "geral", label: "Geral" },
  { key: "exatos", label: "Exatos" },
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
};

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
}: BolaoRankingPanelProps) {
  const entries = limit ? sortedRanking.slice(0, limit) : sortedRanking;
  const podium = entries.slice(0, 3);
  const listEntries = entries.slice(podium.length);

  return (
    <>
      {!compact && (
        <div className="bolao-rules-guide">
          <span className="eyebrow">Como funciona a pontuação</span>
          <ul>
            <li>
              <Target size={16} />
              <div>
                <strong>Placar exato — {board?.rules.exact_score ?? 3} pts</strong>
                <span>Cravou o placar certinho. Palpitou 2x1 e o jogo terminou 2x1.</span>
              </div>
            </li>
            <li>
              <Goal size={16} />
              <div>
                <strong>Artilheiro — {board?.rules.scorer_bonus ?? 1} pt</strong>
                <span>O jogador que você escolheu marcou gol no jogo. Vale sozinho ou somado ao placar exato.</span>
              </div>
            </li>
            <li>
              <Crown size={16} />
              <div>
                <strong>Campeã da Copa — {board?.rules.champion ?? 10} pts</strong>
                <span>Palpite único de quem levanta a taça. Aberto até 1 hora antes da estreia do Brasil.</span>
              </div>
            </li>
          </ul>
          <p className="bolao-rules-note">
            Num jogo dá pra somar até <strong>{maxPoints(board?.rules)} pts</strong> (placar exato + artilheiro). Acertar
            só o vencedor não pontua. Palpites fecham 1 hora antes da bola rolar e a pontuação entra automaticamente
            quando o jogo termina.
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
        <div className={compact ? "bolao-podium compact" : "bolao-podium"}>
          {[podium[1], podium[0], podium[2]].map((entry, column) =>
            entry ? (
              <button
                className={["bolao-podium-step", column === 1 ? "first" : column === 0 ? "second" : "third"].join(" ")}
                key={entry.user.id}
                onClick={() => onSelectEntry?.(entry)}
                type="button"
              >
                <span className="bolao-podium-medal">{column === 1 ? "🥇" : column === 0 ? "🥈" : "🥉"}</span>
                <Avatar user={entry.user} size={column === 1 ? "md" : "sm"} />
                <span className="bolao-podium-name">{entry.user.name.split(" ")[0]}</span>
                <strong>
                  {rankingValue(entry, rankingTab)} {rankingUnit(rankingTab)}
                </strong>
                <small>
                  {entry.exact_scores} exatos · {entry.scorer_hits} ⚽
                </small>
                {entry.champion_team && (
                  <span className="bolao-pick-chip" title={`Palpite de campeã: ${teamLabel(entry.champion_team)}`}>
                    <TeamFlag team={entry.champion_team} />
                  </span>
                )}
              </button>
            ) : (
              <span className="bolao-podium-step empty" key={`empty-${column}`} />
            ),
          )}
        </div>
      )}

      {sortedRanking.length > 0 && (
        <p className="bolao-ranking-hint">Toca em alguém pra ver os palpites jogo a jogo.</p>
      )}

      <div className="bolao-ranking-list">
        {listEntries.map((entry, index) => (
          <button className="bolao-rank-row clickable" key={entry.user.id} onClick={() => onSelectEntry?.(entry)} type="button">
            <strong>{rankingTab === "geral" ? entry.rank : index + podium.length + 1}</strong>
            <Avatar user={entry.user} size="sm" />
            <span className="bolao-rank-main">
              <span className="bolao-rank-name">
                {entry.user.name}
                {entry.champion_team && (
                  <span className="bolao-pick-chip" title={`Palpite de campeã: ${teamLabel(entry.champion_team)}`}>
                    <TeamFlag team={entry.champion_team} />
                  </span>
                )}
              </span>
              <small>
                {entry.exact_scores} exatos · {entry.scorer_hits} artilheiros · {entry.predictions} palpites
              </small>
            </span>
            <b>
              {rankingValue(entry, rankingTab)} {rankingUnit(rankingTab)}
            </b>
            <ChevronRight className="bolao-rank-chevron" size={15} />
          </button>
        ))}
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
    <div className="event-modal-backdrop" onClick={onClose}>
      <div className="event-modal glass-panel wc-modal wc-person-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div className="wc-person-head">
            <Avatar user={entry.user} />
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

type ScorerPlayer = { id: number; name: string; team: string; position?: string | null; club?: string | null };

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
  const groups = [
    { team: game.home_team, players: players.filter((player) => player.team === game.home_team && matches(player)) },
    { team: game.away_team, players: players.filter((player) => player.team === game.away_team && matches(player)) },
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

      {open && (
        <div className="event-modal-backdrop" onClick={() => setOpen(false)}>
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
                      <span className="wc-scorer-option-name">{player.name}</span>
                      <small>
                        {[player.position, player.club].filter(Boolean).join(" · ")}
                      </small>
                    </button>
                  ))}
                </div>
              ))}
              {groups.length === 0 && <p className="rail-empty-copy">Nenhum jogador encontrado com esse nome.</p>}
            </div>
          </div>
        </div>
      )}
    </>
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
  const [adminModalOpen, setAdminModalOpen] = useState(false);
  const [rankingModalOpen, setRankingModalOpen] = useState(false);
  const [myBetsModalOpen, setMyBetsModalOpen] = useState(false);
  const [championQuery, setChampionQuery] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncingSquads, setSyncingSquads] = useState(false);
  const [creatingGame, setCreatingGame] = useState(false);
  const [championDraft, setChampionDraft] = useState("");
  const [savingChampion, setSavingChampion] = useState(false);
  const [championAnnounceDraft, setChampionAnnounceDraft] = useState("");
  const [announcingChampion, setAnnouncingChampion] = useState(false);
  const [rankingTab, setRankingTab] = useState<RankingTab>("geral");
  const [selectedEntry, setSelectedEntry] = useState<WorldCupLeaderboardEntry | null>(null);
  // Acordeão dos jogos abertos: null = só o próximo jogo fica expandido; 0 = todos fechados
  const [expandedGameId, setExpandedGameId] = useState<number | null>(null);
  const [syncStatus, setSyncStatus] = useState<WorldCupSyncStatus | null>(null);
  const [syncStatusError, setSyncStatusError] = useState("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("open");
  const [stageFilter, setStageFilter] = useState("all");
  const [gameDraft, setGameDraft] = useState<GameDraft>(emptyGameDraft);
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
    }

    load();
  }, [router]);

  const isAdminProfile = Boolean(profile?.is_admin);

  useEffect(() => {
    if (!adminModalOpen || !isAdminProfile) return;
    let active = true;
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
    return () => {
      active = false;
    };
  }, [adminModalOpen, isAdminProfile]);

  useEffect(() => {
    const clock = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    const poller = window.setInterval(() => {
      refreshBoard();
    }, 60_000);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(poller);
    };
  }, [refreshBoard]);

  const games = useMemo(() => (board?.games ?? []).filter((game) => game.bettable !== false), [board?.games]);
  const isAdmin = Boolean(profile?.is_admin);
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
    () => sortGames(games).find((game) => isUpcomingGame(game, currentTime)) ?? null,
    [currentTime, games],
  );

  const liveGames = useMemo(() => games.filter((game) => game.status === "live"), [games]);

  const filteredGames = useMemo(() => {
    return games.filter((game) => {
      if (stageFilter !== "all" && game.stage !== stageFilter) return false;
      if (quickFilter === "today") return isSameDay(game.kickoff_at, currentTime);
      if (quickFilter === "open") return isUpcomingGame(game, currentTime);
      if (quickFilter === "live") return game.status === "live";
      if (quickFilter === "finished") return game.status === "finished";
      return true;
    });
  }, [currentTime, games, quickFilter, stageFilter]);

  const myBetGames = useMemo(
    () => games.filter((game) => game.viewer_prediction).sort((a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime()),
    [games],
  );

  const upcomingGames = useMemo(
    () => sortGames(filteredGames.filter((game) => isUpcomingGame(game, currentTime))),
    [currentTime, filteredGames],
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
    const open = games.filter((game) => isUpcomingGame(game, currentTime)).length;
    const predicted = games.filter((game) => game.viewer_prediction).length;
    return {
      open,
      predicted,
      points: myEntry?.points ?? 0,
      rank: myEntry?.rank ?? null,
    };
  }, [currentTime, games, myEntry?.points, myEntry?.rank]);

  const countdown = nextGame ? countdownParts(nextGame.kickoff_at, currentTime) : null;

  const unpickedOpen = openBetGames.length;

  const recentResults = useMemo(
    () =>
      games
        .filter((game) => game.status === "finished" && game.home_score !== null && game.away_score !== null)
        .sort((a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime())
        .slice(0, 6),
    [games],
  );

  const scrollToGame = (gameId: number) => {
    setExpandedGameId(gameId);
    document.getElementById(`game-${gameId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const sortedRanking = useMemo(() => {
    const entries = [...(board?.leaderboard ?? [])];
    if (rankingTab === "geral") return entries;
    return entries.sort((a, b) => rankingValue(b, rankingTab) - rankingValue(a, rankingTab));
  }, [board?.leaderboard, rankingTab]);

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

  const updateGameDraft = <K extends keyof GameDraft>(field: K, value: GameDraft[K]) => {
    setGameDraft((current) => ({ ...current, [field]: value }));
    setError("");
  };

  const handlePrediction = async (game: WorldCupGame) => {
    if (game.viewer_prediction) return;
    const draft = predictionDraftFor(game);
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
      setSavedFlash(game.id);
      window.setTimeout(() => setSavedFlash((id) => (id === game.id ? null : id)), 2400);
      setMessage("Palpite cravado. O próximo jogo na fila só muda quando este encerrar ou começar.");
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

  const handleAnnounceChampion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!championAnnounceDraft.trim()) return;
    setAnnouncingChampion(true);
    setError("");
    setMessage("");
    try {
      const response = await api.announceWorldCupChampion(championAnnounceDraft.trim());
      setBoard((current) =>
        current ? { ...current, champion: response.champion, leaderboard: response.leaderboard } : current,
      );
      setMessage("Campeão definido e pontos distribuídos!");
      setChampionAnnounceDraft("");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível definir o campeão");
    } finally {
      setAnnouncingChampion(false);
    }
  };

  const handleCreateGame = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreatingGame(true);
    setError("");
    setMessage("");
    try {
      const created = await api.createWorldCupGame({
        home_team: gameDraft.home_team.trim(),
        away_team: gameDraft.away_team.trim(),
        kickoff_at: new Date(gameDraft.kickoff_at).toISOString(),
        group_label: gameDraft.group_label.trim() || null,
        stage: gameDraft.stage,
        venue: gameDraft.venue.trim() || null,
        match_number: gameDraft.match_number ? Number(gameDraft.match_number) : null,
        source: "manual",
      });
      setBoard((current) =>
        current
          ? {
              ...current,
              games: sortGames([...current.games, created]),
            }
          : current,
      );
      setGameDraft(emptyGameDraft());
      setMessage("Jogo cadastrado no bolão.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível cadastrar o jogo");
    } finally {
      setCreatingGame(false);
    }
  };

  const handleSyncOpenfootball = async () => {
    setSyncing(true);
    setError("");
    setMessage("");
    try {
      const response = await api.syncWorldCupOpenfootball();
      setBoard((current) =>
        current
          ? {
              ...current,
              games: sortGames(response.games),
              leaderboard: response.leaderboard ?? current.leaderboard,
            }
          : current,
      );
      setMessage(
        `${response.imported} jogos importados e ${response.updated} atualizados. Resultados e artilheiros vêm do openfootball a cada sync.`,
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível importar os jogos");
    } finally {
      setSyncing(false);
    }
  };

  const handleSyncSquads = async () => {
    setSyncingSquads(true);
    setError("");
    setMessage("");
    try {
      const response = await api.syncWorldCupSquads();
      setSquads(response.players);
      setMessage(`Elencos atualizados: ${response.imported} jogadores novos, ${response.updated} atualizados.`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível importar os elencos");
    } finally {
      setSyncingSquads(false);
    }
  };

  if (loading) {
    return <div className="empty-state">Carregando bolão...</div>;
  }

  return (
    <AppShell hideRightRail user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <div className="wc-page">
      <section className="wc-hero glass-panel">
        <div className="wc-hero-top">
          <div className="wc-hero-title">
            <span className="eyebrow">Bolão da Copa 2026</span>
            <h1>Crave. Torça. Domine.</h1>
            <p className="wc-hero-sub">
              Placar exato vale até <strong>+{maxPoints(board?.rules)} pts</strong>. Palpites fecham 1 hora antes de cada jogo.
            </p>
          </div>
          <div className="wc-hero-actions">
            <button className="wc-ranking-button" onClick={() => setMyBetsModalOpen(true)} type="button">
              <Ticket size={16} />
              <span>Minhas apostas ({summary.predicted})</span>
            </button>
            <button className="wc-ranking-button" onClick={() => setRankingModalOpen(true)} type="button">
              <Medal size={16} />
              <span>Ranking</span>
            </button>
            {isAdmin && (
              <button className="wc-admin-button" onClick={() => setAdminModalOpen(true)} type="button">
                <Settings2 size={16} />
                <span>Gerenciar</span>
              </button>
            )}
          </div>
        </div>

        <div className="wc-hero-stats">
          <div className="wc-stat">
            <Sparkles size={16} />
            <strong>{summary.points}</strong>
            <span>pontos</span>
          </div>
          <div className="wc-stat">
            <Medal size={16} />
            <strong>{summary.rank ? `${summary.rank}º` : "—"}</strong>
            <span>posição</span>
          </div>
          <div className="wc-stat">
            <Zap size={16} />
            <strong>{summary.predicted}</strong>
            <span>palpites</span>
          </div>
          <div className="wc-stat">
            <Flame size={16} />
            <strong>{summary.open}</strong>
            <span>abertos</span>
          </div>
        </div>

        {liveGames.length > 0 ? (
          <div className="wc-live-banner">
            <span className="wc-live-dot" />
            <strong>
              {teamLabel(liveGames[0].home_team)} {liveGames[0].home_score ?? 0} x {liveGames[0].away_score ?? 0}{" "}
              {teamLabel(liveGames[0].away_team)}
            </strong>
            <span>rolando agora{liveGames.length > 1 ? ` +${liveGames.length - 1} jogos` : ""}</span>
          </div>
        ) : (
          nextGame &&
          countdown && (
            <div className="wc-countdown">
              <div className="wc-countdown-match">
                <span className="wc-countdown-flag"><TeamFlag team={nextGame.home_team} /></span>
                <strong>
                  {teamLabel(nextGame.home_team)} x {teamLabel(nextGame.away_team)}
                </strong>
                <span className="wc-countdown-flag"><TeamFlag team={nextGame.away_team} /></span>
              </div>
              <div className="wc-countdown-clock" aria-label="Contagem regressiva para o próximo jogo">
                {countdown.days > 0 && (
                  <span className="wc-clock-cell">
                    <strong>{countdown.days}</strong>
                    <small>dias</small>
                  </span>
                )}
                <span className="wc-clock-cell">
                  <strong>{pad(countdown.hours)}</strong>
                  <small>hrs</small>
                </span>
                <span className="wc-clock-sep">:</span>
                <span className="wc-clock-cell">
                  <strong>{pad(countdown.minutes)}</strong>
                  <small>min</small>
                </span>
                <span className="wc-clock-sep">:</span>
                <span className="wc-clock-cell">
                  <strong>{pad(countdown.seconds)}</strong>
                  <small>seg</small>
                </span>
              </div>
              {!nextGame.viewer_prediction ? (
                <button className="wc-countdown-cta" onClick={() => scrollToGame(nextGame.id)} type="button">
                  ⚡ Você ainda não palpitou — crava agora
                </button>
              ) : (
                <span className="wc-countdown-done">Palpite feito — aguardando o início do jogo</span>
              )}
            </div>
          )
        )}
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
          highlights={highlights}
          compact
          limit={8}
          onSelectEntry={setSelectedEntry}
          onShowAll={() => setRankingModalOpen(true)}
          onTabChange={setRankingTab}
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
                <> Fecha {formatEventDate(champion.lock_at)} (1h antes da estreia do Brasil).</>
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

        {champion?.locked && !champion.team && champion.picks.length > 0 && (
          <div className="wc-champion-picks">
            {champion.picks.map((pick) => (
              <span className="wc-champion-chip" key={pick.id} title={pick.user.name}>
                <TeamFlag team={pick.team} /> {pick.user.name.split(" ")[0]}
              </span>
            ))}
          </div>
        )}
      </section>

      {recentResults.length > 0 && quickFilter !== "finished" && (
        <section className="wc-results-panel glass-panel">
          <div className="wc-section-head">
            <div>
              <span className="eyebrow">Resultados oficiais</span>
              <h2>Placares e artilheiros</h2>
              <p className="wc-section-copy">
                Atualizado automaticamente pela fonte openfootball. Quando o jogo finaliza, a pontuação do bolão recalcula
                sozinha.
              </p>
            </div>
          </div>
          <div className="wc-results-list">
            {recentResults.map((game) => (
              <article className="wc-result-card" key={game.id}>
                <div className="wc-result-top">
                  <span className="wc-game-stage">
                    {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                  </span>
                  <span className="wc-game-date">{formatEventDate(game.kickoff_at)}</span>
                </div>
                <div className="wc-result-scoreline">
                  <span><TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}</span>
                  <strong>
                    {game.home_score} x {game.away_score}
                  </strong>
                  <span>
                    {teamLabel(game.away_team)} <TeamFlag team={game.away_team} />
                  </span>
                </div>
                {game.scorers ? (
                  <div className="wc-result-scorers">
                    <Goal size={14} />
                    <span>{game.scorers}</span>
                  </div>
                ) : (
                  <div className="wc-result-scorers muted">Artilheiros ainda não publicados na fonte.</div>
                )}
                {(game.predictions ?? []).length > 0 && (
                  <div className="wc-result-preds">
                    <span className="wc-result-preds-label">Palpites da galera</span>
                    {(game.predictions ?? []).map((prediction) => (
                      <div
                        className={prediction.points > 0 ? "wc-result-pred scored" : "wc-result-pred"}
                        key={prediction.id}
                      >
                        <Avatar user={prediction.user} size="sm" />
                        <span>{prediction.user.name.split(" ")[0]}</span>
                        <small>
                          {prediction.home_score}x{prediction.away_score}
                          {prediction.scorer_guess ? ` · ⚽ ${prediction.scorer_guess}${prediction.scorer_hit ? " ✓" : ""}` : ""}
                        </small>
                        <b className={prediction.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>
                          {prediction.points > 0 ? `+${prediction.points}` : "0"}
                        </b>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
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
            // Jogo fechado/ao vivo/encerrado: card de resultado com palpites da galera
            if (isGameLocked(game, currentTime)) {
              const viewerPick = game.viewer_prediction;
              return (
                <article className="wc-game-card glass-panel closed-card" id={`game-${game.id}`} key={game.id}>
                  <div className="wc-game-top">
                    <span className="wc-game-stage">
                      {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                    </span>
                    <span className="wc-game-date">{formatEventDate(game.kickoff_at)}</span>
                    <div className="wc-game-top-actions">
                      <span className={`wc-game-status ${game.status}`}>
                        {game.status === "live" && <span className="wc-live-dot small" />}
                        {game.status === "scheduled" ? "Fechado" : statusLabels[game.status]}
                      </span>
                    </div>
                  </div>
                  <div className="wc-result-scoreline">
                    <span>
                      <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}
                    </span>
                    <strong>
                      {game.home_score ?? "–"} x {game.away_score ?? "–"}
                    </strong>
                    <span>
                      {teamLabel(game.away_team)} <TeamFlag team={game.away_team} />
                    </span>
                  </div>
                  {game.scorers && (
                    <div className="wc-result-scorers">
                      <Goal size={14} />
                      <span>{game.scorers}</span>
                    </div>
                  )}
                  {viewerPick && (
                    <div className="wc-bet-slip-pick">
                      <span>
                        Seu palpite: <strong>{viewerPick.home_score}x{viewerPick.away_score}</strong>
                        {viewerPick.scorer_guess ? (
                          <>
                            {" · "}
                            <strong className={viewerPick.scorer_hit ? "hit" : ""}>⚽ {viewerPick.scorer_guess}</strong>
                          </>
                        ) : null}
                      </span>
                      {viewerPick.status === "scored" ? (
                        <b className={viewerPick.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>
                          {viewerPick.points > 0 ? `+${viewerPick.points} pts` : "0 pts"}
                        </b>
                      ) : (
                        <b className="wc-points-badge pending">Aguardando</b>
                      )}
                    </div>
                  )}
                  {(game.predictions ?? []).length > 0 && (
                    <div className="wc-result-preds">
                      <span className="wc-result-preds-label">Palpites da galera</span>
                      {(game.predictions ?? []).map((prediction) => (
                        <div
                          className={prediction.points > 0 ? "wc-result-pred scored" : "wc-result-pred"}
                          key={prediction.id}
                        >
                          <Avatar user={prediction.user} size="sm" />
                          <span>{prediction.user.name.split(" ")[0]}</span>
                          <small>
                            {prediction.home_score}x{prediction.away_score}
                            {prediction.scorer_guess ? ` · ⚽ ${prediction.scorer_guess}${prediction.scorer_hit ? " ✓" : ""}` : ""}
                          </small>
                          <b className={prediction.points > 0 ? "wc-points-badge won" : "wc-points-badge"}>
                            {prediction.points > 0 ? `+${prediction.points}` : "0"}
                          </b>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              );
            }

            const draft = predictionDraftFor(game);
            const players = gamePlayers(game);
            const lockMinutes = minutesUntilBetClose(game, currentTime);
            const justSaved = savedFlash === game.id;
            const hasBet = Boolean(game.viewer_prediction);
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
                ]
                  .filter(Boolean)
                  .join(" ")}
                id={`game-${game.id}`}
                key={game.id}
              >
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
                      {!hasBet && <span className="wc-summary-cta">Toca pra palpitar</span>}
                    </div>
                  )}
                </button>

                {isExpanded && (
                  <>
                <div className={lockMinutes < 120 ? "wc-lock-timer urgent" : "wc-lock-timer"}>
                  <span>{urgencyLabel(lockMinutes)}</span>
                </div>

                {hasBet && game.viewer_prediction ? (
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
                      <span>Palpite cravado. Este jogo só sai da fila quando começar ou finalizar.</span>
                    </div>
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
                    <button
                      className={justSaved ? "wc-bet-button saved" : "wc-bet-button"}
                      disabled={savingPrediction === game.id}
                      onClick={() => handlePrediction(game)}
                      type="button"
                    >
                      {justSaved ? (
                        <>
                          <Trophy size={16} />
                          <span>Palpite cravado!</span>
                        </>
                      ) : (
                        <>
                          <Zap size={16} />
                          <span>{savingPrediction === game.id ? "Cravando..." : "Cravar palpite"}</span>
                        </>
                      )}
                    </button>
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

                  return (
                    <article className={["wc-bet-slip", scored && prediction.points > 0 ? "won" : ""].filter(Boolean).join(" ")} key={game.id}>
                      <div className="wc-bet-slip-top">
                        <span className="wc-game-stage">
                          {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                        </span>
                        <span className={`wc-game-status ${game.status}`}>{statusLabels[game.status]}</span>
                      </div>
                      <div className="wc-bet-slip-match">
                        <span>
                          <TeamFlag team={game.home_team} /> {teamLabel(game.home_team)}
                        </span>
                        <strong>
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
              highlights={highlights}
              onSelectEntry={setSelectedEntry}
              onTabChange={setRankingTab}
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

      {adminModalOpen && (
        <div className="event-modal-backdrop" onClick={() => setAdminModalOpen(false)}>
          <div className="event-modal glass-panel wc-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <span className="eyebrow">Admin</span>
                <h2>Gerenciar bolão</h2>
              </div>
              <button className="modal-close" onClick={() => setAdminModalOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>

            {syncStatusError && <p className="bolao-feedback error">{syncStatusError}</p>}
            {syncStatus ? (
              <div className="wc-sync-status">
                <div className={syncStatus.games_sync?.ok === false ? "wc-sync-card error" : "wc-sync-card ok"}>
                  <span className="wc-sync-card-head">
                    <RefreshCcw size={14} />
                    <strong>Jogos & resultados — openfootball</strong>
                    <b className={syncStatus.games_sync?.ok === false ? "wc-sync-pill error" : "wc-sync-pill ok"}>
                      {syncStatus.games_sync ? (syncStatus.games_sync.ok ? "Rodou certinho" : "Falhou") : "Nunca rodou"}
                    </b>
                  </span>
                  <small>
                    Última atualização: {syncStatus.games_sync?.at ? formatEventDate(syncStatus.games_sync.at) : "—"} ·
                    automático a cada {Math.round(syncStatus.sync_interval_seconds / 60)} min
                  </small>
                  <small>
                    {syncStatus.totals.games} jogos na tabela · {syncStatus.totals.finished_games} encerrados ·{" "}
                    {syncStatus.games_sync?.updated ?? 0} atualizados no último sync
                  </small>
                  {syncStatus.games_sync?.error && (
                    <small className="wc-sync-warn">
                      <AlertTriangle size={12} /> {syncStatus.games_sync.error}
                    </small>
                  )}
                  {(syncStatus.games_sync?.missing_scorers?.length ?? 0) > 0 && (
                    <small className="wc-sync-warn">
                      <AlertTriangle size={12} /> Encerrados sem artilheiro:{" "}
                      {(syncStatus.games_sync?.missing_scorers ?? []).join(", ")}
                    </small>
                  )}
                </div>

                <div
                  className={
                    !syncStatus.sources.football_data_configured
                      ? "wc-sync-card muted"
                      : syncStatus.games_sync?.secondary?.ok
                        ? "wc-sync-card ok"
                        : "wc-sync-card error"
                  }
                >
                  <span className="wc-sync-card-head">
                    <CheckCircle2 size={14} />
                    <strong>Conferência — football-data.org</strong>
                    <b
                      className={
                        !syncStatus.sources.football_data_configured
                          ? "wc-sync-pill muted"
                          : syncStatus.games_sync?.secondary?.ok
                            ? "wc-sync-pill ok"
                            : "wc-sync-pill error"
                      }
                    >
                      {!syncStatus.sources.football_data_configured
                        ? "Não configurada"
                        : syncStatus.games_sync?.secondary?.ok
                          ? "Conferindo"
                          : "Falhou"}
                    </b>
                  </span>
                  {syncStatus.sources.football_data_configured ? (
                    <>
                      <small>
                        {syncStatus.games_sync?.secondary?.matched ?? 0} jogos casados ·{" "}
                        {syncStatus.games_sync?.secondary?.filled ?? 0} resultados preenchidos por ela
                      </small>
                      {syncStatus.games_sync?.secondary?.error && (
                        <small className="wc-sync-warn">
                          <AlertTriangle size={12} /> {syncStatus.games_sync.secondary.error}
                        </small>
                      )}
                      {(syncStatus.games_sync?.secondary?.conflicts?.length ?? 0) > 0 ? (
                        <small className="wc-sync-warn">
                          <AlertTriangle size={12} /> Placares divergentes:{" "}
                          {(syncStatus.games_sync?.secondary?.conflicts ?? [])
                            .map((conflict) => `${conflict.game} (of ${conflict.openfootball} x fd ${conflict.football_data})`)
                            .join(" · ")}
                        </small>
                      ) : (
                        <small>Nenhuma divergência entre as duas fontes.</small>
                      )}
                    </>
                  ) : (
                    <small>
                      Defina FOOTBALL_DATA_API_KEY no .env (chave grátis em football-data.org) pra conferir os placares
                      em duas fontes.
                    </small>
                  )}
                </div>

                <div
                  className={
                    !syncStatus.games_sync?.live_source?.configured
                      ? "wc-sync-card muted"
                      : syncStatus.games_sync.live_source.error
                        ? "wc-sync-card error"
                        : "wc-sync-card ok"
                  }
                >
                  <span className="wc-sync-card-head">
                    <Zap size={14} />
                    <strong>Gols ao vivo — API-Football</strong>
                    <b
                      className={
                        !syncStatus.games_sync?.live_source?.configured
                          ? "wc-sync-pill muted"
                          : syncStatus.games_sync.live_source.error
                            ? "wc-sync-pill error"
                            : "wc-sync-pill ok"
                      }
                    >
                      {!syncStatus.games_sync?.live_source?.configured
                        ? "Não configurada"
                        : syncStatus.games_sync.live_source.error
                          ? "Erro"
                          : "Ativa"}
                    </b>
                  </span>
                  {!syncStatus.games_sync?.live_source?.configured ? (
                    <small>Defina API_FOOTBALL_KEY no .env pra capturar placar parcial e artilheiros em tempo real.</small>
                  ) : (
                    <>
                      <small>
                        {syncStatus.games_sync.live_source.skipped
                          ? syncStatus.games_sync.live_source.skipped
                          : `${syncStatus.games_sync.live_source.live_games} jogo(s) ao vivo · artilheiros atualizados em ${syncStatus.games_sync.live_source.scorers_updated}`}
                        {" · "}
                        {syncStatus.games_sync.live_source.calls_today} chamadas hoje (limite 90)
                      </small>
                      {syncStatus.games_sync.live_source.error && (
                        <small className="wc-sync-warn">
                          <AlertTriangle size={12} /> {syncStatus.games_sync.live_source.error}
                        </small>
                      )}
                    </>
                  )}
                </div>

                <div className={syncStatus.squad_sync?.ok === false ? "wc-sync-card error" : "wc-sync-card ok"}>
                  <span className="wc-sync-card-head">
                    <Users size={14} />
                    <strong>Elencos — Wikipedia</strong>
                    <b className={syncStatus.squad_sync?.ok === false ? "wc-sync-pill error" : "wc-sync-pill ok"}>
                      {syncStatus.totals.players > 0 ? "Jogadores puxados" : "Sem jogadores"}
                    </b>
                  </span>
                  <small>
                    {syncStatus.totals.players} jogadores de {syncStatus.totals.teams_with_squads} seleções · última:{" "}
                    {syncStatus.last_squad_sync ? formatEventDate(syncStatus.last_squad_sync) : "—"}
                  </small>
                  {syncStatus.squad_sync?.error && (
                    <small className="wc-sync-warn">
                      <AlertTriangle size={12} /> {syncStatus.squad_sync.error}
                    </small>
                  )}
                </div>
              </div>
            ) : (
              !syncStatusError && <p className="bolao-sync-info">Carregando status das fontes...</p>
            )}

            <div className="wc-admin-sync-row">
              <button className="btn-secondary" disabled={syncing} onClick={handleSyncOpenfootball} type="button">
                <DownloadCloud size={16} />
                <span>{syncing ? "Importando..." : "Sincronizar jogos"}</span>
              </button>
              <button className="btn-secondary" disabled={syncingSquads} onClick={handleSyncSquads} type="button">
                <Users size={16} />
                <span>{syncingSquads ? "Importando..." : "Sincronizar elencos"}</span>
              </button>
            </div>

            <form className="wc-champion-form" onSubmit={handleAnnounceChampion}>
              <input
                className="input-field"
                list="bolao-teams"
                onChange={(event) => setChampionAnnounceDraft(event.target.value)}
                placeholder="Definir campeã da Copa"
                value={championAnnounceDraft}
              />
              <button className="btn-secondary" disabled={announcingChampion || !championAnnounceDraft.trim()} type="submit">
                <Crown size={15} />
                <span>{announcingChampion ? "..." : "Definir"}</span>
              </button>
            </form>

            <form className="bolao-admin-form" onSubmit={handleCreateGame}>
              <span className="eyebrow">
                <CalendarPlus size={13} /> Cadastrar jogo manual
              </span>
              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="game-home">Seleção mandante</label>
                  <input
                    className="input-field"
                    id="game-home"
                    onChange={(event) => updateGameDraft("home_team", event.target.value)}
                    required
                    value={gameDraft.home_team}
                  />
                </div>
                <div className="modal-field">
                  <label htmlFor="game-away">Seleção visitante</label>
                  <input
                    className="input-field"
                    id="game-away"
                    onChange={(event) => updateGameDraft("away_team", event.target.value)}
                    required
                    value={gameDraft.away_team}
                  />
                </div>
              </div>
              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="game-kickoff">Data e hora</label>
                  <input
                    className="input-field"
                    id="game-kickoff"
                    onChange={(event) => updateGameDraft("kickoff_at", event.target.value)}
                    required
                    type="datetime-local"
                    value={gameDraft.kickoff_at}
                  />
                </div>
                <div className="modal-field">
                  <label htmlFor="game-group">Grupo</label>
                  <input
                    className="input-field"
                    id="game-group"
                    onChange={(event) => updateGameDraft("group_label", event.target.value)}
                    placeholder="A"
                    value={gameDraft.group_label}
                  />
                </div>
              </div>
              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="game-stage">Fase</label>
                  <select className="input-field" id="game-stage" onChange={(event) => updateGameDraft("stage", event.target.value)} value={gameDraft.stage}>
                    {Object.entries(stageLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="modal-field">
                  <label htmlFor="game-number">Número do jogo</label>
                  <input
                    className="input-field"
                    id="game-number"
                    min={1}
                    onChange={(event) => updateGameDraft("match_number", event.target.value)}
                    type="number"
                    value={gameDraft.match_number}
                  />
                </div>
              </div>
              <div className="modal-field">
                <label htmlFor="game-venue">Estádio ou cidade</label>
                <input
                  className="input-field"
                  id="game-venue"
                  onChange={(event) => updateGameDraft("venue", event.target.value)}
                  value={gameDraft.venue}
                />
              </div>
              <button className="btn-primary" disabled={creatingGame}>
                <Save size={16} />
                <span>{creatingGame ? "Cadastrando..." : "Cadastrar jogo"}</span>
              </button>
            </form>
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
