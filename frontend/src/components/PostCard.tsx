"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  BadgeCheck,
  Beer,
  Bookmark,
  Camera,
  Check,
  CircleCheck,
  CircleX,
  Clock3,
  FileImage,
  Heart,
  ImagePlus,
  Megaphone,
  MessageCircle,
  MessagesSquare,
  Reply,
  Send,
  ShieldAlert,
  Trophy,
  Utensils,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatShortDate } from "@/lib/format";
import type { Comment, GoalStatus, Post, ReactionType } from "@/types";
import { Avatar } from "./Avatar";

const reactionOptions: Array<{
  type: ReactionType;
  label: string;
  description: string;
  icon: typeof Heart;
  accent: string;
}> = [
  { type: "torcida", label: "Torcida", description: "apoio da arquibancada", icon: Megaphone, accent: "#61a229" },
  { type: "golaco", label: "Golaço", description: "jogada ou gol bonito", icon: Trophy, accent: "#00cfb4" },
  { type: "resenha", label: "Resenha", description: "comentário que rende", icon: MessagesSquare, accent: "#00cfb4" },
  { type: "midia", label: "Mídia", description: "foto, vídeo ou GIF", icon: Camera, accent: "#005aff" },
  { type: "churras", label: "Churras", description: "presença no pós-jogo", icon: Utensils, accent: "#61a229" },
  { type: "bebedeira", label: "Bebedeira", description: "caos bom da firma", icon: Beer, accent: "#e31c79" },
];

function reactionStyle(accent: string) {
  return { "--reaction-color": accent } as CSSProperties;
}

const goalStatusCopy: Record<GoalStatus, { label: string; detail: string; className: string; icon: typeof Clock3 }> = {
  none: { label: "Sem gols", detail: "nenhuma solicitação", className: "neutral", icon: ShieldAlert },
  pending: { label: "Aguardando admin", detail: "não conta no ranking ainda", className: "pending", icon: Clock3 },
  approved: { label: "Gol aprovado", detail: "já vale ponto", className: "approved", icon: CircleCheck },
  rejected: { label: "Gol recusado", detail: "não vale ponto", className: "rejected", icon: CircleX },
};

export function PostCard({
  post,
  onChange,
  onGoalReviewed,
}: {
  post: Post;
  onChange: (post: Post) => void;
  onGoalReviewed?: (post: Post) => void;
}) {
  const [comment, setComment] = useState("");
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [mediaType, setMediaType] = useState<"" | "image" | "gif">("");
  const [mediaUrl, setMediaUrl] = useState("");
  const [commentReactions, setCommentReactions] = useState<Record<number, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [reactionLoading, setReactionLoading] = useState<ReactionType | null>(null);
  const [goalReviewLoading, setGoalReviewLoading] = useState<"approved" | "rejected" | null>(null);
  const [reactionTrayOpen, setReactionTrayOpen] = useState(false);
  const [burstReaction, setBurstReaction] = useState<ReactionType | null>(null);
  const [showAllComments, setShowAllComments] = useState(false);
  const [saved, setSaved] = useState(false);
  const commentInputRef = useRef<HTMLInputElement | null>(null);
  const reactionZoneRef = useRef<HTMLDivElement | null>(null);
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTrayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const burstTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ignoreClickRef = useRef(false);

  useEffect(() => {
    return () => {
      if (holdTimerRef.current) clearTimeout(holdTimerRef.current);
      if (closeTrayTimerRef.current) clearTimeout(closeTrayTimerRef.current);
      if (burstTimerRef.current) clearTimeout(burstTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!reactionTrayOpen) return;

    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && reactionZoneRef.current?.contains(target)) return;
      setReactionTrayOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setReactionTrayOpen(false);
    };

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [reactionTrayOpen]);

  useEffect(() => {
    if (!reactionTrayOpen) return;

    const closeOnOutsideMove = (event: PointerEvent | MouseEvent) => {
      if ("pointerType" in event && event.pointerType !== "mouse") return;

      const zone = reactionZoneRef.current;
      const tray = zone?.querySelector<HTMLElement>(".reaction-tray");
      if (!zone || !tray) return;

      const zoneRect = zone.getBoundingClientRect();
      const trayRect = tray.getBoundingClientRect();
      const x = event.clientX;
      const y = event.clientY;
      const buffer = 10;
      const insideZone =
        x >= zoneRect.left - buffer &&
        x <= zoneRect.right + buffer &&
        y >= zoneRect.top - buffer &&
        y <= zoneRect.bottom + buffer;
      const insideTray =
        x >= trayRect.left - buffer &&
        x <= trayRect.right + buffer &&
        y >= trayRect.top - buffer &&
        y <= trayRect.bottom + buffer;
      const insideBridge =
        x >= Math.min(zoneRect.left, trayRect.left) - buffer &&
        x <= Math.max(zoneRect.right, trayRect.right) + buffer &&
        y >= trayRect.bottom - buffer &&
        y <= zoneRect.top + buffer;

      if (insideZone || insideTray || insideBridge) {
        if (closeTrayTimerRef.current) clearTimeout(closeTrayTimerRef.current);
        return;
      }

      if (closeTrayTimerRef.current) clearTimeout(closeTrayTimerRef.current);
      closeTrayTimerRef.current = setTimeout(() => setReactionTrayOpen(false), 130);
    };

    document.addEventListener("pointermove", closeOnOutsideMove);
    document.addEventListener("mousemove", closeOnOutsideMove);
    return () => {
      document.removeEventListener("pointermove", closeOnOutsideMove);
      document.removeEventListener("mousemove", closeOnOutsideMove);
    };
  }, [reactionTrayOpen]);

  const topLevelComments = useMemo(
    () => post.comments.filter((item) => !item.parent_id),
    [post.comments],
  );

  const repliesByParent = useMemo(() => {
    return post.comments.reduce<Record<number, Comment[]>>((acc, item) => {
      if (item.parent_id) {
        acc[item.parent_id] = [...(acc[item.parent_id] ?? []), item];
      }
      return acc;
    }, {});
  }, [post.comments]);

  const reactionCounts = useMemo(() => {
    return reactionOptions.reduce<Record<ReactionType, number>>((acc, reaction) => {
      acc[reaction.type] = post.reactions?.[reaction.type] ?? 0;
      return acc;
    }, {} as Record<ReactionType, number>);
  }, [post.reactions]);

  const viewerReaction = post.viewer_reaction ?? (post.liked_by_user ? "torcida" : null);
  const selectedReaction = reactionOptions.find((reaction) => reaction.type === viewerReaction) ?? reactionOptions[0];
  const goalStatus = post.goal_status ?? "none";
  const goalCopy = goalStatusCopy[goalStatus];
  const GoalStatusIcon = goalCopy.icon;
  const claimedGoals = post.goals_scored ?? 0;
  const totalReactions = reactionOptions.reduce((total, reaction) => total + reactionCounts[reaction.type], 0);
  const topReactions = [...reactionOptions]
    .filter((reaction) => reactionCounts[reaction.type] > 0)
    .sort((a, b) => reactionCounts[b.type] - reactionCounts[a.type])
    .slice(0, 3);
  const highlightedReactions = topReactions.length > 0 ? topReactions : [selectedReaction];
  const visibleComments = showAllComments ? topLevelComments : topLevelComments.slice(-2);
  const hiddenComments = Math.max(0, topLevelComments.length - visibleComments.length);
  const reactionSummaryText = viewerReaction
    ? totalReactions > 1
      ? `Você e mais ${totalReactions - 1}`
      : "Você"
    : totalReactions === 1
      ? "1 reação"
      : `${totalReactions} reações`;
  const commentSummaryText = post.comments_count === 1 ? "1 comentário" : `${post.comments_count} comentários`;
  const showEngagementLine = totalReactions > 0 || post.comments_count > 0;
  const authorVerified = post.author.verified_enabled && post.author.show_verified_badge !== false;

  const showReactionBurst = (reactionType: ReactionType) => {
    setBurstReaction(reactionType);
    if (burstTimerRef.current) clearTimeout(burstTimerRef.current);
    burstTimerRef.current = setTimeout(() => setBurstReaction(null), 760);
  };

  const selectReaction = async (reactionType: ReactionType) => {
    if (reactionLoading) return;
    setReactionLoading(reactionType);
    try {
      const result = await api.toggleReaction(post.id, reactionType);
      onChange(result.post);
      setReactionTrayOpen(false);
      showReactionBurst(reactionType);
    } finally {
      setReactionLoading(null);
    }
  };

  const reviewGoals = async (status: "approved" | "rejected") => {
    setGoalReviewLoading(status);
    try {
      const updated = await api.reviewPostGoals(post.id, status);
      onChange(updated);
      onGoalReviewed?.(updated);
    } finally {
      setGoalReviewLoading(null);
    }
  };

  const boostGolaco = () => {
    if (viewerReaction === "golaco") {
      showReactionBurst("golaco");
      return;
    }
    void selectReaction("golaco");
  };

  const startReactionHold = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "mouse") return;
    ignoreClickRef.current = false;
    if (holdTimerRef.current) clearTimeout(holdTimerRef.current);
    holdTimerRef.current = setTimeout(() => {
      ignoreClickRef.current = true;
      setReactionTrayOpen(true);
    }, 360);
  };

  const cancelReactionHold = () => {
    if (holdTimerRef.current) {
      clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  const openReactionTray = () => {
    if (closeTrayTimerRef.current) clearTimeout(closeTrayTimerRef.current);
    setReactionTrayOpen(true);
  };

  const closeReactionTraySoon = () => {
    if (closeTrayTimerRef.current) clearTimeout(closeTrayTimerRef.current);
    closeTrayTimerRef.current = setTimeout(() => setReactionTrayOpen(false), 130);
  };

  const handleReactionTriggerClick = () => {
    if (ignoreClickRef.current) {
      ignoreClickRef.current = false;
      return;
    }
    openReactionTray();
  };

  const submitComment = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedComment = comment.trim();
    const trimmedMediaUrl = mediaUrl.trim();
    const fallbackText =
      mediaType === "image" ? "Compartilhou uma foto da resenha" : "Compartilhou um GIF da jogada";

    if (!trimmedComment && !trimmedMediaUrl) return;

    setLoading(true);
    try {
      const updated = await api.addComment(post.id, {
        text: trimmedComment || fallbackText,
        parent_id: replyTo?.id,
        media_url: trimmedMediaUrl || undefined,
        media_type: mediaType || undefined,
      });
      setComment("");
      setReplyTo(null);
      setMediaType("");
      setMediaUrl("");
      setShowAllComments(true);
      onChange(updated);
    } finally {
      setLoading(false);
    }
  };

  const BurstIcon = burstReaction
    ? reactionOptions.find((reaction) => reaction.type === burstReaction)?.icon
    : null;
  const burstAccent = burstReaction
    ? reactionOptions.find((reaction) => reaction.type === burstReaction)?.accent ?? selectedReaction.accent
    : selectedReaction.accent;
  const SelectedIcon = selectedReaction.icon;

  return (
    <article className="post-card social-post glass-panel" id={`post-${post.id}`}>
      <header className="post-header social-post-header">
        <div className="post-author">
          <Link className="post-avatar-link" href={`/profile/${post.author.id}`}>
            <span className="post-avatar-wrap">
              <Avatar user={post.author} />
              {authorVerified && (
                <span aria-label="Perfil verificado" className="profile-verified-mark post-verified-mark" title="Perfil verificado">
                  <BadgeCheck size={13} />
                </span>
              )}
            </span>
          </Link>
          <div className="post-author-copy">
            <div className="post-author-row">
              <Link href={`/profile/${post.author.id}`} className="profile-link">
                {post.author.name}
              </Link>
            </div>
            <p>{post.author.title || post.author.position || "Jogador Conversys"}</p>
          </div>
        </div>
        <time dateTime={post.created_at}>{formatShortDate(post.created_at)}</time>
      </header>

      <div className="social-post-copy">
        {post.title && <h3>{post.title}</h3>}
        {post.description && <p className="post-description">{post.description}</p>}
      </div>

      {post.image_url && (
        <button
          className="post-media-wrap"
          onDoubleClick={boostGolaco}
          title="Dois cliques para reagir com Golaço"
          type="button"
        >
          <img className="post-image" src={post.image_url} alt={post.title || "Post"} />
          {BurstIcon && burstReaction && (
            <span className="reaction-burst" style={reactionStyle(burstAccent)}>
              <BurstIcon aria-hidden size={96} strokeWidth={1.9} />
            </span>
          )}
        </button>
      )}

      <div className="post-context-row">
        {post.match && (
          <Link href={`/events/${post.match.id}`} className="event-pill">
            {post.match.title}
          </Link>
        )}

        {Boolean(claimedGoals) && (
          <div className={`post-match-stat goal-status-${goalCopy.className}`}>
            <GoalStatusIcon size={16} />
            <strong>{claimedGoals}</strong>
            <span>{claimedGoals === 1 ? "gol solicitado" : "gols solicitados"}</span>
            <em>{goalCopy.label}</em>
          </div>
        )}
      </div>

      {Boolean(claimedGoals) && (
        <div className={`goal-review-card ${goalCopy.className}`}>
          <div>
            <strong>{goalCopy.label}</strong>
            <span>{goalCopy.detail}</span>
          </div>
          {post.can_review_goals && (
            <div className="goal-review-actions">
              <button
                className="goal-review-button approve"
                disabled={Boolean(goalReviewLoading)}
                onClick={() => reviewGoals("approved")}
                type="button"
              >
                <Check size={15} />
                <span>{goalReviewLoading === "approved" ? "Aprovando..." : "Aprovar"}</span>
              </button>
              <button
                className="goal-review-button reject"
                disabled={Boolean(goalReviewLoading)}
                onClick={() => reviewGoals("rejected")}
                type="button"
              >
                <X size={15} />
                <span>{goalReviewLoading === "rejected" ? "Recusando..." : "Recusar"}</span>
              </button>
            </div>
          )}
        </div>
      )}

      {showEngagementLine && (
        <div className="post-engagement-line">
          <div className="reaction-summary" aria-label={`${totalReactions} reações`}>
            {totalReactions > 0 && (
              <div className="reaction-stack" aria-hidden>
                {highlightedReactions.map((reaction) => {
                  const Icon = reaction.icon;
                  return (
                    <span key={reaction.type} style={reactionStyle(reaction.accent)}>
                      <Icon size={13} strokeWidth={2.2} />
                    </span>
                  );
                })}
              </div>
            )}
            {totalReactions > 0 && <span className="reaction-summary-text">{reactionSummaryText}</span>}
          </div>
          {post.comments_count > 0 && (
            <button className="comment-count-button" onClick={() => commentInputRef.current?.focus()} type="button">
              {commentSummaryText}
            </button>
          )}
        </div>
      )}

      <div className="post-social-actions">
        <div
          className={reactionTrayOpen ? "reaction-hold-zone open" : "reaction-hold-zone"}
          ref={reactionZoneRef}
          onMouseEnter={openReactionTray}
          onMouseLeave={closeReactionTraySoon}
        >
          <button
            aria-expanded={reactionTrayOpen}
            className={viewerReaction ? "social-action reaction-trigger selected" : "social-action reaction-trigger"}
            disabled={Boolean(reactionLoading)}
            onClick={handleReactionTriggerClick}
            onContextMenu={(event) => {
              event.preventDefault();
              openReactionTray();
            }}
            onPointerCancel={cancelReactionHold}
            onPointerDown={startReactionHold}
            onPointerLeave={cancelReactionHold}
            onPointerUp={cancelReactionHold}
            style={reactionStyle(selectedReaction.accent)}
            title="Clique ou segure para escolher uma reação"
            type="button"
          >
            <SelectedIcon size={20} />
            <span>{viewerReaction ? selectedReaction.label : "Reagir"}</span>
          </button>

          <div
            aria-label="Escolher reação da publicação"
            className={reactionTrayOpen ? "reaction-tray open" : "reaction-tray"}
            onMouseEnter={openReactionTray}
            onMouseLeave={closeReactionTraySoon}
            role="menu"
          >
            {reactionOptions.map((reaction) => {
              const Icon = reaction.icon;
              const selected = viewerReaction === reaction.type;
              return (
                <button
                  className={selected ? "reaction-option selected" : "reaction-option"}
                  disabled={reactionLoading === reaction.type}
                  key={reaction.type}
                  onClick={() => selectReaction(reaction.type)}
                  role="menuitem"
                  style={reactionStyle(reaction.accent)}
                  title={`${reaction.label}: ${reaction.description}`}
                  type="button"
                >
                  <Icon size={23} />
                  <strong>{reaction.label}</strong>
                  <small>{reaction.description}</small>
                </button>
              );
            })}
          </div>
        </div>

        <button className="social-action" onClick={() => commentInputRef.current?.focus()} type="button">
          <MessageCircle size={20} />
          <span>Comentar</span>
        </button>

        <button className={saved ? "social-action saved" : "social-action"} onClick={() => setSaved((value) => !value)} type="button">
          <Bookmark size={20} />
          <span>{saved ? "Salvo" : "Salvar"}</span>
        </button>
      </div>

      <div className="comments">
        {hiddenComments > 0 && (
          <button className="comments-expand" onClick={() => setShowAllComments(true)} type="button">
            Ver todos os {topLevelComments.length} comentários
          </button>
        )}

        {visibleComments.map((item) => (
          <CommentThread
            comment={item}
            commentReacted={Boolean(commentReactions[item.id])}
            key={item.id}
            onReact={() =>
              setCommentReactions((current) => ({ ...current, [item.id]: !current[item.id] }))
            }
            onReply={() => {
              setReplyTo(item);
              commentInputRef.current?.focus();
            }}
            replies={repliesByParent[item.id] ?? []}
          />
        ))}
      </div>

      <form className="comment-form" onSubmit={submitComment}>
        {replyTo && (
          <div className="reply-context">
            <MessageCircle size={15} />
            <span>Respondendo {replyTo.author.name}</span>
            <button
              aria-label="Cancelar resposta"
              className="icon-button compact"
              onClick={() => setReplyTo(null)}
              title="Cancelar resposta"
              type="button"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div className="comment-input-row">
          <input
            className="input-field"
            placeholder={replyTo ? "Responder comentário..." : "Comentar na resenha..."}
            ref={commentInputRef}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <div className="comment-tools">
            <button
              className={mediaType === "image" ? "icon-button active" : "icon-button"}
              onClick={() => setMediaType((current) => (current === "image" ? "" : "image"))}
              title="Adicionar foto por URL"
              type="button"
            >
              <ImagePlus size={17} />
            </button>
            <button
              className={mediaType === "gif" ? "icon-button active" : "icon-button"}
              onClick={() => setMediaType((current) => (current === "gif" ? "" : "gif"))}
              title="Adicionar GIF por URL"
              type="button"
            >
              <FileImage size={17} />
            </button>
            <button className="send-comment-button" disabled={loading} title="Enviar comentário">
              <Send size={17} />
              <span>Enviar</span>
            </button>
          </div>
        </div>

        {mediaType && (
          <input
            className="input-field media-url-field"
            placeholder={mediaType === "image" ? "URL da foto" : "URL do GIF"}
            value={mediaUrl}
            onChange={(event) => setMediaUrl(event.target.value)}
          />
        )}
      </form>
    </article>
  );
}

function CommentThread({
  comment,
  commentReacted,
  onReact,
  onReply,
  replies,
}: {
  comment: Comment;
  commentReacted: boolean;
  onReact: () => void;
  onReply: () => void;
  replies: Comment[];
}) {
  return (
    <div className="comment-thread">
      <div className="comment">
        <Avatar user={comment.author} size="sm" />
        <div className="comment-body">
          <div className="comment-bubble">
            <p>
              <strong>{comment.author.name}</strong> {comment.text}
            </p>
            <CommentMedia comment={comment} />
          </div>
          <div className="comment-actions">
            <button className={commentReacted ? "text-button liked" : "text-button"} onClick={onReact} type="button">
              Resenha · {commentReacted ? 2 : 1}
            </button>
            <button className="text-button" onClick={onReply} type="button">
              <Reply size={13} />
              <span>Responder</span>
            </button>
          </div>
        </div>
      </div>

      {replies.length > 0 && (
        <div className="comment-replies">
          {replies.map((reply) => (
            <div className="comment reply" key={reply.id}>
              <Avatar user={reply.author} size="sm" />
              <div className="comment-body">
                <div className="comment-bubble">
                  <p>
                    <strong>{reply.author.name}</strong> {reply.text}
                  </p>
                  <CommentMedia comment={reply} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CommentMedia({ comment }: { comment: Comment }) {
  if (!comment.media_url) return null;

  return (
    <a className="comment-media" href={comment.media_url} rel="noreferrer" target="_blank">
      <img src={comment.media_url} alt={comment.media_type === "gif" ? "GIF do comentário" : "Foto do comentário"} />
    </a>
  );
}
