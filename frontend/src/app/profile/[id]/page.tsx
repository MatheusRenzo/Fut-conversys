"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PostCard } from "@/components/PostCard";
import { ProfileHeader } from "@/components/ProfileHeader";
import { api } from "@/lib/api";
import type { Event, Leaderboard, Post, UserProfile } from "@/types";

export default function ProfilePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [viewer, setViewer] = useState<UserProfile | null>(null);
  const [profile, setProfile] = useState<(UserProfile & { posts: Post[] }) | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const id = Number(params.id);
        const [me, userProfile, eventList, ranking] = await Promise.all([
          api.me(),
          api.user(id),
          api.events(),
          api.leaderboard(),
        ]);
        setViewer(me);
        setProfile(userProfile);
        setEvents(eventList.events);
        setLeaderboard(ranking);
      } catch {
        router.push("/");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.id, router]);

  const updatePost = (updated: Post) => {
    setProfile((current) => {
      if (!current) return current;
      return {
        ...current,
        posts: current.posts.map((post) => (post.id === updated.id ? updated : post)),
      };
    });
  };

  if (loading || !profile) return <div className="empty-state">Carregando perfil...</div>;

  return (
    <AppShell user={viewer} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <ProfileHeader profile={profile} />

      <section className="profile-posts">
        {profile.posts.length === 0 && <div className="empty-state">Esse jogador ainda não postou fotos.</div>}
        {profile.posts.map((post) => (
          <PostCard post={post} onChange={updatePost} key={post.id} />
        ))}
      </section>
    </AppShell>
  );
}
