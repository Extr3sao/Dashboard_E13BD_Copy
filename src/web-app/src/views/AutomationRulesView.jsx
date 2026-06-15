import React, { useEffect, useMemo, useState } from 'react';

import {
  listAutomationTasks,
  listSeverityRules,
  updateAutomationTask,
  updateSeverityRule,
} from '../api/automation.js';

const TASK_STATUSES = ['pendent', 'en_curs', 'resolta', 'descartada'];

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '-';
  if (typeof value === 'object') return Object.keys(value).length ? JSON.stringify(value) : '-';
  return String(value);
}

export default function AutomationRulesView() {
  const [rules, setRules] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [taskStatus, setTaskStatus] = useState('');

  const pendingTasks = useMemo(
    () => tasks.filter((task) => !['resolta', 'descartada'].includes(task.status)),
    [tasks],
  );

  async function loadData(status = taskStatus) {
    setLoading(true);
    setError('');
    try {
      const [rulesResponse, tasksResponse] = await Promise.all([
        listSeverityRules('global'),
        listAutomationTasks(status || null),
      ]);
      setRules(rulesResponse.items || []);
      setTasks(tasksResponse.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'No s han pogut carregar les regles i tasques.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData('');
  }, []);

  async function handleRuleToggle(rule) {
    const updated = await updateSeverityRule(rule.id, { enabled: !rule.enabled });
    setRules((current) => current.map((item) => (item.id === rule.id ? updated : item)));
  }

  async function handleTaskStatusChange(task, status) {
    const updated = await updateAutomationTask(task.id, { status });
    setTasks((current) => current.map((item) => (item.id === task.id ? updated : item)));
  }

  return (
    <section className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Regles globals</div>
          <div className="mt-2 text-3xl font-bold">{rules.length}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Safata interna de tasques</div>
          <div className="mt-2 text-3xl font-bold">{tasks.length}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Pendents</div>
          <div className="mt-2 text-3xl font-bold">{pendingTasks.length}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={taskStatus}
          onChange={(event) => {
            const nextStatus = event.target.value;
            setTaskStatus(nextStatus);
            loadData(nextStatus);
          }}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="">Tots els estats</option>
          {TASK_STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => loadData()}
          className="rounded-lg border border-border px-3 py-2 text-sm font-semibold hover:bg-white/10"
        >
          Actualitzar
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
          {error}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-3">
          <h3 className="text-lg font-bold">Regles globals</h3>
          {loading && <div className="text-sm text-muted-foreground">Carregant regles...</div>}
          {!loading && rules.length === 0 && (
            <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">No hi ha regles globals configurades.</div>
          )}
          {rules.map((rule) => (
            <article key={rule.id} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">{rule.severity}</div>
                  <div className="text-xs text-muted-foreground">
                    Prioritat {formatValue(rule.task_priority)} · Destinataris {formatValue(rule.recipients)}
                  </div>
                </div>
                <label className="flex items-center gap-2 text-xs font-semibold">
                  <input
                    type="checkbox"
                    checked={Boolean(rule.enabled)}
                    onChange={() => handleRuleToggle(rule)}
                  />
                  Activa
                </label>
              </div>
              <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <div>Tasca: {rule.create_task ? 'sí' : 'no'}</div>
                <div>Email: {rule.send_email ? 'sí' : 'no'}</div>
                <div>Informe: {rule.attach_report ? 'sí' : 'no'}</div>
              </div>
            </article>
          ))}
        </div>

        <div className="space-y-3">
          <h3 className="text-lg font-bold">Safata interna de tasques</h3>
          {loading && <div className="text-sm text-muted-foreground">Carregant tasques...</div>}
          {!loading && tasks.length === 0 && (
            <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">No hi ha tasques amb aquest filtre.</div>
          )}
          {tasks.map((task) => (
            <article key={task.id} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">{task.title || `Tasca #${task.id}`}</div>
                  <div className="text-xs text-muted-foreground">
                    {formatValue(task.priority)} · {formatValue(task.assigned_to)} · {formatValue(task.created_at)}
                  </div>
                </div>
                <select
                  value={task.status || 'pendent'}
                  onChange={(event) => handleTaskStatusChange(task, event.target.value)}
                  className="rounded-lg border border-border bg-background px-2 py-1 text-xs"
                >
                  {TASK_STATUSES.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </div>
              {task.description && (
                <p className="mt-3 text-sm text-muted-foreground">{task.description}</p>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
