export const DEFAULT_TIME_FILTER = { mode: 'preset', preset: 'weekly', start_date: '', end_date: '' };
export const LOT_STATES = ['CON_HALLAZGOS', 'SIN_HALLAZGOS', 'NO_APLICA', 'ERROR_CONSULTA', 'SIN_MAPEO'];
export const DELIVERY_AUDIENCES = ['provider', 'none'];
export const DELIVERY_RESULTS = ['sent', 'retry_pending', 'delivery_error', 'no_route', 'attachment_error', 'skipped_no_findings', 'skipped_not_applicable', 'manual_review'];
export const SCHEMA_NAME_PATTERN = /^[A-Z][A-Z0-9_$#]*$/;

export const LOT_STATE_LABELS = {
  CON_HALLAZGOS: 'Amb troballes',
  SIN_HALLAZGOS: 'Sense troballes',
  NO_APLICA: 'No aplica',
  ERROR_CONSULTA: 'Error de consulta',
  SIN_MAPEO: 'Sense mapatge',
};

export const DELIVERY_AUDIENCE_LABELS = {
  provider: 'Lot',
  tic: 'TIC',
  retry: 'Reintent',
  none: 'Sense enviament',
};

export const DELIVERY_RESULT_LABELS = {
  sent: 'Enviat',
  retry_pending: 'Reintent pendent',
  delivery_error: "Error d'enviament",
  no_route: 'Sense ruta',
  attachment_error: "Error d'adjunt",
  skipped_no_findings: 'Omes sense troballes',
  skipped_not_applicable: 'Omes: no aplica',
  manual_review: 'Revisi\u00f3 manual',
};

export const RUN_STATUS_LABELS = {
  success: 'Correcte',
  partial_error: 'Parcial amb errors',
  error: 'Error',
  running: 'En execuci\u00f3',
  pending: 'Pendent',
};

export const SECTION_IDS = [
  'job_form',
  'context',
  'jobs',
  'schema_map',
  'backfill',
  'master_lots',
  'lot_routes',
  'templates',
  'audit',
  'history',
  'retry',
];

export const AUTOMATION_SCREENS = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    title: 'Dashboard anal\u00edtic',
    description: "Consulta l'hist\u00f2ric mensual per lot, esquema i tipus de check, i exporta'l a PDF.",
    helpKey: 'automationDashboard',
    sections: [],
  },
  {
    id: 'jobs',
    label: 'Jobs',
    title: "Jobs d'automatitzaci\u00f3",
    description: "Configura l'execuci\u00f3, el context de distribuci\u00f3 i el parc de jobs actius.",
    helpKey: 'automationJobs',
    sections: ['job_form', 'context', 'jobs'],
  },
  {
    id: 'lots',
    label: 'Lots i mapatge',
    title: 'Lots i mapatge',
    description: 'Relaciona schemas, prepara el backfill i mant\u00e9n el cat\u00e0leg mestre de lots.',
    helpKey: 'automationLots',
    sections: ['schema_map', 'backfill', 'master_lots'],
  },
  {
    id: 'recipients',
    label: 'Destinataris',
    title: 'Destinataris i rutes',
    description: 'Revisa les rutes TIC i gestiona els correus per lot sense sortir del m\u00f2dul.',
    helpKey: 'automationRecipients',
    sections: ['lot_routes'],
  },
  {
    id: 'templates',
    label: 'Plantilles',
    title: 'Plantilles per audi\u00e8ncia',
    description: "Edita el missatge funcional per lot, resum TIC, reenviament manual i av\u00eds d'error de generaci\u00f3.",
    helpKey: 'automationTemplates',
    sections: ['templates'],
  },
  {
    id: 'history',
    label: 'Hist\u00f2ric',
    title: 'Hist\u00f2ric i auditoria',
    description: 'Consulta execucions, filtres per lot i la tra\u00e7abilitat funcional dels canvis.',
    helpKey: 'automationHistory',
    sections: ['audit', 'history'],
  },
  {
    id: 'retries',
    label: 'Reintents',
    title: 'Cua de reintents',
    description: "Gestiona els enviaments pendents o fallits sense repetir tota l'auditoria.",
    helpKey: 'automationRetries',
    sections: ['retry'],
  },
  {
    id: 'help',
    label: 'Ajuda',
    title: "Guia d'Automatitzacions",
    description: 'Ent\u00e9n el flux complet del m\u00f2dul i quan cal tocar cada pantalla.',
    helpKey: 'automationHelp',
    sections: [],
  },
];

export const TEMPLATE_KEY_LABELS = {
  job_generation_failure: "Error de generaci\u00f3 de l'informe",
  provider_with_findings: 'Lot amb troballes',
  provider_without_findings: 'Lot sense troballes',
  tic_summary: 'Resum TIC',
  manual_resend: 'Reenviament manual',
};

export const TEMPLATE_KEY_DESCRIPTIONS = {
  job_generation_failure: "Av\u00eds enviat quan l'auditoria falla i no es distribueix cap informe.",
  provider_with_findings: 'Correu principal que rep el lot quan hi ha troballes.',
  provider_without_findings: "Correu opcional per informar que el lot s'ha avaluat sense troballes.",
  tic_summary: "Resum global enviat a l'\u00c0rea TIC amb el resultat complet.",
  manual_resend: 'Plantilla utilitzada quan es llan\u00e7a un reenviament des de la cua.',
};

export function buildDefaultSectionState() {
  return Object.fromEntries(SECTION_IDS.map((id) => [id, true]));
}
