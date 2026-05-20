"use client";

import { createAvatar } from "@dicebear/core";
import { adventurerNeutral } from "@dicebear/collection";
import type { UserProfile } from "@/types";

export function buildAvatarSeed(user?: Pick<UserProfile, "name" | "username" | "id"> | null, extra = "") {
  return `${user?.username || user?.name || "conversys"}-${user?.id ?? "player"}-${extra}`;
}

export function SvgAvatarFace({
  seed,
  className = "",
}: {
  seed: string;
  className?: string;
}) {
  const svg = createAvatar(adventurerNeutral, {
    seed,
    radius: 50,
    backgroundColor: ["E6EFFF"],
    backgroundType: ["solid"],
    size: 128,
  }).toString();

  return <span aria-hidden="true" className={`svg-avatar-face ${className}`} dangerouslySetInnerHTML={{ __html: svg }} />;
}
