"""Coletor das Turmas Recursais PE — pje2g.trf5.jus.br.

Fluxo:
  1. Login no pje2g com certificado A1.
  2. Navega para ConsultaProcesso/listView.seam.
  3. Para cada Turma Recursal PE (1ª/2ª/3ª), preenche:
       - Órgão julgador: select com value 29/33/35
       - Nome da parte: INSS
       - Data autuação: data_inicio → data_fim
  4. Percorre TODAS as páginas de resultados.
  5. Para cada processo, abre o detalhe e baixa:
       voto do relator, acórdão, ementa.
  6. Extrai: relator, resultado, ementa.
  7. Persiste em mapas/juizes_tr.json + mapas/acordaos_tr/.
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

TR_BASE_URL = os.getenv("PJE2G_BASE_URL", "https://pje2g.trf5.jus.br")
TR_LOGIN_URL = f"{TR_BASE_URL}/pje/login.seam"
TR_CONSULTA_URL = f"{TR_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
# Segredo TOTP: .env (se preenchido) ou Keychain do macOS (serviço 'pje-totp-secret')
PJE_TOTP_SECRET = ler_segredo("PJE_TOTP_SECRET", "pje-totp-secret").replace(" ", "")

# Perfil base — pode ser sobrescrito por get_profile_dir(turma_num)
_PROFILE_DIR = Path(
    os.getenv("BROWSER_PROFILE_2G",
              str(Path(__file__).resolve().parent.parent / "browser-profile-2g"))
)


def get_profile_dir(turma_num: int | None = None) -> Path:
    """Diretório de perfil do Chrome.
    Por padrão é separado por turma (para rodar em PARALELO). Se a env
    PJE2G_PROFILE_COMPARTILHADO estiver definida (execução SEQUENCIAL), TODAS as
    turmas usam o MESMO perfil já autenticado — evita o relogin falho dos perfis
    t2/t3 (que ficavam presos no SSO por não terem a memória do certificado)."""
    compartilhado = os.getenv("PJE2G_PROFILE_COMPARTILHADO")
    if compartilhado:
        return Path(compartilhado)
    if turma_num:
        base = os.getenv("BROWSER_PROFILE_2G",
                         str(Path(__file__).resolve().parent.parent / "browser-profile-2g"))
        return Path(f"{base}-t{turma_num}")
    return _PROFILE_DIR

# Turmas Recursais de PE no select do pje2g (values extraídos do formulário)
TURMAS_PE = {
    "1ª Turma Recursal de Pernambuco": "29",
    "2ª Turma Recursal de Pernambuco": "33",
    "3ª Turma Recursal de Pernambuco": "35",
}

# Seletores exatos do formulário ConsultaProcesso (descobertos via debug)
SEL_ORGAO = "#fPP\\:orgaoJulgadorColegiadoComboDecoration\\:orgaoJulgadorColegiadoCombo"
SEL_NOME_PARTE = "#fPP\\:j_id148\\:nomeParte"
SEL_DATA_INI = "#fPP\\:dataAutuacaoDecoration\\:dataAutuacaoInicioInputDate"
SEL_DATA_FIM = "#fPP\\:dataAutuacaoDecoration\\:dataAutuacaoFimInputDate"
SEL_PESQUISAR = "#fPP\\:searchProcessos"
SEL_LIMPAR = "#fPP\\:clearButtonProcessos"

TIPOS_DOC_TR = ("voto", "acórdão", "acordao", "ementa",
                "decisão monocrática", "decisao monocratica",
                "decisão", "decisao", "sentença", "sentenca",
                "despacho", "relatório", "relatorio")
TIPOS_VETO_TR = ("certidão", "certidao", "petição inicial", "contestação",
                 "contrarrazões", "contrarrazoes", "petição", "peticao")


@asynccontextmanager
async def pje2g_context(headless: bool = False, turma_num: int | None = None):
    """Contexto autenticado no pje2g via certificado A1 do Keychain."""
    profile = get_profile_dir(turma_num)
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
        await page.goto(TR_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

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
                print("[pje2g] 2FA — digite o código no navegador.")
        except Exception:
            pass

        try:
            await page.wait_for_url(f"{TR_BASE_URL}/pje/**", timeout=180_000)
        except Exception:
            pass
        print(f"[pje2g] autenticado, url={page.url}")
        try:
            yield ctx
        finally:
            await ctx.close()


async def preencher_e_pesquisar(page, orgao_value: str, orgao_nome: str,
                                 nome_parte: str, data_ini: str, data_fim: str) -> None:
    """Limpa o form, preenche todos os campos e clica em Pesquisar."""
    await page.goto(TR_CONSULTA_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)

    # Limpa form anterior
    try:
        await page.click(SEL_LIMPAR)
        await page.wait_for_timeout(1_500)
    except Exception:
        pass

    # Preenche todos os campos via JavaScript puro (sem acionar eventos que resettam o form)
    filled = await page.evaluate(
        """([orgaoVal, nomeParte, dataIni, dataFim]) => {
            const log = [];
            const set = (sel, val) => {
                const el = document.querySelector(sel);
                if (!el) { log.push('not found: ' + sel); return false; }
                el.value = val;
                log.push('set ' + sel + ' = ' + val);
                return true;
            };
            set('select[name*="orgaoJulgadorColegiadoCombo"]', orgaoVal);
            set('select[id*="orgaoJulgadorColegiadoCombo"]',  orgaoVal);
            set('input[name*="nomeParte"]',   nomeParte);
            set('input[id*="nomeParte"]',     nomeParte);
            set('input[name*="dataAutuacaoInicio"]', dataIni);
            set('input[id*="dataAutuacaoInicio"]',   dataIni);
            set('input[name*="dataAutuacaoFim"]',  dataFim);
            set('input[id*="dataAutuacaoFim"]',    dataFim);
            return log;
        }""",
        [orgao_value, nome_parte, data_ini, data_fim],
    )
    print(f"[tr] form: {[l for l in filled if 'set ' in l][:6]}")

    # Clica no botão Pesquisar — reCAPTCHA invisível passa automaticamente em sessão autenticada
    # Se após 3s o resultado ainda não carregou, tenta via A4J direto como fallback
    btn = page.locator('input[id*="searchProcessos"], input[value="Pesquisar"]').first
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(3_000)
        # Verifica se o reCAPTCHA ainda está pendente e tenta submit direto
        has_rows = await page.evaluate(
            "() => document.querySelectorAll('tr.rich-table-row').length > 0"
        )
        if not has_rows:
            # Fallback: dispara A4J com os valores atuais do DOM
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


async def extrair_processos_pagina(page) -> list[dict]:
    """Extrai processos da tabela de resultados.
    Cada item: {id, cnj, proc_id, relatoria, onclick, texto}."""
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
                const tds = row.querySelectorAll('td');
                // Extrai CNJ (coluna "Processo" — geralmente a 2ª col)
                let cnj = '', procId = '', relatoria = '', linkEl = null;
                for (const td of tds) {
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
                    // Coluna "Órgão julgador" / "Relatoria"
                    if (txt.includes('Relatoria') || txt.includes('TR/PE') || txt.includes('TR/')) {
                        relatoria = txt;
                    }
                }
                if (!linkEl && !cnj) continue;
                if (!linkEl) {
                    // Fallback: primeiro link da linha
                    linkEl = row.querySelector('a');
                }
                if (linkEl && !linkEl.id) {
                    linkEl.id = '_tr_' + Math.random().toString(36).slice(2);
                }
                items.push({
                    id: linkEl ? linkEl.id : '',
                    cnj, proc_id: procId, relatoria,
                    texto: cnj || (linkEl ? linkEl.textContent.trim() : ''),
                    onclick: linkEl ? (linkEl.getAttribute('onclick')||'') : '',
                });
            }
            return items;
        }"""
    )


async def contar_resultados(page) -> int:
    """Retorna total de resultados (extrai do rich-data-scroller ou texto da página)."""
    try:
        txt = await page.evaluate(
            """() => {
                const sc = document.querySelector('.rich-dtascroller-table, .rich-datascr');
                return sc ? sc.textContent : '';
            }"""
        )
        m = re.search(r"(\d+)\s*(?:registro|result|process)", txt, re.I)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    rows = await page.query_selector_all(
        "#fPP\\:processosTable tr.rich-table-row, #fPP\\:processosTable tr[class*='row']"
    )
    return len(rows)


async def ir_proxima_pagina(page) -> bool:
    """Clica no botão de próxima página do RichFaces scroller (» ou > ou Próximo)."""
    try:
        prox = await page.evaluate(
            """() => {
                const PROXIMOS = ['>', '»', 'próximo', 'proximo', 'next'];
                const btns = document.querySelectorAll('.rich-datascr-button, td.rich-datascr-button');
                // O botão "próximo" é geralmente o penúltimo (antes do »» que é "última página")
                // Tentativa 1: por texto
                for (const btn of btns) {
                    const txt = btn.textContent.trim().toLowerCase();
                    if (PROXIMOS.includes(txt)) {
                        if (btn.classList.contains('rich-datascr-button-dsbld')) return false;
                        const a = btn.querySelector('a');
                        if (a) { a.click(); return true; }
                        btn.click(); return true;
                    }
                }
                // Tentativa 2: botão ativo após os desabilitados (padrão: «« « ... » »»)
                // O penúltimo botão ativo é "próxima página"
                const todos = Array.from(btns);
                const ativos = todos.filter(b => !b.classList.contains('rich-datascr-button-dsbld'));
                if (ativos.length >= 2) {
                    // Penúltimo ativo = próxima página (último = última página)
                    const candidato = ativos[ativos.length - 2];
                    const a = candidato.querySelector('a');
                    if (a) { a.click(); return true; }
                    candidato.click(); return true;
                }
                return false;
            }"""
        )
        if prox:
            await page.wait_for_timeout(4_000)
        return bool(prox)
    except Exception as e:
        # Distingue "fim das páginas" (return False legítimo) de "browser/página caiu".
        # Se a página foi fechada (crash, sessão derrubada), PROPAGA o erro: o chamador
        # só apaga o checkpoint quando ir_proxima_pagina retorna False, então engolir um
        # crash aqui faria perder o ponto de retomada (bug que zerou t1/t3).
        if page.is_closed() or "closed" in str(e).lower() or "crash" in str(e).lower():
            raise
        return False


async def pagina_ativa(page) -> int:
    """Lê o número da página ativa no datascroller (td.rich-datascr-act)."""
    try:
        return await page.evaluate(
            """() => {
                const act = document.querySelector('td.rich-datascr-act');
                if (!act) return 0;
                const n = parseInt((act.textContent || '').trim(), 10);
                return isNaN(n) ? 0 : n;
            }"""
        )
    except Exception:
        return 0


async def _fire_scroller(page, token) -> bool:
    """Dispara o evento rich:datascroller:onscroll com um token de página
    ('next', 'fastforward', 'last' ou um número). É como o próprio PJe navega
    (vide onclick dos botões), então aceita salto direto para qualquer página."""
    return await page.evaluate(
        """(tok) => {
            const cell = document.querySelector(
                'td.rich-datascr-inact, td.rich-datascr-act, td.rich-datascr-button');
            if (!cell) return false;
            if (typeof Event === 'undefined' || !Event.fire) return false;
            Event.fire(cell, 'rich:datascroller:onscroll', {page: tok});
            return true;
        }""",
        str(token),
    )


async def ir_para_pagina(page, target: int) -> bool:
    """Pula DIRETO para a página `target` no datascroller RichFaces.
    Tenta salto direto numa única requisição; se não suportado, usa 'fastforward'
    (+janela) e 'next' iterativamente. Evita clicar 'próxima' centenas de vezes —
    que era lento (~4s/página) e estourava a memória do Chrome (causa dos crashes).
    Retorna True se chegou em `target` (ou além)."""
    if target <= 1:
        return True
    try:
        # 1) Caminho rápido: salto direto para o número da página.
        await _fire_scroller(page, str(target))
        await page.wait_for_timeout(4_000)
        atual = await pagina_ativa(page)
        if atual >= target:
            return True
        # 2) Fallback: avança em blocos ('fastforward' = +janela) e afina com 'next'.
        guard = 0
        while atual < target and guard < target + 40:
            guard += 1
            token = "fastforward" if (target - atual) >= 10 else "next"
            if not await _fire_scroller(page, token):
                break
            await page.wait_for_timeout(4_000)
            novo = await pagina_ativa(page)
            if novo <= atual:  # não avançou — evita loop infinito
                break
            atual = novo
        return atual >= target
    except Exception as e:
        if page.is_closed() or "closed" in str(e).lower() or "crash" in str(e).lower():
            raise
        return False


async def total_resultados(page) -> int:
    """Lê 'N resultados encontrados' da página de resultados. 0 se não achar.
    Usado para saber a ÚLTIMA página real e nunca concluir a turma antes dela."""
    try:
        n = await page.evaluate(
            r"""() => {
                const t = document.body.innerText || '';
                const m = t.match(/([\d][\d.\s]*)\s+resultados?\s+encontrad/i);
                return m ? (parseInt(m[1].replace(/[.\s]/g, ''), 10) || 0) : 0;
            }"""
        )
        return int(n or 0)
    except Exception:
        return 0


def extrair_advogados(texto: str) -> list[dict]:
    """Extrai advogados do cabeçalho do acórdão.
    Retorna lista de {nome, oab, lado} onde lado = RECORRENTE | RECORRIDO | AUTOR | RÉU."""
    advogados = []
    vistos: set[str] = set()

    # Padrão: "ADVOGADO do(a) [LADO]: NOME - OAB" ou "ADVOGADO: NOME - OAB"
    for m in re.finditer(
        r"ADVOGADO\b[^:\n]{0,40}:\s*([A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇa-záéíóúàèìòùâêîôûãõç ]{5,60}?)\s*-\s*([A-Z]{2}\d{3,6})",
        texto,
        re.IGNORECASE,
    ):
        nome = m.group(1).strip().rstrip(" ,-")
        oab = m.group(2).strip().replace(" ", "")
        if oab in vistos:
            continue
        vistos.add(oab)
        # Identifica o lado a partir do contexto antes do match
        ctx = texto[max(0, m.start() - 100): m.start()].upper()
        if "RECORRENTE" in ctx:
            lado = "RECORRENTE"
        elif "RECORRIDO" in ctx:
            lado = "RECORRIDO"
        elif "AUTOR" in ctx or "POLO ATIVO" in ctx:
            lado = "AUTOR"
        else:
            lado = "RECORRENTE"  # default: quem está representado
        advogados.append({"nome": nome, "oab": oab, "lado": lado})

    # Fallback mais amplo: "REPRESENTANTES [LADO]: NOME - OAB"
    if not advogados:
        for m in re.finditer(
            r"REPRESENTANTES?\b[^:\n]{0,40}:\s*([A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇa-záéíóúàèìòùâêîôûãõç ]{5,60}?)\s*-\s*([A-Z]{2}\d{3,6})",
            texto,
            re.IGNORECASE,
        ):
            nome = m.group(1).strip().rstrip(" ,-")
            oab = m.group(2).strip().replace(" ", "")
            if oab not in vistos:
                vistos.add(oab)
                advogados.append({"nome": nome, "oab": oab, "lado": "AUTOR"})

    return advogados


def extrair_relator(texto: str) -> str | None:
    # Nome: palavra inicial + 1-6 palavras compostas opcionalmente com de/da/do
    _n = (r"[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+"
          r"(?:\s+(?:(?:de|da|do|dos|das|e)\s+)?"
          r"[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+){1,6}")
    for pat in (
        # Nome ANTES de "Juiz Federal" (pje1g e pje2g)
        rf"({_n})\s+Juiz[a]?\s+Federal\b",
        rf"({_n})\s+Relator[a]?\s+(?:pj|do\s)",
        # Nome em MAIÚSCULAS antes de "Nª Relatoria" (padrão acórdão pje2g)
        r"(?:Recife|julgamento)[^\n]{0,50}?\n?\s+([A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ]{3,}(?:\s+(?:DE|DA|DO|DOS|DAS|E)\s+|\s+)[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ]{2,}){0,5})\s+[\dª1-9]",
        rf"({_n})\s+[\dªº]+[ªº]\s+Relatoria",
        # Nome DEPOIS de "Relator:" (padrão pje1g)
        rf"[Rr]elator[a]?[:\s]+(?:Juiz[a]?\s+Federal\s+)?({_n})",
        rf"[Vv]otante[:\s]+({_n})",
        rf"Juiz[a]?\s+Federal\s+({_n})\s*[-–,]",
    ):
        m = re.search(pat, texto)
        if m:
            raw_name = m.group(1).strip().rstrip(".,")
            # Remove palavras finais que não são parte de nomes pessoais
            _nao_nome = {
                'competência', 'competencia', 'jurisdição', 'jurisdicao',
                'função', 'funcao', 'recife', 'relator', 'relatora',
                'federal', 'substituto', 'substituta',
            }
            words = raw_name.split()
            while words and words[-1].lower() in _nao_nome:
                words.pop()
            if len(words) >= 2:
                return ' '.join(words)
    return None


def extrair_resultado(texto: str) -> str | None:
    txt = texto.upper()
    if "JULGO PARCIALMENTE PROCEDENTE" in txt or "PARCIALMENTE PROCEDENTE" in txt:
        return "PARCIALMENTE_PROCEDENTE"
    if any(x in txt for x in ("JULGO PROCEDENTE", "RECURSO PROVIDO", "DOU PROVIMENTO",
                               "DANDO PROVIMENTO", "RECURSO PROVIDO")):
        return "PROCEDENTE"
    if any(x in txt for x in ("JULGO IMPROCEDENTE", "RECURSO NÃO PROVIDO", "RECURSO IMPROVIDO",
                               "NEGO PROVIMENTO", "NEGANDO PROVIMENTO", "IMPROVIDO",
                               "SENTENÇA MANTIDA")):
        return "IMPROCEDENTE"
    return None


def extrair_ementa(texto: str) -> str | None:
    m = re.search(r"EMENTA\s*[:\-]?\s*(.*?)(?:ACÓRDÃO|RELATÓRIO|VOTO|$)", texto, re.S | re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:2000] or None
    return None
