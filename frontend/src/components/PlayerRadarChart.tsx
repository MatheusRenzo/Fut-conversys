"use client";

import type { PlayerStats } from "@/types";

const skills: Array<{ key: keyof PlayerStats; label: string }> = [
  { key: "golaco_score", label: "Finalização" },
  { key: "torcida", label: "Raça" },
  { key: "resenha", label: "Visão" },
  { key: "midia", label: "Estilo" },
  { key: "churrasco", label: "Elenco" },
  { key: "bebedeira", label: "Moral" },
];

function clampScore(value: number | undefined) {
  return Math.max(40, Math.min(99, Math.round(value ?? 50)));
}

function pointFor(index: number, value: number, radius: number, center: number) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / skills.length;
  const scaledRadius = radius * (value / 100);
  return {
    x: center + Math.cos(angle) * scaledRadius,
    y: center + Math.sin(angle) * scaledRadius,
  };
}

function pointsFor(values: number[], radius: number, center: number) {
  return values.map((value, index) => {
    const point = pointFor(index, value, radius, center);
    return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  });
}

export function PlayerRadarChart({ stats }: { stats: PlayerStats }) {
  const center = 104;
  const radius = 72;
  const values = skills.map((skill) => clampScore(stats[skill.key] as number | undefined));
  const radarPoints = pointsFor(values, radius, center);
  const average = Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
  const gridLevels = [0.25, 0.5, 0.75, 1];

  return (
    <div className="player-radar-card">
      <div className="radar-head">
        <span className="eyebrow">Status da firma</span>
        <strong>{average}</strong>
      </div>

      <div className="radar-visual">
        <svg aria-label="Radar de status da firma" className="radar-chart" viewBox="0 0 208 208">
          {gridLevels.map((level) => (
            <polygon
              className="radar-grid"
              key={level}
              points={pointsFor(skills.map(() => level * 100), radius, center).join(" ")}
            />
          ))}
          {skills.map((skill, index) => {
            const outer = pointFor(index, 100, radius, center);
            const label = pointFor(index, 118, radius, center);
            return (
              <g key={skill.key}>
                <line className="radar-axis" x1={center} y1={center} x2={outer.x} y2={outer.y} />
                <text className="radar-label" textAnchor="middle" x={label.x} y={label.y + 4}>
                  {skill.label}
                </text>
              </g>
            );
          })}
          <polygon className="radar-fill" points={radarPoints.join(" ")} />
          <polyline className="radar-stroke" points={`${radarPoints.join(" ")} ${radarPoints[0]}`} />
          {values.map((value, index) => {
            const point = pointFor(index, value, radius, center);
            return <circle className="radar-dot" cx={point.x} cy={point.y} key={skills[index].key} r="3.4" />;
          })}
        </svg>
      </div>

      <div className="radar-skills">
        {skills.map((skill, index) => (
          <div className="radar-skill" key={skill.key}>
            <span>{skill.label}</span>
            <strong>{values[index]}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
