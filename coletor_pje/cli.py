"""CLI do coletor."""
from __future__ import annotations

import argparse
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from .acervo import listar_acervo
from .login import pje_context, PJE_BASE_URL
from .manifest import Manifest, diff_acervo

# tipos de documento que queremos analisar (case-insensitive)
TIPOS_RELEVANTES = ("decisão", "decisao", "intimação", "intimacao",
                    "petição", "peticao", "sentença", "sentenca", "despacho",
                    "laudo")
# vetos (mesmo que match em relevantes, descarta)
TIPOS_VETO = ("certidão", "certidao")

# tipos que interessam ao mapeamento de padrões (juízes + peritos)
TIPOS_MAPEAR = ("decisão", "decisao", "sentença", "sentenca", "laudo")

DOC_RE = re.compile(
    r'(\d{7,12})\s*-\s*([A-Za-zÀ-ÿ ()]+?)(?:\s*\(([^)]{0,200})\))?(?=\s*<|\s*\d{7,12}\s*-)'
)


def _e_relevante(tipo: str) -> bool:
    t = tipo.lower().strip()
    if any(v in t for v in TIPOS_VETO):
        return False
    return any(r in t for r in TIPOS_RELEVANTES)


async def _coletar(headless: bool, debug: bool = False):
    async with pje_context(headless=headless) as ctx:
        return [p async for p in listar_acervo(ctx, debug=debug)]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def cmd_listar(args):
    processos = await _coletar(headless=args.headless, debug=args.debug)
    for p in processos:
        print(f"{p.numero}\t{p.ultima_movimentacao or '-'}\t{p.vara or '-'}\t{(p.titulo or '')[:60]}")
    print(f"\nTotal: {len(processos)}")


async def _abrir_detalhe(ctx, cnj: str):
    """Navega até o painel, busca o CNJ em todas as caixas e devolve a popup."""
    from .acervo import ACERVO_PATH

    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_selector("#tabAcervo_lbl", timeout=30_000)
    await page.locator("#tabAcervo_lbl").click()
    await page.wait_for_function(
        "() => document.querySelectorAll('#formAbaAcervo\\\\:trAc td.rich-tree-node-icon[rich\\\\:onexpand]').length > 0",
        timeout=60_000,
    )
    await page.wait_for_timeout(2_000)

    # Expande TODAS as caixas de entrada de uma vez
    qtd = await page.evaluate(
        """() => {
            const tds = document.querySelectorAll('#formAbaAcervo\\\\:trAc td.rich-tree-node-icon');
            let n = 0;
            for (const td of tds) {
                const code = td.getAttribute('rich:onexpand');
                if (!code) continue;
                try { new Function('event', code)(null); n++; } catch (e) {}
            }
            return n;
        }"""
    )
    try:
        await page.wait_for_function(
            f"() => document.querySelectorAll('a[id$=\":-1::cxItem\"]').length >= {qtd}",
            timeout=120_000,
        )
    except Exception:
        pass
    await page.wait_for_timeout(2_000)

    # Clica na primeira caixa para ativar o contexto de busca
    await page.evaluate(
        """() => {
            const a = document.querySelector('a[id$=":-1::cxItem"]');
            if (a) a.onclick();
        }"""
    )
    await page.wait_for_timeout(4_000)

    # Busca o CNJ pelo campo de pesquisa
    await page.fill("#txtConsultaContextoAcervo", cnj)
    await page.click("#btnPesquisarContexto")
    await page.wait_for_timeout(8_000)

    link_id = await page.evaluate(
        """(cnj) => {
            const links = document.querySelectorAll('a[onclick*="listProcessoCompletoAdvogado"]');
            let target = null;
            for (const a of links) {
                if ((a.getAttribute('onclick') || '').includes(cnj) ||
                    (a.textContent || '').includes(cnj)) { target = a; break; }
            }
            if (!target && links.length > 0) target = links[0];
            if (!target) return null;
            if (!target.id) target.id = '__pje_link_target__';
            return target.id;
        }""",
        cnj,
    )

    # Se não achou na primeira caixa, tenta cada caixa individualmente
    if not link_id:
        caixa_ids = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[id$=":-1::cxItem"]')).map(a => a.id)"""
        )
        for caixa_id in caixa_ids[1:]:  # pula a primeira (já tentada)
            await page.evaluate(
                "(id) => { const e = document.getElementById(id); if (e) e.onclick(); }",
                caixa_id,
            )
            await page.wait_for_timeout(4_000)
            await page.fill("#txtConsultaContextoAcervo", cnj)
            await page.click("#btnPesquisarContexto")
            await page.wait_for_timeout(6_000)
            link_id = await page.evaluate(
                """(cnj) => {
                    const links = document.querySelectorAll('a[onclick*="listProcessoCompletoAdvogado"]');
                    for (const a of links) {
                        if ((a.getAttribute('onclick') || '').includes(cnj) ||
                            (a.textContent || '').includes(cnj)) {
                            if (!a.id) a.id = '__pje_link_target__';
                            return a.id;
                        }
                    }
                    return null;
                }""",
                cnj,
            )
            if link_id:
                break

    if not link_id:
        raise RuntimeError(f"Processo {cnj} não encontrado no painel")
    async with ctx.expect_page(timeout=30_000) as popup_info:
        await page.click(f'[id="{link_id}"]')
    popup = await popup_info.value
    await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    await popup.wait_for_timeout(8_000)
    return popup


def _parse_docs(html: str) -> list[dict]:
    """Extrai documentos da popup de detalhe. Ordem do HTML = ordem cronologica reversa."""
    docs: list[dict] = []
    vistos: set[str] = set()
    for m in DOC_RE.finditer(html):
        did, tipo, desc = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        if did in vistos:
            continue
        vistos.add(did)
        docs.append({"id": did, "tipo": tipo, "desc": desc, "pos": m.start()})
    return docs


async def cmd_detalhe(args):
    """Abre 1 processo via popup do painel e dumpa HTML em debug/."""
    m = Manifest.load(args.numero)
    if not m:
        print(f"sem manifest para {args.numero}; rode `diff --apply` antes.")
        return

    debug = Path("debug")
    debug.mkdir(exist_ok=True)
    async with pje_context(headless=args.headless) as ctx:
        popup = await _abrir_detalhe(ctx, args.numero)
        safe = args.numero.replace("/", "_")
        out = debug / f"detalhe_{safe}.html"
        out.write_text(await popup.content(), encoding="utf-8")
        print(f"salvo: {out} ({out.stat().st_size} bytes), url: {popup.url}")


async def cmd_inspect(args):
    """Inspeciona popup do detalhe atras de tokens de auth (localStorage, sessionStorage, window vars, cookies)."""
    if not Manifest.load(args.numero):
        print(f"sem manifest para {args.numero}; rode `diff --apply` antes.")
        return
    async with pje_context(headless=args.headless) as ctx:
        popup = await _abrir_detalhe(ctx, args.numero)
        diag = await popup.evaluate(
            """() => {
                const out = {ls:{}, ss:{}, wins:[], cookies: document.cookie};
                try { for (const k of Object.keys(localStorage)) out.ls[k] = (localStorage.getItem(k)||'').slice(0,300); } catch(e){}
                try { for (const k of Object.keys(sessionStorage)) out.ss[k] = (sessionStorage.getItem(k)||'').slice(0,300); } catch(e){}
                for (const k of Object.keys(window)) {
                    if (/token|auth|pje|jwt|bearer/i.test(k)) {
                        try {
                            const v = window[k];
                            const repr = typeof v === 'string' ? v.slice(0,300) :
                                         typeof v === 'object' ? JSON.stringify(v).slice(0,300) : String(v);
                            out.wins.push({k, type: typeof v, repr});
                        } catch(e){}
                    }
                }
                return out;
            }"""
        )
        print("=== localStorage ===")
        for k, v in diag["ls"].items():
            print(f"  {k} = {v[:200]}")
        print("=== sessionStorage ===")
        for k, v in diag["ss"].items():
            print(f"  {k} = {v[:200]}")
        print("=== window vars (token/auth/pje/jwt) ===")
        for w in diag["wins"]:
            print(f"  {w['k']} ({w['type']}) = {w['repr'][:200]}")
        print(f"=== cookies ===\n  {diag['cookies'][:500]}")

        # Tambem inspeciona requests do iframe (HARLITE)
        print("=== headers do iframe (fetch via XHR para rastrear) ===")
        sample = await popup.evaluate(
            """async () => {
                const f = document.getElementById('frameHtml');
                if (!f) return 'sem frame';
                const src = f.src;
                const xhr = new XMLHttpRequest();
                xhr.open('GET', src, false);
                try { xhr.send(); } catch(e){ return 'send err:'+e.message; }
                return {status: xhr.status, headers: xhr.getAllResponseHeaders().slice(0,1000),
                        bodyLen: xhr.responseText.length, bodySample: xhr.responseText.slice(0,200)};
            }"""
        )
        print(f"  {sample}")


_FETCH_JS = """
async (src) => {
    const resp = await fetch(src, {credentials: 'same-origin'});
    if (!resp.ok) return {status: resp.status, ctype: '', b64: ''};
    const ctype = resp.headers.get('content-type') || '';
    const buf = await resp.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.byteLength; i += 0x8000) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return {status: resp.status, ctype: ctype.toLowerCase(), b64: btoa(bin)};
}
"""


async def _fetch_via_popup(popup, url: str) -> dict:
    """Faz fetch dentro do contexto da popup (sessão JSF) e retorna {status, ctype, b64}."""
    return await popup.evaluate(_FETCH_JS, url)


async def _clicar_timeline_e_baixar(popup, doc_id: str) -> dict:
    """Clica no link do timeline para o doc_id, aguarda o iframe atualizar e baixa.
    Para documentos com editor JS (laudos), captura o texto renderizado do frame."""
    # 1. Clica no link <a> que contém o doc_id no span
    clicou = await popup.evaluate(
        """(docId) => {
            const spans = document.querySelectorAll('span');
            for (const sp of spans) {
                if (sp.textContent && sp.textContent.trim().startsWith(docId)) {
                    let el = sp.parentElement;
                    for (let i = 0; i < 6 && el; i++) {
                        if (el.tagName === 'A') { el.click(); return true; }
                        el = el.parentElement;
                    }
                }
            }
            return false;
        }""",
        doc_id,
    )
    if not clicou:
        return {"status": 0, "ctype": "", "b64": ""}

    # 2. Aguarda iframe atualizar src
    try:
        await popup.wait_for_function(
            f"() => {{ const f = document.getElementById('frameHtml'); return f && f.src && f.src.includes('{doc_id}'); }}",
            timeout=15_000,
        )
    except Exception:
        pass
    # Aguarda renderização JS do editor
    await popup.wait_for_timeout(4_000)

    # 3. Tenta download binário primeiro
    iframe_src = await popup.evaluate(
        "() => { const f = document.getElementById('frameHtml'); return f ? f.src : ''; }"
    )
    if iframe_src:
        res = await _fetch_via_popup(popup, iframe_src)
        if res["status"] == 200 and res["b64"]:
            return res

    # 4. Fallback: lê conteúdo renderizado do frame Playwright (para editor JS)
    iframe_frame = None
    for frame in popup.frames:
        if doc_id in (frame.url or ""):
            iframe_frame = frame
            break
    if not iframe_frame and len(popup.frames) > 1:
        iframe_frame = popup.frames[-1]  # último frame carregado

    if iframe_frame:
        try:
            # Aguarda o editor JS terminar de carregar o conteúdo
            await iframe_frame.wait_for_function(
                "() => { const c = document.getElementById('bd-pages-inner-container') || document.body; return c && c.innerText && c.innerText.trim().length > 50; }",
                timeout=10_000,
            )
            texto_renderizado = await iframe_frame.evaluate(
                """() => {
                    const c = document.getElementById('bd-pages-inner-container') || document.body;
                    return c ? c.innerText : '';
                }"""
            )
            if texto_renderizado and len(texto_renderizado.strip()) > 50:
                import base64 as _b64
                encoded = _b64.b64encode(texto_renderizado.encode("utf-8")).decode("ascii")
                return {"status": 200, "ctype": "text/plain;charset=utf-8", "b64": encoded, "_rendered": True}
        except Exception:
            pass

    return {"status": 0, "ctype": "", "b64": ""}


async def _baixar_pecas(popup, docs_top, out_dir, log_prefix=""):
    """Baixa documentos via fetch() dentro da popup (sessão JSF).
    Detecta automaticamente se é pje1g ou pje2g pelo URL da popup.
    Para documentos que retornam 204/fetch-error usa fallback de clique no timeline.
    Retorna lista de dicts {id, tipo, desc, ext, size, path, texto}."""
    import base64
    # Detecta base URL a partir da página atual (funciona para pje1g e pje2g)
    popup_url = popup.url or ""
    import re as _re
    base_match = _re.match(r"(https?://[^/]+)", popup_url)
    base = base_match.group(1) if base_match else PJE_BASE_URL
    resultados = []
    for d in docs_top:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", d["tipo"])[:40]
        src = f"{base}/pje/seam/resource/rest/pje-legacy/documento/download/{d['id']}"
        try:
            res = await _fetch_via_popup(popup, src)
            if res["status"] != 200 or not res["b64"]:
                print(f"{log_prefix}  [{d['id']}] status {res['status']}, tentando via timeline...")
                res = await _clicar_timeline_e_baixar(popup, d["id"])
            if res["status"] != 200 or not res["b64"]:
                print(f"{log_prefix}  [{d['id']}] sem conteúdo (status {res['status']}), skip")
                continue
            body = base64.b64decode(res["b64"])
            ctype = res["ctype"]
            rendered = res.get("_rendered", False)
            if rendered:
                ext = ".txt"
            elif "pdf" in ctype:
                ext = ".pdf"
            elif "html" in ctype:
                ext = ".html"
            else:
                ext = ".bin"
            fp = out_dir / f"{d['id']}_{slug}{ext}"
            fp.write_bytes(body)
            texto = ""
            if ext == ".txt" or rendered:
                texto = body.decode("utf-8", errors="replace")
            elif ext in (".html", ".bin"):
                import html as _html_module
                raw = body.decode("utf-8", errors="replace")
                if "<" in raw:
                    raw = re.sub(r"<[^>]+>", " ", raw)
                raw = _html_module.unescape(raw)  # converte &nbsp; &amp; etc.
                texto = re.sub(r"\s+", " ", raw).strip()
            print(f"{log_prefix}  [{d['id']}] {ctype} {len(body)}B -> {fp.name}")
            resultados.append({"id": d["id"], "tipo": d["tipo"], "desc": d["desc"],
                                "ext": ext, "size": len(body), "path": str(fp), "texto": texto})
        except Exception as e:
            print(f"{log_prefix}  [{d['id']}] erro: {e}")
    return resultados


# ---------------------------------------------------------------------------
# Helpers de extração de padrões (para cmd_mapear)
# ---------------------------------------------------------------------------

def _perito_do_titulo(desc: str) -> str | None:
    """Extrai nome do perito a partir da descrição do documento no timeline.
    Ex: 'Laudo Pericial VALTO SOGESON DE ANDRADE' → 'VALTO SOGESON DE ANDRADE'."""
    m = re.match(r"(?i)laudo\s+(?:pericial|médico|social|biopsicossocial)\s+(.+)", desc.strip())
    if m:
        nome = m.group(1).strip().rstrip(".")
        if len(nome) > 3:
            return nome
    return None


def _extrair_juiz(texto: str) -> str | None:
    nome = r"[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+(?:\s+(?:de|da|do|dos|das|e)\s+)?(?:[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+\s*){1,5}"
    for pat in (
        rf"Juiz(?:a)?\s+Federal[:\s]+({nome})",
        rf"MM\.?\s*Juiz[a]?[:\s]+({nome})",
        rf"Magistrad[oa][:\s]+({nome})",
        rf"Dr\.?\s+({nome})\s*[-–]\s*Juiz",
    ):
        m = re.search(pat, texto)
        if m:
            return m.group(1).strip().rstrip(".,")
    return None


def _extrair_perito(texto: str) -> str | None:
    nome = r"[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+(?:\s+(?:de|da|do|dos|das|e)\s+)?(?:[A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÇ][a-záéíóúàèìòùâêîôûãõç]+\s*){1,5}"
    for pat in (
        rf"[Pp]erit[oa][:\s]+Dr[aº]?\.?\s*({nome})",
        rf"Dr[aº]?\.?\s*({nome})\s*[-–,]\s*CRM",
        rf"[Pp]erit[oa]\s+({nome})\s*,",
        rf"Laudo\s+(?:do\s+)?[Pp]erito\s+({nome})",
    ):
        m = re.search(pat, texto)
        if m:
            return m.group(1).strip().rstrip(".,")
    return None


def _extrair_resultado(texto: str) -> str | None:
    txt = texto.upper()
    if "JULGO PARCIALMENTE PROCEDENTE" in txt or "PARCIALMENTE PROCEDENTE" in txt:
        return "PARCIALMENTE_PROCEDENTE"
    if "JULGO PROCEDENTE" in txt or "JULGADO PROCEDENTE" in txt:
        return "PROCEDENTE"
    if "JULGO IMPROCEDENTE" in txt or "JULGADO IMPROCEDENTE" in txt:
        return "IMPROCEDENTE"
    if "EXTINGO O PROCESSO" in txt or "PROCESSO EXTINTO" in txt:
        return "EXTINTO"
    if "DEFIRO" in txt:
        return "DEFERIDO"
    return None


def _extrair_conclusao_laudo(texto: str) -> str | None:
    txt = texto.upper()
    if any(x in txt for x in ("INCAPACIDADE TOTAL", "TOTALMENTE INCAPACITAD", "INCAPAZ PARA TODA")):
        return "INCAPACIDADE_TOTAL"
    if any(x in txt for x in ("INCAPACIDADE PARCIAL", "PARCIALMENTE INCAPACITAD")):
        return "INCAPACIDADE_PARCIAL"
    if any(x in txt for x in ("SEM INCAPACIDADE", "NÃO HÁ INCAPACIDADE", "NAO HA INCAPACIDADE",
                               "CAPAZ PARA", "APTO PARA")):
        return "CAPAZ"
    return None


async def cmd_pecas(args):
    """Baixa as 3 ultimas pecas relevantes (decisao/intimacao/peticao/sentenca/despacho)."""
    if not Manifest.load(args.numero):
        print(f"sem manifest para {args.numero}; rode `diff --apply` antes.")
        return
    out_dir = Path("pecas") / args.numero.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    async with pje_context(headless=args.headless) as ctx:
        popup = await _abrir_detalhe(ctx, args.numero)
        html = await popup.content()
        docs = _parse_docs(html)
        relevantes = [d for d in docs if _e_relevante(d["tipo"])]
        relevantes.sort(key=lambda d: (d["desc"].startswith("A "), d["pos"]))
        top = relevantes[:args.n]
        print(f"docs total: {len(docs)}, relevantes: {len(relevantes)}, baixando top {len(top)}:")
        for d in top:
            print(f"  - {d['id']} | {d['tipo']} | {d['desc'][:60]}")
        await _baixar_pecas(popup, top, out_dir)


async def cmd_relatorio(args):
    """Gera relatorio diario: lista, identifica novidades, extrai 1a peca de cada, monta MD."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    rel_dir = Path("relatorios")
    rel_dir.mkdir(parents=True, exist_ok=True)
    out_md = rel_dir / f"relatorio-{hoje}.md"

    print(f"[relatorio] coletando estado atual...")
    async with pje_context(headless=args.headless) as ctx:
        processos = [p async for p in listar_acervo(ctx, debug=False)]
        pendentes = diff_acervo(processos)
        print(f"[relatorio] {len(processos)} processos, {len(pendentes)} com novidade")
        if args.limit:
            pendentes = pendentes[: args.limit]
            print(f"[relatorio] limitado a {len(pendentes)}")

        linhas: list[str] = [f"# Relatório diário — {hoje}", "",
                              f"**Acervo total:** {len(processos)} processos  ",
                              f"**Com novidade hoje:** {len(pendentes)}", ""]

        for i, p in enumerate(pendentes):
            print(f"[relatorio] {i+1}/{len(pendentes)} {p.numero} ({p.ultima_movimentacao})")
            linhas.append(f"## {p.numero}")
            if p.titulo:
                linhas.append(f"**Partes:** {p.titulo}  ")
            if p.vara:
                linhas.append(f"**Vara:** {p.vara}  ")
            linhas.append(f"**Última movimentação:** {p.ultima_movimentacao} — {p.ultima_movimentacao_desc or '-'}  ")
            try:
                popup = await _abrir_detalhe(ctx, p.numero)
                html = await popup.content()
                docs = _parse_docs(html)
                rels = [d for d in docs if _e_relevante(d["tipo"])]
                rels.sort(key=lambda d: (d["desc"].startswith("A "), d["pos"]))
                top = rels[:1]
                if not top:
                    linhas.append("_(sem peca relevante encontrada)_")
                else:
                    out_d = Path("pecas") / p.numero.replace("/", "_")
                    out_d.mkdir(parents=True, exist_ok=True)
                    res = await _baixar_pecas(popup, top, out_d, log_prefix="    ")
                    if res and res[0]["texto"]:
                        snippet = res[0]["texto"][:1500].strip()
                        linhas.append(f"**Peça {res[0]['tipo']}** ({res[0]['id']}):")
                        linhas.append("")
                        linhas.append("> " + snippet.replace("\n", "\n> "))
                    elif res:
                        linhas.append(f"_(peca {res[0]['id']} salva como {res[0]['ext']}; sem texto extraivel)_")
                await popup.close()
            except Exception as e:
                linhas.append(f"_(erro abrindo detalhe: {e})_")
            linhas.append("")

        # atualiza manifests
        now = _now_iso()
        for p in pendentes:
            m = Manifest.load(p.numero) or Manifest(numero=p.numero)
            m.titulo = p.titulo or m.titulo
            m.vara = p.vara or m.vara
            m.distribuido_em = p.distribuido_em or m.distribuido_em
            m.ultima_movimentacao = p.ultima_movimentacao or m.ultima_movimentacao
            m.ultima_movimentacao_desc = p.ultima_movimentacao_desc or m.ultima_movimentacao_desc
            m.pje_id = p.pje_id or m.pje_id
            m.pje_ca = p.pje_ca or m.pje_ca
            m.ultima_coleta = now
            m.save()

    out_md.write_text("\n".join(linhas), encoding="utf-8")
    print(f"\n[relatorio] salvo em {out_md}")


async def cmd_mapear(args):
    """Robô 2: lista o acervo atual, baixa decisões/sentenças/laudos de cada processo
    e constrói mapa de padrões por juiz e por perito."""
    import json

    mapas_dir = Path("mapas")
    mapas_dir.mkdir(exist_ok=True)
    juizes_fp = mapas_dir / "juizes.json"
    peritos_fp = mapas_dir / "peritos.json"
    decisoes_fp = mapas_dir / "decisoes.json"

    juizes: dict = json.loads(juizes_fp.read_text(encoding="utf-8")) if juizes_fp.exists() else {}
    peritos: dict = json.loads(peritos_fp.read_text(encoding="utf-8")) if peritos_fp.exists() else {}
    decisoes: list = json.loads(decisoes_fp.read_text(encoding="utf-8")) if decisoes_fp.exists() else []
    ids_ja_mapeados: set = {d["doc_id"] for d in decisoes}

    def _e_mapeavel(tipo: str) -> bool:
        return any(k in tipo.lower() for k in TIPOS_MAPEAR)

    def _registrar_perito(perito: str, conclusao: str | None) -> None:
        if perito not in peritos:
            peritos[perito] = {"total": 0, "incapacidade_total": 0,
                               "incapacidade_parcial": 0, "capaz": 0, "indefinido": 0}
        peritos[perito]["total"] += 1
        chave = (conclusao or "indefinido").lower()
        peritos[perito][chave if chave in peritos[perito] else "indefinido"] += 1

    async with pje_context(headless=args.headless) as ctx:
        print("[mapear] listando acervo atual...")
        processos = [p async for p in listar_acervo(ctx, debug=False)]
        if args.limit:
            processos = processos[: args.limit]
        print(f"[mapear] {len(processos)} processos no acervo")

        for i, p in enumerate(processos):
            print(f"[mapear] {i+1}/{len(processos)} {p.numero} | {p.ultima_movimentacao_desc or '-'}")
            try:
                popup = await _abrir_detalhe(ctx, p.numero)
                html = await popup.content()
                docs = _parse_docs(html)

                # Registra peritos dos títulos dos laudos (sem precisar baixar o corpo)
                for doc in docs:
                    if "laudo" in doc["tipo"].lower() and doc["id"] not in ids_ja_mapeados:
                        pt = _perito_do_titulo(doc["desc"])
                        if pt:
                            _registrar_perito(pt, None)
                            ids_ja_mapeados.add(doc["id"])

                alvo = [d for d in docs if _e_mapeavel(d["tipo"]) and d["id"] not in ids_ja_mapeados]
                if not alvo:
                    await popup.close()
                    continue

                out_d = Path("pecas") / p.numero.replace("/", "_")
                out_d.mkdir(parents=True, exist_ok=True)
                res = await _baixar_pecas(popup, alvo, out_d, log_prefix="    ")

                vara = p.vara or ""
                for r in res:
                    if not r["texto"]:
                        continue
                    texto = r["texto"]
                    tipo_lower = r["tipo"].lower()
                    entrada = {
                        "processo": p.numero,
                        "vara": vara,
                        "doc_id": r["id"],
                        "tipo": r["tipo"],
                        "data_mov": p.ultima_movimentacao,
                        "resultado": _extrair_resultado(texto),
                        "path": r["path"],
                    }
                    ids_ja_mapeados.add(r["id"])

                    if any(k in tipo_lower for k in ("decisão", "decisao", "sentença", "sentenca")):
                        juiz = _extrair_juiz(texto)
                        entrada["juiz"] = juiz
                        decisoes.append(entrada)
                        if juiz:
                            if juiz not in juizes:
                                juizes[juiz] = {"vara": vara, "total": 0,
                                                "procedente": 0, "improcedente": 0,
                                                "parcialmente_procedente": 0, "outros": 0}
                            juizes[juiz]["total"] += 1
                            res_key = (entrada["resultado"] or "outros").lower()
                            juizes[juiz][res_key if res_key in juizes[juiz] else "outros"] += 1

                    if "laudo" in tipo_lower:
                        perito = _perito_do_titulo(r["desc"]) or _extrair_perito(texto)
                        conclusao = _extrair_conclusao_laudo(texto)
                        if perito:
                            _registrar_perito(perito, conclusao)
                        decisoes.append({**entrada, "perito": perito, "conclusao": conclusao})

                await popup.close()
            except Exception as e:
                print(f"[mapear] erro {p.numero}: {e}")

    juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
    peritos_fp.write_text(json.dumps(peritos, ensure_ascii=False, indent=2), encoding="utf-8")
    decisoes_fp.write_text(json.dumps(decisoes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[mapear] {len(juizes)} juízes | {len(peritos)} peritos | {len(decisoes)} documentos")
    print(f"[mapear] arquivos em {mapas_dir.resolve()}")


async def cmd_diff(args):
    processos = await _coletar(headless=args.headless, debug=args.debug)
    pendentes = diff_acervo(processos)
    print(f"Acervo total: {len(processos)} | Pendentes: {len(pendentes)}")
    for p in pendentes:
        print(f"  + {p.numero}\t{p.ultima_movimentacao or '-'}")
    if args.apply:
        now = _now_iso()
        for p in pendentes:
            m = Manifest.load(p.numero) or Manifest(numero=p.numero)
            m.classe = p.classe
            m.titulo = p.titulo or m.titulo
            m.vara = p.vara or m.vara
            m.distribuido_em = p.distribuido_em or m.distribuido_em
            m.ultima_movimentacao = p.ultima_movimentacao or m.ultima_movimentacao
            m.ultima_movimentacao_desc = p.ultima_movimentacao_desc or m.ultima_movimentacao_desc
            m.pje_id = p.pje_id or m.pje_id
            m.pje_ca = p.pje_ca or m.pje_ca
            m.ultima_coleta = now
            m.save()
        print(f"\n{len(pendentes)} manifests atualizados.")


async def cmd_turmas(args):
    """Robô 2G: pesquisa as 3 Turmas Recursais PE no pje2g, baixa votos/acórdãos/ementas
    e constrói mapas/juizes_tr.json com padrões dos relatores."""
    import json
    from .turmas_recursais import (
        pje2g_context, TURMAS_PE,
        preencher_e_pesquisar, extrair_processos_pagina, ir_proxima_pagina,
        ir_para_pagina, pagina_ativa, total_resultados,
        extrair_relator, extrair_resultado, extrair_ementa, extrair_advogados,
        TIPOS_DOC_TR, TIPOS_VETO_TR,
    )

    # --so-turma filtra uma turma específica (1, 2 ou 3) — permite rodar em paralelo
    turmas_ativas = TURMAS_PE
    turma_num = getattr(args, 'so_turma', None)
    if turma_num:
        nomes = list(TURMAS_PE.keys())
        if 1 <= turma_num <= 3:
            turmas_ativas = {nomes[turma_num - 1]: TURMAS_PE[nomes[turma_num - 1]]}
        else:
            print(f"[turmas] --so-turma deve ser 1, 2 ou 3. Usando todas.")

    # Arquivo JSON separado por turma (evita conflito entre processos paralelos)
    sufixo = f"_t{turma_num}" if turma_num else ""

    mapas_dir = Path("mapas")
    mapas_dir.mkdir(exist_ok=True)
    acordaos_dir = mapas_dir / "acordaos_tr"
    acordaos_dir.mkdir(exist_ok=True)
    juizes_fp = mapas_dir / f"juizes_tr{sufixo}.json"
    acordaos_fp = mapas_dir / f"acordaos_tr{sufixo}.json"

    juizes: dict = json.loads(juizes_fp.read_text(encoding="utf-8")) if juizes_fp.exists() else {}
    acordaos: list = json.loads(acordaos_fp.read_text(encoding="utf-8")) if acordaos_fp.exists() else []
    processos_ja_mapeados: set = {a["processo"] for a in acordaos}

    def _e_relevante_tr(tipo: str) -> bool:
        t = tipo.lower()
        return any(k in t for k in TIPOS_DOC_TR) and not any(v in t for v in TIPOS_VETO_TR)

    def _registrar_juiz(relator: str, resultado: str | None, orgao: str) -> None:
        if relator not in juizes:
            juizes[relator] = {"orgao": orgao, "total": 0,
                               "procedente": 0, "improcedente": 0,
                               "parcialmente_procedente": 0, "outros": 0}
        juizes[relator]["total"] += 1
        chave = (resultado or "outros").lower()
        juizes[relator][chave if chave in juizes[relator] else "outros"] += 1

    total = 0
    CONC = max(1, getattr(args, "conc", 3))
    async with pje2g_context(headless=args.headless, turma_num=turma_num) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # JS que clica no link do CNJ (abre o popup dos autos) — evita o botão "Peticionar"
        # (btn-default/btn-sm) que vem antes no DOM com o mesmo idProcessoSelecionado.
        _JS_CLICK_CNJ = """(pid) => {
            const CNJ_RE = /\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
            function matchId(oc) {
                return oc.includes(':' + pid + ',') || oc.includes(':' + pid + '}') ||
                       oc.includes("'" + pid + "'") || oc.includes('"' + pid + '"');
            }
            function isPeticionar(a) {
                const cls = a.className || '';
                const title = (a.getAttribute('title') || '').toLowerCase();
                return cls.includes('btn-default') || cls.includes('btn-sm') ||
                       title.includes('peticionar') || title.includes('juntar');
            }
            for (const a of document.querySelectorAll('a[onclick*="idProcessoSelecionado"]')) {
                const oc = a.getAttribute('onclick') || '';
                if (!matchId(oc) || isPeticionar(a)) continue;
                const txt = a.textContent || '', title = a.getAttribute('title') || '';
                if (CNJ_RE.test(txt) || CNJ_RE.test(title)) { a.click(); return true; }
            }
            for (const a of document.querySelectorAll(
                    'a.btn-link[onclick*="idProcessoSelecionado"],' +
                    'a.btn-condensed[onclick*="idProcessoSelecionado"]')) {
                const oc = a.getAttribute('onclick') || '';
                if (matchId(oc) && !isPeticionar(a)) { a.click(); return true; }
            }
            return false;
        }"""

        async def _abrir_popup(proc_id):
            """Clica no link do CNJ e captura o popup dos autos (ou None).
            Aberturas devem ser SEQUENCIAIS — ctx.expect_page() é racy em paralelo."""
            page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            try:
                async with ctx.expect_page(timeout=25_000) as popup_info:
                    clicou = await page.evaluate(_JS_CLICK_CNJ, proc_id)
                    if not clicou:
                        raise RuntimeError("cnj-link-nao-encontrado")
                return await popup_info.value
            except Exception as e:
                if page.is_closed() or "closed" in str(e).lower():
                    raise  # browser caiu → propaga (preserva checkpoint)
                return None

        async def _extrair_de_popup(popup, numero, proc_id, relator_row, orgao_nome):
            """Processa um popup já aberto: parse + download + monta o dict do acórdão.
            NÃO toca estado compartilhado (retorna o dict; consolidação fica no chamador)."""
            await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
            await popup.wait_for_timeout(6_000)
            html_detalhe = await popup.content()
            docs = _parse_docs(html_detalhe)
            texto_pagina = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_detalhe))
            relator_meta = extrair_relator(texto_pagina) or relator_row
            ementa_meta = extrair_ementa(texto_pagina)
            alvo = [d for d in docs if _e_relevante_tr(d["tipo"])]
            print(f"[turmas]   {numero}: {len(docs)} docs, {len(alvo)} relevantes")
            out_d = acordaos_dir / numero.replace("/", "_").replace(".", "_")
            out_d.mkdir(parents=True, exist_ok=True)
            res_dl = await _baixar_pecas(popup, alvo[:5], out_d, log_prefix=f"   [{numero}]")
            texto_doc = " ".join(r["texto"] for r in res_dl if r["texto"])
            relator = extrair_relator(texto_doc) or relator_meta
            return {
                "processo": numero, "orgao": orgao_nome, "relatoria": relator_row,
                "relator": relator, "resultado": extrair_resultado(texto_doc),
                "ementa": extrair_ementa(texto_doc) or ementa_meta,
                "advogados": extrair_advogados(texto_doc),
                "arquivos": [r["path"] for r in res_dl],
            }

        # Itera pelas turmas selecionadas
        for orgao_nome, orgao_value in turmas_ativas.items():
            print(f"\n[turmas] ===== {orgao_nome} =====")
            await preencher_e_pesquisar(
                page, orgao_value, orgao_nome,
                args.parte, args.data_ini, args.data_fim
            )

            if args.debug:
                dbg = Path("debug")
                dbg.mkdir(exist_ok=True)
                slug = orgao_value
                (dbg / f"tr_resultado_{slug}.html").write_text(
                    await page.content(), encoding="utf-8"
                )
                print(f"[turmas] debug salvo em debug/tr_resultado_{slug}.html")

            # Carrega o checkpoint ANTES de tudo (para preservá-lo se algo falhar)
            ckpt_fp = mapas_dir / f"checkpoint_t{sufixo}_{orgao_value}.json"
            pagina_inicio = 1
            if ckpt_fp.exists():
                try:
                    pagina_inicio = json.loads(ckpt_fp.read_text()).get("pagina", 1)
                except Exception:
                    pagina_inicio = 1

            def _preserva_e_sai(motivo):
                """Encerra preservando o checkpoint na página de retomada — NUNCA
                reinicia da pág 1 nem rebaixa o checkpoint. O wrapper relança e tenta
                de novo numa sessão já autenticada/página carregada."""
                print(f"[turmas] ⚠️  {motivo} — checkpoint preservado (pág {pagina_inicio}), encerrando p/ retry.")
                if pagina_inicio > 1:
                    ckpt_fp.write_text(json.dumps({"pagina": pagina_inicio, "orgao": orgao_value, "orgao_nome": orgao_nome}))

            # Total de resultados → última página real (nunca concluir antes dela)
            total_res = await total_resultados(page)
            last_page = (total_res + 19) // 20 if total_res else 10**9
            print(f"[turmas] {total_res} resultados (~{last_page if total_res else '??'} páginas)")

            # Página de resultados vazia = login/sessão incompleta ou busca não carregou.
            if total_res == 0:
                _preserva_e_sai("página de resultados vazia (login/sessão?)")
                return

            # Retoma saltando DIRETO para a página do checkpoint (sem clicar 1 a 1).
            if pagina_inicio > 1:
                print(f"[turmas] ⏩ checkpoint: saltando direto para pág {pagina_inicio}...")
                ok = await ir_para_pagina(page, pagina_inicio)
                atual = await pagina_ativa(page)
                if ok and atual >= pagina_inicio:
                    print(f"[turmas] ✅ retomando na pág {pagina_inicio} (datascroller em {atual})")
                else:
                    _preserva_e_sai(f"salto falhou (parou na pág {atual})")
                    return

            pagina = pagina_inicio
            while True:
                processos = await extrair_processos_pagina(page)
                print(f"[turmas] pág {pagina}: {len(processos)} processos")
                if not processos:
                    if pagina >= last_page:
                        if ckpt_fp.exists():
                            ckpt_fp.unlink()
                        print(f"[turmas] ✅ turma concluída (pág {pagina} ≥ última {last_page}).")
                    else:
                        print(f"[turmas] ⚠️  pág {pagina} vazia ANTES do fim (~{last_page}) — página transitória; checkpoint mantido p/ retry.")
                        ckpt_fp.write_text(json.dumps({"pagina": pagina, "orgao": orgao_value, "orgao_nome": orgao_nome}))
                    break

                # Fila de pendentes (pula os já mapeados — dedup por CNJ)
                pendentes = []
                for link in processos:
                    numero = link.get("cnj") or f"TR-{orgao_value}-{total + len(pendentes) + 1}"
                    if numero in processos_ja_mapeados:
                        continue
                    pendentes.append((numero, link.get("proc_id", ""), link.get("relatoria", "")))

                parar = False
                # Processa em LOTES concorrentes de CONC popups (mais rápido; cabe em 8 GB)
                for i in range(0, len(pendentes), CONC):
                    # Sessão expirou? (redirecionou para o SSO) — encerra preservando checkpoint
                    url_atual = page.url or ""
                    if "login" in url_atual or "sso.cloud" in url_atual or "realms/pje" in url_atual:
                        print("[turmas] ⚠️  Sessão expirada detectada — encerrando para relogar")
                        juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
                        acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
                        ckpt_fp.write_text(json.dumps({"pagina": pagina, "orgao": orgao_value, "orgao_nome": orgao_nome}))
                        print(f"[turmas] Checkpoint salvo: pág {pagina}. Relance — vai retomar aqui.")
                        return

                    lote = pendentes[i:i + CONC]
                    # 1) Abre os popups SEQUENCIALMENTE (ctx.expect_page não é seguro em paralelo)
                    abertos = []
                    for (numero, proc_id, relator_row) in lote:
                        popup = await _abrir_popup(proc_id)  # propaga se o browser cair
                        if popup is None:
                            print(f"[turmas]   {numero}: link não encontrado, skip")
                            continue
                        abertos.append((numero, proc_id, relator_row, popup))

                    # 2) Processa o lote CONCORRENTEMENTE; fecha cada popup ao terminar
                    async def _run(numero, proc_id, relator_row, popup):
                        try:
                            return await _extrair_de_popup(popup, numero, proc_id, relator_row, orgao_nome)
                        except Exception as e:
                            print(f"[turmas]   erro {numero}: {e}")
                            return None
                        finally:
                            if not popup.is_closed():
                                try:
                                    await popup.close()
                                except Exception:
                                    pass

                    resultados = await asyncio.gather(
                        *[_run(n, p, r, pop) for (n, p, r, pop) in abertos]
                    )

                    # 3) Consolida SEQUENCIALMENTE (sem race no estado compartilhado)
                    for (numero, _pid, _rr, _pop), res in zip(abertos, resultados):
                        if not isinstance(res, dict):
                            continue
                        acordaos.append(res)
                        processos_ja_mapeados.add(numero)
                        total += 1
                        if res.get("relator"):
                            _registrar_juiz(res["relator"], res.get("resultado"), orgao_nome)

                    # Salva a cada lote concluído
                    juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
                    acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[turmas] checkpoint: {total} processos salvos")

                    if args.limit and total >= args.limit:
                        print(f"[turmas] limite de {args.limit} atingido.")
                        parar = True
                        break

                if parar:
                    break

                teve_proxima = await ir_proxima_pagina(page)
                if not teve_proxima:
                    if pagina >= last_page:
                        # Fim REAL — última página alcançada
                        if ckpt_fp.exists():
                            ckpt_fp.unlink()
                        print(f"[turmas] ✅ turma concluída (última página {pagina}).")
                    else:
                        # Falso fim: 'próxima' não encontrada antes da última página
                        # (página quebrada/transitória). NÃO concluir — manter checkpoint
                        # e encerrar para o wrapper relançar e saltar de volta (retry).
                        print(f"[turmas] ⚠️  'próxima' não encontrada na pág {pagina} de ~{last_page} (página quebrada?) — checkpoint MANTIDO p/ retry.")
                        ckpt_fp.write_text(json.dumps({"pagina": pagina, "orgao": orgao_value, "orgao_nome": orgao_nome}))
                    break
                pagina += 1
                # Salva checkpoint de página a cada avanço
                ckpt_fp.write_text(json.dumps({"pagina": pagina, "orgao": orgao_value, "orgao_nome": orgao_nome}))

            if args.limit and total >= args.limit:
                break

    # Salva resultados
    juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
    acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[turmas] {total} processos mapeados | {len(juizes)} relatores")
    print(f"[turmas] arquivos em {mapas_dir.resolve()}")


async def cmd_varas(args):
    """Robô 1G: pesquisa varas JEF no pje1g, baixa sentenças/decisões e mapeia juízes."""
    import json
    from datetime import date
    from .varas_1g import (
        pje1g_consulta_context, descobrir_varas_1g,
        preencher_e_pesquisar_1g, extrair_processos_pagina_1g,
        ir_proxima_pagina_1g, TIPOS_DOC_1G, TIPOS_VETO_1G,
        PJE1G_BASE_URL,
    )
    from .turmas_recursais import (
        extrair_relator, extrair_resultado, extrair_ementa, extrair_advogados,
    )

    mapas_dir = Path("mapas")
    mapas_dir.mkdir(exist_ok=True)
    sentencas_dir = mapas_dir / "sentencas_1g"
    sentencas_dir.mkdir(exist_ok=True)

    sufixo = getattr(args, 'perfil_sufixo', '') or ''
    juizes_fp  = mapas_dir / f"juizes_1g{sufixo}.json"
    acordaos_fp = mapas_dir / f"acordaos_1g{sufixo}.json"

    juizes: dict  = json.loads(juizes_fp.read_text(encoding="utf-8"))  if juizes_fp.exists()  else {}
    acordaos: list = json.loads(acordaos_fp.read_text(encoding="utf-8")) if acordaos_fp.exists() else []
    ja_mapeados: set = {a["processo"] for a in acordaos}

    data_fim = args.data_fim or date.today().strftime("%d/%m/%Y")

    def _e_relevante(tipo: str) -> bool:
        t = tipo.lower()
        return any(k in t for k in TIPOS_DOC_1G) and not any(v in t for v in TIPOS_VETO_1G)

    def _registrar_juiz(juiz: str, resultado: str | None, vara: str) -> None:
        if juiz not in juizes:
            juizes[juiz] = {"vara": vara, "total": 0, "procedente": 0,
                            "improcedente": 0, "parcialmente_procedente": 0, "outros": 0}
        juizes[juiz]["total"] += 1
        chave = (resultado or "outros").lower()
        juizes[juiz][chave if chave in juizes[juiz] else "outros"] += 1

    total = 0
    async with pje1g_consulta_context(headless=args.headless, sufixo=sufixo) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Descobre varas disponíveis (debug ou listagem)
        if args.debug or args.listar_varas:
            print("[1g] Descobrindo varas disponíveis no formulário...")
            opcoes = await descobrir_varas_1g(page)
            print(f"[1g] {len(opcoes)} varas encontradas:")
            for o in opcoes:
                print(f"  value={o['value']!r:>8}  {o['text']}")
            if args.listar_varas:
                return

        # Filtra varas pelo texto passado em --varas
        if args.debug:
            opcoes = await descobrir_varas_1g(page)
        else:
            await page.goto(
                f"{PJE1G_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam",
                wait_until="domcontentloaded", timeout=60_000
            )
            await page.wait_for_timeout(2_000)
            opcoes = await descobrir_varas_1g(page)

        # Filtra por value direto (--valores) ou por nome (--varas)
        if args.valores:
            values_set = {v.strip() for v in args.valores.split(',')}
            varas_selecionadas = [o for o in opcoes if o['value'] in values_set]
        else:
            filtros = [f.strip().lower() for f in args.varas.split(',') if f.strip()]
            varas_selecionadas = [
                o for o in opcoes
                if any(o['text'].lower().startswith(f) for f in filtros)
            ]

        if not varas_selecionadas:
            print(f"[1g] Nenhuma vara encontrada com filtro: {args.varas}")
            print("[1g] Varas disponíveis:")
            for o in opcoes[:20]:
                print(f"  {o['text']}")
            return

        print(f"[1g] {len(varas_selecionadas)} vara(s) selecionada(s):")
        for v in varas_selecionadas:
            print(f"  {v['text']} (value={v['value']})")

        for vara in varas_selecionadas:
            print(f"\n[1g] ===== {vara['text']} =====")
            await preencher_e_pesquisar_1g(
                page, vara['value'], vara['text'],
                args.parte, args.data_ini, data_fim
            )

            if args.debug:
                dbg = Path("debug")
                dbg.mkdir(exist_ok=True)
                (dbg / f"varas_1g_{vara['value']}.html").write_text(
                    await page.content(), encoding="utf-8"
                )
                print(f"[1g] debug: varas_1g_{vara['value']}.html")

            pagina = 1
            while True:
                processos = await extrair_processos_pagina_1g(page)
                print(f"[1g] pág {pagina}: {len(processos)} processos")
                if not processos:
                    break

                for link in processos:
                    numero = link.get("cnj") or f"1G-{vara['value']}-{total+1}"
                    proc_id = link.get("proc_id", "")
                    vara_row = link.get("relatoria", vara['text'])
                    if numero in ja_mapeados:
                        continue

                    print(f"[1g]   {numero} (id={proc_id})")
                    try:
                        url_atual = page.url or ""
                        if "login" in url_atual or "sso.cloud" in url_atual:
                            print(f"[1g] ⚠️  Sessão expirada — salvando e saindo")
                            juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
                            acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
                            return

                        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
                        async with ctx.expect_page(timeout=25_000) as popup_info:
                            clicou = await page.evaluate(
                                """(pid) => {
                                    const CNJ_RE = /\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
                                    function matchId(oc) {
                                        return oc.includes(':'+pid+',') || oc.includes(':'+pid+'}') ||
                                               oc.includes("'"+pid+"'") || oc.includes('"'+pid+'"');
                                    }
                                    function isPeticionar(a) {
                                        const cls = a.className || '';
                                        const title = (a.getAttribute('title')||'').toLowerCase();
                                        return cls.includes('btn-default') || cls.includes('btn-sm') ||
                                               title.includes('peticionar') || title.includes('juntar');
                                    }
                                    for (const a of document.querySelectorAll('a[onclick*="idProcessoSelecionado"]')) {
                                        const oc = a.getAttribute('onclick')||'';
                                        if (!matchId(oc) || isPeticionar(a)) continue;
                                        const txt = a.textContent||'';
                                        const title = a.getAttribute('title')||'';
                                        if (CNJ_RE.test(txt) || CNJ_RE.test(title)) { a.click(); return true; }
                                    }
                                    for (const a of document.querySelectorAll(
                                            'a.btn-link[onclick*="idProcessoSelecionado"],' +
                                            'a.btn-condensed[onclick*="idProcessoSelecionado"]')) {
                                        const oc = a.getAttribute('onclick')||'';
                                        if (matchId(oc) && !isPeticionar(a)) { a.click(); return true; }
                                    }
                                    return false;
                                }""",
                                proc_id,
                            )

                        if not clicou:
                            print(f"[1g]     link não encontrado, skip")
                            continue

                        popup = await popup_info.value
                        await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
                        await popup.wait_for_timeout(5_000)

                        html_detalhe = await popup.content()
                        docs = _parse_docs(html_detalhe)
                        texto_pagina = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_detalhe))
                        juiz_meta = extrair_relator(texto_pagina)
                        ementa_meta = extrair_ementa(texto_pagina)

                        alvo = [d for d in docs if _e_relevante(d["tipo"])]
                        print(f"[1g]     {len(docs)} docs, {len(alvo)} relevantes")

                        out_d = sentencas_dir / numero.replace("/", "_").replace(".", "_")
                        out_d.mkdir(parents=True, exist_ok=True)
                        res_dl = await _baixar_pecas(popup, alvo[:4], out_d, log_prefix="      ")

                        texto_doc = " ".join(r["texto"] for r in res_dl if r["texto"])
                        juiz = extrair_relator(texto_doc) or juiz_meta
                        resultado = extrair_resultado(texto_doc)
                        ementa = extrair_ementa(texto_doc) or ementa_meta
                        advogados = extrair_advogados(texto_doc)

                        acordaos.append({
                            "processo": numero,
                            "vara": vara_row or vara['text'],
                            "juiz": juiz,
                            "resultado": resultado,
                            "ementa": ementa,
                            "advogados": advogados,
                            "arquivos": [r["path"] for r in res_dl],
                        })
                        ja_mapeados.add(numero)
                        total += 1
                        if juiz:
                            _registrar_juiz(juiz, resultado, vara_row or vara['text'])

                        await popup.close()

                        if total % 5 == 0:
                            juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
                            acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
                            print(f"[1g] checkpoint: {total} processos salvos")

                        if args.limit and total >= args.limit:
                            print(f"[1g] limite de {args.limit} atingido.")
                            break

                    except Exception as e:
                        print(f"[1g]   erro {numero}: {e}")

                if args.limit and total >= args.limit:
                    break

                teve_proxima = await ir_proxima_pagina_1g(page)
                if not teve_proxima:
                    break
                pagina += 1

            if args.limit and total >= args.limit:
                break

    juizes_fp.write_text(json.dumps(juizes, ensure_ascii=False, indent=2), encoding="utf-8")
    acordaos_fp.write_text(json.dumps(acordaos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[1g] {total} processos | {len(juizes)} juízes")
    print(f"[1g] arquivos em {mapas_dir.resolve()}")


async def cmd_merge_turmas(args):
    """Unifica acordaos_tr_t1.json + t2 + t3 em acordaos_tr.json e juizes_tr.json."""
    import json
    mapas_dir = Path("mapas")
    todos: list = []
    juizes_merged: dict = {}
    vistos: set = set()

    for t in [1, 2, 3]:
        fp = mapas_dir / f"acordaos_tr_t{t}.json"
        jf = mapas_dir / f"juizes_tr_t{t}.json"
        if fp.exists():
            batch = json.loads(fp.read_text(encoding="utf-8"))
            novos = [r for r in batch if r["processo"] not in vistos]
            vistos.update(r["processo"] for r in novos)
            todos.extend(novos)
            print(f"  t{t}: {len(batch)} processos ({len(novos)} únicos adicionados)")
        if jf.exists():
            j = json.loads(jf.read_text(encoding="utf-8"))
            for nome, stats in j.items():
                if nome not in juizes_merged:
                    juizes_merged[nome] = stats.copy()
                else:
                    for k in ("total", "procedente", "improcedente", "parcialmente_procedente", "outros"):
                        juizes_merged[nome][k] = juizes_merged[nome].get(k, 0) + stats.get(k, 0)

    # Também incorpora o arquivo principal atual (rodada sem --so-turma)
    fp_main = mapas_dir / "acordaos_tr.json"
    if fp_main.exists():
        batch = json.loads(fp_main.read_text(encoding="utf-8"))
        novos = [r for r in batch if r["processo"] not in vistos]
        vistos.update(r["processo"] for r in novos)
        todos.extend(novos)
        print(f"  principal: {len(batch)} processos ({len(novos)} únicos adicionados)")

    out_fp = mapas_dir / "acordaos_tr_merged.json"
    out_jf = mapas_dir / "juizes_tr_merged.json"
    out_fp.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
    out_jf.write_text(json.dumps(juizes_merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nMerge concluído: {len(todos)} processos únicos → {out_fp}")
    print(f"Juízes: {len(juizes_merged)} relatores → {out_jf}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--debug", action="store_true", help="salva screenshot + HTML do painel em debug/")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("listar")

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--apply", action="store_true", help="atualiza manifests com o delta")

    p_det = sub.add_parser("detalhe", help="abre 1 processo e dumpa HTML em debug/")
    p_det.add_argument("numero", help="CNJ do processo (precisa ter manifest com pje_id/pje_ca)")

    p_pec = sub.add_parser("pecas", help="baixa N pecas relevantes (decisao/intimacao/peticao)")
    p_pec.add_argument("numero", help="CNJ do processo")
    p_pec.add_argument("-n", type=int, default=3, help="quantas pecas (default 3)")

    p_ins = sub.add_parser("inspect", help="diagnostico de tokens/storage da popup de detalhe")
    p_ins.add_argument("numero", help="CNJ do processo")

    p_rel = sub.add_parser("relatorio", help="gera relatorio diario com novidades + texto da peca mais recente")
    p_rel.add_argument("--limit", type=int, default=0, help="processa no maximo N novidades (0 = todas)")

    p_map = sub.add_parser("mapear", help="robe 2: baixa decisoes/laudos e mapeia padroes de juizes e peritos")
    p_map.add_argument("--limit", type=int, default=0, help="processa no maximo N processos (0 = todos)")

    p_v = sub.add_parser("varas", help="robô 1G: pesquisa varas JEF no pje1g e baixa sentenças/decisões")
    p_v.add_argument("--varas", default="",
                     help="filtro de varas por nome (separado por vírgula)")
    p_v.add_argument("--valores", default="",
                     help="values do select separados por vírgula (ex: 77,151,155)")
    p_v.add_argument("--data-ini", default="01/01/2025")
    p_v.add_argument("--data-fim", default="", help="default: hoje")
    p_v.add_argument("--parte", default="INSS")
    p_v.add_argument("--limit", type=int, default=0)
    p_v.add_argument("--perfil-sufixo", default="", help="sufixo do perfil browser (para paralelo)")
    p_v.add_argument("--listar-varas", action="store_true", help="só lista as varas disponíveis e sai")
    p_v.add_argument("--debug", action="store_true")

    p_tr = sub.add_parser("turmas", help="robô 2G: pesquisa turmas recursais PE no pje2g e baixa votos/acórdãos/ementas")
    p_tr.add_argument("--data-ini", default="01/01/2021", help="data início (DD/MM/AAAA)")
    p_tr.add_argument("--data-fim", default="01/02/2026", help="data fim (DD/MM/AAAA)")
    p_tr.add_argument("--parte", default="INSS", help="nome da parte (default: INSS)")
    p_tr.add_argument("--orgao", default="Turma Recursal", help="texto para filtrar órgão julgador")
    p_tr.add_argument("--limit", type=int, default=0, help="máximo de processos a baixar (0=todos)")
    p_tr.add_argument("--so-turma", type=int, default=0, metavar="N",
                      help="rodar apenas 1 turma: 1=1ªTR, 2=2ªTR, 3=3ªTR (para execução paralela)")
    p_tr.add_argument("--conc", type=int, default=3, metavar="N",
                      help="processos abertos em paralelo por lote (default 3; cuidado com RAM)")
    p_tr.add_argument("--debug", action="store_true", help="salva HTML do formulário em debug/")

    sub.add_parser("merge-turmas", help="unifica acordaos_tr_t1/t2/t3.json em acordaos_tr.json")

    args = parser.parse_args()
    coro = {"listar": cmd_listar, "diff": cmd_diff, "detalhe": cmd_detalhe,
            "pecas": cmd_pecas, "inspect": cmd_inspect, "relatorio": cmd_relatorio,
            "mapear": cmd_mapear, "turmas": cmd_turmas, "varas": cmd_varas,
            "merge-turmas": cmd_merge_turmas}[args.cmd](args)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
