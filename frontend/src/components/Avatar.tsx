import { BadgeCheck } from "lucide-react";
import type { UserProfile } from "@/types";
import { buildAvatarSeed, SvgAvatarFace } from "./SvgAvatarFace";

const supportedProfileEffects = new Set(["pulse", "stadium", "orbit", "nitro"]);

export function Avatar({
  user,
  size = "md",
  showVerified = true,
}: {
  user: UserProfile;
  size?: "sm" | "md" | "lg";
  showVerified?: boolean;
}) {
  const frame = user.profile_frame ?? "conversys";
  const effect =
    frame !== "none" && user.profile_effect && supportedProfileEffects.has(user.profile_effect)
      ? user.profile_effect
      : "off";
  const verified = Boolean(showVerified && user.verified_enabled && user.show_verified_badge !== false);

  return (
    <div aria-label={user.name} className={`avatar avatar-${size} avatar-frame-${frame} avatar-effect-${effect}`} role="img">
      {user.avatar_url ? (
        <img alt="" aria-hidden="true" className="avatar-photo" decoding="async" draggable={false} loading="lazy" src={user.avatar_url} />
      ) : (
        <SvgAvatarFace seed={buildAvatarSeed(user)} />
      )}
      {verified && (
        <span className="avatar-verified-mark" title="Perfil verificado">
          <BadgeCheck size={size === "lg" ? 16 : size === "md" ? 12 : 10} strokeWidth={size === "lg" ? 2.8 : 2.6} />
        </span>
      )}
    </div>
  );
}
