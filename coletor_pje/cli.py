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
                    "petição", "peticao", "sentença", "sentenca", "despacho")
# vetos (mesmo que match em relevantes, descarta)
TIPOS_VETO = ("certidão", "certidao")

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
        print(f"{p.numero}\t{p.pje_id or '-'}\t{p.pje_ca or '-'}\t{p.titulo or ''}")
    print(f"\nTotal: {len(processos)}")


async def _abrir_detalhe(ctx, cnj: str):
    """Navega ate o painel, busca o CNJ, dispara o link e devolve a popup."""
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

    await page.evaluate(
        """() => {
            const a = document.querySelector('a[id$=":-1::cxItem"]');
            if (a) a.onclick();
        }"""
    )
    await page.wait_for_timeout(6_000)

    await page.fill("#txtConsultaContextoAcervo", cnj)
    await page.click("#btnPesquisarContexto")
    await page.wait_for_timeout(8_000)

    async with ctx.expect_page(timeout=30_000) as popup_info:
        await page.evaluate(
            """(cnj) => {
                const links = document.querySelectorAll('a[onclick*="listProcessoCompletoAdvogado"]');
                let target = null;
                for (const a of links) {
                    if ((a.getAttribute('onclick') || '').includes(cnj) ||
                        (a.textContent || '').includes(cnj)) { target = a; break; }
                }
                if (!target && links.length > 0) target = links[0];
                if (target) target.dispatchEvent(
                    new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
            }""",
            cnj,
        )
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
        # prefere principais (sem desc ou comecando com "P ") sobre anexos ("A ...")
        relevantes.sort(key=lambda d: (d["desc"].startswith("A "), d["pos"]))
        top = relevantes[:args.n]

        print(f"docs total: {len(docs)}, relevantes: {len(relevantes)}, baixando top {len(top)}:")
        for d in top:
            print(f"  - {d['id']} | {d['tipo']} | {d['desc'][:60]}")

        import base64
        for d in top:
            slug = re.sub(r"[^A-Za-z0-9._-]+", "_", d["tipo"])[:40]
            src = f"{PJE_BASE_URL}/pje/seam/resource/rest/pje-legacy/documento/download/{d['id']}"
            # 1) clica no doc dentro do timeline pra setar state no servidor
            clicado = await popup.evaluate(
                """(docId) => {
                    // 1) acha qualquer no de texto contendo o docId
                    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let target = null;
                    while (tw.nextNode()) {
                        if (tw.currentNode.nodeValue && tw.currentNode.nodeValue.includes(docId)) {
                            target = tw.currentNode.parentElement; break;
                        }
                    }
                    if (!target) return 'no-text-' + docId;
                    // 2) sobe a arvore ate achar <a> com onclick A4J.AJAX.Submit em divTimeLine
                    let el = target;
                    for (let i = 0; i < 8 && el; i++) {
                        if (el.tagName === 'A' && (el.getAttribute('onclick')||'').includes('divTimeLine')) {
                            el.click(); return 'a: ' + el.id;
                        }
                        el = el.parentElement;
                    }
                    // 3) busca anchor descendente do container do texto
                    let cont = target;
                    for (let i = 0; i < 5 && cont; i++) { cont = cont.parentElement; }
                    if (cont) {
                        const a = cont.querySelector('a[onclick*="divTimeLine"]');
                        if (a) { a.click(); return 'desc: ' + a.id; }
                    }
                    return 'no-anchor-' + docId;
                }""",
                d["id"],
            )
            print(f"  [{d['id']}] timeline click -> {clicado}")
            await popup.wait_for_timeout(4_000)
            try:
                res = await popup.evaluate(
                    """(src) => {
                        const xhr = new XMLHttpRequest();
                        xhr.open('GET', src, false);
                        xhr.overrideMimeType('text/plain; charset=x-user-defined');
                        xhr.send();
                        const ct = (xhr.getResponseHeader('content-type') || '').toLowerCase();
                        const txt = xhr.responseText || '';
                        // converte cada char (0..255) em byte
                        const bytes = new Uint8Array(txt.length);
                        for (let i = 0; i < txt.length; i++) bytes[i] = txt.charCodeAt(i) & 0xff;
                        let bin = '';
                        for (let i = 0; i < bytes.length; i += 0x8000) {
                            bin += String.fromCharCode.apply(null, bytes.subarray(i, i+0x8000));
                        }
                        return {status: xhr.status, ctype: ct, size: bytes.length, b64: btoa(bin)};
                    }""",
                    src,
                )
                body = base64.b64decode(res["b64"])
                ctype = res["ctype"]
                ext = ".pdf" if "pdf" in ctype else (".html" if "html" in ctype else ".bin")
                fp = out_dir / f"{d['id']}_{slug}{ext}"
                fp.write_bytes(body)
                print(f"  [{d['id']}] status={res['status']} ctype={ctype} {len(body)}B -> {fp.name}")
            except Exception as e:
                print(f"  [{d['id']}] erro: {e}")


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
            m.titulo = p.titulo
            m.ultima_movimentacao = p.ultima_movimentacao
            m.pje_id = p.pje_id or m.pje_id
            m.pje_ca = p.pje_ca or m.pje_ca
            m.ultima_coleta = now
            m.save()
        print(f"\n{len(pendentes)} manifests atualizados.")


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

    args = parser.parse_args()
    coro = {"listar": cmd_listar, "diff": cmd_diff, "detalhe": cmd_detalhe,
            "pecas": cmd_pecas, "inspect": cmd_inspect}[args.cmd](args)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
