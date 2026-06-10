"use client";

import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { CalendarCheck2, CalendarPlus, CheckCircle2, Clock3, ListFilter, Save, Search, UsersRound, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { api } from "@/lib/api";
import type { Event, EventCreatePayload, Leaderboard, UserProfile } from "@/types";

type EventDraft = Omit<EventCreatePayload, "max_players"> & {
  max_players: string;
};

type EventStatusFilter = "all" | "open" | "confirmed" | "full" | "past";
type EventSort = "upcoming" | "popular" | "available";

const eventTypeLabels: Record<string, string> = {
  pelada: "Pelada",
  torneio: "Torneio",
  churras: "Churras",
  treino: "Treino",
};

const statusFilters: Array<{
  value: EventStatusFilter;
  label: string;
}> = [
  { value: "all", label: "Todos" },
  { value: "open", label: "Com vaga" },
  { value: "confirmed", label: "Confirmados" },
  { value: "full", label: "Lotados" },
  { value: "past", label: "Encerrados" },
];

const sortOptions: Array<{
  value: EventSort;
  label: string;
}> = [
  { value: "upcoming", label: "Mais próximos" },
  { value: "popular", label: "Mais confirmados" },
  { value: "available", label: "Mais vagas" },
];

function emptyEventDraft(): EventDraft {
  return {
    title: "",
    event_type: "pelada",
    location: "",
    date: "",
    description: "",
    max_players: "20",
    cover_url: "",
  };
}

function toDatetimeLocal(iso: string) {
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function draftFromEvent(event: Event): EventDraft {
  return {
    title: event.title,
    event_type: event.event_type || "pelada",
    location: event.location,
    date: toDatetimeLocal(event.date),
    description: event.description,
    max_players: String(event.max_players),
    cover_url: event.cover_url ?? "",
  };
}

function normalizeType(value: string) {
  return value.trim().toLowerCase();
}

function eventTypeLabel(value: string) {
  const normalized = normalizeType(value);
  return eventTypeLabels[normalized] ?? normalized.replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function availableSpots(event: Event) {
  return Math.max(0, event.max_players - event.confirmed_players);
}

export default function EventsPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<EventStatusFilter>("all");
  const [sortBy, setSortBy] = useState<EventSort>("upcoming");
  const [currentTime, setCurrentTime] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingEventId, setEditingEventId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Event | null>(null);
  const [savingEvent, setSavingEvent] = useState(false);
  const [deletingEvent, setDeletingEvent] = useState(false);
  const [eventDraft, setEventDraft] = useState<EventDraft>(emptyEventDraft);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [me, eventList, ranking] = await Promise.all([
          api.me(),
          api.events(),
          api.leaderboard(),
        ]);
        setProfile(me);
        setEvents(eventList.events);
        setLeaderboard(ranking);
      } catch {
        router.push("/");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [router]);

  useEffect(() => {
    const updateTime = () => setCurrentTime(Date.now());
    updateTime();
    const timer = window.setInterval(updateTime, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const handleRSVP = async (eventId: number, status: "going" | "not_going") => {
    const updated = await api.rsvp(eventId, status);
    setEvents((current) => current.map((event) => (event.id === eventId ? updated : event)));
  };

  const updateDraft = <K extends keyof EventDraft>(field: K, value: EventDraft[K]) => {
    setEventDraft((current) => ({ ...current, [field]: value }));
    setFormError("");
  };

  // Redimensiona a foto escolhida (máx. 1600px) e guarda como data URL
  const selectCoverImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const rawUrl = String(reader.result);
      const image = new Image();
      image.onload = () => {
        const scale = Math.min(1, 1600 / image.width);
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(image.width * scale);
        canvas.height = Math.round(image.height * scale);
        const context = canvas.getContext("2d");
        if (!context) {
          updateDraft("cover_url", rawUrl);
          return;
        }
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        updateDraft("cover_url", canvas.toDataURL("image/jpeg", 0.85));
      };
      image.onerror = () => updateDraft("cover_url", rawUrl);
      image.src = rawUrl;
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  };

  const closeEventModal = () => {
    setCreateOpen(false);
    setEditingEventId(null);
    setFormError("");
    setEventDraft(emptyEventDraft());
  };

  const openCreateModal = () => {
    setEditingEventId(null);
    setEventDraft(emptyEventDraft());
    setFormError("");
    setCreateOpen(true);
  };

  const openEditModal = (event: Event) => {
    setEditingEventId(event.id);
    setEventDraft(draftFromEvent(event));
    setFormError("");
    setCreateOpen(true);
  };

  const openDeleteConfirm = (event: Event) => {
    setDeleteTarget(event);
    setFormError("");
  };

  const closeDeleteConfirm = () => {
    setDeleteTarget(null);
  };

  const buildEventPayload = (): EventCreatePayload => ({
    title: eventDraft.title.trim(),
    event_type: eventDraft.event_type.trim(),
    location: eventDraft.location.trim(),
    date: new Date(eventDraft.date).toISOString(),
    description: eventDraft.description.trim(),
    max_players: Number(eventDraft.max_players) || 20,
    cover_url: eventDraft.cover_url?.trim() || null,
  });

  const handleSaveEvent = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSavingEvent(true);
    setFormError("");

    try {
      const payload = buildEventPayload();

      if (editingEventId) {
        const updated = await api.updateEvent(editingEventId, payload);
        setEvents((current) =>
          current
            .map((item) => (item.id === editingEventId ? updated : item))
            .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()),
        );
      } else {
        const created = await api.createEvent(payload);
        setEvents((current) =>
          [...current, created].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()),
        );
      }

      closeEventModal();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Não foi possível salvar o evento");
    } finally {
      setSavingEvent(false);
    }
  };

  const handleDeleteEvent = async () => {
    if (!deleteTarget) return;

    setDeletingEvent(true);
    setFormError("");

    try {
      await api.deleteEvent(deleteTarget.id);
      setEvents((current) => current.filter((item) => item.id !== deleteTarget.id));
      setDeleteTarget(null);
      if (editingEventId === deleteTarget.id) {
        closeEventModal();
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Não foi possível excluir o evento");
    } finally {
      setDeletingEvent(false);
    }
  };

  const isAdmin = Boolean(profile?.is_admin);
  const isEditing = editingEventId !== null;
  const now = currentTime;
  const normalizedQuery = query.trim().toLowerCase();

  const typeOptions = useMemo(() => {
    const counts = events.reduce<Record<string, number>>((acc, event) => {
      const type = normalizeType(event.event_type || "pelada");
      acc[type] = (acc[type] ?? 0) + 1;
      return acc;
    }, {});

    return Object.entries(counts)
      .sort(([first], [second]) => eventTypeLabel(first).localeCompare(eventTypeLabel(second), "pt-BR"))
      .map(([value, count]) => ({ value, label: eventTypeLabel(value), count }));
  }, [events]);

  const eventSummary = useMemo(() => {
    const upcoming = events.filter((event) => new Date(event.date).getTime() >= now);
    return {
      total: events.length,
      upcoming: upcoming.length,
      confirmedByUser: events.filter((event) => event.user_has_rsvpd).length,
      available: upcoming.reduce((sum, event) => sum + availableSpots(event), 0),
    };
  }, [events, now]);

  const filteredEvents = useMemo(() => {
    return events
      .filter((event) => {
        const eventDate = new Date(event.date).getTime();
        const isPast = eventDate < now;
        const isFull = availableSpots(event) === 0;

        if (typeFilter !== "all" && normalizeType(event.event_type || "pelada") !== typeFilter) return false;
        if (statusFilter === "open" && (isPast || isFull)) return false;
        if (statusFilter === "confirmed" && !event.user_has_rsvpd) return false;
        if (statusFilter === "full" && !isFull) return false;
        if (statusFilter === "past" && !isPast) return false;

        if (!normalizedQuery) return true;
        const searchable = `${event.title} ${event.location} ${event.description} ${eventTypeLabel(event.event_type)}`.toLowerCase();
        return searchable.includes(normalizedQuery);
      })
      .sort((first, second) => {
        if (sortBy === "popular") return second.confirmed_players - first.confirmed_players;
        if (sortBy === "available") return availableSpots(second) - availableSpots(first);
        return new Date(first.date).getTime() - new Date(second.date).getTime();
      });
  }, [events, normalizedQuery, now, sortBy, statusFilter, typeFilter]);

  const activeFilterCount = [
    normalizedQuery,
    typeFilter !== "all" ? typeFilter : "",
    statusFilter !== "all" ? statusFilter : "",
    sortBy !== "upcoming" ? sortBy : "",
  ].filter(Boolean).length;

  const clearFilters = () => {
    setQuery("");
    setTypeFilter("all");
    setStatusFilter("all");
    setSortBy("upcoming");
  };

  if (loading) return <div className="empty-state">Carregando cronograma...</div>;

  return (
    <AppShell user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <section className="section-heading">
        <div>
          <span className="eyebrow">Cronograma</span>
          <h1>Próximos eventos</h1>
          <p>Pelada, torneio, churrasco e os encontros que viram história no feed.</p>
        </div>
        <div className="heading-actions">
          {isAdmin && (
            <button className="btn-primary" onClick={openCreateModal} type="button">
              <CalendarPlus size={17} />
              <span>Cadastrar evento</span>
            </button>
          )}
        </div>
      </section>

      <section className="event-filter-panel glass-panel" aria-label="Filtros de eventos">
        <div className="event-filter-head">
          <div>
            <span className="eyebrow">Filtros</span>
            <h2>Encontre o próximo jogo</h2>
          </div>
          <div className="event-filter-count">
            <ListFilter size={16} />
            <span>
              {filteredEvents.length}/{eventSummary.total} eventos
            </span>
          </div>
        </div>

        <div className="event-filter-search">
          <Search size={18} />
          <input
            aria-label="Buscar eventos"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por nome, local ou tipo"
            value={query}
          />
        </div>

        <div className="event-filter-metrics" aria-label="Resumo do cronograma">
          <div>
            <CalendarCheck2 size={16} />
            <strong>{eventSummary.upcoming}</strong>
            <span>próximos</span>
          </div>
          <div>
            <CheckCircle2 size={16} />
            <strong>{eventSummary.confirmedByUser}</strong>
            <span>confirmados</span>
          </div>
          <div>
            <UsersRound size={16} />
            <strong>{eventSummary.available}</strong>
            <span>vagas abertas</span>
          </div>
        </div>

        <div className="filter-group">
          <span>Tipo</span>
          <div className="filter-chip-row">
            <button
              className={typeFilter === "all" ? "filter-chip active" : "filter-chip"}
              onClick={() => setTypeFilter("all")}
              type="button"
            >
              Todos
              <small>{events.length}</small>
            </button>
            {typeOptions.map((option) => (
              <button
                className={typeFilter === option.value ? "filter-chip active" : "filter-chip"}
                key={option.value}
                onClick={() => setTypeFilter(option.value)}
                type="button"
              >
                {option.label}
                <small>{option.count}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="event-filter-bottom">
          <div className="filter-group">
            <span>Status</span>
            <div className="segmented-control event-status-tabs" aria-label="Status do evento">
              {statusFilters.map((option) => (
                <button
                  className={statusFilter === option.value ? "active" : ""}
                  key={option.value}
                  onClick={() => setStatusFilter(option.value)}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <label className="event-sort-select">
            <span>Ordenar</span>
            <select className="input-field" onChange={(event) => setSortBy(event.target.value as EventSort)} value={sortBy}>
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {activeFilterCount > 0 && (
          <button className="clear-event-filters" onClick={clearFilters} type="button">
            <X size={15} />
            <span>Limpar filtros</span>
          </button>
        )}
      </section>

      <section className="events-grid">
        {filteredEvents.map((event) => (
          <EventCard
            event={event}
            isAdmin={isAdmin}
            key={event.id}
            onDelete={openDeleteConfirm}
            onEdit={openEditModal}
            onRSVP={handleRSVP}
          />
        ))}
      </section>

      {filteredEvents.length === 0 && (
        <section className="empty-state event-empty-state">
          <Clock3 size={22} />
          <strong>Nenhum evento encontrado</strong>
          <span>Ajuste os filtros ou busque por outro local, tipo ou nome.</span>
        </section>
      )}

      {isAdmin && createOpen && (
        <div className="event-modal-backdrop" onClick={closeEventModal}>
          <section
            aria-modal="true"
            className="event-modal glass-panel"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-head">
              <div>
                <span className="eyebrow">Admin</span>
                <h2>{isEditing ? "Editar evento" : "Cadastrar evento"}</h2>
                <p>
                  {isEditing
                    ? "Atualize as informações do evento no cronograma."
                    : "Crie uma nova partida ou encontro para aparecer no cronograma do app."}
                </p>
              </div>
              <button aria-label="Fechar modal" className="modal-close" onClick={closeEventModal} type="button">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveEvent}>
              <div className="modal-field">
                <label htmlFor="event-title">Nome do evento</label>
                <input
                  className="input-field"
                  id="event-title"
                  onChange={(event) => updateDraft("title", event.target.value)}
                  required
                  value={eventDraft.title}
                />
              </div>

              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="event-type">Tipo</label>
                  <select
                    className="input-field"
                    id="event-type"
                    onChange={(event) => updateDraft("event_type", event.target.value)}
                    value={eventDraft.event_type}
                  >
                    <option value="pelada">Pelada</option>
                    <option value="torneio">Torneio</option>
                    <option value="churras">Churras</option>
                    <option value="treino">Treino</option>
                  </select>
                </div>
                <div className="modal-field">
                  <label htmlFor="event-date">Data e hora</label>
                  <input
                    className="input-field"
                    id="event-date"
                    onChange={(event) => updateDraft("date", event.target.value)}
                    required
                    type="datetime-local"
                    value={eventDraft.date}
                  />
                </div>
              </div>

              <div className="modal-grid">
                <div className="modal-field">
                  <label htmlFor="event-location">Local</label>
                  <input
                    className="input-field"
                    id="event-location"
                    onChange={(event) => updateDraft("location", event.target.value)}
                    required
                    value={eventDraft.location}
                  />
                </div>
                <div className="modal-field">
                  <label htmlFor="event-max">Máximo de jogadores</label>
                  <input
                    className="input-field"
                    id="event-max"
                    min={2}
                    onChange={(event) => updateDraft("max_players", event.target.value)}
                    required
                    type="number"
                    value={eventDraft.max_players}
                  />
                </div>
              </div>

              <div className="modal-field">
                <label>Foto de capa</label>
                <label className="media-picker event-cover-picker">
                  <div
                    className="media-preview event-cover-preview"
                    style={{ backgroundImage: eventDraft.cover_url ? `url(${eventDraft.cover_url})` : undefined }}
                  >
                    {!eventDraft.cover_url && <span>Nenhuma foto escolhida</span>}
                  </div>
                  <strong>{eventDraft.cover_url ? "Trocar foto" : "Escolher foto"}</strong>
                  <input accept="image/*" className="file-input" onChange={selectCoverImage} type="file" />
                </label>
                {eventDraft.cover_url && (
                  <button className="event-cover-remove" onClick={() => updateDraft("cover_url", "")} type="button">
                    <X size={14} />
                    <span>Remover foto</span>
                  </button>
                )}
              </div>

              <div className="modal-field">
                <label htmlFor="event-description">Descrição</label>
                <textarea
                  className="input-field"
                  id="event-description"
                  onChange={(event) => updateDraft("description", event.target.value)}
                  required
                  value={eventDraft.description}
                />
              </div>

              {formError && <div className="error-box">{formError}</div>}

              <div className="action-row">
                <button className="btn-primary" disabled={savingEvent}>
                  <Save size={17} />
                  <span>{savingEvent ? "Salvando..." : isEditing ? "Salvar alterações" : "Salvar evento"}</span>
                </button>
                <button className="btn-secondary" onClick={closeEventModal} type="button">
                  Cancelar
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {isAdmin && deleteTarget && (
        <div className="event-modal-backdrop" onClick={closeDeleteConfirm}>
          <section
            aria-modal="true"
            className="event-modal glass-panel event-delete-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-head">
              <div>
                <span className="eyebrow">Admin</span>
                <h2>Excluir evento</h2>
                <p>
                  Tem certeza que deseja excluir <strong>{deleteTarget.title}</strong>? Os RSVPs serão removidos e
                  posts vinculados ficarão sem evento.
                </p>
              </div>
              <button aria-label="Fechar modal" className="modal-close" onClick={closeDeleteConfirm} type="button">
                <X size={18} />
              </button>
            </div>

            {formError && <div className="error-box">{formError}</div>}

            <div className="action-row">
              <button className="btn-danger" disabled={deletingEvent} onClick={handleDeleteEvent} type="button">
                <span>{deletingEvent ? "Excluindo..." : "Excluir evento"}</span>
              </button>
              <button className="btn-secondary" disabled={deletingEvent} onClick={closeDeleteConfirm} type="button">
                Cancelar
              </button>
            </div>
          </section>
        </div>
      )}
    </AppShell>
  );
}
