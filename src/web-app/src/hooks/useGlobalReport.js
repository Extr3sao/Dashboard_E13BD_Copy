import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

export default function useGlobalReport({
  apiBase,
  activeTab,
  databaseAuditSubtab,
  selectedProfile,
  auditData,
  postCrqReportData,
}) {
  const [loading, setLoading] = useState(false);
  const reportDownloadCacheRef = useRef(new Map());
  const cacheScopeKey = JSON.stringify({
    activeTab,
    databaseAuditSubtab,
    selectedProfile,
    auditData,
    postCrqReportData,
  });

  useEffect(() => {
    reportDownloadCacheRef.current.clear();
  }, [cacheScopeKey]);

  const triggerPdfDownload = useCallback((blob, fileName) => {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
  }, []);

  function buildCurrentReportRequest() {
    const hasDeepAudit = Array.isArray(auditData) && auditData.length > 0;
    const hasPostCrqAudit = postCrqReportData?.audit_type === 'post_crq';

    if (!hasDeepAudit && !hasPostCrqAudit) {
      return { error: 'Primer executa una auditoria!' };
    }

    if (activeTab === 'Auditoria BBDD' && databaseAuditSubtab === 'Auditoria de canvis' && hasPostCrqAudit) {
      return {
        reportData: {
          ...postCrqReportData,
          report_options: {
            ...(postCrqReportData?.report_options || {}),
            include_annex: true,
          },
        },
        downloadPrefix: 'report_auditoria_post_crq',
      };
    }

    return {
      reportData: auditData,
      downloadPrefix: 'report_auditoria_detallat',
    };
  }

  function handleGenerateReport() {
    const request = buildCurrentReportRequest();
    if (request.error) {
      return alert(request.error);
    }

    const { reportData, downloadPrefix } = request;
    const fileName = `${downloadPrefix}_${selectedProfile}.pdf`;
    const cacheKey = JSON.stringify({
      downloadPrefix,
      selectedProfile,
      reportData,
    });
    const cached = reportDownloadCacheRef.current.get(cacheKey);
    if (cached) {
      triggerPdfDownload(cached.blob, cached.fileName);
      return;
    }
    setLoading(true);

    axios.post(
      `${apiBase}/report/generate`,
      { data: reportData, profile: selectedProfile, format: 'pdf' },
      { responseType: 'blob' }
    )
      .then((res) => {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        reportDownloadCacheRef.current.set(cacheKey, { blob, fileName });
        triggerPdfDownload(blob, fileName);
        setLoading(false);
      })
      .catch((err) => {
        setLoading(false);
        if (err.response && err.response.data instanceof Blob) {
          err.response.data.text().then((text) => {
            let errorMsg = text;
            try {
              const parsed = JSON.parse(text);
              errorMsg = parsed.detail || text;
            } catch (_error) {
              // Ignore invalid JSON and preserve raw text.
            }
            alert(`Error generant report: ${errorMsg}`);
          });
        } else {
          alert(`Error generant report: ${err.message}`);
        }
      });
  }

  return {
    loading,
    handleGenerateReport,
  };
}
