"""Login no PJe TRF5 via certificado digital A1."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Browser, BrowserContext, async_playwright

load_dotenv()

PJE_BASE_URL = os.getenv("PJE_BASE_URL", "https://pje1g.trf5.jus.br")
PJE_LOGIN_URL = os.getenv("PJE_LOGIN_URL", f"{PJE_BASE_URL}/pje/login.seam")
SSO_ORIGIN = "https://sso.cloud.pje.jus.br"


def _cert_config() -> dict:
    pfx = os.getenv("PFX_PATH")
    pwd = os.getenv("PFX_PASS")
    if not pfx or not pwd:
        raise RuntimeError("PFX_PATH e PFX_PASS precisam estar definidos no .env")
    if not Path(pfx).is_file():
        raise FileNotFoundError(f"Certificado não encontrado: {pfx}")
    return {"origin": SSO_ORIGIN, "pfxPath": pfx, "passphrase": pwd}


@asynccontextmanager
async def pje_context(headless: bool = True):
    """Abre um contexto Playwright autenticado e já logado no PJe."""
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=headless)
        ctx: BrowserContext = await browser.new_context(
            client_certificates=[_cert_config()],
            accept_downloads=True,
        )
        page = await ctx.new_page()
        await page.goto(PJE_LOGIN_URL, wait_until="domcontentloaded")

        # Botão "Certificado digital" — seletor pode variar; ajuste após rodar headed.
        cert_button = page.get_by_role("button", name="Certificado digital")
        if await cert_button.count() == 0:
            cert_button = page.locator("text=Certificado").first
        await cert_button.click()

        await page.wait_for_url(f"{PJE_BASE_URL}/**", timeout=60_000)
        await page.close()
        try:
            yield ctx
        finally:
            await ctx.close()
            await browser.close()
