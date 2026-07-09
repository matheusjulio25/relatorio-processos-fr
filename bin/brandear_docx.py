#!/usr/bin/env python3
"""Aplica a identidade do escritório Fernandes & Rêgo a um .docx:
logo no cabeçalho, títulos em Playfair Display (cor da marca), corpo em Lato,
rodapé com o nome do escritório. Uso: python3 bin/brandear_docx.py <in.docx> <out.docx> <logo.png>"""
import sys
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

ENTRADA, SAIDA, LOGO = sys.argv[1], sys.argv[2], sys.argv[3]
MARCA = "7F8187"      # cinza-taupe do logo
MARCA_ESC = "5F6066"  # variação mais escura p/ subtítulos
CORPO = "222222"
SERIF = "Palatino Linotype"  # títulos/serifa — identidade do escritório
SANS = "Segoe UI"            # corpo

doc = Document(ENTRADA)

def set_fonte(style, nome, size=None, cor=None, bold=None):
    style.font.name = nome
    if size is not None:
        style.font.size = Pt(size)
    if cor is not None:
        style.font.color.rgb = RGBColor.from_string(cor)
    if bold is not None:
        style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), nome)

nomes = {s.name for s in doc.styles}
set_fonte(doc.styles["Normal"], SANS, 11, CORPO)
plano = [("Title", SERIF, 26, MARCA, True), ("Heading 1", SERIF, 18, MARCA, True),
         ("Heading 2", SERIF, 14, MARCA_ESC, True), ("Heading 3", SANS, 12, MARCA_ESC, True),
         ("Heading 4", SANS, 11, MARCA_ESC, True)]
for nome_estilo, fonte, sz, cor, bold in plano:
    if nome_estilo in nomes:
        set_fonte(doc.styles[nome_estilo], fonte, sz, cor, bold)

sec = doc.sections[0]
# Logo no cabeçalho (esquerda)
hp = sec.header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
hp.add_run().add_picture(LOGO, width=Cm(5))
# Rodapé com nome do escritório
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("Fernandes & Rêgo Advogados Associados  ·  Documento interno de inteligência jurídica")
r.font.name = SANS
r.font.size = Pt(8)
r.font.color.rgb = RGBColor.from_string(MARCA)

doc.save(SAIDA)
print("OK:", SAIDA)
