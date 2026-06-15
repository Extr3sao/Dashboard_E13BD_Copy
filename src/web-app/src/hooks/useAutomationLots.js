import { useCallback, useMemo, useState } from 'react';
import {
  applyMasterLotsBackfill,
  previewMasterLotsBackfill,
  updateMasterLots,
  updateSchemaLots,
} from '../api/automation.js';
import {
  emptyMasterLot,
  emptySchemaLot,
  exportSchemaLotsCsv,
  getSchemaLotValidation,
  withRowIds,
  withSchemaLotRowIds,
} from '../utils/automationViewUtils.js';

export function useAutomationLots({ setError, setMessage }) {
  const [masterLots, setMasterLots] = useState([]);
  const [schemaLots, setSchemaLots] = useState([]);
  const [schemaLotFilter, setSchemaLotFilter] = useState({ lot: '', search: '' });
  const [backfillPreview, setBackfillPreview] = useState(null);
  const [backfillSelection, setBackfillSelection] = useState([]);
  const [previewingBackfill, setPreviewingBackfill] = useState(false);
  const [applyingBackfill, setApplyingBackfill] = useState(false);

  const hydrateLotsData = useCallback(({ masterLotsItems, schemaLotsItems, backfillRun }) => {
    setMasterLots(withRowIds((masterLotsItems || []).map((item) => ({ ...item })), 'master-lot'));
    setSchemaLots(withSchemaLotRowIds((schemaLotsItems || []).map((item) => ({ ...item }))));
    setBackfillPreview(backfillRun || null);
    setBackfillSelection(((backfillRun || {}).items || []).filter((item) => item.selected).map((item) => item.lot_code));
  }, []);

  const schemaLotValidation = useMemo(() => getSchemaLotValidation(schemaLots), [schemaLots]);

  const saveSchemaLots = useCallback(async (onRefresh) => {
    try {
      if (schemaLotValidation.emptySchemaIndexes.size > 0) {
        throw new Error('Hi ha files sense schema_name. Omple-les o elimina-les abans de desar.');
      }
      if (schemaLotValidation.invalidSchemaIndexes.size > 0) {
        throw new Error('Hi ha schema_name amb format no valid. Usa lletres, digits, _, $ o # i comenca per una lletra.');
      }
      if (schemaLotValidation.duplicateSchemas.size > 0) {
        throw new Error(`Hi ha schemas duplicats: ${Array.from(schemaLotValidation.duplicateSchemas).sort().join(', ')}`);
      }
      await updateSchemaLots({ items: schemaLots.map(({ _row_id, ...row }) => row), actor: 'automation_ui', reason: 'Edició manual schema_lots' });
      setMessage('Mapeig schema -> lot desat.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut desar el mapatge schema -> lot");
    }
  }, [schemaLotValidation, schemaLots, setError, setMessage]);

  const saveMasterLots = useCallback(async (onRefresh) => {
    try {
      await updateMasterLots({ items: masterLots.map(({ _row_id, ...item }) => item), actor: 'automation_ui' });
      setMessage('Catàleg de lots desat.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut desar el catàleg de lots");
    }
  }, [masterLots, setError, setMessage]);

  const handlePreviewBackfill = useCallback(async (onRefresh) => {
    setPreviewingBackfill(true);
    setError('');
    setMessage('');
    try {
      const preview = await previewMasterLotsBackfill({ actor: 'automation_ui' });
      setBackfillPreview(preview);
      setBackfillSelection((preview.items || []).filter((item) => item.selected).map((item) => item.lot_code));
      setMessage('Previsualització del backfill generada.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut generar la previsualització del backfill");
    } finally {
      setPreviewingBackfill(false);
    }
  }, [setError, setMessage]);

  const handleApplyBackfill = useCallback(async (onRefresh) => {
    if (!backfillPreview?.id) return;
    setApplyingBackfill(true);
    setError('');
    setMessage('');
    try {
      await applyMasterLotsBackfill({ run_id: backfillPreview.id, selected_lot_codes: backfillSelection, actor: 'automation_ui', reason: 'Backfill des de schema_lots' });
      setMessage('Backfill aplicat al catàleg mestre.');
      await onRefresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut aplicar el backfill");
    } finally {
      setApplyingBackfill(false);
    }
  }, [backfillPreview?.id, backfillSelection, setError, setMessage]);

  const masterLotCodes = useMemo(
    () => new Set(masterLots.map((item) => String(item.code || '').trim().toUpperCase()).filter(Boolean)),
    [masterLots],
  );
  const schemaLotOptions = useMemo(
    () => Array.from(new Set(schemaLots.map((item) => String(item.lot_name || '').trim().toUpperCase()).filter(Boolean))).sort(),
    [schemaLots],
  );
  const filteredSchemaLots = useMemo(
    () => schemaLots.filter((item) => {
      const lotMatch = !schemaLotFilter.lot || String(item.lot_name || '').trim().toUpperCase() === schemaLotFilter.lot;
      const searchValue = schemaLotFilter.search.trim().toUpperCase();
      const searchMatch = !searchValue
        || String(item.schema_name || '').trim().toUpperCase().includes(searchValue)
        || String(item.lot_name || '').trim().toUpperCase().includes(searchValue);
      return lotMatch && searchMatch;
    }),
    [schemaLotFilter.lot, schemaLotFilter.search, schemaLots],
  );

  return {
    applyingBackfill,
    backfillPreview,
    backfillSelection,
    emptyMasterLot,
    emptySchemaLot,
    exportSchemaLotsCsv,
    filteredSchemaLots,
    handleApplyBackfill,
    handlePreviewBackfill,
    hydrateLotsData,
    masterLotCodes,
    masterLots,
    previewingBackfill,
    saveMasterLots,
    saveSchemaLots,
    schemaLotFilter,
    schemaLotOptions,
    schemaLotValidation,
    schemaLots,
    setBackfillSelection,
    setMasterLots,
    setSchemaLotFilter,
    setSchemaLots,
  };
}
