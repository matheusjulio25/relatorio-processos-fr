"""MCP server expondo as ferramentas do coletor PJe pro Claude Desktop.

Setup no Mac (1 vez):
  Edite ~/Library/Application Support/Claude/claude_desktop_config.json:
  {
    "mcpServers": {
      "pje-trf5": {
        "command": "/CAMINHO/ATE/relatorio-processos-fr/.venv/bin/python",
        "args": ["-m", "coletor_pje.mcp_server"],
        "cwd": "/CAMINHO/ATE/relatorio-processos-fr"
      }
    }
  }

  Reinicie o Claude Desktop. Depois converse:
    "Liste meus processos no PJe"
    "Gere o relatorio diario"
    "Baixe as 3 ultimas pecas do processo 0000740-91.2026.4.05.8205"
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .acervo import listar_acervo
from .cli import _abrir_detalhe, _baixar_pecas, _e_relevante, _parse_docs
from .login import pje_context
from .manifest import Manifest, diff_acervo

mcp = FastMCP("pje-trf5")


@mcp.tool()
async def listar_processos(headless: bool = True) -> str:
    """Lista todos os processos ativos no PJe TRF5 (Caixa de entrada de cada vara).
    Retorna CNJ + data ultima movimentacao + vara + partes.
    """
    async with pje_context(headless=headless) as ctx:
        processos = [p async for p in listar_acervo(ctx)]
    linhas = [f"{p.numero}\t{p.ultima_movimentacao or '-'}\t{p.vara or '-'}\t{(p.titulo or '')[:80]}"
              for p in processos]
    return f"Total: {len(processos)}\n\n" + "\n".join(linhas)


@mcp.tool()
async def gerar_relatorio(limit: int = 0, headless: bool = True) -> str:
    """Gera o relatorio diario: compara acervo atual com manifests, identifica processos
    com movimentacao nova, abre o detalhe de cada um, extrai a peca mais recente
    (decisao/intimacao/peticao) e devolve o conteudo formatado em Markdown.

    Args:
        limit: maximo de novidades a processar (0 = todas).
        headless: se True roda Chrome sem janela visivel.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rel_dir = Path("relatorios")
    rel_dir.mkdir(parents=True, exist_ok=True)

    async with pje_context(headless=headless) as ctx:
        processos = [p async for p in listar_acervo(ctx)]
        pendentes = diff_acervo(processos)
        if limit:
            pendentes = pendentes[:limit]

        linhas = [f"# Relatório PJe — {hoje}", "",
                  f"**Acervo total:** {len(processos)} | **Novidades hoje:** {len(pendentes)}", ""]

        for p in pendentes:
            linhas.append(f"## {p.numero}")
            if p.titulo: linhas.append(f"**Partes:** {p.titulo}  ")
            if p.vara: linhas.append(f"**Vara:** {p.vara}  ")
            linhas.append(f"**Movimentação:** {p.ultima_movimentacao} — {p.ultima_movimentacao_desc or '-'}  ")
            try:
                popup = await _abrir_detalhe(ctx, p.numero)
                html = await popup.content()
                docs = _parse_docs(html)
                rels = sorted(
                    [d for d in docs if _e_relevante(d["tipo"])],
                    key=lambda d: (d["desc"].startswith("A "), d["pos"]),
                )[:1]
                if rels:
                    out_d = Path("pecas") / p.numero.replace("/", "_")
                    out_d.mkdir(parents=True, exist_ok=True)
                    res = await _baixar_pecas(popup, rels, out_d)
                    if res and res[0]["texto"]:
                        linhas.append(f"**Peça {res[0]['tipo']}** ({res[0]['id']}):")
                        linhas.append("> " + res[0]["texto"][:1500].replace("\n", "\n> "))
                await popup.close()
            except Exception as e:
                linhas.append(f"_(erro: {e})_")
            linhas.append("")

        # persiste manifests
        now = datetime.now().isoformat(timespec="seconds")
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

    md = "\n".join(linhas)
    (rel_dir / f"relatorio-{hoje}.md").write_text(md, encoding="utf-8")
    return md


@mcp.tool()
async def baixar_pecas(cnj: str, n: int = 3, headless: bool = True) -> str:
    """Baixa as N pecas mais recentes (decisao/intimacao/peticao) do processo CNJ.
    Salva em pecas/<CNJ>/ e devolve o texto resumido.
    """
    if not Manifest.load(cnj):
        return f"sem manifest para {cnj}; rode 'gerar_relatorio' antes pra criar."
    out_dir = Path("pecas") / cnj.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    async with pje_context(headless=headless) as ctx:
        popup = await _abrir_detalhe(ctx, cnj)
        html = await popup.content()
        docs = _parse_docs(html)
        rels = sorted(
            [d for d in docs if _e_relevante(d["tipo"])],
            key=lambda d: (d["desc"].startswith("A "), d["pos"]),
        )[:n]
        res = await _baixar_pecas(popup, rels, out_dir)
    saida = [f"Baixadas {len(res)} pecas em pecas/{cnj.replace('/', '_')}/:"]
    for r in res:
        saida.append(f"\n## {r['tipo']} ({r['id']})")
        if r["texto"]:
            saida.append(r["texto"][:2000])
        else:
            saida.append(f"_(binario {r['ext']}, {r['size']}B — sem texto extraivel)_")
    return "\n".join(saida)


if __name__ == "__main__":
    mcp.run()
