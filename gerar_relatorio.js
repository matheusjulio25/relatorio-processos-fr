// Gerador de Relatório Diário .docx — Fernandes & Rego Advogados
// Uso: node gerar_relatorio.js <caminho_json> <caminho_output.docx>

const fs   = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, TabStopType,
  TabStopPosition,
} = require("docx");

// ─── Argumentos ──────────────────────────────────────────────────────────────
const [,, jsonPath, outputPath] = process.argv;
if (!jsonPath || !outputPath) {
  console.error("Uso: node gerar_relatorio.js <json> <output.docx>");
  process.exit(1);
}

const dados = JSON.parse(fs.readFileSync(jsonPath, "utf8"));

// ─── Cores ────────────────────────────────────────────────────────────────────
const COR_PRIMARIA    = "1B3A6B"; // azul escuro F&R
const COR_ALTA        = "C0392B"; // vermelho
const COR_MEDIA       = "D4800A"; // laranja/amarelo
const COR_BAIXA       = "1E7E34"; // verde
const COR_HEADER_BG   = "1B3A6B";
const COR_LINHA_PAR   = "EBF0FA";
const COR_LINHA_IMPAR = "FFFFFF";

// ─── Utilitários ─────────────────────────────────────────────────────────────
const borda = (cor = "CCCCCC") => ({
  style: BorderStyle.SINGLE, size: 1, color: cor,
});
const bordas = (cor) => ({
  top: borda(cor), bottom: borda(cor), left: borda(cor), right: borda(cor),
});

function corUrgencia(u) {
  if (u === "ALTA")  return COR_ALTA;
  if (u === "MEDIA") return COR_MEDIA;
  return COR_BAIXA;
}

function textoUrgencia(u) {
  if (u === "ALTA")  return "ALTA";
  if (u === "MEDIA") return "MÉDIA";
  return "BAIXA";
}

// ─── Cabeçalho do documento ──────────────────────────────────────────────────
function makeHeader() {
  return new Header({
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: "Fernandes & Rego Advogados Associados",
            bold: true, size: 20, font: "Arial", color: COR_PRIMARIA,
          }),
          new TextRun("\t"),
          new TextRun({
            text: `Relatório Diário — ${dados.data}`,
            size: 18, font: "Arial", color: "555555",
          }),
        ],
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        border: { bottom: { style: BorderStyle.SINGLE, size: 4,
                            color: COR_PRIMARIA, space: 4 } },
      }),
    ],
  });
}

// ─── Rodapé ───────────────────────────────────────────────────────────────────
function makeFooter() {
  return new Footer({
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: "Documento gerado automaticamente. Uso interno do escritório.",
            size: 16, font: "Arial", color: "888888",
          }),
          new TextRun("\t"),
          new TextRun({ children: ["Pág. ", PageNumber.CURRENT, " / ", PageNumber.TOTAL_PAGES],
                        size: 16, font: "Arial", color: "888888" }),
        ],
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
      }),
    ],
  });
}

// ─── Cards de resumo (Alta / Média / Baixa) ──────────────────────────────────
function makeCardRow() {
  function card(label, count, cor) {
    return new TableCell({
      width: { size: 3120, type: WidthType.DXA },
      borders: bordas(cor),
      shading: { fill: cor, type: ShadingType.CLEAR },
      margins: { top: 160, bottom: 160, left: 240, right: 240 },
      verticalAlign: VerticalAlign.CENTER,
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: String(count), bold: true,
                                   size: 52, font: "Arial", color: "FFFFFF" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: label, size: 20,
                                   font: "Arial", color: "FFFFFF" })],
        }),
      ],
    });
  }

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3120, 3120, 3120],
    rows: [
      new TableRow({ children: [
        card("🔴  Urgência Alta",  dados.alta,  COR_ALTA),
        card("🟡  Urgência Média", dados.media, COR_MEDIA),
        card("🟢  Urgência Baixa", dados.baixa, COR_BAIXA),
      ]}),
    ],
  });
}

// ─── Tabela de notificações ──────────────────────────────────────────────────
function makeHeaderRow() {
  const cols = ["Origem", "Processo", "Urgência", "Prazo", "Movimentação"];
  const widths = [900, 2100, 1000, 1200, 4160];
  return new TableRow({
    tableHeader: true,
    children: cols.map((c, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: COR_HEADER_BG, type: ShadingType.CLEAR },
        borders: bordas(COR_HEADER_BG),
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: c, bold: true, size: 18,
                                   font: "Arial", color: "FFFFFF" })],
        })],
      })
    ),
  });
}

function makeDataRow(n, idx) {
  const bg = idx % 2 === 0 ? COR_LINHA_PAR : COR_LINHA_IMPAR;
  const corUrg = corUrgencia(n.urgencia);
  const widths = [900, 2100, 1000, 1200, 4160];

  const celulas = [
    // Origem
    new TableCell({
      width: { size: widths[0], type: WidthType.DXA },
      borders: bordas("DDDDDD"),
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: n.origem, size: 16, font: "Arial",
          bold: true, color: n.origem === "INSS" ? "1B3A6B" : "555555" })],
      })],
    }),
    // Processo
    new TableCell({
      width: { size: widths[1], type: WidthType.DXA },
      borders: bordas("DDDDDD"),
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: n.processo, size: 16, font: "Courier New" })],
      })],
    }),
    // Urgência
    new TableCell({
      width: { size: widths[2], type: WidthType.DXA },
      borders: bordas("DDDDDD"),
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: textoUrgencia(n.urgencia),
          bold: true, size: 16, font: "Arial", color: corUrg })],
      })],
    }),
    // Prazo
    new TableCell({
      width: { size: widths[3], type: WidthType.DXA },
      borders: bordas("DDDDDD"),
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: n.prazo, size: 16, font: "Arial",
          color: n.prazo !== "—" ? COR_ALTA : "888888" })],
      })],
    }),
    // Movimentação (assunto truncado)
    new TableCell({
      width: { size: widths[4], type: WidthType.DXA },
      borders: bordas("DDDDDD"),
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: n.assunto.substring(0, 120),
                                 size: 16, font: "Arial" })],
      })],
    }),
  ];

  return new TableRow({ children: celulas });
}

function makeTabelaNotificacoes(lista) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [900, 2100, 1000, 1200, 4160],
    rows: [
      makeHeaderRow(),
      ...lista.map((n, i) => makeDataRow(n, i)),
    ],
  });
}

// ─── Seção por urgência ───────────────────────────────────────────────────────
function secaoUrgencia(titulo, cor, lista) {
  if (!lista.length) return [];
  return [
    new Paragraph({ spacing: { before: 360, after: 120 } }),
    new Paragraph({
      children: [new TextRun({ text: titulo, bold: true, size: 26,
                               font: "Arial", color: cor })],
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: cor, space: 2 } },
    }),
    new Paragraph({ spacing: { before: 80, after: 80 } }),
    makeTabelaNotificacoes(lista),
  ];
}

// ─── Monta o documento ────────────────────────────────────────────────────────
async function gerarDocumento() {
  const alta  = dados.notificacoes.filter(n => n.urgencia === "ALTA");
  const media = dados.notificacoes.filter(n => n.urgencia === "MEDIA");
  const baixa = dados.notificacoes.filter(n => n.urgencia === "BAIXA");

  const children = [
    // Título principal
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: "RELATÓRIO DIÁRIO DE PROCESSOS",
                               bold: true, size: 36, font: "Arial",
                               color: COR_PRIMARIA })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 40 },
      children: [new TextRun({ text: dados.data, size: 24,
                               font: "Arial", color: "555555" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 360 },
      children: [new TextRun({ text: `${dados.total} notificações recebidas`,
                               size: 20, font: "Arial", color: "888888" })],
    }),

    // Cards de resumo
    makeCardRow(),

    // Seções por urgência
    ...secaoUrgencia("🔴  Urgência Alta — Ação Imediata Necessária",   COR_ALTA,  alta),
    ...secaoUrgencia("🟡  Urgência Média — Acompanhar",                COR_MEDIA, media),
    ...secaoUrgencia("🟢  Urgência Baixa — Informativo",               COR_BAIXA, baixa),

    new Paragraph({ spacing: { before: 480 } }),
  ];

  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: "Arial", size: 22 } },
      },
    },
    sections: [{
      properties: {
        page: {
          size: { width: 16838, height: 11906 }, // A4 paisagem
          margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 },
        },
      },
      headers: { default: makeHeader() },
      footers: { default: makeFooter() },
      children,
    }],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`Relatório gerado: ${outputPath}`);
}

gerarDocumento().catch(e => { console.error(e); process.exit(1); });
