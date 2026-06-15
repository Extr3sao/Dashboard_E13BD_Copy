import React from 'react';
import { Plus, Save } from 'lucide-react';
import AutomationSection from './AutomationSection.jsx';

export default function AutomationRecipientsPanel({
  isVisible,
  registerSection,
  open,
  onToggle,
  lotRoutes,
  setLotRoutes,
  emptyRoute,
  saveLotRoutes,
}) {
  return (
    <div id="lot_routes" ref={registerSection('lot_routes')} className={isVisible ? '' : 'hidden'}>
      <AutomationSection
        title="Destinataris per lot"
        description="Edició directa des d'Automatitzacions amb compatibilitat cap enrere."
        open={open}
        onToggle={onToggle}
        actions={<button type="button" onClick={() => setLotRoutes((current) => [...current, emptyRoute()])} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"><Plus size={14} />Afegeix</button>}
      >
        <div className="mt-4 flex flex-col gap-3">
          {lotRoutes.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/15 bg-white/5 p-5 text-sm text-muted-foreground">
              Encara no hi ha cap ruta definida. Fes clic a <span className="font-semibold text-foreground">Afegeix</span> per crear-ne una.
            </div>
          ) : null}
          {lotRoutes.map((item) => (
            <div key={item._row_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="grid gap-3">
                <input value={item.lot_code} onChange={(event) => setLotRoutes((current) => current.map((row) => row._row_id === item._row_id ? { ...row, lot_code: event.target.value.toUpperCase() } : row))} placeholder="Lot" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                <input value={item.label || ''} onChange={(event) => setLotRoutes((current) => current.map((row) => row._row_id === item._row_id ? { ...row, label: event.target.value } : row))} placeholder="Etiqueta visible" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                <textarea value={item.emails_text || ''} onChange={(event) => setLotRoutes((current) => current.map((row) => row._row_id === item._row_id ? { ...row, emails_text: event.target.value } : row))} placeholder="a@proveidor.cat, b@proveidor.cat" className="min-h-[84px] rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={item.enabled !== false} onChange={(event) => setLotRoutes((current) => current.map((row) => row._row_id === item._row_id ? { ...row, enabled: event.target.checked } : row))} />Actiu</label>
                  <button type="button" onClick={() => setLotRoutes((current) => current.filter((row) => row._row_id !== item._row_id))} className="text-xs font-semibold uppercase tracking-wide text-red-200">Elimina</button>
                </div>
              </div>
            </div>
          ))}
          <button type="button" onClick={saveLotRoutes} className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90"><Save size={16} />Desa rutes</button>
        </div>
      </AutomationSection>
    </div>
  );
}
