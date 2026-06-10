"use client";

import { useState } from "react";
import { teamFlagUrl, teamIsoCode } from "@/lib/flags";

export function TeamFlag({ team, className }: { team: string | null | undefined; className?: string }) {
  const [failed, setFailed] = useState(false);
  const code = teamIsoCode(team);

  if (!code || failed) {
    return (
      <span aria-hidden="true" className={["team-flag team-flag-fallback", className].filter(Boolean).join(" ")}>
        ⚽
      </span>
    );
  }

  return (
    <img
      alt={team ?? ""}
      className={["team-flag", className].filter(Boolean).join(" ")}
      decoding="async"
      loading="lazy"
      onError={() => setFailed(true)}
      src={teamFlagUrl(team, 80) ?? undefined}
      srcSet={`${teamFlagUrl(team, 80)} 1x, ${teamFlagUrl(team, 160)} 2x`}
    />
  );
}
