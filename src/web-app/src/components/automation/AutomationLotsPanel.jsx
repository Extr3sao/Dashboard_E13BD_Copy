import React from 'react';
import { Download, Plus, RefreshCcw, Save } from 'lucide-react';
import AutomationSection from './AutomationSection.jsx';

export default function AutomationLotsPanel({
  isVisible,
  registerSection,
  openSections,
  toggleSection,
  filteredSchemaLots,
  exportSchemaLotsCsv,
  setSchemaLots,
  emptySchemaLot,
  schemaLotFilter,
  setSchemaLotFilter,
  schemaLotOptions,
  schemaLotValidation,
  schemaLots,
  masterLotCodes,
  saveSchemaLots,
  handlePreviewBackfill,
  previewingBackfill,
  handleApplyBackfill,
  applyingBackfill,
  backfillPreview,
  backfillSelection,
  setBackfillSelection,
  masterLots,
  setMasterLots,
  emptyMasterLot,
  saveMasterLots,
}) {
  return (
    <div className={`grid gap-8 ${isVisible ? '' : 'hidden'}`}>
      <div id="schema_map" ref={registerSection('schema_map')}>
        <AutomationSection
          title="Mapeig schema -> lot"
          description="Afegeix esquemes nous i associa'ls a un lot. El backfill llegeix aquest mapatge, però no modifica schema_lots."
          open={openSections.schema_map}
          onToggle={() => toggleSection('schema_map')}
          actions={(
            <>
              <button type="button" onClick={() => exportSchemaLotsCsv(filteredSchemaLots.map(({ _row_id, ...row }) => row))} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"><Download size={14} />Exporta CSV</button>
              <button type="button" onClick={() => setSchemaLots((current) => [...current, emptySchemaLot()])} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"><Plus size={14} />Afegeix</button>
            </>
          )}
        >
          <div className="mt-4 flex flex-col gap-4">
            <div className="grid gap-3 md:grid-cols-[0.8fr_1.2fr_auto]">
              <label className="flex flex-col gap-2 text-sm">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Filtra per lot</span>
                <select value={schemaLotFilter.lot} onChange={(event) => setSchemaLotFilter((current) => ({ ...current, lot: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                  <option value="">Tots</option>
                  {schemaLotOptions.map((lot) => <option key={lot} value={lot}>{lot}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Cerca per esquema o lot</span>
                <input value={schemaLotFilter.search} onChange={(event) => setSchemaLotFilter((current) => ({ ...current, search: event.target.value.toUpperCase() }))} placeholder="APP_USER o LOT_APP" className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary" />
              </label>
              <div className="flex items-end">
                <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {filteredSchemaLots.length} files
                </div>
              </div>
            </div>
            {schemaLotValidation.hasErrors ? (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                {schemaLotValidation.emptySchemaIndexes.size > 0 ? 'Hi ha files sense schema_name. ' : ''}
                {schemaLotValidation.invalidSchemaIndexes.size > 0 ? 'Hi ha schema_name amb format no valid. ' : ''}
                {schemaLotValidation.duplicateSchemas.size > 0 ? `Schemas duplicats: ${Array.from(schemaLotValidation.duplicateSchemas).sort().join(', ')}.` : ''}
              </div>
            ) : null}
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/5">
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-white/10 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3">Schema</th>
                      <th className="px-4 py-3">Lot</th>
                      <th className="px-4 py-3">Estat</th>
                      <th className="px-4 py-3">Validacio</th>
                      <th className="px-4 py-3 text-right">Acció</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSchemaLots.length === 0 ? (
                      <tr>
                        <td colSpan="5" className="px-4 py-6 text-sm text-muted-foreground">No hi ha files que coincideixin amb el filtre.</td>
                      </tr>
                    ) : filteredSchemaLots.map((item) => {
                      const index = schemaLots.findIndex((row) => row._row_id === item._row_id);
                      const normalizedSchema = String(item.schema_name || '').trim().toUpperCase();
                      const normalizedLot = String(item.lot_name || '').trim().toUpperCase();
                      const lotExists = !normalizedLot || normalizedLot === 'SENSE LOT' || masterLotCodes.has(normalizedLot);
                      const rowHasEmptySchema = schemaLotValidation.emptySchemaIndexes.has(index);
                      const rowHasInvalidSchema = schemaLotValidation.invalidSchemaIndexes.has(index);
                      const rowHasDuplicateSchema = !!normalizedSchema && schemaLotValidation.duplicateSchemas.has(normalizedSchema);
                      const validationMessage = rowHasEmptySchema
                        ? 'schema_name obligatori'
                        : rowHasInvalidSchema
                          ? 'format no valid'
                          : rowHasDuplicateSchema
                            ? 'schema duplicat'
                            : lotExists
                              ? 'correcte'
                              : 'lot fora del catàleg';
                      return (
                        <tr key={item._row_id} className={`border-t border-white/10 ${lotExists ? 'bg-transparent' : 'bg-amber-500/5'}`}>
                          <td className="px-4 py-3 align-top">
                            <input value={item.schema_name || ''} onChange={(event) => setSchemaLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, schema_name: event.target.value.toUpperCase() } : row))} placeholder="Schema Oracle" className={`w-full rounded-xl border p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary ${rowHasEmptySchema || rowHasInvalidSchema || rowHasDuplicateSchema ? 'border-red-400/60 bg-red-50' : 'border-border bg-white'}`} />
                          </td>
                          <td className="px-4 py-3 align-top">
                            <input value={item.lot_name || ''} onChange={(event) => setSchemaLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, lot_name: event.target.value.toUpperCase() } : row))} placeholder="Lot associat" className="w-full rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary" />
                          </td>
                          <td className="px-4 py-3 align-top">
                            <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${lotExists ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/20 bg-amber-500/10 text-amber-100'}`}>{lotExists ? 'lot resolt' : 'pendent de catàleg'}</span>
                          </td>
                          <td className="px-4 py-3 align-top text-xs text-muted-foreground">
                            {validationMessage}
                          </td>
                          <td className="px-4 py-3 align-top text-right">
                            <button type="button" onClick={() => setSchemaLots((current) => current.filter((row) => row._row_id !== item._row_id))} className="text-xs font-semibold uppercase tracking-wide text-red-200">Elimina</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <button type="button" onClick={saveSchemaLots} disabled={schemaLotValidation.hasErrors} className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"><Save size={16} />Desa mapatge</button>
          </div>
        </AutomationSection>
      </div>

      <div id="backfill" ref={registerSection('backfill')}>
        <AutomationSection
          title="Backfill assistit schema_lots"
          description="Previsualitza l'alta de lots nous al catàleg mestre sense tocar schema_lots ni sobreescriure registres manuals."
          open={openSections.backfill}
          onToggle={() => toggleSection('backfill')}
          actions={(
            <>
              <button type="button" onClick={handlePreviewBackfill} disabled={previewingBackfill} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-semibold text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-60">
                <RefreshCcw size={16} className={previewingBackfill ? 'animate-spin' : ''} />
                {previewingBackfill ? 'Generant...' : 'Genera previsualització'}
              </button>
              <button type="button" onClick={handleApplyBackfill} disabled={applyingBackfill || !backfillPreview?.id || backfillSelection.length === 0} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
                <Save size={16} />
                {applyingBackfill ? 'Aplicant...' : 'Aplica la selecció'}
              </button>
            </>
          )}
        >
          {backfillPreview ? (
            <div className="mt-4 grid gap-6 xl:grid-cols-[0.75fr_1.25fr]">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm"><div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Execució prèvia</div><div className="mt-2 text-foreground">{backfillPreview.id}</div></div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm"><div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lots detectats</div><div className="mt-2 text-foreground">{backfillPreview.summary?.distinct_lots || 0}</div></div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm"><div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Altes proposades</div><div className="mt-2 text-foreground">{backfillPreview.summary?.to_create || 0}</div></div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm"><div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Conflictes</div><div className="mt-2 text-foreground">{backfillPreview.summary?.conflicts || 0}</div></div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-3">Sel</th>
                      <th className="px-3 py-3">Lot</th>
                      <th className="px-3 py-3">Acció</th>
                      <th className="px-3 py-3">Conflicte</th>
                      <th className="px-3 py-3">Schemas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(backfillPreview.items || []).map((item) => (
                      <tr key={`${backfillPreview.id}-${item.lot_code}`} className="border-t border-white/10">
                        <td className="px-3 py-3 text-foreground">
                          <input
                            type="checkbox"
                            checked={backfillSelection.includes(item.lot_code)}
                            disabled={item.action !== 'create'}
                            onChange={(event) => setBackfillSelection((current) => event.target.checked ? [...new Set([...current, item.lot_code])] : current.filter((code) => code !== item.lot_code))}
                          />
                        </td>
                        <td className="px-3 py-3 text-foreground">{item.lot_code}</td>
                        <td className="px-3 py-3 text-foreground">{item.action}</td>
                        <td className="px-3 py-3 text-muted-foreground">{item.conflict_code || '-'}</td>
                        <td className="px-3 py-3 text-muted-foreground">{(item.schema_names || []).join(', ') || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">Encara no hi ha cap previsualització de backfill generada.</p>
          )}
        </AutomationSection>
      </div>

      <div className="grid gap-8 xl:grid-cols-3">
        <div id="master_lots" ref={registerSection('master_lots')}>
          <AutomationSection
            title="Catàleg mestre de lots"
            description="Entitat operativa independent de schema_lots."
            open={openSections.master_lots}
            onToggle={() => toggleSection('master_lots')}
            actions={<button type="button" onClick={() => setMasterLots((current) => [...current, emptyMasterLot()])} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"><Plus size={14} />Afegeix</button>}
          >
            <div className="mt-4 flex flex-col gap-3">
              {masterLots.map((item) => (
                <div key={item._row_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="grid gap-3">
                    <input value={item.code} onChange={(event) => setMasterLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, code: event.target.value.toUpperCase() } : row))} placeholder="Codi del lot" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                    <input value={item.label} onChange={(event) => setMasterLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, label: event.target.value } : row))} placeholder="Etiqueta" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                    <textarea value={item.description || ''} onChange={(event) => setMasterLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, description: event.target.value } : row))} placeholder="Descripció opcional" className="min-h-[84px] rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={item.enabled !== false} onChange={(event) => setMasterLots((current) => current.map((row) => row._row_id === item._row_id ? { ...row, enabled: event.target.checked } : row))} />Actiu</label>
                      <button type="button" onClick={() => setMasterLots((current) => current.filter((row) => row._row_id !== item._row_id))} className="text-xs font-semibold uppercase tracking-wide text-red-200">Elimina</button>
                    </div>
                  </div>
                </div>
              ))}
              <button type="button" onClick={saveMasterLots} className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90"><Save size={16} />Desa catàleg</button>
            </div>
          </AutomationSection>
        </div>
      </div>
    </div>
  );
}
