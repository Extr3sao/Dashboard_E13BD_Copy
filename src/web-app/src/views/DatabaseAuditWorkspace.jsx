import React, { Suspense, lazy } from 'react';

import { DATABASE_AUDIT_SUBTABS } from '../config/databaseAuditTabs.js';

const ObsoletsRegistryView = lazy(() => import('./ObsoletsRegistryView.jsx'));
const PostCrqAuditView = lazy(() => import('./PostCrqAuditView.jsx'));
const AutomationView = lazy(() => import('./AutomationView.jsx'));
const AutomationRulesView = lazy(() => import('./AutomationRulesView.jsx'));
const TutorialView = lazy(() => import('./TutorialView.jsx'));
const ChecksAdminView = lazy(() => import('./ChecksAdminView.jsx'));
const MailConfigView = lazy(() => import('./MailConfigView.jsx'));
const DeepScanView = lazy(() => import('./DeepScanView.jsx'));
const SUBTAB_IDS = Object.fromEntries(
  DATABASE_AUDIT_SUBTABS.map((tab) => [tab.helpKey, tab.id])
);

export default function DatabaseAuditWorkspace({
  databaseAuditSubtab,
  setDatabaseAuditSubtab,
  profiles,
  selectedProfile,
  setSelectedProfile,
  postCrqChecksLoading,
  postCrqChecks,
  selectedChecks,
  setSelectedChecks,
  postCrqCriticalityOverrides,
  setPostCrqCriticalityOverrides,
  postCrqSchedulerOptions,
  setPostCrqSchedulerOptions,
  postCrqTimeFilter,
  setPostCrqTimeFilter,
  postCrqSchemas,
  setPostCrqSchemas,
  isPostCrqRunning,
  postCrqReportData,
  postCrqError,
  postCrqExecutionOrigin,
  fetchPostCrqChecks,
  handleRunPostCrqAudit,
  handleDownloadPostCrqQueries,
  resetPostCrqCriticalityOverrides,
  handleOpenAutomationPostCrqRun,
  auditData,
  selectedAuditIndex,
  setSelectedAuditIndex,
  schemaToAudit,
  setSchemaToAudit,
  runDeepAudit,
  isAuditing,
  handleTestDeepConnection,
  testStatusDeep,
  scoringHelpOpen,
  setScoringHelpOpen,
  scoringMenuOpen,
  setScoringMenuOpen,
  scoringConfig,
  setScoringConfig,
  defaultScoringConfig,
}) {
  return (
    <>
      <div className="flex flex-col gap-8">
        <div className="flex flex-wrap gap-3">
          {DATABASE_AUDIT_SUBTABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setDatabaseAuditSubtab(tab.id)}
              className={`rounded-xl border px-4 py-2 text-sm font-bold transition-all ${
                databaseAuditSubtab === tab.id
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-white/5 hover:bg-white/10'
              }`}
            >
              {tab.id}
            </button>
          ))}
        </div>

        <Suspense fallback={<div className="glass-card p-6 text-sm text-muted-foreground">Carregant subvista...</div>}>
          {databaseAuditSubtab === SUBTAB_IDS.postCrqAudit && (
            <PostCrqAuditView
              profiles={profiles}
              selectedProfile={selectedProfile}
              checksLoading={postCrqChecksLoading}
              checks={postCrqChecks}
              selectedChecks={selectedChecks}
              criticalityOverrides={postCrqCriticalityOverrides}
              schedulerOptions={postCrqSchedulerOptions}
              timeFilter={postCrqTimeFilter}
              schemasValue={postCrqSchemas}
              isRunning={isPostCrqRunning}
              result={postCrqReportData}
              error={postCrqError}
              executionOrigin={postCrqExecutionOrigin}
              onRefreshChecks={fetchPostCrqChecks}
              onProfileChange={setSelectedProfile}
              onToggleCheck={(checkId) => {
                setSelectedChecks((current) => (
                  current.includes(checkId)
                    ? current.filter((item) => item !== checkId)
                    : [...current, checkId]
                ));
              }}
              onSelectAll={() => setSelectedChecks(postCrqChecks.map((check) => check.check_id))}
              onClearAll={() => setSelectedChecks([])}
              onSchemasChange={setPostCrqSchemas}
              onTimeFilterChange={setPostCrqTimeFilter}
              onCriticalityOverrideChange={(checkId, value) => {
                setPostCrqCriticalityOverrides((current) => {
                  const next = { ...current };
                  if (!value) {
                    delete next[checkId];
                    return next;
                  }
                  next[checkId] = value;
                  return next;
                });
              }}
              onSchedulerOptionsChange={setPostCrqSchedulerOptions}
              onResetCriticalityOverrides={resetPostCrqCriticalityOverrides}
              onRun={handleRunPostCrqAudit}
              onDownloadQueries={handleDownloadPostCrqQueries}
            />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.automationOverview && (
            <AutomationView profiles={profiles} onOpenPostCrqRun={handleOpenAutomationPostCrqRun} />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.automationRules && (
            <AutomationRulesView />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.checksAdmin && (
            <ChecksAdminView profiles={profiles} selectedProfile={selectedProfile} />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.mailConfig && (
            <MailConfigView />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.obsoletsRepository && (
            <ObsoletsRegistryView />
          )}
          {databaseAuditSubtab === SUBTAB_IDS.tutorial && (
            <TutorialView />
          )}
        </Suspense>
      </div>

      <Suspense fallback={<div className="glass-card p-6 text-sm text-muted-foreground">Carregant anàlisi...</div>}>
        {databaseAuditSubtab === SUBTAB_IDS.deepScan && (
          <DeepScanView
            profiles={profiles}
            selectedProfile={selectedProfile}
            onProfileChange={setSelectedProfile}
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
            DEFAULT_SCORING_CONFIG={defaultScoringConfig}
          />
        )}
      </Suspense>
    </>
  );
}
