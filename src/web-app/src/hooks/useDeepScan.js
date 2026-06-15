import { useState } from 'react';
import axios from 'axios';

export default function useDeepScan({
  apiBase,
  selectedProfile,
  defaultScoringConfig,
}) {
  const [auditData, setAuditData] = useState([]);
  const [selectedAuditIndex, setSelectedAuditIndex] = useState(0);
  const [isAuditing, setIsAuditing] = useState(false);
  const [schemaToAudit, setSchemaToAudit] = useState('');
  const [scoringMenuOpen, setScoringMenuOpen] = useState(false);
  const [scoringHelpOpen, setScoringHelpOpen] = useState(false);
  const [scoringConfig, setScoringConfig] = useState(defaultScoringConfig);
  const [testStatusDeep, setTestStatusDeep] = useState(null);

  function runDeepAudit() {
    if (!schemaToAudit) return alert('Escriu un esquema o llista!');

    const cleanInput = schemaToAudit.replace(/['"]/g, '').trim();

    setIsAuditing(true);
    setAuditData([]);
    setSelectedAuditIndex(0);

    axios.get(`${apiBase}/audit/deep-scan/${encodeURIComponent(cleanInput)}?profile=${selectedProfile}`)
      .then((res) => {
        const results = Array.isArray(res.data) ? res.data : [res.data];
        setAuditData(results);
        setIsAuditing(false);
        if (results.length > 0) setSelectedAuditIndex(0);
      })
      .catch((err) => {
        alert(`Error: ${err.response?.data?.detail || err.message}`);
        setIsAuditing(false);
      });
  }

  function handleTestDeepConnection() {
    if (!selectedProfile) return alert('Selecciona un perfil!');
    setTestStatusDeep({ status: 'loading', msg: 'Provant...' });
    axios.post(`${apiBase}/db/test`, { profile: selectedProfile })
      .then((res) => {
        setTestStatusDeep({ status: res.data.status, msg: res.data.message });
        setTimeout(() => setTestStatusDeep(null), 5000);
      })
      .catch((err) => {
        setTestStatusDeep({ status: 'error', msg: err.message });
      });
  }

  return {
    auditData,
    selectedAuditIndex,
    setSelectedAuditIndex,
    isAuditing,
    schemaToAudit,
    setSchemaToAudit,
    scoringMenuOpen,
    setScoringMenuOpen,
    scoringHelpOpen,
    setScoringHelpOpen,
    scoringConfig,
    setScoringConfig,
    testStatusDeep,
    runDeepAudit,
    handleTestDeepConnection,
  };
}
