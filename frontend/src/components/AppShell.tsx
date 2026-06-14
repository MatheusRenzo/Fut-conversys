"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CalendarDays,
  ChevronRight,
  FileText,
  Goal,
  Home,
  LoaderCircle,
  LogOut,
  Pencil,
  Search,
  Target,
  Trophy,
  UserRound,
} from "lucide-react";
import { api, clearSession } from "@/lib/api";
import type { Event, Leaderboard, SearchResults, UserProfile, WorldCupLeaderboardEntry } from "@/types";
import { Avatar } from "./Avatar";
import { formatEventDate, formatShortDate } from "@/lib/format";

const navItems = [
  { href: "/dashboard", label: "Feed", icon: Home },
  { href: "/events", label: "Eventos", icon: CalendarDays },
  { href: "/bolao", label: "Bolão", icon: Trophy },
  { href: "/me", label: "Meu perfil", icon: UserRound },
];

function BrandLogo({ compact = false }: { compact?: boolean }) {
  return (
    <span className={compact ? "sidebar-brand-logo compact" : "sidebar-brand-logo"}>
      <Image
        alt="Fut Conversys"
        className="sidebar-brand-image"
        height={compact ? 40 : 72}
        priority
        src="/icons/fut-conversys-logo.png"
        width={compact ? 120 : 220}
      />
    </span>
  );
}

const emptySearchResults: SearchResults = {
  profiles: [],
  events: [],
  posts: [],
};

function GlobalSearch({ compact = false }: { compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults>(emptySearchResults);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement | null>(null);
  const trimmedQuery = query.trim();
  const hasResults = results.profiles.length > 0 || results.events.length > 0 || results.posts.length > 0;

  useEffect(() => {
    const closeWhenOutside = (event: PointerEvent) => {
      if (!searchRef.current?.contains(event.target as Node)) setOpen(false);
    };

    document.addEventListener("pointerdown", closeWhenOutside);
    return () => document.removeEventListener("pointerdown", closeWhenOutside);
  }, []);

  useEffect(() => {
    if (trimmedQuery.length < 2) {
      return;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      api
        .search(trimmedQuery)
        .then((nextResults) => {
          if (!active) return;
          setResults(nextResults);
          setOpen(true);
        })
        .catch(() => {
          if (active) setResults(emptySearchResults);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 220);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [trimmedQuery]);

  const closeSearch = () => setOpen(false);

  return (
    <div className={compact ? "global-search compact" : "global-search"} ref={searchRef}>
      <label className="global-search-field">
        <Search size={17} />
        <input
          aria-label="Buscar perfis, eventos e publicações"
          onChange={(event) => {
            const nextQuery = event.target.value;
            setQuery(nextQuery);
            if (nextQuery.trim().length < 2) {
              setResults(emptySearchResults);
              setLoading(false);
              setOpen(false);
              return;
            }
            setLoading(true);
            setOpen(true);
          }}
          onFocus={() => trimmedQuery.length >= 2 && setOpen(true)}
          placeholder={compact ? "Buscar" : "Buscar perfis, eventos ou posts"}
          value={query}
        />
        {loading && <LoaderCircle className="search-loading-icon" size={15} />}
      </label>

      {open && trimmedQuery.length >= 2 && (
        <div className="global-search-dropdown">
          {hasResults ? (
            <>
              <section>
                <span className="search-section-label">Perfis</span>
                {results.profiles.length > 0 ? (
                  results.profiles.map((profile) => (
                    <Link className="search-result-item" href={`/profile/${profile.id}`} key={profile.id} onClick={closeSearch}>
                      <Avatar user={profile} size="sm" />
                      <span>
                        <strong>{profile.name}</strong>
                        <small>{profile.position || profile.title || "Perfil"}</small>
                      </span>
                    </Link>
                  ))
                ) : (
                  <p className="search-empty-line">Nenhum perfil encontrado</p>
                )}
              </section>

              <section>
                <span className="search-section-label">Eventos</span>
                {results.events.length > 0 ? (
                  results.events.map((event) => (
                    <Link className="search-result-item" href={`/events/${event.id}`} key={event.id} onClick={closeSearch}>
                      <span className="search-result-icon">
                        <CalendarDays size={16} />
                      </span>
                      <span>
                        <strong>{event.title}</strong>
                        <small>
                          {formatEventDate(event.date)} - {event.location}
                        </small>
                      </span>
                    </Link>
                  ))
                ) : (
                  <p className="search-empty-line">Nenhum evento encontrado</p>
                )}
              </section>

              <section>
                <span className="search-section-label">Publicações</span>
                {results.posts.length > 0 ? (
                  results.posts.map((post) => (
                    <Link className="search-result-item" href={`/dashboard#post-${post.id}`} key={post.id} onClick={closeSearch}>
                      <span className="search-result-icon">
                        <FileText size={16} />
                      </span>
                      <span>
                        <strong>{post.title || post.description || `Publicação de ${post.author.name}`}</strong>
                        <small>
                          {post.author.name} - {formatShortDate(post.created_at)}
                        </small>
                      </span>
                    </Link>
                  ))
                ) : (
                  <p className="search-empty-line">Nenhuma publicação encontrada</p>
                )}
              </section>
            </>
          ) : (
            <p className="search-empty-state">{loading ? "Buscando..." : "Nada encontrado por enquanto."}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function AppShell({
  children,
  user,
  nextEvent,
  leaderboard,
  hideRightRail = false,
}: {
  children: ReactNode;
  user: UserProfile | null;
  nextEvent?: Event | null;
  leaderboard?: Leaderboard | null;
  hideRightRail?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [worldCupRanking, setWorldCupRanking] = useState<WorldCupLeaderboardEntry[]>([]);
  const [fetchedLeaderboard, setFetchedLeaderboard] = useState<Leaderboard | null>(null);
  const companyLeaderboard = leaderboard ?? fetchedLeaderboard;

  useEffect(() => {
    if (!user || leaderboard) return;
    let active = true;
    api
      .leaderboard()
      .then((response) => {
        if (active) setFetchedLeaderboard(response);
      })
      .catch(() => null);
    return () => {
      active = false;
    };
  }, [leaderboard, user]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    api
      .worldCupLeaderboard()
      .then((response) => {
        if (active) setWorldCupRanking(response.leaderboard);
      })
      .catch(() => null);
    return () => {
      active = false;
    };
  }, [user]);

  const logout = async () => {
    await api.logout().catch(() => null);
    clearSession();
    router.push("/");
  };

  const isActive = (href: string) => pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
  const eventFill = nextEvent ? Math.min(100, (nextEvent.confirmed_players / nextEvent.max_players) * 100) : 0;

  const bolaoRanking = useMemo(
    () => worldCupRanking.filter((entry) => entry.points > 0),
    [worldCupRanking],
  );

  const bolaoScorerRanking = useMemo(
    () =>
      [...worldCupRanking]
        .filter((entry) => entry.scorer_hits > 0)
        .sort((first, second) => second.scorer_hits - first.scorer_hits || second.points - first.points)
        .slice(0, 5),
    [worldCupRanking],
  );

  const topMarcadores = useMemo(
    () => (companyLeaderboard?.top_scorers ?? []).filter((player) => player.score > 0).slice(0, 10),
    [companyLeaderboard?.top_scorers],
  );

  return (
    <div className={hideRightRail ? "app-shell bolao-focus" : "app-shell"}>
      <header className="mobile-topbar">
        <Link href="/dashboard" aria-label="Fut Conversys — ir para o feed" className="brand-mark sidebar-brand-link compact">
          <BrandLogo compact />
        </Link>
        <GlobalSearch compact />
        {user && (
          <div className="mobile-user-actions">
            <Link href="/me" className="mobile-avatar-link" aria-label="Abrir meu perfil">
              <Avatar user={user} size="sm" />
            </Link>
            <button className="mobile-logout-button" onClick={logout} aria-label="Sair da conta">
              <LogOut size={17} />
            </button>
          </div>
        )}
      </header>

      <aside className="desktop-sidebar glass-panel">
        <Link href="/dashboard" aria-label="Fut Conversys — ir para o feed" className="brand-mark sidebar-brand-link">
          <BrandLogo />
        </Link>

        <GlobalSearch />

        <nav className="nav-stack">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                href={item.href}
                key={item.href}
                className={isActive(item.href) ? "nav-item active" : "nav-item"}
              >
                <Icon size={18} strokeWidth={2.2} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {user && (
          <div className="sidebar-profile">
            <Avatar user={user} />
            <div>
              <strong>{user.name}</strong>
              <small>{user.position || user.title || "Jogador Conversys"}</small>
              <Link className="sidebar-profile-edit" href="/me">
                <Pencil size={12} />
                <span>Editar perfil</span>
              </Link>
            </div>
          </div>
        )}

        <button className="btn-secondary" onClick={logout}>
          <LogOut size={16} />
          <span>Sair</span>
        </button>
      </aside>

      <main className="app-main">{children}</main>

      {!hideRightRail && (
        <aside className="right-rail">
          <section className="glass-panel rail-card rail-bolao-card rail-featured">
            <div className="rail-card-head">
              <span className="eyebrow">Bolão da Copa 2026</span>
              <Trophy size={18} />
            </div>
            <h3>Quem mais pontuou</h3>
            <p className="rail-card-desc">Placares certos, vencedor e campeão somam pontos.</p>
            {bolaoRanking.length > 0 ? (
              <>
                <div className="bolao-podium2">
                  {[bolaoRanking[1], bolaoRanking[0], bolaoRanking[2]].map((entry, column) => {
                    const place = column === 1 ? 1 : column === 0 ? 2 : 3;
                    if (!entry) return <span className="bolao-podium2-step empty" key={`empty-${column}`} />;
                    return (
                      <Link href={`/profile/${entry.user.id}`} className={`bolao-podium2-step place-${place}`} key={entry.user.id}>
                        {place === 1 && <span className="bolao-podium2-crown" aria-hidden="true">👑</span>}
                        <span className="bolao-podium2-avatar">
                          <Avatar user={entry.user} size={place === 1 ? "lg" : "md"} />
                          <span className={`bolao-podium2-medal m-${place}`}>{place}</span>
                        </span>
                        <span className="bolao-podium2-name">{entry.user.name.split(" ")[0]}</span>
                        <span className="bolao-podium2-pts">{entry.points}<i>pts</i></span>
                        <span className="bolao-podium2-sub">{entry.exact_scores} exatos · {entry.scorer_hits} ⚽</span>
                      </Link>
                    );
                  })}
                </div>
                {bolaoRanking.length > 3 && (
                  <div className="bolao-ranking-list">
                    {bolaoRanking.slice(3, 10).map((entry) => (
                      <Link href={`/profile/${entry.user.id}`} className="bolao-rank-row clickable" key={entry.user.id}>
                        <span className="bolao-rank-pos"><strong>{entry.rank}º</strong></span>
                        <Avatar user={entry.user} size="sm" />
                        <span className="bolao-rank-main">
                          <span className="bolao-rank-name"><span className="bolao-rank-fullname">{entry.user.name}</span></span>
                          <small>{entry.exact_scores} exatos · {entry.scorer_hits} artilheiros</small>
                        </span>
                        <b>{entry.points} <i>pts</i></b>
                        <ChevronRight className="bolao-rank-chevron" size={15} />
                      </Link>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="rail-empty-copy">Ninguém pontuou ainda. Crava teu palpite e lidera o bolão.</p>
            )}
            <Link href="/bolao" className="inline-link rail-bolao-cta">
              <span>Ir pro bolão</span>
              <ChevronRight size={16} />
            </Link>
          </section>

          {bolaoScorerRanking.length > 0 && (
            <section className="glass-panel rail-card rail-bolao-scorers-card">
              <div className="rail-card-head">
                <span className="eyebrow">Bolão</span>
                <Target size={18} />
              </div>
              <h3>Quem acertou mais artilheiros</h3>
              <p className="rail-card-desc">Palpite de quem marca gol no jogo da Copa.</p>
              <div className="mini-list">
                {bolaoScorerRanking.map((entry, index) => (
                  <Link href={`/profile/${entry.user.id}`} className="mini-player rail-scorer-row" key={entry.user.id}>
                    <strong className="rail-scorer-medal">{index < 3 ? ["🥇", "🥈", "🥉"][index] : `${index + 1}º`}</strong>
                    <Avatar user={entry.user} size="sm" />
                    <span>{entry.user.name}</span>
                    <strong className="rail-scorer-count">{entry.scorer_hits} ⚽</strong>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {nextEvent && (
            <section className="glass-panel rail-card rail-match-card">
              <div className="rail-card-head">
                <span className="eyebrow">Próxima pelada</span>
                <CalendarDays size={18} />
              </div>
              <h3>{nextEvent.title}</h3>
              <div className="rail-meta">
                <span>{formatEventDate(nextEvent.date)}</span>
                <span>{nextEvent.location}</span>
              </div>
              <div className="capacity-row">
                <strong>
                  {nextEvent.confirmed_players}/{nextEvent.max_players}
                </strong>
                <span>confirmados</span>
              </div>
              <div className="progress-track" aria-label="Lotação do evento">
                <span style={{ width: `${eventFill}%` }} />
              </div>
              <Link href={`/events/${nextEvent.id}`} className="inline-link">
                <span>Confirmar presença</span>
                <ChevronRight size={16} />
              </Link>
            </section>
          )}

          <section className="glass-panel rail-card rail-artilharia-card">
            <div className="rail-card-head">
              <span className="eyebrow">Peladas</span>
              <Goal size={18} />
            </div>
            <h3>Top artilheiros</h3>
            <p className="rail-card-desc">Quem mais marcou gol nas peladas da firma.</p>
            {topMarcadores.length > 0 ? (
              <div className="mini-list rail-rank-list">
                {topMarcadores.map((player, index) => (
                  <Link href={`/profile/${player.id}`} className="mini-player" key={player.id}>
                    <strong className="rail-rank-badge">{index + 1}º</strong>
                    <Avatar user={player} size="sm" />
                    <span>{player.name}</span>
                    <strong>{player.score} gols</strong>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="rail-empty-copy">Ninguém marcou gol nas peladas ainda.</p>
            )}
          </section>
        </aside>
      )}

      <nav className="mobile-nav glass-panel">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              href={item.href}
              key={item.href}
              className={isActive(item.href) ? "mobile-nav-item active" : "mobile-nav-item"}
            >
              <Icon size={19} strokeWidth={2.2} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
