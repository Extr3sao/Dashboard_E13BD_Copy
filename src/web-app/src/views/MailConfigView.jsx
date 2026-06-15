import React, { useEffect, useState } from 'react';
import { Mail, Save, RefreshCcw, Send, Settings, Share2, MessageSquare, Plus, Trash2 } from 'lucide-react';
import { getDeliveryConfig, getDeliveryRoutes, updateDeliveryConfig, updateDeliveryRoutes, testDeliveryEmail } from '../api/automation.js';

function emptyProviderRoute() {
  return {
    provider_code: '',
    label: '',
    emails_text: '',
    enabled: true,
  };
}

export default function MailConfigView() {
  const [config, setConfig] = useState({
    smtp_host: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    smtp_use_tls: true,
    from_email: '',
    default_recipients: [],
    default_recipients_text: '',
    failure_notification_recipients: [],
    failure_notification_recipients_text: '',
    tic_summary_recipients: [],
    tic_summary_recipients_text: '',
    provider_routes: [],
    teams_webhook: '',
    sharepoint_site: '',
    sharepoint_library: '',
    sharepoint_folder: '',
    auto_purge_enabled: true,
    history_retention_days: 30,
    retry_retention_days: 30,
    last_auto_purge_at: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [testRecipient, setTestRecipient] = useState('');

  const loadConfig = async () => {
    setLoading(true);
    try {
      const [data, routes] = await Promise.all([getDeliveryConfig(), getDeliveryRoutes()]);
      const configDefaults = {
        smtp_host: '',
        smtp_port: 587,
        smtp_username: '',
        smtp_password: '',
        smtp_use_tls: true,
        from_email: '',
        default_recipients: [],
        default_recipients_text: '',
        failure_notification_recipients: [],
        failure_notification_recipients_text: '',
        tic_summary_recipients: [],
        tic_summary_recipients_text: '',
        provider_routes: [],
        teams_webhook: '',
        sharepoint_site: '',
        sharepoint_library: '',
        sharepoint_folder: '',
        auto_purge_enabled: true,
        history_retention_days: 30,
        retry_retention_days: 30,
        last_auto_purge_at: '',
      };
      setConfig({
        ...configDefaults,
        ...data,
        default_recipients_text: (data.default_recipients || []).join(', '),
        failure_notification_recipients_text: (data.failure_notification_recipients || []).join(', '),
        tic_summary_recipients: (routes.tic_summary_recipients || []).map(item => {
          if (typeof item === 'object' && item !== null) {
            return { email: item.email || '', enabled: item.enabled !== false };
          }
          return { email: String(item), enabled: true };
        }),
        tic_summary_recipients_text: '', // No el farem servir ja
        provider_routes: (routes.providers || []).map((item) => ({
          provider_code: item.provider_code || '',
          label: item.label || '',
          emails_text: (item.emails || []).join(', '),
          enabled: item.enabled !== false,
        })),
      });
    } catch (err) {
      setMessage({ type: 'error', text: 'Error carregant la configuració: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });
    try {
      const deliveryConfigPayload = {
        ...config,
        smtp_port: Number(config.smtp_port),
        history_retention_days: Number(config.history_retention_days || 30),
        retry_retention_days: Number(config.retry_retention_days || 30),
        default_recipients: (config.default_recipients_text || '').split(/[\s,;]+/).map(s => s.trim()).filter(Boolean),
        failure_notification_recipients: (config.failure_notification_recipients_text || '').split(/[\s,;]+/).map(s => s.trim()).filter(Boolean),
      };
      const deliveryRoutesPayload = {
        tic_summary_recipients: (config.tic_summary_recipients || [])
          .map(item => ({
            email: item.email.trim(),
            enabled: !!item.enabled
          }))
          .filter(item => item.email),
        providers: (config.provider_routes || [])
          .map((item) => ({
            provider_code: item.provider_code.trim(),
            label: (item.label || item.provider_code).trim(),
            emails: String(item.emails_text || '').split(',').map((email) => email.trim()).filter(Boolean),
            enabled: !!item.enabled,
          }))
          .filter((item) => item.provider_code),
      };
      await updateDeliveryConfig(deliveryConfigPayload);
      await updateDeliveryRoutes(deliveryRoutesPayload);
      setMessage({ type: 'success', text: 'Configuració desada correctament.' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Error desant: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testRecipient) {
      setMessage({ type: 'error', text: 'Introdueix un correu per al test.' });
      return;
    }
    setTesting(true);
    setMessage({ type: '', text: '' });
    try {
      const payload = {
        ...config,
        smtp_port: Number(config.smtp_port),
        default_recipients: (config.default_recipients_text || '').split(/[\s,;]+/).map(s => s.trim()).filter(Boolean),
        recipient: testRecipient,
      };
      const res = await testDeliveryEmail(payload);
      setMessage({ type: 'success', text: res.message || 'Correu de prova enviat!' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Error en el test: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setTesting(false);
    }
  };

  const addTicRecipient = () => {
    setConfig(current => ({
      ...current,
      tic_summary_recipients: [...(current.tic_summary_recipients || []), { email: '', enabled: true }]
    }));
  };

  const updateTicRecipient = (index, field, value) => {
    setConfig(current => ({
      ...current,
      tic_summary_recipients: (current.tic_summary_recipients || []).map((item, i) => 
        i === index ? { ...item, [field]: value } : item
      )
    }));
  };

  const removeTicRecipient = (index) => {
    setConfig(current => ({
      ...current,
      tic_summary_recipients: (current.tic_summary_recipients || []).filter((_, i) => i !== index)
    }));
  };

  const updateProviderRoute = (index, field, value) => {
    setConfig((current) => ({
      ...current,
      provider_routes: (current.provider_routes || []).map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      )),
    }));
  };

  const addProviderRoute = () => {
    setConfig((current) => ({
      ...current,
      provider_routes: [...(current.provider_routes || []), emptyProviderRoute()],
    }));
  };

  const removeProviderRoute = (index) => {
    setConfig((current) => ({
      ...current,
      provider_routes: (current.provider_routes || []).filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-20">
        <RefreshCcw className="animate-spin text-primary" size={48} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="glass-card p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-widest text-primary">
              <Settings size={14} />
              Configuració
            </div>
            <h3 className="text-3xl font-extrabold tracking-tight text-primary">Configuració del servidor</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              Gestiona com es distribueixen els reports d'auditoria. Configura el servidor de correu, webhooks de Teams i connectors de SharePoint.
            </p>
          </div>
        </div>
      </div>

      {message.text && (
        <div className={`p-4 rounded-xl border ${message.type === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-200' : 'bg-green-500/10 border-green-500/20 text-green-200'}`}>
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        {/* BLOC SMTP */}
        <div className="glass-card p-6 flex flex-col gap-6">
          <div className="flex items-center gap-3 border-b border-white/10 pb-4">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
              <Mail size={20} />
            </div>
            <h4 className="text-lg font-bold text-foreground">Servidor de Correu (SMTP)</h4>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Servidor Host</label>
              <input 
                value={config.smtp_host} 
                onChange={e => setConfig({...config, smtp_host: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="Ex: smtp.office365.com" 
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Port</label>
              <input 
                type="number"
                value={config.smtp_port} 
                onChange={e => setConfig({...config, smtp_port: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="587" 
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Usuari SMTP</label>
              <input 
                value={config.smtp_username} 
                onChange={e => setConfig({...config, smtp_username: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="usuari@exemple.com" 
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Contrasenya</label>
              <input 
                type="password"
                value={config.smtp_password} 
                onChange={e => setConfig({...config, smtp_password: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="••••••••" 
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Correu Remitent</label>
              <input 
                value={config.from_email} 
                onChange={e => setConfig({...config, from_email: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="noreply@exemple.com" 
              />
            </div>
            <div className="flex items-end pb-1 ml-1">
              <label className="flex items-center gap-3 cursor-pointer group">
                <input 
                  type="checkbox" 
                  checked={config.smtp_use_tls} 
                  onChange={e => setConfig({...config, smtp_use_tls: e.target.checked})}
                  className="w-4 h-4 rounded border-white/20 bg-white/5 text-primary focus:ring-0 focus:ring-offset-0"
                />
                <span className="text-sm font-semibold group-hover:text-primary transition-colors">Utilitza TLS / SSL</span>
              </label>
            </div>
          </div>
          
          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Destinataris per defecte (CSV)</label>
            <textarea 
              value={config.default_recipients_text} 
              onChange={e => setConfig({...config, default_recipients_text: e.target.value})}
              className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary min-h-[80px] transition-all" 
              placeholder="usuari1@exemple.com, usuari2@exemple.com"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Destinataris d'error de generació (CSV)</label>
            <textarea
              value={config.failure_notification_recipients_text}
              onChange={e => setConfig({ ...config, failure_notification_recipients_text: e.target.value })}
              className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary min-h-[80px] transition-all"
              placeholder="suport@exemple.com, dba@exemple.com"
            />
            <p className="text-xs text-muted-foreground">
              Rebran l'avís quan una auditoria no pugui generar l'informe i, per tant, no s'enviï cap report normal.
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-300">
                <RefreshCcw size={20} />
              </div>
              <div>
                <h5 className="text-base font-bold text-foreground">Retenció i purga automàtica</h5>
                <p className="mt-1 text-xs text-muted-foreground">Controla quants dies es conserven l'històric i els reintents tancats. La purga automàtica s'executa una vegada al dia.</p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={config.auto_purge_enabled !== false}
                  onChange={e => setConfig({ ...config, auto_purge_enabled: e.target.checked })}
                  className="w-4 h-4 rounded border-white/20 bg-white/5 text-primary focus:ring-0 focus:ring-offset-0"
                />
                Activa purga automàtica diària
              </label>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-muted-foreground">
                {config.last_auto_purge_at ? `Darrera purga automàtica: ${config.last_auto_purge_at}` : "Encara no s'ha executat cap purga automàtica."}
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Dies d'històric</label>
                <input
                  type="number"
                  min="1"
                  value={config.history_retention_days}
                  onChange={e => setConfig({ ...config, history_retention_days: e.target.value })}
                  className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Dies per a reintents tancats</label>
                <input
                  type="number"
                  min="1"
                  value={config.retry_retention_days}
                  onChange={e => setConfig({ ...config, retry_retention_days: e.target.value })}
                  className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-8">
          <div className="glass-card p-6 flex flex-col gap-6">
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-300">
                <Send size={20} />
              </div>
              <h4 className="text-lg font-bold text-foreground">Rutes de distribució Post-CRQ</h4>
            </div>

            <div className="flex items-center justify-between gap-3">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Destinataris Àrea TIC</label>
              <button
                type="button"
                onClick={addTicRecipient}
                className="inline-flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/10 px-2 py-1 text-xs font-bold text-primary hover:bg-primary/15"
              >
                <Plus size={12} />
                Afegir
              </button>
            </div>

            <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto pr-1 custom-scrollbar">
              {(config.tic_summary_recipients || []).map((item, index) => (
                <div key={`tic-recipient-${index}`} className="flex items-center gap-2">
                  <input
                    value={item.email}
                    onChange={e => updateTicRecipient(index, 'email', e.target.value)}
                    className="flex-1 rounded-xl border border-border bg-white/5 p-2 text-sm outline-none focus:ring-1 focus:ring-primary transition-all"
                    placeholder="correu@exemple.com"
                  />
                  <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs cursor-pointer hover:bg-white/10 transition-colors shrink-0">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      onChange={e => updateTicRecipient(index, 'enabled', e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-primary focus:ring-0"
                    />
                    Actiu
                  </label>
                  <button
                    type="button"
                    onClick={() => removeTicRecipient(index)}
                    className="p-2 rounded-xl border border-red-500/20 bg-red-500/10 text-red-200 hover:bg-red-500/20 transition-colors shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {(!config.tic_summary_recipients || config.tic_summary_recipients.length === 0) && (
                <div className="text-center py-4 rounded-xl border border-dashed border-white/10 text-xs text-muted-foreground">
                  No hi ha destinataris TIC. Clica "Afegir" per començar.
                </div>
              )}
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h5 className="text-sm font-bold uppercase tracking-wider opacity-70">Mapa proveïdor - correus</h5>
                <p className="mt-1 text-xs text-muted-foreground">Cada codi de proveïdor correspon al `lot_code` detectat en el report Post-CRQ.</p>
              </div>
              <button
                type="button"
                onClick={addProviderRoute}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-sm font-semibold text-primary hover:bg-primary/15 sm:w-auto"
              >
                <Plus size={14} />
                Afegir ruta
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {(config.provider_routes || []).map((item, index) => (
                <div key={`provider-route-${index}`} className="min-w-0 rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1.7fr)_auto_auto]">
                    <input
                      value={item.provider_code}
                      onChange={e => updateProviderRoute(index, 'provider_code', e.target.value.toUpperCase())}
                      className="min-w-0 rounded-xl border border-border bg-white/5 p-3 text-sm font-mono outline-none focus:ring-1 focus:ring-primary"
                      placeholder="LOT_APP"
                    />
                    <input
                      value={item.label}
                      onChange={e => updateProviderRoute(index, 'label', e.target.value)}
                      className="min-w-0 rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      placeholder="Nom visible"
                    />
                    <textarea
                      value={item.emails_text}
                      onChange={e => updateProviderRoute(index, 'emails_text', e.target.value)}
                      className="min-h-[46px] min-w-0 resize-y rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary"
                      placeholder="proveidor@exemple.com, suport@exemple.com"
                    />
                    <label className="inline-flex min-w-0 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
                      <input
                        type="checkbox"
                        checked={item.enabled}
                        onChange={e => updateProviderRoute(index, 'enabled', e.target.checked)}
                      />
                      Actiu
                    </label>
                    <button
                      type="button"
                      onClick={() => removeProviderRoute(index)}
                      className="inline-flex items-center justify-center rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-red-200 hover:bg-red-500/15"
                      aria-label={`Eliminar ruta ${item.provider_code || index + 1}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
              {(!config.provider_routes || config.provider_routes.length === 0) && (
                <div className="rounded-xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-muted-foreground">
                  No hi ha rutes de proveïdor configurades.
                </div>
              )}
            </div>
          </div>

          {/* BLOC TEAMS */}
          <div className="glass-card p-6 flex flex-col gap-6">
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                <MessageSquare size={20} />
              </div>
              <h4 className="text-lg font-bold text-foreground">Microsoft Teams</h4>
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Webhook URL</label>
              <input 
                value={config.teams_webhook} 
                onChange={e => setConfig({...config, teams_webhook: e.target.value})}
                className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                placeholder="https://outlook.office.com/webhook/..." 
              />
              <p className="text-[10px] text-muted-foreground mt-1 ml-1 italic">Els reports s'enviaran com a targetes interactives als canals configurats.</p>
            </div>
          </div>

          {/* BLOC SHAREPOINT */}
          <div className="glass-card p-6 flex flex-col gap-6">
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                <Share2 size={20} />
              </div>
              <h4 className="text-lg font-bold text-foreground">SharePoint Online</h4>
            </div>
            <div className="grid grid-cols-1 gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Site URL / ID</label>
                <input 
                  value={config.sharepoint_site} 
                  onChange={e => setConfig({...config, sharepoint_site: e.target.value})}
                  className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                  placeholder="Ex: dte_bbdd_audits" 
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Biblioteca</label>
                  <input 
                    value={config.sharepoint_library} 
                    onChange={e => setConfig({...config, sharepoint_library: e.target.value})}
                    className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                    placeholder="Documents" 
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Carpeta</label>
                  <input 
                    value={config.sharepoint_folder} 
                    onChange={e => setConfig({...config, sharepoint_folder: e.target.value})}
                    className="rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
                    placeholder="Reports/Audit" 
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="glass-card p-6 flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex flex-col gap-4 w-full md:w-auto md:min-w-[300px]">
          <label className="text-xs font-bold text-muted-foreground uppercase ml-1">Prova de tramesa</label>
          <div className="flex gap-2">
            <input 
              value={testRecipient} 
              onChange={e => setTestRecipient(e.target.value)}
              className="flex-1 rounded-xl border border-border bg-white/5 p-3 text-sm outline-none focus:ring-1 focus:ring-primary transition-all" 
              placeholder="Correu de test" 
            />
            <button 
              onClick={handleTest}
              disabled={testing || saving}
              className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-6 text-sm font-bold text-primary hover:bg-primary/20 transition-all disabled:opacity-50"
            >
              {testing ? <RefreshCcw size={16} className="animate-spin" /> : <Send size={16} />}
              Test
            </button>
          </div>
        </div>

        <div className="flex gap-4 w-full md:w-auto">
          <button 
            onClick={loadConfig}
            disabled={loading || saving}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-white/5 px-8 py-4 text-sm font-bold hover:bg-white/10 transition-all"
          >
            <RefreshCcw size={18} />
            Descartar
          </button>
          <button 
            onClick={handleSave}
            disabled={saving || loading}
            className="flex-1 md:flex-none inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-10 py-4 text-sm font-black text-primary-foreground shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {saving ? <RefreshCcw size={18} className="animate-spin" /> : <Save size={18} />}
            Desar Configuració
          </button>
        </div>
      </div>
    </div>
  );
}
