import { fireEvent, render, screen } from '@testing-library/react';
import DeepScanView from './DeepScanView.jsx';

vi.mock('../components/ScoringGuide.jsx', () => ({
  default: () => <div>Guia scoring mock</div>,
}));

function buildAuditData() {
  return [
    {
      username: 'APP_USER',
      summary: {
        SIZE_GB: 0.2,
        OBJECT_COUNT: 5,
        LAST_LOGIN_DAYS: 365,
        DAYS_OLD: 800,
        ACTIVE_JOBS: 0,
        APEX_APPLICATIONS: 0,
        ENABLED_TRIGGERS: 0,
        DAYS_SINCE_NEWEST_DDL: 120,
        TABLES_STATS_RECENT_30D: 0,
        TABLES_WITH_MODS_30D: 0,
        INBOUND_REFERENCES: 0,
        EXTERNAL_DEPENDENCIES_OUT: 0,
      },
      score_meta: { total: 82 },
      code_refs: [],
      activity: { dml: [] },
      table_stats: [],
      executed_queries: [],
    },
    {
      username: 'APP_AUX',
      summary: {
        SIZE_GB: 1.5,
        OBJECT_COUNT: 12,
        LAST_LOGIN_DAYS: 40,
        DAYS_OLD: 300,
        ACTIVE_JOBS: 2,
        APEX_APPLICATIONS: 1,
        ENABLED_TRIGGERS: 1,
        DAYS_SINCE_NEWEST_DDL: 3,
        TABLES_STATS_RECENT_30D: 5,
        TABLES_WITH_MODS_30D: 4,
        INBOUND_REFERENCES: 3,
        EXTERNAL_DEPENDENCIES_OUT: 2,
      },
      score_meta: { total: 25 },
      code_refs: [],
      activity: { dml: [] },
      table_stats: [],
      executed_queries: [],
    },
  ];
}

test('DeepScanView allows switching schema cards and restoring scoring defaults', async () => {
  const setSelectedAuditIndex = vi.fn();
  const setSchemaToAudit = vi.fn();
  const runDeepAudit = vi.fn();
  const handleTestDeepConnection = vi.fn();
  const setScoringHelpOpen = vi.fn();
  const setScoringMenuOpen = vi.fn();
  const setScoringConfig = vi.fn();

  const defaultScoringConfig = {
    dmlNoActivityPts: 25,
    dependenciesMaxPts: 20,
    inboundPenaltyPerDep: 5,
    outboundPenaltyPerDep: 3,
    loginInactivePts: 8,
    loginInactiveDays: 90,
    sizeTinyThresholdGb: 0.1,
    sizeTinyPts: 10,
    sizeSmallThresholdGb: 1,
    sizeSmallPts: 5,
    automationBonusPts: 10,
    automationPenaltyPerBlocker: 8,
    automationPenaltyCap: 40,
  };

  render(
    <DeepScanView
      auditData={buildAuditData()}
      selectedAuditIndex={0}
      setSelectedAuditIndex={setSelectedAuditIndex}
      schemaToAudit="APP_USER"
      setSchemaToAudit={setSchemaToAudit}
      runDeepAudit={runDeepAudit}
      isAuditing={false}
      handleTestDeepConnection={handleTestDeepConnection}
      testStatusDeep={{ status: 'success', msg: 'Connexió OK' }}
      scoringHelpOpen={true}
      setScoringHelpOpen={setScoringHelpOpen}
      scoringMenuOpen={true}
      setScoringMenuOpen={setScoringMenuOpen}
      scoringConfig={defaultScoringConfig}
      setScoringConfig={setScoringConfig}
      DEFAULT_SCORING_CONFIG={defaultScoringConfig}
    />,
  );

  expect(screen.getByDisplayValue('APP_USER')).toBeInTheDocument();
  expect(await screen.findByText('Guia scoring mock')).toBeInTheDocument();
  expect(screen.getByText(/Restaurar valors v4/i)).toBeInTheDocument();

  fireEvent.change(screen.getByDisplayValue('APP_USER'), { target: { value: 'app_stage' } });
  expect(setSchemaToAudit).toHaveBeenCalledWith('APP_STAGE');

  fireEvent.click(screen.getByRole('button', { name: /Auditar/i }));
  expect(runDeepAudit).toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: /APP_AUX/i }));
  expect(setSelectedAuditIndex).toHaveBeenCalledWith(1);

  fireEvent.click(screen.getByRole('button', { name: /Restaurar valors v4/i }));
  expect(setScoringConfig).toHaveBeenCalledWith(defaultScoringConfig);
});
