"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, MapPin, XCircle } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { api } from "@/lib/api";
import { formatEventDate } from "@/lib/format";
import type { Event, Leaderboard, UserProfile } from "@/types";

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [event, setEvent] = useState<Event | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const id = Number(params.id);
        const [me, currentEvent, eventList, ranking] = await Promise.all([
          api.me(),
          api.event(id),
          api.events(),
          api.leaderboard(),
        ]);
        setProfile(me);
        setEvent(currentEvent);
        setEvents(eventList.events);
        setLeaderboard(ranking);
      } catch {
        router.push("/");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.id, router]);

  const handleRSVP = async (status: "going" | "not_going") => {
    if (!event) return;
    const updated = await api.rsvp(event.id, status);
    setEvent(updated);
  };

  if (loading || !event) return <div className="empty-state">Carregando evento...</div>;

  return (
    <AppShell user={profile} nextEvent={events[0] ?? event} leaderboard={leaderboard}>
      <article className="profile-hero glass-panel">
        <div
          className="profile-banner"
          style={{ backgroundImage: event.cover_url ? `url(${event.cover_url})` : undefined }}
        />
        <div className="rail-card">
          <span className="eyebrow">{event.event_type}</span>
          <h1>{event.title}</h1>
          <p>{event.description}</p>
          <div className="event-footer">
            <span>{formatEventDate(event.date)}</span>
            <span>{event.location}</span>
            <strong>
              {event.confirmed_players}/{event.max_players} confirmados
            </strong>
          </div>
          <div className="action-row">
            <button
              className={event.user_has_rsvpd ? "btn-primary confirmed" : "btn-primary"}
              onClick={() => handleRSVP("going")}
            >
              {event.user_has_rsvpd && <CheckCircle2 size={17} />}
              <span>{event.user_has_rsvpd ? "Presença confirmada" : "Confirmar presença"}</span>
            </button>
            <button className="btn-secondary" onClick={() => handleRSVP("not_going")}>
              <XCircle size={17} />
              <span>Não vou</span>
            </button>
          </div>
        </div>
      </article>

      <section className="content-card glass-panel">
        <span className="eyebrow">Escalação</span>
        <h2>Confirmados</h2>
        <p className="content-muted">
          <MapPin size={16} />
          {event.location}
        </p>
        <div className="mini-list">
          {event.attendees.map((attendee) => (
            <Link href={`/profile/${attendee.id}`} className="mini-player" key={attendee.id}>
              <Avatar user={attendee} />
              <span>{attendee.name}</span>
              <strong>{attendee.position}</strong>
            </Link>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
