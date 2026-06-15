import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  listPostCrqOperationalDocumentHistory,
  listPostCrqOperationalDocuments,
  updatePostCrqOperationalDocument,
} from '../api/postCrqDocuments.js';

const DOCUMENT_ORDER = ['post_crq_audit', 'check_quality_explanation'];

function sortDocuments(items) {
  return [...items].sort((left, right) => {
    const leftIndex = DOCUMENT_ORDER.indexOf(left.id);
    const rightIndex = DOCUMENT_ORDER.indexOf(right.id);
    if (leftIndex === rightIndex) {
      return String(left.title || '').localeCompare(String(right.title || ''));
    }
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

function hydrateDocument(item) {
  return {
    id: item.id,
    title: item.title,
    filename: item.filename,
    kind: item.kind,
    contentType: item.content_type || 'markdown',
    content: item.content || '',
    savedContent: item.content || '',
    version: item.version || '',
    updatedAt: item.updated_at || '',
    sizeBytes: item.size_bytes || 0,
    conflict: null,
    saveError: '',
  };
}

export default function usePostCrqOperationalDocuments({ refreshSignal, enabled = true }) {
  const [documents, setDocuments] = useState([]);
  const [activeDocumentId, setActiveDocumentId] = useState('post_crq_audit');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [savingDocumentId, setSavingDocumentId] = useState('');
  const [historyByDocument, setHistoryByDocument] = useState({});
  const [historyLoadingDocumentId, setHistoryLoadingDocumentId] = useState('');
  const [error, setError] = useState('');
  const [pendingExternalRefresh, setPendingExternalRefresh] = useState(false);
  const documentsRef = useRef([]);

  useEffect(() => {
    documentsRef.current = documents;
  }, [documents]);

  const hasDirtyDocuments = useMemo(
    () => documents.some((item) => item.content !== item.savedContent),
    [documents],
  );

  const activeDocument = useMemo(
    () => documents.find((item) => item.id === activeDocumentId) || documents[0] || null,
    [documents, activeDocumentId],
  );

  const loadDocuments = useCallback(async ({ force = false, silent = false } = {}) => {
    const currentDocuments = documentsRef.current;
    const hasDirtyState = currentDocuments.some((item) => item.content !== item.savedContent);
    if (hasDirtyState && !force) {
      setPendingExternalRefresh(true);
      return { skipped: true };
    }

    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError('');

    try {
      const response = await listPostCrqOperationalDocuments();
      const nextDocuments = sortDocuments((response.items || []).map(hydrateDocument));
      setDocuments(nextDocuments);
      setPendingExternalRefresh(false);
      setActiveDocumentId((currentId) => (
        nextDocuments.some((item) => item.id === currentId)
          ? currentId
          : (nextDocuments[0]?.id || 'post_crq_audit')
      ));
      return { skipped: false, items: nextDocuments };
    } catch (loadError) {
      setError(loadError?.response?.data?.detail || loadError.message || 'No s han pogut carregar els documents operatius');
      return { skipped: false, error: loadError };
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    loadDocuments({ silent: documentsRef.current.length > 0 });
  }, [enabled, refreshSignal, loadDocuments]);

  const updateDocumentContent = useCallback((documentId, content) => {
    setDocuments((current) => current.map((item) => (
      item.id === documentId
        ? { ...item, content, saveError: '', conflict: null }
        : item
    )));
  }, []);

  const discardDocumentChanges = useCallback((documentId) => {
    setDocuments((current) => current.map((item) => (
      item.id === documentId
        ? { ...item, content: item.savedContent, saveError: '', conflict: null }
        : item
    )));
    setPendingExternalRefresh(false);
  }, []);

  const applyServerVersion = useCallback((documentId) => {
    setDocuments((current) => current.map((item) => {
      if (item.id !== documentId || !item.conflict) {
        return item;
      }
      return hydrateDocument(item.conflict);
    }));
    setPendingExternalRefresh(false);
  }, []);

  const loadDocumentHistory = useCallback(async (documentId, { limit = 8 } = {}) => {
    setHistoryLoadingDocumentId(documentId);
    try {
      const response = await listPostCrqOperationalDocumentHistory(documentId, { limit });
      const items = response.items || [];
      setHistoryByDocument((current) => ({ ...current, [documentId]: items }));
      return { ok: true, items };
    } catch (historyError) {
      setError(historyError?.response?.data?.detail || historyError.message || 'No s ha pogut carregar l historial');
      return { ok: false, error: historyError };
    } finally {
      setHistoryLoadingDocumentId('');
    }
  }, []);

  const saveDocument = useCallback(async (documentId, { forceOverwrite = false } = {}) => {
    const currentDocument = documentsRef.current.find((item) => item.id === documentId);
    if (!currentDocument) {
      return { ok: false };
    }

    setSavingDocumentId(documentId);
    setError('');
    setDocuments((current) => current.map((item) => (
      item.id === documentId
        ? { ...item, saveError: '', conflict: null }
        : item
    )));

    try {
      const response = await updatePostCrqOperationalDocument(documentId, {
        content: currentDocument.content,
        expected_version: currentDocument.version,
        force_overwrite: forceOverwrite,
      });
      const savedItem = hydrateDocument(response.item || {});
      setDocuments((current) => current.map((item) => (
        item.id === documentId ? savedItem : item
      )));
      if (response.history_entry) {
        setHistoryByDocument((current) => ({
          ...current,
          [documentId]: [response.history_entry, ...(current[documentId] || [])].slice(0, 8),
        }));
      }
      if (pendingExternalRefresh) {
        await loadDocuments({ force: true, silent: true });
      }
      return { ok: true, item: savedItem };
    } catch (saveError) {
      const detail = saveError?.response?.data?.detail;
      if (saveError?.response?.status === 409 && detail?.current) {
        setDocuments((current) => current.map((item) => (
          item.id === documentId
            ? {
                ...item,
                saveError: detail.message || 'Conflicte de versio detectat',
                conflict: detail.current,
              }
            : item
        )));
      } else {
        setDocuments((current) => current.map((item) => (
          item.id === documentId
            ? {
                ...item,
                saveError: detail || saveError.message || 'No s ha pogut desar el document',
              }
            : item
        )));
      }
      return { ok: false, error: saveError };
    } finally {
      setSavingDocumentId('');
    }
  }, [loadDocuments, pendingExternalRefresh]);

  return {
    documents,
    activeDocument,
    activeDocumentId,
    setActiveDocumentId,
    loading,
    refreshing,
    savingDocumentId,
    historyByDocument,
    historyLoadingDocumentId,
    error,
    pendingExternalRefresh,
    hasDirtyDocuments,
    loadDocuments,
    loadDocumentHistory,
    updateDocumentContent,
    discardDocumentChanges,
    applyServerVersion,
    saveDocument,
  };
}
