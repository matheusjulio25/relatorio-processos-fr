# CLAUDE.md — relatorio-processos-fr

## IDENTIDADE VISUAL OBRIGATÓRIA EM RELATÓRIOS E DOCUMENTOS

Todo relatório ou documento entregável (`.docx`/`.pdf`) produzido neste projeto **DEVE** seguir a identidade do escritório **Fernandes & Rêgo Advogados Associados**. Nunca entregar relatório sem ela.

- **Logo no cabeçalho:** `relatorios/assets/logo_fr.png` (arquivo oficial, do Google Drive "Fernandes & Rêgo / Logomarca e Timbrado / Arquivo 01 - Logo"). Largura ~5 cm, alinhado à esquerda.
- **Tipografia:**
  - **Títulos/cabeçalhos:** `Palatino Linotype` (serifa — combina com o logo), na **cor da marca `#7F8187`** (cinza-taupe); subtítulos em `#5F6066`.
  - **Corpo:** `Segoe UI`.
- **Rodapé:** `Fernandes & Rêgo Advogados Associados · Documento interno de inteligência jurídica`.
- **Sumário automático** (TOC) em relatórios longos.

### Pipeline de geração (obrigatório)
1. Escrever o conteúdo em Markdown.
2. `pandoc <arquivo>.md -o _base.docx --toc --toc-depth=3 -V lang=pt-BR --metadata title="<título>"`
3. `python3 bin/brandear_docx.py _base.docx "<saída>.docx" relatorios/assets/logo_fr.png`
4. Remover `_base.docx`.

O script `bin/brandear_docx.py` aplica logo + Palatino Linotype/Segoe UI + cor da marca + rodapé. A cor da marca (`#7F8187`) foi amostrada do logo oficial.

> Observação: Palatino Linotype e Segoe UI são fontes do MS Office/Windows; em Macs sem elas, o Word substitui visualmente, mas o padrão fica correto para o ambiente do escritório.
