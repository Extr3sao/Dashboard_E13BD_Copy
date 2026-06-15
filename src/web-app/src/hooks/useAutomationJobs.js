import { useEffect, useState } from 'react';
import {
  createAutomationJob,
  deleteAutomationJob,
  runAutomationJobNow,
  updateAutomationJob,
} from '../api/automation.js';
import { buildPayload, emptyForm } from '../utils/automationViewUtils.js';

export function useAutomationJobs({ profiles, refreshAll, setError, setMessage }) {
  const [saving, setSaving] = useState(false);
  const [editingJobId, setEditingJobId] = useState(null);
  const [form, setForm] = useState(emptyForm(profiles[0]));

  useEffect(() => {
    if (!form.profile && profiles.length > 0) {
      setForm((current) => ({ ...current, profile: profiles[0] }));
    }
  }, [profiles, form.profile]);

  const resetForm = () => {
    setEditingJobId(null);
    setForm(emptyForm(profiles[0]));
  };

  const handleSaveJob = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      if (form.audit_type === 'post_crq_distribution' && form.lot_scope_mode === 'selected' && (form.selected_lots || []).length === 0) {
        throw new Error('Selecciona almenys un lot quan l àmbit es manual');
      }
      if (form.audit_type === 'post_crq_distribution' && !form.include_summary && !form.include_lot_reports) {
        throw new Error('Activa resum general o report individual per lot');
      }
      const payload = buildPayload(form);
      if (editingJobId) {
        await updateAutomationJob(editingJobId, payload);
        setMessage('Automatització actualitzada.');
      } else {
        await createAutomationJob(payload);
        setMessage('Automatització creada.');
      }
      await refreshAll();
      resetForm();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut desar el job");
    } finally {
      setSaving(false);
    }
  };

  const handleRunNow = async (jobId) => {
    try {
      await runAutomationJobNow(jobId);
      setMessage('Execució iniciada.');
      setTimeout(() => refreshAll(), 1200);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut iniciar el job");
    }
  };

  const handleToggleJob = async (job) => {
    try {
      await updateAutomationJob(job.id, { enabled: !job.enabled });
      await refreshAll();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut canviar l'estat del job");
    }
  };

  const handleDeleteJob = async (jobId) => {
    try {
      await deleteAutomationJob(jobId);
      await refreshAll();
      if (editingJobId === jobId) {
        resetForm();
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No s'ha pogut esborrar el job");
    }
  };

  return {
    editingJobId,
    form,
    handleDeleteJob,
    handleRunNow,
    handleSaveJob,
    handleToggleJob,
    resetForm,
    saving,
    setEditingJobId,
    setForm,
  };
}
