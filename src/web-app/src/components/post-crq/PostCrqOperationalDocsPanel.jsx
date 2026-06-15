import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Columns2,
  Eye,
  FileText,
  History,
  PencilLine,
  RefreshCcw,
  RotateCcw,
  Save,
} from 'lucide-react';

import usePostCrqOperationalDocuments from '../../hooks/usePostCrqOperationalDocuments.js';

function formatTimestamp(value) {
  if (!value) return 'No disponible';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function docTabLabel(documentId) {
  if (documentId === 'post_crq_audit') {
    return 'Auditoria post-CRQ';
  }
  if (documentId === 'check_quality_explanation') {
    return 'Explicacion checks de calidad';
  }
  return documentId;
}

function buildDiffRows(leftContent, rightContent) {
  const leftLines = String(leftContent || '').split('\n');
  const rightLines = String(rightContent || '').split('\n');
  const totalRows = Math.max(leftLines.length, rightLines.length);
  return Array.from({ length: totalRows }, (_, index) => {
    const left = leftLines[index] ?? '';
    const right = rightLines[index] ?? '';
    return {
      index,
      left,
      right,
      changed: left !== right,
    };
  });
}

function SimpleDiffViewer({ leftTitle, rightTitle, leftContent, rightContent }) {
  const rows = React.useMemo(
    () => buildDiffRows(leftContent, rightContent),
    [leftContent, rightContent],
  );

  return (
    <div className="rounded-xl border border-white/10 bg-black/20">
      <div className="grid grid-cols-2 border-b border-white/10 text-xs font-bold uppercase tracking-wide text-muted-foreground">
        <div className="border-r border-white/10 px-4 py-3">{leftTitle}</div>
        <div className="px-4 py-3">{rightTitle}</div>
      </div>
      <div className="max-h-[320px] overflow-auto font-mono text-xs">
        {rows.map((row) => (
          <div key={`${row.index}-${row.left}-${row.right}`} className="grid grid-cols-2">
            <div className={`border-r border-white/10 px-4 py-2 whitespace-pre-wrap ${row.changed ? 'bg-red-500/10 text-red-100' : 'text-foreground/80'}`}>
              <span className="mr-2 opacity-40">{row.index + 1}</span>
              {row.left || ' '}
            </div>
            <div className={`px-4 py-2 whitespace-pre-wrap ${row.changed ? 'bg-emerald-500/10 text-emerald-100' : 'text-foreground/80'}`}>
              <span className="mr-2 opacity-40">{row.index + 1}</span>
              {row.right || ' '}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PostCrqOperationalDocsPanel({
  selectedProfile,
  checks,
  result,
  refreshNonce = 0,
}) {
  const [viewMode, setViewMode] = React.useState('split');
  const [isOpen, setIsOpen] = React.useState(true);
  const [showHistory, setShowHistory] = React.useState(false);
  const [historyComparisonId, setHistoryComparisonId] = React.useState('');
  const [saveNotice, setSaveNotice] = React.useState('');
  const refreshSignal = React.useMemo(() => JSON.stringify({
    selectedProfile: selectedProfile || '',
    checksSignature: (checks || []).map((item) => `${item.check_id}:${item.title || ''}:${item.criteri || ''}`).join('|'),
    generatedAt: result?.report_model?.execution_parameters?.generated_at || result?.context?.generated_at || '',
    refreshNonce,
  }), [checks, refreshNonce, result, selectedProfile]);

  const {
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
  } = usePostCrqOperationalDocuments({ refreshSignal, enabled: isOpen });

  const activeIsDirty = !!activeDocument && activeDocument.content !== activeDocument.savedContent;
  const activeHistory = historyByDocument[activeDocumentId] || [];
  const comparedHistoryItem = activeHistory.find((item) => item.snapshot_id === historyComparisonId) || null;

  React.useEffect(() => {
    if (!savingDocumentId) {
      return;
    }
    setSaveNotice('');
  }, [savingDocumentId]);

  React.useEffect(() => {
    setHistoryComparisonId('');
  }, [activeDocumentId]);

  React.useEffect(() => {
    if (!isOpen || !showHistory || !activeDocumentId) {
      return;
    }
    loadDocumentHistory(activeDocumentId);
  }, [activeDocumentId, isOpen, loadDocumentHistory, showHistory]);

  const handleRefresh = async ({ force = false } = {}) => {
    if (!force && hasDirtyDocuments) {
      const shouldReload = window.confirm('Hi ha canvis sense desar. Vols descartar-los i recarregar els documents?');
      if (!shouldReload) {
        return;
      }
    }
    if (force && activeDocument) {
      discardDocumentChanges(activeDocument.id);
    }
    const response = await loadDocuments({ force: true, silent: documents.length > 0 });
    if (!response?.error) {
      setSaveNotice('');
    }
  };

  const handleSave = async () => {
    if (!activeDocument) {
      return;
    }
    const response = await saveDocument(activeDocument.id);
    if (response?.ok) {
      setSaveNotice(`Document desat: ${activeDocument.title}`);
    }
  };

  const handleOverwriteSave = async () => {
    if (!activeDocument) {
      return;
    }
    const response = await saveDocument(activeDocument.id, { forceOverwrite: true });
    if (response?.ok) {
      setSaveNotice(`Document sobrescrit al servidor: ${activeDocument.title}`);
    }
  };

  return (
    <section className="rounded-2xl border border-white/10 bg-black/10 p-5">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-primary/20 bg-primary/10 p-2 text-primary">
            <FileText size={18} />
          </div>
          <div>
            <h4 className="text-sm font-bold uppercase tracking-wider opacity-70">Auditoria / Checks</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              Editor contextual dels documents operatius Post-CRQ amb recarrega manual i actualitzacio controlada.
            </p>
          </div>
        </div>
        {isOpen ? <ChevronUp size={18} className="text-muted-foreground" /> : <ChevronDown size={18} className="text-muted-foreground" />}
      </button>

      {isOpen && (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {documents.map((item) => {
                const isActive = item.id === activeDocumentId;
                const isDirty = item.content !== item.savedContent;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setActiveDocumentId(item.id);
                      setSaveNotice('');
                    }}
                    className={`rounded-xl border px-4 py-2 text-sm font-semibold transition-all ${
                      isActive
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-white/10 bg-white/5 hover:bg-white/10'
                    }`}
                  >
                    {docTabLabel(item.id)}
                    {isDirty ? ' *' : ''}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setViewMode('edit')}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${viewMode === 'edit' ? 'border-primary bg-primary/15 text-primary' : 'border-white/10 bg-white/5 hover:bg-white/10'}`}
              >
                <span className="inline-flex items-center gap-2"><PencilLine size={14} /> Editar</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('split')}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${viewMode === 'split' ? 'border-primary bg-primary/15 text-primary' : 'border-white/10 bg-white/5 hover:bg-white/10'}`}
              >
                <span className="inline-flex items-center gap-2"><Columns2 size={14} /> Doble vista</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('preview')}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${viewMode === 'preview' ? 'border-primary bg-primary/15 text-primary' : 'border-white/10 bg-white/5 hover:bg-white/10'}`}
              >
                <span className="inline-flex items-center gap-2"><Eye size={14} /> Vista previa</span>
              </button>
              <button
                type="button"
                onClick={() => setShowHistory((current) => !current)}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${showHistory ? 'border-primary bg-primary/15 text-primary' : 'border-white/10 bg-white/5 hover:bg-white/10'}`}
              >
                <span className="inline-flex items-center gap-2"><History size={14} /> Historial</span>
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">
              {error}
            </div>
          )}

          {pendingExternalRefresh && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-100">
              <div className="flex items-start gap-2">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>Hi ha canvis externs al context Post-CRQ. Desa o descarta els teus canvis abans de recarregar.</span>
              </div>
              <button
                type="button"
                onClick={() => handleRefresh({ force: true })}
                className="rounded-lg border border-amber-300/30 bg-amber-200/10 px-3 py-2 text-xs font-semibold hover:bg-amber-200/20"
              >
                Recarregar ara
              </button>
            </div>
          )}

          {saveNotice && (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-100">
              <CheckCircle2 size={16} className="shrink-0" />
              <span>{saveNotice}</span>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-xs text-muted-foreground">
            <div className="flex flex-wrap gap-3">
              <span>Perfil actiu: <strong className="text-foreground">{selectedProfile || 'Sense perfil'}</strong></span>
              <span>Fitxer: <strong className="text-foreground">{activeDocument?.filename || '-'}</strong></span>
              <span>Actualitzat: <strong className="text-foreground">{formatTimestamp(activeDocument?.updatedAt)}</strong></span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => loadDocuments({ force: false, silent: true })}
                className="rounded-lg border border-white/10 bg-black/10 px-3 py-2 font-semibold hover:bg-white/10"
              >
                <span className="inline-flex items-center gap-2">
                  <RefreshCcw size={14} className={refreshing ? 'animate-spin' : ''} />
                  Refrescar
                </span>
              </button>
              <button
                type="button"
                onClick={() => activeDocument && discardDocumentChanges(activeDocument.id)}
                disabled={!activeIsDirty}
                className="rounded-lg border border-white/10 bg-black/10 px-3 py-2 font-semibold hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="inline-flex items-center gap-2">
                  <RotateCcw size={14} />
                  Descartar
                </span>
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={!activeDocument || !activeIsDirty || savingDocumentId === activeDocument?.id}
                className="rounded-lg border border-primary/20 bg-primary/10 px-3 py-2 font-semibold text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="inline-flex items-center gap-2">
                  {savingDocumentId === activeDocument?.id ? <RefreshCcw size={14} className="animate-spin" /> : <Save size={14} />}
                  Desar
                </span>
              </button>
            </div>
          </div>

          {loading && (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
              Carregant documents operatius...
            </div>
          )}

          {!loading && activeDocument?.saveError && (
            <div className="space-y-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-100">
              <div className="flex items-start gap-2">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>{activeDocument.saveError}</span>
              </div>
              {activeDocument.conflict && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => applyServerVersion(activeDocument.id)}
                    className="rounded-lg border border-red-300/30 bg-red-200/10 px-3 py-2 text-xs font-semibold hover:bg-red-200/20"
                  >
                    Carregar versio servidor
                  </button>
                  <button
                    type="button"
                    onClick={handleOverwriteSave}
                    className="rounded-lg border border-emerald-300/30 bg-emerald-200/10 px-3 py-2 text-xs font-semibold hover:bg-emerald-200/20"
                  >
                    Sobreescriure amb el meu canvi
                  </button>
                  <span className="text-xs text-red-100/80">
                    Versio servidor actualitzada a {formatTimestamp(activeDocument.conflict.updated_at)}.
                  </span>
                </div>
              )}
              {activeDocument.conflict && (
                <SimpleDiffViewer
                  leftTitle="Canvi local"
                  rightTitle="Servidor"
                  leftContent={activeDocument.content}
                  rightContent={activeDocument.conflict.content}
                />
              )}
            </div>
          )}

          {showHistory && activeDocument && (
            <div className="space-y-4 rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Historial de versions</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Versions desades des de la UI. Pots carregar una versio anterior a l editor i tornar-la a desar.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => loadDocumentHistory(activeDocument.id)}
                  className="rounded-lg border border-white/10 bg-black/10 px-3 py-2 text-xs font-semibold hover:bg-white/10"
                >
                  <span className="inline-flex items-center gap-2">
                    <RefreshCcw size={14} className={historyLoadingDocumentId === activeDocument.id ? 'animate-spin' : ''} />
                    Recarregar historial
                  </span>
                </button>
              </div>

              {activeHistory.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                  Encara no hi ha versions desades d aquest document.
                </div>
              ) : (
                <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                  <div className="space-y-3">
                    {activeHistory.map((item) => (
                      <div key={item.snapshot_id} className="rounded-xl border border-white/10 bg-black/10 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-foreground">{formatTimestamp(item.saved_at)}</p>
                            <p className="mt-1 text-[11px] font-mono text-muted-foreground">{item.version?.slice(0, 12)}</p>
                          </div>
                          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-bold uppercase text-muted-foreground">
                            {item.size_bytes || 0} bytes
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              updateDocumentContent(activeDocument.id, item.content || '');
                              setSaveNotice('');
                            }}
                            className="rounded-lg border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold text-primary hover:bg-primary/20"
                          >
                            Carregar a l editor
                          </button>
                          <button
                            type="button"
                            onClick={() => setHistoryComparisonId(item.snapshot_id)}
                            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold hover:bg-white/10"
                          >
                            Comparar amb actual
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div>
                    {comparedHistoryItem ? (
                      <SimpleDiffViewer
                        leftTitle={`Versio ${formatTimestamp(comparedHistoryItem.saved_at)}`}
                        rightTitle="Editor actual"
                        leftContent={comparedHistoryItem.content}
                        rightContent={activeDocument.content}
                      />
                    ) : (
                      <div className="rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                        Selecciona una versio de l historial per comparar-la amb el contingut actual de l editor.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && activeDocument && (
            <div className={`grid gap-4 ${viewMode === 'split' ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1'}`}>
              {viewMode !== 'preview' && (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Editor Markdown</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Recarrega automàtica quan canvia el context Post-CRQ, sense sobreescriure canvis locals.
                      </p>
                    </div>
                    {activeIsDirty && (
                      <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-2.5 py-1 text-[10px] font-bold uppercase text-amber-100">
                        Sense desar
                      </span>
                    )}
                  </div>
                  <textarea
                    value={activeDocument.content}
                    onChange={(event) => {
                      updateDocumentContent(activeDocument.id, event.target.value);
                      setSaveNotice('');
                    }}
                    spellCheck={false}
                    className="min-h-[480px] w-full rounded-xl border border-white/10 bg-black/40 p-4 font-mono text-sm leading-6 text-green-200 outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              )}

              {viewMode !== 'edit' && (
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-3">
                    <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Vista previa</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Renderitzat Markdown llegible per revisar l impacte abans de desar.
                    </p>
                  </div>
                  <div className="prose prose-invert max-w-none overflow-auto rounded-xl border border-white/10 bg-black/10 p-4 prose-pre:bg-black/40 prose-code:text-primary">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {activeDocument.content || '*Document buit*'}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
