import React from 'react';
import axios from 'axios';

const when = (value) => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString() : 'Not yet recorded';
const bytes = (value) => `${((value || 0) / 1024 / 1024).toFixed(1)} MiB`;
const panel = 'rounded-lg border border-white/10 bg-white/5 p-4';

export default function OperationsView() {
  const [summary, setSummary] = React.useState(null);
  const [events, setEvents] = React.useState([]);
  const [preview, setPreview] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');
  const load = React.useCallback(async () => {
    const [health, timeline] = await Promise.all([axios.get('/api/operations/summary'), axios.get('/api/operations/timeline')]);
    setSummary(health.data); setEvents(Array.isArray(timeline.data.items) ? timeline.data.items : []); setError('');
  }, []);
  React.useEffect(() => {
    let active = true;
    const refresh = () => { if (active) load().catch(() => { if (active) setError('Operations unavailable. Verify service readiness and your session.'); }); };
    refresh(); const timer = setInterval(refresh, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [load]);
  const action = async (name) => {
    setBusy(true); setError(''); setMessage('');
    try {
      if (name === 'retention') {
        setPreview((await axios.get('/api/operations/retention/preview')).data);
        setMessage('Preview only. No records deleted. Execute bounded purge offline with the runbook.');
      } else {
        const result = (await axios.post(`/api/operations/${name}`)).data;
        setMessage(name === 'backups' ? `Backup verified: ${result.backup_id}` : name === 'integrity-check' ? `Integrity: ${result.status}` : `Health check: ${result.status}`);
        await load();
      }
    } catch (err) { setError(err.response?.data?.detail || 'Operational action failed; verify disk space and storage permissions.'); }
    finally { setBusy(false); }
  };
  return <section aria-label="E13DB Operations" className="space-y-5">
    <header><h2 className="text-2xl font-black">Operations</h2><p className="text-muted-foreground">Service health, recovery and data protection</p></header>
    {error && <p role="alert" className={`${panel} text-red-200`}>{error}</p>}
    {message && <p role="status" className={panel}>{message}</p>}
    {!summary ? <p>Loading service health…</p> : <>
      <div className={panel}><h3 className="font-bold">E13DB STATUS</h3><p className={`text-3xl font-black ${summary.status === 'HEALTHY' ? 'text-emerald-300' : 'text-amber-200'}`}>{summary.status}</p><p>{summary.reason}</p><p className="mt-2 text-sm text-muted-foreground">Updated {when(summary.updated_at)}. Target database health is available in Fleet Dashboard.</p></div>
      <div className="flex flex-wrap gap-3">{[['health-check', 'Run health check'], ['integrity-check', 'Run integrity check'], ['backups', 'Create Backup'], ['retention', 'Preview retention purge']].map(([id, label]) => <button key={id} disabled={busy} onClick={() => action(id)} className={`${panel} disabled:opacity-50`}>{label}</button>)}</div>
      <div><h3 className="mb-3 font-bold">Component health</h3><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{Object.entries(summary.components || {}).map(([name, health]) => <article key={name} className={panel}><h4 className="font-bold">{name}</h4><b className={health.status === 'HEALTHY' ? 'text-emerald-300' : 'text-amber-200'}>{health.status}</b><p className="my-2 text-sm">{health.reason}</p><dl className="text-xs text-muted-foreground"><dt>Last success</dt><dd>{when(health.last_success)}</dd><dt>Last failure</dt><dd>{when(health.last_failure)}</dd></dl>{['DEGRADED', 'FAILED'].includes(health.status) && <p className="mt-3 text-sm"><b>Recommended action:</b> {health.recommended_action}</p>}</article>)}</div></div>
      <div className="grid gap-4 md:grid-cols-2">
        <article className={panel}><h3 className="font-bold">Scheduler</h3><p>{summary.scheduler?.enabled ? 'Enabled' : 'Disabled'}</p><p className="break-all">Owner: {summary.scheduler?.owner || 'No owner'}</p><p>Heartbeat: {when(summary.scheduler?.heartbeat)}</p><p>Last tick: {when(summary.scheduler?.last_tick)}</p><p>Next audit: {when(summary.scheduler?.next_scheduled_audit)}</p><p>Running: {summary.scheduler?.running_jobs || 0} · Queued: {summary.scheduler?.queued_jobs || 0} · Failed/interrupted history: {summary.scheduler?.failed_jobs || 0}</p><p>Missed execution policy: {summary.scheduler?.missed_policy}</p></article>
        <article className={panel}><h3 className="font-bold">Storage & disk</h3>{(summary.storage || []).map((store) => <div key={store.name} className="my-3"><b>{store.name}: {store.disk_status}</b><p>Database: {bytes(store.database_size)} · WAL: {bytes(store.wal_size)}</p><p>Available disk space: {bytes(store.available_bytes)}</p></div>)}<p>Integrity: {summary.integrity?.status || 'Unknown'} · {when(summary.integrity?.checked_at)}</p></article>
        <article className={panel}><h3 className="font-bold">Backup</h3><p>Last backup: {when(summary.backup?.created_at)}</p><p>Status: {summary.backup?.status || 'No backup yet'}</p><p>Size: {bytes(summary.backup?.size)}</p><p>Backup storage: {bytes(summary.backup_storage_size)} · change since refresh: {bytes(summary.backup_growth_bytes_since_last_check)}</p><p>Integrity: {summary.backup?.integrity || 'Unknown'}</p><p>Next scheduled backup: {summary.scheduler?.enabled ? when(summary.next_scheduled_backup) : 'Scheduler disabled'}</p><p className="mt-3 text-sm text-muted-foreground">Restore requires downtime. Follow CPD_OPERATIONS_RUNBOOK.md.</p></article>
        <article className={panel}><h3 className="font-bold">Configuration</h3><p>{summary.configuration?.status || 'Unknown'}</p>{summary.configuration?.diagnostics?.map((item, index) => <p key={index}>{item.level}: {item.reason}</p>)}<h4 className="mt-4 font-bold">Retention (days)</h4>{Object.entries(summary.retention || {}).map(([name, days]) => <p key={name}>{name.replaceAll('_', ' ')}: {days}</p>)}</article>
        <article className={panel}><h3 className="font-bold">Notification delivery</h3><p>Last attempt: {when(summary.notification_delivery?.last_attempt)}</p><p>Status: {summary.notification_delivery?.last_status || 'Unknown'}</p><p>Consecutive failures: {summary.notification_delivery?.consecutive_failures || 0}</p><p className="mt-2 text-sm">Email failures degrade delivery only; audits and findings continue.</p></article>
      </div>
      {preview && <article className={panel}><h3 className="font-bold">Purge preview — no changes made</h3><p>Oldest audit: {when(preview.oldest_audit)}</p><p>Oldest finding history: {when(preview.oldest_finding_history)}</p>{Object.entries(preview.eligible_records).map(([name, count]) => <p key={name}>{name.replaceAll('_', ' ')}: {count} eligible</p>)}<p className="mt-2 text-sm">{preview.reclaim_note}</p></article>}
      <article className={panel}><h3 className="mb-3 font-bold">Recent operational events</h3>{events.length ? <ol className="space-y-2">{events.map((event) => <li key={event.id}><time className="text-xs text-muted-foreground">{when(event.created_at)}</time> <b>{event.component} · {event.status}</b><p className="text-sm">{event.reason}</p></li>)}</ol> : <p>No operational events recorded.</p>}</article>
    </>}
  </section>;
}
