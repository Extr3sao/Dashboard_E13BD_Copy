import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  ArrowLeftRight,
  Brain,
  Check,
  Copy,
  Database,
  Download,
  Loader2,
  Play,
  Sparkles,
  Terminal,
} from 'lucide-react';

function formatEngineDate(date, { withTime = true } = {}) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  if (!withTime) return `${year}-${month}-${day}`;
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

function buildDefaultVariables() {
  const end = new Date();
  const start = new Date(end.getTime() - (24 * 60 * 60 * 1000));
  return {
    START_AT: formatEngineDate(start, { withTime: true }),
    END_AT: formatEngineDate(end, { withTime: true }),
    START_DATE: formatEngineDate(start, { withTime: false }),
    END_DATE: formatEngineDate(end, { withTime: false }),
  };
}

function detectSqlVariables(...sqlTexts) {
  const detected = [];
  sqlTexts.filter(Boolean).forEach((sql) => {
    const matches = String(sql).match(/&([A-Z_][A-Z0-9_]*)/gi) || [];
    matches.forEach((raw) => {
      const normalized = raw.replace('&', '').toUpperCase();
      if (!detected.includes(normalized)) detected.push(normalized);
    });
  });
  return detected;
}

function buildCsv(columns, rows) {
  const escapeValue = (value) => {
    const normalized = value == null ? '' : String(value);
    if (/[",\n]/.test(normalized)) return `"${normalized.replace(/"/g, '""')}"`;
    return normalized;
  };
  const header = columns.map(escapeValue).join(',');
  const body = (rows || []).map((row) => columns.map((column) => escapeValue(row?.[column])).join(',')).join('\n');
  return [header, body].filter(Boolean).join('\n');
}

function downloadBlob(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function comparisonBadge(comparison) {
  if (!comparison) return { label: 'Sense comparar', cls: 'bg-slate-100 text-slate-700 border-slate-200' };
  if (comparison.status === 'match') return { label: 'Coincideixen', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
  if (comparison.status === 'warning') return { label: 'Coincideixen amb matisos', cls: 'bg-amber-50 text-amber-700 border-amber-200' };
  return { label: 'No coincideixen', cls: 'bg-rose-50 text-rose-700 border-rose-200' };
}

function SQLEditor({ value, onChange, height = '190px' }) {
  const textareaRef = useRef(null);

  const handleKeyDown = (event) => {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    const textarea = textareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const nextValue = value.substring(0, start) + '  ' + value.substring(end);
    onChange(nextValue);
    requestAnimationFrame(() => {
      textarea.selectionStart = textarea.selectionEnd = start + 2;
    });
  };

  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={handleKeyDown}
      spellCheck={false}
      style={{ height, fontFamily: 'Consolas, "Courier New", monospace', fontSize: '13px' }}
      className="w-full rounded-xl border border-slate-200 bg-slate-950 px-3 py-3 text-green-300 outline-none focus:ring-2 focus:ring-indigo-200"
    />
  );
}

function ResultPanel({ title, subtitle, result, loading, tone, exportPrefix }) {
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const rows = Array.isArray(result?.rows) ? result.rows : [];
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visibleRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
  const panelTone = tone === 'right' ? 'border-indigo-200 bg-indigo-50/70' : 'border-slate-200 bg-white';

  useEffect(() => {
    setPage(1);
  }, [result]);

  return (
    <div className={`rounded-2xl border ${panelTone} shadow-sm`}>
      <div className="px-4 py-3 border-b border-slate-200/80">
        <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">{title}</div>
        <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
      </div>
      <div className="px-4 py-4">
        {!result && !loading && <div className="text-sm text-slate-500">Encara no s'ha executat.</div>}
        {loading && !result && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Executant consulta...</div>}
        {result && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Estat</div><div className={`mt-1 text-sm font-bold ${result.success ? 'text-emerald-700' : 'text-rose-700'}`}>{result.success ? 'Correcte' : 'Error'}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Files</div><div className="mt-1 text-sm font-bold text-slate-800">{result.row_count ?? 0}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Columnes</div><div className="mt-1 text-sm font-bold text-slate-800">{(result.columns || []).length}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Temps</div><div className="mt-1 text-sm font-bold text-slate-800">{result.execution_ms ?? 0} ms</div></div>
            </div>

            {result.error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{result.error}</div>}

            {!!result.success && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => downloadBlob(`${exportPrefix}.csv`, buildCsv(result.columns || [], result.rows || []), 'text/csv;charset=utf-8')} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-700 hover:bg-slate-50">
                    <Download size={12} /> CSV
                  </button>
                  <button type="button" onClick={() => downloadBlob(`${exportPrefix}.json`, JSON.stringify(result, null, 2), 'application/json;charset=utf-8')} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-700 hover:bg-slate-50">
                    <Download size={12} /> JSON
                  </button>
                  {result.preview_limited && <span className="text-[11px] font-medium text-amber-700">Mostra inicial limitada a {rows.length} files.</span>}
                </div>

                {!!Object.keys(result.variables_used || {}).length && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Paràmetres utilitzats</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(result.variables_used || {}).map(([key, value]) => (
                        <span key={key} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-mono text-slate-700">{key}={String(value)}</span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="rounded-xl border border-slate-200 overflow-hidden">
                  <div className="overflow-auto">
                    <table className="min-w-full text-xs">
                      <thead className="bg-slate-50">
                        <tr>
                          {(result.columns || []).map((column) => (
                            <th key={column} className="px-3 py-2 text-left font-bold uppercase tracking-wide text-slate-600">{column}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((row, index) => (
                          <tr key={`${title}-${safePage}-${index}`} className="border-t border-slate-100">
                            {(result.columns || []).map((column) => (
                              <td key={`${column}-${index}`} className="px-3 py-2 align-top text-slate-700">
                                {row?.[column] == null ? <span className="italic text-slate-400">null</span> : String(row[column])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {rows.length > pageSize && (
                    <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
                      <span>Pàgina {safePage} de {totalPages}</span>
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={safePage === 1} className="rounded-md border border-slate-200 bg-white px-2 py-1 disabled:opacity-40">Anterior</button>
                        <button type="button" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={safePage === totalPages} className="rounded-md border border-slate-200 bg-white px-2 py-1 disabled:opacity-40">Següent</button>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DiffPanel({ comparison, leftResult, rightResult }) {
  const badge = comparisonBadge(comparison);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200/80 px-4 py-3">
        <div>
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">Comparació de resultats</div>
          <div className="mt-1 text-xs text-slate-500">Metadades, cardinalitat, contingut i ordre.</div>
        </div>
        <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${badge.cls}`}>{badge.label}</span>
      </div>
      <div className="px-4 py-4">
        {!comparison && <div className="text-sm text-slate-500">Executa la comparació per veure l'anàlisi diferencial.</div>}
        {comparison && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Files esquerra</div><div className="mt-1 text-sm font-bold text-slate-800">{leftResult?.row_count ?? 0}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Files dreta</div><div className="mt-1 text-sm font-bold text-slate-800">{rightResult?.row_count ?? 0}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Columnes esquerra</div><div className="mt-1 text-sm font-bold text-slate-800">{(leftResult?.columns || []).length}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Columnes dreta</div><div className="mt-1 text-sm font-bold text-slate-800">{(rightResult?.columns || []).length}</div></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Diferències</div><div className="mt-1 text-sm font-bold text-slate-800">{comparison.differences_found ?? 0}</div></div>
            </div>
            <div className={`rounded-xl border px-4 py-3 text-sm ${badge.cls}`}>
              <div className="font-bold">Estat general: {badge.label}</div>
              <div className="mt-1">{comparison.summary}</div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Només a l'esquerra</div>
                <div className="mt-2 space-y-2 text-xs text-slate-700">
                  {(comparison.only_in_left || []).length === 0 && <div>No n'hi ha.</div>}
                  {(comparison.only_in_left || []).map((row, index) => <pre key={`left-only-${index}`} className="overflow-auto rounded-lg bg-white p-2 text-[11px]">{JSON.stringify(row, null, 2)}</pre>)}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Només a la dreta</div>
                <div className="mt-2 space-y-2 text-xs text-slate-700">
                  {(comparison.only_in_right || []).length === 0 && <div>No n'hi ha.</div>}
                  {(comparison.only_in_right || []).map((row, index) => <pre key={`right-only-${index}`} className="overflow-auto rounded-lg bg-white p-2 text-[11px]">{JSON.stringify(row, null, 2)}</pre>)}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Diferències de valors</div>
                <div className="mt-2 space-y-2 text-xs text-slate-700">
                  {(comparison.value_differences || []).length === 0 && <div>Cap diferència de valors amb la clau actual.</div>}
                  {(comparison.value_differences || []).map((row, index) => <pre key={`value-diff-${index}`} className="overflow-auto rounded-lg bg-white p-2 text-[11px]">{JSON.stringify(row, null, 2)}</pre>)}
                </div>
              </div>
            </div>
            <button type="button" onClick={() => downloadBlob('codex-comparison-diff.json', JSON.stringify({ leftResult, rightResult, comparison }, null, 2), 'application/json;charset=utf-8')} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-700 hover:bg-slate-50">
              <Download size={12} /> Exportar diff JSON
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function AnalysisPanel({ analysis, loading }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200/80 px-4 py-3">
        <div>
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">Anàlisi de diferències</div>
          <div className="mt-1 text-xs text-slate-500">Explicació assistida per IA basada només en SQL i resultats reals.</div>
        </div>
        {loading && <Loader2 size={16} className="animate-spin text-slate-400" />}
      </div>
      <div className="px-4 py-4">
        {!analysis && !loading && <div className="text-sm text-slate-500">Encara no s'ha demanat l'anàlisi IA.</div>}
        {analysis && (
          <div className="space-y-3">
            {analysis.status !== 'ok' && <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{analysis.error || 'L’anàlisi IA no està disponible ara mateix.'}</div>}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Resum</div><div className="mt-2 text-sm text-slate-700">{analysis.summary || 'Sense resum disponible.'}</div></div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Possibles causes</div><div className="mt-2 space-y-2 text-sm text-slate-700">{(analysis.possible_causes || []).length === 0 ? <div>No s’han informat causes addicionals.</div> : (analysis.possible_causes || []).map((cause, index) => <div key={`cause-${index}`} className="rounded-lg border border-slate-200 bg-white px-3 py-2">{cause}</div>)}</div></div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Recomanació</div><div className="mt-2 text-sm text-slate-700">{analysis.recommendation || 'Sense recomanació disponible.'}</div></div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SQLCodexWorkbench({ originalSql, selectedProfile, profiles = [] }) {
  const [leftSql, setLeftSql] = useState(originalSql || '');
  const [rightSql, setRightSql] = useState('');
  const [logs, setLogs] = useState([]);
  const [transforming, setTransforming] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [variables, setVariables] = useState(() => buildDefaultVariables());
  const [options, setOptions] = useState({
    trimWhitespace: true,
    nullEqualsEmpty: false,
    ignoreCase: false,
    ignoreRowOrder: false,
    normalizeDates: true,
    normalizeNumbers: true,
    compareByColumnName: true,
    normalizeColumnAliases: true,
    previewLimit: 100,
    sampleLimit: 25,
    comparisonKey: '',
  });
  const [leftResult, setLeftResult] = useState(null);
  const [rightResult, setRightResult] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [busyAction, setBusyAction] = useState('');
  const availableProfiles = Array.isArray(profiles) ? profiles.filter(Boolean) : [];
  const availableProfilesKey = availableProfiles.join('|');
  const [executionProfile, setExecutionProfile] = useState(selectedProfile || availableProfiles[0] || '');

  const detectedVariables = detectSqlVariables(leftSql, rightSql);

  useEffect(() => {
    setExecutionProfile((current) => {
      if (current && availableProfiles.includes(current)) return current;
      if (selectedProfile && (!availableProfiles.length || availableProfiles.includes(selectedProfile))) return selectedProfile;
      return availableProfiles[0] || '';
    });
  }, [selectedProfile, availableProfilesKey]);

  const transformSql = useCallback(async (sourceSql) => {
    setTransforming(true);
    try {
      const response = await axios.post('/api/checks/transform-sql', { sql_text: sourceSql, debug: true });
      setRightSql(response.data?.transformed_sql || '');
      setLogs(response.data?.logs || []);
    } catch (_err) {
      setRightSql('');
      setLogs([]);
    } finally {
      setTransforming(false);
    }
  }, []);

  useEffect(() => {
    const nextSql = originalSql || '';
    setLeftSql(nextSql);
    setLeftResult(null);
    setRightResult(null);
    setComparison(null);
    setAiAnalysis(null);
    if (nextSql) transformSql(nextSql);
    else {
      setRightSql('');
      setLogs([]);
    }
  }, [originalSql, transformSql]);

  useEffect(() => {
    setVariables((current) => {
      const next = { ...current };
      detectedVariables.forEach((name) => {
        if (typeof next[name] === 'undefined') next[name] = '';
      });
      return next;
    });
  }, [leftSql, rightSql]);

  const buildVariablesPayload = () => detectedVariables.reduce((acc, name) => {
    acc[name] = variables[name] ?? '';
    return acc;
  }, {});

  const buildComparisonOptions = () => ({
    trim_whitespace: options.trimWhitespace,
    null_equals_empty: options.nullEqualsEmpty,
    ignore_case: options.ignoreCase,
    ignore_row_order: options.ignoreRowOrder,
    normalize_dates: options.normalizeDates,
    normalize_numbers: options.normalizeNumbers,
    compare_by_column_name: options.compareByColumnName,
    normalize_column_aliases: options.normalizeColumnAliases,
    preview_limit: Number(options.previewLimit) || 100,
    sample_limit: Number(options.sampleLimit) || 25,
    comparison_key: String(options.comparisonKey || '').split(',').map((item) => item.trim()).filter(Boolean),
  });

  const runExecute = async (side) => {
    setBusyAction(side === 'left' ? 'execute-left' : 'execute-right');
    setAiAnalysis(null);
    try {
      const response = await axios.post('/api/checks/codex-engine/execute', {
        sql_text: side === 'left' ? leftSql : rightSql,
        side,
        profile: executionProfile,
        variables: buildVariablesPayload(),
        preview_limit: Number(options.previewLimit) || 100,
      });
      const result = response.data?.result || null;
      if (side === 'left') setLeftResult(result);
      else setRightResult(result);
      setComparison(null);
    } catch (err) {
      const failure = { success: false, columns: [], rows: [], row_count: 0, execution_ms: 0, error: err?.response?.data?.detail || err.message };
      if (side === 'left') setLeftResult(failure);
      else setRightResult(failure);
      setComparison(null);
    } finally {
      setBusyAction('');
    }
  };

  const runExecuteBoth = async () => {
    setBusyAction('execute-both');
    setAiAnalysis(null);
    try {
      const response = await axios.post('/api/checks/codex-engine/execute-both', {
        left_sql: leftSql,
        right_sql: rightSql,
        profile: executionProfile,
        variables: buildVariablesPayload(),
        preview_limit: Number(options.previewLimit) || 100,
      });
      setLeftResult(response.data?.left || null);
      setRightResult(response.data?.right || null);
      setComparison(null);
    } catch (err) {
      const failure = { success: false, columns: [], rows: [], row_count: 0, execution_ms: 0, error: err?.response?.data?.detail || err.message };
      setLeftResult(failure);
      setRightResult(failure);
      setComparison(null);
    } finally {
      setBusyAction('');
    }
  };

  const runCompare = async () => {
    setBusyAction('compare');
    setAiAnalysis(null);
    try {
      const response = await axios.post('/api/checks/codex-engine/compare', {
        left_sql: leftSql,
        right_sql: rightSql,
        profile: executionProfile,
        variables: buildVariablesPayload(),
        options: buildComparisonOptions(),
      });
      setLeftResult(response.data?.left || null);
      setRightResult(response.data?.right || null);
      setComparison(response.data?.comparison || null);
      return response.data;
    } catch (err) {
      setComparison({ status: 'mismatch', summary: err?.response?.data?.detail || err.message, differences_found: 1 });
      return null;
    } finally {
      setBusyAction('');
    }
  };

  const runAiAnalysis = async () => {
    setBusyAction('ai');
    try {
      let comparePayload = { left: leftResult, right: rightResult, comparison };
      if (!comparison || !leftResult || !rightResult) {
        const response = await runCompare();
        if (!response) {
          setAiAnalysis({ status: 'error', summary: '', possible_causes: [], recommendation: '', error: 'No s’ha pogut obtenir una comparació prèvia vàlida.' });
          return;
        }
        comparePayload = response;
      }
      const response = await axios.post('/api/checks/codex-engine/analyze', {
        left_sql: leftSql,
        right_sql: rightSql,
        left: comparePayload.left,
        right: comparePayload.right,
        comparison: comparePayload.comparison,
      });
      setAiAnalysis(response.data?.ai_analysis || null);
    } catch (err) {
      setAiAnalysis({ status: 'error', summary: '', possible_causes: [], recommendation: '', error: err?.response?.data?.detail || err.message });
    } finally {
      setBusyAction('');
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(rightSql || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-2 mb-4 rounded-3xl border border-indigo-200 bg-gradient-to-br from-white via-indigo-50/60 to-slate-50 p-4 shadow-sm overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-indigo-200 bg-indigo-100 p-2 text-indigo-700"><Sparkles size={18} /></div>
          <div>
            <div className="text-xs font-black uppercase tracking-[0.22em] text-indigo-800">Codex Transformation Engine</div>
            <p className="mt-1 text-sm text-slate-600 max-w-3xl">Executa la consulta original, la versió compatible amb Codex i compara el resultat amb normalització configurable.</p>
            <p className="mt-1 text-[11px] text-slate-500">Perfil Oracle actiu: <span className="font-mono text-slate-700">{executionProfile || 'per defecte'}</span></p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setShowLogs((current) => !current)} className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-indigo-700 hover:bg-indigo-50">
            {showLogs ? 'Amagar traces' : `Veure traces (${logs.length})`}
          </button>
          <button type="button" onClick={copyToClipboard} disabled={!rightSql || transforming} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide ${copied ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-50'}`}>
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copiat' : 'Copiar sortida'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wide text-slate-600 ml-1">Entrada (Oracle SQL Developer)</label>
          <div className="relative">
            <SQLEditor value={leftSql} onChange={(value) => { setLeftSql(value); setComparison(null); setAiAnalysis(null); }} />
            <div className="absolute top-2 right-2 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[9px] font-mono uppercase text-slate-200">Native</div>
          </div>
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <label className="text-[10px] font-bold uppercase tracking-wide text-indigo-700 ml-1">Sortida (Codex Compatible)</label>
            <button type="button" onClick={() => transformSql(leftSql)} disabled={transforming || !leftSql.trim()} className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">
              {transforming ? 'Transformant...' : 'Regenerar sortida'}
            </button>
          </div>
          <div className="relative">
            {transforming ? (
              <div className="flex h-[190px] items-center justify-center rounded-xl border border-indigo-200 bg-white"><Loader2 size={24} className="animate-spin text-indigo-400" /></div>
            ) : (
              <>
                <SQLEditor value={rightSql} onChange={(value) => { setRightSql(value); setComparison(null); setAiAnalysis(null); }} />
                <div className="absolute top-2 right-2 rounded-md border border-indigo-200 bg-indigo-100 px-2 py-1 text-[9px] font-mono uppercase text-indigo-700">Codex-Ready</div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">Entorn d'execució</div>
        <div className="mt-1 text-xs text-slate-500">Selecciona el perfil Oracle sobre el qual s'executaran les consultes i la comparació.</div>
        <div className="mt-3 max-w-xs">
          <label className="block">
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Perfil Oracle</span>
            <select
              value={executionProfile}
              onChange={(event) => setExecutionProfile(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
              aria-label="Entorn d'execució"
            >
              {!availableProfiles.length && (
                <option value="">{selectedProfile || 'Sense perfil'}</option>
              )}
              {availableProfiles.map((profile) => (
                <option key={profile} value={profile}>{profile}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[1.2fr,0.8fr] gap-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">Paràmetres detectats</div>
          <div className="mt-1 text-xs text-slate-500">Edita la finestra temporal o qualsevol altre bind abans d'executar.</div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {detectedVariables.length === 0 && <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-500">No s'han detectat variables `&VARIABLE` a les dues consultes.</div>}
            {detectedVariables.map((name) => (
              <label key={name} className="block">
                <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-slate-500">{name}</span>
                <input value={variables[name] ?? ''} onChange={(event) => setVariables((current) => ({ ...current, [name]: event.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100" placeholder={`Valor per ${name}`} />
              </label>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">Opcions de comparació</div>
          <div className="mt-1 text-xs text-slate-500">Normalització prèvia a la comparació de metadades i contingut.</div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-700">
            {[
              ['trimWhitespace', 'Trim d’espais'],
              ['nullEqualsEmpty', 'Null = buit'],
              ['ignoreCase', 'Ignorar majúscules'],
              ['ignoreRowOrder', 'Ignorar ordre'],
              ['normalizeDates', 'Normalitzar dates'],
              ['normalizeNumbers', 'Normalitzar números'],
              ['compareByColumnName', 'Per nom de columna'],
              ['normalizeColumnAliases', 'Normalitzar àlies'],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <input type="checkbox" checked={!!options[key]} onChange={(event) => setOptions((current) => ({ ...current, [key]: event.target.checked }))} />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="block">
              <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Límit mostra</span>
              <input type="number" min="10" max="500" value={options.previewLimit} onChange={(event) => setOptions((current) => ({ ...current, previewLimit: event.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Mostra diff</span>
              <input type="number" min="1" max="100" value={options.sampleLimit} onChange={(event) => setOptions((current) => ({ ...current, sampleLimit: event.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-slate-500">Clau de comparació</span>
              <input value={options.comparisonKey} onChange={(event) => setOptions((current) => ({ ...current, comparisonKey: event.target.value }))} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100" placeholder="ID, OWNER" />
            </label>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => runExecute('left')} disabled={busyAction !== '' || !leftSql.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
          {busyAction === 'execute-left' ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          Executar SQL Developer
        </button>
        <button type="button" onClick={() => runExecute('right')} disabled={busyAction !== '' || !rightSql.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
          {busyAction === 'execute-right' ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          Executar Codex Compatible
        </button>
        <button type="button" onClick={runExecuteBoth} disabled={busyAction !== '' || !leftSql.trim() || !rightSql.trim()} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:opacity-50">
          {busyAction === 'execute-both' ? <Loader2 size={16} className="animate-spin" /> : <Database size={16} />}
          Executar ambdues
        </button>
        <button type="button" onClick={runCompare} disabled={busyAction !== '' || !leftSql.trim() || !rightSql.trim()} className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-bold text-amber-800 disabled:opacity-50">
          {busyAction === 'compare' ? <Loader2 size={16} className="animate-spin" /> : <ArrowLeftRight size={16} />}
          Comparar resultats
        </button>
        <button type="button" onClick={runAiAnalysis} disabled={busyAction !== '' || !leftSql.trim() || !rightSql.trim()} className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50 px-4 py-2 text-sm font-bold text-violet-800 disabled:opacity-50">
          {busyAction === 'ai' ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
          Analitzar diferències amb IA
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ResultPanel title="Resultat SQL Developer" subtitle="Execució de la consulta original sanejada per Oracle." result={leftResult} loading={busyAction === 'execute-left' || busyAction === 'execute-both' || busyAction === 'compare'} tone="left" exportPrefix="sql-developer-result" />
        <ResultPanel title="Resultat Codex Compatible" subtitle="Execució de la consulta compatible amb el motor Codex." result={rightResult} loading={busyAction === 'execute-right' || busyAction === 'execute-both' || busyAction === 'compare'} tone="right" exportPrefix="codex-compatible-result" />
      </div>

      <div className="mt-4 space-y-4">
        <DiffPanel comparison={comparison} leftResult={leftResult} rightResult={rightResult} />
        <AnalysisPanel analysis={aiAnalysis} loading={busyAction === 'ai'} />
      </div>

      {showLogs && logs.length > 0 && (
        <div className="mt-4 border-t border-indigo-100 pt-4">
          <div className="mb-2 flex items-center gap-2">
            <Terminal size={12} className="text-slate-500" />
            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Traces de transformació pas a pas</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {logs.map((log, index) => (
              <div key={index} className="rounded-xl border border-slate-200 bg-white p-3 text-[11px] font-mono shadow-sm">
                <div className="mb-2 border-b border-slate-100 pb-1 text-indigo-700">{log.step}</div>
                <div className={log.changed ? 'text-emerald-700' : 'italic text-slate-500'}>{log.changed ? 'Canvis aplicats' : 'Sense canvis'}</div>
                {log.details && <div className="mt-1 text-[10px] text-slate-500">{log.details}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
