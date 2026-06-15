import React, { useEffect, useState } from 'react';
import { RefreshCcw, Plus } from 'lucide-react';

import { listObsolets, createObsolet } from '../api/obsolets.js';

const DEFAULT_FORM = {
  schema_name: '',
  object_name: '',
  object_type: 'TABLE',
  reason: '',
  risk_level: 'LOW',
  recommendation: '',
  description: '',
};

export default function ObsoletsRegistryView() {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [form, setForm] = useState(DEFAULT_FORM);

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listObsolets({ only_obsolete: true, limit: 200, offset: 0 });
      setItems(res.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Error carregant registre');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const onChange = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    const payload = {
      ...form,
      schema_name: (form.schema_name || '').trim(),
      object_name: (form.object_name || '').trim(),
      object_type: (form.object_type || '').trim(),
      reason: (form.reason || '').trim(),
      risk_level: (form.risk_level || '').trim(),
    };
    if (!payload.schema_name || !payload.object_name || !payload.object_type || !payload.reason || !payload.risk_level) {
      alert('Falten camps obligatoris (schema, objecte, tipus, motiu, risc).');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await createObsolet(payload);
      setForm(DEFAULT_FORM);
      await refresh();
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Error creant entrada');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <div className="glass-card p-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-xl font-bold">Registre d'Obsolets (SQLite)</h3>
          <p className="text-xs text-muted-foreground">Font: `meta_objects` (InternalDB)</p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-2 bg-white/5 border border-border px-4 py-2 rounded-lg hover:bg-white/10 transition-all font-semibold disabled:opacity-50"
        >
          <RefreshCcw size={16} className={loading ? 'animate-spin' : ''} /> Actualitzar
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-200 text-sm">
          {error}
        </div>
      )}

      <div className="glass-card p-6">
        <h4 className="text-sm font-bold uppercase tracking-wider opacity-60 mb-4">Afegir manualment</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            className="bg-white/5 border border-border p-3 rounded-lg text-sm font-mono"
            placeholder="SCHEMA (ex: APP_USER)"
            value={form.schema_name}
            onChange={(e) => onChange('schema_name', e.target.value.toUpperCase())}
          />
          <input
            className="bg-white/5 border border-border p-3 rounded-lg text-sm font-mono"
            placeholder="OBJECTE (ex: TMP_USERS)"
            value={form.object_name}
            onChange={(e) => onChange('object_name', e.target.value)}
          />
          <select
            className="bg-white/5 border border-border p-3 rounded-lg text-sm"
            value={form.object_type}
            onChange={(e) => onChange('object_type', e.target.value)}
          >
            <option value="TABLE">TABLE</option>
            <option value="VIEW">VIEW</option>
            <option value="PACKAGE">PACKAGE</option>
            <option value="PROCEDURE">PROCEDURE</option>
            <option value="FUNCTION">FUNCTION</option>
            <option value="TRIGGER">TRIGGER</option>
            <option value="JOB">JOB</option>
            <option value="OTHER">OTHER</option>
          </select>
          <select
            className="bg-white/5 border border-border p-3 rounded-lg text-sm"
            value={form.risk_level}
            onChange={(e) => onChange('risk_level', e.target.value)}
          >
            <option value="LOW">LOW</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HIGH">HIGH</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <input
            className="bg-white/5 border border-border p-3 rounded-lg text-sm"
            placeholder="Recomanació (opcional)"
            value={form.recommendation}
            onChange={(e) => onChange('recommendation', e.target.value)}
          />
          <input
            className="bg-white/5 border border-border p-3 rounded-lg text-sm"
            placeholder="Descripció (opcional)"
            value={form.description}
            onChange={(e) => onChange('description', e.target.value)}
          />
          <textarea
            className="md:col-span-2 bg-white/5 border border-border p-3 rounded-lg text-sm"
            placeholder="Motiu (obligatori)"
            value={form.reason}
            onChange={(e) => onChange('reason', e.target.value)}
            rows={3}
          />
        </div>
        <div className="mt-4">
          <button
            onClick={submit}
            disabled={loading}
            className="flex items-center gap-2 bg-primary px-4 py-2 rounded-lg font-bold shadow-lg shadow-primary/20 disabled:opacity-50"
          >
            <Plus size={16} /> Afegir al registre
          </button>
        </div>
      </div>

      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-bold uppercase tracking-wider opacity-60">Entrades ({items.length})</h4>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[10px] font-bold uppercase text-muted-foreground border-b border-white/10">
              <tr>
                <th className="pb-3">id</th>
                <th className="pb-3">schema</th>
                <th className="pb-3">objecte</th>
                <th className="pb-3">tipus</th>
                <th className="pb-3">risc</th>
                <th className="pb-3">recomanació</th>
                <th className="pb-3">origen</th>
                <th className="pb-3">motiu</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((it) => (
                <tr key={it.id} className="hover:bg-white/5">
                  <td className="py-3 font-mono text-xs">{it.id}</td>
                  <td className="py-3 font-mono text-xs">{it.schema_name}</td>
                  <td className="py-3 font-mono text-xs">{it.object_name}</td>
                  <td className="py-3 text-xs">{it.object_type}</td>
                  <td className="py-3 text-xs">
                    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${
                      it.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700 border-red-200' :
                      it.risk_level === 'HIGH' ? 'bg-orange-100 text-orange-700 border-orange-200' :
                      it.risk_level === 'MEDIUM' ? 'bg-blue-100 text-blue-700 border-blue-200' :
                      'bg-gray-100 text-gray-600 border-gray-200'
                    }`}>
                      {it.risk_level}
                    </span>
                  </td>
                  <td className="py-3 text-xs">{it.recommendation || '-'}</td>
                  <td className="py-3 text-xs opacity-70">{it.source}</td>
                  <td className="py-3 text-xs opacity-80 max-w-[520px] truncate" title={it.reason || ''}>{it.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {items.length === 0 && (
          <div className="mt-4 text-xs text-muted-foreground italic">No hi ha entrades al registre.</div>
        )}
      </div>
    </div>
  );
}

