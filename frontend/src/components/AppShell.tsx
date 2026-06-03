"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CalendarDays,
  ChevronRight,
  FileText,
  Flame,
  Home,
  LoaderCircle,
  LogOut,
  Search,
  Trophy,
  UserRound,
} from "lucide-react";
import { api, clearSession } from "@/lib/api";
import type { Event, Leaderboard, SearchResults, UserProfile } from "@/types";
import { Avatar } from "./Avatar";
import { formatEventDate, formatShortDate } from "@/lib/format";

const navItems = [
  { href: "/dashboard", label: "Feed", icon: Home },
  { href: "/events", label: "Eventos", icon: CalendarDays },
  { href: "/me", label: "Meu perfil", icon: UserRound },
];

function SoccerBallMark() {
  return (
    <svg className="sidebar-brand-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="m12 7 3.8 2.8-1.45 4.45h-4.7L8.2 9.8 12 7Z" />
      <path d="m12 7 .55-3.9" />
      <path d="m15.8 9.8 3.75-1.25" />
      <path d="m14.35 14.25 2.35 3.25" />
      <path d="m9.65 14.25-2.35 3.25" />
      <path d="M8.2 9.8 4.45 8.55" />
    </svg>
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
}: {
  children: ReactNode;
  user: UserProfile | null;
  nextEvent?: Event | null;
  leaderboard?: Leaderboard | null;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const logout = async () => {
    await api.logout().catch(() => null);
    clearSession();
    router.push("/");
  };

  const isActive = (href: string) => pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
  const eventFill = nextEvent ? Math.min(100, (nextEvent.confirmed_players / nextEvent.max_players) * 100) : 0;

  return (
    <div className="app-shell">
      <header className="mobile-topbar">
        <Link href="/dashboard" className="brand-mark sidebar-brand-panel">
          <span className="sidebar-brand-copy">
            <span className="sidebar-brand-title">
              <SoccerBallMark />
              <strong>Fut Conversys</strong>
            </span>
          </span>
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
        <Link href="/dashboard" className="brand-mark sidebar-brand-panel app-brand-panel">
          <span className="sidebar-brand-copy">
            <span className="sidebar-brand-title">
              <SoccerBallMark />
              <strong>Fut Conversys</strong>
            </span>
          </span>
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

        <section className="sidebar-card">
          <span className="eyebrow">Clube interno</span>
          <strong>Temporada Conversys</strong>
          <p>Feed, presença, ranking e resenha em um só lugar.</p>
        </section>

        {user && (
          <div className="sidebar-profile">
            <Avatar user={user} />
            <div>
              <strong>{user.name}</strong>
              <small>{user.position || user.title || "Jogador Conversys"}</small>
            </div>
          </div>
        )}

        <button className="btn-secondary" onClick={logout}>
          <LogOut size={16} />
          <span>Sair</span>
        </button>
      </aside>

      <main className="app-main">{children}</main>

      <aside className="right-rail">
        {nextEvent && (
          <section className="glass-panel rail-card rail-match-card">
            <div className="rail-card-head">
              <span className="eyebrow">Próximo jogo</span>
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
              <span>Ver evento</span>
              <ChevronRight size={16} />
            </Link>
          </section>
        )}

        {leaderboard && (
          <section className="glass-panel rail-card">
            <div className="rail-card-head">
              <span className="eyebrow">Destaques</span>
              <Trophy size={18} />
            </div>
            <h3>Artilharia da firma</h3>
            <div className="mini-list">
              {leaderboard.top_scorers.slice(0, 3).map((player) => (
                <Link href={`/profile/${player.id}`} className="mini-player" key={player.id}>
                  <Avatar user={player} size="sm" />
                  <span>{player.name}</span>
                  <strong>{player.score}</strong>
                </Link>
              ))}
            </div>
          </section>
        )}

        {leaderboard && (
          <section className="glass-panel rail-card">
            <div className="rail-card-head">
              <span className="eyebrow">Resenha</span>
              <Flame size={18} />
            </div>
            <h3>Ranking do churras</h3>
            <div className="mini-list">
              {leaderboard.top_barbecue.slice(0, 3).map((player) => (
                <Link href={`/profile/${player.id}`} className="mini-player" key={player.id}>
                  <Avatar user={player} size="sm" />
                  <span>{player.name}</span>
                  <strong>{player.score}</strong>
                </Link>
              ))}
            </div>
          </section>
        )}
      </aside>

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
