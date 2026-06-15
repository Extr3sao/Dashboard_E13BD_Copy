import { useCallback, useEffect, useState } from 'react';
import {
  getAutomationMaintenanceSummary,
  getAutomationRunReportData,
  getAutomationRunReportUrl,
  getDeliveryRoutes,
  listAutomationChangeEvents,
  listAutomationJobs,
  listAutomationRuns,
  listDeliveryTemplates,
  listLotRoutes,
  listMasterLotBackfillRuns,
  listMasterLots,
  listRetryQueue,
  listSchemaLots,
} from '../api/automation.js';
import { listPostCrqChecks } from '../api/postCrqAudit.js';
import { AUTOMATION_SCREENS } from '../config/automationViewConfig.js';
import { useAutomationAnalytics } from './useAutomationAnalytics.js';
import { useAutomationHistoryRetries } from './useAutomationHistoryRetries.js';
import { useAutomationJobs } from './useAutomationJobs.js';
import { useAutomationLots } from './useAutomationLots.js';
import { useAutomationNavigation } from './useAutomationNavigation.js';
import { useAutomationRoutesTemplates } from './useAutomationRoutesTemplates.js';
import {
  buildAutomationHelpUrl,
  deliveryAudienceLabel,
  deliveryResultLabel,
  formFromJob,
  lotStatusClass,
  lotStatusLabel,
  resolveRequestErrorMessage,
  runLotSummary,
  runStatusClass,
  runStatusLabel,
  splitCsv,
  templateKeyDescription,
  templateKeyLabel,
  yesNo,
} from '../utils/automationViewUtils.js';

export function useAutomationViewModel(profiles, options = {}) {
  const { onOpenPostCrqRun } = options;
  const [jobs, setJobs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [checks, setChecks] = useState([]);
  const [deliveryRoutes, setDeliveryRoutes] = useState({ tic_summary_recipients: [], providers: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const {
    automationSection,
    helpOpen,
    openSections,
    registerSection,
    sectionRefs,
    setAllSectionsOpen,
    setAutomationSection,
    setHelpOpen,
    toggleSection,
  } = useAutomationNavigation();

  const {
    analyticsChecks,
    analyticsLoading,
    analyticsLots,
    analyticsMonth,
    analyticsOverview,
    analyticsSchemas,
    handleExportAnalyticsPdf,
    refreshAnalytics,
    setAnalyticsMonth,
  } = useAutomationAnalytics(setError);

  const {
    changeEvents,
    expandedRunId,
    handleEnqueueRetry: enqueueRunRetry,
    handleExportRunCsv,
    handlePurgeHistory: purgeHistory,
    handlePurgeRetryQueue: purgeRetryQueue,
    handleRunRetryNow: runRetryFromQueue,
    hydrateHistoryData,
    loadingRunLotsId,
    maintenanceSummary,
    refreshMaintenanceSummary,
    refreshRunLots,
    retentionDays,
    retryQueue,
    runLotFilter,
    runLotsById,
    setRetentionDays,
    setRunLotFilter,
    toggleRunLots,
  } = useAutomationHistoryRetries({ setError, setMessage });

  const {
    applyingBackfill,
    backfillPreview,
    backfillSelection,
    emptyMasterLot,
    emptySchemaLot,
    exportSchemaLotsCsv,
    filteredSchemaLots,
    handleApplyBackfill: applyBackfill,
    handlePreviewBackfill: previewBackfill,
    hydrateLotsData,
    masterLotCodes,
    masterLots,
    previewingBackfill,
    saveMasterLots: persistMasterLots,
    saveSchemaLots: persistSchemaLots,
    schemaLotFilter,
    schemaLotOptions,
    schemaLotValidation,
    schemaLots,
    setBackfillSelection,
    setMasterLots,
    setSchemaLotFilter,
    setSchemaLots,
  } = useAutomationLots({ setError, setMessage });

  const {
    emptyRoute,
    emptyTemplate,
    hydrateRoutesTemplatesData,
    lotRoutes,
    saveLotRoutes: persistLotRoutes,
    saveTemplates: persistTemplates,
    setLotRoutes,
    setTemplates,
    templates,
  } = useAutomationRoutesTemplates({ setError, setMessage });

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [jobsRes, runsRes, checksRes, routesRes, masterLotsRes, schemaLotsRes, backfillRunsRes, lotRoutesRes, templatesRes, changeEventsRes, retryQueueRes, maintenanceRes] = await Promise.all([
        listAutomationJobs(),
        listAutomationRuns(null, 40),
        listPostCrqChecks(),
        getDeliveryRoutes(),
        listMasterLots(false),
        listSchemaLots(),
        listMasterLotBackfillRuns(10),
        listLotRoutes(),
        listDeliveryTemplates(),
        listAutomationChangeEvents({ limit: 30 }),
        listRetryQueue({ limit: 40 }),
        getAutomationMaintenanceSummary(retentionDays),
      ]);
      setJobs(jobsRes.items || []);
      setRuns(runsRes.items || []);
      setChecks(checksRes.checks || []);
      setDeliveryRoutes(routesRes || { tic_summary_recipients: [], providers: [] });
      hydrateLotsData({
        masterLotsItems: masterLotsRes.items || [],
        schemaLotsItems: schemaLotsRes.items || [],
        backfillRun: (backfillRunsRes.items || [])[0] || null,
      });
      hydrateRoutesTemplatesData({
        lotRoutesItems: lotRoutesRes.items || [],
        templateItems: templatesRes.items || [],
      });
      hydrateHistoryData({
        changeEventsItems: changeEventsRes.items || [],
        retryQueueItems: retryQueueRes.items || [],
        maintenanceSummaryItem: maintenanceRes || null,
      });
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Error carregant automatitzacions');
    } finally {
      setLoading(false);
    }
  }, [hydrateHistoryData, hydrateLotsData, hydrateRoutesTemplatesData, retentionDays]);

  const {
    editingJobId,
    form,
    handleDeleteJob,
    handleRunNow,
    handleSaveJob,
    handleToggleJob,
    resetForm,
    saving,
    setEditingJobId,
    setForm,
  } = useAutomationJobs({ profiles, refreshAll, setError, setMessage, splitCsv });

  const saveSchemaLots = useCallback(() => persistSchemaLots(refreshAll), [persistSchemaLots, refreshAll]);
  const saveMasterLots = useCallback(() => persistMasterLots(refreshAll), [persistMasterLots, refreshAll]);
  const handlePreviewBackfill = useCallback(() => previewBackfill(refreshAll), [previewBackfill, refreshAll]);
  const handleApplyBackfill = useCallback(() => applyBackfill(refreshAll), [applyBackfill, refreshAll]);
  const handleEnqueueRetry = useCallback((runId, lot, audience) => enqueueRunRetry(runId, lot, audience, refreshAll), [enqueueRunRetry, refreshAll]);
  const handleRunRetryNow = useCallback((queueId) => runRetryFromQueue(queueId, refreshAll), [refreshAll, runRetryFromQueue]);
  const handlePurgeHistory = useCallback(() => purgeHistory(refreshAll), [purgeHistory, refreshAll]);
  const handlePurgeRetryQueue = useCallback(() => purgeRetryQueue(refreshAll), [purgeRetryQueue, refreshAll]);
  const saveLotRoutes = useCallback(() => persistLotRoutes(refreshAll), [persistLotRoutes, refreshAll]);
  const saveTemplates = useCallback(() => persistTemplates(refreshAll), [persistTemplates, refreshAll]);
  const handleOpenRunSnapshot = useCallback(async (run) => {
    if (typeof onOpenPostCrqRun !== 'function') {
      return;
    }
    setError('');
    try {
      const reportData = await getAutomationRunReportData(run.id);
      onOpenPostCrqRun({ action: 'snapshot', run, reportData });
    } catch (err) {
      setError(await resolveRequestErrorMessage(err, "No s'ha pogut carregar el snapshot del run."));
    }
  }, [onOpenPostCrqRun, setError]);
  const handleRerunLiveFromHistory = useCallback(async (run) => {
    if (typeof onOpenPostCrqRun !== 'function') {
      return;
    }
    setError('');
    try {
      const reportData = await getAutomationRunReportData(run.id);
      onOpenPostCrqRun({ action: 'live', run, reportData });
    } catch (err) {
      setError(await resolveRequestErrorMessage(err, "No s'ha pogut preparar la reexecució en viu."));
    }
  }, [onOpenPostCrqRun, setError]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    refreshMaintenanceSummary();
  }, [refreshMaintenanceSummary]);

  const openHelpInNewWindow = () => {
    window.open(buildAutomationHelpUrl(), '_blank', 'noopener,noreferrer');
  };

  const currentScreen = AUTOMATION_SCREENS.find((screen) => screen.id === automationSection) || AUTOMATION_SCREENS[0];
  const isDashboardScreen = automationSection === 'dashboard';
  const isJobsScreen = automationSection === 'jobs';
  const isLotsScreen = automationSection === 'lots';
  const isRecipientsScreen = automationSection === 'recipients';
  const isTemplatesScreen = automationSection === 'templates';
  const isHistoryScreen = automationSection === 'history';
  const isRetriesScreen = automationSection === 'retries';
  const recipientsOpen = isRecipientsScreen || openSections.lot_routes;
  const templatesOpen = isTemplatesScreen || openSections.templates;
  const auditOpen = isHistoryScreen || openSections.audit;
  const historyOpen = isHistoryScreen || openSections.history;
  const retryOpen = isRetriesScreen || openSections.retry;

  return {
    analyticsChecks,
    analyticsLoading,
    analyticsLots,
    analyticsMonth,
    analyticsOverview,
    analyticsSchemas,
    applyingBackfill,
    auditOpen,
    automationSection,
    backfillPreview,
    backfillSelection,
    changeEvents,
    checks,
    currentScreen,
    deliveryAudienceLabel,
    deliveryResultLabel,
    deliveryRoutes,
    editingJobId,
    emptyMasterLot,
    emptyRoute,
    emptySchemaLot,
    emptyTemplate,
    error,
    expandedRunId,
    exportSchemaLotsCsv,
    filteredSchemaLots,
    form,
    formFromJob,
    getAutomationRunReportUrl,
    handleOpenRunSnapshot,
    handleRerunLiveFromHistory,
    handleApplyBackfill,
    handleDeleteJob,
    handleEnqueueRetry,
    handleExportAnalyticsPdf,
    handleExportRunCsv,
    handlePreviewBackfill,
    handlePurgeHistory,
    handlePurgeRetryQueue,
    handleRunNow,
    handleRunRetryNow,
    handleSaveJob,
    handleToggleJob,
    helpOpen,
    historyOpen,
    isDashboardScreen,
    isHistoryScreen,
    isJobsScreen,
    isLotsScreen,
    isRecipientsScreen,
    isRetriesScreen,
    isTemplatesScreen,
    jobs,
    loading,
    loadingRunLotsId,
    lotRoutes,
    lotStatusClass,
    lotStatusLabel,
    masterLotCodes,
    masterLots,
    maintenanceSummary,
    message,
    openHelpInNewWindow,
    openSections,
    previewingBackfill,
    profiles,
    recipientsOpen,
    refreshAll,
    refreshAnalytics,
    refreshRunLots,
    registerSection,
    resetForm,
    retentionDays,
    retryOpen,
    retryQueue,
    runLotFilter,
    runLotSummary,
    runLotsById,
    runStatusClass,
    runStatusLabel,
    runs,
    saveLotRoutes,
    saveMasterLots,
    saveSchemaLots,
    saveTemplates,
    saving,
    schemaLotFilter,
    schemaLotOptions,
    schemaLotValidation,
    schemaLots,
    sectionRefs,
    setAllSectionsOpen,
    setAnalyticsMonth,
    setAutomationSection,
    setBackfillSelection,
    setEditingJobId,
    setForm,
    setHelpOpen,
    setLotRoutes,
    setMasterLots,
    setRetentionDays,
    setRunLotFilter,
    setSchemaLotFilter,
    setSchemaLots,
    setTemplates,
    templateKeyDescription,
    templateKeyLabel,
    templates,
    templatesOpen,
    toggleRunLots,
    toggleSection,
    yesNo,
  };
}
