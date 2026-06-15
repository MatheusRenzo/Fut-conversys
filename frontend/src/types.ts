export type UserProfile = {
  id: number;
  username: string;
  email?: string | null;
  name: string;
  display_name?: string | null;
  title?: string | null;
  bio?: string | null;
  position?: string | null;
  favorite_team?: string | null;
  favorite_player?: string | null;
  avatar_url?: string | null;
  banner_url?: string | null;
  banner_position_x?: number | null;
  banner_position_y?: number | null;
  profile_frame?: ProfileFrame | null;
  cosmetic_tier?: CosmeticTier | null;
  animated_banner?: boolean;
  profile_effect?: ProfileEffect | null;
  show_verified_badge?: boolean;
  avatar_config?: AvatarConfig | null;
  player_rating?: number;
  verified_domain: boolean;
  verified_enabled: boolean;
  is_admin: boolean;
  stats?: PlayerStats;
};

export type ProfileFrame =
  | "none"
  | "conversys"
  | "copa"
  | "brasil"
  | "argentina"
  | "franca"
  | "portugal"
  | "espanha"
  | "alemanha"
  | "inglaterra"
  | "eua"
  | "mexico"
  | "canada"
  | "africa_sul"
  | "coreia_sul"
  | "tchequia"
  | "bosnia"
  | "qatar"
  | "suica"
  | "marrocos"
  | "haiti"
  | "escocia"
  | "paraguai"
  | "australia"
  | "turquia"
  | "curacao"
  | "costa_marfim"
  | "equador"
  | "holanda"
  | "japao"
  | "suecia"
  | "tunisia"
  | "belgica"
  | "egito"
  | "ira"
  | "nova_zelandia"
  | "cabo_verde"
  | "arabia_saudita"
  | "uruguai"
  | "senegal"
  | "iraque"
  | "noruega"
  | "argelia"
  | "austria"
  | "jordania"
  | "rd_congo"
  | "uzbequistao"
  | "colombia"
  | "croacia"
  | "gana"
  | "panama"
  | "nitro_plus"
  | "pro"
  | "legend"
  | "world"
  | "neon"
  | "pulse"
  | "champion";
export type CosmeticTier = "starter";
export type ProfileEffect = "off" | "pulse" | "stadium" | "orbit" | "nitro";

export type AvatarConfig = {
  body: "slim" | "athletic" | "strong";
  presentation: "player" | "keeper";
  skin: "light" | "medium" | "dark";
  hair: "short" | "curly" | "long" | "fade";
  kit: "home" | "away" | "keeper" | "classic";
  shorts: "navy" | "white" | "blue" | "black";
  boots: "blue" | "cyan" | "pink" | "green";
  gender: "neutral" | "woman" | "man";
  pose: "captain" | "striker" | "keeper";
};

export type PlayerStats = {
  matches_played: number;
  goals: number;
  assists: number;
  fouls: number;
  barbecue_score: number;
  posts?: number;
  likes_received?: number;
  account_age_days?: number;
  churrasco?: number;
  bebedeira?: number;
  golaco_score?: number;
  resenha?: number;
  midia?: number;
  torcida?: number;
  reaction_torcida?: number;
  reaction_golaco?: number;
  reaction_churras?: number;
  reaction_resenha?: number;
  reaction_midia?: number;
  reaction_bebedeira?: number;
  post_goals?: number;
  media_posts?: number;
  comments_received?: number;
  comments_made?: number;
  media_comments?: number;
  overall?: number;
  attack?: number;
  passing?: number;
  defense?: number;
  stamina?: number;
  skill?: number;
  vibe?: number;
};

export type Event = {
  id: number;
  title: string;
  event_type: string;
  location: string;
  date: string;
  description: string;
  max_players: number;
  status: string;
  cover_url?: string | null;
  confirmed_players: number;
  user_has_rsvpd: boolean;
  user_rsvp_status?: string | null;
  attendees: UserProfile[];
};

export type EventCreatePayload = {
  title: string;
  event_type: string;
  location: string;
  date: string;
  description: string;
  max_players: number;
  cover_url?: string | null;
};

export type Comment = {
  id: number;
  text: string;
  parent_id?: number | null;
  media_url?: string | null;
  media_type?: "image" | "gif" | null;
  created_at: string;
  author: UserProfile;
};

export type ReactionType =
  | "torcida"
  | "golaco"
  | "churras"
  | "resenha"
  | "midia"
  | "bebedeira";
export type GoalStatus = "none" | "pending" | "approved" | "rejected";

export type Post = {
  id: number;
  title?: string | null;
  description?: string | null;
  image_url?: string | null;
  goals_scored?: number;
  approved_goals?: number;
  goal_status?: GoalStatus;
  goal_reviewed_at?: string | null;
  can_review_goals?: boolean;
  created_at: string;
  author: UserProfile;
  match?: Event | null;
  likes_count: number;
  reactions?: Record<ReactionType, number>;
  viewer_reaction?: ReactionType | null;
  comments_count: number;
  liked_by_user: boolean;
  comments: Comment[];
};

export type Leaderboard = {
  top_scorers: Array<UserProfile & { score: number }>;
  top_barbecue: Array<UserProfile & { score: number }>;
};

export type WorldCupPrediction = {
  id: number;
  game_id: number;
  home_score: number;
  away_score: number;
  scorer_guess?: string | null;
  scorer_hit?: boolean;
  points: number;
  status: "pending" | "scored";
  created_at?: string | null;
  updated_at?: string | null;
  user: UserProfile;
};

export type WorldCupGame = {
  id: number;
  external_id?: string | null;
  match_number?: number | null;
  home_team: string;
  away_team: string;
  group_label?: string | null;
  stage: string;
  venue?: string | null;
  kickoff_at: string;
  status: "scheduled" | "live" | "finished" | "postponed";
  halftime?: boolean;
  home_score?: number | null;
  away_score?: number | null;
  scorers?: string | null;
  source?: string | null;
  predictions_count: number;
  is_placeholder?: boolean;
  bettable?: boolean;
  lock_passed?: boolean;
  viewer_prediction?: WorldCupPrediction | null;
  // Quem já palpitou (sempre visível); palpites completos só após o fechamento
  bettors?: UserProfile[];
  predictions?: WorldCupPrediction[];
};

export type WorldCupLeaderboardEntry = {
  rank: number;
  user: UserProfile;
  points: number;
  predictions: number;
  scored_predictions: number;
  exact_scores: number;
  outcome_hits: number;
  scorer_hits: number;
  champion_team?: string | null;
  champion_points: number;
  movement?: number;
  round_gain?: number;
};

export type WorldCupChampionPick = {
  id: number;
  team: string;
  points: number;
  status: "pending" | "scored";
  user: UserProfile;
};

export type WorldCupChampion = {
  team?: string | null;
  locked: boolean;
  lock_at?: string | null;
  points_award: number;
  picks_count: number;
  viewer_pick?: WorldCupChampionPick | null;
  picks: WorldCupChampionPick[];
};

export type WorldCupPlayer = {
  id: number;
  name: string;
  number?: number | null;
  position?: string | null;
  club?: string | null;
};

export type WorldCupSquads = Record<string, WorldCupPlayer[]>;

export type WorldCupHighlights = {
  last_game?: WorldCupGame | null;
  last_game_winners: WorldCupPrediction[];
};

export type WorldCupBoard = {
  games: WorldCupGame[];
  leaderboard: WorldCupLeaderboardEntry[];
  champion: WorldCupChampion;
  highlights: WorldCupHighlights;
  last_sync?: string | null;
  rules: {
    exact_score: number;
    correct_outcome: number;
    scorer_bonus: number;
    champion: number;
    locked_after_kickoff: boolean;
  };
};

export type WorldCupSyncStatus = {
  last_sync?: string | null;
  last_squad_sync?: string | null;
  games_sync?: {
    at?: string;
    ok?: boolean;
    error?: string | null;
    imported?: number;
    updated?: number;
    finished_games?: number;
    missing_scorers?: string[];
    secondary?: {
      configured: boolean;
      ok: boolean;
      matched: number;
      filled: number;
      conflicts: Array<{ match_number?: number | null; game: string; openfootball: string; football_data: string }>;
      error?: string | null;
    };
    live_source?: {
      configured: boolean;
      ok: boolean;
      live_games: number;
      scorers_updated: number;
      finalized?: number;
      calls_made?: number;
      calls_today?: number;
      daily_remaining?: number | null;
      daily_limit?: number;
      games_today?: number;
      active_today?: number;
      per_game_cap?: number;
      live_gap_seconds?: number;
      mid_checks?: number;
      confirmed?: number;
      reconfirmed?: number;
      retries?: number;
      ai_reconciles?: number;
      reserve?: number;
      tsd_calls?: number;
      minute_throttled?: boolean;
      goal_pending?: boolean;
      key_used?: number;
      skipped?: string | null;
      error?: string | null;
    };
  } | null;
  runs?: Array<{
    at?: string;
    ok?: boolean;
    error?: string | null;
    imported?: number;
    updated?: number;
    finished?: number;
    live_games?: number;
    scorers_updated?: number;
    finalized?: number;
    api_calls?: number;
    api_remaining?: number | null;
    filled?: number;
    conflicts?: number;
  }>;
  live_now?: boolean;
  interval_seconds?: number;
  live_interval_seconds?: number;
  idle_interval_seconds?: number;
  squad_sync?: {
    at?: string;
    ok?: boolean;
    error?: string | null;
    imported?: number;
    updated?: number;
    teams?: number;
    players?: number;
  } | null;
  sync_interval_seconds: number;
  sources: {
    openfootball_url: string;
    football_data_configured: boolean;
    api_football_configured?: boolean;
    api_football_keys?: number;
    api_football_daily_remaining?: number | null;
    api_football_daily_limit?: number;
    score_source?: string;
    scorer_source?: string;
    ai_configured?: boolean;
    ai_calls_today?: number;
    thesportsdb_configured?: boolean;
    squads_source: string;
  };
  games_health?: Array<{
    match_number?: number | null;
    matchup: string;
    status: string;
    score?: string | null;
    goals: number;
    scorers?: string | null;
    scorers_count: number;
    scorers_complete: boolean;
    scorers_final: boolean;
    scorers_confirmed?: boolean;
    scorers_confirmations?: number;
    confirmation_sources?: string | null;
    end_source?: string | null;
    halftime?: boolean;
    reconfirmed?: boolean;
    polls?: { api_football: number; thesportsdb: number };
    has_fixture_id: boolean;
    predictions: number;
  }>;
  totals: {
    games: number;
    live_games?: number;
    finished_games: number;
    finished_without_scorers: number;
    players: number;
    teams_with_squads: number;
  };
  game_events?: Array<{
    at: string;
    match_number?: number | null;
    game: string;
    action: string;
    phase?: string | null;
    api?: string | null;
    ok?: boolean | null;
  }>;
  today_games?: Array<{
    match_number?: number | null;
    home_team: string;
    away_team: string;
    kickoff_at?: string | null;
    status: string;
    score?: string | null;
    scorers?: string | null;
    scorers_complete?: boolean;
    scorers_confirmations?: number;
    end_source?: string | null;
    halftime?: boolean;
  }>;
  requests_today?: Record<
    string,
    {
      calls: number;
      daily_cap?: number | null;
      remaining?: number | null;
      limit_per_min?: number;
      label?: string;
    }
  >;
  cadence?: {
    live_now: boolean;
    loop_seconds: number;
    last_sync_at?: string | null;
    last_live_poll_at?: string | null;
    live_poll_gap_seconds?: number;
    goal_pending?: boolean;
    last_scorer_update_at?: string | null;
  };
};

export type SearchResults = {
  profiles: UserProfile[];
  events: Event[];
  posts: Post[];
};
