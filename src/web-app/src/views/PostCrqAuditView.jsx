import React, { useEffect, useId, useState } from 'react';
import mermaid from 'mermaid';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from 'axios';
import { downloadPostCrqReport } from '../api/postCrqAudit.js';
import { resolveRequestErrorMessage } from '../utils/automationViewUtils.js';
import {
  AlertTriangle,
  CalendarRange,
  ChevronDown,
  ChevronUp,
  CheckSquare,
  Database,
  Download,
  FileArchive,
  FileSearch,
  Filter,
  Play,
  RefreshCcw,
  Square,
  Info,
  X,
  ExternalLink,
} from 'lucide-react';

mermaid.initialize({
  startOnLoad: true,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'Inter, system-ui, sans-serif',
});

const MermaidChart = ({ chart }) => {
  const [svg, setSvg] = useState('');
  const rawId = useId();
  const id = `mermaid-${rawId.replace(/:/g, '-')}`;

  useEffect(() => {
    const renderChart = async () => {
      if (!chart) return;
      try {
        const cleanChart = chart.trim();
        const { svg: svgCode } = await mermaid.render(id, cleanChart);
        setSvg(svgCode);
      } catch (err) {
        console.error('Mermaid render error:', err);
        setSvg(`<div class="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-red-200 text-xs font-mono">
          <p class="font-bold mb-1">Error en el diagrama Mermaid:</p>
          <pre class="whitespace-pre-wrap">${err.message || 'Error desconegut'}</pre>
        </div>`);
      }
    };
    renderChart();
  }, [chart, id]);

  return (
    <div 
      className="my-8 flex justify-center bg-white/5 p-6 rounded-2xl border border-white/10 overflow-x-auto scrollbar-thin scrollbar-thumb-white/10" 
      dangerouslySetInnerHTML={{ __html: svg }} 
    />
  );
};

const PRESET_OPTIONS = [
  { value: 'daily', label: 'Diari' },
  { value: 'weekly', label: 'Setmanal' },
  { value: 'monthly', label: 'Mensual' },
];

const CRITICALITY_OPTIONS = [
  { value: 'CRITIC', label: 'Crític' },
  { value: 'MITJA', label: 'Mitjà' },
  { value: 'BAIX', label: 'Baix' },
];

const CONCURRENCY_OPTIONS = [1, 2, 3, 4];

const CRITICALITY_ORDER = ['CRITIC', 'MITJA', 'BAIX'];

function criticalityKey(value) {
  if (!value) return 'BAIX';
  const text = normalizeUiText(String(value));
  const normalized = text.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  if (normalized.includes('CRIT')) {
    return 'CRITIC';
  }
  if (normalized.includes('MITJ')) {
    return 'MITJA';
  }
  return 'BAIX';
}

function criticalityLabel(value) {
  const key = criticalityKey(value);
  if (key === 'CRITIC') return 'Crític';
  if (key === 'MITJA') return 'Mitjà';
  return 'Baix';
}

function normalizeUiText(value) {
  if (value === null || value === undefined) return '';
  let text = String(value);

  if (/[\u00c3\u00c2\u00e2]/.test(text)) {
    try {
      text = decodeURIComponent(escape(text));
    } catch (_error) {
      // Manté el text original si la reparació automàtica falla.
    }
  }

  return text
    .replace(/â€¢/g, '•')
    .replace(/â€•/g, '—')
    .replace(/Â·/g, '·')
    .replace(/\u00A0/g, ' ');
}

function severityClass(value) {
  const normalized = criticalityKey(value);
  if (normalized === 'CRITIC') {
    return 'bg-red-100 text-red-700 border-red-200 font-extrabold shadow-sm shadow-red-500/10';
  }
  if (normalized === 'MITJA') {
    return 'bg-orange-100 text-orange-700 border-orange-200';
  }
  return 'bg-blue-50 text-blue-700 border-blue-100';
}

function checkSeverityTextColor(value) {
  const normalized = criticalityKey(value);
  return normalized === 'CRITIC' ? 'text-red-700 font-bold' : 'text-primary';
}

function statusClass(value) {
  if (value === 'ok') return 'bg-green-100 text-green-700 border-green-200';
  if (value === 'error') return 'bg-red-100 text-red-700 border-red-200';
  return 'bg-white/10 text-foreground border-white/10';
}

function schedulerRiskAssessment(options) {
  const global = options?.max_concurrency || 1;
  const heavy = options?.max_heavy_concurrency || 1;
  const autoThrottle = !!options?.enable_auto_throttle;
  const retries = options?.max_retries || 0;

  if (global === 1 && heavy === 1 && autoThrottle) {
    return {
      label: 'Segur',
      detail: 'Configuració conservadora. Recomanada mentre encara no tens mètriques estables de càrrega.',
      className: 'bg-green-500/15 text-green-300 border-green-500/20',
    };
  }

  if (global <= 3 && heavy <= 1 && autoThrottle && retries <= 1) {
    return {
      label: 'Prudent',
      detail: 'Bona opció per reduir temps total sense exposar massa la BBDD si els últims lots han estat estables.',
      className: 'bg-yellow-500/15 text-yellow-200 border-yellow-500/20',
    };
  }

  return {
    label: 'Agressiu',
    detail: 'Pot tensar sessions, CPU o I/O. Mantén aquesta configuració només si tens observabilitat i proves prèvies.',
    className: 'bg-red-500/15 text-red-400 border-red-500/20',
  };
}


function humanizeDuration(value) {
  const durationMs = Number(value || 0);
  if (durationMs < 1000) return `${durationMs} ms`;
  if (durationMs < 60000) return `${(durationMs / 1000).toFixed(2).replace('.', ',')} s`;
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} min ${seconds} s`;
}

function priorityBadgeClass(value) {
  const normalized = criticalityKey(value);
  if (normalized === 'CRITIC') return 'bg-red-100 text-red-700 border-red-200 font-extrabold';
  if (normalized === 'MITJA') return 'bg-orange-100 text-orange-700 border-orange-200';
  return 'bg-blue-50 text-blue-700 border-blue-100';
}

export default function PostCrqAuditView({
  profiles,
  selectedProfile,
  checksLoading,
  checks,
  selectedChecks,
  criticalityOverrides,
  schedulerOptions,
  timeFilter,
  schemasValue,
  isRunning,
  result,
  error,
  executionOrigin,
  onRefreshChecks,
  onProfileChange,
  onToggleCheck,
  onSelectAll,
  onClearAll,
  onSchemasChange,
  onTimeFilterChange,
  onCriticalityOverrideChange,
  onSchedulerOptionsChange,
  onResetCriticalityOverrides,
  onRun,
  onDownloadQueries,
}) {
  const [showDocs, setShowDocs] = useState(false);
  const [docContent, setDocContent] = useState('');
  const [isDocsLoading, setIsDocsLoading] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [isReportDownloadRunning, setIsReportDownloadRunning] = useState(false);
  const [reportVariant, setReportVariant] = useState('all');
  const [selectedProviderCode, setSelectedProviderCode] = useState('');
  const reportDownloadCacheRef = React.useRef(new Map());

  useEffect(() => {
    reportDownloadCacheRef.current.clear();
  }, [result]);

  const triggerReportDownload = React.useCallback((blob, fileName) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }, []);

  const handleDownloadReport = async (summaryVersion = 'v1') => {
    if (reportVariant === 'provider' && !selectedProviderCode) {
      alert("Cal seleccionar un prove?dor abans de generar el report.");
      return;
    }
    if (summaryVersion !== 'v1' && reportVariant !== 'general') {
      alert("La versió experimental només està disponible per al resum general.");
      return;
    }

    const cacheKey = JSON.stringify({
      variant: reportVariant,
      provider: reportVariant === 'provider' ? selectedProviderCode : '',
      summaryVersion,
      generatedAt: result?.report_model?.execution_parameters?.generated_at || result?.context?.generated_at || '',
      profile: selectedProfile || '',
    });
    const cachedDownload = reportDownloadCacheRef.current.get(cacheKey);
    if (cachedDownload) {
      triggerReportDownload(cachedDownload.blob, cachedDownload.fileName);
      return;
    }

    setIsReportDownloadRunning(true);
    try {
      const response = await downloadPostCrqReport({
        profile: selectedProfile,
        schemas: schemasValue ? schemasValue.split(',').map((item) => item.trim()) : [],
        time_filter: timeFilter,
        selected_checks: selectedChecks,
        criticality_overrides: criticalityOverrides,
        scheduler_options: schedulerOptions,
        variant: reportVariant,
        summary_version: summaryVersion,
        provider_code: reportVariant === 'provider' ? selectedProviderCode : '',
        report_data: result?.audit_type === 'post_crq' ? result : undefined,
      });

      const contentDisposition = response.headers['content-disposition'];
      let fileName = reportVariant === 'all'
        ? `auditoria_lots_${selectedProfile}.zip`
        : summaryVersion === 'v2'
          ? `report_post_crq_${selectedProfile}_v2.pdf`
          : `report_post_crq_${selectedProfile}.pdf`;
      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename=(.+)/);
        if (fileNameMatch?.length === 2) fileName = fileNameMatch[1];
      }
      const blob = new Blob([response.data]);
      reportDownloadCacheRef.current.set(cacheKey, { blob, fileName });
      triggerReportDownload(blob, fileName);
    } catch (err) {
      console.error('Error generant report Post-CRQ:', err);
      alert(await resolveRequestErrorMessage(err, "S'ha produ?t un error en generar el report seleccionat."));
    } finally {
      setIsReportDownloadRunning(false);
    }
  };

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

  const [isConfigurationMenuOpen, setIsConfigurationMenuOpen] = React.useState(false);
  const [configurationPanel, setConfigurationPanel] = React.useState('criticality');
  const [showTechnicalDetail, setShowTechnicalDetail] = React.useState(false);
  const [showLotSummary, setShowLotSummary] = React.useState(true);
  const [showLotIncidents, setShowLotIncidents] = React.useState(true);
  
  const summary = result?.summary || {};
  const reportModel = result?.report_model || null;
  const executionParameters = reportModel?.execution_parameters || null;
  const finalObservations = reportModel?.final_observations || null;
  const queryExport = result?.query_export || null;
  const schedulerSummary = summary?.scheduler || {};
  const findingsByCriticality = summary?.findings_by_criticality || {};
  const lotSummary = React.useMemo(() => reportModel?.lot_summary || [], [reportModel]);
  const lotIncidentGroups = React.useMemo(() => reportModel?.lot_incident_groups || [], [reportModel]);
  const detailSections = React.useMemo(() => reportModel?.detail_sections || [], [reportModel]);
  const executedChecks = React.useMemo(() => result?.executed_checks || [], [result]);
  const resultsByCheck = React.useMemo(() => result?.results_by_check || [], [result]);
  const criticalFindingsCount = Number(
    summary?.critical_findings ??
    findingsByCriticality.CRITIC ??
    findingsByCriticality['Cr\u00edtic'] ??
    findingsByCriticality['Cr?tic'] ??
    0,
  );
  const mediumFindingsCount = Number(
    summary?.medium_findings ??
    findingsByCriticality.MITJA ??
    findingsByCriticality['Mitj\u00e0'] ??
    findingsByCriticality['Mitj?'] ??
    0,
  );
  const lowFindingsCount = Number(
    summary?.low_findings ??
    findingsByCriticality.BAIX ??
    findingsByCriticality['Baix'] ??
    0,
  );

  const effectiveSchedulerOptions = schedulerOptions || {
    max_concurrency: 2,
    max_concurrency_upper_bound: 4,
    max_heavy_concurrency: 1,
    max_medium_concurrency: 1,
    max_light_concurrency: 2,
    max_retries: 1,
    enable_auto_throttle: true,
  };

  const schedulerRisk = schedulerRiskAssessment(effectiveSchedulerOptions);
  const activeCriticalityOverrides = React.useMemo(
    () => Object.entries(criticalityOverrides || {}).filter(([, value]) => Boolean(value)),
    [criticalityOverrides],
  );
  const providerOptions = React.useMemo(
    () => lotSummary.map((lot) => String(lot.lot || '').trim()).filter(Boolean),
    [lotSummary],
  );
  const effectiveConfigSummary = React.useMemo(() => {
    const checksText = selectedChecks.length > 0 ? selectedChecks.join(', ') : 'Cap check seleccionat';
    const windowText = timeFilter.mode === 'range'
      ? `${timeFilter.start_date || '-'} -> ${timeFilter.end_date || '-'}`
      : `Preset ${timeFilter.preset || 'weekly'}`;
    const schedulerText = [
      `global ${effectiveSchedulerOptions.max_concurrency}`,
      `pesades ${effectiveSchedulerOptions.max_heavy_concurrency}`,
      `mitjanes ${effectiveSchedulerOptions.max_medium_concurrency}`,
      `lleugeres ${effectiveSchedulerOptions.max_light_concurrency}`,
      `reintents ${effectiveSchedulerOptions.max_retries}`,
      effectiveSchedulerOptions.enable_auto_throttle ? 'auto-throttle actiu' : 'auto-throttle desactivat',
    ].join(' · ');
    const overridesText = activeCriticalityOverrides.length > 0
      ? activeCriticalityOverrides.map(([checkId, value]) => `${checkId}: ${criticalityLabel(value)}`).join(' · ')
      : 'Backend base';
    return {
      checksText,
      windowText,
      schedulerText,
      overridesText,
      schemasText: schemasValue || 'Tots els esquemes visibles per Oracle',
    };
  }, [activeCriticalityOverrides, effectiveSchedulerOptions, schemasValue, selectedChecks, timeFilter]);

  useEffect(() => {
    if (reportVariant !== 'provider') {
      return;
    }
    if (!providerOptions.length) {
      setSelectedProviderCode('');
      return;
    }
    if (!providerOptions.includes(selectedProviderCode)) {
      setSelectedProviderCode(providerOptions[0]);
    }
  }, [providerOptions, reportVariant, selectedProviderCode]);
  
  const resolveConfiguredCriticality = (checkId, fallbackValue) => (
    normalizeUiText(criticalityLabel(criticalityOverrides?.[checkId] || fallbackValue))
  );

  const technicalCheckRows = React.useMemo(() => {
    const items = [...executedChecks];
    items.sort((left, right) => {
      const leftKey = criticalityKey(criticalityOverrides?.[left.check_id] || left.criticitat || left.severitat || left.criticality);
      const rightKey = criticalityKey(criticalityOverrides?.[right.check_id] || right.criticitat || right.severitat || right.criticality);
      const leftRank = CRITICALITY_ORDER.indexOf(leftKey);
      const rightRank = CRITICALITY_ORDER.indexOf(rightKey);
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return String(left.check_id || '').localeCompare(String(right.check_id || ''));
    });
    return items;
  }, [executedChecks, criticalityOverrides]);

  const technicalResults = React.useMemo(() => {
    const items = [...resultsByCheck];
    items.sort((left, right) => {
      const leftKey = criticalityKey(criticalityOverrides?.[left.check_id] || left.criticitat || left.severitat || left.criticality);
      const rightKey = criticalityKey(criticalityOverrides?.[right.check_id] || right.criticitat || right.severitat || right.criticality);
      const leftRank = CRITICALITY_ORDER.indexOf(leftKey);
      const rightRank = CRITICALITY_ORDER.indexOf(rightKey);
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return String(left.check_id || '').localeCompare(String(right.check_id || ''));
    });
    return items;
  }, [resultsByCheck, criticalityOverrides]);

  const detailSectionByCheck = React.useMemo(() => {
    const mapping = {};
    detailSections.forEach((section) => {
      mapping[section.check_id] = section;
    });
    return mapping;
  }, [detailSections]);

  const lotIncidentGroupMap = React.useMemo(() => {
    const mapping = {};
    lotIncidentGroups.forEach((group) => {
      mapping[`${group.lot || 'SENSE LOT'}::${group.check}`] = group;
    });
    return mapping;
  }, [lotIncidentGroups]);

  const lotCards = React.useMemo(
    () => lotSummary.map((lot) => ({
      ...lot,
      schemasList: (lot.schemas || []).map((schema) => normalizeUiText(schema)),
      checksForLot: (lot.checks || []).map((checkId) => {
        const detail = detailSectionByCheck[checkId] || {};
        const fallbackTitle = lot.check_descriptions?.find((entry) => entry.check_id === checkId)?.title || checkId;
        return {
          check_id: checkId,
          title: normalizeUiText(detail.title || fallbackTitle),
          overview: normalizeUiText(detail.overview || 'Sense descripció funcional disponible.'),
          whyItMatters: normalizeUiText(detail.why_it_matters || ''),
          criticality: normalizeUiText(lot.priority || 'Baix'),
        };
      }),
    })),
    [lotSummary, detailSectionByCheck],
  );

  const enrichedLotCards = React.useMemo(
    () => lotCards.map((lot) => ({
      ...lot,
      checksForLot: (lot.checksForLot || []).map((check) => {
        const incidentGroup = lotIncidentGroupMap[`${lot.lot || 'SENSE LOT'}::${check.check_id}`] || {};
        return {
          ...check,
          overview: normalizeUiText(check.overview || incidentGroup.description || 'Sense descripció funcional disponible.'),
          whyItMatters: normalizeUiText(check.whyItMatters || incidentGroup.impacte || ''),
          recommendedAction: normalizeUiText(incidentGroup.accio_recomanada || lot.first_action || ''),
          criticality: normalizeUiText(incidentGroup.severity || check.criticality || lot.priority || 'Baix'),
          terminiDies: incidentGroup.termini_dies,
        };
      }),
    })),
    [lotCards, lotIncidentGroupMap],
  );

  const incidentTableColumns = React.useCallback((objects) => {
    const preferredOrder = ['OBJECTE', 'TIPUS', 'DADA TÈCNICA', 'ESQUEMA', 'OBSERVACIÓ', 'SUBTIPUS'];
    const available = new Set();
    (objects || []).forEach((item) => {
      Object.entries(item || {}).forEach(([key, value]) => {
        if (value !== null && value !== undefined && String(value).trim() !== '') {
          available.add(key);
        }
      });
    });
    return preferredOrder.filter((column) => available.has(column));
  }, []);

  const visibleTechnicalColumns = React.useCallback((item) => {
    const columns = item?.columns || [];
    if (item?.check_id === 'CHECK_12') {
      return columns;
    }
    const hiddenAiMarkers = ['IA', 'EXPLICACIO', 'RECOMANACIO', 'CLASSIFICACIO', 'CONFIANCA', 'ESTAT_ANALISI'];
    return columns.filter((column) => {
      const normalized = String(column || '').toUpperCase();
      return !hiddenAiMarkers.some((marker) => normalized.includes(marker));
    });
  }, []);

  const renderLotIncidentCard = (group) => (
    <div
      key={`lot-group-${group.lot}-${group.check}`}
      className="rounded-[28px] border border-white/10 bg-white/5 p-6 shadow-sm shadow-black/5"
    >
      <div className="mb-6 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-muted-foreground">
            Lot prioritzat
          </p>
          <h5 className="mt-2 text-3xl font-black tracking-tight text-foreground">
            LOT {normalizeUiText(group.lot || 'SENSE LOT')}
          </h5>
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            {normalizeUiText(group.check || '-')}
          </p>
          <h6 className="mt-2 text-lg font-bold leading-7 text-foreground">
            {normalizeUiText(group.title || '-')}
          </h6>
        </div>
        <div className="flex flex-wrap gap-3 xl:justify-end">
          <div className={`inline-flex rounded-full border px-4 py-2 text-xs font-extrabold uppercase tracking-wide ${priorityBadgeClass(group.severity)}`}>
            {normalizeUiText(group.severity || '-')}
          </div>
          <div className="rounded-full border border-white/10 bg-black/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {Number.isFinite(group.termini_dies) ? `Termini ${group.termini_dies} dies` : 'Termini no informat'}
          </div>
          <div className="rounded-full border border-white/10 bg-black/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {(group.schemas || []).reduce((sum, schemaGroup) => sum + ((schemaGroup.objectes || []).length || 0), 0)} objectes
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-black/10 px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground">
              Què s'ha detectat
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/85">
              {normalizeUiText(group.description || 'Sense descripció disponible.')}
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/10 px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground">
              Impacte
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/85">
              {normalizeUiText(group.impacte || 'Sense impacte informat.')}
            </p>
          </div>
          <div className="rounded-2xl border border-primary/10 bg-primary/5 px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.2em] text-primary">
              Acció requerida
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/85">
              {normalizeUiText(group.accio_recomanada || 'Sense acció recomanada.')}
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/10 px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground">
              Validació posterior
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/85">
              {normalizeUiText(group.validacio_posterior || 'Sense validació posterior.')}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 px-5 py-4">
          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground">
            Esquemes afectats
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(group.schemas || []).map((schemaGroup) => (
              <span
                key={`${group.lot}-${group.check}-pill-${schemaGroup.nom}`}
                className="inline-flex rounded-full border border-primary/15 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary"
              >
                {normalizeUiText(schemaGroup.nom || '-')} · {schemaGroup.object_count || 0}
              </span>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Cada etiqueta mostra l'esquema afectat i el nombre d'objectes que el lot ha de revisar.
          </p>
        </div>
      </div>

      <div className="mt-6 space-y-5">
        {(group.schemas || []).map((schemaGroup) => (
          <div key={`${group.lot}-${group.check}-${schemaGroup.nom}`} className="rounded-2xl border border-white/10 bg-black/10 p-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.2em] text-muted-foreground">Esquema</p>
                <p className="mt-1 text-base font-bold text-foreground">{normalizeUiText(schemaGroup.nom || '-')}</p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-muted-foreground">
                {schemaGroup.object_count || 0} objectes
              </span>
            </div>
            <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/5">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-white/10 bg-primary/10 text-[10px] uppercase text-muted-foreground">
                  <tr>
                    {incidentTableColumns(schemaGroup.objectes || []).map((column) => (
                      <th key={`${group.lot}-${group.check}-${schemaGroup.nom}-${column}`} className="px-4 py-3 pr-3">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {(schemaGroup.objectes || []).map((objecte, index) => (
                    <tr key={`${group.lot}-${group.check}-${schemaGroup.nom}-${index}`}>
                      {incidentTableColumns(schemaGroup.objectes || []).map((column) => (
                        <td key={`${group.lot}-${group.check}-${schemaGroup.nom}-${index}-${column}`} className="px-4 py-3 pr-3 align-top">
                          {normalizeUiText(objecte?.[column] || '-')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-8">
      <div className="glass-card p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-widest text-primary">
              <Database size={14} />
              Auditoria de canvis
            </div>
            <div className="flex items-center gap-3">
              <h3 className="text-3xl font-extrabold tracking-tight text-primary">Control de qualitat post-CRQ</h3>
              <button 
                onClick={() => setShowHelp(true)}
                className="p-1.5 rounded-full bg-white/5 hover:bg-white/10 text-muted-foreground hover:text-foreground border border-white/10 transition-all flex items-center justify-center shadow-sm"
                title="Com funciona aquesta pàgina?"
              >
                <Info size={20} />
              </button>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              Executa checks tècnics contra consultes definides al markdown i genera un informe homogeni amb traçabilitat.
            </p>
            <div className="mt-4 flex flex-wrap gap-3 text-xs">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-mono">
                BBDD activa: {selectedProfile || 'Sense perfil'}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                Font checks: {normalizeUiText(result?.context?.source_file || 'Auditoria_post_crq.md')}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                Checks disponibles: {checks.length}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                Seleccionats: {selectedChecks.length}
              </span>
            </div>
          </div>

          <div className="grid w-full max-w-5xl grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-[1.1fr_1.1fr_0.9fr]">
            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold uppercase tracking-wider opacity-60">Base de dades</span>
              <select
                value={selectedProfile}
                onChange={(e) => onProfileChange(e.target.value)}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
              >
                {profiles.length === 0 && <option value="">Sense perfils disponibles</option>}
                {profiles.map((profile) => (
                  <option key={profile} value={profile}>{profile}</option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold uppercase tracking-wider opacity-60">Esquemes opcionals</span>
              <input
                value={schemasValue}
                onChange={(e) => onSchemasChange(e.target.value.toUpperCase())}
                placeholder="APP_USER, CORE_DB"
                className="rounded-xl border border-border bg-white/5 p-3 font-mono text-sm outline-none focus:ring-1 focus:ring-primary"
              />
            </label>

            <div className="flex flex-col gap-2">
              <span className="text-xs font-bold uppercase tracking-wider opacity-60">Controls</span>
              <div className="flex flex-wrap gap-2">
                <select
                  value={reportVariant}
                  onChange={(e) => setReportVariant(e.target.value)}
                  className="min-w-[170px] rounded-xl border border-indigo-300/70 bg-white px-3 py-3 text-sm font-semibold text-slate-700 shadow-sm outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  <option value="general">Resum general</option>
                  <option value="provider">Un proveïdor</option>
                  <option value="all">Tots (ZIP)</option>
                </select>
                {reportVariant === 'provider' && (
                  <select
                    value={selectedProviderCode}
                    onChange={(e) => setSelectedProviderCode(e.target.value)}
                    disabled={providerOptions.length === 0}
                    className="min-w-[180px] rounded-xl border border-indigo-300/70 bg-white px-3 py-3 text-sm font-semibold text-slate-700 shadow-sm outline-none focus:ring-2 focus:ring-indigo-300 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 disabled:opacity-100"
                  >
                    {providerOptions.length === 0 ? (
                      <option value="">Executa l'auditoria per detectar lots</option>
                    ) : (
                      providerOptions.map((providerCode) => (
                        <option key={providerCode} value={providerCode}>{providerCode}</option>
                      ))
                    )}
                  </select>
                )}
                <button
                  onClick={onRefreshChecks}
                  type="button"
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-blue-500/20 bg-blue-500/10 px-3 py-3 text-sm font-semibold text-blue-400 transition-all hover:bg-blue-500/20"
                  title="Sincronitzar llibreria de checks des de Markdown"
                >
                  <RefreshCcw size={16} className={checksLoading ? 'animate-spin' : ''} />
                  Sinc. Checks
                </button>
                <button
                  onClick={onRun}
                  type="button"
                  disabled={isRunning || isReportDownloadRunning || !selectedProfile || selectedChecks.length === 0}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-3 py-3 text-sm font-bold text-primary-foreground transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isRunning ? <RefreshCcw size={16} className="animate-spin" /> : <Play size={16} />}
                  Executar
                </button>
                <button
                  onClick={() => handleDownloadReport('v1')}
                  type="button"
                  disabled={isRunning || isReportDownloadRunning || !selectedProfile || selectedChecks.length === 0 || (reportVariant === 'provider' && providerOptions.length === 0)}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3 py-3 text-sm font-bold text-white transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 shadow-lg shadow-indigo-500/20"
                  title={reportVariant === 'all' ? 'Generar resum general i un PDF per cada lot en un ZIP' : 'Generar el report Post-CRQ seleccionat'}
                >
                  {isReportDownloadRunning ? (
                    <RefreshCcw size={16} className="animate-spin" />
                  ) : reportVariant === 'all' ? (
                    <FileArchive size={16} />
                  ) : (
                    <Download size={16} />
                  )}
                  {reportVariant === 'general' ? 'Descarregar resum' : reportVariant === 'provider' ? 'Descarregar proveïdor' : 'Descarregar ZIP'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="mt-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        {executionOrigin && executionOrigin.mode === 'snapshot' ? (
          <div className={`mt-6 rounded-2xl border px-4 py-4 text-sm ${
            executionOrigin.mode === 'snapshot'
              ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-50'
              : 'border-amber-500/20 bg-amber-500/10 text-amber-50'
          }`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-current/20 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide">
                {executionOrigin.label}
              </span>
              {executionOrigin.generatedAt ? (
                <span className="text-xs opacity-80">Generat originalment: {executionOrigin.generatedAt}</span>
              ) : null}
            </div>
            <p className="mt-2 leading-6">{executionOrigin.warning}</p>
          </div>
        ) : null}

        <div className="mt-6 rounded-2xl border border-white/10 bg-black/10 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-muted-foreground">Configuració efectiva</p>
              <p className="mt-2 text-sm text-muted-foreground">Aquest resum fa visible la configuració real de checks, finestra, scheduler i overrides que s'utilitzarà o que s'ha recuperat del snapshot.</p>
            </div>
            <button
              type="button"
              onClick={onResetCriticalityOverrides}
              className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"
            >
              Restablecer criticidades
            </button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Checks</p>
              <p className="mt-2 text-sm text-foreground">{effectiveConfigSummary.checksText}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Finestra</p>
              <p className="mt-2 text-sm text-foreground">{effectiveConfigSummary.windowText}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Scheduler</p>
              <p className="mt-2 text-sm text-foreground">{effectiveConfigSummary.schedulerText}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Overrides actius</p>
              <p className="mt-2 text-sm text-foreground">{effectiveConfigSummary.overridesText}</p>
            </div>
          </div>
          <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Esquemes</p>
            <p className="mt-2 text-sm text-foreground">{effectiveConfigSummary.schemasText}</p>
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-6">
          <div className="flex items-center justify-end">
            <button
              type="button"
              onClick={() => setIsConfigurationMenuOpen((current) => !current)}
              className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold transition-all ${
                isConfigurationMenuOpen
                  ? 'border-primary/40 bg-primary/15 text-primary'
                  : 'border-white/10 bg-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground'
              }`}
            >
              {isConfigurationMenuOpen ? 'Amagar configuració' : 'Obrir configuració'}
            </button>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/10 p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <CalendarRange size={16} className="text-primary" />
                <h4 className="text-sm font-bold uppercase tracking-wider opacity-70">Temporalitat</h4>
              </div>
              <span className="text-[11px] text-muted-foreground">L'aplicació calcula automàticament el període de revisió.</span>
            </div>

            <p className="mb-4 text-xs text-muted-foreground">
              Si tries una freqüència, l'aplicació converteix automàticament l'opció en el període que ha de revisar.
            </p>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2">
                <span className="text-xs font-semibold opacity-80">Tipus de període</span>
                <select
                  value={timeFilter.mode}
                  onChange={(e) => onTimeFilterChange({ ...timeFilter, mode: e.target.value })}
                  className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="preset">Període predefinit</option>
                  <option value="range">Entre dues dates</option>
                </select>
              </label>

              {timeFilter.mode === 'preset' ? (
                <label className="flex flex-col gap-2">
                  <span className="text-xs font-semibold opacity-80">Freqüència</span>
                  <select
                    value={timeFilter.preset}
                    onChange={(e) => onTimeFilterChange({ ...timeFilter, preset: e.target.value })}
                    className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                  >
                    {PRESET_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <>
                  <label className="flex flex-col gap-2">
                    <span className="text-xs font-semibold opacity-80">Data i hora inici</span>
                    <input
                      type="datetime-local"
                      value={timeFilter.start_date}
                      onChange={(e) => onTimeFilterChange({ ...timeFilter, start_date: e.target.value })}
                      className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>
                  <label className="flex flex-col gap-2">
                    <span className="text-xs font-semibold opacity-80">Data i hora fi</span>
                    <input
                      type="datetime-local"
                      value={timeFilter.end_date}
                      onChange={(e) => onTimeFilterChange({ ...timeFilter, end_date: e.target.value })}
                      className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>
                </>
              )}

            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/10 p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Filter size={16} className="text-primary" />
                <h4 className="text-sm font-bold uppercase tracking-wider opacity-70">Selecció de checks</h4>
              </div>
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  onClick={onSelectAll}
                  className="rounded-lg border border-border bg-white/5 px-3 py-1.5 font-semibold hover:bg-white/10"
                >
                  Tots
                </button>
                <button
                  type="button"
                  onClick={onClearAll}
                  className="rounded-lg border border-border bg-white/5 px-3 py-1.5 font-semibold hover:bg-white/10"
                >
                  Netejar
                </button>
              </div>
            </div>

            <p className="mb-4 text-xs text-muted-foreground">
              Selecciona els controls que vols executar. Cada targeta indica el check i el criteri funcional que revisa.
            </p>

            <div className="max-h-[560px] space-y-3 overflow-auto pr-1">
              {checksLoading && (
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                  Carregant checks disponibles...
                </div>
              )}

              {!checksLoading && checks.map((check) => {
                const checked = selectedChecks.includes(check.check_id);
                return (
                  <label
                    key={check.check_id}
                    className={`flex cursor-pointer gap-3 rounded-xl border p-4 transition-all ${
                      checked ? 'border-primary bg-primary/10' : 'border-white/10 bg-white/5 hover:bg-white/10'
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => onToggleCheck(check.check_id)}
                    />
                    <div className="pt-0.5">
                      {checked ? <CheckSquare size={18} className="text-primary" /> : <Square size={18} className="opacity-50" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`font-mono text-xs font-bold ${checkSeverityTextColor(check.criticitat || check.severitat)}`}>{check.check_id}</span>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${severityClass(resolveConfiguredCriticality(check.check_id, check.criticitat || check.severitat))}`}>
                          {resolveConfiguredCriticality(check.check_id, check.criticitat || check.severitat)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm font-semibold">{normalizeUiText(check.title)}</p>
                      {check.criteri && (
                        <p className="mt-1 text-xs text-muted-foreground">{normalizeUiText(check.criteri)}</p>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {isConfigurationMenuOpen && (
            <div className="rounded-2xl border border-white/10 bg-black/10 p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={16} className="text-primary" />
                  <h4 className="text-sm font-bold uppercase tracking-wider opacity-70">Submenú de configuració</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setConfigurationPanel('scheduler')}
                    className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
                      configurationPanel === 'scheduler'
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-white/10 bg-white/5 hover:bg-white/10'
                    }`}
                  >
                    Planificador d'execució
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfigurationPanel('criticality')}
                    className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
                      configurationPanel === 'criticality'
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-white/10 bg-white/5 hover:bg-white/10'
                    }`}
                  >
                    Criticitat de les consultes
                  </button>
                </div>
              </div>

              {configurationPanel === 'scheduler' && (
                <>
                  <div className="mb-4 rounded-xl border border-white/10 bg-black/10 p-4">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase ${schedulerRisk.className}`}>
                        Risc del pla: {schedulerRisk.label}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {schedulerRisk.detail}
                      </span>
                    </div>
                  </div>
                  <p className="mb-4 text-xs text-muted-foreground">
                    Configura un paral·lelisme prudent. El valor inicial recomanat és 2, amb un màxim de 4, i el backend evita executar més d'una consulta pesada alhora.
                  </p>
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs text-muted-foreground">
                      Cada override és explícit i visible. Si el deixes a <span className="font-semibold text-foreground">Backend base</span>, la criticitat la resol el backend.
                    </p>
                    <button
                      type="button"
                      onClick={onResetCriticalityOverrides}
                      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"
                    >
                      Restablecer criticidades
                    </button>
                  </div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Concurrència global</span>
                      <select
                        value={effectiveSchedulerOptions.max_concurrency}
                        onChange={(e) => onSchedulerOptionsChange({
                          ...effectiveSchedulerOptions,
                          max_concurrency: Number(e.target.value),
                        })}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      >
                        {CONCURRENCY_OPTIONS.map((value) => (
                          <option key={`global-${value}`} value={value}>{value}</option>
                        ))}
                      </select>
                      <span className="text-xs text-muted-foreground">Comença amb 2 i només puja a 3 o 4 quan el temps total millori sense generar errors ni timeouts.</span>
                    </label>

                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Pesades simultànies</span>
                      <select
                        value={effectiveSchedulerOptions.max_heavy_concurrency}
                        onChange={(e) => onSchedulerOptionsChange({
                          ...effectiveSchedulerOptions,
                          max_heavy_concurrency: Number(e.target.value),
                        })}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      >
                        {[1, 2].map((value) => (
                          <option key={`heavy-${value}`} value={value}>{value}</option>
                        ))}
                      </select>
                      <span className="text-xs text-muted-foreground">Recomanat: 1. Evita solapar consultes costoses sobre diccionari Oracle.</span>
                    </label>

                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Mitjanes simultànies</span>
                      <select
                        value={effectiveSchedulerOptions.max_medium_concurrency}
                        onChange={(e) => onSchedulerOptionsChange({
                          ...effectiveSchedulerOptions,
                          max_medium_concurrency: Number(e.target.value),
                        })}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      >
                        {CONCURRENCY_OPTIONS.map((value) => (
                          <option key={`medium-${value}`} value={value}>{value}</option>
                        ))}
                      </select>
                    </label>

                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Lleugeres simultànies</span>
                      <select
                        value={effectiveSchedulerOptions.max_light_concurrency}
                        onChange={(e) => onSchedulerOptionsChange({
                          ...effectiveSchedulerOptions,
                          max_light_concurrency: Number(e.target.value),
                        })}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      >
                        {CONCURRENCY_OPTIONS.map((value) => (
                          <option key={`light-${value}`} value={value}>{value}</option>
                        ))}
                      </select>
                    </label>

                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Reintents transitoris</span>
                      <select
                        value={effectiveSchedulerOptions.max_retries}
                        onChange={(e) => onSchedulerOptionsChange({
                          ...effectiveSchedulerOptions,
                          max_retries: Number(e.target.value),
                        })}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      >
                        {[0, 1].map((value) => (
                          <option key={`retry-${value}`} value={value}>{value}</option>
                        ))}
                      </select>
                    </label>

                    <label className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <span className="text-xs font-bold uppercase tracking-wider opacity-70">Protecció automàtica</span>
                      <label className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-black/10 px-3 py-3 text-sm">
                        <input
                          type="checkbox"
                          checked={!!effectiveSchedulerOptions.enable_auto_throttle}
                          onChange={(e) => onSchedulerOptionsChange({
                            ...effectiveSchedulerOptions,
                            enable_auto_throttle: e.target.checked,
                          })}
                        />
                        Reduir paral·lelisme si hi ha símptomes de saturació
                      </label>
                    </label>
                  </div>
                </>
              )}

              {configurationPanel === 'criticality' && (
                <>
                  <p className="mb-4 text-xs text-muted-foreground">
                    Cada check es pot reclassificar a crític, mitjà o baix abans d'executar l'auditoria.
                  </p>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {checks.map((check) => (
                      <label key={`criticality-${check.check_id}`} className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold uppercase tracking-wider ${checkSeverityTextColor(check.criticitat || check.severitat)}`}>{check.check_id}</span>
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${severityClass(resolveConfiguredCriticality(check.check_id, check.criticitat || check.severitat))}`}>
                            {resolveConfiguredCriticality(check.check_id, check.criticitat || check.severitat)}
                          </span>
                        </div>
                        <span className="text-sm font-semibold">{normalizeUiText(check.title || 'Configuració de criticitat')}</span>
                        <select
                          value={criticalityOverrides?.[check.check_id] || ''}
                          onChange={(e) => onCriticalityOverrideChange(check.check_id, e.target.value)}
                          className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                        >
                          <option value="">Backend base ({normalizeUiText(criticalityLabel(check.criticitat || check.severitat))})</option>
                          {CRITICALITY_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{normalizeUiText(option.label)}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          <div className="glass-card p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="space-y-1 text-sm text-muted-foreground">
                <p>
                  <span className="font-semibold text-foreground">Consultes llegides des de:</span>{' '}
                  <span className="font-mono">{normalizeUiText(result?.context?.source_file || 'Auditoria_post_crq.md')}</span>
                </p>
                <p>
                  <span className="font-semibold text-foreground">Ruta:</span>{' '}
                  <span className="font-mono text-xs">{normalizeUiText(result?.context?.source_path || '-')}</span>
                </p>
                <p>
                  <span className="font-semibold text-foreground">Temps total:</span> {summary.total_duration_ms || 0} ms
                  {' · '}
                  <span className="font-semibold text-foreground">Workers:</span> {summary.parallel_workers || 1}
                </p>
                <p>
                  <span className="font-semibold text-foreground">Scheduler:</span>{' '}
                  global {schedulerSummary.configured_max_concurrency || effectiveSchedulerOptions.max_concurrency}
                  {' · '}paral·lel real {schedulerSummary.max_parallel_observed || 1}
                  {' · '}pesades {schedulerSummary.max_parallel_by_category?.heavy ?? 0}
                </p>
                <p>
                  <span className="font-semibold text-foreground">Auto-throttle:</span>{' '}
                  {schedulerSummary.degraded_mode_triggered ? 'activat' : (effectiveSchedulerOptions.enable_auto_throttle ? 'armat' : 'desactivat')}
                  {' · '}
                  <span className="font-semibold text-foreground">Reintents usats:</span> {schedulerSummary.retries_used || 0}
                </p>
              </div>
              <button
                type="button"
                onClick={onDownloadQueries}
                disabled={!queryExport?.content}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-white/5 px-4 py-3 text-sm font-semibold transition-all hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Download size={16} />
                Descarregar consultes (.txt)
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 transition-all hover:bg-white/10">
              <p className="text-xs font-bold uppercase tracking-widest opacity-60">Troballes totals</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-black tracking-tight">{summary.total_findings || 0}</span>
                <span className="text-xs font-medium opacity-40">files</span>
              </div>
            </div>
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6 transition-all hover:bg-red-100 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-widest text-red-700">Crítics</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-black tracking-tight text-red-700">{criticalFindingsCount}</span>
              </div>
            </div>
            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/5 p-6 transition-all hover:bg-orange-500/10">
              <p className="text-xs font-bold uppercase tracking-widest text-orange-400/60">Mitjans</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-black tracking-tight text-orange-400">{mediumFindingsCount}</span>
              </div>
            </div>
            <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-6 transition-all hover:bg-blue-500/10">
              <p className="text-xs font-bold uppercase tracking-widest text-blue-400/60">Baixos</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-4xl font-black tracking-tight text-blue-400">{lowFindingsCount}</span>
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 transition-all hover:bg-white/10">
              <p className="text-xs font-bold uppercase tracking-widest opacity-60">Errors Execució</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className={`text-4xl font-black tracking-tight ${summary.error_count > 0 ? 'text-red-400' : ''}`}>
                  {summary.error_count || 0}
                </span>
              </div>
            </div>
          </div>

          {reportModel && (
            <>
              <div className="glass-card p-6">
                <div className="mb-4 flex items-center gap-2">
                  <Info size={18} className="text-primary" />
                  <h4 className="text-lg font-bold">Paràmetres d'execució</h4>
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div className="space-y-2 text-sm">
                    <p><span className="font-semibold text-foreground">Perfil:</span> {normalizeUiText(executionParameters?.profile || selectedProfile || '-')}</p>
                    <p><span className="font-semibold text-foreground">Data i hora:</span> {normalizeUiText(executionParameters?.generated_at || '-')}</p>
                    <p><span className="font-semibold text-foreground">Mode temporal:</span> {normalizeUiText(timeFilter.mode === 'range' ? 'rang de dates' : 'mode predefinit')}</p>
                    <p><span className="font-semibold text-foreground">Període aplicat:</span> {normalizeUiText(timeFilter.mode === 'range' ? `${timeFilter.start_date || '-'} -> ${timeFilter.end_date || '-'}` : PRESET_OPTIONS.find((option) => option.value === timeFilter.preset)?.label || '-')}</p>
                    <p><span className="font-semibold text-foreground">Finestra consultada:</span> {normalizeUiText(`${executionParameters?.time_window?.start_at || '-'} -> ${executionParameters?.time_window?.end_at || '-'}`)}</p>
                  </div>
                  <div className="space-y-2 text-sm">
                    <p><span className="font-semibold text-foreground">Idioma:</span> {normalizeUiText(executionParameters?.language || 'Català')}</p>
                    <p><span className="font-semibold text-foreground">Codificació:</span> {normalizeUiText(executionParameters?.encoding || 'UTF-8')}</p>
                    <p><span className="font-semibold text-foreground">Fitxer de checks:</span> {normalizeUiText(executionParameters?.source_file || result?.context?.source_file || '-')}</p>
                    <p><span className="font-semibold text-foreground">Lots o esquemes filtrats:</span> {normalizeUiText((executionParameters?.schemas || []).join(', ') || 'Tots')}</p>
                  </div>
                </div>
              </div>

              <div className="glass-card p-6">
                <button
                  type="button"
                  onClick={() => setShowLotSummary((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div className="flex items-center gap-2">
                    <Database size={18} className="text-primary" />
                    <h4 className="text-lg font-bold">Resum executiu per lots</h4>
                  </div>
                  {showLotSummary ? <ChevronUp size={18} className="text-muted-foreground" /> : <ChevronDown size={18} className="text-muted-foreground" />}
                </button>
                {showLotSummary && (
                  <>
                    <p className="mb-4 mt-4 text-sm text-muted-foreground">
                      Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes impactats, la prioritat i els checks que cal revisar primer.
                    </p>
                    {enrichedLotCards.length > 0 ? (
                  <div className="space-y-4">
                    {enrichedLotCards.map((lot) => (
                      <div key={`lot-summary-${lot.lot}`} className="rounded-[28px] border border-white/10 bg-white/5 p-6 shadow-sm shadow-black/5">
                        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                          <div className="min-w-0">
                            <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-muted-foreground">
                              Lot prioritzat
                            </p>
                            <h5 className="mt-2 text-3xl font-black tracking-tight text-foreground">
                              LOT {normalizeUiText(lot.lot || 'SENSE LOT')}
                            </h5>
                            <p className="mt-2 text-sm text-muted-foreground">
                              {lot.affected_objects || 0} objectes afectats
                            </p>
                          </div>
                          <span className={`inline-flex rounded-full border px-4 py-2 text-xs font-extrabold uppercase tracking-wide ${priorityBadgeClass(lot.priority)}`}>
                            Prioritat {normalizeUiText(lot.priority || 'Baix')}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                          <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4">
                            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-red-700">Crítiques</div>
                            <div className="mt-2 text-3xl font-black text-red-700">{lot.critical || 0}</div>
                          </div>
                          <div className="rounded-2xl border border-orange-200 bg-orange-50 px-5 py-4">
                            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-orange-700">Mitjanes</div>
                            <div className="mt-2 text-3xl font-black text-orange-700">{lot.medium || 0}</div>
                          </div>
                          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4">
                            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700">Baixes</div>
                            <div className="mt-2 text-3xl font-black text-blue-700">{lot.low || 0}</div>
                          </div>
                        </div>

                        <div className="mt-6">
                          <p className="text-xs font-bold uppercase tracking-[0.24em] text-muted-foreground">
                            Esquemes afectats
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {lot.schemasList.length > 0 ? (
                              lot.schemasList.map((schema) => (
                                <span
                                  key={`lot-schema-${lot.lot}-${schema}`}
                                  className="rounded-full border border-primary/15 bg-primary/10 px-3 py-1.5 text-sm font-semibold text-primary"
                                >
                                  {schema}
                                </span>
                              ))
                            ) : (
                              <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1.5 text-sm text-muted-foreground">
                                Sense esquema assignable
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="mt-6 rounded-2xl border border-white/10 bg-black/10 px-5 py-4 text-sm">
                          <p><span className="font-semibold text-foreground">Acció inicial:</span> {normalizeUiText(lot.first_action || '-')}</p>
                          <p className="mt-2"><span className="font-semibold text-foreground">Impacte principal:</span> {normalizeUiText(lot.dominant_impact || '-')}</p>
                        </div>

                        <div className="mt-6">
                          <div className="mb-3 flex items-center justify-between gap-3">
                            <p className="text-xs font-bold uppercase tracking-[0.24em] text-muted-foreground">
                              Checks afectats
                            </p>
                            <span className="text-xs text-muted-foreground">
                              {lot.checksForLot.length} checks
                            </span>
                          </div>
                          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                            {lot.checksForLot.map((check) => (
                              <article
                                key={`lot-check-${lot.lot}-${check.check_id}`}
                                className="rounded-2xl border border-white/10 bg-white/5 px-5 py-4"
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary">
                                      {check.check_id}
                                    </p>
                                    <h6 className="mt-2 text-sm font-extrabold uppercase tracking-wide text-foreground">
                                      {check.title}
                                    </h6>
                                  </div>
                                  <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase ${priorityBadgeClass(check.criticality)}`}>
                                    {normalizeUiText(check.criticality || 'Baix')}
                                  </span>
                                </div>
                                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                                  {check.overview}
                                </p>
                                {check.whyItMatters && (
                                  <p className="mt-3 text-sm leading-6 text-foreground/80">
                                    {check.whyItMatters}
                                  </p>
                                )}
                                {check.recommendedAction && (
                                  <div className="mt-4 rounded-2xl border border-primary/10 bg-primary/5 px-4 py-3">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <p className="text-[11px] font-black uppercase tracking-[0.2em] text-primary">
                                        Acció recomanada
                                      </p>
                                      {Number.isFinite(check.terminiDies) ? (
                                        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                          Termini {check.terminiDies} dies
                                        </span>
                                      ) : null}
                                    </div>
                                    <p className="mt-2 text-sm leading-6 text-foreground/85">
                                      {check.recommendedAction}
                                    </p>
                                  </div>
                                )}
                              </article>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                    ) : (
                      <p className="mt-4 text-sm text-muted-foreground">No s'han detectat lots amb incidències en aquesta execució.</p>
                    )}
                  </>
                )}
              </div>

              <div className="glass-card p-6">
                <button
                  type="button"
                  onClick={() => setShowLotIncidents((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={18} className="text-primary" />
                    <h4 className="text-lg font-bold">Incidències prioritzades per lot</h4>
                  </div>
                  {showLotIncidents ? <ChevronUp size={18} className="text-muted-foreground" /> : <ChevronDown size={18} className="text-muted-foreground" />}
                </button>
                {showLotIncidents && (
                  <>
                    {lotIncidentGroups.length > 0 ? (
                      <div className="mt-4 space-y-6">
                        {lotIncidentGroups.map((group) => renderLotIncidentCard(group))}
                      </div>
                    ) : (
                      <p className="mt-4 text-sm text-muted-foreground">No hi ha incidències prioritzades per lot en aquesta execució.</p>
                    )}
                  </>
                )}
              </div>

              {finalObservations && (
                <div className="glass-card p-6">
                  <div className="mb-4 flex items-center gap-2">
                    <Info size={18} className="text-primary" />
                    <h4 className="text-lg font-bold">Observacions finals</h4>
                  </div>
                  {(finalObservations.blocking_errors || []).length > 0 && (
                    <div className="mb-4">
                      <p className="mb-2 text-sm font-semibold">Bloquejos</p>
                      <ul className="space-y-2 text-sm text-muted-foreground">
                        {(finalObservations.blocking_errors || []).map((item) => (
                          <li key={`blocking-${item.check_id}`}><span aria-hidden="true">{'\u2022'}</span> <span className="font-semibold text-foreground">{item.check_id}</span>: {normalizeUiText(item.error || 'Error no detallat')}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(finalObservations.warnings || []).length > 0 && (
                    <div className="mb-4">
                      <p className="mb-2 text-sm font-semibold">Advertiments</p>
                      <ul className="space-y-2 text-sm text-muted-foreground">
                        {(finalObservations.warnings || []).map((item, index) => (
                          <li key={`warning-${index}`}><span aria-hidden="true">{'\u2022'}</span> {normalizeUiText(item)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(finalObservations.next_steps || []).length > 0 && (
                    <div>
                      <p className="mb-2 text-sm font-semibold">Següents passos</p>
                      <ul className="space-y-2 text-sm text-muted-foreground">
                        {(finalObservations.next_steps || []).map((item, index) => (
                          <li key={`next-step-${index}`}><span aria-hidden="true">{'\u2022'}</span> {normalizeUiText(item)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <div className="glass-card p-6">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-primary/20 text-primary">
                  <FileSearch size={20} />
                </div>
                <h4 className="text-xl font-bold">Detall tècnic per check</h4>
              </div>
              <button
                type="button"
                onClick={() => setShowTechnicalDetail((current) => !current)}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-bold transition-all hover:bg-white/10"
              >
                {showTechnicalDetail ? 'Amagar detall' : 'Mostrar detall'}
              </button>
            </div>

            {showTechnicalDetail && (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-white/10 text-[10px] uppercase text-muted-foreground">
                      <tr>
                        <th className="pb-3">Check</th>
                        <th className="pb-3">Títol</th>
                        <th className="pb-3">Criticitat</th>
                        <th className="pb-3">Estat</th>
                        <th className="pb-3 text-right">Temps</th>
                        <th className="pb-3 text-right">Files</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {technicalCheckRows.map((item) => (
                        <tr key={item.check_id} className="hover:bg-white/5">
                          <td className={`py-3 font-mono text-xs font-bold ${checkSeverityTextColor(criticalityOverrides?.[item.check_id] || item.criticitat || item.severitat || item.criticality)}`}>{item.check_id}</td>
                          <td className="py-3">{normalizeUiText(item.title)}</td>
                          <td className="py-3">
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${severityClass(criticalityOverrides?.[item.check_id] || item.criticitat || item.severitat || item.criticality)}`}>
                              {resolveConfiguredCriticality(item.check_id, item.criticitat || item.severitat || item.criticality)}
                            </span>
                          </td>
                          <td className="py-3">
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusClass(item.status)}`}>
                              {item.status}
                            </span>
                          </td>
                          <td className="py-3 text-right font-mono">{humanizeDuration(item.duration_ms || 0)}</td>
                          <td className="py-3 text-right font-mono">{item.row_count || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-8 space-y-6">
                  {technicalResults.map((item) => {
                    const columns = visibleTechnicalColumns(item);
                    return (
                    <div key={item.check_id} className="glass-card p-6">
                      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className={`text-lg font-bold ${checkSeverityTextColor(criticalityOverrides?.[item.check_id] || item.criticitat || item.severitat || item.criticality)}`}>{item.check_id}</h4>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${severityClass(criticalityOverrides?.[item.check_id] || item.criticitat || item.severitat || item.criticality)}`}>
                              {resolveConfiguredCriticality(item.check_id, item.criticitat || item.severitat || item.criticality)}
                            </span>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusClass(item.status)}`}>
                              {item.status}
                            </span>
                          </div>
                          <p className="mt-1 text-base font-semibold">{normalizeUiText(item.title)}</p>
                          {item.criteri && (
                            <p className="mt-1 text-xs text-muted-foreground">{normalizeUiText(item.criteri)}</p>
                          )}
                        </div>

                        <div className="flex flex-wrap gap-2 text-xs">
                          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                            Files: {item.row_count || 0}
                          </span>
                          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                            Temps: {humanizeDuration(item.duration_ms || 0)}
                          </span>
                        </div>
                      </div>

                      {item.error && (
                        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">
                          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                          <span>{item.error}</span>
                        </div>
                      )}

                      {(item.rows || []).length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead className="border-b border-white/10 text-[10px] uppercase text-muted-foreground">
                              <tr>
                                {columns.map((column) => (
                                  <th key={column} className="pb-3 pr-3">{column}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                              {(item.rows || []).slice(0, 100).map((row, idx) => (
                                <tr key={`${item.check_id}-${idx}`} className="hover:bg-white/5">
                                  {columns.map((column) => (
                                    <td key={column} className="py-3 pr-3 align-top">
                                      {row[column] === null || row[column] === undefined || row[column] === '' ? '-' : normalizeUiText(row[column])}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {(item.rows || []).length > 100 && (
                            <p className="mt-3 text-xs italic text-muted-foreground">
                              Es mostren les primeres 100 files de {item.rows.length}.
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="rounded-xl border border-dashed border-white/10 bg-white/5 p-6 text-center text-sm italic text-muted-foreground">
                          Sense troballes per aquest check.
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {showDocs && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 md:p-10">
          <div 
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setShowDocs(false)}
          />
          <div className="relative glass-card w-full max-w-5xl h-full flex flex-col overflow-hidden animate-in fade-in zoom-in duration-300">
            <div className="flex items-center justify-between p-6 border-b border-white/10 bg-white/5">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-primary/20 text-primary">
                  <Info size={20} />
                </div>
                <div>
                  <h4 className="text-lg font-bold">Documentació Tècnica: Sistema d'Auditoria</h4>
                  <p className="text-xs text-muted-foreground italic">Vista prèvia del fitxer AUDITORIA_BBDD_DOC.md</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setShowDocs(false)}
                  className="p-2 rounded-xl hover:bg-white/10 text-muted-foreground transition-all"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-8 prose prose-invert prose-primary max-w-none">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({node, ...props}) => <h1 className="text-4xl font-black mb-10 text-primary border-b-4 border-primary pb-4 inline-block" {...props} />,
                  h2: ({node, ...props}) => <h2 className="text-2xl font-bold mt-12 mb-6 flex items-center gap-2 border-l-4 border-primary pl-4" {...props} />,
                  h3: ({node, ...props}) => <h3 className="text-xl font-bold mt-8 mb-4 text-primary/80" {...props} />,
                  pre: ({node, ...props}) => <pre className="bg-black/50 border border-white/10 p-4 rounded-xl font-mono text-sm my-6 overflow-x-auto" {...props} />,
                  code: ({ node, inline, className, children, ...props }) => {
                    const match = /language-(\w+)/.exec(className || '');
                    if (!inline && match && match[1] === 'mermaid') {
                      return <MermaidChart chart={String(children).replace(/\n$/, '')} />;
                    }
                    return inline
                      ? <code className="bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold text-[0.9em]" {...props}>{children}</code>
                      : <code className={className} {...props}>{children}</code>;
                  },
                  blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-white/20 pl-6 my-8 italic text-muted-foreground bg-white/5 p-4 rounded-r-xl" {...props} />,
                  table: ({node, ...props}) => (
                    <div className="overflow-x-auto my-8">
                      <table className="w-full border-collapse border border-white/10 text-sm" {...props} />
                    </div>
                  ),
                  th: ({node, ...props}) => <th className="border border-white/10 bg-white/10 p-3 font-bold text-left" {...props} />,
                  td: ({node, ...props}) => <td className="border border-white/10 p-3" {...props} />,
                  ul: ({node, ...props}) => <ul className="space-y-2 my-6 list-disc list-inside" {...props} />,
                  li: ({node, ...props}) => <li className="text-muted-foreground" {...props} />,
                }}
              >
                {docContent}
              </ReactMarkdown>
            </div>

            <div className="p-4 bg-white/5 border-t border-white/10 flex justify-end gap-3">
              <button 
                onClick={() => setShowDocs(false)}
                className="bg-white/10 hover:bg-white/20 px-6 py-2 rounded-xl font-bold text-sm transition-all"
              >
                Tancar
              </button>
            </div>
          </div>
        </div>
      )}

      {showHelp && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 md:p-10">
          <div 
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setShowHelp(false)}
          />
          <div className="relative glass-card w-full max-w-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-300">
            <div className="flex items-center justify-between p-6 border-b border-white/10 bg-white/5">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-primary/20 text-primary">
                  <Info size={20} />
                </div>
                <div>
                  <h4 className="text-lg font-bold">Com utilitzar aquesta pàgina?</h4>
                  <p className="text-xs text-muted-foreground">Guia ràpida de l'auditoria Post-CRQ</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setShowHelp(false)}
                  className="p-2 rounded-xl hover:bg-white/10 text-muted-foreground transition-all"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            <div className="p-8 prose prose-invert max-w-none text-sm space-y-4">
              <p>Aquesta pantalla permet avaluar la qualitat de dades un cop s'hi ha aplicat un desplegament (CRQ).</p>
              
              <ul className="space-y-3">
                <li>
                  <strong className="text-primary">1. Sincronitzar (Refresh):</strong> Utilitza el botó blau de <strong className="text-blue-400 border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 rounded text-xs ml-1">Sinc. Checks</strong> per tornar a llegir i carregar els checks des dels fitxers Markdown (<code>auditoria_post_crq.md</code>) on hi ha definides les proves de qualitat.
                </li>
                <li>
                  <strong className="text-primary">2. BBDD i Esquemes:</strong> Selecciona l'entorn on vols avaluar el codi i opcionalment afegeix els filtres d'esquema (ex. <code>APP_USER, CORE_DB</code>).
                </li>
                <li>
                  <strong className="text-primary">3. Selecció:</strong> Marca únicament els checks que t'interessa provar de la taula <strong>Selecció de checks</strong>.
                </li>
                <li>
                  <strong className="text-primary">4. Configuració (Opcional):</strong> Fes clic a <em>Obrir configuració</em> per escalar el grau de <span className="text-red-400">Criticitat</span> (Si vols fer un check concret més exigent) o programar el <span className="text-yellow-200">Paral·lelisme</span> si notes l'auditoria molt lenta i la BBDD té capacitat.
                </li>
                <li>
                  <strong className="text-primary">5. Detall i KPIs:</strong> Segons els resultats, la pantalla mostrarà de forma visual quants registres "incompleixen" la norma definida al fitxer en verd i en vermell, generant un <code>Post-CRQ Report</code> en format taula i targetes.
                </li>
              </ul>

              <div className="mt-6 flex justify-end gap-2 p-4 bg-white/5 border border-white/10 rounded-xl">
                <button
                  type="button"
                  onClick={() => {
                    setShowHelp(false);
                    fetchDocs();
                  }}
                  disabled={isDocsLoading}
                  className="flex items-center gap-1.5 text-xs font-bold text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <FileSearch size={14} />
                  {isDocsLoading ? 'Carregant documentacio tecnica...' : 'Veure la Documentació Tècnica (Arquitectura BBDD Doc)'}
                </button>
              </div>
            </div>
            
            <div className="p-4 bg-white/5 border-t border-white/10 flex justify-end gap-3">
              <button 
                onClick={() => setShowHelp(false)}
                className="bg-primary text-primary-foreground hover:brightness-110 px-6 py-2 rounded-xl font-bold text-sm transition-all"
              >
                Entesos
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}




