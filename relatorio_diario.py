#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relatório Diário de Processos - Fernandes & Rego Advogados
Lê notificações do PJe e INSS nos dois e-mails e gera relatório Word + Notion + E-mail.
"""

import imaplib
import email
import re
import os
import json
import subprocess
import smtplib
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from dotenv import load_dotenv

# Carrega configurações do .env (na mesma pasta do script)
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# ─── CONFIGURAÇÕES ───────────────────────────────────────────────────────────
IMAP_SERVER   = os.getenv("IMAP_SERVER", "mail4.deploycloud.com.br")
IMAP_PORT     = int(os.getenv("IMAP_PORT", "993"))
CONTAS        = [
    {"email": os.getenv("EMAIL_1", "matheus@fernandeserego.adv.br"),
     "senha": os.getenv("SENHA_1", ""),
     "label": "Matheus"},
    {"email": os.getenv("EMAIL_2", "administrativo@fernandeserego.adv.br"),
     "senha": os.getenv("SENHA_2", ""),
     "label": "Administrativo"},
]
DIAS          = int(os.getenv("DIAS_HISTORICO", "1"))
NOTION_TOKEN  = os.getenv("NOTION_TOKEN", "")
NOTION_PAGE   = os.getenv("NOTION_PAGE_ID", "")
OUTPUT_DIR    = Path(__file__).parent

# ─── CONFIGURAÇÕES DE ENVIO DE E-MAIL ────────────────────────────────────────
SMTP_SERVER   = os.getenv("SMTP_SERVER", "mail4.deploycloud.com.br")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
EMAIL_ENVIO   = os.getenv("EMAIL_ENVIO", "matheus@fernandeserego.adv.br")
SENHA_ENVIO   = os.getenv("SENHA_ENVIO", "")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO", "leticia@fernandeserego.adv.br")

# ─── REMETENTES CONHECIDOS (PJe / INSS) ──────────────────────────────────────
REMETENTES_PJE  = [
    "noreply@pje.jus.br", "pje@trf", "pje@tjsp", "pje@trt",
    "noreply@cni.jus.br", "intimacao@", "notificacao@pje", "pje@trf1",
    "pje@trf3", "pje@trf4", "naoresponda@pje", "pje1g@", "pje2g@",
    "comunicacao@", "noreply@trf", "noreply@tjsp", "noreply@trt",
]
REMETENTES_INSS = [
    "noreply@inss.gov.br", "noreply@previdencia.gov.br", "meu.inss@",
    "atendimento@inss", "gestao@inss", "noreply@inss",
    "noreply@meu.inss.gov.br",
]

# ─── PALAVRAS-CHAVE DE URGÊNCIA ───────────────────────────────────────────────
URGENCIA_ALTA  = ["prazo", "improrrogável", "citação", "mandado", "liminar",
                  "urgente", "imediato", "tutela", "medida cautelar",
                  "bloqueio", "penhora", "leilão", "arresto", "fatal",
                  "peremptório", "decadência", "prescrição"]
URGENCIA_MEDIA = ["intimação", "vista", "manifestação", "audiência",
                  "julgamento", "pauta", "despacho", "notificação",
                  "perícia", "laudo", "recurso", "apelação", "contestação",
                  "resposta", "impugnação"]


def decodificar_header(valor):
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = []
    for parte, enc in partes:
        if isinstance(parte, bytes):
            # Trata encodings desconhecidos com fallback
            enc_safe = enc if enc and enc.lower() not in ("unknown-8bit", "unknown") else "latin-1"
            resultado.append(parte.decode(enc_safe, errors="replace"))
        else:
            resultado.append(str(parte))
    return " ".join(resultado)


def extrair_corpo(msg):
    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    # Tenta detectar encoding do part
                    enc = part.get_content_charset() or "utf-8"
                    if enc.lower() in ("unknown-8bit", "unknown"):
                        enc = "latin-1"
                    corpo += payload.decode(enc, errors="replace")
            elif ct == "text/html" and not corpo:
                payload = part.get_payload(decode=True)
                if payload:
                    enc = part.get_content_charset() or "utf-8"
                    if enc.lower() in ("unknown-8bit", "unknown"):
                        enc = "latin-1"
                    texto = payload.decode(enc, errors="replace")
                    texto = re.sub(r"<[^>]+>", " ", texto)
                    texto = re.sub(r"\s+", " ", texto).strip()
                    corpo += texto
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            corpo = payload.decode("utf-8", errors="replace")
    return corpo[:3000]


def extrair_numero_processo(texto):
    padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
    matches = re.findall(padrao, texto)
    return matches[0] if matches else None


def extrair_prazo(texto):
    padroes = [
        r"prazo de (\d+) dias?",
        r"até (\d{1,2}/\d{1,2}/\d{4})",
        r"até o dia (\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4}).*?prazo",
        r"vence em (\d{1,2}/\d{1,2}/\d{4})",
    ]
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def classificar_urgencia(assunto, corpo):
    texto = (assunto + " " + corpo).lower()
    for kw in URGENCIA_ALTA:
        if kw in texto:
            return "ALTA"
    for kw in URGENCIA_MEDIA:
        if kw in texto:
            return "MEDIA"
    return "BAIXA"


def e_notificacao_relevante(remetente):
    rem = remetente.lower()
    for r in REMETENTES_PJE + REMETENTES_INSS:
        if r in rem:
            return True
    return False


def origem_notificacao(remetente):
    rem = remetente.lower()
    for r in REMETENTES_INSS:
        if r in rem:
            return "INSS"
    return "PJe"


def buscar_emails(conta):
    notificacoes = []
    print(f"  Conectando em {conta['email']}...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(conta["email"], conta["senha"])
        mail.select("INBOX")

        desde = (datetime.now() - timedelta(days=DIAS)).strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{desde}")')
        ids_lista = ids[0].split()
        print(f"  {len(ids_lista)} e-mails encontrados desde {desde}")

        for uid in ids_lista:
            _, data = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])

            remetente = decodificar_header(msg.get("From", ""))
            assunto   = decodificar_header(msg.get("Subject", "(sem assunto)"))
            data_msg  = msg.get("Date", "")

            if not e_notificacao_relevante(remetente):
                continue

            corpo    = extrair_corpo(msg)
            processo = extrair_numero_processo(assunto + " " + corpo)
            prazo    = extrair_prazo(corpo)
            urgencia = classificar_urgencia(assunto, corpo)
            origem   = origem_notificacao(remetente)

            notificacoes.append({
                "conta":    conta["label"],
                "origem":   origem,
                "assunto":  assunto,
                "processo": processo or "Não identificado",
                "prazo":    prazo or "—",
                "urgencia": urgencia,
                "data":     data_msg[:25] if data_msg else "—",
                "corpo":    corpo[:500],
            })

        mail.logout()
    except Exception as e:
        print(f"  ERRO em {conta['email']}: {e}")

    return notificacoes


def coletar_todas_notificacoes():
    todas = []
    for conta in CONTAS:
        if not conta["senha"]:
            print(f"  [AVISO] Senha não configurada para {conta['email']} — pulando.")
            continue
        todas.extend(buscar_emails(conta))
    return todas


def gerar_json_para_docx(notificacoes, data_relatorio):
    payload = {
        "data":  data_relatorio,
        "total": len(notificacoes),
        "alta":  sum(1 for n in notificacoes if n["urgencia"] == "ALTA"),
        "media": sum(1 for n in notificacoes if n["urgencia"] == "MEDIA"),
        "baixa": sum(1 for n in notificacoes if n["urgencia"] == "BAIXA"),
        "notificacoes": notificacoes,
    }
    json_path = Path(__file__).parent / "relatorio_data.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return json_path


def gerar_docx(json_path, output_path):
    script = Path(__file__).parent / "gerar_relatorio.js"
    result = subprocess.run(
        ["node", str(script), str(json_path), str(output_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERRO ao gerar DOCX:\n{result.stderr}")
        return False
    return True


def salvar_notion(notificacoes, data_relatorio, docx_path):
    if not NOTION_TOKEN or not NOTION_PAGE:
        print("  [AVISO] Notion não configurado — pulando.")
        return
    try:
        from notion_client import Client
        notion = Client(auth=NOTION_TOKEN)

        alta  = [n for n in notificacoes if n["urgencia"] == "ALTA"]
        media = [n for n in notificacoes if n["urgencia"] == "MEDIA"]
        baixa = [n for n in notificacoes if n["urgencia"] == "BAIXA"]

        def bloco_texto(texto, bold=False):
            return {"object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [
                        {"type": "text", "text": {"content": texto[:2000]},
                         "annotations": {"bold": bold}}]}}

        def bloco_h2(texto):
            return {"object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [
                        {"type": "text", "text": {"content": texto}}]}}

        def bloco_item(n):
            emoji = "🔴" if n["urgencia"] == "ALTA" else ("🟡" if n["urgencia"] == "MEDIA" else "🟢")
            linha = f"{emoji} [{n['origem']}] {n['processo']} | Prazo: {n['prazo']} | {n['assunto'][:80]}"
            return bloco_texto(linha)

        blocos = [
            bloco_texto(
                f"📊 Total: {len(notificacoes)}  |  🔴 Alta: {len(alta)}  "
                f"🟡 Média: {len(media)}  🟢 Baixa: {len(baixa)}", bold=True),
        ]
        if alta:
            blocos.append(bloco_h2("🔴 Urgência Alta — Ação Imediata"))
            blocos.extend(bloco_item(n) for n in alta)
        if media:
            blocos.append(bloco_h2("🟡 Urgência Média — Acompanhar"))
            blocos.extend(bloco_item(n) for n in media)
        if baixa:
            blocos.append(bloco_h2("🟢 Urgência Baixa — Informativo"))
            blocos.extend(bloco_item(n) for n in baixa)
        blocos.append(bloco_texto(f"📄 Arquivo Word: {docx_path.name}"))

        notion.pages.create(
            parent={"page_id": NOTION_PAGE},
            properties={"title": [{"text": {"content": f"📋 {data_relatorio}"}}]},
            children=blocos[:100],
        )
        print("  ✓ Salvo no Notion.")
    except Exception as e:
        print(f"  ERRO ao salvar no Notion: {e}")


def enviar_por_email(docx_path, data_relatorio, resumo):
    if not SENHA_ENVIO:
        print("  [AVISO] SENHA_ENVIO não configurada — e-mail não enviado.")
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_ENVIO
        msg["To"]      = EMAIL_DESTINO
        msg["Subject"] = f"Relatório Diário de Processos — {data_relatorio}"

        corpo_email = (
            f"Olá,\n\n"
            f"Segue em anexo o Relatório Diário de Processos — {data_relatorio}.\n\n"
            f"Resumo:\n"
            f"  🔴 Urgência Alta:  {resumo['alta']}\n"
            f"  🟡 Urgência Média: {resumo['media']}\n"
            f"  🟢 Urgência Baixa: {resumo['baixa']}\n"
            f"  📋 Total:          {resumo['total']}\n\n"
            f"Fernandes & Rego Advogados Associados\n"
            f"(Mensagem gerada automaticamente)\n"
        )
        msg.attach(MIMEText(corpo_email, "plain", "utf-8"))

        with open(docx_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={docx_path.name}")
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_ENVIO, SENHA_ENVIO)
            server.send_message(msg)

        print(f"  ✓ E-mail enviado para {EMAIL_DESTINO}")
    except Exception as e:
        print(f"  ERRO ao enviar e-mail: {e}")


def main():
    data_relatorio = datetime.now().strftime("%d/%m/%Y")
    data_arquivo   = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  RELATÓRIO DIÁRIO — {data_relatorio}")
    print(f"{'='*55}")

    print("\n[1/4] Buscando notificações nos e-mails...")
    notificacoes = coletar_todas_notificacoes()
    print(f"  Total de notificações coletadas: {len(notificacoes)}")

    if not notificacoes:
        print("\n  Nenhuma notificação do PJe ou INSS nas últimas 24h.")
        print("  Relatório não gerado.\n")
        return

    print("\n[2/4] Gerando arquivo Word...")
    json_path   = gerar_json_para_docx(notificacoes, data_relatorio)
    output_path = OUTPUT_DIR / f"Relatorio_Diario_{data_arquivo}.docx"
    if gerar_docx(json_path, output_path):
        print(f"  ✓ Word salvo em: {output_path}")

    alta  = sum(1 for n in notificacoes if n["urgencia"] == "ALTA")
    media = sum(1 for n in notificacoes if n["urgencia"] == "MEDIA")
    baixa = sum(1 for n in notificacoes if n["urgencia"] == "BAIXA")
    resumo = {"alta": alta, "media": media, "baixa": baixa, "total": len(notificacoes)}

    print("\n[3/4] Salvando no Notion...")
    salvar_notion(notificacoes, data_relatorio, output_path)

    print("\n[3.5/4] Enviando relatório por e-mail...")
    enviar_por_email(output_path, data_relatorio, resumo)

    print("\n[4/4] Concluído!")
    print(f"  🔴 Alta: {alta}  |  🟡 Média: {media}  |  🟢 Baixa: {baixa}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
