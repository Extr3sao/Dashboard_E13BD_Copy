import {
  DEFAULT_TIME_FILTER,
  DELIVERY_AUDIENCE_LABELS,
  DELIVERY_RESULT_LABELS,
  LOT_STATE_LABELS,
  RUN_STATUS_LABELS,
  SCHEMA_NAME_PATTERN,
  TEMPLATE_KEY_DESCRIPTIONS,
  TEMPLATE_KEY_LABELS,
} from '../config/automationViewConfig.js';
import {
  DEFAULT_POST_CRQ_CRITICALITY_OVERRIDES,
  DEFAULT_POST_CRQ_SCHEDULER_OPTIONS,
  DEFAULT_POST_CRQ_TIME_FILTER,
} from '../config/appShellConfig.js';

let schemaLotRowSequence = 0;
let uiRowSequence = 0;
export const DEFAULT_TEST_RECIPIENT = 'franciscovalladares@gencat.cat';
const POST_CRQ_ALLOWED_CRITICALITIES = new Set(['CRITIC', 'MITJA', 'BAIX']);

export function defaultStartAt() {
  const value = new Date(Date.now() + 60 * 60 * 1000);
  const iso = new Date(value.getTime() - (value.getTimezoneOffset() * 60000)).toISOString();
  return iso.slice(0, 16);
}

export function currentMonthValue() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export function splitCsv(value) {
  if (!value) return [];
  // Split using regex for commas, semicolons or spaces
  return String(value).split(/[\s,;]+/).map((item) => item.trim()).filter((item) => item.length > 0 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(item) || item.length > 0);
}

export function downloadBlob(response, filename) {
  const blob = new Blob([response.data], { type: response.headers['content-type'] || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function resolveRequestErrorMessage(error, fallbackMessage) {
  const directDetail = error?.response?.data?.detail;
  if (typeof directDetail === 'string' && directDetail.trim()) {
    return directDetail.trim();
  }

  const responseData = error?.response?.data;
  if (responseData instanceof Blob) {
    try {
      const rawText = await responseData.text();
      if (rawText) {
        try {
          const parsed = JSON.parse(rawText);
          if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
            return parsed.detail.trim();
          }
        } catch {
          if (rawText.trim()) {
            return rawText.trim();
          }
        }
      }
    } catch {
      // Ignore blob parsing failures and fall through to generic messages.
    }
  }

  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message.trim();
  }

  return fallbackMessage;
}

export function defaultDistributionConfig() {
  return {
    lot_scope_mode: 'all',
    selected_lots: [], // Nou camp format llista d'objectes {code, emails: [{email, enabled}]}
    send_only_with_findings: true,
    send_without_findings: false,
    record_without_findings: true,
    email_subject: '[Oracle Audit] {job_name} - {lot}',
    email_body: 'Bon dia\n\nS\'ha executat correctament l\'auditoria autom\u00e0tica del lot {lot}.\n\nResum de l\'execuci\u00f3\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d\'execuci\u00f3: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda t\u00e8cnica\n{technical_legend}\n\nTrobar\u00e0s el detall complet a l\'informe adjunt.\n\nSalutacions,\nSistema d\'auditoria BBDD',
    include_summary: true,
    include_lot_reports: true,
    delivery_targets: ['lots', 'tic'],
    delivery_override_recipients: DEFAULT_TEST_RECIPIENT,
  };
}

export function normalizePostCrqSchedulerOptions(
  options,
  defaults = DEFAULT_POST_CRQ_SCHEDULER_OPTIONS,
) {
  const source = options || {};
  const normalized = { ...defaults };
  [
    'max_concurrency',
    'max_concurrency_upper_bound',
    'max_heavy_concurrency',
    'max_medium_concurrency',
    'max_light_concurrency',
    'max_retries',
  ].forEach((key) => {
    const rawValue = source[key];
    if (rawValue === undefined || rawValue === null || rawValue === '') {
      return;
    }
    const numericValue = Number(rawValue);
    if (Number.isFinite(numericValue)) {
      normalized[key] = numericValue;
    }
  });
  if (source.enable_auto_throttle !== undefined) {
    normalized.enable_auto_throttle = !!source.enable_auto_throttle;
  }
  return normalized;
}

export function normalizePostCrqCriticalityOverrides(overrides) {
  return Object.fromEntries(
    Object.entries(overrides || {})
      .map(([checkId, value]) => [String(checkId || '').trim().toUpperCase(), String(value || '').trim().toUpperCase()])
      .filter(([checkId, value]) => checkId && POST_CRQ_ALLOWED_CRITICALITIES.has(value)),
  );
}

export function derivePostCrqExecutionConfigFromReport(reportData, fallback = {}) {
  const snapshotMetadata = reportData?.snapshot_metadata || {};
  const reportModel = reportData?.report_model || {};
  const executionParameters = reportModel.execution_parameters || {};
  const enabledChecks = reportModel.enabled_checks || [];
  const executedChecks = reportData?.executed_checks || [];
  const resultsByCheck = reportData?.results_by_check || [];
  const selectedChecksCandidates = [
    snapshotMetadata.selected_checks,
    enabledChecks.map((item) => item.check_id).filter(Boolean),
    executedChecks.map((item) => item.check_id).filter(Boolean),
    resultsByCheck.map((item) => item.check_id).filter(Boolean),
  ];
  const selectedChecks = selectedChecksCandidates.find((items) => Array.isArray(items) && items.length > 0) || [];
  const timeWindow = executionParameters.time_window || {};

  let timeFilter = snapshotMetadata.time_filter || reportData?.context?.time_filter;
  if ((!timeFilter || Object.keys(timeFilter).length === 0) && (timeWindow.start_at || timeWindow.end_at)) {
    timeFilter = {
      mode: 'range',
      start_date: timeWindow.start_at || '',
      end_date: timeWindow.end_at || '',
    };
  }

  return {
    profile: fallback.profile || reportData?.context?.profile || executionParameters.profile || '',
    schemas: Array.isArray(fallback.schemas) ? fallback.schemas : (reportData?.context?.schemas || []),
    selected_checks: Array.from(new Set((selectedChecks || []).map((item) => String(item || '').trim()).filter(Boolean))),
    time_filter: { ...DEFAULT_POST_CRQ_TIME_FILTER, ...(timeFilter || {}) },
    criticality_overrides: normalizePostCrqCriticalityOverrides(
      snapshotMetadata.criticality_overrides || reportData?.criticality_overrides || DEFAULT_POST_CRQ_CRITICALITY_OVERRIDES,
    ),
    scheduler_options: normalizePostCrqSchedulerOptions(
      snapshotMetadata.scheduler_options || reportData?.context?.scheduler || DEFAULT_POST_CRQ_SCHEDULER_OPTIONS,
    ),
    report_data: reportData || null,
    generated_at: snapshotMetadata.generated_at || executionParameters.generated_at || '',
    source_file: snapshotMetadata.source_file || reportData?.context?.source_file || '',
    final_criticality_by_check: snapshotMetadata.final_criticality_by_check || {},
  };
}

function makeUiRowId(prefix) {
  return `${prefix}-${uiRowSequence++}`;
}

export function withRowIds(items, rowType) {
  return (items || []).map((item) => ({
    ...item,
    _row_id: item._row_id || makeUiRowId(rowType),
  }));
}

export function stripUiRowIds(items) {
  return (items || []).map(({ _row_id, ...item }) => item);
}

export function emptyMasterLot() {
  return { _row_id: makeUiRowId('master-lot'), code: '', label: '', description: '', enabled: true };
}

export function emptySchemaLot() {
  return { _row_id: `schema-lot-${schemaLotRowSequence++}`, schema_name: '', lot_name: '' };
}

export function emptyRoute() {
  return { _row_id: makeUiRowId('route'), lot_code: '', audience: 'provider', label: '', emails_text: '', enabled: true };
}

export function emptyTemplate() {
  return { _row_id: makeUiRowId('template'), template_key: '', audience: 'provider', subject_template: '', body_template: '', enabled: true };
}

export function withSchemaLotRowIds(items) {
  return (items || []).map((item) => ({
    ...item,
    _row_id: item._row_id || `schema-lot-${schemaLotRowSequence++}`,
  }));
}

function downloadText(content, filename, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function exportSchemaLotsCsv(items) {
  const rows = [
    ['schema_name', 'lot_name'],
    ...(items || []).map((item) => [item.schema_name || '', item.lot_name || '']),
  ];
  const csv = rows.map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n');
  downloadText(csv, 'schema_lots_mapping.csv', 'text/csv;charset=utf-8');
}

export function getSchemaLotValidation(items) {
  const duplicateSchemas = new Set();
  const emptySchemaIndexes = new Set();
  const invalidSchemaIndexes = new Set();
  const firstSeenBySchema = new Map();

  (items || []).forEach((item, index) => {
    const schemaName = String(item.schema_name || '').trim().toUpperCase();
    if (!schemaName) {
      emptySchemaIndexes.add(index);
      return;
    }
    if (!SCHEMA_NAME_PATTERN.test(schemaName)) {
      invalidSchemaIndexes.add(index);
    }
    if (firstSeenBySchema.has(schemaName)) {
      duplicateSchemas.add(schemaName);
      duplicateSchemas.add(firstSeenBySchema.get(schemaName));
      return;
    }
    firstSeenBySchema.set(schemaName, schemaName);
  });

  return {
    emptySchemaIndexes,
    invalidSchemaIndexes,
    duplicateSchemas,
    hasErrors: emptySchemaIndexes.size > 0 || invalidSchemaIndexes.size > 0 || duplicateSchemas.size > 0,
  };
}

export function buildPayload(form) {
  const isDistribution = form.audit_type === 'post_crq_distribution';
  const selectedDeliveryOptions = Array.from(new Set(
    (Array.isArray(form.delivery_targets) ? form.delivery_targets : [])
      .map((item) => String(item || '').trim().toLowerCase())
      .filter((item) => ['lots', 'tic', 'proves'].includes(item)),
  ));
  const deliveryTargets = selectedDeliveryOptions.filter((item) => ['lots', 'tic'].includes(item));
  const testMode = selectedDeliveryOptions.includes('proves');

  return {
    name: form.name.trim(),
    enabled: !!form.enabled,
    audit_type: form.audit_type,
    profile: form.profile,
    schemas: splitCsv(form.schemas_text).map((item) => item.toUpperCase()),
    checks: ['post_crq', 'post_crq_distribution'].includes(form.audit_type) ? form.selected_checks : [],
    time_filter: ['post_crq', 'post_crq_distribution'].includes(form.audit_type) ? form.time_filter : {},
    criticality_overrides: {},
    scheduler_options: ['post_crq', 'post_crq_distribution'].includes(form.audit_type)
      ? normalizePostCrqSchedulerOptions(form.scheduler_options)
      : {},
    report_format: isDistribution ? 'pdf' : form.report_format,
    schedule_type: form.schedule_type,
    schedule_config: { start_at: form.start_at },
    timeout_seconds: Number(form.timeout_seconds || 300),
    delivery_targets: isDistribution ? [] : [{ type: 'email', enabled: !!form.email_enabled, config: { recipients: splitCsv(form.email_recipients) } }],
    severity_rules: [],
    job_config: isDistribution ? {
      lot_scope: { 
        mode: form.lot_scope_mode, 
        selected_lots: (form.selected_lots || []).map(lot => ({
          code: lot.code.toUpperCase(),
          emails: (lot.emails || []).map(e => ({
            email: e.email.trim(),
            enabled: !!e.enabled
          })).filter(e => e.email.length > 0)
        }))
      },
      send_policy: {
        send_only_with_findings: true,
        send_without_findings: !!form.send_without_findings,
        record_without_findings: true,
      },
      email_template: { subject: form.email_subject, body: form.email_body },
      report_options: { include_summary: !!form.include_summary, include_lot_reports: !!form.include_lot_reports },
      delivery: {
        targets: deliveryTargets,
        test_mode: testMode,
        override_recipients: testMode ? splitCsv(form.delivery_override_recipients) : [],
      },
    } : {},
  };
}

export function emptyForm(profile) {
  return {
    name: '',
    enabled: true,
    audit_type: 'post_crq',
    profile: profile || '',
    schemas_text: '',
    selected_checks: [],
    time_filter: { ...DEFAULT_TIME_FILTER },
    scheduler_options: { ...DEFAULT_POST_CRQ_SCHEDULER_OPTIONS },
    criticality_overrides: {},
    report_format: 'markdown',
    schedule_type: 'weekly',
    start_at: defaultStartAt(),
    timeout_seconds: 300,
    email_enabled: true,
    email_recipients: '',
    ...defaultDistributionConfig(),
  };
}

export function formFromJob(job) {
  const email = (job.delivery_targets || []).find((item) => item.type === 'email') || {};
  const distribution = job.job_config || {};
  const lotScope = distribution.lot_scope || {};
  const sendPolicy = distribution.send_policy || {};
  const emailTemplate = distribution.email_template || {};
  const reportOptions = distribution.report_options || {};
  const delivery = distribution.delivery || {};

  // Normalitzem selected_lots per al formulari (sempre llista d'objectes)
  let selectedLotsForm = [];
  if (Array.isArray(lotScope.selected_lots)) {
    selectedLotsForm = lotScope.selected_lots.map(item => {
      if (typeof item === 'string') {
        return { code: item, emails: [] };
      }
      return {
        code: item.code || '',
        emails: (item.emails || []).map(e => ({
          email: e.email || '',
          enabled: e.enabled !== false
        }))
      };
    });
  }

  const hasExplicitTargets = Array.isArray(delivery.targets);
  let deliveryTargets = hasExplicitTargets
    ? delivery.targets.map((item) => String(item || '').trim().toLowerCase()).filter((item) => ['lots', 'tic'].includes(item))
    : [];

  if (!hasExplicitTargets) {
    if (distribution.send_to_lots !== false) deliveryTargets.push('lots');
    if (distribution.send_to_tic !== false) deliveryTargets.push('tic');
  }

  if (delivery.test_mode === true) {
    deliveryTargets.push('proves');
  }
  deliveryTargets = Array.from(new Set(deliveryTargets));

  return {
    name: job.name || '',
    enabled: !!job.enabled,
    audit_type: job.audit_type || 'post_crq',
    profile: job.profile || '',
    schemas_text: (job.schemas || []).join(', '),
    selected_checks: job.checks || [],
    time_filter: { ...DEFAULT_TIME_FILTER, ...(job.time_filter || {}) },
    scheduler_options: normalizePostCrqSchedulerOptions(job.scheduler_options || distribution.scheduler_options || {}),
    criticality_overrides: {},
    report_format: job.report_format || 'markdown',
    schedule_type: job.schedule_type || 'weekly',
    start_at: (job.schedule_config || {}).start_at ? String(job.schedule_config.start_at).slice(0, 16) : defaultStartAt(),
    timeout_seconds: Number(job.timeout_seconds || 300),
    email_enabled: !!email.enabled,
    email_recipients: ((email.config || {}).recipients || []).join(', '),
    ...defaultDistributionConfig(),
    lot_scope_mode: lotScope.mode || 'all',
    selected_lots: selectedLotsForm,
    send_only_with_findings: sendPolicy.send_only_with_findings !== false,
    send_without_findings: sendPolicy.send_without_findings === true,
    record_without_findings: sendPolicy.record_without_findings !== false,
    email_subject: emailTemplate.subject || defaultDistributionConfig().email_subject,
    email_body: emailTemplate.body || defaultDistributionConfig().email_body,
    include_summary: reportOptions.include_summary !== false,
    include_lot_reports: reportOptions.include_lot_reports !== false,
    delivery_targets: deliveryTargets,
    delivery_override_recipients: ((delivery.override_recipients || []).join(', ')) || DEFAULT_TEST_RECIPIENT,
  };
}

export function runStatusClass(status) {
  if (status === 'success') return 'border-green-500/20 bg-green-500/15 text-green-300';
  if (status === 'partial_error') return 'border-yellow-500/20 bg-yellow-500/15 text-yellow-200';
  if (status === 'error') return 'border-red-500/20 bg-red-500/15 text-red-300';
  return 'border-white/10 bg-white/10 text-foreground';
}

export function lotStatusClass(status) {
  if (status === 'CON_HALLAZGOS') return 'border-red-500/20 bg-red-500/15 text-red-200';
  if (status === 'SIN_HALLAZGOS') return 'border-green-500/20 bg-green-500/15 text-green-200';
  if (status === 'NO_APLICA') return 'border-slate-500/20 bg-slate-500/15 text-slate-200';
  if (status === 'ERROR_CONSULTA') return 'border-amber-500/20 bg-amber-500/15 text-amber-200';
  if (status === 'SIN_MAPEO') return 'border-fuchsia-500/20 bg-fuchsia-500/15 text-fuchsia-200';
  return 'border-white/10 bg-white/10 text-foreground';
}

export function runStatusLabel(status) {
  return RUN_STATUS_LABELS[status] || status || '-';
}

export function lotStatusLabel(status) {
  return LOT_STATE_LABELS[status] || status || '-';
}

export function deliveryAudienceLabel(audience) {
  return DELIVERY_AUDIENCE_LABELS[audience] || audience || '-';
}

export function deliveryResultLabel(result) {
  return DELIVERY_RESULT_LABELS[result] || result || '-';
}

export function runLotSummary(summary) {
  const lotSummary = summary?.lot_execution;
  if (!lotSummary) return '-';
  return `Amb troballes ${lotSummary.with_findings || 0} | Sense troballes ${lotSummary.without_findings || 0} | Revisió ${(lotSummary.query_errors || 0) + (lotSummary.unmapped || 0)}`;
}

export function yesNo(value) {
  return value ? 'Sí' : 'No';
}

export function buildAutomationHelpUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set('automation-help', '1');
  return url.toString();
}

export function templateKeyLabel(templateKey) {
  return TEMPLATE_KEY_LABELS[templateKey] || templateKey || 'Plantilla personalitzada';
}

export function templateKeyDescription(templateKey) {
  return TEMPLATE_KEY_DESCRIPTIONS[templateKey] || 'Clau interna compatible amb el backend actual.';
}
