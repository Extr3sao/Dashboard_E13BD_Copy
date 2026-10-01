import React from 'react';
import { ArrowLeft, Check, ClipboardCheck, Lightbulb, Search, ShieldCheck, X } from 'lucide-react';
import {
  confirmInvestigationCause, getInvestigation, getInvestigations, recordInvestigationResolution,
  getCapacityProjection, setInvestigationStatus, updateInvestigationCheck, updateInvestigationHypothesis,
} from '../api/investigations.js';

const panel = 'rounded-xl border border-white/10 bg-white/5 p-4';
const date = (value) => value ? new Date(Number(value) * 1000).toLocaleString() : '—';
const kindClass = { FACT: 'border-sky-400/50 bg-sky-500/10', EVENT: 'border-white/10 bg-white/5' };
const buildQueryFilters = (filters, database) => Object.fromEntries(Object.entries({ ...filters, database: database || filters.database }).filter(([, value]) => value));

export default function InvestigationsView({ database }) {
  const [items, setItems] = React.useState([]);
  const [selected, setSelected] = React.useState(null);
  const [cause, setCause] = React.useState('');
  const [resolution, setResolution] = React.useState('');
  const [actions, setActions] = React.useState('');
  const [projection, setProjection] = React.useState(null);
  const [capabilities, setCapabilities] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [filters, setFilters] = React.useState({ status: '', database: database || '', rule: '', category: '', object_name: '', cause: '' });
  const loadList = React.useCallback(async () => {
    const result = await getInvestigations({ ...buildQueryFilters(filters, database), limit: 100 });
    setItems(result.items || []);
  }, [database, filters]);

  const open = React.useCallback(async (id) => {
    setLoading(true); setError('');
    try {
      const result = await getInvestigation(id);
      setSelected(result); setCause(''); setResolution(''); setActions('');
      localStorage.setItem('e13db:selected-investigation-id', String(id));
    } catch (_error) { setError('Investigation detail is unavailable. Refresh the list and retry.'); }
    finally { setLoading(false); }
  }, []);

  React.useEffect(() => {
    if (!selected) { setProjection(null); return; }
    const sample=selected.facts?.find((fact) => fact.category==='CAPACITY' && fact.metric_name==='growth_bytes');
    if (!sample) { setProjection(null); return; }
    let active=true;
    getCapacityProjection(selected.id,sample.id).then((result) => { if (active) setProjection(result); }).catch(() => { if (active) setProjection({available:false,reason:'Capacity projection is unavailable for this evidence.'}); });
    return () => { active=false; };
  }, [selected]);

  React.useEffect(() => {
    let active = true;
    getInvestigations({ ...buildQueryFilters(filters, database), limit: 100 }).then((result) => { if (active) setItems(result.items || []); }).catch(() => { if (active) setError('Investigations are unavailable. Verify your session and service readiness.'); });
    import('axios').then(({ default: axios }) => axios.get('/api/investigations/capabilities').then((r) => { if (active) setCapabilities(r.data); }).catch(() => {}));
    const requested = localStorage.getItem('e13db:selected-investigation-id');
    if (requested) open(requested);
    const listener = (event) => { if (event.detail?.id) open(event.detail.id); };
    window.addEventListener('e13db-open-investigation', listener);
    return () => { active = false; window.removeEventListener('e13db-open-investigation', listener); };
  }, [database, open, filters]);

  const refresh = async () => { await loadList(); if (selected) await open(selected.id); };
  const doStatus = async (next) => { try { const result = await setInvestigationStatus(selected.id, next); setSelected(result); await loadList(); } catch (_error) { setError('Could not update investigation status.'); } };
  const doCause = async (event) => { event.preventDefault(); if (!cause.trim()) return; try { setSelected(await confirmInvestigationCause(selected.id, cause.trim())); setCause(''); } catch (_error) { setError('Could not record operator-confirmed cause.'); } };
  const doResolution = async (event) => { event.preventDefault(); if (!resolution.trim()) return; try { setSelected(await recordInvestigationResolution(selected.id, resolution.trim(), actions.trim())); setResolution(''); setActions(''); await loadList(); } catch (_error) { setError('Could not record resolution.'); } };
  const setCheck = async (check, next) => { try { setSelected(await updateInvestigationCheck(selected.id, check.id, next, next === 'COMPLETED' ? 'Operator completed this recommended check.' : '')); } catch (_error) { setError('Could not update recommended check.'); } };
  const setHypothesis = async (hypothesis, next) => { try { setSelected(await updateInvestigationHypothesis(selected.id, hypothesis.id, next)); } catch (_error) { setError('Could not update hypothesis status.'); } };

  return <section className="space-y-5" aria-label="DBA investigations">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-sky-200">Deterministic DBA intelligence</p><h2 className="text-3xl font-black">Investigations</h2><p className="text-sm text-muted-foreground">Observed facts, rule-based correlations, operator-reviewable hypotheses.</p></div><button type="button" onClick={refresh} className={`${panel} flex items-center gap-2`}><Search size={16}/> Refresh</button></header>
    {error && <p role="alert" className={`${panel} text-red-200`}>{error}</p>}
    {capabilities && <p className="text-xs text-muted-foreground">Oracle evidence uses stored, redacted Finding observations. AWR: {capabilities.awr.status}; ASH: {capabilities.ash.status}. No arbitrary SQL is executed.</p>}
    {selected ? <div className="space-y-5">
      <button type="button" onClick={() => { setSelected(null); localStorage.removeItem('e13db:selected-investigation-id'); }} className="flex items-center gap-2 text-sm text-sky-200"><ArrowLeft size={16}/> All investigations</button>
      <article className={`${panel} border-sky-400/30`}><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase text-sky-200">{selected.database_id} · {selected.source} · {date(selected.opened_at)}</p><h3 className="mt-1 text-xl font-black">{selected.summary}</h3><p className="mt-2 text-sm text-muted-foreground">Primary problem: {selected.primary_finding?.summary || selected.primary_finding?.rule_id || 'Database-level instability'} · {selected.primary_finding?.severity || '—'} · {selected.primary_finding?.delta || selected.status}</p></div><span className="rounded border border-white/20 px-3 py-1 text-sm font-bold">{selected.status}</span></div>
        <div className="mt-4 flex flex-wrap gap-2">{['OPEN', 'MONITORING', 'CLOSED'].filter((value) => selected.status !== value).map((value) => <button key={value} onClick={() => doStatus(value)} className="rounded border border-white/15 px-3 py-2 text-sm hover:bg-white/10">Set {value.toLowerCase()}</button>)}</div>
        {selected.recurrence?.length > 0 && <aside className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/5 p-3"><b>Similar historical investigation found.</b>{selected.recurrence.map((item) => <p key={item.id} className="mt-1 text-sm">{date(item.opened_at)} · {item.confirmed_cause ? `Previous confirmed cause: ${item.confirmed_cause}` : 'No operator-confirmed cause'} · {item.resolution ? `Resolution: ${item.resolution}` : 'No recorded resolution'}</p>)}<p className="text-xs text-muted-foreground">Historical resolution is context only; it is not applied automatically.</p></aside>}
      </article>

      <section aria-labelledby="facts-heading"><h3 id="facts-heading" className="mb-3 flex items-center gap-2 text-lg font-bold"><ShieldCheck size={19}/>1. Facts</h3><div className="space-y-2">{selected.facts?.length ? selected.facts.map((fact) => <article key={fact.id} className={`${panel} border-sky-400/20`}><div className="flex flex-wrap justify-between gap-2"><b>FACT · {fact.category.replaceAll('_', ' ')}</b><time className="text-xs text-muted-foreground">{date(fact.observed_at)}</time></div><p className="mt-1">{fact.summary}</p><p className="mt-1 text-xs text-muted-foreground">Rule {fact.rule_id}{fact.owner || fact.object_name ? ` · ${[fact.owner, fact.object_name, fact.object_type].filter(Boolean).join(' / ')}` : ''}{fact.metric_name ? ` · ${fact.metric_name}: ${fact.value_json}${fact.unit ? ` ${fact.unit}` : ''}` : ''}</p></article>) : <p className={panel}>No normalized audit observations are available in this time window yet.</p>}</div></section>
      {selected.lock_chain?.length > 0 && <section className={panel} aria-label="Blocking chain"><h3 className="font-bold">Observed blocking chain</h3><ol className="mt-2 space-y-1">{selected.lock_chain.map((edge,index) => <li key={`${edge.evidence_id}-${index}`}>Session {edge.blocking_session} blocked session {edge.blocked_session} · {date(edge.observed_at)}</li>)}</ol><p className="mt-1 text-xs text-muted-foreground">Only explicit session edges from stored evidence are shown.</p></section>}
      {projection && <section className={panel} aria-label="Capacity trend"><h3 className="font-bold">Capacity trend</h3>{projection.available ? <><p>Linear projection based on {projection.sample_count} observations · {date(projection.window_start)}–{date(projection.window_end)}</p><p>Projected threshold crossing: {date(projection.projected_threshold_at)}</p><p className="text-xs text-muted-foreground">{projection.assumption}</p></> : <p>{projection.reason}</p>}</section>}

      <section aria-labelledby="timeline-heading"><h3 id="timeline-heading" className="mb-3 text-lg font-bold">2. Timeline</h3><ol className="space-y-2">{selected.timeline?.map((event,index) => <li key={`${event.type}-${event.at}-${index}`} className={`${panel} ${kindClass[event.type] || ''}`}><time className="text-xs text-muted-foreground">{date(event.at)}</time><p><b>{event.type}</b> · {event.summary}</p></li>)}</ol></section>

      <section aria-labelledby="related-heading"><h3 id="related-heading" className="mb-3 text-lg font-bold">3. Related Findings & correlations</h3>{selected.correlations?.length ? <div className="space-y-2">{selected.correlations.map((correlation) => <article key={correlation.id} className={panel}><div className="flex justify-between gap-2"><b>{correlation.finding?.summary || correlation.finding?.rule_id || 'Related Finding'}</b><span className="text-xs font-bold">{correlation.strength}</span></div><p className="text-xs text-muted-foreground">{correlation.finding?.database_id} · {correlation.category.replaceAll('_',' ')} · {date(correlation.occurred_at)}</p><p className="mt-2 text-sm"><b>CORRELATION — why:</b> {correlation.reasons?.join(' · ')}</p></article>)}</div> : <p className={panel}>No related Finding met the documented temporal/object/rule relationship criteria.</p>}</section>

      <section aria-labelledby="hypothesis-heading"><h3 id="hypothesis-heading" className="mb-3 flex items-center gap-2 text-lg font-bold"><Lightbulb size={19}/>4. Hypotheses</h3>{selected.hypotheses?.length ? <div className="space-y-3">{selected.hypotheses.map((hypothesis) => { const evidenceById = new Map((selected.facts || []).map((fact) => [fact.id, fact])); return <article key={hypothesis.id} className={`${panel} border-amber-300/30`}><div className="flex flex-wrap justify-between gap-2"><b>HYPOTHESIS · {hypothesis.title}</b><span>{hypothesis.status.replaceAll('_',' ')}</span></div><p className="mt-2">{hypothesis.description}</p><details className="mt-3"><summary className="cursor-pointer font-semibold">Why this hypothesis?</summary><p className="mt-2 text-sm font-bold text-emerald-200">Supporting evidence</p>{hypothesis.supporting_evidence?.length ? hypothesis.supporting_evidence.map((id) => <p key={`s${id}`} className="text-sm">{evidenceById.get(id)?.summary || 'Linked observed evidence'}</p>) : <p className="text-sm">No supporting observation linked.</p>}<p className="mt-2 text-sm font-bold text-orange-200">Contradicting evidence</p>{hypothesis.contradicting_evidence?.length ? hypothesis.contradicting_evidence.map((id) => <p key={`c${id}`} className="text-sm">{evidenceById.get(id)?.summary || 'Linked observed evidence'}</p>) : <p className="text-sm">No contradicting observation identified in the available evidence.</p>}<p className="mt-2 text-xs text-muted-foreground">Deterministic relationship rules explain relevance, not causal probability. Only an operator can confirm a cause.</p></details><div className="mt-3 flex flex-wrap gap-2">{['SUPPORTED','WEAKENED','REJECTED','CONFIRMED_BY_OPERATOR'].filter((value) => value !== hypothesis.status).map((value) => <button key={value} onClick={() => setHypothesis(hypothesis,value)} className="rounded border border-white/15 px-2 py-1 text-xs">Mark {value.replaceAll('_',' ').toLowerCase()}</button>)}</div></article>; })}</div> : <p className={panel}>Insufficient overlapping evidence to generate a supported hypothesis. No cause is inferred.</p>}</section>

      <section aria-labelledby="checks-heading"><h3 id="checks-heading" className="mb-3 flex items-center gap-2 text-lg font-bold"><ClipboardCheck size={19}/>5. Recommended checks</h3><div className="space-y-2">{selected.recommended_checks?.length ? selected.recommended_checks.map((check) => <article key={check.id} className={panel}><div className="flex flex-wrap items-center justify-between gap-2"><p>{check.description}</p><span className="text-xs font-bold">{check.status}</span></div>{check.result_summary && <p className="text-sm text-muted-foreground">Result: {check.result_summary}</p>}{check.status === 'PENDING' && <div className="mt-2 flex gap-2"><button onClick={() => setCheck(check,'COMPLETED')} className="flex items-center gap-1 rounded border border-emerald-400/30 px-2 py-1 text-xs"><Check size={14}/> Completed</button><button onClick={() => setCheck(check,'NOT_APPLICABLE')} className="flex items-center gap-1 rounded border border-white/15 px-2 py-1 text-xs"><X size={14}/> Not applicable</button></div>}</article>) : <p className={panel}>No next checks can be recommended from the current evidence.</p>}</div></section>

      <section className="grid gap-4 xl:grid-cols-2"><form onSubmit={doCause} className={`${panel} space-y-2`}><h3 className="font-bold">Operator-confirmed cause</h3><p className="text-xs text-muted-foreground">This is operator knowledge, distinct from engine hypotheses.</p>{selected.confirmed_cause && <p>{selected.confirmed_cause} · {selected.cause_actor} · {date(selected.cause_at)}</p>}<textarea value={cause} onChange={(event) => setCause(event.target.value)} maxLength={500} className="w-full rounded border border-white/15 bg-black/20 p-2" placeholder="Describe confirmed cause and evidence basis"/><button className="rounded bg-primary px-3 py-2 text-sm" disabled={!cause.trim()}>Record confirmed cause</button></form>
      <form onSubmit={doResolution} className={`${panel} space-y-2`}><h3 className="font-bold">Resolution record</h3>{selected.resolution && <p>{selected.resolution} · {selected.resolved_by} · {date(selected.resolved_at)}</p>}<input value={resolution} onChange={(event) => setResolution(event.target.value)} maxLength={500} className="w-full rounded border border-white/15 bg-black/20 p-2" placeholder="Resolution summary"/><input value={actions} onChange={(event) => setActions(event.target.value)} maxLength={500} className="w-full rounded border border-white/15 bg-black/20 p-2" placeholder="Actions taken (optional)"/><button className="rounded bg-primary px-3 py-2 text-sm" disabled={!resolution.trim()}>Record resolution</button></form></section>
      {selected.primary_finding?.evidence && <details className={panel}><summary className="cursor-pointer font-semibold">Original redacted Finding evidence</summary><pre className="mt-2 whitespace-pre-wrap break-all text-xs">{typeof selected.primary_finding.evidence === 'string' ? selected.primary_finding.evidence : JSON.stringify(selected.primary_finding.evidence,null,2)}</pre></details>}
    </div> : <><div className="grid grid-cols-2 gap-3 md:grid-cols-4">{['OPEN','MONITORING','RESOLVED','CLOSED'].map((value) => <article key={value} className={panel}><b className="text-xs text-muted-foreground">{value}</b><p className="text-2xl font-black">{items.filter((item) => item.status===value).length}</p></article>)}</div><div className={`${panel} grid gap-2 md:grid-cols-3 xl:grid-cols-6`} aria-label="Investigation filters"><select aria-label="Filter status" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))} className="rounded border border-white/15 bg-slate-900 p-2"><option value="">All statuses</option>{['OPEN','MONITORING','RESOLVED','CLOSED'].map((value) => <option key={value}>{value}</option>)}</select>{[['database','Database'],['rule','Rule'],['category','Evidence category'],['object_name','Object'],['cause','Confirmed cause']].map(([key,label]) => <input key={key} aria-label={`Filter ${label}`} value={filters[key]} onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))} placeholder={label} className="min-w-0 rounded border border-white/15 bg-black/20 p-2" />)}</div>{loading ? <p>Loading investigations…</p> : items.length ? <div className="space-y-2">{items.map((item) => <button key={item.id} onClick={() => open(item.id)} className={`${panel} grid w-full gap-2 text-left hover:bg-white/10 md:grid-cols-[1.2fr_1fr_.7fr_1fr]`}><span><b>{item.database_id}</b><span className="block text-xs text-muted-foreground">Primary problem</span><span>{item.primary_finding?.summary || item.summary}</span></span><span><b>{item.primary_finding?.severity || 'DATABASE'}</b><span className="block text-xs text-muted-foreground">Top hypothesis</span><span>{item.top_hypothesis || 'No hypothesis supported'}</span></span><span><b>{item.status}</b><span className="block text-xs text-muted-foreground">Started</span><span>{date(item.opened_at)}</span></span><span><b>Next recommended check</b><span className="block text-sm">{item.next_recommended_check || 'No pending check'}</span></span></button>)}</div> : <p className={panel}>No investigations match these filters. High-priority and critical worsening Findings are opened automatically; an operator can also open an investigation from a Finding.</p>}</>}
  </section>;
}
