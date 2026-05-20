# Politica de seguranca

Se voce encontrar uma vulnerabilidade, por favor nao abra uma issue publica com detalhes exploraveis.

Envie um relato privado para o mantenedor do projeto com:

- Descricao do problema.
- Passos para reproduzir.
- Impacto esperado.
- Versao, commit ou ambiente usado.

## Escopo inicial

O Fut Conversys ainda e um projeto em evolucao. Os pontos mais sensiveis sao:

- Autenticacao local e Microsoft Entra ID.
- Aprovacao administrativa de gols.
- Upload/uso de imagens em perfil, posts e comentarios.
- Dados de perfil dos usuarios.

Credenciais reais nunca devem ser commitadas. Use sempre `.env.example` como base.
