// Horários do bolão são sempre exibidos no fuso de Brasília,
// independente do fuso do navegador do usuário
const BRAZIL_TIME_ZONE = "America/Sao_Paulo";

export function formatEventDate(value: string) {
  return new Date(value).toLocaleDateString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: BRAZIL_TIME_ZONE,
  });
}

export function formatShortDate(value: string) {
  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    timeZone: BRAZIL_TIME_ZONE,
  });
}
