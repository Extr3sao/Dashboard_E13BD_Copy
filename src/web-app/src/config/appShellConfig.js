import { DATABASE_AUDIT_HELP_KEYS } from './databaseAuditTabs.js';

export const API_BASE = '/api';

export const DEFAULT_SCORING_CONFIG = {
  dmlNoActivityPts: 25,
  dependenciesMaxPts: 30,
  inboundPenaltyPerDep: 10,
  outboundPenaltyPerDep: 2,
  loginInactivePts: 10,
  loginInactiveDays: 180,
  sizeTinyThresholdGb: 0.05,
  sizeTinyPts: 20,
  sizeSmallThresholdGb: 1,
  sizeSmallPts: 10,
  automationBonusPts: 15,
  automationPenaltyPerBlocker: 10,
  automationPenaltyCap: 40,
};

export const DEFAULT_POST_CRQ_TIME_FILTER = {
  mode: 'preset',
  preset: 'weekly',
  start_date: '',
  end_date: '',
};

export const DEFAULT_POST_CRQ_SCHEDULER_OPTIONS = {
  max_concurrency: 2,
  max_concurrency_upper_bound: 4,
  max_heavy_concurrency: 1,
  max_medium_concurrency: 1,
  max_light_concurrency: 2,
  max_retries: 1,
  enable_auto_throttle: true,
};

export const DEFAULT_POST_CRQ_CRITICALITY_OVERRIDES = {};

export function resolvePageHelpKey(activeTab, databaseAuditSubtab) {
  if (activeTab === 'Auditoria BBDD') {
    return DATABASE_AUDIT_HELP_KEYS[databaseAuditSubtab] || 'databaseAuditOverview';
  }

  if (activeTab === 'Arquitectura') {
    return 'architecture';
  }

  return null;
}
