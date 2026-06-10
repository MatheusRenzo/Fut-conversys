import type { UserProfile } from "@/types";
import { buildAvatarSeed, SvgAvatarFace } from "./SvgAvatarFace";

const supportedProfileEffects = new Set(["pulse", "stadium", "orbit", "nitro"]);

export function Avatar({ user, size = "md" }: { user: UserProfile; size?: "sm" | "md" | "lg" }) {
  const frame = user.profile_frame ?? "conversys";
  const effect =
    frame !== "none" && user.profile_effect && supportedProfileEffects.has(user.profile_effect)
      ? user.profile_effect
      : "off";

  return (
    <div aria-label={user.name} className={`avatar avatar-${size} avatar-frame-${frame} avatar-effect-${effect}`} role="img">
      {user.avatar_url ? (
        <img alt="" aria-hidden="true" className="avatar-photo" draggable={false} src={user.avatar_url} />
      ) : (
        <SvgAvatarFace seed={buildAvatarSeed(user)} />
      )}
    </div>
  );
}
