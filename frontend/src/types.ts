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
  home_score?: number | null;
  away_score?: number | null;
  source?: string | null;
  predictions_count: number;
  viewer_prediction?: WorldCupPrediction | null;
};

export type WorldCupLeaderboardEntry = {
  rank: number;
  user: UserProfile;
  points: number;
  predictions: number;
  scored_predictions: number;
  exact_scores: number;
};

export type WorldCupBoard = {
  games: WorldCupGame[];
  leaderboard: WorldCupLeaderboardEntry[];
  rules: {
    exact_score: number;
    correct_outcome: number;
    locked_after_kickoff: boolean;
  };
};

export type SearchResults = {
  profiles: UserProfile[];
  events: Event[];
  posts: Post[];
};
