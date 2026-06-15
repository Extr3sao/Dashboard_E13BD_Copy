import { useCallback, useEffect, useRef, useState } from 'react';
import {
  enqueueRetry,
  exportAutomationRunLotsCsv,
  getAutomationMaintenanceSummary,
  listAutomationRunLotsFiltered,
  purgeAutomationHistory,
  purgeAutomationRetryQueue,
  runRetryNow,
} from '../api/automation.js';
import { downloadBlob, resolveRequestErrorMessage } from '../utils/automationViewUtils.js';

export function useAutomationHistoryRetries({ setError, setMessage }) {
  const [changeEvents, setChangeEvents] = useState([]);
  const [retryQueue, setRetryQueue] = useState([]);
  const [maintenanceSummary, setMaintenanceSummary] = useState(null);
  const [retentionDays, setRetentionDays] = useState(30);
  const [runLotsById, setRunLotsById] = useState({});
  const [expandedRunId, setExpandedRunId] = useState(null);
  const [loadingRunLotsId, setLoadingRunLotsId] = useState(null);
  const [runLotFilter, setRunLotFilter] = useState({ status: '', audience: '', delivery_result: '', search: '' });
  const runCsvCacheRef = useRef(new Map());

  const clearRunCsvCache = useCallback(() => {
    runCsvCacheRef.current.clear();
  }, []);

  useEffect(() => {
    clearRunCsvCache();
  }, [clearRunCsvCache, runLotFilter]);

  const hydrateHistoryData = useCallback(({ changeEventsItems, retryQueueItems, maintenanceSummaryItem }) => {
    setChangeEvents(changeEventsItems || []);
    setRetryQueue(retryQueueItems || []);
    setMaintenanceSummary(maintenanceSummaryItem || null);
    clearRunCsvCache();
  }, [clearRunCsvCache]);

  const refreshMaintenanceSummary = useCallback(async () => {
    try {
      const result = await getAutomationMaintenanceSummary(retentionDays);
      setMaintenanceSummary(result || null);
    } catch {
      // Keep the current summary if the refresh fails.
    }
  }, [retentionDays]);

  const refreshRunLots = useCallback(async (runId, nextFilter = runLotFilter) => {
    setLoadingRunLotsId(runId);
    try {
      const response = await listAutomationRunLotsFiltered(runId, {
        status: nextFilter.status || undefined,
        audience: nextFilter.audience || undefined,
        delivery_result: nextFilter.delivery_result || undefined,
        search: nextFilter.search || undefined,
      });
      setRunLotsById((current) => ({ ...current, [runId]: response.items || [] }));
      clearRunCsvCache();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut carregar el detall per lots");
    } finally {
      setLoadingRunLotsId(null);
    }
  }, [clearRunCsvCache, runLotFilter, setError]);

  const toggleRunLots = useCallback(async (runId) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    await refreshRunLots(runId);
  }, [expandedRunId, refreshRunLots]);

  const handleExportRunCsv = useCallback(async (runId) => {
    try {
      const cacheKey = JSON.stringify({ runId, runLotFilter });
      const cached = runCsvCacheRef.current.get(cacheKey);
      if (cached) {
        downloadBlob(
          {
            data: cached.blob,
            headers: { 'content-type': cached.contentType },
          },
          cached.fileName,
        );
        return;
      }
      const response = await exportAutomationRunLotsCsv(runId, {
        status: runLotFilter.status || undefined,
        audience: runLotFilter.audience || undefined,
        delivery_result: runLotFilter.delivery_result || undefined,
        search: runLotFilter.search || undefined,
      });
      const fileName = `automation_run_${runId}_lots.csv`;
      const contentType = response.headers?.['content-type'] || 'text/csv;charset=utf-8';
      const blob = new Blob([response.data], { type: contentType });
      runCsvCacheRef.current.set(cacheKey, { blob, contentType, fileName });
      downloadBlob(
        {
          data: blob,
          headers: { 'content-type': contentType },
        },
        fileName,
      );
    } catch (err) {
      setError(await resolveRequestErrorMessage(err, "No s'ha pogut exportar el CSV"));
    }
  }, [runLotFilter, setError]);

  const handleEnqueueRetry = useCallback(async (runId, lot, audience, onRefresh) => {
    try {
      await enqueueRetry({ run_id: runId, lot, audience, requested_by: 'automation_ui' });
      clearRunCsvCache();
      setMessage('Element afegit a la cua de reintents.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut afegir el reintent");
    }
  }, [clearRunCsvCache, setError, setMessage]);

  const handleRunRetryNow = useCallback(async (queueId, onRefresh) => {
    try {
      await runRetryNow(queueId);
      clearRunCsvCache();
      setMessage('Reintent processat.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut executar el reintent");
    }
  }, [clearRunCsvCache, setError, setMessage]);

  const handlePurgeHistory = useCallback(async (onRefresh) => {
    if (!window.confirm(`S'esborrar\u00e0 l'hist\u00f2ric anterior als \u00faltims ${retentionDays} dies. Vols continuar?`)) return;
    try {
      const result = await purgeAutomationHistory({ retain_days: retentionDays, delete_reports: true });
      setExpandedRunId(null);
      setRunLotsById({});
      clearRunCsvCache();
      setMessage(`Hist\u00f2ric netejat. Runs eliminats: ${result.deleted_runs || 0}. Fitxers eliminats: ${result.deleted_report_files || 0}.`);
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut netejar l'hist\u00f2ric");
    }
  }, [clearRunCsvCache, retentionDays, setError, setMessage]);

  const handlePurgeRetryQueue = useCallback(async (onRefresh) => {
    if (!window.confirm("S'esborraran tots els elements de la cua de reintents. Vols continuar?")) return;
    try {
      const result = await purgeAutomationRetryQueue({});
      clearRunCsvCache();
      setMessage(`Cua de reintents buidada. Elements eliminats: ${result.deleted_retry_items || 0}.`);
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut buidar la cua de reintents");
    }
  }, [clearRunCsvCache, setError, setMessage]);

  return {
    changeEvents,
    expandedRunId,
    handleEnqueueRetry,
    handleExportRunCsv,
    handlePurgeHistory,
    handlePurgeRetryQueue,
    handleRunRetryNow,
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
  };
}
