"use client";

import { useState } from "react";
import { CalendarDays, Goal, ImagePlus, Send, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Event, Post, UserProfile } from "@/types";
import { Avatar } from "./Avatar";

export function PostComposer({
  events,
  onCreated,
  user,
}: {
  events: Event[];
  onCreated: (post: Post) => void;
  user: UserProfile | null;
}) {
  const [description, setDescription] = useState("");
  const [title, setTitle] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [matchId, setMatchId] = useState("");
  const [goalsScored, setGoalsScored] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!description.trim()) return;
    if (goalsScored > 0 && !matchId) {
      setError("Selecione o evento para enviar gols para aprovação.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const post = await api.createPost({
        title: title || undefined,
        description,
        image_url: imageUrl || undefined,
        match_id: matchId ? Number(matchId) : undefined,
        goals_scored: goalsScored,
      });
      setTitle("");
      setDescription("");
      setImageUrl("");
      setMatchId("");
      setGoalsScored(0);
      onCreated(post);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível publicar agora");
    } finally {
      setLoading(false);
    }
  };

  const firstName = user?.name.split(" ")[0] || "jogador";

  return (
    <form className="post-composer glass-panel" onSubmit={submit}>
      <div className="composer-head composer-social-head">
        <div className="composer-author">
          {user && <Avatar user={user} />}
          <div>
            <span>Publicar como</span>
            <strong>{user?.name || "Jogador Conversys"}</strong>
          </div>
        </div>
        <ShieldCheck size={20} />
      </div>

      <div className="composer-status-row">
        {user && <Avatar user={user} size="sm" />}
        <textarea
          className="composer-status-input"
          placeholder={`No que você está pensando, ${firstName}?`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>

      <div className="composer-title-row">
        <input
          className="input-field title-input"
          placeholder="Título opcional da resenha"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>

      <div className="quick-prompts" aria-label="Sugestões de publicação">
        {["Convocação", "Craque do jogo", "Churras confirmado"].map((item) => (
          <button
            key={item}
            onClick={() => setTitle((current) => current || item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>

      <div className="composer-attachment-panel">
        <div>
          <span className="eyebrow">Adicionar ao post</span>
          <p>Foto, evento e gols para validação.</p>
        </div>
        <label className="field-with-icon composer-action-field">
          <ImagePlus size={17} />
          <input
            className="input-field"
            placeholder="URL da foto ou GIF"
            value={imageUrl}
            onChange={(event) => setImageUrl(event.target.value)}
          />
        </label>
        <label className="field-with-icon composer-action-field">
          <CalendarDays size={17} />
          <select className="input-field" value={matchId} onChange={(event) => setMatchId(event.target.value)}>
            <option value="">Sem evento</option>
            {events.map((item) => (
              <option value={item.id} key={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field-with-icon composer-action-field">
          <Goal size={17} />
          <input
            className="input-field"
            min={0}
            max={20}
            placeholder="Gols para aprovação"
            type="number"
            value={goalsScored}
            onChange={(event) => setGoalsScored(Number(event.target.value))}
          />
        </label>
      </div>

      {error && <div className="error-box">{error}</div>}
      <div className="composer-submit-row">
        <p className="composer-note">
          Gols informados em evento ficam pendentes até aprovação do admin.
        </p>
        <button className="btn-primary" disabled={loading}>
          <Send size={17} />
          <span>{loading ? "Publicando..." : "Publicar"}</span>
        </button>
      </div>
    </form>
  );
}
