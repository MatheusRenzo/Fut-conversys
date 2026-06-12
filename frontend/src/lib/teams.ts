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

// Nomes das seleções em pt-BR (os dados ficam em inglês — fonte openfootball)
const TEAM_NAMES_PT: Record<string, string> = {
  Mexico: "México",
  "South Africa": "África do Sul",
  "South Korea": "Coreia do Sul",
  "Czech Republic": "República Tcheca",
  Canada: "Canadá",
  "Bosnia & Herzegovina": "Bósnia e Herzegovina",
  Qatar: "Catar",
  Switzerland: "Suíça",
  Brazil: "Brasil",
  Morocco: "Marrocos",
  Haiti: "Haiti",
  Scotland: "Escócia",
  USA: "Estados Unidos",
  Paraguay: "Paraguai",
  Australia: "Austrália",
  Turkey: "Turquia",
  Germany: "Alemanha",
  Curaçao: "Curaçao",
  "Ivory Coast": "Costa do Marfim",
  Ecuador: "Equador",
  Netherlands: "Holanda",
  Japan: "Japão",
  Sweden: "Suécia",
  Tunisia: "Tunísia",
  Belgium: "Bélgica",
  Egypt: "Egito",
  Iran: "Irã",
  "New Zealand": "Nova Zelândia",
  Spain: "Espanha",
  "Cape Verde": "Cabo Verde",
  "Saudi Arabia": "Arábia Saudita",
  Uruguay: "Uruguai",
  France: "França",
  Senegal: "Senegal",
  Iraq: "Iraque",
  Norway: "Noruega",
  Argentina: "Argentina",
  Algeria: "Argélia",
  Austria: "Áustria",
  Jordan: "Jordânia",
  Portugal: "Portugal",
  "DR Congo": "RD Congo",
  Uzbekistan: "Uzbequistão",
  Colombia: "Colômbia",
  England: "Inglaterra",
  Croatia: "Croácia",
  Ghana: "Gana",
  Panama: "Panamá",
};

export function teamLabel(team: string | null | undefined): string {
  if (!team) return "";
  const cleaned = team.trim();
  return TEAM_NAMES_PT[squadAliases[cleaned] ?? cleaned] ?? cleaned;
}
