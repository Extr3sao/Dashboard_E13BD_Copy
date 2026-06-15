import { useCallback, useState } from 'react';
import { updateDeliveryTemplates, updateLotRoutes } from '../api/automation.js';
import { emptyRoute, emptyTemplate, splitCsv, stripUiRowIds, withRowIds } from '../utils/automationViewUtils.js';

export function useAutomationRoutesTemplates({ setError, setMessage }) {
  const [lotRoutes, setLotRoutes] = useState([]);
  const [templates, setTemplates] = useState([]);

  const hydrateRoutesTemplatesData = useCallback(({ lotRoutesItems, templateItems }) => {
    setLotRoutes(withRowIds((lotRoutesItems || []).map((item) => ({ ...item, emails_text: (item.emails || []).join(', ') })), 'route'));
    setTemplates(withRowIds((templateItems || []).map((item) => ({ ...item })), 'template'));
  }, []);

  const saveLotRoutes = useCallback(async (onRefresh) => {
    try {
      await updateLotRoutes({
        items: stripUiRowIds(lotRoutes).map((item) => ({ ...item, emails: splitCsv(item.emails_text) })),
        actor: 'automation_ui',
      });
      setMessage('Destinataris per lot desats.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'han pogut desar els destinataris");
    }
  }, [lotRoutes, setError, setMessage]);

  const saveTemplates = useCallback(async (onRefresh) => {
    try {
      await updateDeliveryTemplates({ items: stripUiRowIds(templates), actor: 'automation_ui' });
      setMessage('Plantilles desades.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'han pogut desar les plantilles");
    }
  }, [setError, setMessage, templates]);

  return {
    emptyRoute,
    emptyTemplate,
    hydrateRoutesTemplatesData,
    lotRoutes,
    saveLotRoutes,
    saveTemplates,
    setLotRoutes,
    setTemplates,
    templates,
  };
}
