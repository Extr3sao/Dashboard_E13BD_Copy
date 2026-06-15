/**
 * ChecksAdminView.jsx
 * ===================
 * Pantalla de GestiÃ³ de Consultes: CRUD de checks d'auditoria Post-CRQ.
 * Permet veure, crear, editar (amb versionat SQL i diff), eliminar,
 * i forÃ§ar la regeneraciÃ³ de l'explicaciÃ³ IA de cada check.
 *
 * PatrÃ³: iguala l'estÃ¨tica glassmorphism/dark del dashboard existent.
/**
 * ChecksAdminView.jsx
 * ===================
 * Pantalla de GestiÃ³ de Consultes: CRUD de checks d'auditoria Post-CRQ.
 * Permet veure, crear, editar (amb versionat SQL i diff), eliminar,
 * i forÃ§ar la regeneraciÃ³ de l'explicaciÃ³ IA de cada check.
 *
 * PatrÃ³: iguala l'estÃ¨tica glassmorphism/dark del dashboard existent.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import {
  Plus, Pencil, Trash2, RefreshCcw, AlertTriangle, CheckCircle,
  Clock, Brain, ChevronDown, ChevronUp, History, Sparkles, Terminal,
  Database, X, Save, Eye, RotateCcw, Info, Loader2, Search, AlertCircle, RefreshCw, Copy, Check,
  Play, ArrowLeftRight, Download
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import PostCrqOperationalDocsPanel from '../components/post-crq/PostCrqOperationalDocsPanel.jsx';
import SQLCodexWorkbench from '../components/checks/SQLCodexWorkbench.jsx';

const API = '/api/checks';
const MARKDOWN_API = '/api/audit/post-crq/checks';
const VALIDATE_API = `${API}/validate-preview`;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeUiText(value) {
  if (value == null) return '';
  const text = String(value);
  if (!/[ÃƒÃ‚Ã¢ï¿½]/.test(text)) return text;
  try {
    return decodeURIComponent(escape(text));
  } catch {
    return text;
  }
}

function normalizeSeverity(value) {
  const normalized = normalizeUiText(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  if (normalized.includes('CRIT')) return 'Crític';
  if (normalized.includes('MITJ')) return 'Mitjà';
  if (normalized.includes('BAIX')) return 'Baix';
  return normalizeUiText(value) || 'Mitjà';
}

function formatValidationWindow(timeFilter) {
  if (!timeFilter) return '';
  const start = normalizeUiText(timeFilter.range_start_at || timeFilter.start_date || '');
  const end = normalizeUiText(timeFilter.range_end_at || timeFilter.end_date || '');
  if (!start || !end) return '';
  return `${start} -> ${end}`;
}

function toDateTimeLocalValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function buildDefaultValidationWindow() {
  const end = new Date();
  const start = new Date(end.getTime() - (24 * 60 * 60 * 1000));
  return {
    startAt: toDateTimeLocalValue(start),
    endAt: toDateTimeLocalValue(end),
  };
}

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

function buildDefaultEngineVariables() {
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
  sqlTexts
    .filter(Boolean)
    .forEach((sql) => {
      const matches = String(sql).match(/&([A-Z_][A-Z0-9_]*)/gi) || [];
      matches.forEach((rawMatch) => {
        const normalized = rawMatch.replace('&', '').toUpperCase();
        if (!detected.includes(normalized)) detected.push(normalized);
      });
    });
  return detected;
}

function mergeDetectedVariables(variableNames, currentValues) {
  const next = { ...currentValues };
  variableNames.forEach((name) => {
    if (typeof next[name] === 'undefined') next[name] = '';
  });
  return next;
}

function formatComparisonState(comparison) {
  if (!comparison) return { label: 'Sense comparar', cls: 'bg-slate-100 text-slate-700 border-slate-200' };
  if (comparison.status === 'match') return { label: 'Coincideixen', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
  if (comparison.status === 'warning') return { label: 'Coincideixen amb matisos', cls: 'bg-amber-50 text-amber-700 border-amber-200' };
  return { label: 'No coincideixen', cls: 'bg-rose-50 text-rose-700 border-rose-200' };
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

// ─── SQL Codex Playground ───────────────────────────────────────────────────

function SQLCodexPlayground({ originalSql }) {
  const [transformedSql, setTransformedSql] = useState('');
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  const transformSql = async () => {
    setLoading(true);
    try {
      const response = await axios.post('/api/checks/transform-sql', {
        sql_text: originalSql,
        debug: true
      });
      setTransformedSql(response.data.transformed_sql);
      setLogs(response.data.logs || []);
    } catch (err) {
      console.error('Error transformant SQL:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (originalSql) transformSql();
  }, [originalSql]);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(transformedSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-2 mb-4 bg-indigo-500/5 border border-indigo-500/20 rounded-2xl p-4 shadow-inner overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300">
            <Sparkles size={16} />
          </div>
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-200">Codex Transformation Engine</span>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setShowLogs(!showLogs)}
            className="text-[10px] font-bold uppercase text-indigo-400 hover:text-indigo-200 transition-colors"
          >
            {showLogs ? 'Amagar traces' : `Veure traces d'anàlisi (${logs.length})`}
          </button>
          <button
            onClick={copyToClipboard}
            disabled={!transformedSql || loading}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-[10px] font-black uppercase transition-all
              ${copied ? 'bg-green-500/20 text-green-300 border border-green-500/30' : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30'}`}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copiat!' : 'Copiar per a Codex'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold text-gray-500 uppercase ml-1">Entrada (Oracle SQL Developer)</label>
          <div className="relative">
            <SQLEditor value={originalSql} onChange={() => {}} readOnly height="160px" />
            <div className="absolute top-2 right-2 p-1.5 rounded-md bg-black/60 text-[9px] font-mono text-gray-400 border border-white/5 uppercase">Native</div>
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold text-indigo-400 uppercase ml-1">Sortida (Codex Compatible)</label>
          <div className="relative">
            {loading ? (
              <div className="h-[160px] w-full bg-black/40 border border-indigo-500/20 rounded-xl flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-indigo-500/40" />
              </div>
            ) : (
              <>
                <textarea
                  value={transformedSql}
                  readOnly
                  style={{ height: '160px', fontFamily: 'Consolas, monospace', fontSize: '13px' }}
                  className="w-full bg-black/60 border border-indigo-500/30 text-indigo-200 rounded-xl p-3 outline-none leading-relaxed shadow-lg"
                />
                <div className="absolute top-2 right-2 p-1.5 rounded-md bg-indigo-500/20 text-[9px] font-mono text-indigo-300 border border-indigo-500/30 uppercase">Codex-Ready</div>
              </>
            )}
          </div>
        </div>
      </div>

      {showLogs && logs.length > 0 && (
        <div className="mt-4 pt-4 border-t border-indigo-500/10">
          <div className="flex items-center gap-2 mb-2">
            <Terminal size={12} className="text-gray-500" />
            <span className="text-[10px] font-bold uppercase text-gray-500">Traces de transformació pas a pas</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {logs.map((log, i) => (
              <div key={i} className="text-[10px] font-mono bg-black/30 border border-white/5 p-2 rounded-lg flex flex-col gap-1">
                <span className="text-indigo-400 border-b border-indigo-500/10 pb-1 mb-1">{log.step}</span>
                <span className={log.changed ? 'text-green-400' : 'text-gray-500 italic'}>
                  {log.changed ? '✓ Canvis aplicats' : 'Sense canvis'}
                </span>
                {log.details && <span className="text-gray-400 text-[9px]">{log.details}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function buildMarkdownMap(payload) {
  return (Array.isArray(payload?.checks) ? payload.checks : []).reduce((acc, item) => {
    if (item?.check_id) {
      acc[String(item.check_id).trim().toUpperCase()] = {
        check_id: String(item.check_id).trim().toUpperCase(),
        title: normalizeUiText(item.title || ''),
        criteri: normalizeUiText(item.criteri || ''),
        sql: item.sql || '',
      };
    }
    return acc;
  }, {});
}

function mergeCheckWithMarkdown(check, markdownCheck) {
  const normalized = {
    ...check,
    check_id: String(check?.check_id || '').trim().toUpperCase(),
    titol: normalizeUiText(check?.titol || ''),
    severitat_base: normalizeSeverity(check?.severitat_base),
    context_check: normalizeUiText(check?.context_check || ''),
    sql_vigent: check?.sql_vigent || '',
  };

  if (!markdownCheck) {
    return {
      ...normalized,
      sql_source: 'sqlite',
      markdown_sql: '',
      markdown_title: '',
      markdown_context_check: '',
    };
  }

  return {
    ...normalized,
    titol: markdownCheck.title || normalized.titol,
    context_check: markdownCheck.criteri || normalized.context_check,
    sql_vigent: markdownCheck.sql || normalized.sql_vigent,
    markdown_sql: markdownCheck.sql || '',
    markdown_title: markdownCheck.title || '',
    markdown_context_check: markdownCheck.criteri || '',
    sql_source: 'markdown',
  };
}

function buildValidationSignature(form, selectedProfile) {
  return JSON.stringify({
    check_id: String(form.check_id || '').trim().toUpperCase(),
    titol: String(form.titol || '').trim(),
    severitat_base: normalizeSeverity(form.severitat_base),
    parametres: String(form.parametres || '').trim(),
    tipus: String(form.tipus || 'SQL').trim().toUpperCase(),
    ordre: Number(form.ordre || 0),
    context_check: String(form.context_check || '').trim(),
    ai_enabled: Number(form.ai_enabled || 0),
    sql_text: String(form.sql_text || ''),
    profile: String(selectedProfile || ''),
  });
}

function buildCreatePayload(form) {
  return {
    check_id: String(form.check_id || '').trim().toUpperCase(),
    titol: String(form.titol || '').trim(),
    severitat_base: normalizeSeverity(form.severitat_base),
    parametres: String(form.parametres || '').trim() || 'days_back',
    tipus: String(form.tipus || 'SQL').trim().toUpperCase(),
    ordre: Number(form.ordre || 0),
    context_check: String(form.context_check || '').trim(),
    ai_enabled: Number(form.ai_enabled || 0),
    sql_text: String(form.sql_text || ''),
  };
}

function buildUpdatePayload(form) {
  return {
    titol: String(form.titol || '').trim(),
    severitat_base: normalizeSeverity(form.severitat_base),
    parametres: String(form.parametres || '').trim() || 'days_back',
    context_check: String(form.context_check || '').trim(),
    ai_enabled: Number(form.ai_enabled || 0),
    sql_text: String(form.sql_text || ''),
  };
}

const SEVERITAT_COLORS = {
  'Crític': 'bg-red-100 text-red-700 border-red-200 shadow-[0_0_10px_rgba(185,28,28,0.05)] font-extrabold',
  'Mitjà':  'bg-orange-100 text-orange-700 border-orange-200 shadow-[0_0_2px_rgba(194,65,12,0.05)]',
  'Baix':   'bg-blue-50 text-blue-700 border-blue-100',
};
const SEVERITAT_OPTIONS = ['Crític', 'Mitjà', 'Baix'];
const TIPUS_OPTIONS = ['SQL', 'PLSQL'];

const ESTAT_EXPL_BADGE = {
  VIGENT:   { cls: 'bg-green-100 text-green-700 border-green-200', label: 'IA vigent' },
  PENDENT:  { cls: 'bg-orange-50 text-orange-600 border-orange-100', label: "Pendent d'execució" },
  ERROR:    { cls: 'bg-red-100 text-red-700 border-red-200', label: 'Error IA' },
  OBSOLETA: { cls: 'bg-gray-100 text-gray-500 border-gray-200', label: 'Obsoleta' },
};

const ESTAT_SYNC_BADGE = {
  OK:      { cls: 'bg-green-100 text-green-700 border-green-200', label: 'Sync OK' },
  PENDENT: { cls: 'bg-orange-50 text-orange-600 border-orange-100', label: 'Sync pendent' },
  ERROR:   { cls: 'bg-red-100 text-red-700 border-red-200', label: 'Sync error' },
};

const sevBadge = (sev) => {
  const cls = SEVERITAT_COLORS[sev] || 'bg-gray-500/20 text-gray-300';
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls}`}>{sev}</span>;
};

const explBadge = (estat) => {
  const { cls, label } = ESTAT_EXPL_BADGE[estat] || ESTAT_EXPL_BADGE.PENDENT;
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${cls}`}>{label}</span>;
};

const syncBadge = (estat) => {
  const { cls, label } = ESTAT_SYNC_BADGE[estat] || ESTAT_SYNC_BADGE.PENDENT;
  return <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${cls}`}>{label}</span>;
};

// ─── SQL Editor mínim ──────────────────────────────────────────────────────────

function SQLEditor({ value, onChange, readOnly = false, height = '300px' }) {
  const textareaRef = useRef(null);
  // Tab → insereix 2 espais
  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = textareaRef.current;
      const start = ta.selectionStart;
      const end   = ta.selectionEnd;
      const newVal = value.substring(0, start) + '  ' + value.substring(end);
      onChange(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  };
  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      readOnly={readOnly}
      spellCheck={false}
      style={{ height, fontFamily: 'Consolas, "Courier New", monospace', fontSize: '13px' }}
      className="w-full bg-black/40 border border-white/10 text-green-300 rounded-xl p-3
                 resize-y outline-none focus:ring-1 focus:ring-green-400/50 leading-relaxed"
    />
  );
}

// ─── Diff visual simple ────────────────────────────────────────────────────────

function DiffViewer({ anterior, nou }) {
  if (!anterior) return <p className="text-xs text-gray-500 italic">Primera versió — no hi ha diff.</p>;
  const liniesAnt = anterior.split('\n');
  const liniesNou = nou.split('\n');
  const setAnt = new Set(liniesAnt);
  const setNou = new Set(liniesNou);

  const eliminades = liniesAnt.filter(l => !setNou.has(l));
  const afegides   = liniesNou.filter(l => !setAnt.has(l));

  if (!eliminades.length && !afegides.length) {
    return <p className="text-xs text-green-400">Sense canvis detectats.</p>;
  }

  return (
    <div className="text-xs font-mono space-y-1">
      {eliminades.map((l, i) => (
        <div key={`-${i}`} className="bg-red-500/10 text-red-300 px-2 py-0.5 rounded">
          <span className="text-red-500 mr-1">−</span>{l || '(línia buida)'}
        </div>
      ))}
      {afegides.map((l, i) => (
        <div key={`+${i}`} className="bg-green-500/10 text-green-300 px-2 py-0.5 rounded">
          <span className="text-green-400 mr-1">+</span>{l || '(línia buida)'}
        </div>
      ))}
    </div>
  );
}

// ─── Modal d'edició/creació ──────────────────────────────────────────────────

function ValidationPreview({ result, selectedProfile }) {
  if (!result) return null;
  const validation = result.validation || {};
  const aiPreview = result.ai_preview || {};
  const columns = Array.isArray(validation.columns) ? validation.columns : [];
  const rows = Array.isArray(validation.rows) ? validation.rows : [];
  const validationOk = result.status === 'ok' && validation.status === 'ok';
  const validationWindow = formatValidationWindow(result.time_filter);

  return (
    <div className="space-y-4">
      <div className={`rounded-xl border px-4 py-3 text-sm shadow-sm ${validationOk ? 'border-emerald-300 bg-emerald-50 text-emerald-950' : 'border-rose-300 bg-rose-50 text-rose-900'}`}>
        {validationOk
          ? `Validació correcta sobre ${selectedProfile || result.profile || 'Oracle'}. ${validation.row_count ?? 0} files detectades.`
          : `La prevalidació ha fallat sobre ${selectedProfile || result.profile || 'Oracle'}.`}
      </div>

      {validationWindow && (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950 shadow-sm">
          <p className="text-[11px] font-bold uppercase tracking-wide text-sky-700">Finestra temporal utilitzada</p>
          <p className="mt-1 font-mono text-[12px]">{validationWindow}</p>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-700">Execució Oracle</p>
            {validationOk && <span className="text-[11px] font-semibold text-emerald-800">{validation.preview_row_count ?? 0}/{validation.row_count ?? 0} files mostrades</span>}
          </div>
          {validationOk ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 gap-2 text-xs text-slate-800 md:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">Durada: {validation.duration_ms ?? 0} ms</div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">Filtre temporal SQL: {validation.time_filter_pushed ? 'sí' : 'no'}</div>
              </div>
              <div className="overflow-auto rounded-lg border border-slate-300">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-100 text-slate-800">
                    <tr>{columns.map((column) => <th key={column} className="px-2 py-2 text-left font-bold">{column}</th>)}</tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 ? (
                      <tr><td className="px-2 py-3 text-slate-700" colSpan={columns.length || 1}>La consulta ha executat correctament però no ha retornat files.</td></tr>
                    ) : null}
                    {rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="border-t border-slate-200">{columns.map((column) => <td key={`${rowIndex}-${column}`} className="px-2 py-2 align-top text-slate-900">{String(row?.[column] ?? '')}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <p className="mb-1 text-[11px] font-bold uppercase text-slate-700">SQL executat</p>
                <pre className="max-h-48 overflow-auto rounded-xl bg-slate-950 border border-slate-800 p-3 text-[11px] text-emerald-200 whitespace-pre-wrap">{validation.rendered_sql || validation.executed_sql}</pre>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-medium text-red-800">{validation.error || "La consulta no s'ha pogut executar correctament."}</p>
              <pre className="max-h-48 overflow-auto rounded-xl bg-red-50 border border-red-200 p-3 text-[11px] text-red-700 whitespace-pre-wrap">{validation.rendered_sql || validation.executed_sql}</pre>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <p className="text-xs font-bold uppercase text-slate-700">Previsualització IA</p>
          {aiPreview.status === 'ok' ? (
            <div className="mt-3 space-y-3 text-sm text-slate-900">
              <div className="grid grid-cols-1 gap-2 text-xs text-slate-800 md:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">Model: {aiPreview.model_utilitzat}</div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">Confiança: {Math.round((aiPreview.nivell_confianca || 0) * 100)}%</div>
              </div>
              <div><p className="text-[11px] font-bold uppercase text-slate-700">Resum executiu</p><p>{normalizeUiText(aiPreview.resum_executiu)}</p></div>
              <div><p className="text-[11px] font-bold uppercase text-slate-700">Explicació funcional</p><p>{normalizeUiText(aiPreview.explicacio_funcional)}</p></div>
              <div><p className="text-[11px] font-bold uppercase text-slate-700">Explicació tècnica</p><p>{normalizeUiText(aiPreview.explicacio_tecnica)}</p></div>
              {aiPreview.explicacio_preview_text ? (
                <div>
                  <p className="text-[11px] font-bold uppercase text-slate-700">Informe ampliat del check</p>
                  <pre className="mt-1 max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-[12px] leading-6 text-slate-900">{normalizeUiText(aiPreview.explicacio_preview_text)}</pre>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-700">{normalizeUiText(aiPreview.error || "La previsualització IA s'executarà després d'una validació Oracle correcta.")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function CheckModal({ check, onClose, onSaved, selectedProfile, profiles = [] }) {
  const isNou = !check;
  const [form, setForm] = useState({
    check_id:      check?.check_id     || '',
    titol:         check?.titol        || '',
    severitat_base: check?.severitat_base || 'Mitjà',
    parametres:    check?.parametres   || 'days_back',
    tipus:         check?.tipus        || 'SQL',
    ordre:         check?.ordre        || 0,
    context_check: check?.context_check|| '',
    ai_enabled:    check?.ai_enabled   || 0,
    sql_text:      check?.sql_vigent   || '',
  });
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError]   = useState('');
  const [showDiff, setShowDiff] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [validatedSignature, setValidatedSignature] = useState('');
  const availableProfiles = Array.isArray(profiles) ? profiles.filter(Boolean) : [];
  const [validationProfile, setValidationProfile] = useState(selectedProfile || availableProfiles[0] || '');
  const [validationWindow, setValidationWindow] = useState(() => buildDefaultValidationWindow());

  useEffect(() => {
    if (availableProfiles.length === 0) {
      setValidationProfile(selectedProfile || '');
      return;
    }
    setValidationProfile((current) => (
      current && availableProfiles.includes(current)
        ? current
        : (selectedProfile && availableProfiles.includes(selectedProfile) ? selectedProfile : availableProfiles[0])
    ));
  }, [availableProfiles, selectedProfile]);

  const currentSignature = JSON.stringify({
    ...JSON.parse(buildValidationSignature(form, validationProfile)),
    validation_start_at: validationWindow.startAt,
    validation_end_at: validationWindow.endAt,
  });

  useEffect(() => {
    if (validatedSignature && validatedSignature !== currentSignature) {
      setValidationResult(null);
      setValidatedSignature('');
    }
  }, [currentSignature, validatedSignature]);

  const handleChange = (field, val) => {
    setForm(f => ({ ...f, [field]: val }));
    setError('');
  };

  const handleValidationWindowChange = (field, value) => {
    setValidationWindow((current) => ({ ...current, [field]: value }));
    setError('');
  };

  const handleValidate = async () => {
    const payload = buildCreatePayload(form);
    if (!payload.check_id || !payload.titol || !payload.sql_text.trim()) {
      setError("Cal indicar check ID, títol i consulta SQL abans de validar.");
      return;
    }
    if (!validationWindow.startAt || !validationWindow.endAt) {
      setError("Cal indicar l'inici i el final de la finestra de prevalidació.");
      return;
    }

    setError('');
    setValidating(true);
    try {
      const response = await axios.post(VALIDATE_API, {
        ...payload,
        profile: validationProfile || '',
        validation_start_at: validationWindow.startAt,
        validation_end_at: validationWindow.endAt,
      });
      setValidationResult(response.data);
      setValidatedSignature(currentSignature);
    } catch (err) {
      setValidationResult(null);
      setValidatedSignature('');
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setValidating(false);
    }
  };

  const canSave = validatedSignature === currentSignature
    && validationResult?.status === 'ok'
    && validationResult?.validation?.status === 'ok'
    && validationResult?.ai_preview?.status !== 'error';

  const handleSave = async () => {
    const payload = buildCreatePayload(form);
    if (!payload.check_id) return setError("El check_id és obligatori.");
    if (!payload.titol) return setError("El títol és obligatori.");
    if (!payload.sql_text.trim()) return setError("La consulta SQL no pot estar buida.");
    if (!canSave) return setError("Cal validar la versió actual del formulari abans de desar.");
    setError('');
    setSaving(true);
    try {
      if (isNou) {
        await axios.post(API, payload);
      } else {
        await axios.put(`${API}/${payload.check_id}`, buildUpdatePayload(form));
      }
      await onSaved();
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="glass-card w-full max-w-3xl max-h-[90vh] overflow-y-auto p-8 flex flex-col gap-6"
      >
        {/* Capçalera */}
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-bold flex items-center gap-2">
            <Database size={20} className="text-primary" />
            {isNou ? 'Nou Check' : `Editar ${check.check_id}`}
          </h3>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-300 text-sm rounded-xl p-3 flex gap-2 items-start">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {/* Camps del formulari */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold uppercase text-gray-400">Check ID *</label>
            <input
              type="text" value={form.check_id} disabled={!isNou}
              onChange={e => handleChange('check_id', e.target.value.toUpperCase())}
              placeholder="CHECK_14"
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold uppercase text-gray-400">Ordre</label>
            <input
              type="number" value={form.ordre}
              onChange={e => handleChange('ordre', e.target.value)}
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex flex-col gap-1.5 md:col-span-2">
            <label className="text-xs font-bold uppercase text-gray-400">Títol *</label>
            <input
              type="text" value={form.titol}
              onChange={e => handleChange('titol', e.target.value)}
              placeholder="Ús de WHEN OTHERS THEN NULL"
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold uppercase text-gray-400">Severitat base *</label>
            <select
              value={form.severitat_base}
              onChange={e => handleChange('severitat_base', e.target.value)}
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary"
            >
              {SEVERITAT_OPTIONS.map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold uppercase text-gray-400">Tipus</label>
            <select
              value={form.tipus}
              onChange={e => handleChange('tipus', e.target.value)}
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary"
            >
              {TIPUS_OPTIONS.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold uppercase text-gray-400">Activació IA</label>
            <button
              onClick={() => handleChange('ai_enabled', form.ai_enabled === 1 ? 0 : 1)}
              className={`h-10 rounded-lg border px-3 text-sm font-bold transition-all flex items-center justify-between
                ${form.ai_enabled === 1 
                  ? 'bg-purple-500/20 border-purple-500/40 text-purple-300 shadow-[0_0_15px_rgba(168,85,247,0.15)]' 
                  : 'bg-black/30 border-white/10 text-gray-500'}`}
            >
              <div className="flex items-center gap-2">
                <Brain size={16} className={form.ai_enabled === 1 ? 'animate-pulse' : ''} />
                {form.ai_enabled === 1 ? 'ANÀLISI IA ACTIU' : 'IA DESACTIVADA'}
              </div>
              <div className={`w-8 h-4 rounded-full relative transition-colors ${form.ai_enabled === 1 ? 'bg-purple-500' : 'bg-gray-600'}`}>
                <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${form.ai_enabled === 1 ? 'left-[18px]' : 'left-[2px]'}`} />
              </div>
            </button>
          </div>
          <div className="flex flex-col gap-1.5 md:col-span-2">
            <label className="text-xs font-bold uppercase text-gray-400">Paràmetres</label>
            <input
              type="text" value={form.parametres}
              onChange={e => handleChange('parametres', e.target.value)}
              placeholder="days_back, schema_filter"
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm
                         outline-none focus:ring-1 focus:ring-primary"
            />
            <p className="text-[11px] text-slate-500">
              Prevalidació temporal: pots fer servir <span className="font-mono">START_AT</span> i <span className="font-mono">END_AT</span>. Per defecte s'usa l'últim dia.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="checks-validation-profile" className="text-xs font-bold uppercase text-gray-400">Entorn prevalidació</label>
            <select
              id="checks-validation-profile"
              value={validationProfile}
              onChange={(e) => {
                setValidationProfile(e.target.value);
                setError('');
              }}
              className="h-10 rounded-lg bg-black/30 border border-white/10 px-3 text-sm outline-none focus:ring-1 focus:ring-primary"
            >
              {availableProfiles.length === 0 ? (
                <option value="">{selectedProfile || 'Sense perfil'}</option>
              ) : (
                availableProfiles.map((profile) => <option key={profile} value={profile}>{profile}</option>)
              )}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="checks-validation-start" className="text-xs font-bold uppercase text-gray-400">Inici prevalidació</label>
            <input
              id="checks-validation-start"
              type="datetime-local"
              value={validationWindow.startAt}
              onChange={e => handleValidationWindowChange('startAt', e.target.value)}
              className="h-10 rounded-lg bg-black/20 border border-white/10 px-3 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="checks-validation-end" className="text-xs font-bold uppercase text-gray-400">Final prevalidació</label>
            <input
              id="checks-validation-end"
              type="datetime-local"
              value={validationWindow.endAt}
              onChange={e => handleValidationWindowChange('endAt', e.target.value)}
              className="h-10 rounded-lg bg-black/20 border border-white/10 px-3 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex flex-col gap-1.5 md:col-span-2">
            <label className="text-xs font-bold uppercase text-gray-400">Context del check</label>
            <textarea
              value={form.context_check}
              onChange={e => handleChange('context_check', e.target.value)}
              rows={2}
              placeholder="Descripció breu de la finalitat del check (per a la IA)..."
              className="rounded-xl bg-black/30 border border-white/10 px-3 py-2 text-sm resize-y
                         outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* Editor SQL */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs font-bold uppercase text-gray-400">Consulta SQL/PL-SQL *</label>
              {!isNou && check?.sql_source === 'markdown' && (
                <p className="mt-1 text-[11px] text-emerald-300">
                  Mostrant la consulta activa de <code className="font-mono">auditoria_post_crq.md</code>.
                </p>
              )}
            </div>
            {!isNou && check?.sql_vigent && (
              <button
                onClick={() => setShowDiff(v => !v)}
                className="text-xs text-primary flex items-center gap-1 hover:underline"
              >
                {showDiff ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {showDiff ? 'Ocultar diff' : 'Veure diff vs. versió actual'}
              </button>
            )}
          </div>
          <SQLEditor value={form.sql_text} onChange={v => handleChange('sql_text', v)} />
          {showDiff && !isNou && (
            <div className="bg-black/30 border border-white/10 rounded-xl p-4">
              <p className="text-xs font-bold uppercase text-gray-400 mb-2">Diff vs. versió vigent:</p>
              <DiffViewer anterior={check.sql_vigent} nou={form.sql_text} />
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-indigo-200 bg-white p-4 space-y-4 shadow-sm">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-bold text-slate-900">Prevalidació obligatòria abans de desar</p>
              <p className="mt-1 text-xs text-slate-700">La validació executa la consulta a Oracle amb el flux Post-CRQ real i genera una previsualització IA sense persistir cap canvi.</p>
              <p className="mt-2 text-xs text-slate-600">
                Finestra actual: <span className="font-mono text-slate-800">{validationWindow.startAt || 'sense inici'} -&gt; {validationWindow.endAt || 'sense final'}</span>
              </p>
            </div>
            <button
              type="button"
              onClick={handleValidate}
              disabled={validating}
              aria-busy={validating ? 'true' : 'false'}
              className="px-4 py-2 rounded-xl bg-indigo-700 border border-indigo-800 text-white text-sm font-bold hover:bg-indigo-800 disabled:opacity-60 disabled:cursor-wait flex items-center gap-2 shadow-sm"
            >
              {validating ? <Loader2 size={16} className="animate-spin" /> : <Brain size={16} />}
              {validating ? 'Validant consulta i previsualització IA...' : 'Validar consulta i previsualitzar IA'}
            </button>
          </div>

          {validating && (
            <div className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950" role="status" aria-live="polite">
              <Loader2 size={16} className="mt-0.5 shrink-0 animate-spin text-sky-700" />
              <div>
                <p className="font-semibold">Executant prevalidació a Oracle</p>
                <p className="mt-1 text-xs text-sky-800">S'està executant la consulta i preparant la previsualització IA. Aquest procés pot trigar uns segons.</p>
              </div>
            </div>
          )}

          {!canSave && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-700" />
              Cal executar la validació per a la versió actual del formulari abans de poder desar.
            </div>
          )}

          <ValidationPreview result={validationResult} selectedProfile={validationProfile} />
        </div>

        {/* Accions */}
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-6 py-2 rounded-xl border border-white/10 text-sm hover:bg-white/5">
            Cancel·lar
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave || saving}
            className="px-6 py-2 rounded-xl bg-primary text-white text-sm font-bold
                       hover:bg-primary/80 disabled:opacity-50 flex items-center gap-2"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {isNou ? 'Crear i Regenerar IA' : 'Desar i Regenerar IA'}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Detall / Historial del check ─────────────────────────────────────────────

function CheckDetailPanel({ check, onClose, onRegenerate }) {
  const [history, setHistory] = useState([]);
  const [syncStatus, setSyncStatus] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [regnerating, setRegenerating] = useState(false);
  const [tab, setTab] = useState('sql');

  useEffect(() => {
    const cid = check.check_id;
    axios.get(`${API}/${cid}/history`)
      .then(r => { setHistory(r.data); setLoadingHistory(false); })
      .catch(() => setLoadingHistory(false));
    axios.get(`${API}/${cid}/sync-status`)
      .then(r => setSyncStatus(r.data))
      .catch(() => {});
  }, [check.check_id]);

  const doRegenerarate = async () => {
    setRegenerating(true);
    try {
      await axios.post(`${API}/${check.check_id}/regenerate`);
      onRegenerate();
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 50 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 50 }}
      className="glass-card p-6 flex flex-col gap-5 h-full overflow-y-auto"
    >
      {/* Capçalera */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs text-gray-400 mb-0.5">{check.check_id}</p>
          <h3 className="font-bold text-sm leading-snug">{check.titol}</h3>
          <div className="flex items-center gap-2 mt-2">
            {sevBadge(check.severitat_base)}
            {explBadge(check.estat_explicacio)}
            {check.ai_enabled === 1 && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center gap-1 shadow-[0_0_10px_rgba(168,85,247,0.1)]">
                <Brain size={10} className="animate-pulse" /> IA ACTIVA
              </span>
            )}
          </div>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 shrink-0">
          <X size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 text-xs font-bold">
        {['sql', 'historial', 'sync'].map(t => (
          <button key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1 rounded-lg capitalize transition-all
              ${tab === t ? 'bg-primary text-white' : 'bg-white/5 hover:bg-white/10'}`}
          >
            {t === 'sql' ? 'SQL vigent' : t === 'historial' ? 'Historial' : 'Sync'}
          </button>
        ))}
      </div>

      {/* SQL vigent */}
      {tab === 'sql' && (
        <div>
          <p className="text-[11px] text-gray-500 mb-1">Versió {check.versio_vigent}</p>
          <SQLEditor value={check.sql_vigent || '-- (sense consulta vigent)'} onChange={() => {}} readOnly height="200px" />
          {check.context_check && (
            <div className="mt-3 bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 text-xs text-blue-200">
              <strong className="block mb-1">Context per a la IA:</strong>
              {check.context_check}
            </div>
          )}
        </div>
      )}

      {/* Historial */}
      {tab === 'historial' && (
        <div>
          {loadingHistory
            ? <p className="text-xs text-gray-500">Carregant historial...</p>
            : history.length === 0
              ? <p className="text-xs text-gray-500 italic">Sense versions registrades.</p>
              : (
                <div className="space-y-2">
                  {history.map(v => (
                    <div key={v.id}
                      className={`p-3 rounded-xl border text-xs flex flex-col gap-1
                        ${v.es_vigent ? 'border-primary/40 bg-primary/5' : 'border-white/5 bg-white/2'}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-bold">v{v.versio}</span>
                        {v.es_vigent && <span className="text-[10px] bg-primary/20 text-primary px-2 py-0.5 rounded-full">VIGENT</span>}
                      </div>
                      <div className="text-gray-400">{v.creat_per} · {new Date(v.creat_en).toLocaleString('ca-ES')}</div>
                      {v.estat_explicacio && (
                        <div className="flex items-center gap-2">
                          {explBadge(v.estat_explicacio)}
                          {v.model_utilitzat && <span className="text-gray-500">{v.model_utilitzat}</span>}
                          {v.nivell_confianca != null && (
                            <span className={`font-mono ${v.nivell_confianca >= 0.7 ? 'text-green-400' : 'text-yellow-400'}`}>
                              conf: {(v.nivell_confianca * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )
          }
        </div>
      )}

      {/* Sync */}
      {tab === 'sync' && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 mb-2">Estat de sincronització dels fitxers derivats:</p>
          {syncStatus.length === 0
            ? <p className="text-xs text-gray-500 italic">Sense informació de sync.</p>
            : syncStatus.map(s => (
              <div key={s.fitxer} className="flex items-center justify-between p-2 bg-white/5 rounded-lg text-xs">
                <span className="font-mono text-gray-300">{s.fitxer}</span>
                <div className="flex items-center gap-2">
                  {syncBadge(s.estat)}
                  {s.darrera_sync && <span className="text-gray-500">{new Date(s.darrera_sync).toLocaleString('ca-ES')}</span>}
                </div>
              </div>
            ))
          }
        </div>
      )}

      {/* Explicació Estat IA */}
      {check.estat_explicacio === 'PENDENT' && (
        <div className="bg-orange-500/5 border border-orange-500/20 rounded-xl p-3">
          <div className="flex items-center gap-2 text-orange-400 mb-1">
            <Clock size={14} />
            <span className="text-xs font-bold uppercase">Què significa "Pendent"?</span>
          </div>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Aquest check està activat per a IA, però encara no s'ha executat cap auditoria. 
            L'estat passarà a <span className="text-green-400">Vigent</span> automàticament quan 
            rebi dades d'Oracle en una execució real. També pots forçar-ho ara:
          </p>
        </div>
      )}

      {/* Botó Regenerar */}
      <button
        onClick={doRegenerarate}
        disabled={regnerating}
        className="w-full py-2.5 rounded-xl bg-purple-600/20 border border-purple-500/30 text-purple-200
                   hover:bg-purple-600/30 text-sm font-bold flex items-center justify-center gap-2
                   disabled:opacity-50 transition-all shadow-lg shadow-purple-900/10"
      >
        {regnerating
          ? <><Loader2 size={16} className="animate-spin" /> Regenerant IA...</>
          : <><Brain size={16} /> {check.estat_explicacio === 'PENDENT' ? 'Generar Explicació Ara' : 'Regenerar explicació IA'}</>
        }
      </button>
    </motion.div>
  );
}

// ─── Vista principal ──────────────────────────────────────────────────────────

export default function ChecksAdminView({ selectedProfile = '', profiles = [] }) {
  const [checks, setChecks]       = useState([]);
  const [markdownMap, setMarkdownMap] = useState({});
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState('');
  const [warning, setWarning] = useState('');
  const [search, setSearch]       = useState('');
  const [filterSev, setFilterSev] = useState('');
  const [filterStat, setFilterStat] = useState('');
  const [modal, setModal]         = useState(null); // null | 'nou' | check (per editar)
  const [detail, setDetail]       = useState(null); // check seleccionat al panel dret
  const [deletingId, setDeletingId] = useState(null);
  const [expandedCodex, setExpandedCodex] = useState(null); // ID del check expandit per visualitzar Codex

  const [showDocs, setShowDocs] = useState(false);
  const [docContent, setDocContent] = useState('');
  const [isDocsLoading, setIsDocsLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const fetchDocs = async () => {
    setIsDocsLoading(true);
    try {
      const timestamp = Date.now();
      const response = await axios.get(`/api/docs/technical-audit?t=${timestamp}`);
      setDocContent(response.data.content || '');
      setShowDocs(true);
    } catch (fetchError) {
      console.error('Error fetching docs:', fetchError);
      alert("No s'ha pogut carregar la documentació.");
    } finally {
      setIsDocsLoading(false);
    }
  };

  const fetchChecks = useCallback(async () => {
    setLoading(true);
    setError('');
    setWarning('');
    try {
      const [checksResponse, markdownResponse] = await Promise.allSettled([
        axios.get(API),
        axios.get(MARKDOWN_API),
      ]);

      if (checksResponse.status !== 'fulfilled') {
        throw checksResponse.reason;
      }

      const nextMarkdownMap = markdownResponse.status === 'fulfilled'
        ? buildMarkdownMap(markdownResponse.value.data)
        : {};

      if (markdownResponse.status !== 'fulfilled') {
        setWarning("No s'han pogut carregar les consultes vigents des del Markdown. Es mostra la versió SQLite.");
      }

      const merged = (checksResponse.value.data || [])
        .map((item) => mergeCheckWithMarkdown(item, nextMarkdownMap[String(item?.check_id || '').trim().toUpperCase()]));

      setMarkdownMap(nextMarkdownMap);
      setChecks(merged);
      setDetail((current) => current?.check_id ? merged.find((item) => item.check_id === current.check_id) || null : null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Error carregant checks');
    } finally {
      setLoading(false);
      setRefreshNonce((current) => current + 1);
    }
  }, []);

  useEffect(() => { fetchChecks(); }, [fetchChecks]);

  const handleDelete = async (check) => {
    if (!confirm(`Eliminar '${check.check_id} — ${check.titol}'? Acció reversible (soft-delete).`)) return;
    setDeletingId(check.check_id);
    try {
      await axios.delete(`${API}/${check.check_id}`);
      fetchChecks();
      if (detail?.check_id === check.check_id) setDetail(null);
    } finally {
      setDeletingId(null);
    }
  };

  // Filtres aplicats
  const filtered = checks.filter(c => {
    const termMatch = !search ||
      c.check_id.toLowerCase().includes(search.toLowerCase()) ||
      c.titol.toLowerCase().includes(search.toLowerCase());
    const sevMatch  = !filterSev  || c.severitat_base === filterSev;
    const statMatch = !filterStat || c.estat_explicacio === filterStat;
    return termMatch && sevMatch && statMatch;
  });

  return (
    <div className="flex flex-col gap-6 min-h-0">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-black tracking-tight text-primary">Gestió de controls</h1>
            <button 
              onClick={fetchDocs}
              disabled={isDocsLoading}
              className="p-1 px-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-all flex items-center gap-1.5"
              title="Informació tècnica del sistema"
            >
              {isDocsLoading ? <RefreshCw size={14} className="animate-spin" /> : <Info size={14} />}
              <span className="text-[10px] font-bold uppercase tracking-wider">Doc tècnica</span>
            </button>
          </div>
          <p className="mt-1 text-sm text-muted-foreground uppercase font-bold tracking-widest opacity-60">Control de Consultes Post-CRQ</p>
        </div>
      </div>

      {/* Banner informatiu */}
      <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-2xl p-4 flex items-start gap-4 shadow-xl backdrop-blur-md">
        <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-300">
          <Brain size={20} />
        </div>
        <div>
          <p className="text-sm font-bold text-indigo-100 italic">Gestió de consultes d'auditoria</p>
          <p className="text-xs text-gray-400 mt-1 leading-relaxed">
            Cada check pot tenir múltiples versions SQL. Al desar un canvi,
            la IA regenera automàticament l'explicació i sincronitza els fitxers
            <code className="mx-1.5 px-1.5 py-0.5 rounded bg-black/40 text-green-400/90 font-mono text-[10px] border border-white/5 font-normal">auditoria_post_crq.md</code> i
            <code className="mx-1.5 px-1.5 py-0.5 rounded bg-black/40 text-green-400/90 font-mono text-[10px] border border-white/5 font-normal">consultes_post_crq.txt</code>.
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-amber-300 bg-amber-50 px-5 py-4 flex items-start gap-4 shadow-sm">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-300 bg-white text-amber-700 shadow-sm">
          <AlertTriangle size={20} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold text-amber-900">Desar requereix prevalidació</p>
          <p className="mt-1 text-sm leading-relaxed text-slate-800">
            Qualsevol canvi al formulari o a la SQL s'ha de validar amb Oracle i la previsualització IA abans de poder desar la versió actual.
          </p>
        </div>
      </div>

      {/* Barra de filtre + acció */}
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex flex-wrap gap-2 flex-1">
          <input
            type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cercar check..."
            className="h-9 rounded-lg bg-white/5 border border-white/10 px-3 text-sm
                       outline-none focus:ring-1 focus:ring-primary min-w-[180px]"
          />
          <select value={filterSev} onChange={e => setFilterSev(e.target.value)}
            className="h-9 rounded-lg bg-white/5 border border-white/10 px-3 text-sm
                       outline-none focus:ring-1 focus:ring-primary">
            <option value="">Totes les severitats</option>
            {SEVERITAT_OPTIONS.map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={filterStat} onChange={e => setFilterStat(e.target.value)}
            className="h-9 rounded-lg bg-white/5 border border-white/10 px-3 text-sm
                       outline-none focus:ring-1 focus:ring-primary">
            <option value="">Tots els estats</option>
            <option value="VIGENT">IA vigent</option>
            <option value="PENDENT">Pendent IA</option>
            <option value="ERROR">Error IA</option>
          </select>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchChecks}
            className="h-9 px-3 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10
                       flex items-center gap-1.5 text-sm">
            <RefreshCcw size={14} /> Actualitzar
          </button>
          <button onClick={() => setModal('nou')}
            className="h-9 px-4 rounded-lg bg-primary text-white font-bold text-sm
                       hover:bg-primary/80 flex items-center gap-1.5">
            <Plus size={16} /> Nou check
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 rounded-xl p-3 flex gap-2 text-sm">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {error}
        </div>
      )}
      {warning && (
        <div className="bg-amber-500/10 border border-amber-500/20 text-amber-100 rounded-xl p-3 flex gap-2 text-sm">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {warning}
        </div>
      )}

      {/* Cos: taula + panel lateral */}
      <div className="flex gap-6 min-h-[500px]">

        {/* Taula de checks */}
        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="grid gap-3">
              {[1,2,3,4].map(i => <div key={i} className="h-14 bg-white/3 rounded-xl animate-pulse" />)}
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-500">
              <Database size={36} strokeWidth={1} />
              <p className="text-sm">Cap check trobat.</p>
              {checks.length === 0 && (
                <p className="text-xs text-center max-w-xs">
                  Executa el script de migració per importar
                  els checks des d'<code>auditoria_post_crq.md</code>.
                </p>
              )}
            </div>
          )}
          {!loading && filtered.length > 0 && (
            <table className="w-full text-left text-sm border-separate border-spacing-y-1">
              <thead>
                <tr className="text-[10px] font-bold uppercase text-gray-500">
                  <th className="pb-2 px-3">Check</th>
                  <th className="pb-2 px-3">Títol</th>
                  <th className="pb-2 px-3">Sev.</th>
                  <th className="pb-2 px-3">Estat IA</th>
                  <th className="pb-2 px-3">Sync</th>
                  <th className="pb-2 px-3 text-right">Accions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(c => {
                  const isExpanded = expandedCodex === c.check_id;
                  return (
                    <React.Fragment key={c.check_id}>
                      <motion.tr
                        layout
                        className={`group bg-white/5 border border-white/10 hover:bg-white/10 transition-colors ${detail?.check_id === c.check_id ? 'ring-1 ring-primary' : ''}`}
                      >
                        <td className="py-3 px-3 font-mono font-bold text-primary">
                          <button onClick={() => setDetail(c)} className="hover:underline">
                            {normalizeUiText(c.check_id)}
                          </button>
                        </td>
                        <td className="py-3 px-3">
                          <div className="font-medium text-gray-200 line-clamp-1">{normalizeUiText(c.titol)}</div>
                        </td>
                        <td className="py-3 px-3">
                          {sevBadge(c.severitat_base)}
                        </td>
                        <td className="py-3 px-3">
                          {explBadge(c.estat_explicacio)}
                        </td>
                        <td className="py-3 px-3">
                          {syncBadge(c.estat_sync)}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button 
                              onClick={() => setExpandedCodex(isExpanded ? null : c.check_id)}
                              className={`p-1.5 rounded-lg transition-all ${isExpanded ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20' : 'bg-white/5 hover:bg-indigo-500/20 text-indigo-400 hover:text-indigo-300'}`}
                              title="Codex Expert Mode"
                            >
                              <Sparkles size={14} className={isExpanded ? 'animate-pulse' : ''} />
                            </button>
                            <button title="Editar" onClick={() => setModal(c)} className="p-1.5 rounded-lg bg-white/5 hover:bg-blue-500/20 text-blue-400">
                              <Pencil size={14} />
                            </button>
                            <button 
                              title="Eliminar"
                              onClick={() => handleDelete(c)} 
                              disabled={deletingId === c.check_id}
                              className="p-1.5 rounded-lg bg-white/5 hover:bg-red-500/20 text-red-400"
                            >
                              {deletingId === c.check_id ? <RefreshCcw size={14} className="animate-spin" /> : <Trash2 size={14} />}
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                      
                      <AnimatePresence>
                        {isExpanded && (
                          <motion.tr
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="bg-indigo-500/5 overscroll-none overflow-hidden"
                          >
                            <td colSpan={6} className="px-3 pb-3">
                              <SQLCodexWorkbench originalSql={c.sql_vigent} selectedProfile={selectedProfile} profiles={profiles} />
                            </td>
                          </motion.tr>
                        )}
                      </AnimatePresence>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Panel lateral de detall */}
        <AnimatePresence mode="wait">
          {detail && (
            <div className="w-[340px] shrink-0">
              <CheckDetailPanel
                check={detail}
                onClose={() => setDetail(null)}
                onRegenerate={() => {
                  fetchChecks();
                  setTimeout(() => {
                    axios.get(`${API}/${detail.check_id}`)
                      .then(r => setDetail(mergeCheckWithMarkdown(r.data, markdownMap[String(r.data?.check_id || '').trim().toUpperCase()])))
                      .catch(() => {});
                  }, 600);
                }}
              />
            </div>
          )}
        </AnimatePresence>
      </div>

      <PostCrqOperationalDocsPanel
        selectedProfile={selectedProfile}
        checks={checks.map((item) => ({
          check_id: item.check_id,
          title: item.titol,
          criteri: item.context_check,
        }))}
        result={null}
        refreshNonce={refreshNonce}
      />

      {/* Modals */}
      <AnimatePresence>
        {modal && (
          <CheckModal
            check={modal === 'nou' ? null : modal}
            onClose={() => setModal(null)}
            onSaved={fetchChecks}
            selectedProfile={selectedProfile}
            profiles={profiles}
          />
        )}
      </AnimatePresence>

      {/* Modal de Documentació */}
      <AnimatePresence>
        {showDocs && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowDocs(false)}
              className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative z-10 flex h-full max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-[#0d0d0d] shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 p-6 bg-white/5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20 text-primary">
                    <Info size={24} />
                  </div>
                  <div>
                    <h4 className="text-lg font-bold text-primary">Documentació tècnica: gestió de controls</h4>
                    <p className="text-xs text-muted-foreground italic tracking-wide">Manual d'ús i definicions del diccionari de checks</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowDocs(false)}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-muted-foreground transition-all hover:bg-white/10 hover:text-foreground shadow-lg"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="flex-1 overflow-auto p-8 scrollbar-thin scrollbar-thumb-white/10">
                <div className="prose prose-invert prose-primary max-w-none prose-pre:bg-white/5 prose-pre:border prose-pre:border-white/10 prose-pre:rounded-2xl">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {docContent}
                  </ReactMarkdown>
                </div>
              </div>
              
              <div className="border-t border-white/10 p-4 bg-white/5 flex justify-end">
                <button
                  onClick={() => setShowDocs(false)}
                  className="px-6 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-sm font-bold transition-all"
                >
                  Tancar
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
