export const meta = {
  name: 'proximo-passo-cnj',
  description: 'Lê a timeline (movimentos+docs) de cada processo e decide o ESTADO REAL e a PRÓXIMA DILIGÊNCIA para destravar rumo à sentença — com verificação adversarial de arquivado/sentenciado vs despachável',
  phases: [
    { title: 'Analisar', detail: 'inteligência lê timeline + laudo/sentença e decide' },
    { title: 'Verificar', detail: '2º agente refuta despachar_agora / estado' },
  ],
}

// args = [{cnj, classe, timeline_file, sentenca_files:[...], laudo_files:[...]}]
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) { _a = [] } }
const PROCS = Array.isArray(_a) ? _a : []

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['cnj', 'estado_processo', 'classe_beneficio', 'pericia_medica', 'pericia_social',
             'motivo_indeferimento', 'dispensa_social_tema187',
             'pronto_para_sentenca', 'despachar_agora', 'proxima_diligencia', 'texto_peticao',
             'resultado_sentenca', 'resultado_laudo', 'juiz', 'perito', 'fundamento'],
  properties: {
    cnj: { type: 'string' },
    motivo_indeferimento: { type: 'string',
      enum: ['deficiencia', 'renda_miserabilidade', 'ambos', 'outro', 'nao_identificado'] },
    dispensa_social_tema187: { type: 'boolean', description: 'true se indeferimento foi por deficiência (renda incontroversa) => Tema 187/TNU dispensa perícia social' },
    estado_processo: { type: 'string',
      enum: ['ativo_sem_sentenca', 'sentenciado', 'arquivado_extinto', 'em_recurso',
             'cumprimento_sentenca', 'suspenso_sobrestado', 'outro'] },
    classe_beneficio: { type: 'string',
      enum: ['bpc_deficiencia', 'bpc_idoso', 'incapacidade', 'pensao_morte', 'outro', 'indefinido'] },
    pericia_medica: { type: 'string', enum: ['realizada', 'designada_pendente', 'nao_ha', 'dispensada'] },
    pericia_social: { type: 'string', enum: ['realizada', 'designada_pendente', 'nao_ha', 'na'] },
    pronto_para_sentenca: { type: 'boolean', description: 'instrução completa (perícias exigidas feitas) e sem sentença ainda' },
    despachar_agora: { type: 'boolean', description: 'true SOMENTE se ativo, sem sentença, e pronto p/ julgamento (NUNCA se arquivado/sentenciado/em recurso)' },
    proxima_diligencia: { type: 'string', description: 'ação objetiva e específica para o próximo passo (ex.: requerer designação de perícia social; requerer julgamento; nada a fazer - arquivado)' },
    texto_peticao: { type: 'string', description: 'minuta curta do que peticionar; "" se não aplicável' },
    resultado_sentenca: { type: 'string',
      enum: ['procedente', 'parcialmente_procedente', 'improcedente', 'extincao_sem_merito',
             'homologacao', 'sem_sentenca', 'nao_verificado'] },
    resultado_laudo: { type: 'string',
      enum: ['favoravel', 'desfavoravel', 'inconclusivo', 'sem_laudo_judicial', 'nao_verificado'] },
    juiz: { type: 'string' },
    perito: { type: 'string' },
    fundamento: { type: 'string', description: '1-3 frases em cadeia lógica: por que esse é o estado e a próxima diligência' },
  },
}

const VSCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['despachar_agora_correto', 'estado_correto', 'concorda', 'confianca', 'obs'],
  properties: {
    despachar_agora_correto: { type: 'boolean' },
    estado_correto: { type: 'string',
      enum: ['ativo_sem_sentenca', 'sentenciado', 'arquivado_extinto', 'em_recurso',
             'cumprimento_sentenca', 'suspenso_sobrestado', 'outro'] },
    concorda: { type: 'boolean' },
    confianca: { type: 'string', enum: ['alta', 'media', 'baixa'] },
    obs: { type: 'string' },
  },
}

const METODO = `Você é advogado previdenciarista sênior fazendo triagem de acervo no Juizado Especial Federal (PE).
NÃO resuma o processo — decida o ESTADO REAL e a PRÓXIMA DILIGÊNCIA para destravar rumo à SENTENÇA. Pense como quem quer sentença.
MÉTODO (cadeia fechada, premissa→premissa→conclusão):
1) BENEFÍCIO e rito probatório: BPC/LOAS deficiência exige, EM REGRA, DUAS perícias (MÉDICA + SOCIAL). BPC idoso/auxílio-incapacidade/aposentadoria por incapacidade em regra UMA médica. Se indefinido, trate médica+social.
2) ESTADO pela TIMELINE INTEIRA (não só a última linha): procure "arquivado", "baixa definitiva", "extinto", "trânsito em julgado", "sentença", "remetidos à turma recursal", "cumprimento de sentença", "conclusos", perícias designadas/realizadas, laudos juntados, impugnações.
   - Se JÁ arquivado/extinto/baixado ou já sentenciado ou em recurso/cumprimento => despachar_agora=false (não há o que despachar p/ julgamento).
3) Mapeie o estado de CADA perícia exigida.
4) MOTIVO DO INDEFERIMENTO (crítico p/ BPC deficiência): leia a petição inicial e/ou a contestação e/ou a carta/comunicado de indeferimento do INSS para descobrir POR QUE o INSS negou administrativamente:
   - Se negou por NÃO reconhecer a DEFICIÊNCIA (e NÃO impugnou a renda/miserabilidade) => a miserabilidade é INCONTROVERSA e, pelo **Tema 187/TNU**, DISPENSA-SE a perícia SOCIAL. Nesse caso, com a perícia MÉDICA judicial favorável e processo ativo/sem sentença, pronto_para_sentenca=true e despachar_agora=true (dispensa_social_tema187=true).
   - Se negou por RENDA/miserabilidade (ou por ambos) => a social é necessária; não há dispensa.
   Preencha motivo_indeferimento e dispensa_social_tema187.
5) pronto_para_sentenca = instrução completa E sem sentença. "Instrução completa" = perícias EXIGIDAS realizadas com laudo juntado — considerando que a SOCIAL pode ser dispensada pelo Tema 187 (item 4).
6) despachar_agora = true SOMENTE se ativo_sem_sentenca E pronto_para_sentenca.
7) proxima_diligencia: ação mais útil agora. Ex.: "requerer JULGAMENTO invocando Tema 187/TNU (indeferimento foi por deficiência; renda incontroversa; social dispensável) + laudo médico favorável"; "requerer designação da perícia social"; "impugnar laudo em X dias"; "requerer julgamento (conclusos há N dias)"; "nada — arquivado". texto_peticao: minuta curta quando fizer sentido (no caso Tema 187, minutar o requerimento de julgamento com a tese).`

function promptAnalisar(p) {
  const laudos = p.laudo_files || []
  const sents = p.sentenca_files || []
  const ctx = p.contexto_files || []
  return `${METODO}

PROCESSO ${p.cnj} (classe: ${p.classe || 'n/d'}).
PASSO A) Use Read para LER a TIMELINE completa (movimentos + documentos + datas) — base do estado e da próxima diligência:
- ${p.timeline_file}
PASSO B) OBRIGATÓRIO ler o CONTEÚDO dos laudos abaixo (Read; os .pdf são escaneados — leia por IMAGEM/visão). Identifique o laudo do PERITO JUDICIAL (nomeado pelo juízo) e NÃO confunda com laudo/atestado PARTICULAR trazido pela parte (costuma vir como "Documento Comprobatório"). Da conclusão do laudo do perito judicial, preencha resultado_laudo (favoravel = constata incapacidade/deficiência; desfavoravel = não constata) e o nome do perito e CID:
${laudos.map((f) => `- ${f}`).join('\n') || '- (nenhum laudo baixado — use "sem_laudo_judicial")'}
PASSO C) MOTIVO DO INDEFERIMENTO (Tema 187) — LEIA os documentos abaixo (Read). O motivo está no COMUNICADO/CARTA DE DECISÃO (indeferimento) do INSS ou no PROCESSO ADMINISTRATIVO (PA/CEAP), que normalmente vêm juntados na PETIÇÃO INICIAL ou na EMENDA À INICIAL (e o INSS, ao juntar o PA, traz o indeferimento). Procure a "razão do indeferimento"/"motivo": deficiência? renda? ambos? Preencha motivo_indeferimento + dispensa_social_tema187 conforme o MÉTODO item 4:
${ctx.map((f) => `- ${f}`).join('\n') || '- (sem inicial/emenda/PA baixada — infira do que houver na timeline; se não der, motivo_indeferimento="nao_identificado")'}
PASSO D) Se houver sentença, LEIA-A (Read) e preencha resultado_sentenca + juiz do ponto de vista do AUTOR:
${sents.map((f) => `- ${f}`).join('\n') || '- (sem sentença baixada)'}
Só use "nao_verificado" se o arquivo existir mas for ilegível. Responda SOMENTE pela ferramenta estruturada. cnj="${p.cnj}".`
}

function promptVerificar(p, a) {
  return `Verificação adversarial do processo ${p.cnj}. Outro analista decidiu:
estado_processo=${a.estado_processo} | despachar_agora=${a.despachar_agora} | pronto_para_sentenca=${a.pronto_para_sentenca}
proxima_diligencia="${a.proxima_diligencia}"
LEIA você mesmo a timeline (Read: ${p.timeline_file}) e tente REFUTAR. Erro mais grave a evitar: marcar despachar_agora=true num processo JÁ ARQUIVADO/EXTINTO/SENTENCIADO/EM RECURSO. Confirme ou corrija estado e despachar_agora. Na dúvida, despachar_agora_correto=false e confianca="baixa". Responda só pela ferramenta.`
}

log(`Analisando ${PROCS.length} processos (timeline + método próximo-passo, com verificação adversarial)`)

const results = await pipeline(
  PROCS,
  (p) => agent(promptAnalisar(p), { label: `an:${p.cnj}`, phase: 'Analisar', schema: SCHEMA }),
  (a, p) => {
    if (!a) return null
    return agent(promptVerificar(p, a), { label: `vf:${p.cnj}`, phase: 'Verificar', schema: VSCHEMA })
      .then((v) => ({ ...a, verificacao: v || null }))
      .catch(() => ({ ...a, verificacao: null }))
  },
)

return results.filter(Boolean)
