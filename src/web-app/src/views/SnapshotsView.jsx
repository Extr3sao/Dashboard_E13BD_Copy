import React, { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import {
  ResponsiveContainer,
  PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { RefreshCcw, Download, Filter } from 'lucide-react';

import { latestSnapshot, querySnapshot, exportSnapshotCsv } from '../api/snapshots.js';

const COLORS = ['#22c55e', '#2563eb', '#f97316', '#ef4444', '#a855f7', '#06b6d4', '#eab308'];

function kpi(n, digits = 2) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(digits) : '0.00';
}

export default function SnapshotsView() {
  const [loading, setLoading] = useState(false);
  const [snapshotId, setSnapshotId] = useState('');
  const [facets, setFacets] = useState({ schemas: [], recommendations: [] });
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({ total_objects: 0, total_gb: 0, avg_score: 0, drop_count: 0 });
  const [error, setError] = useState('');

  const [schemas, setSchemas] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [minScore, setMinScore] = useState(0);
  const [sortBy, setSortBy] = useState('score');
  const [sortDir, setSortDir] = useState('desc');
  const exportCsvCacheRef = useRef(new Map());

  const payload = useMemo(() => ({
    snapshot_id: snapshotId || undefined,
    schemas,
    recommendations,
    min_score: minScore,
    limit: 1000,
    offset: 0,
    sort_by: sortBy,
    sort_dir: sortDir,
  }), [snapshotId, schemas, recommendations, minScore, sortBy, sortDir]);
  const exportCacheScopeKey = useMemo(() => JSON.stringify({
    snapshotId,
    payload,
  }), [payload, snapshotId]);

  const fetchInitial = async () => {
    setLoading(true);
    setError('');
    try {
      const latest = await latestSnapshot();
      const sid = latest?.snapshot?.snapshot_id || '';
      setSnapshotId(sid);
      const q = await querySnapshot({ ...payload, snapshot_id: sid || undefined });
      setRows(q.rows || []);
      setSummary(q.summary || {});
      setFacets(q.facets || { schemas: [], recommendations: [] });
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Error carregant les captures');
    } finally {
      setLoading(false);
    }
  };

  const fetchWithFilters = async () => {
    setLoading(true);
    setError('');
    try {
      const q = await querySnapshot(payload);
      setRows(q.rows || []);
      setSummary(q.summary || {});
      setFacets(q.facets || { schemas: [], recommendations: [] });
      setSnapshotId(q.snapshot_id || snapshotId);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Error carregant la captura');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitial();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    exportCsvCacheRef.current.clear();
  }, [exportCacheScopeKey]);

  const pieData = useMemo(() => {
    const bySchema = new Map();
    for (const r of rows || []) {
      const k = String(r.schema ?? '');
      const v = Number(r.size_gb ?? 0) || 0;
      bySchema.set(k, (bySchema.get(k) || 0) + v);
    }
    return [...bySchema.entries()]
      .map(([name, value]) => ({ name, value: Number(value.toFixed(6)) }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 12);
  }, [rows]);

  const top10 = useMemo(() => {
    return [...(rows || [])]
      .map(r => ({ ...r, size_gb: Number(r.size_gb ?? 0) || 0 }))
      .sort((a, b) => (b.size_gb - a.size_gb))
      .slice(0, 10);
  }, [rows]);

  const scatter = useMemo(() => {
    const eps = 1e-6;
    return (rows || []).map(r => ({
      table_name: r.table_name,
      schema: r.schema,
      size_gb: Math.max(Number(r.size_gb ?? 0) || 0, eps),
      score: Number(r.score ?? 0) || 0,
      recommendation: r.recommendation,
    }));
  }, [rows]);

  const toggleSort = (col) => {
    if (sortBy === col) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col);
      setSortDir('desc');
    }
  };

  const handleExportCsv = async () => {
    try {
      const cacheKey = exportCacheScopeKey;
      const cached = exportCsvCacheRef.current.get(cacheKey);
      if (cached) {
        const url = window.URL.createObjectURL(cached.blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = cached.fileName;
        a.click();
        return;
      }
      const res = await exportSnapshotCsv(payload);
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const fileName = `snapshot_export_${snapshotId || 'latest'}.csv`;
      exportCsvCacheRef.current.set(cacheKey, { blob, fileName });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      a.click();
    } catch (e) {
      alert(e?.response?.data?.detail || e?.message || 'Error exportant CSV');
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <div className="glass-card p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-xl font-bold">Captures (Legacy Dashboard)</h3>
            <p className="text-xs text-muted-foreground">Captura activa: <span className="font-mono">{snapshotId || 'latest'}</span></p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={fetchWithFilters}
              disabled={loading}
              className="flex items-center gap-2 bg-primary px-4 py-2 rounded-lg font-bold shadow-lg shadow-primary/20 disabled:opacity-50"
            >
              <Filter size={16} /> Aplicar filtres
            </button>
            <button
              onClick={fetchInitial}
              disabled={loading}
              className="flex items-center gap-2 bg-white/5 border border-border px-4 py-2 rounded-lg hover:bg-white/10 transition-all font-semibold disabled:opacity-50"
            >
              <RefreshCcw size={16} className={clsx(loading && 'animate-spin')} /> Actualitzar
            </button>
            <button
              onClick={handleExportCsv}
              className="flex items-center gap-2 bg-white/5 border border-border px-4 py-2 rounded-lg hover:bg-white/10 transition-all font-semibold"
            >
              <Download size={16} /> Exportar CSV
            </button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-200 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl border border-white/10 bg-white/5">
            <p className="text-[10px] font-bold uppercase opacity-50 mb-2">Schemas</p>
            <select
              multiple
              value={schemas}
              onChange={(e) => setSchemas([...e.target.selectedOptions].map(o => o.value))}
              className="w-full bg-black/30 border border-border rounded-lg p-2 text-xs font-mono h-36"
            >
              {facets.schemas.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <div className="mt-2 flex justify-between text-[10px] opacity-50">
              <span>Seleccionats: {schemas.length}</span>
              <button onClick={() => setSchemas([])} className="underline">Neteja</button>
            </div>
          </div>

          <div className="p-4 rounded-xl border border-white/10 bg-white/5">
            <p className="text-[10px] font-bold uppercase opacity-50 mb-2">Recomanació</p>
            <select
              multiple
              value={recommendations}
              onChange={(e) => setRecommendations([...e.target.selectedOptions].map(o => o.value))}
              className="w-full bg-black/30 border border-border rounded-lg p-2 text-xs font-mono h-36"
            >
              {facets.recommendations.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <div className="mt-2 flex justify-between text-[10px] opacity-50">
              <span>Seleccionats: {recommendations.length}</span>
              <button onClick={() => setRecommendations([])} className="underline">neteja</button>
            </div>
          </div>

          <div className="p-4 rounded-xl border border-white/10 bg-white/5">
            <p className="text-[10px] font-bold uppercase opacity-50 mb-2">Puntuació mínima</p>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0"
                max="100"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full"
              />
              <span className="font-mono text-xs w-10 text-right">{minScore}</span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <button
                onClick={() => { setSortBy('score'); setSortDir('desc'); }}
                className={clsx("px-3 py-2 rounded-lg border border-white/10", sortBy === 'score' ? "bg-primary/20 text-primary" : "bg-white/5")}
              >
                Ordre: Puntuació
              </button>
              <button
                onClick={() => { setSortBy('size_gb'); setSortDir('desc'); }}
                className={clsx("px-3 py-2 rounded-lg border border-white/10", sortBy === 'size_gb' ? "bg-primary/20 text-primary" : "bg-white/5")}
              >
                Ordre: Mida
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="glass-card p-6">
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Total Objectes</p>
          <p className="text-3xl font-black mt-2">{summary.total_objects ?? 0}</p>
        </div>
        <div className="glass-card p-6">
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Mida Total (GB)</p>
          <p className="text-3xl font-black mt-2">{kpi(summary.total_gb, 3)}</p>
        </div>
        <div className="glass-card p-6">
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Candidats DROP</p>
          <p className="text-3xl font-black mt-2">{summary.drop_count ?? 0}</p>
        </div>
        <div className="glass-card p-6">
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Avg Score</p>
          <p className="text-3xl font-black mt-2">{kpi(summary.avg_score, 1)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="glass-card p-6 h-[420px]">
          <h4 className="text-sm font-bold uppercase tracking-wider opacity-60 mb-3">Distribució de mida per esquema</h4>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={140} innerRadius={70}>
                  {pieData.map((_, idx) => <Cell key={idx} fill={COLORS[idx % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #ffffff10', borderRadius: '12px' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-card p-6 h-[420px]">
          <h4 className="text-sm font-bold uppercase tracking-wider opacity-60 mb-3">Top 10 objectes més pesats</h4>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={top10} margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                <XAxis dataKey="table_name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #ffffff10', borderRadius: '12px' }} />
                <Bar dataKey="size_gb" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="glass-card p-6 h-[480px]">
        <h4 className="text-sm font-bold uppercase tracking-wider opacity-60 mb-3">Score vs Mida (log)</h4>
        <div className="h-[420px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ left: 10, right: 10, top: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis type="number" dataKey="size_gb" scale="log" domain={['dataMin', 'dataMax']} tick={{ fontSize: 10 }} name="size_gb" />
              <YAxis type="number" dataKey="score" domain={[0, 100]} tick={{ fontSize: 10 }} name="score" />
              <ZAxis type="number" range={[40, 200]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #ffffff10', borderRadius: '12px' }} />
              <Scatter data={scatter} fill="#22c55e" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-bold uppercase tracking-wider opacity-60">Backlog filtrat</h4>
          <p className="text-xs text-muted-foreground">Ordenació: <span className="font-mono">{sortBy} {sortDir}</span></p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[10px] font-bold uppercase text-muted-foreground border-b border-white/10">
              <tr>
                <th className="pb-3 cursor-pointer" onClick={() => toggleSort('schema')}>schema</th>
                <th className="pb-3 cursor-pointer" onClick={() => toggleSort('table_name')}>table</th>
                <th className="pb-3 cursor-pointer text-right" onClick={() => toggleSort('size_gb')}>size_gb</th>
                <th className="pb-3 cursor-pointer text-right" onClick={() => toggleSort('days_inactive')}>days_inactive</th>
                <th className="pb-3 cursor-pointer text-right" onClick={() => toggleSort('score')}>score</th>
                <th className="pb-3 cursor-pointer" onClick={() => toggleSort('recommendation')}>recommendation</th>
                <th className="pb-3">risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {(rows || []).map((r, i) => (
                <tr key={i} className="hover:bg-white/5">
                  <td className="py-3 font-mono text-xs">{r.schema}</td>
                  <td className="py-3 font-mono text-xs">{r.table_name}</td>
                  <td className="py-3 text-right font-mono text-xs">{kpi(r.size_gb, 3)}</td>
                  <td className="py-3 text-right font-mono text-xs">{r.days_inactive}</td>
                  <td className="py-3 text-right font-mono text-xs">{kpi(r.score, 1)}</td>
                  <td className="py-3 text-xs">{r.recommendation}</td>
                  <td className="py-3 text-xs opacity-70">{r.risk_level}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {(summary.total_objects || 0) > (rows || []).length && (
          <div className="mt-4 text-xs text-muted-foreground">
            Mostrant {rows.length} de {summary.total_objects}. Augmenta `limit` al backend si necessites visualitzar-ho tot d'un cop.
          </div>
        )}
      </div>
    </div>
  );
}
