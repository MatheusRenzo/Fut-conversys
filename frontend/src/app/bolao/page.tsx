"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarPlus,
  CheckCircle2,
  Clock3,
  Crown,
  DownloadCloud,
  Goal,
  ListFilter,
  Medal,
  RefreshCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Target,
  Trophy,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { api } from "@/lib/api";
import { formatEventDate } from "@/lib/format";
import type {
  Event as AppEvent,
  Leaderboard,
  UserProfile,
  WorldCupBoard,
  WorldCupGame,
  WorldCupLeaderboardEntry,
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
  finished: "Finalizado",
  postponed: "Adiado",
};

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

function isGameLocked(game: WorldCupGame, now: number) {
  return game.status !== "scheduled" || new Date(game.kickoff_at).getTime() <= now;
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

export default function BolaoPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [board, setBoard] = useState<WorldCupBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [predictionDrafts, setPredictionDrafts] = useState<Record<number, PredictionDraft>>({});
  const [resultDrafts, setResultDrafts] = useState<Record<number, ResultDraft>>({});
  const [savingPrediction, setSavingPrediction] = useState<number | null>(null);
  const [savingResult, setSavingResult] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [creatingGame, setCreatingGame] = useState(false);
  const [championDraft, setChampionDraft] = useState("");
  const [savingChampion, setSavingChampion] = useState(false);
  const [championAnnounceDraft, setChampionAnnounceDraft] = useState("");
  const [announcingChampion, setAnnouncingChampion] = useState(false);
  const [rankingTab, setRankingTab] = useState<RankingTab>("geral");
  const [statusFilter, setStatusFilter] = useState<"all" | WorldCupGame["status"]>("all");
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
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [router]);

  useEffect(() => {
    const clock = window.setInterval(() => setCurrentTime(Date.now()), 60_000);
    const poller = window.setInterval(() => {
      refreshBoard();
    }, 60_000);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(poller);
    };
  }, [refreshBoard]);

  const games = useMemo(() => board?.games ?? [], [board?.games]);
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

  const filteredGames = useMemo(() => {
    return games.filter((game) => {
      if (statusFilter !== "all" && game.status !== statusFilter) return false;
      if (stageFilter !== "all" && game.stage !== stageFilter) return false;
      return true;
    });
  }, [games, stageFilter, statusFilter]);

  const summary = useMemo(() => {
    const open = games.filter((game) => !isGameLocked(game, currentTime)).length;
    const predicted = games.filter((game) => game.viewer_prediction).length;
    return {
      open,
      predicted,
      points: myEntry?.points ?? 0,
    };
  }, [currentTime, games, myEntry?.points]);

  const sortedRanking = useMemo(() => {
    const entries = [...(board?.leaderboard ?? [])];
    if (rankingTab === "geral") return entries;
    return entries.sort((a, b) => rankingValue(b, rankingTab) - rankingValue(a, rankingTab));
  }, [board?.leaderboard, rankingTab]);

  const predictionDraftFor = (game: WorldCupGame): PredictionDraft =>
    predictionDrafts[game.id] ?? {
      home: String(game.viewer_prediction?.home_score ?? 0),
      away: String(game.viewer_prediction?.away_score ?? 0),
      scorer: game.viewer_prediction?.scorer_guess ?? "",
    };

  const resultDraftFor = (game: WorldCupGame): ResultDraft =>
    resultDrafts[game.id] ?? {
      home: String(game.home_score ?? 0),
      away: String(game.away_score ?? 0),
      scorers: game.scorers ?? "",
    };

  const updatePredictionDraft = (game: WorldCupGame, field: keyof PredictionDraft, value: string) => {
    setPredictionDrafts((current) => ({
      ...current,
      [game.id]: { ...predictionDraftFor(game), ...current[game.id], [field]: value },
    }));
  };

  const updateResultDraft = (game: WorldCupGame, field: keyof ResultDraft, value: string) => {
    setResultDrafts((current) => ({
      ...current,
      [game.id]: { ...resultDraftFor(game), ...current[game.id], [field]: value },
    }));
  };

  const updateGameDraft = <K extends keyof GameDraft>(field: K, value: GameDraft[K]) => {
    setGameDraft((current) => ({ ...current, [field]: value }));
    setError("");
  };

  const handlePrediction = async (game: WorldCupGame) => {
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
      setMessage("Palpite salvo. Agora é torcer para esse placar bater.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível salvar o palpite");
    } finally {
      setSavingPrediction(null);
    }
  };

  const handleResult = async (game: WorldCupGame) => {
    const draft = resultDraftFor(game);
    setSavingResult(game.id);
    setError("");
    setMessage("");
    try {
      const response = await api.setWorldCupGameResult(game.id, {
        home_score: scoreValue(draft.home),
        away_score: scoreValue(draft.away),
        status: "finished",
        scorers: draft.scorers.trim() || null,
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
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível lançar o resultado");
    } finally {
      setSavingResult(null);
    }
  };

  const handleChampionPick = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!championDraft.trim()) return;
    setSavingChampion(true);
    setError("");
    setMessage("");
    try {
      const updated = await api.submitWorldCupChampionPick(championDraft.trim());
      setBoard((current) => (current ? { ...current, champion: updated } : current));
      setMessage("Palpite de campeão registrado. Boa sorte!");
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
      setMessage(`${response.imported} jogos importados e ${response.updated} atualizados. Resultados sincronizam sozinhos a cada 10 minutos.`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Não foi possível importar os jogos");
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return <div className="empty-state">Carregando bolão...</div>;
  }

  return (
    <AppShell user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <section className="bolao-hero glass-panel">
        <div className="bolao-hero-copy">
          <span className="eyebrow">Bolão da Copa</span>
          <h1>Palpites, placares e ranking da firma</h1>
          <p>
            Acerte o placar, chute quem marca gol e escolha o campeão da Copa. Os jogos e resultados sincronizam
            automaticamente — é só palpitar antes da bola rolar.
          </p>
        </div>
        <div className="bolao-scoreboard">
          <div>
            <Sparkles size={18} />
            <strong>{summary.points}</strong>
            <span>meus pontos</span>
          </div>
          <div>
            <CheckCircle2 size={18} />
            <strong>{summary.predicted}</strong>
            <span>palpites feitos</span>
          </div>
          <div>
            <Clock3 size={18} />
            <strong>{summary.open}</strong>
            <span>jogos abertos</span>
          </div>
        </div>
      </section>

      {(message || error) && (
        <section className={error ? "bolao-feedback error" : "bolao-feedback"}>
          <span>{error || message}</span>
        </section>
      )}

      <section className="bolao-champion glass-panel">
        <div className="bolao-champion-head">
          <div>
            <span className="eyebrow">Campeão da Copa</span>
            <h2>
              <Crown size={20} />
              {champion?.team
                ? `Campeã: ${champion.team}`
                : champion?.locked
                  ? "Palpites de campeão fechados"
                  : "Quem leva a taça?"}
            </h2>
          </div>
          <span className="bolao-champion-award">vale {champion?.points_award ?? 10} pts</span>
        </div>

        {champion?.viewer_pick && (
          <p className="bolao-champion-mine">
            Seu palpite: <strong>{champion.viewer_pick.team}</strong>
            {champion.viewer_pick.status === "scored" && champion.viewer_pick.points > 0 && (
              <b> · +{champion.viewer_pick.points} pts</b>
            )}
          </p>
        )}

        {!champion?.locked && (
          <form className="bolao-champion-form" onSubmit={handleChampionPick}>
            <input
              className="input-field"
              list="bolao-teams"
              onChange={(event) => setChampionDraft(event.target.value)}
              placeholder={champion?.viewer_pick ? "Trocar palpite de campeão" : "Escolha a seleção campeã"}
              value={championDraft}
            />
            <datalist id="bolao-teams">
              {teams.map((team) => (
                <option key={team} value={team} />
              ))}
            </datalist>
            <button className="btn-primary" disabled={savingChampion || !championDraft.trim()} type="submit">
              <Trophy size={16} />
              <span>{savingChampion ? "Salvando..." : "Cravar campeão"}</span>
            </button>
          </form>
        )}

        {champion?.locked && champion.picks.length > 0 && (
          <div className="bolao-champion-picks">
            {champion.picks.map((pick) => (
              <div className="bolao-champion-pick" key={pick.id}>
                <Avatar user={pick.user} size="sm" />
                <span>{pick.user.name}</span>
                <strong>{pick.team}</strong>
                {pick.status === "scored" && pick.points > 0 && <b>+{pick.points}</b>}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="bolao-layout">
        <div className="bolao-main">
          <section className="bolao-filter-panel glass-panel">
            <div>
              <span className="eyebrow">Jogos</span>
              <h2>Agenda de palpites</h2>
            </div>
            <div className="bolao-filter-actions">
              <label>
                <ListFilter size={16} />
                <select className="input-field" onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)} value={statusFilter}>
                  <option value="all">Todos os status</option>
                  <option value="scheduled">Abertos</option>
                  <option value="live">Ao vivo</option>
                  <option value="finished">Finalizados</option>
                  <option value="postponed">Adiados</option>
                </select>
              </label>
              <label>
                <Trophy size={16} />
                <select className="input-field" onChange={(event) => setStageFilter(event.target.value)} value={stageFilter}>
                  <option value="all">Todas as fases</option>
                  {stageOptions.map((stage) => (
                    <option key={stage} value={stage}>
                      {stageLabels[stage] ?? stage}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          {filteredGames.length > 0 ? (
            <section className="bolao-game-grid">
              {filteredGames.map((game) => {
                const locked = isGameLocked(game, currentTime);
                const predictionDraft = predictionDraftFor(game);
                const resultDraft = resultDraftFor(game);

                return (
                  <article className={locked ? "bolao-game-card glass-panel locked" : "bolao-game-card glass-panel"} key={game.id}>
                    <div className="bolao-game-head">
                      <div>
                        <span className="eyebrow">
                          {game.group_label ? `Grupo ${game.group_label}` : stageLabels[game.stage] ?? game.stage}
                        </span>
                        <strong>{formatEventDate(game.kickoff_at)}</strong>
                      </div>
                      <span className={`bolao-status ${game.status}`}>{statusLabels[game.status]}</span>
                    </div>

                    <div className="bolao-matchup">
                      <div>
                        <span>{game.home_team}</span>
                        {(game.status === "finished" || game.status === "live") && game.home_score !== null && (
                          <strong>{game.home_score}</strong>
                        )}
                      </div>
                      <small>x</small>
                      <div>
                        {(game.status === "finished" || game.status === "live") && game.away_score !== null && (
                          <strong>{game.away_score}</strong>
                        )}
                        <span>{game.away_team}</span>
                      </div>
                    </div>

                    <div className="bolao-game-meta">
                      <span>{game.venue || "Local a confirmar"}</span>
                      <span>{game.predictions_count} palpites</span>
                    </div>

                    {game.status === "finished" && game.scorers && (
                      <div className="bolao-scorers">
                        <Goal size={14} />
                        <span>{game.scorers}</span>
                      </div>
                    )}

                    <div className="bolao-prediction-box">
                      <div>
                        <span>Seu palpite</span>
                        {game.viewer_prediction && (
                          <strong>
                            {game.viewer_prediction.home_score} x {game.viewer_prediction.away_score}
                            {game.viewer_prediction.scorer_guess ? ` · ⚽ ${game.viewer_prediction.scorer_guess}` : ""}
                            {game.viewer_prediction.status === "scored" ? ` · ${game.viewer_prediction.points} pts` : ""}
                          </strong>
                        )}
                      </div>
                      <div className="score-input-row">
                        <input
                          aria-label={`Gols de ${game.home_team}`}
                          disabled={locked}
                          min={0}
                          onChange={(event) => updatePredictionDraft(game, "home", event.target.value)}
                          type="number"
                          value={predictionDraft.home}
                        />
                        <span>x</span>
                        <input
                          aria-label={`Gols de ${game.away_team}`}
                          disabled={locked}
                          min={0}
                          onChange={(event) => updatePredictionDraft(game, "away", event.target.value)}
                          type="number"
                          value={predictionDraft.away}
                        />
                        <button disabled={locked || savingPrediction === game.id} onClick={() => handlePrediction(game)} type="button">
                          <Save size={15} />
                          <span>{savingPrediction === game.id ? "Salvando" : "Salvar"}</span>
                        </button>
                      </div>
                    </div>

                    {!locked && (
                      <div className="bolao-scorer-guess">
                        <Target size={14} />
                        <input
                          aria-label="Quem marca gol?"
                          className="input-field"
                          maxLength={80}
                          onChange={(event) => updatePredictionDraft(game, "scorer", event.target.value)}
                          placeholder="Quem marca gol? (bônus +1 pt)"
                          value={predictionDraft.scorer}
                        />
                      </div>
                    )}

                    {isAdmin && (
                      <div className="bolao-admin-result-wrap">
                        <div className="bolao-admin-result">
                          <span>Resultado admin</span>
                          <div className="score-input-row">
                            <input
                              aria-label={`Resultado de ${game.home_team}`}
                              min={0}
                              onChange={(event) => updateResultDraft(game, "home", event.target.value)}
                              type="number"
                              value={resultDraft.home}
                            />
                            <span>x</span>
                            <input
                              aria-label={`Resultado de ${game.away_team}`}
                              min={0}
                              onChange={(event) => updateResultDraft(game, "away", event.target.value)}
                              type="number"
                              value={resultDraft.away}
                            />
                            <button disabled={savingResult === game.id} onClick={() => handleResult(game)} type="button">
                              <ShieldCheck size={15} />
                              <span>{savingResult === game.id ? "Lançando" : "Finalizar"}</span>
                            </button>
                          </div>
                        </div>
                        <input
                          aria-label="Quem marcou os gols"
                          className="input-field"
                          onChange={(event) => updateResultDraft(game, "scorers", event.target.value)}
                          placeholder="Quem marcou? Ex: Vini Jr, Mbappé"
                          value={resultDraft.scorers}
                        />
                      </div>
                    )}
                  </article>
                );
              })}
            </section>
          ) : (
            <section className="empty-state bolao-empty">
              <Trophy size={24} />
              <strong>Nenhum jogo encontrado</strong>
              <span>{isAdmin ? "Importe a tabela openfootball ou cadastre o primeiro jogo manualmente." : "O admin ainda vai liberar os jogos do bolão."}</span>
            </section>
          )}
        </div>

        <aside className="bolao-side">
          {highlights?.last_game && (
            <section className="bolao-highlight glass-panel">
              <div className="bolao-side-head">
                <span className="eyebrow">Último jogo</span>
                <Goal size={18} />
              </div>
              <h2>
                {highlights.last_game.home_team} {highlights.last_game.home_score} x {highlights.last_game.away_score}{" "}
                {highlights.last_game.away_team}
              </h2>
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
            </section>
          )}

          <section className="bolao-ranking glass-panel">
            <div className="bolao-side-head">
              <span className="eyebrow">Leaderboard</span>
              <Medal size={18} />
            </div>
            <h2>Ranking do bolão</h2>
            <div className="bolao-rules">
              <span>Placar exato: {board?.rules.exact_score ?? 3} pts</span>
              <span>Vencedor certo: {board?.rules.correct_outcome ?? 1} pt</span>
              <span>Artilheiro certo: +{board?.rules.scorer_bonus ?? 1} pt</span>
              <span>Campeão da Copa: {board?.rules.champion ?? 10} pts</span>
            </div>
            <div className="segmented-control bolao-ranking-tabs">
              {rankingTabs.map((tab) => (
                <button
                  className={rankingTab === tab.key ? "active" : ""}
                  key={tab.key}
                  onClick={() => setRankingTab(tab.key)}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="bolao-ranking-list">
              {sortedRanking.slice(0, 8).map((entry, index) => (
                <div className="bolao-rank-row" key={entry.user.id}>
                  <strong>{rankingTab === "geral" ? entry.rank : index + 1}</strong>
                  <Avatar user={entry.user} size="sm" />
                  <span>{entry.user.name}</span>
                  <small>
                    {rankingTab === "geral"
                      ? `${entry.exact_scores} exatos`
                      : rankingTab === "artilheiro"
                        ? `${entry.scorer_hits} acertos`
                        : `${entry.predictions} palpites`}
                  </small>
                  <b>
                    {rankingValue(entry, rankingTab)} {rankingUnit(rankingTab)}
                  </b>
                </div>
              ))}
              {sortedRanking.length === 0 && <p>Ninguém pontuou ainda. O ranking nasce no primeiro resultado finalizado.</p>}
            </div>
          </section>

          {isAdmin && (
            <section className="bolao-admin-panel glass-panel">
              <div className="bolao-side-head">
                <span className="eyebrow">Admin</span>
                <CalendarPlus size={18} />
              </div>
              <h2>Gerenciar jogos</h2>
              {board?.last_sync && (
                <p className="bolao-sync-info">
                  <RefreshCcw size={13} /> Sync automático: {formatEventDate(board.last_sync)}
                </p>
              )}
              <button className="btn-secondary bolao-sync-button" disabled={syncing} onClick={handleSyncOpenfootball} type="button">
                <DownloadCloud size={17} />
                <span>{syncing ? "Importando..." : "Sincronizar agora"}</span>
              </button>

              <form className="bolao-champion-form" onSubmit={handleAnnounceChampion}>
                <input
                  className="input-field"
                  list="bolao-teams"
                  onChange={(event) => setChampionAnnounceDraft(event.target.value)}
                  placeholder="Definir campeã da Copa"
                  value={championAnnounceDraft}
                />
                <button className="btn-secondary" disabled={announcingChampion || !championAnnounceDraft.trim()} type="submit">
                  <Crown size={16} />
                  <span>{announcingChampion ? "Definindo..." : "Definir campeã"}</span>
                </button>
              </form>

              <form className="bolao-admin-form" onSubmit={handleCreateGame}>
                <label>
                  Seleção mandante
                  <input
                    className="input-field"
                    onChange={(event) => updateGameDraft("home_team", event.target.value)}
                    required
                    value={gameDraft.home_team}
                  />
                </label>
                <label>
                  Seleção visitante
                  <input
                    className="input-field"
                    onChange={(event) => updateGameDraft("away_team", event.target.value)}
                    required
                    value={gameDraft.away_team}
                  />
                </label>
                <div className="bolao-admin-form-grid">
                  <label>
                    Data e hora
                    <input
                      className="input-field"
                      onChange={(event) => updateGameDraft("kickoff_at", event.target.value)}
                      required
                      type="datetime-local"
                      value={gameDraft.kickoff_at}
                    />
                  </label>
                  <label>
                    Grupo
                    <input
                      className="input-field"
                      onChange={(event) => updateGameDraft("group_label", event.target.value)}
                      placeholder="A"
                      value={gameDraft.group_label}
                    />
                  </label>
                </div>
                <label>
                  Fase
                  <select className="input-field" onChange={(event) => updateGameDraft("stage", event.target.value)} value={gameDraft.stage}>
                    {Object.entries(stageLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Estádio ou cidade
                  <input
                    className="input-field"
                    onChange={(event) => updateGameDraft("venue", event.target.value)}
                    value={gameDraft.venue}
                  />
                </label>
                <label>
                  Número do jogo
                  <input
                    className="input-field"
                    min={1}
                    onChange={(event) => updateGameDraft("match_number", event.target.value)}
                    type="number"
                    value={gameDraft.match_number}
                  />
                </label>
                <button className="btn-primary" disabled={creatingGame}>
                  <Save size={17} />
                  <span>{creatingGame ? "Cadastrando..." : "Cadastrar jogo"}</span>
                </button>
              </form>
            </section>
          )}
        </aside>
      </section>
    </AppShell>
  );
}
