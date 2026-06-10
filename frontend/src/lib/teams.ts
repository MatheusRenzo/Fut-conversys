const squadAliases: Record<string, string> = {
  "United States": "USA",
  "Bosnia and Herzegovina": "Bosnia & Herzegovina",
};

export function squadTeamKey(team: string | null | undefined): string {
  if (!team) return "";
  const cleaned = team.trim();
  return squadAliases[cleaned] ?? cleaned;
}

export function isPlaceholderTeam(team: string | null | undefined): boolean {
  if (!team) return true;
  const name = team.trim();
  if (!name || name.includes("/")) return true;
  return /^(?:[12][A-L]|W\d+|L\d+|3[A-L](?:\/[A-L])+)$/.test(name);
}

export function isBettableGame(homeTeam: string, awayTeam: string): boolean {
  return !isPlaceholderTeam(homeTeam) && !isPlaceholderTeam(awayTeam);
}
