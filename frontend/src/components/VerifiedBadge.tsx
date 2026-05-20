import { BadgeCheck } from "lucide-react";

export function VerifiedBadge({ verified }: { verified?: boolean }) {
  if (!verified) return null;

  return (
    <span className="verified-badge">
      <BadgeCheck size={14} />
      Conversys verified
    </span>
  );
}
