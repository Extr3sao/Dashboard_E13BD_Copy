import React from 'react';
import { Activity, AlertTriangle, ChevronDown, Database, LoaderCircle, RefreshCcw, Search } from 'lucide-react';
import { getFindings } from '../api/findings.js';
import { getOracleDiagnosticHistory, runOracleDiagnostics } from '../api/oracleDiagnostics.js';

const PAGE_SIZE = 50;
const panel = 'oracle-panel rounded-xl border p-4';
const when = (value) => value ? new Date(Number(value) * 1000).toLocaleString('ca-ES') : '—';
const number = (value, unit = '') => value === null || value === undefined || !Number.isFinite(Number(value)) ? 'Desconegut' : `${Number(value).toLocaleString('ca-ES')}${unit}`;

const categoryNames = {
  SESSION: 'Sessions', BLOCKING: 'Bloquejos', SQL_PERFORMANCE: 'Rendiment SQL', PLAN: 'Plans d’execució',
  STATISTICS: 'Estadístiques', SEGMENT_GROWTH: 'Creixement d’objectes', CAPACITY: 'Emmagatzematge',
};
const categoryGroups = {
  SESSION: 'sessions', BLOCKING: 'bloquejos', SQL_PERFORMANCE: 'rendiment', PLAN: 'rendiment',
  SEGMENT_GROWTH: 'emmagatzematge', CAPACITY: 'emmagatzematge', STATISTICS: 'estadistiques',
};
const groups = [
  ['sessions', 'Sessions'], ['bloquejos', 'Bloquejos'], ['rendiment', 'Rendiment'],
  ['emmagatzematge', 'Emmagatzematge'], ['estadistiques', 'Estadístiques'],
];
const categoryRule = {
  SESSION: 'ORACLE_SESSIONS', BLOCKING: 'ORACLE_BLOCKING', SQL_PERFORMANCE: 'ORACLE_SQL_PERFORMANCE',
  PLAN: 'ORACLE_PLAN_CHANGES', STATISTICS: 'ORACLE_OBJECT_STATISTICS', SEGMENT_GROWTH: 'ORACLE_SEGMENT_GROWTH',
  CAPACITY: 'ORACLE_CAPACITY',
};
const ruleNames = {
  ORACLE_SESSIONS: 'Sessions Oracle', ORACLE_BLOCKING: 'Bloquejos Oracle', ORACLE_SQL_PERFORMANCE: 'Rendiment SQL Oracle',
  ORACLE_PLAN_CHANGES: 'Canvis de pla Oracle', ORACLE_PLAN_DETAILS: 'Detall del pla Oracle',
  ORACLE_OBJECT_STATISTICS: 'Estadístiques dels objectes', ORACLE_CAPACITY: 'Capacitat assignada',
  ORACLE_CAPACITY_MAX: 'Capacitat màxima efectiva', ORACLE_TEMP_CAPACITY: 'Capacitat temporal',
  ORACLE_SEGMENT_GROWTH: 'Creixement de segments', ORACLE_RAC_SCOPE: 'Visibilitat RAC', ORACLE_CONTAINER_SCOPE: 'Visibilitat CDB/PDB',
};
const thresholdNames = {
  long_session_seconds: 'Durada d’una sessió llarga (s)', blocking_warning_seconds: 'Avís de bloqueig (s)',
  blocking_critical_seconds: 'Bloqueig crític (s)', blocking_critical_sessions: 'Sessions per considerar crític un bloqueig',
  sql_elapsed_warning_seconds: 'Avís de temps SQL (s)', sql_elapsed_critical_seconds: 'Temps SQL crític (s)',
  sql_regression_percent: 'Regressió SQL (%)', segment_growth_warning_percent: 'Avís de creixement de segment (%)',
  segment_growth_warning_bytes: 'Avís de creixement de segment (bytes)', segment_growth_critical_percent: 'Creixement crític de segment (%)',
  segment_growth_critical_bytes: 'Creixement crític de segment (bytes)', tablespace_warning_percent: 'Avís d’ocupació (%)',
  tablespace_critical_percent: 'Ocupació crítica (%)', min_sql_executions: 'Execucions SQL mínimes', query_timeout_ms: 'Límit de consulta (ms)',
};
const statusNames = {
  SUCCESS: 'Correcte', PARTIAL: 'Parcial', ERROR: 'Error', SKIPPED: 'Omesa', UNKNOWN: 'Desconegut',
  PASS: 'Correcte', WARN: 'Avís', FAIL: 'Incidència', AVAILABLE: 'Disponible', RUNNING: 'En execució',
  FAILED: 'Error', COMPLETED: 'Finalitzat', RECONCILED: 'Conciliat', FULL: 'Completa', DEGRADED: 'Parcial',
  NOT_LICENSED: 'Sense llicència declarada', INSUFFICIENT_PRIVILEGES: 'Permisos insuficients',
  UNSUPPORTED_VERSION: 'Versió no compatible', UNAVAILABLE: 'No disponible', EVALUATED: 'Avaluada',
  NOT_EVALUATED: 'No avaluada', EVALUATION_ERROR: 'Error d’avaluació', NEW: 'Nova', OPEN: 'Oberta',
  WORSENING: 'Empitjora', IMPROVING: 'Millora', STABLE: 'Estable', CRITICAL: 'Crítica', CRITIC: 'Crítica',
  MEDIUM: 'Mitjana', MITJA: 'Mitjana', HIGH: 'Alta', ALT: 'Alta', LOW: 'Baixa', BAIXA: 'Baixa', INFO: 'Informativa',
  NOT_REQUIRED: 'No requerit', NOT_APPLICABLE: 'No aplicable',
  PERMANENT: 'Permanent', TEMPORARY: 'Temporal', APPLICATION: 'Aplicació',
  HIGHER_IS_WORSE: 'Un valor més alt indica més risc', NONE: 'Sense comparació',
  DATAFILES_OR_CAPACITY_VALUES_UNAVAILABLE: 'No es poden consultar els fitxers o les dades de capacitat necessàries.',
  TEMPFILE_CAPACITY_UNAVAILABLE: 'No es pot consultar la capacitat dels fitxers temporals.',
  UNKNOWN_NOT_EXPOSED_BY_CURRENT_ORACLE_DICTIONARY_PROBES: 'Capacitat física desconeguda: no s’exposa a les vistes Oracle consultades.',
  NO_PRIOR_SNAPSHOT: 'No hi ha cap mostra anterior', NO_PRIOR_OR_MULTIPLE_PLAN_VARIANTS: 'No hi ha prou mostres comparables o hi ha diversos plans',
  NOT_COMPARABLE_COUNTER_RESET_OR_NO_NEW_EXECUTIONS: 'No comparable: el comptador s’ha reiniciat o no hi ha execucions noves',
};
const fieldNames = {
  tablespace: 'Espai de taules', contents: 'Tipus', allocated_bytes: 'Espai assignat (bytes)',
  used_bytes: 'Espai ocupat (bytes)', free_bytes: 'Espai lliure actual (bytes)', max_bytes: 'Capacitat màxima efectiva (bytes)',
  used_percent: 'Ocupació de l’espai assignat (%)', assigned_space_used_percent: 'Ocupació de l’espai assignat (%)',
  max_capacity_percent: 'Ocupació de la capacitat màxima (%)', effective_capacity_used_percent: 'Ocupació de la capacitat màxima (%)',
  autoextend_headroom_bytes: 'Marge d’autoextensió (bytes)', effective_free_capacity_bytes: 'Espai lliure més autoextensió (bytes)',
  quota_used_bytes: 'Quota emprada per l’usuari connectat (bytes)', quota_limit_bytes: 'Límit de quota (bytes)',
  quota_used_percent: 'Quota emprada per l’usuari connectat (%)',
  quota_unlimited: 'Quota il·limitada', physical_capacity_limit_bytes: 'Límit físic observat (bytes)',
  capacity_known: 'Capacitat coneguda', capacity_unknown_reason: 'Motiu de capacitat desconeguda',
  physical_capacity_status: 'Estat de la capacitat física', quota_scope: 'Abast de la quota',
  autoextend_files: 'Fitxers amb autoextensió', file_count: 'Nombre de fitxers', growth_bytes: 'Creixement observat (bytes)',
  growth_percent: 'Creixement observat (%)', warning_percent: 'Llindar d’avís (%)', critical_percent: 'Llindar crític (%)',
  session_id: 'SID', serial_num: 'SERIAL#', sid: 'SID', sql_id: 'SQL_ID', plan_hash: 'Hash del pla',
  root_blocker: 'Bloquejador arrel', root_blocker_name: 'Usuari del bloquejador', affected_sessions: 'Sessions afectades',
  chain_depth: 'Profunditat de la cadena', observed_duration_seconds: 'Temps observat (s)', sample_count: 'Mostres',
  progress_observation: 'Observació de progrés', observation_note: 'Nota d’observació',
  last_call_et: 'Temps de la darrera crida (s)', seconds_in_wait: 'Temps d’espera (s)', active_sessions: 'Sessions actives',
  long_running_sessions: 'Sessions actives de llarga durada', long_idle_sessions: 'Sessions inactives de llarga durada',
  blocked_sessions: 'Sessions bloquejades', row_count: 'Files consultades', executions: 'Execucions',
  plan_variant_count: 'Variants de pla', elapsed_microseconds: 'Temps transcorregut (µs)', cpu_microseconds: 'CPU (µs)',
  buffer_gets: 'Lectures lògiques', disk_reads: 'Lectures de disc', rows_processed: 'Files processades', parse_calls: 'Anàlisis SQL',
  execution_seconds: 'Temps d’execució (s)', elapsed_per_exec_seconds: 'Temps per execució (s)',
  interval_elapsed_per_execution_seconds: 'Variació del temps per execució (s)', execution_cpu_seconds: 'CPU per execució (s)',
  buffer_gets_per_execution: 'Lectures lògiques per execució', disk_reads_per_execution: 'Lectures de disc per execució',
  rows_per_execution: 'Files per execució', comparison_comparable: 'Comparació disponible', metric_delta_percent: 'Variació de la mètrica (%)',
  statistics_age_days: 'Antiguitat de les estadístiques (dies)', num_rows: 'Files estimades', blocks: 'Blocs', sample_size: 'Mida de la mostra',
  stale_statistics: 'Estadístiques obsoletes', segment_bytes: 'Mida del segment (bytes)', segment_growth_bytes: 'Creixement del segment (bytes)',
  comparison_status: 'Estat de comparació', comparison_direction: 'Direcció de la comparació', comparison_meaning: 'Criteri de comparació',
  chain_integrity: 'Abast de la cadena observada', first_observed_epoch: 'Primera observació (marca temporal)',
  prior_audit_run_id: 'AuditRun anterior', first_observed_at: 'Data de primera observació', last_observed_at: 'Data de darrera observació',
  capacity_comparable: 'Mostres comparables', previous_plan_hash: 'Hash del pla anterior', plan_change_observed: 'Canvi de pla observat',
  plan_comparison_status: 'Estat de comparació dels plans', plan_steps_status: 'Estat de visibilitat dels passos',
  plan_related: 'Relacionat amb un pla SQL', object_owner: 'Propietari de l’objecte', object_name: 'Nom de l’objecte',
  object_type: 'Tipus d’objecte', partition_name: 'Nom de la partició', last_analyzed: 'Darrera anàlisi', stale_stats: 'Estadístiques obsoletes',
  con_id: 'CON_ID', inst_id: 'INST_ID', module: 'Mòdul', transaction_start: 'Inici de la transacció',
  undo_blocks: 'Blocs UNDO', undo_records: 'Registres UNDO', blocking_session: 'SID bloquejador', blocking_instance: 'Instància bloquejadora',
  comparison_window_days: 'Finestra de comparació (dies)', metric_basis: 'Base de la mètrica',
};
const knownMessages = {
  'Observed across scheduled snapshots; sample interval is not proof of continuous blocking.': 'S’ha observat en diverses mostres programades; l’interval entre mostres no demostra un bloqueig continu.',
  'One sample cannot distinguish progress from a stalled call.': 'Una sola mostra no permet distingir entre una crida en curs i una d’aturada.',
  'Observed plan change is a fact, not proof of regression or causality.': 'El canvi de pla és un fet observat, però no demostra una regressió ni una relació causal.',
  'Observed snapshots only; no forecast is produced.': 'Només s’utilitzen mostres observades; no es fa cap previsió.',
  'Read-only metadata probe succeeded.': 'La comprovació de metadades de només lectura ha funcionat.',
  'Read-only fixture metadata probe succeeded.': 'La comprovació de metadades de prova, de només lectura, ha funcionat.',
  'Two fixture instances represented.': 'S’hi representen dues instàncies de prova.',
  'Required dictionary view is not accessible or its privilege is unknown.': 'No es pot consultar la vista de diccionari necessària o no es coneix el permís.',
  'Oracle connection was unavailable during capability discovery.': 'La connexió Oracle no estava disponible en detectar les capacitats.',
  'Cluster-wide instance metadata could not be read.': 'No s’han pogut llegir les metadades de les instàncies del clúster.',
  'GV$ instance metadata is not visible.': 'Les metadades GV$ de les instàncies no són visibles.',
  'AWR/ASH data views are never queried here. AVAILABLE requires explicit license acknowledgement and privilege attestation.': 'Aquí no es consulten les vistes de dades AWR/ASH. «Disponible» requereix declarar explícitament la llicència i el permís.',
  'Explicit environment attestations; AWR/ASH views are not probed or queried.': 'Declaracions explícites de l’entorn; no es comproven ni es consulten les vistes AWR/ASH.',
  'not requested': 'no sol·licitat',
  'NO_ROWS_OR_OUTSIDE_DETAIL_BUDGET': 'sense files o fora del límit de detall',
  'NO_PLAN_ROWS_FOR_HASH': 'el hash no té files de pla',
  'BASELINE_ONLY': 'només hi ha una mostra inicial',
  'COMPARABLE_SNAPSHOTS': 'mostres comparables',
};

function translateValue(value) {
  if (typeof value === 'boolean') return value ? 'Sí' : 'No';
  if (value === null || value === undefined || value === '') return 'Desconegut';
  if (typeof value === 'string') {
    if (knownMessages[value]) return knownMessages[value];
    const rac = value.match(/^GV\$ metadata visible; (\d+) instance\(s\) observed\.$/i);
    if (rac) return `Metadades GV$ visibles; s’han observat ${rac[1]} instàncies.`;
    const minVersion = value.match(/^(.+) requires Oracle (\d+)c or later\.$/i);
    if (minVersion) return `${minVersion[1]} requereix Oracle ${minVersion[2]}c o posterior.`;
    return statusNames[value.toUpperCase()] || value;
  }
  if (Array.isArray(value)) return value.map(translateValue).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function severityName(value) {
  const normalized = String(value || 'UNKNOWN').toUpperCase();
  return statusNames[normalized] || 'Desconeguda';
}

function outcome(report, summary, ruleResults, hasProfile) {
  if (!report) return hasProfile ? 'AVAILABLE' : 'UNKNOWN';
  const state = String(report.audit_state || report.state || report.status || '').toUpperCase();
  const queryMetrics = Array.isArray(summary.query_metrics) ? summary.query_metrics : [];
  if (['FAILED', 'ERROR'].includes(state)) return 'ERROR';
  if (state === 'UNKNOWN') return 'UNKNOWN';
  if (state === 'SKIPPED' || (ruleResults.length > 0 && ruleResults.every((item) => item.status === 'SKIPPED'))) return 'SKIPPED';
  if (report.coverage_state === 'DEGRADED' || report.coverage_state === 'PARTIAL'
    || Number(summary.queries_failed || 0) > 0 || Number(summary.checks_error || 0) > 0
    || queryMetrics.some((item) => item.status === 'ERROR' || item.status === 'FAILED')
    || Number(summary.checks_skipped || 0) > 0
    || ruleResults.some((item) => ['ERROR', 'SKIPPED'].includes(item.status) || item.coverage_meaning === 'partial_visibility')) return 'PARTIAL';
  if (['SUCCESS', 'COMPLETED', 'REPLAYED'].includes(state)) return 'SUCCESS';
  return 'UNKNOWN';
}

function statusForRule(ruleResults, ruleId) {
  return ruleResults.find((result) => result.rule_id === ruleId)?.status || 'UNKNOWN';
}

function ruleSummary(item) {
  if (item.error) return translateValue(item.error);
  if (item.status === 'FAIL') return 'S’ha detectat una incidència segons aquesta comprovació.';
  if (item.status === 'WARN') return 'S’ha observat una condició que cal revisar.';
  if (item.status === 'PASS') return 'La comprovació no ha detectat incidències segons els llindars actuals.';
  if (item.status === 'SKIPPED') return translateValue(item.evidence?.capability || item.summary || 'SKIPPED');
  if (item.status === 'ERROR') return translateValue(item.summary || 'ORACLE_QUERY_FAILED');
  return 'Resultat de la comprovació desconegut.';
}

function observationSeverity(item, findings, ruleResults) {
  if (item.evidence?.observation_severity) return String(item.evidence.observation_severity).toUpperCase();
  const finding = findings.find((row) => String(row.rule_id || '').startsWith('ORACLE_') && row.database_id === item.database_id
    && (row.object_name === item.object_name || row.object_name === item.evidence?.root_blocker || row.evidence?.includes?.(item.sql_id)));
  if (finding) return String(finding.severity || 'UNKNOWN').toUpperCase();
  return String(ruleResults.find((row) => row.rule_id === categoryRule[item.category])?.severity || 'UNKNOWN').toUpperCase();
}

function observationStatus(item, ruleResults) {
  if (item.category === 'CAPACITY' && item.metrics?.capacity_known === false) return 'UNKNOWN';
  if (statusNames[item.evidence?.rule_status]) return item.evidence.rule_status;
  return statusForRule(ruleResults, categoryRule[item.category]);
}

function ObservationCard({ item, findings, ruleResults, onOpenFinding }) {
  const evidence = item.evidence || {};
  const metrics = item.metrics || {};
  const matched = findings.filter((finding) => String(finding.rule_id || '').startsWith('ORACLE_') && (
    finding.database_id === item.database_id && (finding.object_name === item.object_name || finding.object_name === evidence.root_blocker || finding.evidence?.includes?.(item.sql_id))
  ));
  const fields = [...Object.entries(metrics), ...Object.entries(evidence)];
  const severity = observationSeverity(item, findings, ruleResults);
  const state = observationStatus(item, ruleResults);
  const capacity = item.category === 'CAPACITY';
  return <article className="oracle-observation rounded-xl border p-3">
    <details>
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 rounded-md p-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
        <span className="flex flex-wrap items-center gap-2"><b>{categoryNames[item.category] || 'Observació Oracle'}</b><span className="oracle-code">{item.object_name || item.identity_key}</span></span>
        <span className="flex flex-wrap items-center gap-2 text-sm"><span className={`oracle-pill oracle-${state.toLowerCase()}`}>{statusNames[state] || 'Desconegut'}</span><span className="oracle-pill">{severityName(severity)}</span><time>{when(item.observed_at)}</time><ChevronDown aria-hidden="true" size={16}/></span>
      </summary>
      <div className="mt-3 space-y-2 text-sm">
        {item.category === 'SESSION' && <p>Usuari: {evidence.username || 'Desconegut'} · Estat Oracle: <span className="oracle-code">{evidence.session_status || 'UNKNOWN'}</span> · INST {item.inst_id ?? '—'} / CON_ID {item.con_id ?? '—'} · SID {evidence.session_id ?? '—'} / SERIAL# {evidence.serial_num ?? '—'}</p>}
        {item.category === 'BLOCKING' && <><p><b>Bloquejador arrel:</b> <span className="oracle-code">{evidence.root_blocker || '—'}</span> {evidence.root_blocker_name ? `(${evidence.root_blocker_name})` : ''}</p><p>{number(metrics.affected_sessions)} sessions afectades · profunditat {number(metrics.chain_depth)} · {number(metrics.observed_duration_seconds, ' s')} observats / {number(metrics.sample_count)} mostres</p><ol className="list-inside list-decimal space-y-1">{(evidence.chain || []).map((edge, index) => <li key={`${edge.blocking_instance}-${edge.blocking_session}-${edge.blocked_instance}-${edge.blocked_session}-${index}`}>INST {edge.blocking_instance} SID {edge.blocking_session} → INST {edge.blocked_instance} SID {edge.blocked_session} · {translateValue(edge.wait_class || 'UNKNOWN')} / <span className="oracle-code">{edge.event || 'UNKNOWN'}</span> ({number(edge.wait_seconds, ' s')})</li>)}</ol></>}
        {item.category === 'SQL_PERFORMANCE' && <div className="grid gap-1 sm:grid-cols-2"><span>SQL_ID: <span className="oracle-code">{item.sql_id || '—'}</span></span><span>Hash del pla: {item.plan_hash || '—'}</span><span>Execucions: {number(metrics.executions)}</span><span>Temps total: {number(metrics.elapsed_microseconds, ' µs')}</span><span>Temps per execució: {number(metrics.elapsed_per_exec_seconds, ' s')}</span><span>CPU per execució: {number(metrics.execution_cpu_seconds, ' s')}</span><span>Lectures de memòria/execució: {number(metrics.buffer_gets_per_execution)}</span><span>Lectures de disc/execució: {number(metrics.disk_reads_per_execution)}</span><span>Comparació: {translateValue(evidence.comparison_status)} · {translateValue(evidence.metric_basis)}</span></div>}
        {item.category === 'PLAN' && <><p>SQL_ID <span className="oracle-code">{item.sql_id || '—'}</span>: pla {evidence.previous_plan_hash || '—'} → {item.plan_hash || evidence.plan_hash || '—'}</p><p className="text-sm">Un canvi de pla és un fet observat; no demostra regressió ni causalitat. Visibilitat dels passos: {translateValue(evidence.plan_steps_status || 'not requested')}.</p>{evidence.plan_steps?.length > 0 && <div className="overflow-x-auto"><table className="min-w-full text-xs"><thead><tr>{['Id', 'Operació', 'Opcions', 'Objecte', 'Files estimades', 'Cost'].map((label) => <th className="p-1 text-left" key={label}>{label}</th>)}</tr></thead><tbody>{evidence.plan_steps.slice(0, 50).map((step, index) => <tr key={`${step.id}-${index}`}><td>{step.id}</td><td>{step.operation}</td><td>{step.options}</td><td>{[step.object_owner, step.object_name].filter(Boolean).join('.') || '—'}</td><td>{number(step.cardinality)}</td><td>{number(step.cost)}</td></tr>)}</tbody></table></div>}</>}
        {item.category === 'STATISTICS' && <><p>{evidence.object_owner}.{evidence.object_name}{evidence.partition_name ? ` · partició ${evidence.partition_name}` : ''} · {evidence.stale_stats ? 'Estadístiques obsoletes' : 'Estadístiques no obsoletes'}</p><p>Darrera anàlisi: {evidence.last_analyzed || 'Desconeguda'} · antiguitat {number(metrics.statistics_age_days, ' dies')} · files estimades {number(metrics.num_rows)} · blocs {number(metrics.blocks)} · mostra {number(metrics.sample_size)}</p><p className="text-sm">Les estadístiques es consulten només per als objectes que apareixen als plans SQL seleccionats amb límit.</p></>}
        {item.category === 'SEGMENT_GROWTH' && <><p>{evidence.object_owner}.{evidence.object_name}{evidence.partition_name ? ` · partició ${evidence.partition_name}` : ''} · {evidence.segment_type} · espai de taules {evidence.tablespace || 'desconegut'}</p><p>Mida {number(metrics.segment_bytes, ' bytes')} · creixement observat {number(metrics.segment_growth_bytes, ' bytes')} ({number(metrics.growth_percent, '%')})</p><p className="text-sm">{translateValue(evidence.comparison_status)} · només mostres observades; no es fa cap previsió.</p></>}
        {capacity && <section className="oracle-capacity-grid grid gap-2 sm:grid-cols-2" aria-label="Mesures de capacitat">
          <p><b>Espai de taules:</b> <span className="oracle-code">{evidence.tablespace || item.object_name || '—'}</span> · {translateValue(evidence.contents || 'PERMANENT')}</p>
          <p><b>Ocupació de l’espai assignat:</b> {number(metrics.assigned_space_used_percent ?? metrics.used_percent, '%')}</p>
          <p><b>Ocupació de la capacitat màxima efectiva:</b> {number(metrics.effective_capacity_used_percent ?? metrics.max_capacity_percent, '%')}</p>
          <p><b>Espai lliure actual:</b> {number(metrics.free_bytes, ' bytes')}</p>
          <p><b>Marge d’autoextensió:</b> {number(metrics.autoextend_headroom_bytes, ' bytes')}</p>
          <p><b>Espai lliure més autoextensió:</b> {number(metrics.effective_free_capacity_bytes, ' bytes')}</p>
          <p><b>Quota de l’usuari Oracle connectat:</b> {metrics.quota_unlimited ? 'Il·limitada' : number(metrics.quota_limit_bytes, ' bytes')} · consum {number(metrics.quota_used_bytes, ' bytes')} ({number(metrics.quota_used_percent, '%')})</p>
          <p><b>Capacitat física:</b> Desconeguda (no exposada per les vistes consultades)</p>
          <p><b>Llindars:</b> avís {number(evidence.warning_percent, '%')} · crític {number(evidence.critical_percent, '%')}</p>
          {!metrics.capacity_known && <p role="note"><b>Capacitat desconeguda:</b> {translateValue(evidence.capacity_unknown_reason)}</p>}
          <p className="text-sm sm:col-span-2">Les quotes només cobreixen l’usuari Oracle de connexió; no descriuen les quotes d’altres esquemes. El marge d’autoextensió no implica que el disc físic disposi d’espai.</p>
        </section>}
        {fields.length > 0 && <details className="oracle-technical-details rounded-md border p-2"><summary className="cursor-pointer font-semibold">Detalls tècnics sanejats i traçables</summary><dl className="mt-2 grid gap-2 sm:grid-cols-2">{fields.map(([key, value], index) => <div className="min-w-0" key={`${key}-${index}`}><dt className="font-semibold">{fieldNames[key] || key.replaceAll('_', ' ')}</dt><dd className="oracle-code break-words">{translateValue(value)}</dd></div>)}</dl></details>}
        {matched.map((finding) => <button key={finding.id} type="button" onClick={() => onOpenFinding(finding.id)} className="oracle-secondary-button rounded border px-2 py-1 text-xs font-bold">Incidència #{finding.id} · {severityName(finding.severity)} · {translateValue(finding.delta)}</button>)}
      </div>
    </details>
  </article>;
}

function TechnicalErrors({ report, ruleResults }) {
  const errors = report?.diagnostic_errors || report?.errors || [];
  const failedRules = ruleResults.filter((item) => item.status === 'ERROR' || item.status === 'SKIPPED');
  if (!errors.length && !failedRules.length) return null;
  const normalized = [...errors, ...failedRules.map((item) => ({ rule_id: item.rule_id, error_class: item.error || item.summary || item.status }))];
  return <details className={`${panel} oracle-error-panel`}>
    <summary className="cursor-pointer font-bold">Consulta els errors tècnics sanejats ({normalized.length})</summary>
    <ul className="mt-2 space-y-2">{normalized.map((item, index) => <li key={`${item.rule_id}-${index}`}><span className="oracle-code">{item.rule_id || 'ORACLE_DIAGNOSTIC'}</span> · <span className="oracle-code">{translateValue(item.error_class || item.error || 'UNKNOWN')}</span></li>)}</ul>
  </details>;
}

export default function OracleDiagnosticsView({ profiles = [], selectedProfile = '', onProfileChange = () => {} }) {
  const [profile, setProfile] = React.useState(selectedProfile || profiles[0] || '');
  const [report, setReport] = React.useState(null);
  const [auditDetail, setAuditDetail] = React.useState(null);
  const [observations, setObservations] = React.useState([]);
  const [findings, setFindings] = React.useState([]);
  const [totalObservations, setTotalObservations] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState('');
  const [severityFilter, setSeverityFilter] = React.useState('ALL');
  const [statusFilter, setStatusFilter] = React.useState('ALL');
  const [objectFilter, setObjectFilter] = React.useState('');
  const runningRef = React.useRef(false);
  const loadingRef = React.useRef(false);
  const observationsRef = React.useRef([]);
  const requestSequence = React.useRef(0);

  React.useEffect(() => {
    if (selectedProfile && selectedProfile !== profile) setProfile(selectedProfile);
    else if (!profile && profiles[0]) setProfile(profiles[0]);
  }, [selectedProfile, profiles, profile]);

  const load = React.useCallback(async ({ append = false } = {}) => {
    if (!profile || loadingRef.current) return;
    loadingRef.current = true;
    const offset = append ? observationsRef.current.length : 0;
    setLoading(true);
    setError('');
    try {
      const [history, findingResult] = await Promise.all([
        getOracleDiagnosticHistory(profile, { limit: PAGE_SIZE, offset }),
        append ? Promise.resolve(null) : getFindings({ database: profile }),
      ]);
      const items = history.items || [];
      setFindings((current) => findingResult ? (findingResult.items || []) : current);
      setAuditDetail(history.latest_audit || null);
      const nextItems = append ? [...observationsRef.current, ...items] : items;
      observationsRef.current = nextItems;
      setObservations(nextItems);
      setTotalObservations(Number(history.total ?? items.length));
    } catch (loadError) {
      const message = loadError?.code === 'ECONNABORTED' ? 'S’ha esgotat el temps per carregar l’historial.' : 'No s’ha pogut carregar l’historial o les evidències Oracle. Comprova la connexió seleccionada i el servei.';
      setError(message);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [profile]);

  React.useEffect(() => { observationsRef.current = []; setObservations([]); setTotalObservations(0); load(); }, [load]);

  async function runNow() {
    if (!profile || runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setError('');
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 300_000);
    try {
      const result = await runOracleDiagnostics({
        profile,
        audit_run_id: `AUD-MAN-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
      }, { signal: controller.signal, timeout: 300_000 });
      if (sequence !== requestSequence.current) return;
      setReport(result);
      await load();
    } catch (runError) {
      const timeoutError = controller.signal.aborted || runError?.code === 'ECONNABORTED';
      setError(timeoutError
        ? 'El diagnòstic ha superat el límit de cinc minuts. Actualitza l’historial abans de tornar-lo a executar.'
        : 'No s’ha pogut completar el diagnòstic Oracle. Les incidències existents es conserven si la cobertura és incompleta.');
    } finally {
      window.clearTimeout(timeout);
      runningRef.current = false;
      setRunning(false);
    }
  }

  function openFinding(id) {
    localStorage.setItem('e13db:selected-finding-id', String(id));
    window.dispatchEvent(new CustomEvent('e13db-open-finding', { detail: { id } }));
  }

  const visibleReport = report || auditDetail;
  const capabilities = visibleReport?.capability_snapshot?.snapshot?.capabilities || visibleReport?.capability_snapshot?.capabilities || {};
  const scope = visibleReport?.capability_snapshot?.snapshot || visibleReport?.capability_snapshot || {};
  const summary = visibleReport?.summary || visibleReport?.diagnostic_summary || {};
  const diagnosticOptions = visibleReport?.context?.diagnostic_options || visibleReport?.execution_options || {};
  const ruleResults = visibleReport?.rule_results || [];
  const overall = outcome(visibleReport, summary, ruleResults, Boolean(profile));
  const queryMetrics = Array.isArray(summary.query_metrics) ? summary.query_metrics : null;
  const executedCount = summary.queries_executed ?? summary.query_count ?? null;
  const errorsCount = summary.queries_failed ?? (queryMetrics ? queryMetrics.filter((item) => item.status === 'ERROR').length : null);
  const succeededCount = summary.queries_succeeded ?? (queryMetrics ? queryMetrics.filter((item) => item.status === 'AVAILABLE').length : executedCount !== null && errorsCount !== null ? executedCount - errorsCount : null);
  const skippedCount = summary.queries_skipped ?? (ruleResults.length ? ruleResults.filter((item) => item.status === 'SKIPPED' && item.rule_id !== 'ORACLE_CAPACITY_MAX').length : null);
  const ruleTotal = summary.checks_total ?? (ruleResults.length || null);
  const ruleFailures = summary.checks_fail ?? (ruleResults.length ? ruleResults.filter((item) => item.status === 'FAIL').length : null);
  const ruleErrors = summary.checks_error ?? (ruleResults.length ? ruleResults.filter((item) => item.status === 'ERROR').length : null);
  const ruleSkipped = summary.checks_skipped ?? (ruleResults.length ? ruleResults.filter((item) => item.status === 'SKIPPED').length : null);
  const filtered = observations.filter((item) => {
    const severity = observationSeverity(item, findings, ruleResults);
    const status = observationStatus(item, ruleResults);
    const objectText = `${item.object_name || ''} ${item.identity_key || ''} ${item.sql_id || ''} ${item.evidence?.tablespace || ''}`.toLocaleLowerCase('ca');
    const severityMatch = severityFilter === 'ALL' || (severityFilter === 'CRITICAL' ? ['CRITICAL', 'CRITIC'].includes(severity) : severityFilter === 'MEDIUM' ? ['MEDIUM', 'MITJA'].includes(severity) : ['LOW', 'BAIXA'].includes(severity));
    return severityMatch && (statusFilter === 'ALL' || status === statusFilter) && (!objectFilter.trim() || objectText.includes(objectFilter.trim().toLocaleLowerCase('ca')));
  });
  const visibleFindings = findings.filter((item) => String(item.rule_id || '').startsWith('ORACLE_') && item.status !== 'RESOLVED');

  return <section className="oracle-diagnostics space-y-5" aria-label="Diagnòstics operatius Oracle" aria-busy={loading || running}>
    <header className="oracle-header flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-[.16em]">Oracle · només lectura</p><h2 className="text-3xl font-black">Diagnòstics Oracle en profunditat</h2><p className="max-w-3xl text-sm">Sessions, bloquejos, rendiment, plans, estadístiques i emmagatzematge observats. Les correlacions són indicis, no causes confirmades.</p></div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="oracle-control-label grid gap-1 text-sm font-semibold">Connexió Oracle
          <select aria-label="Connexió Oracle" value={profile} disabled={loading || running} onChange={(event) => { setProfile(event.target.value); onProfileChange(event.target.value); setReport(null); setAuditDetail(null); observationsRef.current = []; setObservations([]); setTotalObservations(0); }} className="oracle-select rounded border px-3 py-2">
            {profiles.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <button type="button" onClick={() => { setReport(null); load(); }} disabled={!profile || loading || running} className="oracle-secondary-button flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 font-semibold disabled:cursor-not-allowed disabled:opacity-60"><RefreshCcw aria-hidden="true" size={15}/>{loading ? 'Actualitzant…' : 'Actualitza'}</button>
        <button type="button" onClick={runNow} disabled={!profile || running || loading} aria-describedby="oracle-run-status" className="oracle-run-button flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60">
          {running ? <LoaderCircle aria-hidden="true" size={17} className="animate-spin"/> : <Activity aria-hidden="true" size={17}/>}
          {running ? 'Executant el diagnòstic…' : 'Executa el diagnòstic'}
        </button>
      </div>
    </header>

    <p id="oracle-run-status" role="status" aria-live="polite" className={`oracle-run-state oracle-${running ? 'running' : overall.toLowerCase()} rounded-md border px-3 py-2 text-sm font-semibold`}>
      {running ? 'Executant el diagnòstic… Les consultes són de només lectura. El procés finalitzarà automàticament en cinc minuts com a màxim.' : `Estat de l’execució: ${statusNames[overall] || 'Desconegut'} (${overall}). ${overall === 'UNKNOWN' ? 'No hi ha cap execució registrada.' : ''}`}
    </p>
    {error && <p role="alert" className="oracle-alert rounded-xl border p-4">{error}</p>}

    {visibleReport && <section className="oracle-executive-summary rounded-xl border p-4" aria-labelledby="oracle-executive-title">
      <h3 id="oracle-executive-title" className="flex items-center gap-2 text-xl font-bold"><Activity aria-hidden="true" size={19}/>Resum executiu</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <article className="oracle-summary-tile"><b>Resultat</b><p className={`oracle-pill oracle-${overall.toLowerCase()} mt-1 inline-flex`}>{statusNames[overall]} ({overall})</p><p>{visibleReport.coverage_state ? `Cobertura: ${translateValue(visibleReport.coverage_state)}` : 'Cobertura desconeguda'}</p></article>
        <article className="oracle-summary-tile"><b>Consultes de només lectura</b><p>{number(executedCount)} executades · {number(succeededCount)} correctes · {number(errorsCount)} fallides · {number(skippedCount)} omeses per manca de cobertura</p><p>Pressupost màxim: {number(summary.query_budget)}.</p></article>
        <article className="oracle-summary-tile"><b>Regles analitzades</b><p>{number(ruleTotal)} totals · {number(ruleFailures)} incidències · {number(ruleErrors)} errors · {number(ruleSkipped)} omeses</p></article>
        <article className="oracle-summary-tile"><b>Execució traçable</b><p className="oracle-code break-all">{visibleReport.audit_run_id || 'Desconegut'}</p><p>{visibleReport.trigger_type === 'SCHEDULED' ? 'Programada' : 'Manual'} · conciliació {translateValue(visibleReport.reconciliation_state || 'UNKNOWN')}</p></article>
      </div>
      {overall === 'PARTIAL' && <p className="oracle-partial-note mt-3 rounded-md border p-3"><b>Cobertura parcial:</b> no totes les regles han pogut consultar dades. Les dades absents no s’interpreten com a estat correcte; revisa les limitacions i els errors sanejats.</p>}
    </section>}

    <div className="grid gap-3 md:grid-cols-4">
      <article className={`${panel} oracle-summary-tile`}><b className="text-xs">Connexió i abast</b><p className="mt-1 font-bold">{profile || '—'} · {translateValue(scope.cdb_scope || 'UNKNOWN')}</p><p className="text-xs">Instàncies RAC: {scope.rac_instance_count ?? 'Desconegut'} · CON_ID actual: {scope.current_container_id ?? 'Desconegut'}.</p></article>
      <article className={`${panel} oracle-summary-tile`}><b className="text-xs">AuditRun</b><p className="oracle-code mt-1 break-all text-xs">{visibleReport?.audit_run_id || 'Cap execució registrada'}</p><p className="text-xs">Estat {translateValue(visibleReport?.state || visibleReport?.audit_state || 'UNKNOWN')} · cobertura {translateValue(visibleReport?.coverage_state || 'UNKNOWN')} · conciliació {translateValue(visibleReport?.reconciliation_state || 'UNKNOWN')}</p><p className="mt-1 text-xs">Sondeigs de capacitat: {summary.capability_probe_count ?? '—'} · temps {summary.capability_discovery_seconds ?? '—'} s</p></article>
      <article className={`${panel} oracle-summary-tile`}><b className="text-xs">Incidències Oracle actives</b><p className="mt-1 text-2xl font-black">{visibleFindings.length}</p><p className="text-xs">Les incidències obertes es conserven quan una regla queda omesa o perd visibilitat.</p></article>
      <article className={`${panel} oracle-summary-tile`}><b className="text-xs">AWR / ASH</b><p className="oracle-code mt-1 font-bold">{translateValue(capabilities.AWR_ALLOWED || 'UNKNOWN')} / {translateValue(capabilities.ASH_ALLOWED || 'UNKNOWN')}</p><p className="text-xs">Aquest diagnòstic no consulta les vistes de dades AWR ni ASH.</p></article>
    </div>

    <section className={`${panel} oracle-capability-panel`} aria-label="Capacitats Oracle">
      <h3 className="flex items-center gap-2 font-bold"><Database aria-hidden="true" size={17}/>Capacitats, permisos i visibilitat</h3>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(capabilities).map(([key, value]) => <div key={key} className="oracle-capability rounded border p-2 text-xs"><b className="oracle-code">{key}</b><span className="ml-2 font-semibold">{translateValue(value)}</span><span className="mt-1 block">{translateValue(scope.reasons?.[key] || scope.snapshot?.reasons?.[key] || '')}</span></div>)}</div>
      <p className="mt-2 text-xs">Classificació de connexió: {translateValue(scope.connection_class || 'UNKNOWN')} · detecció de permisos: {translateValue(scope.privilege_discovery_status || 'UNKNOWN')} · resum de capacitats <span className="oracle-code">{visibleReport?.capability_snapshot_hash || visibleReport?.capability_snapshot?.snapshot_hash || '—'}</span></p>
    </section>

    {ruleResults.some((item) => item.status === 'SKIPPED' || item.status === 'ERROR' || item.coverage_meaning === 'partial_visibility') && <section className="oracle-partial-note rounded-xl border p-4" aria-label="Limitacions de cobertura"><h3 className="flex items-center gap-2 font-bold"><AlertTriangle aria-hidden="true" size={17}/>Limitacions de cobertura</h3>{ruleResults.filter((item) => item.status === 'SKIPPED' || item.status === 'ERROR' || item.coverage_meaning === 'partial_visibility').map((item) => <p key={item.rule_id} className="mt-2 text-sm"><span className="oracle-code">{item.rule_id}</span> · {statusNames[item.status] || item.status} — {translateValue(item.error || item.summary || item.evidence?.capability || 'Visibilitat parcial o no disponible.')}</p>)}</section>}

    {Object.keys(diagnosticOptions).length > 0 && <section className={`${panel} oracle-thresholds`} aria-label="Llindars efectius"><h3 className="font-bold">Llindars efectius del diagnòstic</h3><div className="mt-2 flex flex-wrap gap-2">{Object.entries(diagnosticOptions).map(([key, value]) => <span key={key} className="oracle-pill">{thresholdNames[key] || key.replaceAll('_', ' ')}: {translateValue(value)}</span>)}</div></section>}
    <TechnicalErrors report={visibleReport} ruleResults={ruleResults}/>

    <section className="oracle-observations-section" aria-label="Observacions i historial">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="text-xl font-bold">Observacions amb data i hora</h3><p className="text-sm">Historial limitat i paginat, amb dades sanejades. No s’hi desen literals SQL ni valors de bind.</p></div><span className="text-sm" role="status">{filtered.length} visibles de {totalObservations} observacions</span></div>
      <div className="oracle-filters mt-3 grid gap-2 rounded-xl border p-3 sm:grid-cols-3">
        <label className="grid gap-1 text-sm font-semibold">Filtra per gravetat<select aria-label="Filtra per gravetat" className="oracle-select rounded border px-2 py-2" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}><option value="ALL">Totes les gravetats</option><option value="CRITICAL">Crítica</option><option value="MEDIUM">Mitjana</option><option value="LOW">Baixa</option></select></label>
        <label className="grid gap-1 text-sm font-semibold">Filtra per estat<select aria-label="Filtra per estat" className="oracle-select rounded border px-2 py-2" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">Tots els estats</option>{['PASS', 'WARN', 'FAIL', 'ERROR', 'SKIPPED', 'UNKNOWN'].map((value) => <option key={value} value={value}>{statusNames[value]} ({value})</option>)}</select></label>
        <label className="grid gap-1 text-sm font-semibold">Filtra per objecte o SQL_ID<span className="relative"><Search aria-hidden="true" size={15} className="absolute left-2 top-3"/><input aria-label="Filtra per objecte o SQL_ID" className="oracle-select w-full rounded border py-2 pl-8 pr-2" value={objectFilter} onChange={(event) => setObjectFilter(event.target.value)} placeholder="Nom d’objecte, SID o SQL_ID"/></span></label>
      </div>
      {groups.map(([groupKey, groupName]) => {
        const groupItems = filtered.filter((item) => categoryGroups[item.category] === groupKey);
        if (!groupItems.length) return null;
        return <section key={groupKey} className="mt-4" aria-label={`Observacions: ${groupName}`}><h4 className="mb-2 text-lg font-bold">{groupName} <span className="oracle-pill">{groupItems.length}</span></h4><div className="space-y-2">{groupItems.map((item, index) => <ObservationCard key={`${item.audit_run_id}-${item.category}-${item.identity_key}-${index}`} item={item} findings={findings} ruleResults={ruleResults} onOpenFinding={openFinding}/>)}</div></section>;
      })}
      {filtered.length === 0 && <p className={`${panel} mt-3`}>{observations.length ? 'No hi ha observacions que coincideixin amb els filtres.' : 'Encara no hi ha observacions per a aquesta connexió. Executa un diagnòstic o comprova que hagi acabat la tasca programada.'}</p>}
      {observations.length < totalObservations && <button type="button" disabled={loading} onClick={() => load({ append: true })} className="oracle-secondary-button mt-3 flex items-center gap-2 rounded border px-3 py-2 font-semibold disabled:opacity-60">{loading ? <LoaderCircle aria-hidden="true" size={16} className="animate-spin"/> : null}{loading ? 'Carregant observacions…' : `Carrega’n més (${observations.length} de ${totalObservations})`}</button>}
      {loading && <p role="status" aria-live="polite" className="mt-2 text-sm">Actualitzant l’historial…</p>}
    </section>

    <section className={`${panel} oracle-rule-results`} aria-label="Resultats de les regles"><h3 className="font-bold">Resultats de les comprovacions</h3><div className="mt-2 divide-y">{ruleResults.length ? ruleResults.map((item) => <div key={`${item.attempt_no || 0}-${item.rule_id}`} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><b><span className="oracle-code">{item.rule_id}</span><span className="ml-2">{ruleNames[item.rule_id] || 'Comprovació Oracle'}</span></b><span>{statusNames[item.status] || item.status} · {translateValue(item.coverage_meaning || 'EVALUATED')} · {ruleSummary(item)}</span></div>) : <p className="text-sm">Selecciona una execució recent per consultar-ne les comprovacions.</p>}</div></section>
    {(visibleReport?.runtime_identity || visibleReport?.capability_snapshot_hash) && <p className="oracle-metadata text-xs">Entorn {visibleReport.runtime_identity?.git_sha || 'desconegut'} · paquet de regles <span className="oracle-code">{visibleReport.rule_pack_identity || 'desconegut'}</span> · AuditRun traçable a l’historial d’auditories.</p>}
  </section>;
}
