import type {
  Event,
  EventCreatePayload,
  GoalStatus,
  Leaderboard,
  Post,
  ReactionType,
  SearchResults,
  UserProfile,
  WorldCupBoard,
  WorldCupChampion,
  WorldCupGame,
  WorldCupLeaderboardEntry,
} from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiOptions = RequestInit & {
  auth?: boolean;
};

export function setSession(user: UserProfile) {
  localStorage.setItem("user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("user");
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);

  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const targetPath = path.startsWith("/api/session")
    ? path
    : path.startsWith("/api/")
      ? `/api/backend${path}`
      : path;
  const response = await fetch(targetPath, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    if (response.status === 401) {
      clearSession();
      if (typeof window !== "undefined" && window.location.pathname !== "/") {
        window.location.href = "/";
      }
    }
    throw new Error(data?.detail || "Erro ao comunicar com o servidor");
  }

  return data as T;
}

export const api = {
  login: (username: string, password: string) =>
    apiFetch<{ user: UserProfile }>("/api/session/login", {
      auth: false,
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (payload: { name: string; email: string; password: string; username?: string }) =>
    apiFetch<{ user: UserProfile }>("/api/session/register", {
      auth: false,
      method: "POST",
      body: JSON.stringify(payload),
    }),
  logout: () =>
    apiFetch<{ ok: boolean }>("/api/session/logout", {
      auth: false,
      method: "POST",
    }),
  sessionMe: () => apiFetch<UserProfile>("/api/session/me", { auth: false }),
  microsoftConfig: () =>
    apiFetch<{
      enabled: boolean;
      provider: string;
      required_env: string[];
      redirect_uri: string;
      verified_domain: string;
    }>("/api/auth/microsoft/config", { auth: false }),
  me: () => apiFetch<UserProfile>("/api/me"),
  search: (query: string) => apiFetch<SearchResults>(`/api/search?q=${encodeURIComponent(query)}`),
  updateMe: (profile: Partial<UserProfile>) =>
    apiFetch<UserProfile>("/api/users/me/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    }),
  user: (id: number) => apiFetch<UserProfile & { posts: Post[] }>(`/api/users/${id}`),
  adminUsers: () => apiFetch<{ users: UserProfile[] }>("/api/admin/users"),
  setUserVerified: (userId: number, verifiedEnabled: boolean) =>
    apiFetch<UserProfile>(`/api/admin/users/${userId}/verified`, {
      method: "PUT",
      body: JSON.stringify({ verified_enabled: verifiedEnabled }),
    }),
  feed: () => apiFetch<{ posts: Post[] }>("/api/feed"),
  createPost: (payload: {
    title?: string;
    description: string;
    image_url?: string;
    match_id?: number;
    goals_scored?: number;
  }) =>
    apiFetch<Post>("/api/posts", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  toggleLike: (postId: number) =>
    apiFetch<{ liked: boolean; post: Post }>(`/api/posts/${postId}/like`, { method: "POST" }),
  toggleReaction: (postId: number, reactionType: ReactionType) =>
    apiFetch<{ liked: boolean; post: Post }>(`/api/posts/${postId}/like`, {
      method: "POST",
      body: JSON.stringify({ reaction_type: reactionType }),
    }),
  reviewPostGoals: (postId: number, status: Extract<GoalStatus, "approved" | "rejected">) =>
    apiFetch<Post>(`/api/admin/posts/${postId}/goals`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  addComment: (
    postId: number,
    payload: {
      text: string;
      parent_id?: number;
      media_url?: string;
      media_type?: "image" | "gif";
    },
  ) =>
    apiFetch<Post>(`/api/posts/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  events: () => apiFetch<{ events: Event[] }>("/api/events"),
  createEvent: (payload: EventCreatePayload) =>
    apiFetch<Event>("/api/events", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  event: (id: number) => apiFetch<Event>(`/api/events/${id}`),
  rsvp: (eventId: number, status: "going" | "not_going") =>
    apiFetch<Event>(`/api/events/${eventId}/rsvp`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  leaderboard: () => apiFetch<Leaderboard>("/api/leaderboard"),
  worldCupBoard: () => apiFetch<WorldCupBoard>("/api/world-cup/board"),
  createWorldCupGame: (payload: {
    home_team: string;
    away_team: string;
    kickoff_at: string;
    group_label?: string | null;
    stage?: string;
    venue?: string | null;
    match_number?: number | null;
    external_id?: string | null;
    source?: string | null;
  }) =>
    apiFetch<WorldCupGame>("/api/world-cup/games", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  syncWorldCupOpenfootball: () =>
    apiFetch<{ imported: number; updated: number; games: WorldCupGame[]; leaderboard: WorldCupLeaderboardEntry[] }>(
      "/api/world-cup/sync/openfootball",
      {
        method: "POST",
      },
    ),
  submitWorldCupPrediction: (gameId: number, payload: { home_score: number; away_score: number; scorer_guess?: string | null }) =>
    apiFetch<WorldCupGame>(`/api/world-cup/games/${gameId}/prediction`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  setWorldCupGameResult: (
    gameId: number,
    payload: { home_score: number; away_score: number; status?: string; scorers?: string | null },
  ) =>
    apiFetch<{ game: WorldCupGame; leaderboard: WorldCupLeaderboardEntry[] }>(`/api/world-cup/games/${gameId}/result`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitWorldCupChampionPick: (team: string) =>
    apiFetch<WorldCupChampion>("/api/world-cup/champion-pick", {
      method: "POST",
      body: JSON.stringify({ team }),
    }),
  announceWorldCupChampion: (team: string) =>
    apiFetch<{ champion: WorldCupChampion; leaderboard: WorldCupLeaderboardEntry[] }>("/api/world-cup/champion", {
      method: "POST",
      body: JSON.stringify({ team }),
    }),
};
