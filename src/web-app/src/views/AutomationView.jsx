import React from 'react';
import { RefreshCcw } from 'lucide-react';
import AutomationDashboardPanel from '../components/automation/AutomationDashboardPanel.jsx';
import AutomationHelpModal from '../components/automation/AutomationHelpModal.jsx';
import AutomationHelpPanel from '../components/automation/AutomationHelpPanel.jsx';
import AutomationHistoryPanel from '../components/automation/AutomationHistoryPanel.jsx';
import AutomationJobsPanel from '../components/automation/AutomationJobsPanel.jsx';
import AutomationLotsPanel from '../components/automation/AutomationLotsPanel.jsx';
import AutomationRecipientsPanel from '../components/automation/AutomationRecipientsPanel.jsx';
import AutomationRetryPanel from '../components/automation/AutomationRetryPanel.jsx';
import AutomationScreenHeader from '../components/automation/AutomationScreenHeader.jsx';
import AutomationSidebar from '../components/automation/AutomationSidebar.jsx';
import AutomationTemplatesPanel from '../components/automation/AutomationTemplatesPanel.jsx';
import { AUTOMATION_SCREENS } from '../config/automationViewConfig.js';
import { useAutomationViewModel } from '../hooks/useAutomationViewModel.js';

export default function AutomationView({ profiles, onOpenPostCrqRun }) {
  const {
    analyticsChecks,
    analyticsLoading,
    analyticsLots,
    analyticsMonth,
    analyticsOverview,
    analyticsSchemas,
    applyingBackfill,
    auditOpen,
    automationSection,
    backfillPreview,
    backfillSelection,
    changeEvents,
    checks,
    currentScreen,
    deliveryAudienceLabel,
    deliveryResultLabel,
    deliveryRoutes,
    editingJobId,
    emptyMasterLot,
    emptyRoute,
    emptySchemaLot,
    emptyTemplate,
    error,
    expandedRunId,
    exportSchemaLotsCsv,
    filteredSchemaLots,
    form,
    formFromJob,
    getAutomationRunReportUrl,
    handleOpenRunSnapshot,
    handleRerunLiveFromHistory,
    handleApplyBackfill,
    handleDeleteJob,
    handleEnqueueRetry,
    handleExportAnalyticsPdf,
    handleExportRunCsv,
    handlePreviewBackfill,
    handlePurgeHistory,
    handlePurgeRetryQueue,
    handleRunNow,
    handleRunRetryNow,
    handleSaveJob,
    handleToggleJob,
    helpOpen,
    historyOpen,
    isDashboardScreen,
    isHistoryScreen,
    isJobsScreen,
    isLotsScreen,
    isRecipientsScreen,
    isRetriesScreen,
    isTemplatesScreen,
    jobs,
    loading,
    loadingRunLotsId,
    lotRoutes,
    lotStatusClass,
    lotStatusLabel,
    masterLotCodes,
    masterLots,
    maintenanceSummary,
    message,
    openHelpInNewWindow,
    openSections,
    previewingBackfill,
    recipientsOpen,
    refreshAll,
    refreshAnalytics,
    refreshRunLots,
    registerSection,
    resetForm,
    retentionDays,
    retryOpen,
    retryQueue,
    runLotFilter,
    runLotSummary,
    runLotsById,
    runStatusClass,
    runStatusLabel,
    runs,
    saveLotRoutes,
    saveMasterLots,
    saveSchemaLots,
    saveTemplates,
    saving,
    schemaLotFilter,
    schemaLotOptions,
    schemaLotValidation,
    schemaLots,
    setAllSectionsOpen,
    setAnalyticsMonth,
    setAutomationSection,
    setBackfillSelection,
    setEditingJobId,
    setForm,
    setHelpOpen,
    setLotRoutes,
    setMasterLots,
    setRetentionDays,
    setRunLotFilter,
    setSchemaLotFilter,
    setSchemaLots,
    setTemplates,
    templateKeyDescription,
    templateKeyLabel,
    templates,
    templatesOpen,
    toggleRunLots,
    toggleSection,
    yesNo,
  } = useAutomationViewModel(profiles, { onOpenPostCrqRun });

  return (
    <div className="flex flex-col gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <AutomationHelpModal
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        onOpenInlineHelp={() => {
          setAutomationSection('help');
          setHelpOpen(false);
        }}
        onOpenNewWindow={openHelpInNewWindow}
      />

      {loading ? (
        <div className="glass-card flex items-center justify-center p-12 text-sm text-muted-foreground">
          <RefreshCcw className="mr-3 animate-spin" size={18} />
          Carregant automatitzacions...
        </div>
      ) : (
        <div className="grid gap-8 xl:grid-cols-[260px_minmax(0,1fr)]">
                    <AutomationSidebar
            screens={AUTOMATION_SCREENS}
            activeScreen={automationSection}
            onSelectScreen={setAutomationSection}
            onExpandAll={() => setAllSectionsOpen(true)}
            onCollapseAll={() => setAllSectionsOpen(false)}
            onRefresh={refreshAll}
          />

          <div className="flex min-w-0 flex-col gap-8">
            {(error || message) && (
              <div className={`rounded-2xl border p-4 text-sm ${error ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-emerald-300/70 bg-emerald-50 text-emerald-950'}`}>
                {error || message}
              </div>
            )}

                        <AutomationScreenHeader
              screen={currentScreen}
              jobsCount={jobs.length}
              routesCount={(deliveryRoutes.providers || []).length}
              retryCount={retryQueue.length}
            />

            
            {isDashboardScreen ? (
              <AutomationDashboardPanel
                analyticsMonth={analyticsMonth}
                onChangeMonth={setAnalyticsMonth}
                onRefresh={() => refreshAnalytics(analyticsMonth)}
                onExportPdf={handleExportAnalyticsPdf}
                analyticsLoading={analyticsLoading}
                analyticsOverview={analyticsOverview}
                analyticsLots={analyticsLots}
                analyticsSchemas={analyticsSchemas}
                analyticsChecks={analyticsChecks}
              />
            ) : null}

            {automationSection === 'help' ? <AutomationHelpPanel /> : null}


            <AutomationJobsPanel
              isVisible={isJobsScreen}
              registerSection={registerSection}
              openSections={openSections}
              toggleSection={toggleSection}
              editingJobId={editingJobId}
              resetForm={resetForm}
              form={form}
              setForm={setForm}
              profiles={profiles}
              checks={checks}
              saving={saving}
              handleSaveJob={handleSaveJob}
              deliveryRoutes={deliveryRoutes}
              masterLots={masterLots}
              jobs={jobs}
              setEditingJobId={setEditingJobId}
              formFromJob={formFromJob}
              handleRunNow={handleRunNow}
              handleToggleJob={handleToggleJob}
              handleDeleteJob={handleDeleteJob}
            />

          <AutomationLotsPanel
            isVisible={isLotsScreen}
            registerSection={registerSection}
            openSections={openSections}
            toggleSection={toggleSection}
            filteredSchemaLots={filteredSchemaLots}
            exportSchemaLotsCsv={exportSchemaLotsCsv}
            setSchemaLots={setSchemaLots}
            emptySchemaLot={emptySchemaLot}
            schemaLotFilter={schemaLotFilter}
            setSchemaLotFilter={setSchemaLotFilter}
            schemaLotOptions={schemaLotOptions}
            schemaLotValidation={schemaLotValidation}
            schemaLots={schemaLots}
            masterLotCodes={masterLotCodes}
            saveSchemaLots={saveSchemaLots}
            handlePreviewBackfill={handlePreviewBackfill}
            previewingBackfill={previewingBackfill}
            handleApplyBackfill={handleApplyBackfill}
            applyingBackfill={applyingBackfill}
            backfillPreview={backfillPreview}
            backfillSelection={backfillSelection}
            setBackfillSelection={setBackfillSelection}
            masterLots={masterLots}
            setMasterLots={setMasterLots}
            emptyMasterLot={emptyMasterLot}
            saveMasterLots={saveMasterLots}
          />

            <AutomationRecipientsPanel
              isVisible={isRecipientsScreen}
              registerSection={registerSection}
              open={recipientsOpen}
              onToggle={() => toggleSection('lot_routes')}
              lotRoutes={lotRoutes}
              setLotRoutes={setLotRoutes}
              emptyRoute={emptyRoute}
              saveLotRoutes={saveLotRoutes}
            />

            <AutomationTemplatesPanel
              isVisible={isTemplatesScreen}
              registerSection={registerSection}
              open={templatesOpen}
              onToggle={() => toggleSection('templates')}
              templates={templates}
              setTemplates={setTemplates}
              emptyTemplate={emptyTemplate}
              saveTemplates={saveTemplates}
              templateKeyLabel={templateKeyLabel}
              templateKeyDescription={templateKeyDescription}
            />

          <AutomationHistoryPanel
            isVisible={isHistoryScreen}
            registerSection={registerSection}
            auditOpen={auditOpen}
            historyOpen={historyOpen}
            toggleSection={toggleSection}
            changeEvents={changeEvents}
            retentionDays={retentionDays}
            setRetentionDays={setRetentionDays}
            handlePurgeHistory={handlePurgeHistory}
            maintenanceSummary={maintenanceSummary}
            runLotFilter={runLotFilter}
            setRunLotFilter={setRunLotFilter}
            expandedRunId={expandedRunId}
            refreshRunLots={refreshRunLots}
            runs={runs}
            toggleRunLots={toggleRunLots}
            getAutomationRunReportUrl={getAutomationRunReportUrl}
            handleOpenRunSnapshot={handleOpenRunSnapshot}
            handleRerunLiveFromHistory={handleRerunLiveFromHistory}
            handleExportRunCsv={handleExportRunCsv}
            loadingRunLotsId={loadingRunLotsId}
            runLotsById={runLotsById}
            lotStatusLabel={lotStatusLabel}
            lotStatusClass={lotStatusClass}
            runStatusLabel={runStatusLabel}
            runStatusClass={runStatusClass}
            runLotSummary={runLotSummary}
            deliveryAudienceLabel={deliveryAudienceLabel}
            deliveryResultLabel={deliveryResultLabel}
            yesNo={yesNo}
            handleEnqueueRetry={handleEnqueueRetry}
          />

          <AutomationRetryPanel
            isVisible={isRetriesScreen}
            registerSection={registerSection}
            retryOpen={retryOpen}
            toggleSection={toggleSection}
            retryQueue={retryQueue}
            handlePurgeRetryQueue={handlePurgeRetryQueue}
            maintenanceSummary={maintenanceSummary}
            handleRunRetryNow={handleRunRetryNow}
          />
          </div>
        </div>
      )}
    </div>
  );
}
