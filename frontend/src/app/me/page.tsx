"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Pencil, Save, Sparkles, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { LineupPreview } from "@/components/LineupPreview";
import { ProfileHeader } from "@/components/ProfileHeader";
import { api } from "@/lib/api";
import type { Event, Leaderboard, UserProfile } from "@/types";

const positionOptions = ["Goleiro", "Zagueiro", "Lateral", "Volante", "Meia", "Ponta", "Atacante"];
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

export default function MePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);
  const [saved, setSaved] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);

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
      }
    }

    load();
  }, [router]);

  const updateField = <K extends keyof UserProfile>(field: K, value: UserProfile[K]) => {
    setProfile((current) => (current ? { ...current, [field]: value } : current));
    setSaved(false);
  };

  const selectProfileFrame = (frame: NonNullable<UserProfile["profile_frame"]>) => {
    setProfile((current) =>
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
    if (!profile) return;
    const updated = await api.updateMe(profile);
    setProfile(updated);
    setSaved(true);
  };

  const selectImage = (field: "avatar_url" | "banner_url") => (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      updateField(field, String(reader.result) as UserProfile[typeof field]);
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  };

  const selectProfileEffect = (effect: NonNullable<UserProfile["profile_effect"]>) => {
    setProfile((current) =>
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

  if (!profile) return <div className="empty-state">Carregando seu perfil...</div>;

  const currentFrame = profile.profile_frame ?? "conversys";
  const profileEffect = effectOptions.some((option) => option.value === profile.profile_effect) ? profile.profile_effect : "off";
  const currentEffect = currentFrame !== "none" && profileEffect && profileEffect !== "off" ? profileEffect : "off";

  return (
    <AppShell user={profile} nextEvent={events[0] ?? null} leaderboard={leaderboard}>
      <ProfileHeader profile={profile} />

      <section className="content-card glass-panel profile-edit-card">
        <div className="section-heading compact-heading">
          <div>
            <span className="eyebrow">Perfil</span>
            <h2>Atualização de perfil</h2>
            <p>Dados do jogador ficam protegidos até você abrir a edição.</p>
          </div>
          <button
            className={editingProfile ? "profile-edit-toggle active" : "profile-edit-toggle"}
            onClick={() => setEditingProfile((current) => !current)}
            type="button"
          >
            {editingProfile ? <X size={17} /> : <Pencil size={17} />}
            <span>{editingProfile ? "Fechar edição" : "Editar perfil"}</span>
          </button>
        </div>

        {editingProfile && (
          <form className="profile-edit-form" onSubmit={submit}>
            <div className="profile-editor-layout">
              <div className="profile-editor-fields">
                <div className="settings-grid">
                  <input
                    className="input-field"
                    placeholder="Nome de perfil"
                    value={profile.display_name || profile.name || ""}
                    onChange={(event) => updateField("display_name", event.target.value)}
                  />
                  <input
                    className="input-field"
                    placeholder="Título da resenha"
                    value={profile.title || ""}
                    onChange={(event) => updateField("title", event.target.value)}
                  />
                  <select
                    className="input-field"
                    value={profile.position || ""}
                    onChange={(event) => updateField("position", event.target.value)}
                  >
                    <option value="">Posição que joga</option>
                    {profile.position && !positionOptions.includes(profile.position) && (
                      <option value={profile.position}>{profile.position}</option>
                    )}
                    {positionOptions.map((position) => (
                      <option key={position} value={position}>
                        {position}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input-field"
                    placeholder="Time preferido"
                    value={profile.favorite_team || ""}
                    onChange={(event) => updateField("favorite_team", event.target.value)}
                  />
                  <input
                    className="input-field"
                    placeholder="Jogador favorito"
                    value={profile.favorite_player || ""}
                    onChange={(event) => updateField("favorite_player", event.target.value)}
                  />
                </div>

                <div className="media-picker-grid">
                  <div className="profile-photo-stack">
                    <label className="media-picker">
                      <span>Foto de perfil</span>
                      <div className="media-preview avatar-media-preview">
                        <Avatar user={profile} size="lg" />
                      </div>
                      <strong>Escolher foto</strong>
                      <input accept="image/*" className="file-input" onChange={selectImage("avatar_url")} type="file" />
                    </label>

                    <LineupPreview profile={profile} />
                  </div>

                  <label className="media-picker">
                    <span>Banner do perfil</span>
                    <div
                      className="media-preview banner-media-preview"
                      style={{
                        backgroundImage: profile.banner_url ? `url(${profile.banner_url})` : undefined,
                      }}
                    />
                    <strong>Escolher banner</strong>
                    <input accept="image/*" className="file-input" onChange={selectImage("banner_url")} type="file" />
                  </label>
                </div>

                <div className="cosmetic-studio">
                  <div className="cosmetic-studio-head">
                    <div>
                      <span className="eyebrow">Personalização</span>
                      <h3>Bordas do perfil</h3>
                      <p>A mesma borda aparece na foto e em volta do banner. O movimento é opcional.</p>
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
                        className={currentFrame === option.value ? "cosmetic-option active" : "cosmetic-option"}
                        key={option.value}
                        onClick={() => selectProfileFrame(option.value)}
                        type="button"
                      >
                        <span className="frame-preview-stack">
                          <Avatar user={{ ...profile, profile_frame: option.value, profile_effect: "off" }} size="sm" />
                          <span className={`frame-banner-preview banner-frame-${option.value}`} />
                        </span>
                        <strong>{option.label}</strong>
                        <span>{option.description}</span>
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
                            user={{ ...profile, profile_frame: currentFrame, profile_effect: option.value }}
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
                    className={profile.verified_domain && profile.show_verified_badge !== false ? "verified-visibility-toggle active" : "verified-visibility-toggle"}
                    disabled={!profile.verified_domain}
                    onClick={() => updateField("show_verified_badge", !(profile.show_verified_badge !== false))}
                    type="button"
                  >
                    <BadgeCheck size={18} />
                    <span>
                      <strong>
                        {!profile.verified_domain
                          ? "Verificado indisponível"
                          : profile.show_verified_badge === false
                            ? "Mostrar verificado"
                            : "Verificado visível"}
                      </strong>
                      <small>
                        {!profile.verified_domain
                          ? "Use uma conta Conversys validada para liberar o selo."
                          : "Você pode exibir ou esconder o selo no perfil e nos posts."}
                      </small>
                    </span>
                  </button>
                </div>

                <textarea
                  className="input-field"
                  placeholder="Bio"
                  value={profile.bio || ""}
                  onChange={(event) => updateField("bio", event.target.value)}
                />
              </div>
            </div>
            <div className="action-row">
              <button className="btn-primary">
                <Save size={17} />
                <span>Salvar perfil</span>
              </button>
              {saved && <span className="verified-badge">Perfil atualizado</span>}
            </div>
          </form>
        )}
      </section>
    </AppShell>
  );
}
