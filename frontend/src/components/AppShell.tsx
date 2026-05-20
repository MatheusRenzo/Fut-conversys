"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import {
  CalendarDays,
  ChevronRight,
  Flame,
  Home,
  LogOut,
  Trophy,
  UserRound,
} from "lucide-react";
import { api, clearSession } from "@/lib/api";
import type { Event, Leaderboard, UserProfile } from "@/types";
import { Avatar } from "./Avatar";
import { formatEventDate } from "@/lib/format";

const navItems = [
  { href: "/dashboard", label: "Feed", icon: Home },
  { href: "/events", label: "Eventos", icon: CalendarDays },
  { href: "/me", label: "Meu perfil", icon: UserRound },
];

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
          <span className="brand-ball sidebar-brand-logo">
            <Image src="/icons/fut-conversys-logo.png" alt="" width={86} height={86} priority />
          </span>
          <span className="sidebar-brand-copy">
            <small>Clube interno</small>
            <strong>Fut Conversys</strong>
            <em>Pelada da firma</em>
          </span>
        </Link>
        {user && <Avatar user={user} size="sm" />}
      </header>

      <aside className="desktop-sidebar glass-panel">
        <Link href="/dashboard" className="brand-mark sidebar-brand-panel app-brand-panel">
          <span className="brand-ball sidebar-brand-logo">
            <Image src="/icons/fut-conversys-logo.png" alt="" width={86} height={86} priority />
          </span>
          <span className="sidebar-brand-copy">
            <small>Clube interno</small>
            <strong>Fut Conversys</strong>
            <em>Pelada da firma</em>
          </span>
        </Link>

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
