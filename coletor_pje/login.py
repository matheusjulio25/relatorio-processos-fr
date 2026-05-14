"""Login no PJe TRF5.

Estratégia: usar o Chrome do sistema (channel="chrome") com perfil persistente,
deixando o macOS Keychain apresentar o certificado A1. Evita o proxy interno
de mTLS do Playwright, que quebra o handshake com o WAF do TRF5.

Pré-requisito (1x): importar o .pfx no Keychain (duplo-clique no arquivo,
informar a senha). Em "Acesso aos chaveiros", marcar o certificado como
"Sempre confiar" e em "Controle de acesso" permitir o Google Chrome.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import BrowserContext, async_playwright

load_dotenv()

PJE_BASE_URL = os.getenv("PJE_BASE_URL", "https://pje1g.trf5.jus.br")
PJE_LOGIN_URL = os.getenv("PJE_LOGIN_URL", f"{PJE_BASE_URL}/pje/login.seam")

PROFILE_DIR = Path(
    os.getenv("BROWSER_PROFILE", str(Path(__file__).resolve().parent.parent / "browser-profile"))
)


@asynccontextmanager
async def pje_context(headless: bool = False):
    """Contexto Playwright já autenticado via certificado do Keychain.

    Roda preferencialmente headed na primeira vez para você selecionar o
    certificado quando o macOS pedir. As escolhas são lembradas no perfil
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

        cert_button = page.get_by_role("button", name="Certificado digital")
        if await cert_button.count() == 0:
            cert_button = page.locator("text=Certificado").first
        if await cert_button.count() > 0:
            await cert_button.click()

        try:
            await page.wait_for_url(f"{PJE_BASE_URL}/**", timeout=120_000)
        except Exception:
            pass
        try:
            yield ctx
        finally:
            await ctx.close()
