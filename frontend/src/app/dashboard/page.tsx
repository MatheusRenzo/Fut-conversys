"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Flame, MessageCircle, UsersRound } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { PostCard } from "@/components/PostCard";
import { PostComposer } from "@/components/PostComposer";
import { api } from "@/lib/api";
import type { Event, Leaderboard, Post, UserProfile } from "@/types";

const adminUsername = process.env.NEXT_PUBLIC_ADMIN_USERNAME ?? "admin";

export default function Dashboard() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [me, feed, eventList, ranking] = await Promise.all([
          api.me(),
          api.feed(),
          api.events(),
          api.leaderboard(),
        ]);
        setProfile(me);
        setPosts(feed.posts);
        setEvents(eventList.events);
        setLeaderboard(ranking);
      } catch {
        router.push("/");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [router]);

  const updatePost = (updated: Post) => {
    setPosts((current) => current.map((post) => (post.id === updated.id ? updated : post)));
  };

  const refreshGoalScores = async () => {
    const [me, ranking] = await Promise.all([api.me(), api.leaderboard()]);
    setProfile(me);
    setLeaderboard(ranking);
  };

  const handleRSVP = async (eventId: number, status: "going" | "not_going") => {
    const updated = await api.rsvp(eventId, status);
    setEvents((current) => current.map((event) => (event.id === eventId ? updated : event)));
  };

  if (loading) {
    return <div className="empty-state">Carregando vestiário...</div>;
  }

  const nextEvent = events[0] ?? null;
  const isAdmin = profile?.username === adminUsername;
  const pendingGoalClaims = isAdmin
    ? posts.filter((post) => (post.goals_scored ?? 0) > 0 && post.goal_status === "pending")
    : [];

  return (
    <AppShell user={profile} nextEvent={nextEvent} leaderboard={leaderboard}>
      <section className="section-heading dashboard-hero">
        <div>
          <span className="eyebrow">Feed da firma</span>
          <h1>Resenha, gols e churras</h1>
          <p>Publique fotos, combine o próximo jogo e acompanhe quem confirmou presença.</p>
        </div>
        <div className="hero-metrics">
          <div>
            <UsersRound size={18} />
            <strong>{nextEvent?.confirmed_players ?? 0}</strong>
            <span>confirmados</span>
          </div>
          <div>
            <MessageCircle size={18} />
            <strong>{posts.reduce((total, post) => total + post.comments_count, 0)}</strong>
            <span>comentários</span>
          </div>
          <div>
            <Flame size={18} />
            <strong>{posts.reduce((total, post) => total + post.likes_count, 0)}</strong>
            <span>reações</span>
          </div>
        </div>
      </section>

      <PostComposer events={events} onCreated={(post) => setPosts((current) => [post, ...current])} user={profile} />

      {isAdmin && pendingGoalClaims.length > 0 && (
        <section className="goal-admin-summary glass-panel">
          <div>
            <span className="eyebrow">Admin</span>
            <h2>{pendingGoalClaims.length} solicitação{pendingGoalClaims.length > 1 ? "ões" : ""} de gol pendente{pendingGoalClaims.length > 1 ? "s" : ""}</h2>
            <p>Abra o post e aprove apenas gols conferidos no evento.</p>
          </div>
        </section>
      )}

      {nextEvent && <EventCard event={nextEvent} onRSVP={handleRSVP} />}

      <section className="feed-stack">
        {posts.map((post) => (
          <PostCard post={post} onChange={updatePost} onGoalReviewed={refreshGoalScores} key={post.id} />
        ))}
      </section>
    </AppShell>
  );
}
