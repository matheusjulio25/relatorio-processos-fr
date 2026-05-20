"""CLI do coletor.

Uso:
    python -m coletor_pje.cli listar          # lista todo o acervo
    python -m coletor_pje.cli diff            # mostra só o delta vs manifests/
    python -m coletor_pje.cli diff --apply    # atualiza manifests com o delta
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from .acervo import listar_acervo
from .login import pje_context, PJE_BASE_URL
from .manifest import Manifest, diff_acervo


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


async def cmd_detalhe(args):
    """Abre 1 processo via popup do painel (sessao correta) e dumpa HTML em debug/.

    Fluxo: vai pro painel -> Acervo -> usa o campo de busca por CNJ -> clica no
    link da listagem -> captura a popup que o PJe abre (window.open + AJAX que
    prepara contexto). Navegar direto pra listProcessoCompletoAdvogado.seam cai
    em error.seam porque pula a AJAX de contexto.
    """
    from pathlib import Path
    from .acervo import ACERVO_PATH

    m = Manifest.load(args.numero)
    if not m:
        print(f"sem manifest para {args.numero}; rode `diff --apply` antes.")
        return

    debug = Path("debug")
    debug.mkdir(exist_ok=True)
    async with pje_context(headless=args.headless) as ctx:
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
        print(f"  cidades expandidas: {qtd}")
        try:
            await page.wait_for_function(
                f"() => document.querySelectorAll('a[id$=\":-1::cxItem\"]').length >= {qtd}",
                timeout=120_000,
            )
        except Exception:
            pass
        await page.wait_for_timeout(2_000)

        ativou = await page.evaluate(
            """() => {
                const a = document.querySelector('a[id$=":-1::cxItem"]');
                if (!a) return false;
                a.onclick();
                return true;
            }"""
        )
        print(f"  ativou caixa: {ativou}")
        await page.wait_for_timeout(6_000)

        print(f"buscando CNJ {args.numero}")
        await page.fill("#txtConsultaContextoAcervo", args.numero)
        await page.click("#btnPesquisarContexto")
        await page.wait_for_timeout(8_000)

        achados = await page.evaluate(
            """() => {
                const links = document.querySelectorAll('a[onclick*="listProcessoCompletoAdvogado"]');
                return Array.from(links).slice(0,5).map(a => (a.getAttribute('onclick')||'').slice(0,200));
            }"""
        )
        print(f"  links com onclick listProcesso achados: {len(achados)}")
        for s in achados[:3]:
            print(f"    {s[:140]}...")

        if debug_dump := True:
            (debug / f"busca_{args.numero}.html").write_text(await page.content(), encoding="utf-8")

        try:
            async with ctx.expect_page(timeout=30_000) as popup_info:
                ok = await page.evaluate(
                    """(cnj) => {
                        const links = document.querySelectorAll('a[onclick*="listProcessoCompletoAdvogado"]');
                        let target = null;
                        for (const a of links) {
                            if ((a.getAttribute('onclick') || '').includes(cnj) ||
                                (a.textContent || '').includes(cnj)) { target = a; break; }
                        }
                        if (!target && links.length > 0) target = links[0];
                        if (!target) return 'none';
                        target.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                        return 'dispatched';
                    }""",
                    args.numero,
                )
            print(f"  evaluate -> {ok}")
            popup = await popup_info.value
        except Exception as e:
            print(f"  expect_page falhou: {e}")
            return

        await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
        await popup.wait_for_timeout(8_000)

        safe = args.numero.replace("/", "_")
        out = debug / f"detalhe_{safe}.html"
        out.write_text(await popup.content(), encoding="utf-8")
        png = debug / f"detalhe_{safe}.png"
        try:
            await popup.screenshot(path=str(png), full_page=True)
        except Exception as e:
            print(f"  screenshot falhou: {e}")
        print(f"salvo: {out} ({out.stat().st_size} bytes), url popup: {popup.url}")


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

    args = parser.parse_args()
    coro = {"listar": cmd_listar, "diff": cmd_diff, "detalhe": cmd_detalhe}[args.cmd](args)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
