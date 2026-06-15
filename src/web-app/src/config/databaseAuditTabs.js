export const DATABASE_AUDIT_SUBTABS = [
  { id: 'Anàlisi obsolets', helpKey: 'deepScan' },
  { id: "Repositori d'obsolets", helpKey: 'obsoletsRepository' },
  { id: 'Auditoria de canvis', helpKey: 'postCrqAudit' },
  { id: 'Automatitzacions', helpKey: 'automationOverview' },
  { id: 'Tasques i regles', helpKey: 'automationRules' },
  { id: 'Gestió de controls', helpKey: 'checksAdmin' },
  { id: 'Configuració del servidor', helpKey: 'mailConfig' },
  { id: 'Guia i Ajuda', helpKey: 'tutorial' },
];

export const DATABASE_AUDIT_HELP_KEYS = Object.fromEntries(
  DATABASE_AUDIT_SUBTABS.map((tab) => [tab.id, tab.helpKey])
);

export const DATABASE_AUDIT_SUBTABS_HIDE_PROFILE_SELECTOR = [
  'Anàlisi obsolets',
  'Auditoria de canvis',
  'Automatitzacions',
  'Tasques i regles',
  'Gestió de controls',
  'Configuració del servidor',
];

export const DATABASE_AUDIT_SUBTABS_HIDE_GLOBAL_REPORT = [
  'Automatitzacions',
  'Tasques i regles',
  'Gestió de controls',
  'Configuració del servidor',
];
