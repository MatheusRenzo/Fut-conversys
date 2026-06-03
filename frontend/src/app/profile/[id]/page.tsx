"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { FileImage, Heart, MessageCircle } from "lucide-react";
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

      <ProfilePostGrid posts={profile.posts} />

      <section className="profile-posts">
        {profile.posts.length === 0 && <div className="empty-state">Esse jogador ainda não postou fotos.</div>}
        {profile.posts.map((post) => (
          <div id={`post-${post.id}`} key={post.id}>
            <PostCard post={post} onChange={updatePost} />
          </div>
        ))}
      </section>
    </AppShell>
  );
}

function ProfilePostGrid({ posts }: { posts: Post[] }) {
  const recentPosts = posts.slice(0, 9);

  return (
    <section className="profile-gallery glass-panel">
      <div className="profile-gallery-head">
        <div>
          <span className="eyebrow">Últimos posts</span>
          <h2>Grade do jogador</h2>
        </div>
        <span>{posts.length} posts</span>
      </div>

      {recentPosts.length === 0 ? (
        <div className="profile-gallery-empty">
          <FileImage size={22} />
          <span>Nenhum post ainda. Quando esse jogador postar, aparece aqui.</span>
        </div>
      ) : (
        <div className="profile-gallery-grid">
          {recentPosts.map((post) => (
            <button
              className="profile-gallery-item"
              key={post.id}
              onClick={() => document.getElementById(`post-${post.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
              type="button"
            >
              {post.image_url ? (
                <span
                  aria-label={post.title || post.description || "Post do jogador"}
                  className="profile-gallery-photo"
                  role="img"
                  style={{ backgroundImage: `url(${post.image_url})` }}
                />
              ) : (
                <span className="profile-gallery-text-card">
                  <FileImage size={20} />
                  <strong>{post.title || "Post sem foto"}</strong>
                  {post.description && <small>{post.description}</small>}
                </span>
              )}
              <span className="profile-gallery-overlay">
                <span>
                  <Heart size={15} />
                  {post.likes_count}
                </span>
                <span>
                  <MessageCircle size={15} />
                  {post.comments_count}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
