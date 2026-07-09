#!/usr/bin/env python3
"""Aplica a identidade Fernandes & Rêgo a um .docx COM PÁGINA DE CAPA.
Capa: logo centralizado + título + subtítulo + data + nome do escritório.
Miolo: logo no cabeçalho, títulos em Palatino Linotype (cor da marca), corpo Segoe UI, rodapé.

Uso: python3 bin/brandear_capa.py <in.docx> <out.docx> <logo.png> "<titulo>" "<subtitulo>" "<data>"
"""
import sys
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn

ENTRADA, SAIDA, LOGO = sys.argv[1], sys.argv[2], sys.argv[3]
TITULO   = sys.argv[4] if len(sys.argv) > 4 else "Documento"
SUBTITULO= sys.argv[5] if len(sys.argv) > 5 else ""
DATA     = sys.argv[6] if len(sys.argv) > 6 else ""

MARCA = "7F8187"      # cinza-taupe do logo
MARCA_ESC = "5F6066"  # variação mais escura p/ subtítulos
CORPO = "222222"
SERIF = "Palatino Linotype"
SANS  = "Segoe UI"

doc = Document(ENTRADA)

def set_fonte(style, nome, size=None, cor=None, bold=None):
    style.font.name = nome
    if size is not None: style.font.size = Pt(size)
    if cor is not None:  style.font.color.rgb = RGBColor.from_string(cor)
    if bold is not None: style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), nome)

nomes = {s.name for s in doc.styles}
set_fonte(doc.styles["Normal"], SANS, 11, CORPO)
plano = [("Title", SERIF, 26, MARCA, True), ("Heading 1", SERIF, 18, MARCA, True),
         ("Heading 2", SERIF, 14, MARCA_ESC, True), ("Heading 3", SANS, 12, MARCA_ESC, True),
         ("Heading 4", SANS, 11, MARCA_ESC, True)]
for ne, fonte, sz, cor, bold in plano:
    if ne in nomes:
        set_fonte(doc.styles[ne], fonte, sz, cor, bold)

sec = doc.sections[0]
# Cabeçalho com logo (miolo)
hp = sec.header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
hp.add_run().add_picture(LOGO, width=Cm(5))
# Rodapé
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("Fernandes & Rêgo Advogados Associados  ·  Documento interno de inteligência jurídica")
r.font.name = SANS; r.font.size = Pt(8); r.font.color.rgb = RGBColor.from_string(MARCA)

# ---- Página de capa (construída ao fim e movida para o topo) ----
def novo_par(align=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=6):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    return p

def run(p, texto, nome=SANS, size=12, cor=CORPO, bold=False, italic=False):
    rr = p.add_run(texto)
    rr.font.name = nome; rr.font.size = Pt(size)
    rr.font.color.rgb = RGBColor.from_string(cor)
    rr.font.bold = bold; rr.font.italic = italic
    rpr = rr._element.get_or_add_rPr(); rf = rpr.get_or_add_rFonts()
    for a in ("w:ascii","w:hAnsi","w:cs"): rf.set(qn(a), nome)
    return rr

capa = []
p = novo_par(space_before=90, space_after=18); p.add_run().add_picture(LOGO, width=Cm(7)); capa.append(p)
p = novo_par(space_after=4);  run(p, TITULO, SERIF, 26, MARCA, bold=True); capa.append(p)
if SUBTITULO:
    p = novo_par(space_after=30); run(p, SUBTITULO, SANS, 13, MARCA_ESC); capa.append(p)
# filete
p = novo_par(space_before=6, space_after=30); run(p, "—" * 12, SERIF, 14, MARCA); capa.append(p)
p = novo_par(space_before=120, space_after=2); run(p, "Fernandes & Rêgo Advogados Associados", SERIF, 14, MARCA_ESC, bold=True); capa.append(p)
p = novo_par(space_after=2); run(p, "Inteligência Jurídica — Direito Previdenciário", SANS, 10, MARCA); capa.append(p)
if DATA:
    p = novo_par(space_before=8); run(p, DATA, SANS, 10, MARCA); capa.append(p)
# quebra de página após a capa
p = novo_par(); p.add_run().add_break(WD_BREAK.PAGE); capa.append(p)

# Move os parágrafos da capa para o início do corpo, na ordem
body = doc.element.body
for i, par in enumerate(capa):
    body.insert(i, par._p)

doc.save(SAIDA)
print("OK:", SAIDA)
