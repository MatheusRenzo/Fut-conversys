"use client";

import type { UserProfile } from "@/types";
import { Avatar } from "./Avatar";

const positionMap: Record<string, { label: string; x: number; y: number }> = {
  goleiro: { label: "Goleiro", x: 10, y: 50 },
  zagueiro: { label: "Zagueiro", x: 28, y: 50 },
  lateral: { label: "Lateral", x: 30, y: 22 },
  volante: { label: "Volante", x: 44, y: 50 },
  meia: { label: "Meia", x: 58, y: 50 },
  ponta: { label: "Ponta", x: 72, y: 24 },
  atacante: { label: "Atacante", x: 84, y: 50 },
};

function normalizePosition(position?: string | null) {
  const normalized = (position || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  return Object.entries(positionMap).find(([key]) => normalized.includes(key))?.[1] ?? {
    label: position || "Sem posição",
    x: 54,
    y: 50,
  };
}

export function LineupPreview({ compact = false, profile }: { compact?: boolean; profile: UserProfile }) {
  const position = normalizePosition(profile.position);

  return (
    <div className={compact ? "lineup-preview compact" : "lineup-preview"}>
      <div className="lineup-head">
        <span className="eyebrow">Escalação</span>
        <strong>{position.label}</strong>
      </div>
      <div className="lineup-field" aria-label={`Posição em campo: ${position.label}`}>
        <span className="lineup-box left" />
        <span className="lineup-box right" />
        <span className="lineup-midline" />
        <span className="lineup-circle" />
        <div
          className="lineup-player"
          style={{
            left: `${position.x}%`,
            top: `${position.y}%`,
          }}
        >
          <Avatar user={profile} size="sm" />
          <span>{profile.name.split(" ")[0]}</span>
        </div>
      </div>
    </div>
  );
}
