"""Coletor do 1º grau (pje1g) — ConsultaProcesso.

Mesma lógica do turmas_recursais.py mas para as varas JEF do 1º grau.
Faz login no pje1g, pesquisa por INSS em varas específicas e baixa sentenças/decisões.
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

PJE1G_BASE_URL = os.getenv("PJE_BASE_URL", "https://pje1g.trf5.jus.br")
PJE1G_LOGIN_URL = f"{PJE1G_BASE_URL}/pje/login.seam"
PJE1G_CONSULTA_URL = f"{PJE1G_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
PJE_TOTP_SECRET = ler_segredo("PJE_TOTP_SECRET", "pje-totp-secret").replace(" ", "")

# Perfil separado para não conflitar com o acervo
_PROFILE_DIR_1G = Path(
    os.getenv("BROWSER_PROFILE_1G_CONSULTA",
              str(Path(__file__).resolve().parent.parent / "browser-profile-1g-consulta"))
)


def get_profile_dir_1g(sufixo: str = "") -> Path:
    base = str(_PROFILE_DIR_1G)
    return Path(f"{base}{sufixo}" if sufixo else base)


@asynccontextmanager
async def pje1g_consulta_context(headless: bool = False, sufixo: str = ""):
    """Login no pje1g para ConsultaProcesso (perfil separado do acervo)."""
    profile = get_profile_dir_1g(sufixo)
    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx: BrowserContext = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=headless,
            accept_downloads=True,
            locale="pt-BR",
            timezone_id="America/Recife",
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(PJE1G_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

        for sel in ("button:has-text('Certificado digital')", "text=Certificado"):
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click()
                break

        try:
            campo = page.locator(
                "input[type='text'][autocomplete='one-time-code'], input[name*='otp' i]"
            ).first
            await campo.wait_for(state="visible", timeout=8_000)
            if PJE_TOTP_SECRET:
                await campo.fill(pyotp.TOTP(PJE_TOTP_SECRET).now())
                btn = page.get_by_role("button", name="Validar")
                if await btn.count() == 0:
                    btn = page.locator("button[type='submit']").first
                await btn.click()
            else:
                print("[pje1g] 2FA — digite o código no navegador.")
        except Exception:
            pass

        try:
            await page.wait_for_selector("#tabAcervo_lbl, #formAbaAcervo", timeout=180_000)
        except Exception:
            try:
                await page.wait_for_url(f"{PJE1G_BASE_URL}/pje/**", timeout=30_000)
            except Exception:
                pass

        print(f"[pje1g-consulta] autenticado, url={page.url}")
        try:
            yield ctx
        finally:
            await ctx.close()


async def descobrir_varas_1g(page) -> list[dict]:
    """Navega para ConsultaProcesso e retorna todas as opções de órgão julgador."""
    await page.goto(PJE1G_CONSULTA_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)

    opcoes = await page.evaluate(
        """() => {
            // pje1g: orgaoJulgadorCombo (sem "Colegiado")
            const sel = document.querySelector('select[name*="orgaoJulgadorCombo"]') ||
                        document.querySelector('select[id*="orgaoJulgadorCombo"]') ||
                        document.querySelector('select[name*="orgaoJulgador"]');
            if (!sel) return [];
            return Array.from(sel.options).map(o => ({value: o.value, text: o.text.trim()}));
        }"""
    )
    return [o for o in opcoes if o['text'] and o['text'] != 'Selecione']


async def preencher_e_pesquisar_1g(page, orgao_value: str, orgao_nome: str,
                                    nome_parte: str, data_ini: str, data_fim: str) -> None:
    """Preenche o formulário de ConsultaProcesso do pje1g e submete."""
    await page.goto(PJE1G_CONSULTA_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)

    # Preenche via JS direto (sem acionar onchange que reseta o form)
    filled = await page.evaluate(
        """([orgaoVal, nomeParte, dataIni, dataFim]) => {
            const set = (sel, val) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                el.value = val;
                return true;
            };
            // pje1g usa orgaoJulgadorCombo (sem "Colegiado")
            const results = {
                orgao: set('select[name*="orgaoJulgadorCombo"]', orgaoVal) ||
                       set('select[id*="orgaoJulgadorCombo"]', orgaoVal),
                parte: set('input[name*="nomeParte"]', nomeParte) ||
                       set('input[id*="nomeParte"]', nomeParte),
                dataIni: set('input[name*="dataAutuacaoInicio"]', dataIni) ||
                         set('input[id*="dataAutuacaoInicio"]', dataIni),
                dataFim: set('input[name*="dataAutuacaoFim"]', dataFim) ||
                         set('input[id*="dataAutuacaoFim"]', dataFim),
            };
            return results;
        }""",
        [orgao_value, nome_parte, data_ini, data_fim],
    )
    print(f"[1g] form: orgao={filled.get('orgao')} parte={filled.get('parte')} "
          f"datas={filled.get('dataIni')}/{filled.get('dataFim')}")

    # Clica pesquisar (mesmo botão do pje2g)
    btn = page.locator('input[id*="searchProcessos"], input[value="Pesquisar"]').first
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(3_000)
        has_rows = await page.evaluate(
            "() => document.querySelectorAll('tr.rich-table-row').length > 0"
        )
        if not has_rows:
            await page.evaluate(
                """() => {
                    if (typeof A4J !== 'undefined' && A4J.AJAX) {
                        A4J.AJAX.Submit('fPP', null, {
                            'similarityGroupingId': 'fPP:searchProcessos',
                            'parameters': {'fPP:searchProcessos': 'fPP:searchProcessos'}
                        });
                    }
                }"""
            )
    await page.wait_for_timeout(5_000)


async def extrair_processos_pagina_1g(page) -> list[dict]:
    """Extrai processos da tabela de resultados (mesmo formato do pje2g)."""
    return await page.evaluate(
        """() => {
            const CNJ_RE = /\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
            const ID_RE = /idProcessoSelecionado['"]?\\s*:\\s*(\\d+)/;
            const rows = document.querySelectorAll(
                '#fPP\\\\:processosTable tr.rich-table-row, ' +
                '#fPP\\\\:processosTable tr[class*="row"]'
            );
            const items = [];
            for (const row of rows) {
                let cnj = '', procId = '', relatoria = '', linkEl = null;
                for (const td of row.querySelectorAll('td')) {
                    const txt = (td.textContent || '').trim();
                    if (CNJ_RE.test(txt)) {
                        cnj = txt.match(CNJ_RE)[0];
                        const a = td.querySelector('a');
                        if (a) {
                            linkEl = a;
                            const m = (a.getAttribute('onclick')||'').match(ID_RE);
                            if (m) procId = m[1];
                        }
                    }
                    if (txt.includes('Vara') || txt.includes('JEF')) {
                        relatoria = txt.trim().slice(0, 60);
                    }
                }
                if (!cnj && !procId) continue;
                if (!linkEl) linkEl = row.querySelector('a');
                if (linkEl && !linkEl.id)
                    linkEl.id = '_1g_' + Math.random().toString(36).slice(2);
                items.push({
                    id: linkEl ? linkEl.id : '',
                    cnj, proc_id: procId, relatoria,
                    texto: cnj,
                    onclick: linkEl ? (linkEl.getAttribute('onclick')||'') : '',
                });
            }
            return items;
        }"""
    )


async def ir_proxima_pagina_1g(page) -> bool:
    """Avança para próxima página nos resultados."""
    try:
        clicou = await page.evaluate(
            """() => {
                const btns = document.querySelectorAll('.rich-datascr-button, td.rich-datascr-button');
                const ativos = Array.from(btns).filter(b =>
                    !b.classList.contains('rich-datascr-button-dsbld'));
                if (ativos.length >= 2) {
                    const prox = ativos[ativos.length - 2];
                    const a = prox.querySelector('a');
                    if (a) { a.click(); return true; }
                    prox.click(); return true;
                }
                return false;
            }"""
        )
        if clicou:
            await page.wait_for_timeout(4_000)
        return bool(clicou)
    except Exception:
        return False


# Tipos de documentos de interesse no 1º grau
TIPOS_DOC_1G = ("sentença", "sentenca", "decisão", "decisao", "despacho")
TIPOS_VETO_1G = ("certidão", "certidao", "petição", "peticao", "contestação",
                  "contrarrazões", "recurso inominado")
