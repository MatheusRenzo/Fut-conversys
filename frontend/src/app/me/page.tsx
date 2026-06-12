"use client";

import { useRef, useState, useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Check, Clock3, Pencil, Save, ShieldCheck, Sparkles, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { LineupPreview } from "@/components/LineupPreview";
import { ProfileHeader } from "@/components/ProfileHeader";
import { api } from "@/lib/api";
import type { Event, Leaderboard, Post, UserProfile } from "@/types";

const frameOptions: Array<{
  value: NonNullable<UserProfile["profile_frame"]>;
  label: string;
  description: string;
}> = [
  { value: "none", label: "Sem borda", description: "perfil limpo" },
  { value: "conversys", label: "Conversys", description: "azul, ciano e verde" },
  { value: "copa", label: "Copa 2026", description: "contorno torneio" },
  { value: "nitro_plus", label: "Nitro+", description: "contorno premium" },
  { value: "brasil", label: "Brasil", description: "verde, amarelo e azul" },
  { value: "argentina", label: "Argentina", description: "celeste, branco e ouro" },
  { value: "franca", label: "França", description: "azul, branco e vermelho" },
  { value: "portugal", label: "Portugal", description: "verde, vermelho e ouro" },
  { value: "espanha", label: "Espanha", description: "vermelho e amarelo" },
  { value: "alemanha", label: "Alemanha", description: "preto, vermelho e ouro" },
  { value: "inglaterra", label: "Inglaterra", description: "branco, vermelho e azul" },
  { value: "eua", label: "EUA", description: "azul, vermelho e branco" },
  { value: "mexico", label: "México", description: "verde, branco e vermelho" },
  { value: "canada", label: "Canadá", description: "vermelho e branco" },
  { value: "africa_sul", label: "África do Sul", description: "verde, ouro e preto" },
  { value: "coreia_sul", label: "Coreia do Sul", description: "branco, vermelho e azul" },
  { value: "tchequia", label: "Tchéquia", description: "azul, branco e vermelho" },
  { value: "bosnia", label: "Bósnia", description: "azul e amarelo" },
  { value: "qatar", label: "Qatar", description: "vinho e branco" },
  { value: "suica", label: "Suíça", description: "vermelho e branco" },
  { value: "marrocos", label: "Marrocos", description: "vermelho e verde" },
  { value: "haiti", label: "Haiti", description: "azul e vermelho" },
  { value: "escocia", label: "Escócia", description: "azul e branco" },
  { value: "paraguai", label: "Paraguai", description: "vermelho, branco e azul" },
  { value: "australia", label: "Austrália", description: "azul, vermelho e ouro" },
  { value: "turquia", label: "Turquia", description: "vermelho e branco" },
  { value: "curacao", label: "Curaçao", description: "azul e amarelo" },
  { value: "costa_marfim", label: "Costa do Marfim", description: "laranja, branco e verde" },
  { value: "equador", label: "Equador", description: "amarelo, azul e vermelho" },
  { value: "holanda", label: "Holanda", description: "laranja, branco e azul" },
  { value: "japao", label: "Japão", description: "branco e vermelho" },
  { value: "suecia", label: "Suécia", description: "azul e amarelo" },
  { value: "tunisia", label: "Tunísia", description: "vermelho e branco" },
  { value: "belgica", label: "Bélgica", description: "preto, amarelo e vermelho" },
  { value: "egito", label: "Egito", description: "vermelho, branco e preto" },
  { value: "ira", label: "Irã", description: "verde, branco e vermelho" },
  { value: "nova_zelandia", label: "Nova Zelândia", description: "azul, vermelho e branco" },
  { value: "cabo_verde", label: "Cabo Verde", description: "azul, branco e vermelho" },
  { value: "arabia_saudita", label: "Arábia Saudita", description: "verde e branco" },
  { value: "uruguai", label: "Uruguai", description: "azul, branco e sol" },
  { value: "senegal", label: "Senegal", description: "verde, amarelo e vermelho" },
  { value: "iraque", label: "Iraque", description: "vermelho, branco e preto" },
  { value: "noruega", label: "Noruega", description: "vermelho, branco e azul" },
  { value: "argelia", label: "Argélia", description: "verde, branco e vermelho" },
  { value: "austria", label: "Áustria", description: "vermelho e branco" },
  { value: "jordania", label: "Jordânia", description: "preto, verde e vermelho" },
  { value: "rd_congo", label: "RD Congo", description: "azul, amarelo e vermelho" },
  { value: "uzbequistao", label: "Uzbequistão", description: "azul, branco e verde" },
  { value: "colombia", label: "Colômbia", description: "amarelo, azul e vermelho" },
  { value: "croacia", label: "Croácia", description: "vermelho, branco e azul" },
  { value: "gana", label: "Gana", description: "vermelho, amarelo e verde" },
  { value: "panama", label: "Panamá", description: "branco, azul e vermelho" },
];
const effectOptions: Array<{
  value: NonNullable<UserProfile["profile_effect"]>;
  label: string;
  description: string;
}> = [
  { value: "off", label: "Parada", description: "borda fixa" },
  { value: "pulse", label: "Pulso", description: "batida leve da borda" },
  { value: "stadium", label: "Estádio", description: "flash fino de arquibancada" },
  { value: "orbit", label: "Orbital", description: "marcador correndo na borda" },
  { value: "nitro", label: "Nitro+", description: "energia premium no contorno" },
];

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function cloneProfile(profile: UserProfile): UserProfile {
  return JSON.parse(JSON.stringify(profile)) as UserProfile;
}

function profileSnapshot(profile: UserProfile, verified: boolean) {
  if (verified) {
    return {
      display_name: profile.display_name || profile.name || "",
      title: profile.title || "",
      position: profile.position || "",
      favorite_team: profile.favorite_team || "",
      favorite_player: profile.favorite_player || "",
      bio: profile.bio || "",
      avatar_url: profile.avatar_url || "",
      banner_url: profile.banner_url || "",
      banner_position_x: profile.banner_position_x ?? 50,
      banner_position_y: profile.banner_position_y ?? 50,
      profile_frame: profile.profile_frame ?? "conversys",
      profile_effect: profile.profile_effect ?? "off",
      show_verified_badge: profile.show_verified_badge !== false,
    };
  }

  return {
    avatar_url: profile.avatar_url || "",
    banner_url: profile.banner_url || "",
    banner_position_x: profile.banner_position_x ?? 50,
    banner_position_y: profile.banner_position_y ?? 50,
  };
}

function isProfileDirty(original: UserProfile, draft: UserProfile) {
  const verified = Boolean(original.verified_enabled);
  return JSON.stringify(profileSnapshot(original, verified)) !== JSON.stringify(profileSnapshot(draft, verified));
}

function ProfileField({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className ? `profile-field ${className}` : "profile-field"}>
      <span>{label}</span>
      <small>{hint}</small>
      {children}
    </div>
  );
}

export default function MePage() {
  const router = useRouter();
  const bannerDragRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [adminUsers, setAdminUsers] = useState<UserProfile[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [saved, setSaved] = useState(false);
  const [draft, setDraft] = useState<UserProfile | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [goalReviewLoading, setGoalReviewLoading] = useState<string | null>(null);
  const [verifiedLoading, setVerifiedLoading] = useState<number | null>(null);

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
        if (me.is_admin) {
          const [feed, usersResponse] = await Promise.all([api.feed(), api.adminUsers()]);
          setPosts(feed.posts);
          setAdminUsers(usersResponse.users);
        }
      } catch {
        router.push("/");
      }
    }

    load();
  }, [router]);

  const isEditing = draft !== null;
  const editProfile = draft ?? profile;

  const updateDraftField = <K extends keyof UserProfile>(field: K, value: UserProfile[K]) => {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setSaved(false);
  };

  const startEditing = () => {
    if (!profile) return;
    setDraft(cloneProfile(profile));
    setSaved(false);
  };

  const stopEditing = () => {
    if (profile && draft && isProfileDirty(profile, draft)) {
      const discard = window.confirm("Descartar alterações que ainda não foram confirmadas?");
      if (!discard) return;
    }
    setDraft(null);
    setSaved(false);
  };

  const selectProfileFrame = (frame: NonNullable<UserProfile["profile_frame"]>) => {
    if (!draft?.verified_enabled) return;
    setDraft((current) =>
      current
        ? {
            ...current,
            profile_frame: frame,
            profile_effect: frame === "none" ? "off" : current.profile_effect,
            animated_banner: false,
          }
        : current,
    );
    setSaved(false);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!profile || !draft) return;

    setSavingProfile(true);
    try {
      const payload = draft.verified_enabled
        ? draft
        : {
            avatar_url: draft.avatar_url,
            banner_url: draft.banner_url,
            banner_position_x: draft.banner_position_x,
            banner_position_y: draft.banner_position_y,
          };
      const updated = await api.updateMe(payload);
      setProfile(updated);
      setDraft(null);
      setSaved(true);
    } finally {
      setSavingProfile(false);
    }
  };

  // Recorta a foto em quadrado centralizado para encaixar no círculo do avatar em qualquer tela
  const cropToSquare = (dataUrl: string, maxSide = 512): Promise<string> =>
    new Promise((resolve) => {
      const image = new Image();
      image.onload = () => {
        const side = Math.min(image.width, image.height);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = Math.min(maxSide, side);
        const context = canvas.getContext("2d");
        if (!context || !side) {
          resolve(dataUrl);
          return;
        }
        context.drawImage(
          image,
          (image.width - side) / 2,
          (image.height - side) / 2,
          side,
          side,
          0,
          0,
          canvas.width,
          canvas.height,
        );
        resolve(canvas.toDataURL("image/jpeg", 0.92));
      };
      image.onerror = () => resolve(dataUrl);
      image.src = dataUrl;
    });

  const selectImage = (field: "avatar_url" | "banner_url") => (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !draft) return;

    const reader = new FileReader();
    reader.onload = async () => {
      const rawUrl = String(reader.result);
      const imageUrl = (field === "avatar_url" ? await cropToSquare(rawUrl) : rawUrl) as UserProfile[typeof field];
      setDraft((current) =>
        current
          ? {
              ...current,
              [field]: imageUrl,
              ...(field === "banner_url"
                ? {
                    banner_position_x: 50,
                    banner_position_y: 50,
                  }
                : {}),
            }
          : current,
      );
      setSaved(false);
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  };

  const updateBannerPosition = (x: number, y: number) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            banner_position_x: clampPercent(x),
            banner_position_y: clampPercent(y),
          }
        : current,
    );
    setSaved(false);
  };

  const startBannerDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!draft?.banner_url) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    bannerDragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: draft.banner_position_x ?? 50,
      originY: draft.banner_position_y ?? 50,
    };
  };

  const moveBannerDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = bannerDragRef.current;
    if (!drag) return;

    const bounds = event.currentTarget.getBoundingClientRect();
    const deltaX = ((event.clientX - drag.startX) / bounds.width) * 100;
    const deltaY = ((event.clientY - drag.startY) / bounds.height) * 100;
    updateBannerPosition(drag.originX - deltaX, drag.originY - deltaY);
  };

  const stopBannerDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    bannerDragRef.current = null;
  };

  const selectProfileEffect = (effect: NonNullable<UserProfile["profile_effect"]>) => {
    if (!draft?.verified_enabled) return;
    setDraft((current) =>
      current
        ? {
            ...current,
            animated_banner: false,
            profile_effect: effect,
          }
        : current,
    );
    setSaved(false);
  };

  const reviewGoalClaim = async (postId: number, status: "approved" | "rejected") => {
    setGoalReviewLoading(`${postId}-${status}`);
    try {
      const updated = await api.reviewPostGoals(postId, status);
      setPosts((current) => current.map((post) => (post.id === updated.id ? updated : post)));
      const [me, ranking] = await Promise.all([api.me(), api.leaderboard()]);
      setProfile(me);
      setLeaderboard(ranking);
    } finally {
      setGoalReviewLoading(null);
    }
  };

  const toggleVerified = async (target: UserProfile) => {
    setVerifiedLoading(target.id);
    try {
      const updated = await api.setUserVerified(target.id, !target.verified_enabled);
      setAdminUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (profile?.id === updated.id) {
        const refreshed = await api.me();
        setProfile(refreshed);
      }
    } finally {
      setVerifiedLoading(null);
    }
  };

  if (!profile || !editProfile) return <div className="empty-state">Carregando seu perfil...</div>;

  const previewProfile = isEditing ? draft ?? profile : profile;
  const currentFrame = editProfile.profile_frame ?? "conversys";
  const bannerPositionX = editProfile.banner_position_x ?? 50;
  const bannerPositionY = editProfile.banner_position_y ?? 50;
  const profileEffect = effectOptions.some((option) => option.value === editProfile.profile_effect)
    ? editProfile.profile_effect
    : "off";
  const currentEffect = currentFrame !== "none" && profileEffect && profileEffect !== "off" ? profileEffect : "off";
  const isAdmin = profile.is_admin;
  const canUseVerifiedFeatures = profile.verified_enabled;
  const hasUnsavedChanges = Boolean(draft && isProfileDirty(profile, draft));
  const pendingGoalClaims = isAdmin
    ? posts.filter((post) => (post.goals_scored ?? 0) > 0 && post.goal_status === "pending")
    : [];

  return (
    <AppShell user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <ProfileHeader profile={previewProfile} />

      {!isEditing && (
        <section className="content-card glass-panel profile-edit-cta">
          <div>
            <strong>Deixa o perfil com a tua cara</strong>
            <span>Troca foto, capa de fundo, borda do avatar e efeitos. Verificados desbloqueiam bordas e efeitos especiais.</span>
          </div>
          <button
            className="btn-primary profile-edit-cta-button"
            onClick={() => {
              startEditing();
              window.setTimeout(() => {
                document.querySelector(".profile-edit-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }, 60);
            }}
            type="button"
          >
            <Pencil size={16} />
            <span>Editar perfil</span>
          </button>
        </section>
      )}

      {isAdmin && (
        <section className="content-card glass-panel goal-approval-panel">
          <div className="approval-panel-head">
            <div>
              <span className="eyebrow">Admin</span>
              <h2>Aprovações de gols</h2>
              <p>Valide apenas gols conferidos no evento antes de contar no ranking.</p>
            </div>
            <strong>{pendingGoalClaims.length}</strong>
          </div>

          {pendingGoalClaims.length > 0 ? (
            <div className="approval-list">
              {pendingGoalClaims.map((post) => {
                const approveKey = `${post.id}-approved`;
                const rejectKey = `${post.id}-rejected`;
                return (
                  <article className="approval-item" key={post.id}>
                    <div>
                      <span>
                        <Clock3 size={15} />
                        Pendente
                      </span>
                      <strong>{post.author.name}</strong>
                      <p>
                        {post.goals_scored} {post.goals_scored === 1 ? "gol" : "gols"}
                        {post.match ? ` em ${post.match.title}` : ""}
                      </p>
                    </div>
                    <div className="approval-actions">
                      <button
                        className="goal-review-button approve"
                        disabled={Boolean(goalReviewLoading)}
                        onClick={() => reviewGoalClaim(post.id, "approved")}
                        type="button"
                      >
                        <Check size={15} />
                        <span>{goalReviewLoading === approveKey ? "Aprovando..." : "Aprovar"}</span>
                      </button>
                      <button
                        className="goal-review-button reject"
                        disabled={Boolean(goalReviewLoading)}
                        onClick={() => reviewGoalClaim(post.id, "rejected")}
                        type="button"
                      >
                        <X size={15} />
                        <span>{goalReviewLoading === rejectKey ? "Recusando..." : "Recusar"}</span>
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="approval-empty">Nenhum gol pendente agora.</div>
          )}
        </section>
      )}

      {isAdmin && (
        <section className="content-card glass-panel verified-admin-panel">
          <div className="approval-panel-head">
            <div>
              <span className="eyebrow">Admin</span>
              <h2>Verificados</h2>
              <p>Ligue ou desligue selo, bordas e efeitos de cada jogador manualmente.</p>
            </div>
            <strong>{adminUsers.filter((item) => item.verified_enabled).length}</strong>
          </div>

          <div className="verified-admin-list">
            {adminUsers.map((item) => (
              <article className={item.verified_enabled ? "verified-admin-item active" : "verified-admin-item"} key={item.id}>
                <Avatar user={item} size="sm" />
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.email || item.username}</span>
                </div>
                <button
                  className={item.verified_enabled ? "verified-admin-toggle active" : "verified-admin-toggle"}
                  disabled={verifiedLoading === item.id}
                  onClick={() => toggleVerified(item)}
                  type="button"
                >
                  <ShieldCheck size={16} />
                  <span>
                    {verifiedLoading === item.id
                      ? "Salvando..."
                      : item.verified_enabled
                        ? "Desaprovar"
                        : "Aprovar"}
                  </span>
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="content-card glass-panel profile-edit-card">
        <div className="section-heading compact-heading">
          <div>
            <span className="eyebrow">Perfil</span>
            <h2>Meu perfil</h2>
            <p>Abra a edição, ajuste os campos e confirme no final. Nada é salvo automaticamente.</p>
          </div>
          <button
            className={isEditing ? "profile-edit-toggle active" : "profile-edit-toggle"}
            onClick={() => (isEditing ? stopEditing() : startEditing())}
            type="button"
          >
            {isEditing ? <X size={17} /> : <Pencil size={17} />}
            <span>{isEditing ? "Fechar edição" : "Editar perfil"}</span>
          </button>
        </div>

        {isEditing && draft && (
          <form className="profile-edit-form" onSubmit={submit}>
            <div className="profile-save-notice">
              <strong>Alterações pendentes</strong>
              <span>
                Você está vendo uma prévia local. Clique em <em>Confirmar alterações</em> no final para publicar no
                perfil.
              </span>
            </div>

            <div className="profile-editor-layout">
              <div className="profile-editor-fields">
                {canUseVerifiedFeatures ? (
                  <div className="settings-grid profile-settings-grid">
                    <ProfileField
                      hint="Nome que aparece no feed, comentários, rankings e cards de evento."
                      label="Nome de exibição"
                    >
                      <input
                        className="input-field"
                        id="profile-display-name"
                        onChange={(event) => updateDraftField("display_name", event.target.value)}
                        value={editProfile.display_name || editProfile.name || ""}
                      />
                    </ProfileField>
                    <ProfileField
                      hint="Frase curta abaixo do nome, tipo apelido da resenha ou vibe do jogador."
                      label="Título da resenha"
                    >
                      <input
                        className="input-field"
                        id="profile-title"
                        onChange={(event) => updateDraftField("title", event.target.value)}
                        value={editProfile.title || ""}
                      />
                    </ProfileField>
                    <ProfileField
                      className="profile-field-wide"
                      hint="Posição que aparece no seu perfil e ajuda o time a te reconhecer em campo."
                      label="Posição em campo"
                    >
                      <div className="position-field-picker">
                        <LineupPreview
                          profile={editProfile}
                          selectable
                          onSelectPosition={(position) => updateDraftField("position", position)}
                        />
                      </div>
                    </ProfileField>
                    <ProfileField
                      hint="Time de coração exibido no perfil e usado nas conversas do app."
                      label="Time preferido"
                    >
                      <input
                        className="input-field"
                        id="profile-favorite-team"
                        onChange={(event) => updateDraftField("favorite_team", event.target.value)}
                        value={editProfile.favorite_team || ""}
                      />
                    </ProfileField>
                    <ProfileField
                      hint="Jogador referência que aparece como curiosidade no seu perfil."
                      label="Jogador favorito"
                    >
                      <input
                        className="input-field"
                        id="profile-favorite-player"
                        onChange={(event) => updateDraftField("favorite_player", event.target.value)}
                        value={editProfile.favorite_player || ""}
                      />
                    </ProfileField>
                  </div>
                ) : (
                  <div className="verified-locked-card">
                    <ShieldCheck size={20} />
                    <div>
                      <strong>Perfil básico</strong>
                      <p>O admin ainda não liberou verificado para esta conta. Por enquanto, só foto e banner podem ser alterados.</p>
                    </div>
                  </div>
                )}

                <div className="media-picker-grid">
                  <ProfileField
                    hint="Foto circular exibida no avatar, comentários, rankings e confirmações de evento."
                    label="Foto de perfil"
                  >
                    <label className="media-picker">
                      <div className="media-preview avatar-media-preview">
                        <Avatar user={editProfile} size="lg" />
                      </div>
                      <strong>Escolher foto</strong>
                      <input accept="image/*" className="file-input" onChange={selectImage("avatar_url")} type="file" />
                    </label>
                  </ProfileField>

                  <ProfileField
                    className="profile-field-wide"
                    hint="Imagem de capa do perfil. Depois de enviar, arraste a prévia para definir o recorte."
                    label="Banner do perfil"
                  >
                    <div className="media-picker banner-position-editor">
                      <div
                        className={`media-preview banner-media-preview banner-real-preview frame-banner-preview banner-frame-${currentFrame}`}
                        onPointerCancel={stopBannerDrag}
                        onPointerDown={startBannerDrag}
                        onPointerMove={moveBannerDrag}
                        onPointerUp={stopBannerDrag}
                        role="img"
                        aria-label="Prévia reposicionável do banner"
                        style={{
                          backgroundImage: editProfile.banner_url ? `url(${editProfile.banner_url})` : undefined,
                          backgroundPosition: `${bannerPositionX}% ${bannerPositionY}%`,
                        }}
                      >
                        {editProfile.banner_url ? (
                          <>
                            <span className="banner-visible-frame" />
                            <em>Arraste para reposicionar</em>
                          </>
                        ) : (
                          <label className="banner-empty-hint">
                            <strong>Escolher banner</strong>
                            <span>Depois de subir, arraste para ajustar o recorte.</span>
                            <input accept="image/*" className="file-input" onChange={selectImage("banner_url")} type="file" />
                          </label>
                        )}
                      </div>
                      {editProfile.banner_url && (
                        <label className="banner-change-button">
                          Alterar foto do banner
                          <input accept="image/*" className="file-input" onChange={selectImage("banner_url")} type="file" />
                        </label>
                      )}
                    </div>
                  </ProfileField>
                </div>

                {canUseVerifiedFeatures && (
                <div className="cosmetic-studio">
                  <div className="cosmetic-studio-head">
                    <div>
                      <span className="eyebrow">Personalização</span>
                      <h3>Bordas do perfil</h3>
                      <p>A mesma borda aparece na foto e em volta do banner. O movimento é opcional e só entra após confirmar.</p>
                    </div>
                    <Sparkles size={20} />
                  </div>

                  <div className="customization-step">
                    <span>1</span>
                    <strong>Borda compartilhada</strong>
                    <small>Escolha o contorno que une foto e banner.</small>
                  </div>

                  <div className="cosmetic-grid" aria-label="Molduras do avatar">
                    {frameOptions.map((option) => (
                      <button
                        className={`cosmetic-option frame-choice banner-frame-${option.value}${currentFrame === option.value ? " active" : ""}`}
                        key={option.value}
                        onClick={() => selectProfileFrame(option.value)}
                        type="button"
                      >
                        <span className="frame-color-sample" aria-hidden="true">
                          <span className="frame-color-ring" />
                          <span className="frame-color-track" />
                        </span>
                        <strong>{option.label}</strong>
                        <small>{option.description}</small>
                      </button>
                    ))}
                  </div>

                  <div className="customization-step">
                    <span>2</span>
                    <strong>Movimento da borda</strong>
                    <small>O mesmo movimento aparece na foto e no banner.</small>
                  </div>

                  <div className="motion-effect-grid" aria-label="Efeitos de movimento">
                    {effectOptions.map((option) => (
                      <button
                        className={currentEffect === option.value ? "motion-effect-option active" : "motion-effect-option"}
                        disabled={currentFrame === "none" && option.value !== "off"}
                        key={option.value}
                        onClick={() => selectProfileEffect(option.value)}
                        type="button"
                      >
                        <span className="effect-preview-stack">
                          <Avatar
                            user={{ ...editProfile, profile_frame: currentFrame, profile_effect: option.value }}
                            size="sm"
                          />
                          <span className={`banner-effect-preview banner-frame-${currentFrame} banner-effect-${option.value}`} />
                        </span>
                        <span>
                          <strong>{option.label}</strong>
                          <small>{option.description}</small>
                        </span>
                      </button>
                    ))}
                  </div>

                  <button
                    className={editProfile.verified_enabled && editProfile.show_verified_badge !== false ? "verified-visibility-toggle active" : "verified-visibility-toggle"}
                    onClick={() => updateDraftField("show_verified_badge", !(editProfile.show_verified_badge !== false))}
                    type="button"
                  >
                    <BadgeCheck size={18} />
                    <span>
                      <strong>
                        {editProfile.show_verified_badge === false
                            ? "Mostrar verificado"
                            : "Verificado visível"}
                      </strong>
                      <small>
                        Controla se o selo aparece no perfil e nos posts depois de confirmar.
                      </small>
                    </span>
                  </button>
                </div>
                )}

                {canUseVerifiedFeatures && (
                  <ProfileField
                    hint="Texto livre sobre você. Aparece na área principal do perfil público."
                    label="Bio"
                  >
                    <textarea
                      className="input-field"
                      id="profile-bio"
                      onChange={(event) => updateDraftField("bio", event.target.value)}
                      value={editProfile.bio || ""}
                    />
                  </ProfileField>
                )}
              </div>
            </div>
            <div className="profile-save-footer">
              <div className="action-row">
                <button className="btn-primary" disabled={savingProfile || !hasUnsavedChanges}>
                  <Save size={17} />
                  <span>{savingProfile ? "Salvando..." : "Confirmar alterações"}</span>
                </button>
                <button className="btn-secondary" disabled={savingProfile} onClick={stopEditing} type="button">
                  Descartar
                </button>
              </div>
              {hasUnsavedChanges && !savingProfile && <span className="profile-unsaved-badge">Alterações ainda não publicadas</span>}
              {saved && !isEditing && <span className="verified-badge">Perfil atualizado</span>}
            </div>
          </form>
        )}
      </section>
    </AppShell>
  );
}
