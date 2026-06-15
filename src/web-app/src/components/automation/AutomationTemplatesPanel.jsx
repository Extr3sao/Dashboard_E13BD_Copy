import React from 'react';
import { Plus, Save } from 'lucide-react';
import AutomationSection from './AutomationSection.jsx';

export default function AutomationTemplatesPanel({
  isVisible,
  registerSection,
  open,
  onToggle,
  templates,
  setTemplates,
  emptyTemplate,
  saveTemplates,
  templateKeyLabel,
  templateKeyDescription,
}) {
  return (
    <div id="templates" ref={registerSection('templates')} className={isVisible ? '' : 'hidden'}>
      <AutomationSection
        title="Plantilles per audiència"
        description="Rutes TIC, lots i reintents manuals amb variables comunes."
        open={open}
        onToggle={onToggle}
        actions={<button type="button" onClick={() => setTemplates((current) => [...current, emptyTemplate()])} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10"><Plus size={14} />Afegeix</button>}
      >
        <div className="mt-4 flex flex-col gap-3">
          <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4 text-sm text-foreground">
            <p className="font-semibold text-primary">Etiquetes visibles de les plantilles</p>
            <p className="mt-2 text-muted-foreground">
              La interfície mostra noms funcionals en català. La clau interna es manté sense canvis per compatibilitat.
            </p>
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-white/70 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lot amb troballes</p>
                <p className="mt-1 text-xs text-muted-foreground">Plantilla principal per a enviaments amb adjunt individual.</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/70 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lot sense troballes</p>
                <p className="mt-1 text-xs text-muted-foreground">Correu opcional quan el lot s'ha avaluat correctament i no té anomalies.</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/70 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Resum TIC</p>
                <p className="mt-1 text-xs text-muted-foreground">Resum general per a l'Àrea TIC.</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/70 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Reenviament manual</p>
                <p className="mt-1 text-xs text-muted-foreground">Plantilla usada quan es força un reintent des de la cua.</p>
              </div>
            </div>
          </div>
          {templates.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/15 bg-white/5 p-5 text-sm text-muted-foreground">
              No hi ha cap plantilla carregada. Fes clic a <span className="font-semibold text-foreground">Afegeix</span> per crear-ne una.
            </div>
          ) : null}
          {templates.map((item) => (
            <div key={item._row_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="grid gap-3">
                <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                  <p className="text-sm font-bold text-foreground">{templateKeyLabel(item.template_key)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{templateKeyDescription(item.template_key)}</p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <input value={item.template_key} onChange={(event) => setTemplates((current) => current.map((row) => row._row_id === item._row_id ? { ...row, template_key: event.target.value } : row))} placeholder="Clau interna de plantilla" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                  <select value={item.audience || 'provider'} onChange={(event) => setTemplates((current) => current.map((row) => row._row_id === item._row_id ? { ...row, audience: event.target.value } : row))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                    <option value="provider">Lot</option>
                    <option value="tic">TIC</option>
                    <option value="retry">Reenviament</option>
                  </select>
                </div>
                <input value={item.subject_template || ''} onChange={(event) => setTemplates((current) => current.map((row) => row._row_id === item._row_id ? { ...row, subject_template: event.target.value } : row))} placeholder="Assumpte" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                <textarea value={item.body_template || ''} onChange={(event) => setTemplates((current) => current.map((row) => row._row_id === item._row_id ? { ...row, body_template: event.target.value } : row))} placeholder="Cos del missatge" className="min-h-[120px] rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={item.enabled !== false} onChange={(event) => setTemplates((current) => current.map((row) => row._row_id === item._row_id ? { ...row, enabled: event.target.checked } : row))} />Activa</label>
                  <button type="button" onClick={() => setTemplates((current) => current.filter((row) => row._row_id !== item._row_id))} className="text-xs font-semibold uppercase tracking-wide text-red-200">Elimina</button>
                </div>
              </div>
            </div>
          ))}
          <button type="button" onClick={saveTemplates} className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90"><Save size={16} />Desa plantilles</button>
        </div>
      </AutomationSection>
    </div>
  );
}
