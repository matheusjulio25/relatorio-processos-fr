"""Aba Expedientes do Painel do Advogado — prazos em aberto sem abrir processo.

Diferente do Acervo, que só dá o último movimento, aqui vem a data limite para
manifestação de cada expediente, o prazo em dias, quem tomou ciência e quando,
e as tags de prioridade (ex.: "Pessoa com Deficiência", relevante p/ Tema 187).

Estrutura da tela (calibrada em 29/07/2026, pje1g TRF5):

    #tabExpedientes_lbl                                  clica a aba
    formAbaExpediente:listaAgrSitExp:<g>:linhaN1          agrupamento por situação
      (clicar o anchor A4J do grupo cria a árvore abaixo)
    formAbaExpediente:listaAgrSitExp:<g>:trPend           árvore de jurisdições
      ...:trPend:<jur>::jNp                               jurisdição -> CARREGA a lista
      ...:trPend:<jur>:<cx>::j_id186:cxExItem             caixas (subfiltro; vazias
                                                          para pendentes)
    formExpedientes:tbExpedientes:<id_expediente>:...     linhas da lista

Atenção: é a jurisdição (jNp) que carrega a lista, não o cxExItem.

EM ABERTO — paginação: a coleta para na 1ª página de cada jurisdição (49 dos 143
pendentes). O clique em "próxima" é aceito (td.onclick() retorna ok), mas o
conjunto de ids não muda em 30s de polling. Hipóteses já descartadas: estado
acumulado no browser-profile (perfil limpo dá o mesmo 49) e escape do Python nos
trechos JS (IDS_JS e LINHAS_JS são idênticos e o regex casa). Os contadores por
situação (--resumo) não dependem disso e são exatos.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import BrowserContext

from .acervo import ACERVO_PATH
from .login import PJE_BASE_URL

DEBUG_DIR = Path(os.getenv("DEBUG_DIR", "debug"))

CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
CLASSE_CNJ_RE = re.compile(r"\b([A-Z][A-Za-z]{1,9})\s+(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})")
TIPO_ID_RE = re.compile(r"^(?P<tipo>.+?)\s*\((?P<id>\d{4,})\)\s*$")
MEIO_DATA_RE = re.compile(r"^(?P<meio>[^(]+?)\s*\(\s*(?P<data>\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)\s*\)\s*$")
PRAZO_RE = re.compile(r"Prazo:\s*(\d+)\s*dias?", re.I)
CIENCIA_RE = re.compile(r"ci[êe]ncia em\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)", re.I)
LIMITE_RE = re.compile(
    r"Data limite prevista para manifesta[çc][ãa]o:\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)", re.I
)
ULT_MOV_RE = re.compile(
    r"[ÚU]ltimo movimento:\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)\s*-\s*(.+)"
)
BOTOES = {"responder", "tomar ciência", "tomar ciencia", "selecionar"}

# Ids de expediente presentes na tela. A espera compara conjuntos em laço curto
# de evaluate, e não com um wait_for_function longo: o A4J.AJAX.Submit do PJe
# re-renderiza e destrói o contexto de execução, o que derruba a espera longa
# mesmo quando a lista carregou — era isso que travava a paginação em 49/143.
IDS_JS = """() => {
    const ids = new Set();
    for (const el of document.querySelectorAll('[id^="formExpedientes:tbExpedientes:"]')) {
        const m = el.id.match(/^formExpedientes:tbExpedientes:(\\d+):/);
        if (m) ids.add(m[1]);
    }
    return Array.from(ids);
}"""

RESUMO_JS = """() => {
    const out = [];
    for (let i = 0; i < 20; i++) {
        const el = document.getElementById('formAbaExpediente:listaAgrSitExp:' + i + ':linhaN1');
        if (!el) continue;
        const t = (el.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
        out.push({indice: i, rotulo: t[0] || '', total: t[1] || ''});
    }
    return out;
}"""

# O sufixo do anchor do grupo é gerado pelo JSF (j_id178 hoje), então localiza
# pelo onclick em vez de fixar o id.
ANCHOR_GRUPO_JS = """(g) => {
    const pre = 'formAbaExpediente:listaAgrSitExp:' + g + ':';
    for (const a of document.querySelectorAll('a[onclick]')) {
        if (!a.id || !a.id.startsWith(pre)) continue;
        const oc = a.getAttribute('onclick') || '';
        if (oc.includes("A4J.AJAX.Submit('formAbaExpediente'")) return a.id;
    }
    return null;
}"""

EXPANDIR_JS = """(g) => {
    const raiz = document.getElementById('formAbaExpediente:listaAgrSitExp:' + g + ':trPend');
    if (!raiz) return -1;
    let k = 0;
    for (const td of raiz.querySelectorAll('td.rich-tree-node-icon, td[rich\\\\:onexpand]')) {
        const code = td.getAttribute('rich:onexpand');
        if (!code) continue;
        try { new Function('event', code)(null); k++; } catch (e) {}
    }
    return k;
}"""

JURISDICOES_JS = """(g) => {
    const raiz = document.getElementById('formAbaExpediente:listaAgrSitExp:' + g + ':trPend');
    if (!raiz) return [];
    return Array.from(raiz.querySelectorAll('a[id$="::jNp"]')).map(a => {
        const t = (a.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
        return {id: a.id, jurisdicao: t[0] || '', total: t[1] || ''};
    });
}"""

LINHAS_JS = """() => {
    const ids = new Set();
    for (const el of document.querySelectorAll('[id^="formExpedientes:tbExpedientes:"]')) {
        const m = el.id.match(/^formExpedientes:tbExpedientes:(\\d+):/);
        if (m) ids.add(m[1]);
    }
    const out = [];
    for (const id of ids) {
        const alvo = document.querySelector('[id="formExpedientes:tbExpedientes:' + id + ':toolbarDiv"]')
                  || document.querySelector('[id^="formExpedientes:tbExpedientes:' + id + ':"]');
        if (!alvo) continue;
        const tr = alvo.closest('tr');
        if (!tr) continue;
        // Tags de prioridade sao nos de texto SOLTOS no div do link do CNJ (sem
        // elemento proprio), e o pje-clipboard entre eles nao tem texto, entao o
        // innerText cola a tag na linha do CNJ. Por isso lemos do DOM.
        const tags = [];
        const link = tr.querySelector('a[title="Autos Digitais"]');
        if (link && link.parentElement) {
            for (const n of link.parentElement.childNodes) {
                if (n.nodeType === 3) {
                    const t = (n.textContent || '').trim();
                    if (t) tags.push(t);
                }
            }
        }
        out.push({id: id, texto: (tr.innerText || '').trim(), tags: tags});
    }
    return out;
}"""

# Escopado ao datascroller do grid de expedientes: varrer o documento inteiro
# procurando 'page': 'next' pega o paginador de outra aba (o Acervo continua no
# DOM). "dsbld" é como o RichFaces marca o botão desabilitado na última página.
PROXIMA_JS = """() => {
    const sc = document.querySelector('[id$="tbExpedientes:scPendentes_table"]')
            || document.querySelector('[id*="tbExpedientes:scPendentes"]');
    if (!sc) return 'sem-scroller';
    for (const td of sc.querySelectorAll('td[onclick]')) {
        const oc = td.getAttribute('onclick') || '';
        if (!oc.includes("'page': 'next'") && !oc.includes('"page":"next"')) continue;
        const cls = td.className || '';
        if (cls.includes('dsbld') || cls.includes('disabled')) return 'ultima-pagina';
        try { td.onclick(); } catch (e) { return 'err:' + e.message; }
        return 'ok';
    }
    return 'sem-botao';
}"""


@dataclass
class Expediente:
    id: str
    numero: str
    classe: str | None = None
    tipo: str | None = None  # Intimação, Notificação e intimação, Citação...
    meio: str | None = None  # Diário Eletrônico, Sistema...
    criado_em: str | None = None
    prazo_dias: int | None = None
    ciencia_em: str | None = None
    ciencia_texto: str | None = None
    data_limite: str | None = None  # prazo real para manifestação
    destinatario: str | None = None
    partes: str | None = None
    vara: str | None = None
    tags: list[str] = field(default_factory=list)  # Pessoa com Deficiência, etc.
    ultima_movimentacao: str | None = None
    ultima_movimentacao_desc: str | None = None
    jurisdicao: str | None = None
    situacao: str | None = None  # rótulo do agrupamento de origem

    @property
    def com_deficiencia(self) -> bool:
        """Tag de pessoa com deficiência — eixo do Tema 187/TNU."""
        return any("deficiência" in t.lower() or "deficiencia" in t.lower() for t in self.tags)


def _juntar_parenteses(linhas: list[str]) -> list[str]:
    """Reúne "Diário Eletrônico (" + data + ")" numa linha só.

    São spans inline, então o innerText às vezes vem junto e às vezes quebrado —
    normalizar aqui evita que o meio de comunicação e a data de criação se perdam.
    """
    out: list[str] = []
    for l in linhas:
        if out and out[-1].endswith("("):
            out[-1] = f"{out[-1]} {l}"
        elif out and l.startswith(")") and "(" in out[-1]:
            out[-1] = f"{out[-1]} {l}".strip()
        else:
            out.append(l)
    return out


def _parse_linha(id_exp: str, texto: str, tags: list[str] | None = None) -> Expediente | None:
    """Monta o Expediente a partir do innerText da linha.

    A ordem das linhas é estável: destinatário, tipo (id), meio (data), prazo,
    ciência, data limite, classe + CNJ, partes, vara, último movimento.

    As tags de prioridade vêm do DOM (parâmetro `tags`), porque no innerText elas
    colam na linha do CNJ. Sem elas, cai em dois fallbacks: o resto da linha do
    CNJ e, por último, as linhas entre o CNJ e as partes.
    """
    linhas = _juntar_parenteses([l.strip() for l in texto.split("\n") if l.strip()])
    if not linhas:
        return None

    m_cnj = None
    i_cnj = -1
    for i, l in enumerate(linhas):
        m = CLASSE_CNJ_RE.search(l)
        if m:
            m_cnj, i_cnj = m, i
            break
    if not m_cnj:
        m = CNJ_RE.search(texto)
        if not m:
            return None
        exp = Expediente(id=id_exp, numero=m.group(0))
    else:
        exp = Expediente(id=id_exp, numero=m_cnj.group(2), classe=m_cnj.group(1))

    i_partes = -1
    i_tipo = -1
    for i, l in enumerate(linhas):
        if i_tipo < 0:
            mt = TIPO_ID_RE.match(l)
            if mt and not CNJ_RE.search(l):
                exp.tipo = mt.group("tipo").strip()
                i_tipo = i
                continue
        mm = MEIO_DATA_RE.match(l)
        if mm and exp.meio is None and not CNJ_RE.search(l):
            exp.meio = mm.group("meio").strip()
            exp.criado_em = mm.group("data")
            continue
        mp = PRAZO_RE.search(l)
        if mp and exp.prazo_dias is None:
            exp.prazo_dias = int(mp.group(1))
        mc = CIENCIA_RE.search(l)
        if mc and exp.ciencia_em is None:
            exp.ciencia_em = mc.group(1)
            exp.ciencia_texto = l
        ml = LIMITE_RE.search(l)
        if ml and exp.data_limite is None:
            exp.data_limite = ml.group(1)
        mu = ULT_MOV_RE.search(l)
        if mu and exp.ultima_movimentacao is None:
            exp.ultima_movimentacao = mu.group(1)
            exp.ultima_movimentacao_desc = mu.group(2).strip().rstrip(".")
        if " X " in l and i_partes < 0 and i > i_cnj >= 0:
            exp.partes = l
            i_partes = i
        if l.startswith("/") and exp.vara is None:
            exp.vara = l.lstrip("/").strip()

    # destinatário: linha imediatamente antes do "tipo (id)", ignorando botões
    if i_tipo > 0:
        cand = linhas[i_tipo - 1]
        if cand.lower() not in BOTOES and not CNJ_RE.search(cand):
            exp.destinatario = cand

    if tags:
        exp.tags = [t for t in tags if t and t.lower() not in BOTOES]
    elif m_cnj and i_cnj >= 0 and linhas[i_cnj][m_cnj.end():].strip():
        exp.tags = [linhas[i_cnj][m_cnj.end():].strip()]
    elif i_cnj >= 0:
        fim = i_partes if i_partes > i_cnj else i_cnj + 1
        exp.tags = [l for l in linhas[i_cnj + 1:fim] if l.lower() not in BOTOES]

    return exp


async def _esperar_ids(page, antes: set[str], timeout: int = 30_000) -> set[str]:
    """Espera a lista trocar de conteúdo; devolve os ids novos (vazio = não trocou).

    Faz polling curto com evaluate em vez de um wait_for_function longo, porque a
    re-renderização do A4J destrói o contexto e mataria a espera longa. Cada
    evaluate que falha é apenas mais uma tentativa perdida, não o fim da espera.
    """
    passo = 1_500
    restante = timeout
    erros = 0
    primeiro_erro = ""
    visto = ""
    while restante > 0:
        await page.wait_for_timeout(passo)
        restante -= passo
        try:
            ids = set(await page.evaluate(IDS_JS))
        except Exception as e:
            erros += 1
            primeiro_erro = primeiro_erro or str(e)[:110]
            continue
        visto = f"{len(ids)} ids"
        if ids and ids != antes:
            await page.wait_for_timeout(1_000)  # deixa o render terminar
            try:
                ids = set(await page.evaluate(IDS_JS)) or ids
            except Exception:
                pass
            return ids
    # Sem isso não se distingue "a lista veio vazia" de "o evaluate falhou N vezes",
    # e são causas opostas.
    print(f"[expedientes]    espera esgotou: última leitura={visto or 'nenhuma'}, "
          f"evaluate falhou {erros}x{(' — ' + primeiro_erro) if primeiro_erro else ''}, "
          f"antes={len(antes)} ids")
    return set()


async def abrir_aba(page) -> list[dict]:
    """Abre a aba Expedientes e devolve o resumo por situação (rótulo + total)."""
    await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_selector("#tabExpedientes_lbl", timeout=30_000)
    await page.locator("#tabExpedientes_lbl").click()
    await page.wait_for_selector(
        '[id="formAbaExpediente:listaAgrSitExp:0:linhaN1"]', timeout=60_000
    )
    await page.wait_for_timeout(2_500)
    return await page.evaluate(RESUMO_JS)


async def listar_expedientes(
    ctx: BrowserContext, grupo: int = 0, debug: bool = False
) -> tuple[list[Expediente], list[dict]]:
    """Coleta os expedientes de um agrupamento por situação.

    grupo 0 = "Pendentes de ciência ou de resposta" (o que interessa para prazo).
    Devolve (expedientes, resumo_por_situação).
    """
    page = await ctx.new_page()
    try:
        resumo = await abrir_aba(page)
        for r in resumo:
            print(f"[expedientes] [{r['indice']}] {r['rotulo']}: {r['total']}")

        anchor = await page.evaluate(ANCHOR_GRUPO_JS, str(grupo))
        if not anchor:
            print(f"[expedientes] grupo {grupo} não encontrado")
            return [], resumo
        rotulo_grupo = next((r["rotulo"] for r in resumo if r["indice"] == grupo), None)
        print(f"[expedientes] abrindo grupo {grupo}: {rotulo_grupo}")
        await page.evaluate("(id) => document.getElementById(id).onclick()", anchor)
        try:
            await page.wait_for_selector(
                f'[id="formAbaExpediente:listaAgrSitExp:{grupo}:trPend"]', timeout=45_000
            )
        except Exception:
            print("[expedientes] árvore de jurisdições não apareceu")
            return [], resumo
        await page.wait_for_timeout(2_500)

        n = await page.evaluate(EXPANDIR_JS, str(grupo))
        print(f"[expedientes] {n} jurisdição(ões) expandida(s)")
        await page.wait_for_timeout(6_000)

        jurs = await page.evaluate(JURISDICOES_JS, str(grupo))
        print(f"[expedientes] {len(jurs)} jurisdição(ões): "
              + ", ".join(f"{j['jurisdicao']} ({j['total']})" for j in jurs))

        achados: dict[str, Expediente] = {}
        incompletas: list[str] = []
        na_tela: set[str] = set()

        for j in jurs:
            print(f"[expedientes] -> {j['jurisdicao']} (esperado {j['total']})")
            try:
                await page.evaluate("(id) => document.getElementById(id).onclick()", j["id"])
            except Exception as e:
                print(f"[expedientes]    erro clicando: {e}")
                incompletas.append(j["jurisdicao"])
                continue
            # Se a troca não for confirmada, ainda tenta ler o que está na tela:
            # a confirmação falha em alguns carregamentos mesmo com a lista certa
            # presente, e desistir aqui zera a coleta inteira.
            nova = await _esperar_ids(page, na_tela)
            if nova:
                na_tela = nova
            else:
                print("[expedientes]    AVISO: troca não confirmada — lendo a tela mesmo assim")
                incompletas.append(j["jurisdicao"])

            pagina = 1
            while True:
                novos = 0
                for l in await page.evaluate(LINHAS_JS):
                    if l["id"] in achados:
                        continue
                    exp = _parse_linha(l["id"], l["texto"], l.get("tags"))
                    if not exp:
                        continue
                    exp.jurisdicao = j["jurisdicao"]
                    exp.situacao = rotulo_grupo
                    achados[l["id"]] = exp
                    novos += 1
                print(f"[expedientes]    página {pagina}: +{novos} (total {len(achados)})")

                if debug:
                    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    safe = re.sub(r"[^A-Za-z0-9]+", "_", j["jurisdicao"])[:40]
                    (DEBUG_DIR / f"exp_{safe}_p{pagina}.html").write_text(
                        await page.content(), encoding="utf-8"
                    )

                r = await page.evaluate(PROXIMA_JS)
                if r != "ok":
                    if r != "ultima-pagina":
                        print(f"[expedientes]    paginação encerrada: {r}")
                    break
                pagina += 1
                novas = await _esperar_ids(page, na_tela)
                if not novas:
                    print(f"[expedientes]    AVISO: página {pagina} não carregou — parando")
                    incompletas.append(f"{j['jurisdicao']}#p{pagina}")
                    break
                na_tela = novas

        if incompletas:
            print(f"[expedientes] ATENÇÃO: {len(incompletas)} jurisdição(ões)/página(s) sem "
                  f"confirmação — total INCOMPLETO: {', '.join(incompletas)}")

        return list(achados.values()), resumo
    finally:
        await page.close()
