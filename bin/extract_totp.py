#!/usr/bin/env python3
"""Extrai o segredo TOTP de um payload otpauth-migration do Google Authenticator
e grava em PJE_TOTP_SECRET no .env — SEM imprimir o segredo na tela.

Como obter o payload: Google Authenticator -> Transferir contas -> Exportar ->
selecione a conta do PJe -> aparece um QR. Leia esse QR (com 2º aparelho / leitor)
para obter a string `otpauth-migration://offline?data=...`. Salve essa string num
arquivo (ex.: ~/ga.txt) para não expô-la, e rode:

    .venv/bin/python bin/extract_totp.py ~/ga.txt            # lista as contas
    .venv/bin/python bin/extract_totp.py ~/ga.txt --write 0  # grava a conta [0] no .env

Depois apague o arquivo (rm ~/ga.txt).
"""
import sys, os, base64, urllib.parse, re


def read_varint(b, i):
    shift = result = 0
    while True:
        byte = b[i]; i += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, i
        shift += 7


def parse_fields(b):
    """Itera campos protobuf: (field_number, wire_type, valor)."""
    i, n, out = 0, len(b), []
    while i < n:
        key, i = read_varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            val, i = read_varint(b, i)
        elif wt == 2:
            ln, i = read_varint(b, i)
            val = b[i:i + ln]; i += ln
        elif wt == 5:
            val = b[i:i + 4]; i += 4
        elif wt == 1:
            val = b[i:i + 8]; i += 8
        else:
            raise ValueError(f"wire type {wt} não suportado")
        out.append((fn, wt, val))
    return out


def extrair_contas(text):
    text = text.strip()
    # QR direto do PJe: otpauth://totp/LABEL?secret=BASE32&issuer=...
    if text.lower().startswith("otpauth://totp/"):
        u = urllib.parse.urlparse(text)
        q = urllib.parse.parse_qs(u.query)
        secret = (q.get("secret") or [""])[0].replace(" ", "").upper()
        if not secret:
            return []
        label = urllib.parse.unquote(u.path.lstrip("/"))
        return [((q.get("issuer") or [""])[0], label, secret)]

    m = re.search(r"data=([^&\s]+)", text)
    data_b64 = urllib.parse.unquote(m.group(1)) if m else text.strip()
    raw = base64.b64decode(data_b64)
    contas = []
    for fn, wt, val in parse_fields(raw):
        if fn == 1 and wt == 2:  # otp_parameters
            secret = name = issuer = None
            for f2, w2, v2 in parse_fields(val):
                if f2 == 1 and w2 == 2:
                    secret = v2
                elif f2 == 2 and w2 == 2:
                    name = v2.decode("utf-8", "replace")
                elif f2 == 3 and w2 == 2:
                    issuer = v2.decode("utf-8", "replace")
            if secret:
                b32 = base64.b32encode(secret).decode().rstrip("=")
                contas.append((issuer or "", name or "", b32))
    return contas


def gravar_env(b32):
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    linhas = []
    if os.path.exists(env):
        linhas = open(env, encoding="utf-8").read().splitlines()
    linhas = [l for l in linhas if not l.startswith("PJE_TOTP_SECRET=")]
    linhas.append(f"PJE_TOTP_SECRET={b32}")
    with open(env, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    # Validação: gera um código sem mostrar o segredo
    try:
        import pyotp
        codigo = pyotp.TOTP(b32).now()
        print(f"OK: PJE_TOTP_SECRET gravado no .env. Código atual de teste: {codigo}")
    except Exception as e:
        print(f"Gravado, mas validação pyotp falhou: {e}")


def ler_qr_imagem(path):
    """Decodifica o(s) QR de uma imagem e devolve o texto otpauth-migration."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        raise SystemExit(f"não consegui abrir a imagem: {path}")
    det = cv2.QRCodeDetector()
    ok, decoded, _, _ = det.detectAndDecodeMulti(img)
    textos = [t for t in decoded if t] if ok else []
    if not textos:
        t, _, _ = det.detectAndDecode(img)
        if t:
            textos = [t]
    if not textos:
        raise SystemExit("nenhum QR detectado na imagem.")
    for t in textos:
        if "otpauth" in t or "data=" in t:
            return t
    return textos[0]


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    if os.path.exists(src) and src.lower().endswith((".png", ".jpg", ".jpeg", ".heic", ".webp")):
        text = ler_qr_imagem(src)
    elif os.path.exists(src):
        text = open(src, encoding="utf-8").read()
    else:
        text = src
    contas = extrair_contas(text)
    if not contas:
        print("Nenhuma conta TOTP encontrada no payload."); sys.exit(2)
    if "--write" in sys.argv:
        idx = int(sys.argv[sys.argv.index("--write") + 1])
        iss, nm, b32 = contas[idx]
        print(f"Gravando conta [{idx}] issuer='{iss}' name='{nm}'")
        gravar_env(b32)
    else:
        print(f"{len(contas)} conta(s) encontrada(s) (segredo oculto):")
        for i, (iss, nm, b32) in enumerate(contas):
            print(f"  [{i}] issuer='{iss}' name='{nm}'  segredo={b32[:3]}…{b32[-2:]} ({len(b32)} chars)")
        print("\nUse: --write <índice> para gravar a conta certa no .env")


if __name__ == "__main__":
    main()
