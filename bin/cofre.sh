#!/bin/bash
# Cofre de credenciais do PJe no Keychain do macOS.
# O coletor lê o TOTP via coletor_pje/segredos.py (env -> Keychain).
#
# Uso:
#   bin/cofre.sh totp-from-env   # move PJE_TOTP_SECRET do .env para o Keychain e limpa o .env
#   bin/cofre.sh totp            # pede o segredo TOTP (oculto) e guarda no Keychain
#   bin/cofre.sh cert            # pede a senha do certificado A1 (oculta) e guarda no Keychain
#   bin/cofre.sh check           # verifica o que está guardado (sem revelar valores)
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SVC_TOTP="pje-totp-secret"
SVC_CERT="pje-cert-a1-pass"
ACC="${USER}"

guarda() {  # $1=service  $2=valor
  security add-generic-password -a "$ACC" -s "$1" -w "$2" -U \
    -l "PJE: $1" -j "Coletor relatorio-processos-fr" 2>/dev/null
}

case "${1:-}" in
  totp-from-env)
    val="$(grep -E '^PJE_TOTP_SECRET=.+' "$REPO/.env" | head -1 | cut -d= -f2-)"
    if [ -z "$val" ]; then echo "Nada em PJE_TOTP_SECRET no .env."; exit 1; fi
    guarda "$SVC_TOTP" "$val" && echo "OK: TOTP guardado no Keychain ($SVC_TOTP)."
    # limpa o valor do .env (deixa a chave vazia)
    sed -i '' -E 's/^PJE_TOTP_SECRET=.*/PJE_TOTP_SECRET=/' "$REPO/.env"
    echo "OK: removido o valor do .env (chave deixada vazia; o coletor lê do Keychain)."
    unset val
    ;;
  totp)
    read -rsp "Segredo TOTP (base32): " val; echo
    [ -z "$val" ] && { echo "vazio, abortei."; exit 1; }
    guarda "$SVC_TOTP" "$val" && echo "OK: TOTP guardado no Keychain ($SVC_TOTP)."
    unset val
    ;;
  cert)
    read -rsp "Senha do certificado A1: " val; echo
    [ -z "$val" ] && { echo "vazio, abortei."; exit 1; }
    guarda "$SVC_CERT" "$val" && echo "OK: senha do cert A1 guardada no Keychain ($SVC_CERT)."
    unset val
    ;;
  check)
    security find-generic-password -s "$SVC_TOTP" >/dev/null 2>&1 \
      && echo "TOTP    ($SVC_TOTP): ✅ guardado" || echo "TOTP    ($SVC_TOTP): ❌ ausente"
    security find-generic-password -s "$SVC_CERT" >/dev/null 2>&1 \
      && echo "Cert A1 ($SVC_CERT): ✅ guardado" || echo "Cert A1 ($SVC_CERT): ❌ ausente"
    ;;
  *)
    echo "uso: bin/cofre.sh <totp-from-env|totp|cert|check>"
    exit 1
    ;;
esac
