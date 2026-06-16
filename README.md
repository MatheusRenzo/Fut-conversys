<div align="center">
  <img src="frontend/public/icons/fut-conversys-logo.png" width="140" alt="Fut Conversys logo" />

  # Fut Conversys

  **Rede social esportiva corporativa + Bolão da Copa 2026 com motor de dados ao vivo, multi-fonte e auto-confiável.**

  Peladas da firma, eventos, resenha, ranking gamer, validação de gols com aprovação — e um bolão que acompanha a Copa em tempo real cruzando várias APIs, com IA reconciliando os goleadores e um painel admin transparente.

  [![CI](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/ci.yml/badge.svg)](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/ci.yml)
  [![Deploy](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/deploy.yml/badge.svg)](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/deploy.yml)
  [![License: MIT](https://img.shields.io/badge/License-MIT-61A229.svg)](LICENSE)
  [![Open Source](https://img.shields.io/badge/Open%20Source-ready-00CFB4.svg)](CONTRIBUTING.md)
  [![Security Policy](https://img.shields.io/badge/Security-policy-041E42.svg)](SECURITY.md)
  [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-005AFF.svg)](CONTRIBUTING.md)

  [![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
  [![React](https://img.shields.io/badge/React-19-005AFF?logo=react&logoColor=white)](https://react.dev/)
  [![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![PWA](https://img.shields.io/badge/PWA-installable-00CFB4)](frontend/public/manifest.webmanifest)
</div>

---

## ⚽ Sobre o projeto

O **Fut Conversys** transforma o futebol de empresa numa experiência social completa — e ganhou um **bolão da Copa do Mundo 2026** de verdade: aposta de placar e artilheiro, ranking ao vivo, e um motor de sincronização que acompanha os jogos em tempo real sem depender de uma única fonte.

A proposta é parecer **produto de casa de apostas**, não protótipo: identidade visual Conversys, app instalável, dopamina no ranking, e por baixo um pipeline de dados resiliente que respeita limites de API e nunca trava.

## 🎯 O que a plataforma faz

**Rede social esportiva**
- Feed com posts, fotos/GIFs, comentários, respostas e **reações com significado** (torcida, golaço, churras, resenha, mídia) que alimentam o status do jogador.
- **Eventos da firma** com presença, capacidade e cadastro controlado por admin.
- **Gols com aprovação**: o jogador registra, o admin valida antes de virar ponto.
- **Perfil gamer**: avatar, banner, bio, posição em campo, radar de atributos, bordas personalizáveis e selo verificado.
- **PWA instalável** + **Login Microsoft Entra ID** para contas corporativas.

**Bolão da Copa 2026**
- Palpite de **placar exato (3 pts)**, **vencedor (1 pt)**, **artilheiro (+1)** e **campeã (10 pts)**.
- Palpites fecham **1h antes** de cada jogo; pontuação entra sozinha quando o jogo acaba.
- **Ranking ao vivo** com movimentação real (▲/▼), "+N pontos na rodada 🔥" e flash dos seus pontos subindo.
- **Painel admin transparente**: status por jogo, etapas, limites de cada API, confirmação/re-confirmação e log do que rodou.

## 🛰️ Motor de dados ao vivo (o coração do bolão)

O placar e os goleadores são capturados **cruzando várias fontes**, com a regra de **nunca depender de uma só** e **nunca estourar limite de API**:

| Fonte | Papel | Limite | Estratégia |
| --- | --- | --- | --- |
| **football-data.org** | Placar + status (ao vivo / intervalo / fim) | 10/min | Dirige o ao vivo; roda a cada ciclo (grátis) |
| **API-Football** | Nome do goleador (definitivo) | 100/dia · 9/min | **Event-driven**: só dispara no gol; retry até achar; 1× no fim |
| **TheSportsDB** | 2ª confirmação + failover ao vivo | 26/min | Backoff por jogo; assume o vivo se a paga zerar |
| **openfootball** | 3ª confirmação (backup curado) | ilimitada | Reconcilia e corrobora |
| **IA (GPT-4o-mini)** | Normaliza nomes no elenco oficial e reconcilia divergências | cacheada | ~2 chamadas por jogo |

**Como funciona o ciclo de um jogo**
1. **Começou** → football-data marca *ao vivo*; **intervalo** vira selo `⏸`.
2. **Gol** → detectado de graça pela football-data; aí a API-Football pega **só o nome** (em ~1 min), com *retry* até achar. Sem cota? **failover** na TheSportsDB.
3. **Fim** → a paga roda **1×** e recupera todos os goleadores (confirmação final).
4. **+10 min** → re-confirmação grátis (TheSportsDB + openfootball + IA), sinalizando o que veio a mais.

**Garantias de robustez**
- A lista de goleadores **só cresce** (união) — nunca perde um gol já capturado.
- Cada nome é **encaixado no elenco oficial salvo** (à prova de bala pro casamento com o palpite).
- **Confirmação por corroboração**: conta quantas fontes independentes batem, sem contradizer.
- **Rede de segurança**: jogo nunca fica "ao vivo" por horas; se nenhuma fonte confirma o fim, encerra sozinho.
- Limites controlados por janela de minuto + reserva diária → **nunca quebra a API**.

## 🔒 Segurança

Repositório **público** tratado com higiene de produto sério:

- **Segredos só em `.env`** (gitignored): API keys, `AUTH_SECRET`, Microsoft secret, senha de admin. No código, apenas `os.getenv(...)` com defaults em placeholder. `.env.example` sem valores reais.
- **Sem PII no repositório**: nada de e-mail pessoal, IP, topologia de rede, usuário SSH ou caminho de máquina. Runbooks de infra ficam fora do versionamento.
- **Acesso corporativo**: cadastro/verificação por domínio via Microsoft Entra ID; selo verificado só para contas da empresa.
- **Gols e resultados auditáveis**: aprovação administrativa de gols e painel que mostra fonte e confirmação de cada dado.
- **CI** valida frontend (lint + build) e backend (compile) a cada push. Política em [SECURITY.md](SECURITY.md).

## 🧱 Stack

| Camada | Tecnologias |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, CSS moderno, Lucide |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Banco | SQLite local por padrão · PostgreSQL via Docker Compose |
| Auth | Login local (dev) + Microsoft Entra ID |
| Dados ao vivo | football-data, API-Football, TheSportsDB, openfootball, OpenAI |
| App | PWA (manifest, service worker, ícones maskable/apple) |
| Qualidade | ESLint, Next build, py_compile, GitHub Actions |

## 🗂️ Estrutura

```txt
Fut-conversys/
├── backend/            # API FastAPI, modelos, motor de sync e regras do bolão
├── frontend/           # App Next.js (UI, PWA, painel admin)
├── nginx/              # Reverse proxy / TLS (configs genéricas)
├── postgres/           # Config do PostgreSQL
├── .github/            # CI, deploy e templates
├── docker-compose.yml  # Stack completa (db + backend + frontend + nginx)
└── README.md
```

## 🚀 Rodando localmente

```bash
git clone git@github.com:MatheusRenzo/Fut-conversys.git
cd Fut-conversys
```

**Backend**
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # preencha as chaves no .env (nunca comite)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Ou suba tudo com Docker:
```bash
docker compose up -d --build
```

### E-mail de deploy (GitHub Actions)

O workflow `.github/workflows/deploy.yml` envia um HTML no estilo Fut Conversys após cada deploy na `main`.

Secrets necessários no repositório (`Settings → Secrets`):

| Secret | Descrição |
|--------|-----------|
| `MAIL_USERNAME` | Gmail usado para enviar |
| `MAIL_PASSWORD` | Senha de app do Gmail |
| `NOTIFY_EMAIL` | Quem recebe (padrão: `admin@example.com`) |

Atalho local (com `gh` autenticado):

```bash
cp .github/deploy-mail.env.example .github/deploy-mail.env
# edite o arquivo
bash scripts/setup-deploy-mail-secrets.sh
bash scripts/send-deploy-email-test.sh   # envia preview de teste
```

Se `NOTIFY_EMAIL` não existir no GitHub, o workflow envia para `admin@example.com` (e só depois cai no `MAIL_USERNAME`).

Acesse `http://localhost:3000` (app) e `http://localhost:8000` (API).

## ⚙️ Configuração (.env)

Todas as integrações são **opcionais** — sem chave, o app roda com as fontes grátis e logins locais.

```env
# Admin local (troque em produção)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=troque-isto
ADMIN_EMAIL=admin@example.com
AUTH_SECRET=use-um-valor-longo-e-aleatorio

# Bolão — dados ao vivo (deixe vazio para usar só as grátis)
FOOTBALL_DATA_API_KEY=
API_FOOTBALL_KEY=
THESPORTSDB_KEY=123
OPENAI_API_KEY=

# Microsoft Entra ID (login corporativo)
MICROSOFT_CLIENT_ID=
MICROSOFT_TENANT_ID=
MICROSOFT_CLIENT_SECRET=
```

> Nunca suba o `.env` real. Veja [MICROSOFT_ENTRA_SETUP.md](MICROSOFT_ENTRA_SETUP.md) para o login corporativo.

## 🤝 Open source

- [x] Licença MIT · Guia de contribuição · Código de conduta · Política de segurança
- [x] Templates de issue e PR · CI de frontend e backend
- [x] `.env.example` sem credenciais · `.gitignore` protegendo segredos, banco e build

Contribuições são bem-vindas — veja [CONTRIBUTING.md](CONTRIBUTING.md).

## 🗺️ Roadmap

- Ranking por temporada e histórico de bolões.
- Galeria de momentos dos eventos e moderação de mídia.
- Conquistas e loja de personalização.
- Notificações push (PWA) de gol e mudança de posição.

## 👤 Autor

Feito por **Matheus Renzo** como produto interno de futebol corporativo. Se curtir, deixa uma ⭐ e acompanhe a evolução.
