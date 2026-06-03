"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { PostCard } from "@/components/PostCard";
import { PostComposer } from "@/components/PostComposer";
import { api } from "@/lib/api";
import type { Event, Leaderboard, Post, UserProfile } from "@/types";

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
  const isAdmin = Boolean(profile?.is_admin);
  const pendingGoalClaims = isAdmin
    ? posts.filter((post) => (post.goals_scored ?? 0) > 0 && post.goal_status === "pending")
    : [];

  return (
    <AppShell user={profile} nextEvent={nextEvent} leaderboard={leaderboard}>
      <section className="feed-intro">
        <span className="eyebrow">Início</span>
        <h1>Publicações</h1>
        <p>Compartilhe uma atualização, foto ou lance com o grupo.</p>
      </section>

      <PostComposer
        events={events}
        isAdmin={isAdmin}
        onCreated={(post) => setPosts((current) => [post, ...current])}
        onEventCreated={(event) =>
          setEvents((current) =>
            [...current, event].sort((first, second) => new Date(first.date).getTime() - new Date(second.date).getTime()),
          )
        }
        user={profile}
      />

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
