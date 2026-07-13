#!/usr/bin/env python3
"""Etapa 1 do modo CNJ (confiável): abre cada processo (ConsultaProcesso por
número) e BAIXA sentença(s) + laudo(s) para mapas/docs_cnj/<cnj>/. Não classifica
(isso é feito por leitura/visão na etapa 2). Resume-safe.

Prioridade: processos com perícia realizada (feitas>=1) — os 216 do despacho.
Uso: python3 bin/coletar_pecas_cnj.py [--limit N] [--todos]
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
from coletor_pje.cli import _parse_docs, _baixar_pecas  # noqa: E402

CONSULTA = f"{PJE1G_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")
POR = Path("mapas/pericias_por_processo.json")
IDX = Path("mapas/coleta_cnj.json")
DOCS = Path("mapas/docs_cnj")


async def _fill(page, fid, val):
    loc = page.locator("#" + fid.replace(":", "\\:"))
    if await loc.count():
        try:
            await loc.fill(val)
        except Exception:
            pass


async def abrir(ctx, page, cnj, tentativas=2):
    m = CNJ_RE.search(cnj)
    seq, dv, ano, ramo, trib, org = m.groups()
    for _ in range(tentativas):
        await page.goto(CONSULTA, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1_200)
        # guarda de sessão: sem o campo do número, não estamos logados na consulta
        if await page.locator("#fPP\\:numeroProcesso\\:numeroSequencial").count() == 0:
            raise RuntimeError(f"nao_autenticado (url={page.url})")
        await _fill(page, "fPP:numeroProcesso:numeroSequencial", seq)
        await _fill(page, "fPP:numeroProcesso:numeroDigitoVerificador", dv)
        await _fill(page, "fPP:numeroProcesso:Ano", ano)
        await _fill(page, "fPP:numeroProcesso:ramoJustica", ramo)
        await _fill(page, "fPP:numeroProcesso:respectivoTribunal", trib)
        await _fill(page, "fPP:numeroProcesso:NumeroOrgaoJustica", org)

        def is_post(r):
            try:
                return "listView.seam" in r.url and r.request.method == "POST"
            except Exception:
                return False
        try:
            async with page.expect_response(is_post, timeout=30_000):
                await page.locator("#fPP\\:searchProcessos").click()
        except Exception:
            pass
        await page.wait_for_timeout(2_000)
        try:
            async with ctx.expect_page(timeout=20_000) as pinfo:
                await page.evaluate(
                    """() => {
                        const CNJ=/\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
                        for (const a of document.querySelectorAll('a[onclick*="idProcessoSelecionado"]')) {
                            if (CNJ.test((a.textContent||'')+(a.getAttribute('title')||''))) { a.click(); return true; }
                        }
                        const a=document.querySelector('a[onclick*="idProcessoSelecionado"]');
                        if(a){a.click(); return true;} return false;
                    }"""
                )
            popup = await pinfo.value
            await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
            await popup.wait_for_timeout(4_500)
            return popup
        except Exception:
            continue
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--todos", action="store_true", help="inclui os sem perícia (feitas==0)")
    ap.add_argument("--sufixo", default="", help="sufixo do perfil do navegador (p/ paralelo)")
    ap.add_argument("--shard", default="", help="I/M: processa só os CNJs com índice%%M==I (paralelo)")
    args = ap.parse_args()

    por = json.loads(POR.read_text(encoding="utf-8"))
    # prioridade: perícia realizada primeiro (maduros e 1-perícia), depois o resto
    cnjs = [c for c, v in por.items() if v.get("feitas", 0) >= 2]
    cnjs += [c for c, v in por.items() if v.get("feitas", 0) == 1]
    if args.todos:
        cnjs += [c for c, v in por.items() if v.get("feitas", 0) == 0]
    if args.shard:
        I, M = (int(x) for x in args.shard.split("/"))
        cnjs = [c for k, c in enumerate(cnjs) if k % M == I]
    if args.limit:
        cnjs = cnjs[: args.limit]

    idx_fp = Path(f"mapas/coleta_cnj{args.sufixo}.json")
    idx = json.loads(idx_fp.read_text(encoding="utf-8")) if idx_fp.exists() else {}
    DOCS.mkdir(parents=True, exist_ok=True)
    total = len(cnjs)
    print(f"[coleta{args.sufixo}] shard={args.shard or 'todo'} {total} CNJs; {len(idx)} no checkpoint", flush=True)

    async with pje1g_consulta_context(headless=False, sufixo=args.sufixo) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, cnj in enumerate(cnjs, 1):
            # pula por PASTA já coletada (race-safe entre shards paralelos)
            if (DOCS / cnj.replace(".", "_") / "detalhe.txt").exists():
                continue
            if cnj in idx:
                continue
            try:
                popup = await abrir(ctx, page, cnj)
            except RuntimeError as e:
                if "nao_autenticado" in str(e):
                    print(f"[coleta] NAO AUTENTICADO — faça login (clique no certificado 'Sempre Permitir') "
                          f"e rode de novo. Nada foi gravado. {e}", flush=True)
                    return
                raise
            if not popup:
                print(f"[coleta] {i}/{total} {cnj} -> NAO ABRIU", flush=True)
                idx[cnj] = {"aberto": False}
                idx_fp.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            try:
                html = await popup.content()
                docs = _parse_docs(html)
                sents = [d for d in docs if "senten" in d["tipo"].lower()]
                _SOC = ("laudo", "social", "socioecon", "estudo social",
                        "avaliacao social", "avaliação social", "assistente social")
                laudos = [d for d in docs
                          if any(k in (d["tipo"] + " " + d.get("desc", "")).lower() for k in _SOC)]
                # contexto p/ motivo do indeferimento (Tema 187). O indeferimento/PA costuma vir
                # na inicial ou na emenda à inicial (juntado pela parte), ou no processo
                # administrativo (juntado pela parte ou pelo INSS).
                _kw = ("inicial", "emenda", "contesta", "indefer", "comunicado de decis",
                       "carta de concess", "processo administrativo", "administrativo",
                       "ceap", "documento comprobat")
                contexto = [d for d in docs
                            if any(k in (d["tipo"] + " " + d.get("desc", "")).lower() for k in _kw)]
                out = DOCS / cnj.replace(".", "_")
                out.mkdir(parents=True, exist_ok=True)
                # TIMELINE: o texto visível do detalhe (docs + movimentos + datas +
                # partes + situação) — é o que a inteligência lê para decidir o estado real.
                (out / "detalhe.html").write_text(html, encoding="utf-8")
                try:
                    innertext = await popup.evaluate("() => document.body.innerText")
                    (out / "detalhe.txt").write_text(innertext or "", encoding="utf-8")
                except Exception:
                    pass
                # baixa até 2 sentenças + até 4 laudos (todos os tipos de laudo)
                baixados = await _baixar_pecas(
                    popup, sents[:2] + laudos[:4] + contexto[:3], out, log_prefix="   ")
                # salva também o texto extraído (quando houver) num json por doc
                man = {"cnj": cnj, "tipos": sorted({d["tipo"] for d in docs}),
                       "sentencas": [], "laudos": [], "contexto": []}
                _ctx_ids = {d["id"] for d in contexto}
                for b in baixados:
                    reg = {"id": b["id"], "tipo": b["tipo"], "desc": b["desc"],
                           "ext": b["ext"], "path": b["path"], "chars": len(b.get("texto", ""))}
                    if b.get("texto"):
                        (out / f"{b['id']}.txt").write_text(b["texto"], encoding="utf-8")
                        reg["txt"] = str(out / f"{b['id']}.txt")
                    t = b["tipo"].lower()
                    if "senten" in t:
                        man["sentencas"].append(reg)
                    elif "laudo" in t:
                        man["laudos"].append(reg)
                    else:
                        man["contexto"].append(reg)
                (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
                idx[cnj] = {"aberto": True, "dir": str(out), "n_sent": len(sents),
                            "n_laudo": len(laudos), "tipos": man["tipos"]}
                print(f"[coleta] {i}/{total} {cnj} -> sent={len(sents)} laudos={len(laudos)} baixados={len(baixados)}", flush=True)
            except Exception as e:
                print(f"[coleta] {i}/{total} {cnj} ERRO: {e}", flush=True)
                idx[cnj] = {"aberto": True, "erro": str(e)}
            finally:
                try:
                    await popup.close()
                except Exception:
                    pass
            idx_fp.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[coleta] FIM. {len(idx)} processados", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
