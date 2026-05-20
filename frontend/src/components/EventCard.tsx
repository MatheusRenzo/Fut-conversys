"use client";

import Link from "next/link";
import { ArrowRight, CalendarDays, CheckCircle2, MapPin, UsersRound } from "lucide-react";
import type { Event } from "@/types";
import { formatEventDate } from "@/lib/format";
import { Avatar } from "./Avatar";

export function EventCard({
  event,
  onRSVP,
  compact = false,
}: {
  event: Event;
  onRSVP?: (eventId: number, status: "going" | "not_going") => void;
  compact?: boolean;
}) {
  const fill = Math.min(100, (event.confirmed_players / event.max_players) * 100);

  return (
    <article className={compact ? "event-card compact" : "event-card glass-panel"}>
      {event.cover_url && <img className="event-cover" src={event.cover_url} alt={event.title} />}
      <div className="event-content">
        <div className="event-meta">
          <span>{event.event_type}</span>
          <span>
            <CalendarDays size={14} />
            {formatEventDate(event.date)}
          </span>
        </div>
        <h3>{event.title}</h3>
        <p>{event.description}</p>
        <div className="event-location">
          <MapPin size={16} />
          <span>{event.location}</span>
        </div>
        <div className="event-footer">
          <span>
            <UsersRound size={16} />
            {event.confirmed_players}/{event.max_players} confirmados
          </span>
          <strong>
            {Math.round(fill)}%
          </strong>
        </div>
        <div className="progress-track" aria-label="Lotação do evento">
          <span style={{ width: `${fill}%` }} />
        </div>
        {event.attendees.length > 0 && (
          <div className="attendee-strip" aria-label="Jogadores confirmados">
            {event.attendees.slice(0, 5).map((attendee) => (
              <Avatar user={attendee} size="sm" key={attendee.id} />
            ))}
            {event.attendees.length > 5 && <span>+{event.attendees.length - 5}</span>}
          </div>
        )}
        <div className="action-row">
          <button
            className={event.user_has_rsvpd ? "btn-primary confirmed" : "btn-primary"}
            onClick={() => onRSVP?.(event.id, "going")}
          >
            {event.user_has_rsvpd && <CheckCircle2 size={17} />}
            <span>{event.user_has_rsvpd ? "Presença confirmada" : "Confirmar presença"}</span>
          </button>
          <Link href={`/events/${event.id}`} className="btn-secondary as-link">
            <span>Detalhes</span>
            <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </article>
  );
}
