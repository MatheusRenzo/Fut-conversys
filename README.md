<div align="center">
  <img src="frontend/public/icons/fut-conversys-logo.png" width="140" alt="Fut Conversys logo" />

  # Fut Conversys

  **Uma rede social esportiva interna para peladas corporativas, eventos, resenha, ranking, perfil gamer e validacao de gols com aprovacao administrativa.**

  [![CI](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/ci.yml/badge.svg)](https://github.com/MatheusRenzo/Fut-conversys/actions/workflows/ci.yml)
  [![License: MIT](https://img.shields.io/badge/License-MIT-61A229.svg)](LICENSE)
  [![Open Source](https://img.shields.io/badge/Open%20Source-ready-00CFB4.svg)](CONTRIBUTING.md)
  [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-005AFF.svg)](CONTRIBUTING.md)
  [![Code of Conduct](https://img.shields.io/badge/Code%20of%20Conduct-active-E31C79.svg)](CODE_OF_CONDUCT.md)
  [![Security Policy](https://img.shields.io/badge/Security-policy-041E42.svg)](SECURITY.md)

  [![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
  [![React](https://img.shields.io/badge/React-19-005AFF?logo=react&logoColor=white)](https://react.dev/)
  [![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![PWA](https://img.shields.io/badge/PWA-installable-00CFB4)](frontend/public/manifest.webmanifest)
</div>

---

## Sobre o projeto

O **Fut Conversys** nasceu como uma plataforma interna para transformar futebol de empresa em uma experiencia social completa: feed, comentarios, reacoes, eventos, ranking, presenca, perfil personalizavel e metricas com clima de jogo.

O objetivo nao e ser apenas um CRUD bonito. A proposta e parecer produto real: identidade visual Conversys, app instalavel no celular, fluxo de administracao, aprovacao de gols e perfil com personalizacao estilo rede social moderna.

## O que a plataforma faz

- **Feed social esportivo** com posts, fotos/GIFs, comentarios, respostas e reacoes.
- **Reacoes com significado** para alimentar metricas do perfil: torcida, golaco, churras, resenha, midia e bebedeira.
- **Eventos da firma** com presenca, capacidade, filtros e cadastro controlado por admin.
- **Sistema de gols com aprovacao**: o jogador informa gols em um post/evento, mas o admin aprova antes de virar ponto.
- **Perfil de jogador** com foto, banner, bio, time preferido, jogador favorito e posicao em campo.
- **Radar de status da firma** inspirado em games de futebol, mas com metricas sociais e internas.
- **Escalacao visual** mostrando onde o usuario joga no campo.
- **Bordas personalizaveis** para foto e banner, incluindo temas Conversys, Copa 2026, selecoes e Nitro+.
- **Selo verificado** controlavel no perfil.
- **PWA instalavel** para adicionar na tela inicial do Android e iPhone.
- **Login Microsoft Entra ID** preparado para contas corporativas Conversys.

## Experiencia de produto

A interface foi desenhada para parecer uma rede social esportiva interna, nao um prototipo generico:

- Paleta inspirada no brand system da Conversys.
- Layout responsivo para desktop e mobile.
- Feed com ergonomia de app social.
- Perfil com destaque para avatar, banner, estatisticas e identidade do jogador.
- Efeitos visuais controlados, com foco em bordas e microinteracoes.

## Stack

| Camada | Tecnologias |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, CSS moderno, Lucide React |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Banco | SQLite local por padrao, PostgreSQL via Docker Compose |
| Auth | Login local de desenvolvimento e Microsoft Entra ID |
| App | Manifest PWA, service worker, icons maskable/apple |
| Qualidade | ESLint, Next build, Python compile check, GitHub Actions |

## Estrutura

```txt
Fut-conversys/
├── backend/                 # API FastAPI, modelos e regras de negocio
├── frontend/                # App Next.js com UI, PWA e rotas
├── .github/                 # CI, templates de issue e PR
├── docker-compose.yml       # PostgreSQL local opcional
├── start-dev.sh             # Atalho para subir backend + frontend no macOS/Linux
├── start-dev.bat            # Atalho para Windows
└── README.md
```

## Como rodar localmente

### 1. Clone o repositorio

```bash
git clone git@github.com:MatheusRenzo/Fut-conversys.git
cd Fut-conversys
```

### 2. Configure o backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Por padrao, o backend usa SQLite local:

```env
DATABASE_URL=sqlite:///./conversys_fut.db
```

Para usar PostgreSQL, suba o Docker Compose e ajuste o `DATABASE_URL`:

```bash
docker compose up -d db
```

### 3. Configure o frontend

```bash
cd ../frontend
npm install
cp .env.example .env.local
```

### 4. Rode a aplicacao

Em dois terminais:

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm run dev
```

Ou use o atalho na raiz:

```bash
./start-dev.sh
```

Acesse:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## Login de desenvolvimento

O backend cria um usuario admin local usando variaveis de ambiente:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=redacted@example.com
```

> Para publicar ou rodar em ambiente real, troque as credenciais no `.env` e nunca suba esse arquivo para o GitHub.

## Microsoft Entra ID

O login corporativo esta preparado para Microsoft Entra ID. Configure:

```env
MICROSOFT_CLIENT_ID=
MICROSOFT_TENANT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_REDIRECT_URI=http://localhost:3000/api/auth/callback/microsoft
```

Veja tambem: [MICROSOFT_ENTRA_SETUP.md](MICROSOFT_ENTRA_SETUP.md)

## Scripts uteis

### Frontend

```bash
cd frontend
npm run dev
npm run lint
npm run build
npm run start
```

### Backend

```bash
cd backend
python -m py_compile main.py models.py database.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Open source

Este repo esta preparado para comunidade:

- [x] Licenca MIT
- [x] Guia de contribuicao
- [x] Codigo de conduta
- [x] Politica de seguranca
- [x] Templates de issue e pull request
- [x] CI com validacao de frontend e backend
- [x] `.env.example` sem credenciais reais
- [x] `.gitignore` para proteger banco, venv, build e segredos

## Roadmap

- Ranking por temporada.
- Galeria de momentos dos eventos.
- Moderacao de midias.
- Sistema de conquistas.
- Notificacoes push PWA.
- Loja de personalizacao para bordas e identidade do perfil.
- Painel administrativo mais completo para eventos, gols e usuarios.

## Autor

Feito por **Matheus Renzo** como projeto de produto interno/social para futebol corporativo.

Se este projeto te inspirar, deixe uma estrela no repo e acompanhe a evolucao.
