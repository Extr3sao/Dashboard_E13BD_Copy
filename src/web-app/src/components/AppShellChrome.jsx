import React from 'react';
import { Settings, ShieldAlert, Network } from 'lucide-react';

function SidebarItem({ icon: Icon, label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`nav-tab ${active ? 'nav-tab-active' : ''}`}
    >
      <Icon size={16} />
      <span>{label}</span>
    </button>
  );
}

export default function AppShellChrome({
  showProfileSelector,
  selectedProfile,
  onProfileChange,
  profiles,
  activeTab,
  onSelectMainTab,
}) {
  const handleSkipToContent = (event) => {
    event.preventDefault();
    const mainContent = document.getElementById('main-content');
    if (!mainContent) return;

    window.location.hash = 'main-content';
    mainContent.focus();
  };

  return (
    <>
      <a className="skip-link" href="#main-content" onClick={handleSkipToContent}>
        Salta al contingut
      </a>
      <div className="top-stripe" aria-hidden="true" />
      <header className="topbar">
        <div className="brand">
          <img
            className="brand-logo brand-logo-light"
            src="/logo-educacio.png"
            alt="Departament d'Educacio"
          />
          <img
            className="brand-logo brand-logo-dark"
            src="/logo-educacio-blanc.png"
            alt="Departament d'Educacio"
          />
          <div className="brand-mark" aria-hidden="true">
            <ShieldAlert size={16} />
          </div>
          <div className="brand-text">
            <h1 className="brand-title">Oracle Audit</h1>
            <span className="brand-sub">Portal principal d'aplicacions internes</span>
          </div>
        </div>

        {showProfileSelector && (
          <div className="topbar-actions">
            <label className="text-xs font-bold uppercase text-muted-foreground">Connexió activa</label>
            <select
              value={selectedProfile}
              onChange={(event) => onProfileChange(event.target.value)}
              className="h-10 min-w-[220px] rounded-lg border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-primary"
            >
              {profiles.map((profile) => (
                <option key={profile} value={profile}>{profile}</option>
              ))}
            </select>
          </div>
        )}
      </header>

      <nav className="top-nav" aria-label="Navegació principal">
        <SidebarItem
          icon={ShieldAlert}
          label="Auditoria BBDD"
          active={activeTab === 'Auditoria BBDD'}
          onClick={() => onSelectMainTab('Auditoria BBDD')}
        />
        <SidebarItem
          icon={Network}
          label="Arquitectura"
          active={activeTab === 'Arquitectura'}
          onClick={() => onSelectMainTab('Arquitectura')}
        />
        <button
          disabled
          className="nav-tab opacity-30 cursor-not-allowed"
          title="Configuració deshabilitada"
        >
          <Settings size={16} />
          <span>Configuració</span>
        </button>
      </nav>
    </>
  );
}
