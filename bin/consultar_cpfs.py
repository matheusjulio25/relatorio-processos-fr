#!/usr/bin/env python3
"""Consulta em lote por CPF no pje1g (ConsultaProcesso) — triagem da esteira.

Para cada CPF pesquisa em https://pje1g.trf5.jus.br ConsultaProcesso e coleta os
processos encontrados (CNJ, órgão julgador, classe, polos, última movimentação).

Classifica cada CPF em 3 grupos (o que Matheus pediu):
  - sem_processo         → nenhum processo ajuizado
  - arquivado_definitivo → só possui processo(s) arquivado(s) definitivamente
  - com_processo         → possui ao menos 1 processo ativo (não arquivado)

Checkpoint por CPF em mapas/consulta_cpfs.json (resume-safe: relança pula os já
consultados). Uso:
    python3 bin/consultar_cpfs.py [--limit N] [--debug] [--headless]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coletor_pje.varas_1g import pje1g_consulta_context, PJE1G_BASE_URL  # noqa: E402

CONSULTA_URL = f"{PJE1G_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
OUT_FP = Path("mapas/consulta_cpfs.json")
CPFS_FP = Path("mapas/cpfs_consulta.txt")
DEBUG_DIR = Path("debug")

# "arquivado definitivamente" / "arquivamento definitivo" na última movimentação
ARQUIV_DEF_RE = re.compile(r"arquiv\w*\s+defin", re.I)


def so_digitos(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def fmt_cpf(digitos: str) -> str:
    d = so_digitos(digitos)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else digitos


async def _esperar_busca(page, timeout_ms: int = 30_000):
    """Espera o AJAX da pesquisa renderizar. Conclui quando a contagem
    '<N> resultados encontrados.' mostra um número OU quando surgem linhas
    com CNJ no tbody de dados. Devolve o texto da contagem (ou None no timeout)."""
    elapsed, step = 0, 500
    while elapsed < timeout_ms:
        estado = await page.evaluate(
            r"""() => {
                const spans = [...document.querySelectorAll('span.text-muted')];
                const s = spans.find(x => /resultados?\s+encontrad/i.test(x.textContent||''));
                const cont = s ? s.textContent.replace(/\s+/g,' ').trim() : null;
                const tb = document.querySelector('#fPP\\:processosTable\\:tb');
                let rows = 0;
                if (tb) rows = [...tb.querySelectorAll('tr')]
                    .filter(tr => /\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}/.test(tr.textContent||'')).length;
                return {cont, rows};
            }"""
        )
        if estado["rows"] > 0:
            return estado["cont"] or f"{estado['rows']}+ linhas"
        if estado["cont"] and re.search(r"\d", estado["cont"]):
            return estado["cont"]
        await page.wait_for_timeout(step)
        elapsed += step
    return None


async def buscar_cpf(page, cpf_digits: str, debug: bool = False) -> dict:
    """Pesquisa 1 CPF e devolve {status, erro, processos:[...]}."""
    await page.goto(CONSULTA_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(1_500)

    # se o campo de CPF não existe, não estamos na tela de consulta => sessão caiu
    if await page.locator("#fPP\\:dpDec\\:documentoParte").count() == 0:
        raise RuntimeError(f"sessao_expirada (url={page.url})")

    # garante radio CPF marcado + máscara e limpa o campo
    await page.evaluate(
        """() => {
            const r = document.getElementById('cpf');
            if (r && !r.checked) { r.checked = true; if (r.onclick) r.onclick(); }
            const e = document.getElementById('fPP:dpDec:documentoParte');
            if (e) e.value = '';
        }"""
    )
    campo = page.locator("#fPP\\:dpDec\\:documentoParte")

    async def _setar_cpf():
        # fill() seta o valor de UMA vez (não tecla-a-tecla): a máscara não embola
        # nem deixa o campo vazio. Mantém a máscara (unmask quebra a busca).
        # Até 3 tentativas, conferindo o valor.
        try:
            await campo.wait_for(state="visible", timeout=10_000)
        except Exception:
            pass
        v = ""
        for _ in range(3):
            await campo.click()
            await campo.fill("")
            await campo.fill(fmt_cpf(cpf_digits))  # valor formatado completo
            await campo.press("Tab")                # blur -> apenasNumeros() commita
            await page.wait_for_timeout(300)
            v = re.sub(r"\D", "", (await campo.input_value()) or "")
            if v == cpf_digits:
                return v
            await page.wait_for_timeout(250)
        return v

    val_dig = await _setar_cpf()
    if val_dig != cpf_digits:
        raise RuntimeError(f"campo_cpf_incorreto (esperado {cpf_digits}, campo {val_dig!r})")
    if debug:
        print(f"[diag] {fmt_cpf(cpf_digits)} campo={val_dig!r} ok={val_dig == cpf_digits}", flush=True)

    # ---- dispara a pesquisa e captura o CORPO da resposta AJAX (fonte da verdade) ----
    def _e_post_busca(r):
        try:
            return ("listView.seam" in r.url) and (r.request.method == "POST")
        except Exception:
            return False

    async def _submeter(trigger, timeout=30_000):
        """Dispara `trigger` e devolve o texto da resposta AJAX (ou None)."""
        try:
            async with page.expect_response(_e_post_busca, timeout=timeout) as ri:
                await trigger()
            resp = await ri.value
            return await resp.text()
        except Exception:
            return None

    body = await _submeter(lambda: page.locator("#fPP\\:searchProcessos").click())
    if not body or "processosTable" not in body:
        body = await _submeter(
            lambda: page.evaluate(
                "() => { if (typeof executarPesquisaReCaptcha === 'function') executarPesquisaReCaptcha(); }"
            ),
            timeout=20_000,
        )
    buscou = bool(body and "processosTable" in body)

    if debug:
        DEBUG_DIR.mkdir(exist_ok=True)
        (DEBUG_DIR / f"cpf_{cpf_digits}_resp.html").write_text(body or "(sem body)", encoding="utf-8")

    # parser das linhas a partir de um HTML (a resposta A4J traz a tabela renderizada)
    PARSER_JS = r"""(html) => {
        const CNJ = /\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}/;
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const tbl = doc.getElementById('fPP:processosTable');
        if (!tbl) return [];
        const heads = [...tbl.querySelectorAll('thead th')]
            .map(th => (th.textContent||'').replace(/\s+/g,' ').trim().toLowerCase());
        const idx = (frag) => heads.findIndex(h => h.startsWith(frag));
        const iOrg = idx('órgão') >= 0 ? idx('órgão') : idx('orgao');
        const iAut = idx('autuado');
        const iCls = idx('classe');
        const iAtv = idx('polo ativo');
        const iPas = idx('polo passivo');
        const iMov = idx('última') >= 0 ? idx('última') : idx('ultima');
        const tb = doc.getElementById('fPP:processosTable:tb') || tbl;
        const out = [];
        for (const tr of tb.querySelectorAll('tr')) {
            const tds = [...tr.querySelectorAll('td')].map(td => (td.textContent||'').replace(/\s+/g,' ').trim());
            const joined = tds.join(' | ');
            const m = joined.match(CNJ);
            if (!m || m[0].startsWith('9999999-99')) continue;
            out.push({cnj:m[0], orgao:iOrg>=0?(tds[iOrg]||''):'', autuado:iAut>=0?(tds[iAut]||''):'',
                classe:iCls>=0?(tds[iCls]||''):'', polo_ativo:iAtv>=0?(tds[iAtv]||''):'',
                polo_passivo:iPas>=0?(tds[iPas]||''):'', ultima_mov:iMov>=0?(tds[iMov]||''):'', row_text:joined});
        }
        return out;
    }"""

    processos: list[dict] = []
    vistos: set[str] = set()

    def _absorver(rows) -> int:
        n = 0
        for r in rows:
            if r["cnj"] in vistos:
                continue
            vistos.add(r["cnj"])
            r["arquivado_definitivo"] = bool(ARQUIV_DEF_RE.search(r.get("ultima_mov", "")))
            processos.append(r)
            n += 1
        return n

    if buscou:
        _absorver(await page.evaluate(PARSER_JS, body))
        # paginação: só se houver "próxima" habilitada no DOM (evita esperar POST à toa)
        pagina = 1
        while pagina < 20:
            tem_prox = await page.evaluate(
                """() => {
                    const btns = document.querySelectorAll('.rich-datascr-button');
                    const ativos = [...btns].filter(b => !b.className.includes('dsbld'));
                    return ativos.length >= 2;
                }"""
            )
            if not tem_prox:
                break
            body_prox = await _submeter(
                lambda: page.evaluate(
                    """() => {
                        const btns = document.querySelectorAll('.rich-datascr-button');
                        const ativos = [...btns].filter(b => !b.className.includes('dsbld'));
                        const prox = ativos[ativos.length - 2];
                        (prox.querySelector('a') || prox).click();
                    }"""
                ),
                timeout=20_000,
            )
            if not body_prox or _absorver(await page.evaluate(PARSER_JS, body_prox)) == 0:
                break
            pagina += 1

    contagem = f"{len(processos)} proc no corpo da resposta"

    # classificação do CPF
    if not buscou:
        status = "falha_busca"        # POST não confirmado — reprocessar depois, NÃO é "sem processo"
    elif not processos:
        status = "sem_processo"
    elif all(p["arquivado_definitivo"] for p in processos):
        status = "arquivado_definitivo"
    else:
        status = "com_processo"

    return {"status": status, "buscou": buscou, "contagem": contagem, "processos": processos}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="consulta só os N primeiros (teste)")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--diag", default="", help="CPF único para diagnóstico (repete N vezes, sem checkpoint)")
    ap.add_argument("--repeat", type=int, default=3, help="repetições no modo --diag")
    args = ap.parse_args()

    # modo diagnóstico: repete CPF(s) várias vezes p/ testar estabilidade
    if args.diag:
        alvos = [so_digitos(x) for x in args.diag.split(",") if so_digitos(x)]
        async with pje1g_consulta_context(headless=args.headless) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            for d in alvos:
                for k in range(1, args.repeat + 1):
                    try:
                        res = await buscar_cpf(page, d, debug=True)
                        print(f"[diag] {fmt_cpf(d)} rodada {k}/{args.repeat} -> {res['status']} "
                              f"({len(res['processos'])} proc; {res['contagem']})", flush=True)
                    except Exception as e:
                        print(f"[diag] {fmt_cpf(d)} rodada {k}/{args.repeat} -> EXCEÇÃO: {e}", flush=True)
        return

    cpfs = [c.strip() for c in CPFS_FP.read_text(encoding="utf-8").splitlines() if c.strip()]
    # dedup preservando ordem
    seen, ordenados = set(), []
    for c in cpfs:
        d = so_digitos(c)
        if len(d) == 11 and d not in seen:
            seen.add(d)
            ordenados.append(d)
    if args.limit:
        ordenados = ordenados[: args.limit]

    resultados: dict = json.loads(OUT_FP.read_text(encoding="utf-8")) if OUT_FP.exists() else {}
    total = len(ordenados)
    print(f"[cpfs] {total} CPFs a consultar; {len(resultados)} já no checkpoint")

    async with pje1g_consulta_context(headless=args.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, d in enumerate(ordenados, 1):
            if d in resultados:
                continue
            try:
                res = await buscar_cpf(page, d, debug=args.debug)
            except Exception as e:
                if "sessao_expirada" in str(e):
                    print(f"[cpfs] ⚠️ sessão expirada em {fmt_cpf(d)} — salvando e saindo. {e}")
                    print("[cpfs] rode de novo para retomar (resume-safe).")
                    break
                print(f"[cpfs] {i}/{total} {fmt_cpf(d)} ERRO: {e}")
                res = {"status": "erro", "erro": str(e), "processos": []}
            n = len(res.get("processos", []))
            cont = res.get("contagem")
            print(f"[cpfs] {i}/{total} {fmt_cpf(d)} -> {res['status']} ({n} proc; {cont})")
            # NÃO grava falhas: assim são reprocessadas numa próxima execução
            if res["status"] in ("erro", "falha_busca"):
                continue
            resultados[d] = res
            OUT_FP.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    # resumo
    from collections import Counter
    c = Counter(v["status"] for v in resultados.values())
    print(f"[cpfs] FIM. {dict(c)}")


if __name__ == "__main__":
    asyncio.run(main())
