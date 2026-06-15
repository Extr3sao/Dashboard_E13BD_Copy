import { Suspense, lazy, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import AppPageHeader from './components/AppPageHeader.jsx';
import AppShellChrome from './components/AppShellChrome.jsx';
import {
  API_BASE,
  DEFAULT_POST_CRQ_CRITICALITY_OVERRIDES,
  DEFAULT_POST_CRQ_SCHEDULER_OPTIONS,
  DEFAULT_POST_CRQ_TIME_FILTER,
  DEFAULT_SCORING_CONFIG,
  resolvePageHelpKey,
} from './config/appShellConfig.js';
import {
  DATABASE_AUDIT_SUBTABS_HIDE_GLOBAL_REPORT,
  DATABASE_AUDIT_SUBTABS_HIDE_PROFILE_SELECTOR,
} from './config/databaseAuditTabs.js';
import useDeepScan from './hooks/useDeepScan.js';
import useGlobalReport from './hooks/useGlobalReport.js';
import usePersistedNavigationState from './hooks/usePersistedNavigationState.js';
import usePostCrqAudit from './hooks/usePostCrqAudit.js';
import useProfiles from './hooks/useProfiles.js';
const DatabaseAuditWorkspace = lazy(() => import('./views/DatabaseAuditWorkspace.jsx'));
const SystemArchitectureView = lazy(() => import('./views/SystemArchitectureView.jsx'));


function App() {
  const [isEmbedded] = useState(() => typeof window !== 'undefined' && window.self !== window.top);
  const [requestedProfile] = useState(() => {
    if (typeof window === 'undefined') return '';
    return String(new URL(window.location.href).searchParams.get('profile') || '').trim();
  });
  const {
    activeTab,
    setActiveTab,
    selectedProfile,
    setSelectedProfile,
    databaseAuditSubtab,
    setDatabaseAuditSubtab,
  } = usePersistedNavigationState();
  const { profiles } = useProfiles({
    apiBase: API_BASE,
    onDefaultProfile: setSelectedProfile,
    preferredProfile: requestedProfile || selectedProfile,
  });
  const {
    postCrqChecks,
    selectedChecks,
    setSelectedChecks,
    postCrqSchemas,
    setPostCrqSchemas,
    postCrqTimeFilter,
    setPostCrqTimeFilter,
    postCrqChecksLoading,
    isPostCrqRunning,
    postCrqReportData,
    postCrqError,
    postCrqExecutionOrigin,
    postCrqSchedulerOptions,
    setPostCrqSchedulerOptions,
    postCrqCriticalityOverrides,
    setPostCrqCriticalityOverrides,
    fetchPostCrqChecks,
    handleRunPostCrqAudit,
    handleDownloadPostCrqQueries,
    resetPostCrqCriticalityOverrides,
    openPostCrqSnapshot,
    rerunPostCrqAuditFromSnapshot,
  } = usePostCrqAudit({
    activeTab,
    databaseAuditSubtab,
    selectedProfile,
    defaultTimeFilter: DEFAULT_POST_CRQ_TIME_FILTER,
    defaultSchedulerOptions: DEFAULT_POST_CRQ_SCHEDULER_OPTIONS,
    defaultCriticalityOverrides: DEFAULT_POST_CRQ_CRITICALITY_OVERRIDES,
  });
  const {
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
  } = useDeepScan({
    apiBase: API_BASE,
    selectedProfile,
    defaultScoringConfig: DEFAULT_SCORING_CONFIG,
  });
  const currentPageHelpKey = resolvePageHelpKey(activeTab, databaseAuditSubtab);
  const { loading, handleGenerateReport } = useGlobalReport({
    apiBase: API_BASE,
    activeTab,
    databaseAuditSubtab,
    selectedProfile,
    auditData,
    postCrqReportData,
  });
  const hideEmbeddedProfileSelector = (
    activeTab === 'Auditoria BBDD'
      && DATABASE_AUDIT_SUBTABS_HIDE_PROFILE_SELECTOR.includes(databaseAuditSubtab)
  );
  const showHeaderProfileSelector = !hideEmbeddedProfileSelector;
  const showGlobalReportControls = !(
    activeTab === 'Auditoria BBDD'
      && DATABASE_AUDIT_SUBTABS_HIDE_GLOBAL_REPORT.includes(databaseAuditSubtab)
  );

  function handleOpenAutomationPostCrqRun({ action, reportData, run }) {
    const nextProfile = run?.profile || reportData?.context?.profile || selectedProfile;
    if (nextProfile) {
      setSelectedProfile(nextProfile);
    }
    setActiveTab('Auditoria BBDD');
    setDatabaseAuditSubtab('Auditoria de canvis');
    const fallback = {
      profile: nextProfile,
      schemas: reportData?.context?.schemas || [],
    };
    if (action === 'live') {
      rerunPostCrqAuditFromSnapshot(reportData, fallback);
      return;
    }
    openPostCrqSnapshot(reportData, fallback);
  }

  return (
    <div className={`app-frame ${isEmbedded ? 'embedded' : ''}`}>
      {!isEmbedded && (
        <AppShellChrome
          showProfileSelector={showHeaderProfileSelector}
          selectedProfile={selectedProfile}
          onProfileChange={setSelectedProfile}
          profiles={profiles}
          activeTab={activeTab}
          onSelectMainTab={setActiveTab}
        />
      )}

      <main id="main-content" tabIndex={-1} className={`main-content ${isEmbedded ? 'embedded-main' : ''}`}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className={`mx-auto w-full ${
              activeTab === 'Auditoria BBDD' && databaseAuditSubtab === 'Automatitzacions'
                ? 'max-w-[1780px]'
                : 'max-w-[1400px]'
            }`}
          >
            <Suspense fallback={<div className="glass-card p-6 text-sm text-muted-foreground">Carregant vista...</div>}>
              <AppPageHeader
                activeTab={activeTab}
                subtabLabel={activeTab === 'Auditoria BBDD' ? databaseAuditSubtab : null}
                helpKey={currentPageHelpKey}
                showGlobalReportControls={showGlobalReportControls}
                loading={loading}
                onRefresh={() => window.location.reload()}
                onGenerateReport={handleGenerateReport}
              />

              {activeTab === 'Auditoria BBDD' && (
                <DatabaseAuditWorkspace
                  databaseAuditSubtab={databaseAuditSubtab}
                  setDatabaseAuditSubtab={setDatabaseAuditSubtab}
                  profiles={profiles}
                  selectedProfile={selectedProfile}
                  setSelectedProfile={setSelectedProfile}
                  postCrqChecksLoading={postCrqChecksLoading}
                  postCrqChecks={postCrqChecks}
                  selectedChecks={selectedChecks}
                  setSelectedChecks={setSelectedChecks}
                  postCrqCriticalityOverrides={postCrqCriticalityOverrides}
                  setPostCrqCriticalityOverrides={setPostCrqCriticalityOverrides}
                  postCrqSchedulerOptions={postCrqSchedulerOptions}
                  setPostCrqSchedulerOptions={setPostCrqSchedulerOptions}
                  postCrqTimeFilter={postCrqTimeFilter}
                  setPostCrqTimeFilter={setPostCrqTimeFilter}
                  postCrqSchemas={postCrqSchemas}
                  setPostCrqSchemas={setPostCrqSchemas}
                  isPostCrqRunning={isPostCrqRunning}
                  postCrqReportData={postCrqReportData}
                  postCrqError={postCrqError}
                  postCrqExecutionOrigin={postCrqExecutionOrigin}
                  fetchPostCrqChecks={fetchPostCrqChecks}
                  handleRunPostCrqAudit={handleRunPostCrqAudit}
                  handleDownloadPostCrqQueries={handleDownloadPostCrqQueries}
                  resetPostCrqCriticalityOverrides={resetPostCrqCriticalityOverrides}
                  handleOpenAutomationPostCrqRun={handleOpenAutomationPostCrqRun}
                  auditData={auditData}
                  selectedAuditIndex={selectedAuditIndex}
                  setSelectedAuditIndex={setSelectedAuditIndex}
                  schemaToAudit={schemaToAudit}
                  setSchemaToAudit={setSchemaToAudit}
                  runDeepAudit={runDeepAudit}
                  isAuditing={isAuditing}
                  handleTestDeepConnection={handleTestDeepConnection}
                  testStatusDeep={testStatusDeep}
                  scoringHelpOpen={scoringHelpOpen}
                  setScoringHelpOpen={setScoringHelpOpen}
                  scoringMenuOpen={scoringMenuOpen}
                  setScoringMenuOpen={setScoringMenuOpen}
                  scoringConfig={scoringConfig}
                  setScoringConfig={setScoringConfig}
                  defaultScoringConfig={DEFAULT_SCORING_CONFIG}
                />
              )}

              {activeTab === 'Arquitectura' && (
                <SystemArchitectureView />
              )}
            </Suspense>

        </motion.div>
      </AnimatePresence>
    </main>
    {!isEmbedded && (
      <footer className="app-footer">
        Entorn intern. Sense dades personals fora del sistema.
      </footer>
    )}
  </div>
  );
}

export default App;







