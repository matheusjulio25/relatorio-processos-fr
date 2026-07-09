"""Leitura de segredos com prioridade: variável de ambiente (.env) → Keychain do macOS.

Permite guardar segredos (ex.: TOTP do 2FA) no Keychain em vez de texto puro no .env.
Gravação é feita pelo script bin/cofre.sh (usa `security add-generic-password`)."""
from __future__ import annotations

import os
import subprocess


def ler_segredo(env_var: str, keychain_service: str) -> str:
    """Retorna o segredo. Prioridade: variável de ambiente; senão Keychain (macOS `security`).
    Retorna "" se não encontrado em nenhum lugar."""
    v = (os.getenv(env_var) or "").strip()
    if v:
        return v
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", keychain_service, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""
