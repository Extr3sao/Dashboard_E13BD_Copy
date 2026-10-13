export const DATABASE_AUDIT_SUBTABS = [
  { id: 'Quadre operatiu', helpKey: 'fleetDashboard' },
  { id: 'Anàlisi obsolets', helpKey: 'deepScan' },
  { id: "Repositori d'obsolets", helpKey: 'obsoletsRepository' },
  { id: 'Auditoria de canvis', helpKey: 'postCrqAudit' },
  { id: 'Diagnòstics Oracle', helpKey: 'oracleDiagnostics' },
  { id: 'Problemes', helpKey: 'findings' },
  { id: 'Alertes i informes', helpKey: 'alertingReports' },
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
  'Diagnòstics Oracle',
  'Problemes',
  'Alertes i informes',
  'Automatitzacions',
  'Tasques i regles',
  'Gestió de controls',
  'Configuració del servidor',
];

export const DATABASE_AUDIT_SUBTABS_HIDE_GLOBAL_REPORT = [
  'Diagnòstics Oracle',
  'Problemes',
  'Alertes i informes',
  'Automatitzacions',
  'Tasques i regles',
  'Gestió de controls',
  'Configuració del servidor',
];
