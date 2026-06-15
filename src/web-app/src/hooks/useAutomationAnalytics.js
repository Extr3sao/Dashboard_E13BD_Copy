import { useCallback, useEffect, useRef, useState } from 'react';
import {
  exportAutomationAnalyticsMonthlyPdf,
  getAutomationAnalyticsOverview,
  listAutomationAnalyticsChecks,
  listAutomationAnalyticsLots,
  listAutomationAnalyticsSchemas,
} from '../api/automation.js';
import { currentMonthValue, downloadBlob, resolveRequestErrorMessage } from '../utils/automationViewUtils.js';

export function useAutomationAnalytics(setError) {
  const [analyticsMonth, setAnalyticsMonth] = useState(currentMonthValue());
  const [analyticsOverview, setAnalyticsOverview] = useState(null);
  const [analyticsLots, setAnalyticsLots] = useState([]);
  const [analyticsSchemas, setAnalyticsSchemas] = useState([]);
  const [analyticsChecks, setAnalyticsChecks] = useState([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const analyticsPdfCacheRef = useRef(new Map());

  const refreshAnalytics = useCallback(async (monthValue) => {
    setAnalyticsLoading(true);
    try {
      const [overviewRes, lotsRes, schemasRes, checksRes] = await Promise.all([
        getAutomationAnalyticsOverview(monthValue),
        listAutomationAnalyticsLots(monthValue, 25),
        listAutomationAnalyticsSchemas(monthValue, 25),
        listAutomationAnalyticsChecks(monthValue, 25),
      ]);
      setAnalyticsOverview(overviewRes || null);
      setAnalyticsLots(lotsRes.items || []);
      setAnalyticsSchemas(schemasRes.items || []);
      setAnalyticsChecks(checksRes.items || []);
      analyticsPdfCacheRef.current.clear();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut carregar el dashboard anal\u00edtic");
    } finally {
      setAnalyticsLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    refreshAnalytics(analyticsMonth);
  }, [analyticsMonth, refreshAnalytics]);

  const handleExportAnalyticsPdf = async () => {
    try {
      const cacheKey = JSON.stringify({ month: analyticsMonth, limit: 25 });
      const cached = analyticsPdfCacheRef.current.get(cacheKey);
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
      const response = await exportAutomationAnalyticsMonthlyPdf(analyticsMonth, 25);
      const fileName = `dashboard_automatitzacions_${analyticsMonth}.pdf`;
      const blob = new Blob([response.data], { type: response.headers?.['content-type'] || 'application/pdf' });
      analyticsPdfCacheRef.current.set(cacheKey, {
        blob,
        contentType: response.headers?.['content-type'] || 'application/pdf',
        fileName,
      });
      downloadBlob(
        {
          data: blob,
          headers: { 'content-type': response.headers?.['content-type'] || 'application/pdf' },
        },
        fileName,
      );
    } catch (err) {
      setError(await resolveRequestErrorMessage(err, "No s'ha pogut exportar el PDF mensual"));
    }
  };

  return {
    analyticsChecks,
    analyticsLoading,
    analyticsLots,
    analyticsMonth,
    analyticsOverview,
    analyticsSchemas,
    handleExportAnalyticsPdf,
    refreshAnalytics,
    setAnalyticsMonth,
  };
}
