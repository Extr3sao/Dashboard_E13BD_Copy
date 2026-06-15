import { useEffect, useRef, useState } from 'react';

import { listPostCrqChecks, runPostCrqAudit } from '../api/postCrqAudit.js';
import {
  derivePostCrqExecutionConfigFromReport,
  normalizePostCrqCriticalityOverrides,
  normalizePostCrqSchedulerOptions,
} from '../utils/automationViewUtils.js';

const SCHEDULER_STORAGE_KEY = 'postCrqSchedulerOptions';
const CRITICALITY_STORAGE_KEY = 'postCrqCriticalityOverrides';
const CRITICALITY_MIGRATION_KEY = 'postCrqCriticalityOverridesVersion';
const CRITICALITY_MIGRATION_VERSION = '2026-04-20';
const LEGACY_IMPLICIT_OVERRIDES = {
  CHECK_03: 'CRITIC',
  CHECK_04: 'CRITIC',
};

function parseStoredJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback;
  } catch (_error) {
    return fallback;
  }
}

function shouldDropLegacyCriticalityOverrides(value) {
  const normalized = normalizePostCrqCriticalityOverrides(value);
  const normalizedLegacy = normalizePostCrqCriticalityOverrides(LEGACY_IMPLICIT_OVERRIDES);
  const keys = Object.keys(normalized);
  const legacyKeys = Object.keys(normalizedLegacy);
  if (keys.length !== legacyKeys.length) {
    return false;
  }
  return legacyKeys.every((key) => normalized[key] === normalizedLegacy[key]);
}

export default function usePostCrqAudit({
  activeTab,
  databaseAuditSubtab,
  selectedProfile,
  defaultTimeFilter,
  defaultSchedulerOptions,
  defaultCriticalityOverrides,
}) {
  const [postCrqChecks, setPostCrqChecks] = useState([]);
  const [selectedChecks, setSelectedChecks] = useState([]);
  const [postCrqSchemas, setPostCrqSchemas] = useState('');
  const [postCrqTimeFilter, setPostCrqTimeFilter] = useState(defaultTimeFilter);
  const [postCrqChecksLoading, setPostCrqChecksLoading] = useState(false);
  const [isPostCrqRunning, setIsPostCrqRunning] = useState(false);
  const [postCrqReportData, setPostCrqReportData] = useState(null);
  const [postCrqError, setPostCrqError] = useState('');
  const [postCrqExecutionOrigin, setPostCrqExecutionOrigin] = useState(null);
  const [postCrqSchedulerOptions, setPostCrqSchedulerOptions] = useState(() => {
    return normalizePostCrqSchedulerOptions(
      parseStoredJson(SCHEDULER_STORAGE_KEY, {}),
      defaultSchedulerOptions,
    );
  });
  const [postCrqCriticalityOverrides, setPostCrqCriticalityOverrides] = useState(() => {
    const migrationVersion = localStorage.getItem(CRITICALITY_MIGRATION_KEY);
    const storedOverrides = parseStoredJson(CRITICALITY_STORAGE_KEY, {});
    if (migrationVersion !== CRITICALITY_MIGRATION_VERSION) {
      localStorage.setItem(CRITICALITY_MIGRATION_KEY, CRITICALITY_MIGRATION_VERSION);
      if (shouldDropLegacyCriticalityOverrides(storedOverrides)) {
        localStorage.removeItem(CRITICALITY_STORAGE_KEY);
        return normalizePostCrqCriticalityOverrides(defaultCriticalityOverrides);
      }
    }
    return normalizePostCrqCriticalityOverrides({
      ...defaultCriticalityOverrides,
      ...storedOverrides,
    });
  });
  const queryDownloadCacheRef = useRef(new Map());

  useEffect(() => {
    queryDownloadCacheRef.current.clear();
  }, [postCrqReportData, selectedProfile]);

  function fetchPostCrqChecks() {
    setPostCrqChecksLoading(true);
    setPostCrqError('');
    listPostCrqChecks()
      .then((res) => {
        const checks = res.checks || [];
        setPostCrqChecks(checks);
        setSelectedChecks((current) => (
          current.filter((item) => checks.some((check) => check.check_id === item))
        ));
        setPostCrqChecksLoading(false);
      })
      .catch((err) => {
        setPostCrqError(err?.response?.data?.detail || err.message || 'Error carregant checks post-CRQ');
        setPostCrqChecksLoading(false);
      });
  }

  useEffect(() => {
    if (activeTab === 'Auditoria BBDD' && databaseAuditSubtab === 'Auditoria de canvis' && postCrqChecks.length === 0) {
      listPostCrqChecks()
        .then((res) => {
          const checks = res.checks || [];
          setPostCrqChecks(checks);
          setSelectedChecks((current) => current.filter((item) => checks.some((check) => check.check_id === item)));
        })
        .catch((err) => {
          setPostCrqError(err?.response?.data?.detail || err.message || 'Error carregant checks post-CRQ');
        });
    }
  }, [activeTab, databaseAuditSubtab, postCrqChecks.length]);

  useEffect(() => {
    localStorage.setItem(SCHEDULER_STORAGE_KEY, JSON.stringify(postCrqSchedulerOptions));
  }, [postCrqSchedulerOptions]);

  useEffect(() => {
    localStorage.setItem(CRITICALITY_STORAGE_KEY, JSON.stringify(postCrqCriticalityOverrides));
  }, [postCrqCriticalityOverrides]);

  function executePostCrqAudit(config, executionOrigin) {
    const profile = config?.profile || selectedProfile;
    const selectedChecksForRun = config?.selected_checks || selectedChecks;
    const schemasForRun = Array.isArray(config?.schemas)
      ? config.schemas
      : postCrqSchemas.split(',').map((item) => item.trim()).filter(Boolean);
    const timeFilterForRun = config?.time_filter || postCrqTimeFilter;
    const criticalityOverridesForRun = normalizePostCrqCriticalityOverrides(
      config?.criticality_overrides || postCrqCriticalityOverrides,
    );
    const schedulerOptionsForRun = normalizePostCrqSchedulerOptions(
      config?.scheduler_options || postCrqSchedulerOptions,
      defaultSchedulerOptions,
    );

    if (!profile) return alert('Selecciona una base de dades.');
    if (selectedChecksForRun.length === 0) return alert('Selecciona almenys un check.');
    if (timeFilterForRun.mode === 'range' && (!timeFilterForRun.start_date || !timeFilterForRun.end_date)) {
      return alert('Indica data inici i data fi per al rang personalitzat.');
    }

    setIsPostCrqRunning(true);
    setPostCrqError('');
    setPostCrqReportData(null);
    setPostCrqExecutionOrigin(executionOrigin || null);

    runPostCrqAudit({
      profile,
      schemas: schemasForRun,
      time_filter: timeFilterForRun,
      selected_checks: selectedChecksForRun,
      criticality_overrides: criticalityOverridesForRun,
      scheduler_options: schedulerOptionsForRun,
    })
      .then((res) => {
        setPostCrqReportData(res);
        setIsPostCrqRunning(false);
      })
      .catch((err) => {
        setPostCrqError(err?.response?.data?.detail || err.message || 'Error executant auditoria post-CRQ');
        setIsPostCrqRunning(false);
      });
  }

  function handleRunPostCrqAudit() {
    executePostCrqAudit(null, {
      mode: 'manual_live',
      label: 'Execució en viu',
      warning: "Aquesta execució consulta Oracle en viu. Repetir la mateixa finestra més tard pot donar un resultat diferent.",
    });
  }

  function resetPostCrqCriticalityOverrides() {
    setPostCrqCriticalityOverrides({});
  }

  function applyPostCrqExecutionConfig(config, options = {}) {
    const nextConfig = config || {};
    setSelectedChecks(nextConfig.selected_checks || []);
    setPostCrqSchemas(Array.isArray(nextConfig.schemas) ? nextConfig.schemas.join(', ') : '');
    setPostCrqTimeFilter({ ...defaultTimeFilter, ...(nextConfig.time_filter || {}) });
    setPostCrqSchedulerOptions(normalizePostCrqSchedulerOptions(nextConfig.scheduler_options || {}, defaultSchedulerOptions));
    setPostCrqCriticalityOverrides(normalizePostCrqCriticalityOverrides(nextConfig.criticality_overrides || {}));
    setPostCrqReportData(options.reportData || null);
    setPostCrqError('');
    setPostCrqExecutionOrigin(options.executionOrigin || null);
  }

  function openPostCrqSnapshot(reportData, fallback = {}) {
    const config = derivePostCrqExecutionConfigFromReport(reportData, fallback);
    applyPostCrqExecutionConfig(config, {
      reportData,
      executionOrigin: {
        mode: 'snapshot',
        label: 'Snapshot del run',
        warning: "Aquest resultat surt del snapshot guardat del run automàtic. Les xifres s'han de considerar la referència històrica exacta.",
        generatedAt: config.generated_at || '',
      },
    });
  }

  function rerunPostCrqAuditFromSnapshot(reportData, fallback = {}) {
    const config = derivePostCrqExecutionConfigFromReport(reportData, fallback);
    applyPostCrqExecutionConfig(config, {
      reportData: null,
      executionOrigin: {
        mode: 'live_rerun',
        label: 'Reexecució en viu',
        warning: "Aquesta reexecució torna a consultar Oracle en viu. Pot diferir del run històric encara que la finestra sigui la mateixa.",
        generatedAt: config.generated_at || '',
      },
    });
    executePostCrqAudit(config, {
      mode: 'live_rerun',
      label: 'Reexecució en viu',
      warning: "Aquesta reexecució torna a consultar Oracle en viu. Pot diferir del run històric encara que la finestra sigui la mateixa.",
      generatedAt: config.generated_at || '',
    });
  }

  function handleDownloadPostCrqQueries() {
    const queryExport = postCrqReportData?.query_export;
    if (!queryExport?.content) {
      return alert("Encara no hi ha consultes exportables. Executa primer l'auditoria.");
    }

    const fileName = queryExport.filename || `consultes_post_crq_${selectedProfile || 'perfil'}.txt`;
    const cacheKey = JSON.stringify({
      fileName,
      content: queryExport.content,
    });
    const cached = queryDownloadCacheRef.current.get(cacheKey);
    const blob = cached || new Blob([queryExport.content], { type: 'text/plain;charset=utf-8' });
    if (!cached) {
      queryDownloadCacheRef.current.set(cacheKey, blob);
    }
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  return {
    postCrqChecks,
    selectedChecks,
    setSelectedChecks,
    postCrqSchemas,
    setPostCrqSchemas,
    postCrqTimeFilter,
    setPostCrqTimeFilter,
    postCrqChecksLoading,
    isPostCrqRunning,
    postCrqReportData,
    postCrqError,
    postCrqExecutionOrigin,
    postCrqSchedulerOptions,
    setPostCrqSchedulerOptions,
    postCrqCriticalityOverrides,
    setPostCrqCriticalityOverrides,
    fetchPostCrqChecks,
    handleRunPostCrqAudit,
    handleDownloadPostCrqQueries,
    resetPostCrqCriticalityOverrides,
    applyPostCrqExecutionConfig,
    openPostCrqSnapshot,
    rerunPostCrqAuditFromSnapshot,
  };
}
