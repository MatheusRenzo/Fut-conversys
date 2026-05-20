# Microsoft Entra setup

O MVP já tem campos de usuário e endpoint de configuração preparados para Microsoft Auth. A integração OAuth completa depende das credenciais do Microsoft Entra.

## Criar o app

1. Acesse o Microsoft Entra admin center.
2. Entre em **App registrations** e crie um novo registro.
3. Use um nome como `Conversys Fut`.
4. Configure o redirect URI de desenvolvimento:

```text
http://localhost:3000/api/auth/callback/microsoft
```

5. Copie o **Application (client) ID** e o **Directory (tenant) ID**.
6. Crie um client secret em **Certificates & secrets**.

## Variáveis esperadas

Adicione no ambiente do backend quando for ativar:

```bash
MICROSOFT_CLIENT_ID="..."
MICROSOFT_TENANT_ID="..."
MICROSOFT_CLIENT_SECRET="..."
MICROSOFT_REDIRECT_URI="http://localhost:3000/api/auth/callback/microsoft"
```

## Verificação Conversys

O backend considera verificado quem tiver email terminando com:

```text
@conversys.global
```

Quando o fluxo Microsoft for ligado, o usuário deve ser criado/atualizado com `provider="microsoft_entra"`, `provider_subject`, `tenant_id`, `email`, `avatar_url` e `verified_domain=true` quando o domínio bater.
