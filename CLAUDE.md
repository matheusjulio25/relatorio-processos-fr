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

---

## COMO O AGENTE NAVEGA NO PJe (coletor_pje) — onde ficam andamentos e arquivos

Pacote `coletor_pje/`. CLI: `python -m coletor_pje.cli <cmd>` (ou wrapper `bin/pje`).
Ambiente Playwright em `.venv` (ative antes: `source .venv/bin/activate`).

### Login (headed; agora AUTOMÁTICO por CPF+senha)
- **Login automático (SSO Keycloak `sso.cloud.pje.jus.br`):** `pje1g_consulta_context` preenche **CPF (`PJE_USUARIO` no `.env`) + senha (Keychain `pje-login-senha`)** no formulário `#username`/`#password` e clica `#kc-login`. Se pedir **2FA**, preenche o **TOTP** (Keychain `pje-totp-secret`, via `pyotp`) — seletores amplos (`#otp`, `input[name*=otp]`, etc.). Segredos: `bin/cofre.sh senha|senha-gui|totp|check` (nunca em texto puro; `.env` limpo e gitignored).
- **Certificado** = fallback (só se faltar credencial): o botão "Certificado digital" abre **diálogo NATIVO** do Chrome → NÃO automatizável por Playwright (era o que travava). Por isso o caminho é **CPF+senha**.
- **SEMPRE `--no-headless`.** O WAF do TRF5 **bloqueia Chrome headless**. Headed passa.
- **2FA "lembra o dispositivo"**: às vezes não é pedido (device confiável); quando pedido, o auto-fill do TOTP resolve; se falhar, os scripts esperam ~4 min p/ digitar manual.

### ✅ CAMINHO CONFIÁVEL para "meus processos": ConsultaProcesso por REPRESENTANTE
Fonte oficial (não o acervo!): **ConsultaProcesso** `/pje/Processo/ConsultaProcesso/listView.seam` (perfil `browser-profile-1g-consulta`, via `varas_1g.pje1g_consulta_context`).
- Pesquisar pelo campo **"Nome do Representante"** = `input[id$=":nomeAdvogado"]` (ex.: "Matheus Julio Lyra Rego") + intervalo de **autuação** (`dataAutuacaoInicioInputDate`/`dataAutuacaoFimInputDate`). Botão `input[id$=":searchProcessos"]`. Isso lista TODOS os processos do advogado no período (ordenados do mais recente ao mais antigo).
- **Paginar** os resultados com `ir_proxima_pagina_1g` (datascroller `rich-datascr`); extrair CNJ+link com `extrair_processos_pagina_1g` (tabela `#fPP:processosTable`).
- **Abrir cada processo**: clicar no link do resultado (`a[onclick*="idProcessoSelecionado"]`) com `ctx.expect_page()`. O popup abre em **janela nova** → **NÃO corrompe a paginação** dos resultados (validado: página 1→2 ok após abrir 20 popups). E abre **direto nos autos** (visão geral, ~36 docs) — sem cair em aba de "juntar petição".
- Ler documentos: `_parse_docs(await popup.content())`. Download: `_baixar_pecas` (fetch na sessão JSF em `/pje/seam/resource/rest/pje-legacy/documento/download/<id>`; usa fallback via timeline quando dá 404). Template provado: `bin/coletar_pecas_cnj.py`.

### ⚠️ NÃO usar o painel do Acervo para abrir em massa (lição aprendida)
- O painel `advogado.seam` (aba Acervo, `acervo.py::listar_acervo`) serve para **listar**, mas **abrir processos por clique inline durante a varredura CORROMPE a paginação** (`A4J.AJAX.Submit` no form da listagem) — numa rodada pegou só **128 de 706**.
- Além disso, o link inline do acervo abre na aba **`tbAnexar`** (juntar petição), sem a lista de documentos; os docs ficam na aba **`autosDigitais`**. (Se algum dia precisar do acervo, troque `aba=` para `autosDigitais`.) **Prefira sempre a ConsultaProcesso acima.**

### Mapa de automação das abas (recon verificado)
Recon de 3 processos em `mapas/recon_pje/` (HTML+txt+screenshot de cada aba) + roadmap em `mapas/recon_pje/ROADMAP.md` (9 domínios, seletores testados contra HTML real). Âncoras estáveis confirmadas (NUNCA ancorar em `j_id*` — variam por processo):
- **Expedientes/prazos (MAIOR valor, fácil):** aba `processoExpedienteTab` → `#processoParteExpedienteMenuGridList:tb`, 4 colunas: `td1`=prazo (`Prazo:\s*(\d+)\s*dias`)+tipo de ato+ciência; `td2`=data-limite fatal (1º `<h6>`); `td4`=Fechado (SIM/NÃO). Dedup por id do documento. `abaListaIntimacaoInss` vem **VAZIA** pro advogado — não usar.
- **Perícias:** aba `marcaPericia` → `#processoPericiaNovaPericiaList:tb`, 5 colunas: data designada / periciado / honorário (`:valorajaxDivMarcarPericia`) / perito+CPF / situação. Laudo: aba `documentos` → `#processoDocumentoGridList:tb`, Tipo `contains "Laudo Pericial"`.
- **Timeline:** `autosDigitais` → `#divTimeLine` `span.texto-movimento` + `span.data-interna` (paginação por scroll, `input#totalPaginas`).
- **Características:** `caracteristicaProcesso` → `#maisDetalhes dl.dl-horizontal` (pares dt/dd por rótulo). **Partes:** `form#navbar #poloAtivo/#poloPassivo` (CPF vem completo mesmo com nome mascarado).
- **Download peça:** `/pje/seam/resource/rest/pje-legacy/documento/download/TRF5/1g/{idProcesso}/{idDocumento}`.
- Audiências e Objeto vieram vazios (JEF documental); nome do juiz não existe no perfil advogado.

### Painel → Expedientes (controle de prazos em massa) — COMO AUTOMATIZAR
A aba **Expedientes** do painel (`advogado.seam`, `#tabExpedientes_lbl`) lista os processos com pendência de TODOS os autos. É uma **árvore RichFaces de 3 níveis**: situação (`formAbaExpediente:listaAgrSitExp:{0..6}:j_id178`) → jurisdição (`...:trPend:N::`) → órgão (`...:trPend:N:XXXX::`). Grupos de situação: 0=pendentes ciência/resposta, 3=ciência Judiciário pend., **4=prazo findou últimos 10 dias (urgente)**, 5=sem prazo, 6=respondidos.
- **PEGADINHA CRÍTICA:** o A4J que carrega os filhos só dispara com **CLIQUE REAL do Playwright** (`locator.click()`) no **link do nó (`...:trPend:N::jNp`)** — clique sintético (`el.click()`/eval do onclick) e clique no `:handle` NÃO funcionam (só toggle visual). Expandir recursivamente todos os nós colapsados (`[id*=":trPend:"][id$=":handle"]` com `:img:collapsed` visível → clicar o `jNp` correspondente).
- Script pronto: `bin/navegar_expedientes.py --grupos todos` → `mapas/expedientes_auto.json` (CNJs por situação). Entrega: `bin/dashboard_expedientes.py`.
- Só extrai NÚMEROS de processo (a lista curta p/ trabalhar manual). Detalhe de cada prazo (data-limite, tipo) sai da aba `processoExpedienteTab` por processo (`bin/checar_prazos.py`).
- **ROTINA DIÁRIA:** `bash bin/rotina_diaria.sh` navega os 3 grupos (0 Pendentes de ciência/resposta, 4 Prazo findou 10d, 6 Respondidos 10d) e gera SÓ as **novidades** (`bin/rotina_expedientes.py`, dedup por chave `CNJ|grupo` em `mapas/expedientes_historico.json`). Contorna o **bug do PJe** (grupo 0 nunca solta os processos): item já visto não repete; evolução real reaparece como chave nova nos grupos 4/6. Semear 1x com `--baseline`. Saída: `Novidades_expedientes_AAAA-MM-DD.xlsx` no Drive. Login manual toda manhã (SSO não auto-loga).
- **Sessão expira ~30 min:** o SSO novo (`sso.cloud.pje.jus.br`) não faz auto-login; rode com login manual (os scripts esperam até 4 min) e mantenha a varredura contínua (ociosidade derruba a sessão).

### Agenda de PERÍCIAS (Pauta de Perícia) — LIMPO, recomendado
Página dedicada **`/pje/PautaPericia/listView.seam`** (form `pautaPericiaAdvogadoGridSearchForm`) — tabela `pautaPericiaAdvogadoGridList` **sem árvore, fácil de raspar**. Filtro de data: campos `...dtMarcacaoInicio` / `...dtMarcacaoFim` (DD/MM/AAAA). Colunas (16, col0 vazia): 1=Processo, 2=Classe, 3=**Especialidade** (Médico/Ortopedista/Psiquiatra), 5=**Data**, 6=**Hora**, 7=**Valor**, 8=**Periciado (o cliente)**, 11=**Situação** (Designada/Ausência...), 13=**Órgão**. (Não há coluna de nome do perito — isso só na aba `marcaPericia` do processo.) Sem paginação visível: filtrar por data janela os resultados.
- Extrator: `bin/extrair_pauta_pericia.py` → `mapas/pauta_pericia.json`. Agenda: `bin/agenda_pericias.py` → Excel + PDF + **`.ics`** (importável no Google Calendar, com alarme 1 dia antes). Há também `/pje/ProcessoAudiencia/PautaAudiencia/listView.seam` (mesma ideia p/ audiências).
- **⚠️ A Pauta só lista perícias FUTURAS/pendentes** — as já ocorridas somem dela; **não dá** para olhar "últimos 90 dias" retroativo pela Pauta. O filtro de data (`dtMarcacao...`, calendário RichFaces) **não aplica de forma confiável** via Playwright, então NÃO se depende dele — busca-se tudo e filtra-se no cliente.

### Perícias × LAUDO (rotina "pra frente") — `bin/rotina_pericias_laudo.py`
Como a Pauta não guarda perícias passadas, o acompanhamento é construído **para a frente**: a cada rodada (a) lê a Pauta e **grava cada perícia** em `mapas/pericias_historico.json` enquanto ainda é futura; (b) para as que a **data já passou** e ainda não têm laudo confirmado, abre o processo (ConsultaProcesso por nº) e verifica se o **laudo** foi juntado — laudo detectado **só pelo TIPO do documento** (`LAUDO_KW`: laudo/estudo social/avaliação social/parecer médico), para não casar menções soltas a "perícia". Laudo apareceu → marca resolvida (não checa mais); sem laudo → entra em **PENDENTES** (cobrar). Só abre processos das perícias ocorridas e não resolvidas (conjunto pequeno/dia) → leve. Saída estável **`Pericias_sem_laudo.xlsx`** no Drive/Automações (backlog atual, com 🆕 do que é novo). `--baseline` semeia sem alertar. **Já integrado** ao `bin/rotina_completa.sh` (etapa 4/4).

### Retrato RETROATIVO (uma vez) — `bin/retrato_pericias_laudo.py`
Para "perícias realizadas de X até hoje × laudo". Limites descobertos: a tela HTML da Pauta e o filtro de situação (`select` `statusDecoration:status`, opção "Realizada") **só retornam perícias FUTURAS** (Realizada devolve 0). O **relatório PDF** ("Gerar PDF" → `/pje/PautaPericia/reportAdv.seam`) traz o histórico completo, MAS depende do **calendário RichFaces** (`dtMarcacao...SearchInputDate`+`...InputCurrentDate`) que **só aceita datas clicadas por humano** — valor por JS/`.fill()`/`.type()` NÃO cola (grid volta 10). Então o retrato é feito **abrindo cada processo**: universo = CNJs de `mapas/pericias_pauta.json` (parse do PDF `reportAdv` via `bin/parse_pauta_pdf.py`, pdfplumber estratégia `lines`, situação normalizada) com data na janela e situação ≠ Cancelada; abre cada um, lê aba de perícia (`processoPericiaNovaPericiaList:tb`, fresca — pega julho) + documentos (laudo por `LAUDO_KW`); classifica pela régua de **15 dias úteis** (`FERIADOS` ajustável; 'Enviado p/ pagamento'/AJG = laudo já entregue; 'Ausência de Parte' = remarcar; multi-perícia = laudos<perícias → verificar). Resumível (`mapas/retrato_pericias.json`). Saída `Retrato_Pericias_Laudo.xlsx` no Drive. `bin/baixar_pauta_pdf.py` baixa o PDF (mas sem filtro de data cola só as futuras). Rodada 27/07/2026: 99 processos, 106 perícias mai→jul, 2 vencidas s/ laudo.

### Sentenças de UMA JANELA DE DATAS (ex.: "última semana") — `bin/sentencas_semana.py`
A ConsultaProcesso **não filtra por data de sentença** (só autuação), então "sentenças prolatadas na semana" sai do **radar do acervo**:
1. `python bin/radar_sentencas.py` — varre o acervo e grava/atualiza `mapas/radar_historico.json` (todo marco visto, com `data_mov` e `desc`).
2. `python3 bin/sentencas_semana.py --data-ini DD/MM/AAAA --data-fim DD/MM/AAAA` — filtra os marcos `SENTENCA` na janela (data tirada do próprio `Publicado Sentença em DD/MM/AAAA`), abre cada CNJ na ConsultaProcesso e baixa a peça → `mapas/sentencas_semana.json` + `pecas_semana/<cnj>/`. Resume-safe.
   - **Falsos positivos filtrados** (`FALSO_POSITIVO`): "Evoluída a classe … para CUMPRIMENTO DE SENTENÇA", baixa definitiva, arquivamento — o regex do radar casa "sentença" nesses movimentos e eles **não são** sentença nova.
   - **Limite conhecido:** o radar lê só o **último** movimento; processo sentenciado e depois movimentado *no mesmo dia da varredura* pode escapar. O histórico das rodadas anteriores cobre os dias já varridos.
   - O download da sentença costuma dar **404** e cair no fallback via timeline → o arquivo vem em **HTML**, não PDF.
3. `python3 bin/espelhar_semana_drive.py --pasta-semana Semana_AAAA-MM-DD_a_MM-DD` — converte HTML→PDF (Chrome `--headless=new --print-to-pdf`) e copia para o Drive em `Automações/Sentencas_abr2025-hoje/`: na **pasta da semana** (por categoria) **e** no **banco acumulado** (categoria na raiz), + `indice.csv`. A classificação vem de `mapas/sentencas_semana_classificado.json` (`{cnj, autor, resultado, resumo}`, mesmas categorias da rubrica).

### Comando `sentencas` (coleta de sentenças)
`python -m coletor_pje.cli --no-headless sentencas [--representante "Nome"] [--data-ini DD/MM/AAAA] [--data-fim ...] [--limit N] [--reprocessar]`
- Pesquisa por representante + autuação, pagina os resultados, clica cada CNJ, baixa docs tipo **"Sentença"** (se houver mais de uma, a mais recente = menor `pos`), extrai texto → `mapas/sentencas_run.json` (+ PDFs em `pecas/<cnj>/`). **Resumível** (pula CNJs já em `ja_feitos`).
- Classificação (procedente/parcial/improcedente/extinção sem mérito, art. 485 CPC): `mapas/RUBRICA_CLASSIFICACAO.md` + `bin/preparar_lotes_classificacao.py` → subagentes → `bin/merge_classificacao.py` → `bin/espelhar_sentencas_drive.py` (espelha no Google Drive).

---

## LAUDOS E PERÍCIAS — o que quebra no PJe (aprendido em 03/09/2026)

Três descobertas que mudaram a triagem de acervo. Sem elas, a classificação de laudo erra.

### 1. A aba de perícias é obrigatória — a timeline não mostra perícia designada
A timeline (`autosDigitais`) **não registra** que existe perícia marcada. Quem só lê a timeline conclui
"não há perícia" num processo que já tem perícia designada, realizada, ou onde o cliente **faltou**.
Numa amostra de 160 processos, **53 tinham perícia que a timeline escondia**.

Aba `marcaPericia` → `#processoPericiaNovaPericiaList:tb`. Script: `bin/ler_aba_pericia.py`.
O clique que abre a aba procura qualquer elemento com texto "perícia" **e** handler de clique.

Situações e o que significam: `Ausência de Parte` = cliente faltou (emergência) · `Designada` futura =
antifalta D-3/D-1 · `Designada`/`Pendente` passada = cobrar laudo (**régua de 15 dias úteis** — não
cobrar perícia recente) · `Realizada`/`Enviado para pagamento` = **laudo entregue** (o AJG só paga contra
laudo) · aba vazia = requerer designação.

### 2. O download de documento devolve o visualizador, não o PDF
`/documento/download/<id>` responde HTML do PDF.js, e o `innerText` do iframe traz **só a página 1**.

Solução — pegar os bytes pela API do PDF.js (`bin/baixar_laudo_pdf.py`, `bin/baixar_laudo_amplo.py`):
```js
const app = window.PDFViewerApplication;
await app.pdfLoadingTask.promise;
const data = await app.pdfDocument.getData();   // Uint8Array do PDF real
```
Salvar como `.pdf` e rodar `pdftotext -layout`. Aí a camada de texto vem completa.

### 3. O laudo está no id VIZINHO — o primeiro documento é a capa
O perito junta uma capa (`Laudo Pericial`, sem descrição) e o **laudo em anexo** (`Laudo Pericial` com o
nome do periciado), em ids consecutivos. Baixar só o primeiro traz o **diploma do perito**.
**Baixe o documento de laudo e os 2 seguintes.**

Documentos que se disfarçam de laudo: PA do INSS (`Meu INSS`, `gov.br/meuinss`), Anexo III da Portaria em
branco (`INSTRUMENTO UNIFICADO DE AVALIAÇÃO`), diploma do perito (`CONCLUSÃO DE CURSO`, `CARGA HORÁRIA`),
peça nossa (`OAB/PE`, `Pede deferimento`), ofício de honorários do AJG (`OFÍCIO REQUISITÓRIO`).

**Âncora para achar o certo:** o nome do perito, que vem da aba de perícias. `bin/achar_laudo_certo.py`
pontua os candidatos e dá +20 ao PDF que contém esse nome.

### 4. O acervo do painel não lista tudo
12 processos que sumiram da varredura do acervo estavam **todos vivos** — subseção **8312**, que o painel
não lista. Processo que some do acervo **não** é processo encerrado: verifique por CNJ com
`bin/verificar_estado_cnj.py --lista`.

### Pipeline de laudos (ordem que funciona)
```bash
python bin/dump_acervo.py                                   # acervo completo
python bin/verificar_estado_cnj.py --lista <vivos> --shard 0/2
python bin/ler_aba_pericia.py     --lista <sem-laudo> --shard 0/2
python bin/baixar_laudo_amplo.py  --lista <com-laudo> --shard 0/2
python bin/achar_laudo_certo.py && python bin/ler_pdf_laudo.py && python bin/classificar_pdf_laudo.py
python bin/kpi_exito_0309.py && python bin/planilha_providencias.py && python bin/planilha_tres_filas.py
python bin/gerar_artifact_exito.py
```
Máquina de 8 GB: **máximo 2 shards**. ~10 s/processo na timeline, ~30 s/processo no download de laudos.
