"use client";

import { useState } from "react";
import { CalendarDays, CalendarPlus, Goal, ImagePlus, Send, UsersRound, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Event, EventCreatePayload, Post, UserProfile } from "@/types";
import { Avatar } from "./Avatar";

type ComposerMode = "post" | "event";
type EventDraft = Omit<EventCreatePayload, "max_players"> & {
  max_players: string;
};

const emptyEventDraft = (): EventDraft => ({
  title: "",
  event_type: "pelada",
  location: "",
  date: "",
  description: "",
  max_players: "20",
  cover_url: "",
});

const allowedMediaTypes = new Set(["image/png", "image/jpeg", "image/gif"]);

export function PostComposer({
  events,
  isAdmin = false,
  onEventCreated,
  onCreated,
  user,
}: {
  events: Event[];
  isAdmin?: boolean;
  onEventCreated?: (event: Event) => void;
  onCreated: (post: Post) => void;
  user: UserProfile | null;
}) {
  const [mode, setMode] = useState<ComposerMode>("post");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [imageName, setImageName] = useState("");
  const [matchId, setMatchId] = useState("");
  const [goalsScored, setGoalsScored] = useState("");
  const [claimingGoals, setClaimingGoals] = useState(false);
  const [eventDraft, setEventDraft] = useState<EventDraft>(emptyEventDraft);
  const [eventCoverName, setEventCoverName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const readMediaFile = (
    file: File | undefined,
    onLoaded: (dataUrl: string, name: string) => void,
  ) => {
    if (!file) return;
    if (!allowedMediaTypes.has(file.type)) {
      setError("Selecione uma imagem PNG, JPG ou GIF.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      onLoaded(String(reader.result), file.name);
      setError("");
      setNotice("");
    };
    reader.readAsDataURL(file);
  };

  const selectPostMedia = (event: React.ChangeEvent<HTMLInputElement>) => {
    readMediaFile(event.target.files?.[0], (dataUrl, name) => {
      setImageUrl(dataUrl);
      setImageName(name);
    });
    event.target.value = "";
  };

  const selectEventCover = (event: React.ChangeEvent<HTMLInputElement>) => {
    readMediaFile(event.target.files?.[0], (dataUrl, name) => {
      setEventDraft((current) => ({ ...current, cover_url: dataUrl }));
      setEventCoverName(name);
    });
    event.target.value = "";
  };

  const updateEventDraft = <K extends keyof EventDraft>(field: K, value: EventDraft[K]) => {
    setEventDraft((current) => ({ ...current, [field]: value }));
    setError("");
    setNotice("");
  };

  const resetPost = () => {
    setDescription("");
    setImageUrl("");
    setImageName("");
    setMatchId("");
    setGoalsScored("");
    setClaimingGoals(false);
  };

  const resetEvent = () => {
    setEventDraft(emptyEventDraft());
    setEventCoverName("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();

    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (mode === "event") {
        if (!isAdmin) {
          setError("Apenas o admin pode cadastrar eventos.");
          return;
        }
        if (!eventDraft.title.trim() || !eventDraft.date || !eventDraft.location.trim()) {
          setError("Informe nome, data/hora e local do evento.");
          return;
        }

        const created = await api.createEvent({
          title: eventDraft.title.trim(),
          event_type: eventDraft.event_type.trim() || "pelada",
          location: eventDraft.location.trim(),
          date: new Date(eventDraft.date).toISOString(),
          description: eventDraft.description.trim() || eventDraft.title.trim(),
          max_players: Number(eventDraft.max_players) || 20,
          cover_url: eventDraft.cover_url || undefined,
        });

        onEventCreated?.(created);
        resetEvent();
        setMode("post");
        setNotice("Evento criado e publicado no calendário.");
        return;
      }

      if (!description.trim()) return;

      const claimedGoals = claimingGoals ? Math.max(0, Math.min(20, Number(goalsScored) || 0)) : 0;
      if (claimedGoals > 0 && !matchId) {
        setError("Selecione o evento onde esses gols aconteceram.");
        return;
      }

      const post = await api.createPost({
        description,
        image_url: imageUrl || undefined,
        match_id: claimingGoals && matchId ? Number(matchId) : undefined,
        goals_scored: claimedGoals,
      });
      resetPost();
      onCreated(post);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível concluir agora");
    } finally {
      setLoading(false);
    }
  };

  const firstName = user?.name.split(" ")[0] || "jogador";
  const eventCount = events.length;

  return (
    <form className="post-composer glass-panel" onSubmit={submit}>
      {mode === "post" && (
        <>
          <div className="composer-status-row">
            {user && <Avatar user={user} size="sm" />}
            <textarea
              className="composer-status-input"
              placeholder={`O que está pensando hoje, ${firstName}?`}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                setNotice("");
              }}
            />
          </div>

          {imageUrl && (
            <div className="composer-media-preview">
              <span
                aria-label="Prévia da mídia selecionada"
                className="composer-media-thumb"
                role="img"
                style={{ backgroundImage: `url(${imageUrl})` }}
              />
              <div>
                <strong>{imageName || "Mídia selecionada"}</strong>
                <span>PNG, JPG ou GIF anexado ao post</span>
              </div>
              <button
                aria-label="Remover mídia"
                onClick={() => {
                  setImageUrl("");
                  setImageName("");
                }}
                type="button"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <div className="composer-tools">
            <label className="composer-tool-button">
              <ImagePlus size={17} />
              <span>{imageUrl ? "Trocar mídia" : "Mídia"}</span>
              <input accept="image/png,image/jpeg,image/gif" onChange={selectPostMedia} type="file" />
            </label>
            <button
              className={claimingGoals ? "composer-tool-button active" : "composer-tool-button"}
              onClick={() => {
                setClaimingGoals((current) => !current);
                setNotice("");
              }}
              type="button"
            >
              <Goal size={17} />
              <span>Marquei gol</span>
            </button>
            {isAdmin && (
              <button className="composer-tool-button" onClick={() => setMode("event")} type="button">
                <CalendarPlus size={17} />
                <span>Criar evento</span>
              </button>
            )}
          </div>

          {claimingGoals && (
            <div className="composer-goal-row">
              <label>
                <span>Gols</span>
                <input
                  className="input-field"
                  min={0}
                  max={20}
                  placeholder="0"
                  type="number"
                  value={goalsScored}
                  onChange={(event) => setGoalsScored(event.target.value)}
                />
              </label>
              <label>
                <span>Evento</span>
                <select className="input-field" value={matchId} onChange={(event) => setMatchId(event.target.value)}>
                  <option value="">Onde aconteceu?</option>
                  {events.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
        </>
      )}

      {mode === "event" && isAdmin && (
        <div className="composer-event-shell">
          <div className="composer-event-grid">
            <input
              className="input-field"
              placeholder="Nome do evento"
              value={eventDraft.title}
              onChange={(event) => updateEventDraft("title", event.target.value)}
            />
            <label className="field-with-icon composer-action-field">
              <CalendarDays size={17} />
              <input
                className="input-field"
                type="datetime-local"
                value={eventDraft.date}
                onChange={(event) => updateEventDraft("date", event.target.value)}
              />
            </label>
            <input
              className="input-field"
              placeholder="Local"
              value={eventDraft.location}
              onChange={(event) => updateEventDraft("location", event.target.value)}
            />
            <label className="field-with-icon composer-action-field">
              <UsersRound size={17} />
              <input
                className="input-field"
                min={2}
                max={200}
                placeholder="Vagas"
                type="number"
                value={eventDraft.max_players}
                onChange={(event) => updateEventDraft("max_players", event.target.value)}
              />
            </label>
          </div>
          <textarea
            className="composer-status-input"
            placeholder="O que vai rolar nesse evento?"
            value={eventDraft.description}
            onChange={(event) => updateEventDraft("description", event.target.value)}
          />

          {eventDraft.cover_url && (
            <div className="composer-media-preview">
              <span
                aria-label="Prévia da imagem do evento"
                className="composer-media-thumb"
                role="img"
                style={{ backgroundImage: `url(${eventDraft.cover_url})` }}
              />
              <div>
                <strong>{eventCoverName || "Imagem do evento"}</strong>
                <span>Imagem usada como capa do evento</span>
              </div>
              <button
                aria-label="Remover imagem do evento"
                onClick={() => {
                  updateEventDraft("cover_url", "");
                  setEventCoverName("");
                }}
                type="button"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <div className="composer-tools">
            <label className="composer-tool-button">
              <ImagePlus size={17} />
              <span>{eventDraft.cover_url ? "Trocar imagem" : "Imagem"}</span>
              <input accept="image/png,image/jpeg,image/gif" onChange={selectEventCover} type="file" />
            </label>
            <button className="composer-tool-button" onClick={() => setMode("post")} type="button">
              <X size={17} />
              <span>Cancelar evento</span>
            </button>
          </div>
        </div>
      )}

      {error && <div className="error-box">{error}</div>}
      {notice && <div className="success-box">{notice}</div>}
      <div className="composer-submit-row">
        <p className="composer-note">
          {mode === "event"
            ? "Eventos criados aqui entram direto no calendário da firma."
            : claimingGoals
              ? "Gols informados ficam pendentes até aprovação do admin."
              : eventCount
                ? `${eventCount} evento${eventCount > 1 ? "s" : ""} no calendário da firma.`
                : "Publique uma atualização simples, com ou sem mídia."}
        </p>
        <button className="btn-primary" disabled={loading}>
          <Send size={17} />
          <span>{loading ? "Enviando..." : mode === "event" ? "Criar evento" : "Publicar"}</span>
        </button>
      </div>
    </form>
  );
}
