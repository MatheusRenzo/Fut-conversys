"use client";

import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    navigator.serviceWorker.register("/sw.js").catch(() => {
      // A instalação do app não deve bloquear o uso normal se o navegador recusar o SW.
    });
  }, []);

  return null;
}
