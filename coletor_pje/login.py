"""Login no PJe TRF5.

Dois métodos, escolhidos por PJE_METODO_LOGIN (ou inferidos: "senha" quando
PJE_CPF está configurado, senão "certificado"):

- "senha": CPF + senha no formulário do PJe. Não depende de certificado nem do
  cofre do sistema operacional, então roda igual em macOS e Windows.
- "certificado": Chrome do sistema (channel="chrome") com perfil persistente,
  deixando o cofre do SO apresentar o certificado A1 — Keychain no macOS,
  repositório de certificados do usuário no Windows. Evita o proxy interno de
  mTLS do Playwright, que quebra o handshake com o WAF do TRF5.

Pré-requisito do certificado (1x): importar o .pfx no cofre do SO. No macOS,
duplo-clique no arquivo, informar a senha e, em "Acesso aos chaveiros", marcar
"Sempre confiar" e permitir o Google Chrome em "Controle de acesso".
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pyotp
from dotenv import load_dotenv
from playwright.async_api import BrowserContext, async_playwright

from .segredos import ler_segredo

load_dotenv()

PJE_BASE_URL = os.getenv("PJE_BASE_URL", "https://pje1g.trf5.jus.br")
PJE_LOGIN_URL = os.getenv("PJE_LOGIN_URL", f"{PJE_BASE_URL}/pje/login.seam")
PJE_TOTP_SECRET = ler_segredo("PJE_TOTP_SECRET", "pje-totp-secret").replace(" ", "")
PJE_CPF = ler_segredo("PJE_CPF", "pje-cpf").strip()
PJE_SENHA = ler_segredo("PJE_SENHA", "pje-senha")
PJE_METODO_LOGIN = (
    os.getenv("PJE_METODO_LOGIN") or ("senha" if PJE_CPF else "certificado")
).strip().lower()

PROFILE_DIR = Path(
    os.getenv("BROWSER_PROFILE", str(Path(__file__).resolve().parent.parent / "browser-profile"))
)

DEBUG_DIR = Path(os.getenv("DEBUG_DIR", "debug"))

# Seletor do painel autenticado — serve de confirmação de que o login passou.
PAINEL = "#tabAcervo_lbl, #formAbaAcervo"

# O formulário varia entre instâncias (Seam antigo x Keycloak), então tentamos
# vários nomes antes de cair no primeiro campo de texto visível.
CAMPO_USUARIO = (
    "#username, input[name='username'], input[id$=':username'], "
    "input[name*='cpf' i], input[id*='cpf' i], input[name*='usuario' i]"
)


async def _dump_debug(page, nome: str) -> None:
    """Screenshot + HTML para calibrar seletores quando algo não é encontrado."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(DEBUG_DIR / f"{nome}.png"), full_page=True)
        (DEBUG_DIR / f"{nome}.html").write_text(await page.content(), encoding="utf-8")
        print(f"[login] diagnóstico salvo em {DEBUG_DIR.resolve()}")
    except Exception:
        pass


async def _mensagem_erro(page) -> str | None:
    """Texto do erro de credencial, se o PJe exibiu algum."""
    for sel in ("#kc-error-message", ".alert-error", ".rich-messages-label", "span.error"):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                texto = (await loc.inner_text()).strip()
                if texto:
                    return texto[:200]
        except Exception:
            continue
    return None


async def _handle_totp(page) -> None:
    """Preenche o código TOTP se o PJe pedir 2FA.

    O segredo vem de PJE_TOTP_SECRET (base32). Sem segredo configurado, deixa
    o usuário digitar manualmente — útil enquanto o "lembrar dispositivo" do
    PJe ainda não confiou no perfil.
    """
    try:
        campo = page.locator(
            "input[type='text'][autocomplete='one-time-code'], input[name*='otp' i], input[name*='codigo' i]"
        ).first
        await campo.wait_for(state="visible", timeout=8_000)
    except Exception:
        return

    if not PJE_TOTP_SECRET:
        print("[login] 2FA detectado — digite o código no navegador.")
        return

    codigo = pyotp.TOTP(PJE_TOTP_SECRET).now()
    await campo.fill(codigo)
    botao = page.get_by_role("button", name="Validar")
    if await botao.count() == 0:
        botao = page.locator("button[type='submit']").first
    await botao.click()


async def _login_senha(page) -> None:
    """Preenche CPF + senha no formulário do PJe.

    Sem PJE_SENHA configurada, apenas preenche o CPF e devolve o controle: a
    senha é digitada no navegador (exige headed). Assim o coletor funciona sem
    que a senha precise ficar em texto puro em lugar nenhum.
    """
    senha = page.locator("input[type='password']").first

    async def campo_visivel(timeout: int) -> bool:
        try:
            await senha.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    if not await campo_visivel(5_000):
        # Só procura a aba quando não há campo à vista, e com texto específico:
        # "senha" solto casa com "Solicitar nova senha" e "Esqueci minha senha",
        # que levam para fora da tela de login.
        aba = page.get_by_role(
            "link", name=re.compile(r"CPF\s*/?\s*CNPJ|Usu[áa]rio\s+e\s+senha", re.I)
        )
        if await aba.count() > 0:
            try:
                await aba.first.click(timeout=3_000)
            except Exception:
                pass
        if not await campo_visivel(15_000):
            # Pode ter caído numa tela de recuperação: volta para o login.
            await page.goto(PJE_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            if not await campo_visivel(15_000):
                await _dump_debug(page, "login")
                raise RuntimeError(
                    "campo de senha não encontrado na página de login — veja debug/login.png"
                )

    usuario = page.locator(CAMPO_USUARIO).first
    if await usuario.count() == 0:
        usuario = page.locator("input[type='text']:visible").first
    if PJE_CPF:
        await usuario.fill(PJE_CPF)
    else:
        print("[login] PJE_CPF não configurado — digite o CPF no navegador.")

    if not PJE_SENHA:
        print("[login] PJE_SENHA não configurada — digite a senha no navegador e confirme.")
        return

    await senha.fill(PJE_SENHA)
    botao = page.get_by_role("button", name=re.compile(r"Entrar|Acessar", re.I))
    if await botao.count() == 0:
        botao = page.locator("input[type='submit'], button[type='submit']").first
    await botao.first.click()


@asynccontextmanager
async def pje_context(headless: bool = False):
    """Contexto Playwright já autenticado no PJe.

    Rode headed na primeira vez: é quando você digita a senha (ou escolhe o
    certificado, no método antigo) e resolve o 2FA. As escolhas ficam no perfil
    persistente, então execuções seguintes podem ir headless.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx: BrowserContext = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=headless,
            accept_downloads=True,
            locale="pt-BR",
            timezone_id="America/Recife",
            viewport={"width": 1366, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(PJE_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

        # Perfil persistente pode já estar autenticado — aí não há formulário.
        if await page.locator(PAINEL).count() == 0:
            print(f"[login] método: {PJE_METODO_LOGIN}")
            if PJE_METODO_LOGIN == "senha":
                await _login_senha(page)
            else:
                cert_button = page.get_by_role("button", name="Certificado digital")
                if await cert_button.count() == 0:
                    cert_button = page.locator("text=Certificado").first
                if await cert_button.count() > 0:
                    await cert_button.click()

            await _handle_totp(page)

        # Aguarda o painel principal (não apenas qualquer URL do domínio).
        # Se a senha/2FA for manual, dá 3 minutos para o usuário digitar.
        entrou = True
        try:
            await page.wait_for_selector(PAINEL, timeout=180_000)
        except Exception:
            try:
                await page.wait_for_url(f"{PJE_BASE_URL}/pje/Painel/**", timeout=30_000)
            except Exception:
                entrou = False

        if not entrou:
            msg = await _mensagem_erro(page)
            await _dump_debug(page, "login")
            if msg:
                raise RuntimeError(f"login recusado pelo PJe: {msg}")
            print("[login] AVISO: painel não confirmado — o contexto pode não estar autenticado.")

        try:
            yield ctx
        finally:
            await ctx.close()
