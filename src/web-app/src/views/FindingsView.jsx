import React from 'react';
import { AlertTriangle, CheckCircle2, ChevronRight, ShieldAlert, X } from 'lucide-react';
import { applyFindingAction, getFinding, getFindings, getNeedsAttention } from '../api/findings.js';
import { getInvestigations, openInvestigation } from '../api/investigations.js';

const priorityClass = { P1: 'border-red-500/50 bg-red-500/15 text-red-200', P2: 'border-orange-400/50 bg-orange-500/15 text-orange-100', P3: 'border-amber-400/50 bg-amber-500/15 text-amber-100', P4: 'border-sky-400/40 bg-sky-500/10 text-sky-100' };

function formatTime(value) {
  return value ? new Date(Number(value) * 1000).toLocaleString() : '—';
}

export default function FindingsView({ database }) {
  const [attention, setAttention] = React.useState([]);
  const [findings, setFindings] = React.useState([]);
  const [summary, setSummary] = React.useState({ findings: {}, red_flags: {} });
  const [selected, setSelected] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const [filter, setFilter] = React.useState('');
  const [action, setAction] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [reviewDate, setReviewDate] = React.useState('');
  const [investigations, setInvestigations] = React.useState([]);

  const load = React.useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [queue, result, cases] = await Promise.all([getNeedsAttention(database ? { database } : {}), getFindings({ ...(filter ? { delta: filter } : {}), ...(database ? { database } : {}) }), getInvestigations({ ...(database ? { database } : {}), limit: 10 })]);
      setAttention(queue.items || []); setSummary(queue.summary || { findings: {}, red_flags: {} }); setFindings(result.items || []); setInvestigations(cases.items || []);
    } catch (_error) { setError('No s’han pogut carregar els problemes operatius.'); }
    finally { setLoading(false); }
  }, [filter, database]);

  React.useEffect(() => { load(); }, [load]);

  const openFinding = React.useCallback(async (id) => {
    try { setSelected(await getFinding(id)); setAction(''); setReason(''); setReviewDate(''); }
    catch (_error) { setError('No s’ha pogut carregar el detall del finding.'); }
  }, []);

  React.useEffect(() => {
    const requested=localStorage.getItem('e13db:selected-finding-id');
    if (!requested) return;
    localStorage.removeItem('e13db:selected-finding-id');
    openFinding(Number(requested));
  }, [openFinding]);

  async function submitAction(event) {
    event.preventDefault();
    if (!selected || !action || !reason.trim()) return;
    try {
      const updated = await applyFindingAction(selected.id, action, { reason: reason.trim(), review_date: reviewDate || undefined });
      setSelected(updated); await load();
    } catch (_error) { setError('No s’ha pogut guardar l’acció de l’operador.'); }
  }

  async function investigateSelected() {
    if (!selected) return;
    try {
      const investigation = await openInvestigation(selected.database_id, selected.id);
      localStorage.setItem('e13db:selected-investigation-id', String(investigation.id));
      window.dispatchEvent(new CustomEvent('e13db-open-investigation', { detail: { id: investigation.id } }));
    } catch (_error) { setError('Could not open an investigation for this Finding.'); }
  }

  function openCase(id) {
    localStorage.setItem('e13db:selected-investigation-id', String(id));
    window.dispatchEvent(new CustomEvent('e13db-open-investigation', { detail: { id } }));
  }

  return <section className="space-y-6" aria-label="Problems">
    {selected && <button type="button" onClick={investigateSelected} className="fixed bottom-6 right-6 z-[60] rounded-lg border border-sky-400/50 bg-sky-700 px-4 py-3 text-sm font-bold shadow-xl hover:bg-sky-600">Open investigation for this Finding</button>}
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-4">
      <div><p className="text-xs font-bold uppercase tracking-[0.16em] text-sky-200">Operational intelligence</p><h2 className="text-2xl font-black text-foreground">Problems</h2></div>
      <button type="button" onClick={load} className="rounded-lg border border-white/15 px-3 py-2 text-sm font-semibold hover:bg-white/10">Refresh</button>
    </header>
    {error && <div role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Red flags summary">
      {['P1', 'P2', 'P3', 'P4'].map((priority) => <div key={priority} className={`rounded-lg border p-4 ${priorityClass[priority]}`}><div className="text-xs font-bold">RED FLAGS {priority}</div><div className="mt-1 text-3xl font-black">{summary.red_flags?.[priority] || 0}</div></div>)}
    </div>
    <section className="rounded-xl border border-white/10 bg-white/5 p-4" aria-label="Database investigations"><h3 className="mb-2 font-bold">Active Investigations{database ? ` · ${database}` : ''}</h3>{investigations.filter((item) => ['OPEN','MONITORING'].includes(item.status)).length ? <div className="space-y-2">{investigations.filter((item) => ['OPEN','MONITORING'].includes(item.status)).slice(0,5).map((item) => <button key={item.id} onClick={() => openCase(item.id)} className="w-full rounded border border-white/10 p-3 text-left hover:bg-white/10"><b>{item.primary_finding?.summary || item.summary}</b><span className="block text-xs text-muted-foreground">{item.status} · {item.top_hypothesis || 'No hypothesis supported'}</span>{item.recent_correlation && <span className="block text-xs text-sky-100">Recent correlation: {item.recent_correlation.strength} · {item.recent_correlation.reasons.join(' · ')}</span>}</button>)}</div> : <p className="text-sm text-muted-foreground">No active investigations for this database.</p>}</section>
    <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-bold uppercase text-muted-foreground">Findings</span>{['', 'NEW', 'WORSENING', 'PERSISTENT', 'IMPROVING', 'RESOLVED'].map((delta) => <button key={delta || 'all'} onClick={() => setFilter(delta)} className={`rounded-md border px-2 py-1 text-xs ${filter === delta ? 'border-primary bg-primary text-primary-foreground' : 'border-white/15 hover:bg-white/10'}`}>{delta ? `${delta[0]}${delta.slice(1).toLowerCase()} ${summary.findings?.[delta] || 0}` : 'All'}</button>)}</div>
    <div className="grid gap-6 xl:grid-cols-[1.25fr_.75fr]">
      <div className="space-y-3"><h3 className="flex items-center gap-2 text-lg font-bold"><ShieldAlert size={19}/>Needs Attention</h3>{loading ? <p className="text-sm text-muted-foreground">Loading operational state…</p> : attention.length === 0 ? <p className="rounded-lg border border-white/10 p-5 text-sm text-muted-foreground">No active red flags.</p> : attention.map((item) => <button key={item.id} type="button" onClick={() => item.finding_id && openFinding(item.finding_id)} className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg border border-white/10 bg-white/5 p-4 text-left hover:bg-white/10"><span className={`rounded border px-2 py-1 text-xs font-black ${priorityClass[item.priority]}`}>{item.priority}</span><span><span className="block font-bold">{item.finding_summary || item.flag_type}</span><span className="block text-sm text-muted-foreground">{item.database_id} · {item.finding_delta || item.flag_type}</span><span className="block pt-1 text-xs text-sky-100">{item.explanation}</span></span><ChevronRight size={18}/></button>)}</div>
      <div className="space-y-3"><h3 className="flex items-center gap-2 text-lg font-bold"><AlertTriangle size={19}/>Active Findings</h3><div className="max-h-[520px] space-y-2 overflow-auto pr-1">{findings.map((item) => <button key={item.id} type="button" onClick={() => openFinding(item.id)} className="w-full rounded-lg border border-white/10 p-3 text-left hover:bg-white/10"><span className="font-semibold">{item.summary || item.rule_id}</span><span className="block text-xs text-muted-foreground">{item.database_id} · {item.severity} · {item.delta} · {item.occurrences} observations</span></button>)}</div></div>
    </div>
    {selected && <div className="fixed inset-0 z-50 flex justify-end bg-black/55" role="dialog" aria-modal="true" aria-label="Finding detail"><aside className="h-full w-full max-w-2xl overflow-y-auto border-l border-white/15 bg-slate-950 p-6 shadow-2xl"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase text-sky-200">{selected.database_id} · {selected.rule_id}</p><h3 className="text-xl font-black">{selected.summary || 'Finding'}</h3></div><button type="button" title="Close finding detail" onClick={() => setSelected(null)} className="rounded-md p-2 hover:bg-white/10"><X size={19}/></button></div><dl className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><dt className="text-muted-foreground">Severity / status</dt><dd>{selected.severity} · {selected.status}</dd></div><div><dt className="text-muted-foreground">Evolution</dt><dd>{selected.delta}</dd></div><div><dt className="text-muted-foreground">First seen</dt><dd>{formatTime(selected.first_seen)}</dd></div><div><dt className="text-muted-foreground">Last seen / occurrences</dt><dd>{formatTime(selected.last_seen)} · {selected.occurrences}</dd></div><div><dt className="text-muted-foreground">Current / previous value</dt><dd>{selected.current_value || '—'} / {selected.previous_value || '—'}</dd></div><div><dt className="text-muted-foreground">Object</dt><dd>{[selected.owner, selected.object_name, selected.object_type].filter(Boolean).join(' · ') || 'Rule-level'}</dd></div></dl><div className="mt-5 space-y-3"><div><h4 className="font-bold">Recommended action</h4><p className="text-sm text-muted-foreground">{selected.recommendation || 'Review the rule evidence and correct the underlying condition.'}</p></div><div><h4 className="font-bold">Evidence</h4><pre className="mt-1 overflow-auto rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-slate-200">{selected.evidence || '{}'}</pre></div><div><h4 className="font-bold">History</h4><ol className="mt-2 space-y-2">{(selected.history || []).map((event) => <li key={event.id} className="border-l border-sky-400/50 pl-3 text-sm"><b>{event.delta}</b> · {formatTime(event.observed_at)} · {event.value || 'resolved'}</li>)}</ol></div></div><form onSubmit={submitAction} className="mt-6 border-t border-white/10 pt-5"><h4 className="font-bold">Operator action</h4><div className="mt-2 flex flex-wrap gap-2">{[['acknowledge', 'Acknowledge'], ['accept-risk', 'Accept Risk'], ['false-positive', 'False Positive']].map(([value, label]) => <button key={value} type="button" onClick={() => setAction(value)} className={`rounded-md border px-3 py-2 text-sm ${action === value ? 'border-primary bg-primary text-primary-foreground' : 'border-white/15'}`}>{label}</button>)}</div>{action && <><label className="mt-3 block text-sm font-semibold">Reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} required className="mt-1 min-h-20 w-full rounded-md border border-white/15 bg-black/20 p-2" /></label>{action === 'accept-risk' && <label className="mt-2 block text-sm font-semibold">Review date<input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} className="ml-2 rounded border border-white/15 bg-black/20 p-1" /></label>}<button type="submit" className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-bold text-primary-foreground"><CheckCircle2 size={16}/>Save action</button></>}</form></aside></div>}
  </section>;
}
