#!/usr/bin/env python3
"""Gera HTML do e-mail de deploy Fut Conversys (bolão)."""
from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def esc(value: str | None) -> str:
    return html.escape((value or "").strip(), quote=True)


def build_deploy_email(
    *,
    success: bool,
    commit_message: str,
    commit_sha: str,
    commit_short: str,
    branch: str,
    actor: str,
    repository: str,
    run_url: str,
    app_url: str,
    timestamp: str,
    error_log: str = "",
) -> str:
    status_label = "Deploy concluído" if success else "Falha no deploy"
    status_color = "#61a229" if success else "#ff5c7a"
    status_bg = "rgba(97,162,41,0.18)" if success else "rgba(255,92,122,0.16)"
    headline = "Bolão no ar" if success else "Deploy interrompido"
    intro = (
        "O Fut Conversys foi publicado com sucesso. Placar ao vivo, intervalo e fluxo por gol estão atualizados."
        if success
        else "O pipeline de produção encontrou um erro. Revise o log abaixo e os detalhes no GitHub Actions."
    )
    error_block = ""
    if not success and error_log.strip():
        error_block = f"""
        <tr><td style="padding:0 28px 22px;">
          <div style="border:1px solid rgba(255,92,122,0.45);border-radius:14px;background:rgba(255,92,122,0.08);padding:16px 18px;">
            <div style="font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#ff9cb0;margin-bottom:10px;">Erro / log</div>
            <pre style="margin:0;white-space:pre-wrap;word-break:break-word;font:500 12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#ffd7df;">{esc(error_log)}</pre>
          </div>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(status_label)} — Fut Conversys</title>
</head>
<body style="margin:0;padding:24px 12px;background:#020b18;font-family:Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8f2ff;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:0 auto;">
    <tr><td style="padding:8px 8px 18px;text-align:center;">
      <div style="display:inline-block;padding:8px 14px;border-radius:999px;background:linear-gradient(135deg,#005aff,#00cfb4);color:#fff;font-size:11px;font-weight:900;letter-spacing:0.14em;text-transform:uppercase;">Fut Conversys</div>
      <div style="margin-top:14px;font-size:28px;font-weight:900;line-height:1.15;color:#ffffff;">{esc(headline)}</div>
      <div style="margin-top:8px;font-size:14px;line-height:1.6;color:#9eb4d8;">{esc(intro)}</div>
    </td></tr>
    <tr><td>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-radius:22px;overflow:hidden;border:1px solid rgba(0,207,180,0.22);background:linear-gradient(180deg,rgba(4,30,66,0.96),rgba(5,28,44,0.98));box-shadow:0 18px 50px rgba(0,0,0,0.35);">
        <tr><td style="padding:22px 28px 10px;">
          <span style="display:inline-block;padding:6px 12px;border-radius:999px;background:{status_bg};color:{status_color};font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">{esc(status_label)}</span>
        </td></tr>
        <tr><td style="padding:4px 28px 18px;">
          <div style="font-size:12px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#7f97bb;margin-bottom:8px;">Commit</div>
          <div style="font-size:16px;font-weight:700;line-height:1.45;color:#ffffff;">{esc(commit_message or "(sem mensagem)")}</div>
          <div style="margin-top:8px;font-size:12px;color:#8ea4c7;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">{esc(commit_short)} · {esc(branch)}</div>
        </td></tr>
        <tr><td style="padding:0 28px 18px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-spacing:0 8px;">
            <tr>
              <td style="width:50%;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);vertical-align:top;">
                <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#7f97bb;">Autor</div>
                <div style="margin-top:6px;font-size:14px;font-weight:700;color:#fff;">{esc(actor)}</div>
              </td>
              <td style="width:50%;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);vertical-align:top;">
                <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#7f97bb;">Hora (UTC)</div>
                <div style="margin-top:6px;font-size:14px;font-weight:700;color:#fff;">{esc(timestamp)}</div>
              </td>
            </tr>
            <tr>
              <td colspan="2" style="padding:12px 14px;border-radius:12px;background:rgba(227,28,121,0.08);border:1px solid rgba(227,28,121,0.22);">
                <div style="font-size:10px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#f3a6c8;">Módulo</div>
                <div style="margin-top:6px;font-size:14px;font-weight:700;color:#fff;">Bolão · placar ao vivo · intervalo · pipeline por gol</div>
              </td>
            </tr>
          </table>
        </td></tr>
        {error_block}
        <tr><td style="padding:6px 28px 24px;">
          <a href="{esc(app_url)}" style="display:inline-block;margin-right:10px;padding:12px 18px;border-radius:12px;background:linear-gradient(135deg,#e31c79,#005aff);color:#fff;text-decoration:none;font-size:13px;font-weight:800;">Abrir bolão</a>
          <a href="{esc(run_url)}" style="display:inline-block;padding:12px 18px;border-radius:12px;border:1px solid rgba(0,207,180,0.35);color:#9fe8de;text-decoration:none;font-size:13px;font-weight:700;">Ver pipeline</a>
        </td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:18px 8px 0;text-align:center;font-size:11px;line-height:1.6;color:#6f86a8;">
      {esc(repository)} · SHA {esc(commit_sha[:12])}<br/>Notificação automática do deploy Fut Conversys
    </td></tr>
  </table>
</body>
</html>"""


def main() -> int:
    success = os.environ.get("DEPLOY_STATUS", "success").lower() == "success"
    commit_message = os.environ.get("COMMIT_MESSAGE", "")
    commit_sha = os.environ.get("COMMIT_SHA", "")
    commit_short = os.environ.get("COMMIT_SHORT", commit_sha[:7])
    branch = os.environ.get("BRANCH", "main")
    actor = os.environ.get("ACTOR", "github-actions")
    repository = os.environ.get("REPOSITORY", "MatheusRenzo/Fut-conversys")
    run_url = os.environ.get("RUN_URL", "https://github.com/MatheusRenzo/Fut-conversys/actions")
    app_url = os.environ.get("APP_URL", "https://fut.conversys.global:9443/bolao")
    timestamp = os.environ.get("TIMESTAMP") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    error_log = os.environ.get("ERROR_LOG", "")
    if not error_log and os.environ.get("ERROR_LOG_FILE"):
        p = Path(os.environ["ERROR_LOG_FILE"])
        if p.exists():
            error_log = p.read_text(encoding="utf-8", errors="replace")[-6000:]

    out = Path(os.environ.get("OUTPUT_FILE", "deploy-email.html"))
    out.write_text(
        build_deploy_email(
            success=success,
            commit_message=commit_message,
            commit_sha=commit_sha,
            commit_short=commit_short,
            branch=branch,
            actor=actor,
            repository=repository,
            run_url=run_url,
            app_url=app_url,
            timestamp=timestamp,
            error_log=error_log,
        ),
        encoding="utf-8",
    )
    print(f"HTML gerado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
