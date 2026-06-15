export function hasMandatoryQueryErrors(item) {
  return (item?.executed_queries || []).some(
    (query) => !query.optional && (query.status === 'error' || query.status === 'skipped')
  );
}

export function asNum(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

export function calculateCustomScoring(item, scoringConfig) {
  if (!item) return { raw: 0, final: 0, breakdown: [] };

  const summary = item.summary || {};
  const inbound = asNum(summary.INBOUND_REFERENCES, 0);
  const outbound = asNum(summary.EXTERNAL_DEPENDENCIES_OUT, 0);
  const dmlMods = asNum(summary.TABLES_WITH_MODS_30D, 0);
  const statsRecent = asNum(summary.TABLES_STATS_RECENT_30D, 0);
  const loginDays = asNum(summary.LAST_LOGIN_DAYS, 999);
  const sizeGb = asNum(summary.SIZE_GB, 0);
  const activeJobs = asNum(summary.ACTIVE_JOBS, 0);
  const triggers = asNum(summary.ENABLED_TRIGGERS, 0);
  const apexApps = asNum(summary.APEX_APPLICATIONS, 0);
  const codeRefsCount = (item.code_refs || []).length;

  let score = 0;
  const breakdown = [];

  if (dmlMods === 0 && statsRecent === 0) {
    score += scoringConfig.dmlNoActivityPts;
    breakdown.push({ factor: 'Activitat DML', pts: scoringConfig.dmlNoActivityPts, desc: 'Sense modificacions ni estadístiques recents' });
  } else {
    breakdown.push({ factor: 'Activitat DML', pts: 0, desc: 'Activitat recent detectada' });
  }

  const depPenaltyRaw = inbound * scoringConfig.inboundPenaltyPerDep + outbound * scoringConfig.outboundPenaltyPerDep;
  const depPenalty = Math.min(scoringConfig.dependenciesMaxPts, Math.floor(depPenaltyRaw));
  const depPts = Math.max(0, scoringConfig.dependenciesMaxPts - depPenalty);
  score += depPts;
  breakdown.push({ factor: 'Dependències', pts: depPts, desc: `Entrants=${Math.trunc(inbound)}, sortints=${Math.trunc(outbound)}` });

  if (loginDays > scoringConfig.loginInactiveDays) {
    score += scoringConfig.loginInactivePts;
    breakdown.push({ factor: 'Login', pts: scoringConfig.loginInactivePts, desc: `Inactiu >${scoringConfig.loginInactiveDays} dies` });
  } else {
    breakdown.push({ factor: 'Login', pts: 0, desc: 'Login recent' });
  }

  if (sizeGb < scoringConfig.sizeTinyThresholdGb) {
    score += scoringConfig.sizeTinyPts;
    breakdown.push({ factor: 'Mida', pts: scoringConfig.sizeTinyPts, desc: `<${(scoringConfig.sizeTinyThresholdGb * 1024).toFixed(0)}MB` });
  } else if (sizeGb < scoringConfig.sizeSmallThresholdGb) {
    score += scoringConfig.sizeSmallPts;
    breakdown.push({ factor: 'Mida', pts: scoringConfig.sizeSmallPts, desc: `<${scoringConfig.sizeSmallThresholdGb}GB` });
  } else {
    breakdown.push({ factor: 'Mida', pts: 0, desc: 'Mida significativa' });
  }

  let blockers = 0;
  if (activeJobs > 0) blockers += 1;
  if (triggers > 0) blockers += 1;
  if (apexApps > 0) blockers += 1;
  if (codeRefsCount > 0) blockers += 1;

  if (blockers === 0) {
    score += scoringConfig.automationBonusPts;
    breakdown.push({ factor: 'Automatismes/Codi', pts: scoringConfig.automationBonusPts, desc: 'Sense jobs/triggers/APEX/code refs' });
  } else {
    const penalty = Math.min(scoringConfig.automationPenaltyCap, blockers * scoringConfig.automationPenaltyPerBlocker);
    score -= penalty;
    breakdown.push({ factor: 'Automatismes/Codi', pts: -penalty, desc: 'Hi ha bloquejadors operatius' });
  }

  const raw = Math.round(score);
  const final = Math.max(0, Math.min(100, raw));
  return { raw, final, breakdown };
}

export function getEffectiveScore(item, scoringConfig) {
  if (hasMandatoryQueryErrors(item)) return 0;
  return calculateCustomScoring(item, scoringConfig).final;
}

export function getEffectiveBreakdown(item, scoringConfig) {
  return hasMandatoryQueryErrors(item)
    ? [{ factor: 'Qualitat de dades', pts: 0, desc: 'Consultes obligatòries amb error. Score invalidat.' }]
    : calculateCustomScoring(item, scoringConfig).breakdown;
}

export const signalByScore = (score) => (score >= 70 ? 'green' : score >= 40 ? 'yellow' : 'red');
export const signalByBlockerCount = (count) => (asNum(count, 0) > 0 ? 'red' : 'green');
export const signalByOutgoing = (count) => (asNum(count, 0) > 0 ? 'yellow' : 'green');
export const signalByDaysSinceDDL = (days) => {
  const num = asNum(days, 999);
  if (num <= 30) return 'red';
  if (num <= 180) return 'yellow';
  return 'green';
};
export const signalByRecentCount = (count) => (asNum(count, 0) > 0 ? 'red' : 'green');
export const signalByLoginDays = (days) => {
  const num = asNum(days, 999);
  if (num <= 90) return 'red';
  if (num <= 180) return 'yellow';
  return 'green';
};
export const signalCardClass = (signal) => (
  signal === 'green'
    ? 'bg-green-500/10 border-green-500/30'
    : signal === 'yellow'
      ? 'bg-yellow-500/10 border-yellow-500/30'
      : 'bg-red-500/10 border-red-500/30'
);
export const signalDotClass = (signal) => (
  signal === 'green'
    ? 'bg-green-400'
    : signal === 'yellow'
      ? 'bg-yellow-400'
      : 'bg-red-400'
);

const QUERY_OBJECTIVES = {
  Q01_SUMMARY_360: 'Resum integral de risc i activitat',
  Q02_SIZE: "Mida de segments de l'esquema",
  Q03_USER_ACCOUNT: 'Estat del compte i dates clau',
  Q04_ACTIVITY_CLASS: "Classificació d'activitat recent",
  Q05_OBJECTS_BY_TYPE: "Inventari d'objectes per tipus",
  Q06_RECENT_DDL: 'Canvis DDL recents',
  Q07_TABLE_STATS: "Recència d'estadístiques de taules",
  Q08_DEPS_INCOMING: 'Dependències entrants',
  Q09_DEPS_OUTGOING: 'Dependències sortints',
  Q10_SYNONYMS: 'Sinònims vinculats',
  Q11_GRANTS_GIVEN: 'Permisos atorgats',
  Q12_GRANTS_RECEIVED: 'Permisos rebuts',
  Q13_SYS_PRIVS: 'Privilegis de sistema',
  Q14_CODE_REFS_SOURCE: 'Referències de codi (source)',
  Q14_CODE_REFS_VIEWS: 'Referències de codi (views)',
  Q14_CODE_REFS_TRIGGERS: 'Referències de codi (triggers)',
  Q15_JOBS: 'Jobs scheduler',
  Q16_TRIGGERS_ENABLED: 'Triggers habilitats',
  Q17_APEX_APPS: 'Aplicacions APEX',
  Q18_DB_LINKS: 'DB links',
  Q19_INVALID_OBJECTS: 'Objectes invàlids',
};

export function getQueryObjective(queryId) {
  return QUERY_OBJECTIVES[queryId] || "Consulta d'auditoria";
}

export function getQueryReason(query) {
  if (query?.error) return String(query.error).slice(0, 120);
  if (query?.status === 'ok') return `Nº de files: ${query?.rows ?? 0}`;
  if (query?.status === 'optional_error') return 'Consulta opcional no disponible en aquest entorn';
  if (query?.status === 'skipped') return 'Saltada per manca de connexió/configuració';
  return '-';
}
