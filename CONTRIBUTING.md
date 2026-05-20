# Contribuindo com o Fut Conversys

Obrigado por querer melhorar o Fut Conversys. A ideia do projeto e ser uma referencia de produto social esportivo interno, com codigo claro, experiencia visual forte e fluxo simples para rodar localmente.

## Como começar

1. Faca um fork do repositorio.
2. Crie uma branch com nome objetivo:
   ```bash
   git checkout -b feat/nome-da-feature
   ```
3. Configure os ambientes usando `backend/.env.example` e `frontend/.env.example`.
4. Rode frontend e backend localmente.
5. Abra um pull request explicando o que mudou e como foi testado.

## Padrao de qualidade

- Prefira mudancas pequenas e bem descritas.
- Mantenha o visual alinhado a paleta da Conversys.
- Evite dados sensiveis, credenciais e arquivos locais no commit.
- Antes do PR, rode:
  ```bash
  cd frontend && npm run lint && npm run build
  cd .. && python3 -m py_compile backend/main.py backend/models.py
  ```

## Commits

Use mensagens curtas e claras. Exemplos:

- `feat: add goal approval workflow`
- `fix: align profile banner border motion`
- `docs: improve setup guide`
