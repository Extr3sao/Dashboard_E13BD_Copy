import { useEffect, useState } from 'react';

function getRequestedProfile() {
  if (typeof window === 'undefined') return '';
  const url = new URL(window.location.href);
  return String(url.searchParams.get('profile') || '').trim();
}

function normalizeDatabaseAuditSubtab(storedMainTab, storedSubtab) {
  if (storedMainTab === 'Repositori') return "Repositori d'obsolets";
  if (storedMainTab === 'Obsolets') return 'Anàlisi obsolets';
  if (storedMainTab === 'Tutorial') return 'Guia i Ajuda';
  if (storedMainTab === 'Gestió Checks' || storedMainTab === 'Gestió de controls') return 'Gestió de controls';
  if (
    storedMainTab === 'Notificacions'
    || storedMainTab === 'Configuració servidor correu'
    || storedMainTab === 'Configuració del servidor'
  ) {
    return 'Configuració del servidor';
  }

  if (storedSubtab === 'Gestió de consultes') return 'Gestió de controls';
  if (storedSubtab === 'Configuració servidor correu') return 'Configuració del servidor';
  return storedSubtab;
}

export default function usePersistedNavigationState() {
  const [activeTab, setActiveTab] = useState(() => {
    const storedTab = localStorage.getItem('activeTab') || 'Auditoria BBDD';
    const availableTabs = ['Auditoria BBDD'];
    return availableTabs.includes(storedTab) ? storedTab : 'Auditoria BBDD';
  });
  const [selectedProfile, setSelectedProfile] = useState(() => getRequestedProfile() || localStorage.getItem('selectedProfile') || '');
  const [databaseAuditSubtab, setDatabaseAuditSubtab] = useState(() => {
    const storedMainTab = localStorage.getItem('activeTab') || 'Anàlisi';
    const storedSubtab = localStorage.getItem('databaseAuditSubtab') || 'Anàlisi obsolets';
    return normalizeDatabaseAuditSubtab(storedMainTab, storedSubtab);
  });

  useEffect(() => {
    const requestedProfile = getRequestedProfile();
    if (requestedProfile && requestedProfile !== selectedProfile) {
      setSelectedProfile(requestedProfile);
    }
  }, [selectedProfile]);

  useEffect(() => {
    localStorage.setItem('activeTab', activeTab);
  }, [activeTab]);

  useEffect(() => {
    localStorage.setItem('databaseAuditSubtab', databaseAuditSubtab);
  }, [databaseAuditSubtab]);

  useEffect(() => {
    if (selectedProfile) {
      localStorage.setItem('selectedProfile', selectedProfile);
    }
  }, [selectedProfile]);

  return {
    activeTab,
    setActiveTab,
    selectedProfile,
    setSelectedProfile,
    databaseAuditSubtab,
    setDatabaseAuditSubtab,
  };
}
