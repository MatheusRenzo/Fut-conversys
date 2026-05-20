# Frontend do Fut Conversys

Este diretorio contem o app web/PWA do Fut Conversys, construido com Next.js, React e TypeScript.

Para a documentacao completa do projeto, veja o [README da raiz](../README.md).

## Scripts

```bash
npm run dev
npm run lint
npm run build
npm run start
```

O frontend conversa com a API FastAPI pelo proxy `/api/backend/*` e tambem pode usar `NEXT_PUBLIC_API_URL` configurado em `.env.local`.
