"use client";

import type { UserProfile } from "@/types";
import { BadgeCheck, CalendarDays, Flame, Goal, Handshake, ShieldCheck, Trophy } from "lucide-react";
import { Avatar } from "./Avatar";
import { LineupPreview } from "./LineupPreview";
import { PlayerRadarChart } from "./PlayerRadarChart";

const supportedProfileEffects = new Set(["pulse", "stadium", "orbit", "nitro"]);

function resolveEffect(profile: UserProfile) {
  if (profile.profile_effect && supportedProfileEffects.has(profile.profile_effect)) return profile.profile_effect;
  return "off";
}

export function ProfileHeader({ profile }: { profile: UserProfile }) {
  const frame = profile.profile_frame ?? "conversys";
  const effect = frame !== "none" ? resolveEffect(profile) : "off";
  const hasMotion = effect !== "off";

  return (
    <section className={`profile-hero glass-panel profile-frame-${frame}`}>
      <div
        className={`profile-banner banner-frame-${frame} banner-effect-${effect}${hasMotion ? " animated" : ""}`}
        style={{
          backgroundImage: profile.banner_url ? `url(${profile.banner_url})` : undefined,
          backgroundPosition: `${profile.banner_position_x ?? 50}% ${profile.banner_position_y ?? 50}%`,
        }}
      />
      <div className="profile-main">
        <div className="profile-info">
          <div className="profile-avatar-wrap">
            <Avatar user={profile} size="lg" />
            {profile.verified_enabled && profile.show_verified_badge !== false && (
              <span aria-label="Perfil verificado" className="profile-verified-mark" title="Perfil verificado">
                <BadgeCheck size={17} />
              </span>
            )}
          </div>
          <div className="profile-copy">
            <div className="profile-title-row">
              <h1>{profile.name}</h1>
            </div>
            <p>{profile.title || profile.position || "Jogador Conversys"}</p>
            <span>{profile.bio}</span>
            <div className="profile-tags">
              {profile.position && <span>{profile.position}</span>}
              {profile.favorite_team && <span>Time: {profile.favorite_team}</span>}
              {profile.favorite_player && <span>Inspiração: {profile.favorite_player}</span>}
            </div>
          </div>
        </div>
        <div className="profile-insights">
          {profile.stats && <PlayerRadarChart stats={profile.stats} />}
          <LineupPreview compact profile={profile} />
        </div>
      </div>

      {profile.stats && (
        <div className="stats-grid">
          <Stat icon={Trophy} label="Overall" value={profile.player_rating ?? profile.stats.overall ?? 78} />
          <Stat icon={ShieldCheck} label="Jogos" value={profile.stats.matches_played} />
          <Stat icon={Goal} label="Gols" value={profile.stats.goals} />
          <Stat icon={Handshake} label="Assists" value={profile.stats.assists} />
          <Stat icon={Flame} label="Churras" value={profile.stats.barbecue_score} />
          <Stat icon={CalendarDays} label="Conta" value={profile.stats.account_age_days ?? 0} />
        </div>
      )}
    </section>
  );
}

function Stat({ icon: Icon, label, value }: { icon: typeof Trophy; label: string; value: number }) {
  return (
    <div>
      <Icon size={18} />
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
