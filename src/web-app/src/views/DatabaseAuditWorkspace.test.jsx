import { fireEvent, render, screen } from '@testing-library/react';
import DatabaseAuditWorkspace from './DatabaseAuditWorkspace.jsx';

const postCrqViewMock = vi.fn((props) => (
  <div>
    <div>PostCrq mock</div>
    <div data-testid="postcrq-profile">{props.selectedProfile}</div>
    <div data-testid="postcrq-checks">{props.checks.length}</div>
    <button type="button" onClick={() => props.onProfileChange('P2')}>profile change</button>
    <button type="button" onClick={() => props.onRun()}>run postcrq</button>
    <button type="button" onClick={() => props.onDownloadQueries()}>download queries</button>
  </div>
));

const deepScanViewMock = vi.fn((props) => (
  <div>
    <div>DeepScan mock</div>
    <div data-testid="deep-schema">{props.schemaToAudit}</div>
    <div data-testid="deep-default-score">{props.DEFAULT_SCORING_CONFIG.ownerWeight}</div>
    <button type="button" onClick={() => props.runDeepAudit()}>run deep scan</button>
    <button type="button" onClick={() => props.setSchemaToAudit('NEWSCHEMA')}>schema change</button>
  </div>
));

vi.mock('./PostCrqAuditView.jsx', () => ({ default: (props) => postCrqViewMock(props) }));
vi.mock('./DeepScanView.jsx', () => ({ default: (props) => deepScanViewMock(props) }));
vi.mock('./AutomationView.jsx', () => ({ default: () => <div>Automation view mock</div> }));
vi.mock('./AutomationRulesView.jsx', () => ({ default: () => <div>Automation rules mock</div> }));
vi.mock('./ChecksAdminView.jsx', () => ({ default: () => <div>Checks admin mock</div> }));
vi.mock('./MailConfigView.jsx', () => ({ default: () => <div>Mail config mock</div> }));
vi.mock('./ObsoletsRegistryView.jsx', () => ({ default: () => <div>Obsolets registry mock</div> }));
vi.mock('./TutorialView.jsx', () => ({ default: () => <div>Tutorial view mock</div> }));

function buildProps(overrides = {}) {
  return {
    databaseAuditSubtab: 'Auditoria de canvis',
    setDatabaseAuditSubtab: vi.fn(),
    profiles: [{ name: 'P1' }, { name: 'P2' }],
    selectedProfile: 'P1',
    setSelectedProfile: vi.fn(),
    postCrqChecksLoading: false,
    postCrqChecks: [{ check_id: 'CHK_1' }, { check_id: 'CHK_2' }],
    selectedChecks: ['CHK_1'],
    setSelectedChecks: vi.fn(),
    postCrqCriticalityOverrides: { CHK_1: 'ALT' },
    setPostCrqCriticalityOverrides: vi.fn(),
    postCrqSchedulerOptions: { notify: true },
    setPostCrqSchedulerOptions: vi.fn(),
    postCrqTimeFilter: '7d',
    setPostCrqTimeFilter: vi.fn(),
    postCrqSchemas: 'SCH1,SCH2',
    setPostCrqSchemas: vi.fn(),
    isPostCrqRunning: false,
    postCrqReportData: { run_id: 101 },
    postCrqError: '',
    fetchPostCrqChecks: vi.fn(),
    handleRunPostCrqAudit: vi.fn(),
    handleDownloadPostCrqQueries: vi.fn(),
    auditData: [{ schema_name: 'SCH1' }],
    selectedAuditIndex: 0,
    setSelectedAuditIndex: vi.fn(),
    schemaToAudit: 'SCH1',
    setSchemaToAudit: vi.fn(),
    runDeepAudit: vi.fn(),
    isAuditing: false,
    handleTestDeepConnection: vi.fn(),
    testStatusDeep: 'ok',
    scoringHelpOpen: false,
    setScoringHelpOpen: vi.fn(),
    scoringMenuOpen: false,
    setScoringMenuOpen: vi.fn(),
    scoringConfig: { ownerWeight: 10 },
    setScoringConfig: vi.fn(),
    defaultScoringConfig: { ownerWeight: 25 },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

test('DatabaseAuditWorkspace routes subtabs and wires PostCrq handlers', async () => {
  const props = buildProps();
  render(<DatabaseAuditWorkspace {...props} />);

  expect(await screen.findByText('PostCrq mock')).toBeInTheDocument();
  expect(screen.getByTestId('postcrq-profile')).toHaveTextContent('P1');
  expect(screen.getByTestId('postcrq-checks')).toHaveTextContent('2');

  fireEvent.click(screen.getByText('profile change'));
  fireEvent.click(screen.getByText('run postcrq'));
  fireEvent.click(screen.getByText('download queries'));

  expect(props.setSelectedProfile).toHaveBeenCalledWith('P2');
  expect(props.handleRunPostCrqAudit).toHaveBeenCalled();
  expect(props.handleDownloadPostCrqQueries).toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: /Automatitzacions/i }));
  fireEvent.click(screen.getByRole('button', { name: /Tasques i regles/i }));
  fireEvent.click(screen.getByRole('button', { name: /Guia i Ajuda/i }));

  expect(props.setDatabaseAuditSubtab).toHaveBeenCalledWith('Automatitzacions');
  expect(props.setDatabaseAuditSubtab).toHaveBeenCalledWith('Tasques i regles');
  expect(props.setDatabaseAuditSubtab).toHaveBeenCalledWith('Guia i Ajuda');
});

test('DatabaseAuditWorkspace renders DeepScan and passes deep-audit props', async () => {
  const props = buildProps({ databaseAuditSubtab: 'Anàlisi obsolets' });
  render(<DatabaseAuditWorkspace {...props} />);

  expect(await screen.findByText('DeepScan mock')).toBeInTheDocument();
  expect(screen.getByTestId('deep-schema')).toHaveTextContent('SCH1');
  expect(screen.getByTestId('deep-default-score')).toHaveTextContent('25');

  fireEvent.click(screen.getByText('run deep scan'));
  fireEvent.click(screen.getByText('schema change'));

  expect(props.runDeepAudit).toHaveBeenCalled();
  expect(props.setSchemaToAudit).toHaveBeenCalledWith('NEWSCHEMA');

  const deepScanProps = deepScanViewMock.mock.calls[0][0];
  expect(deepScanProps).toEqual(expect.objectContaining({
    auditData: [{ schema_name: 'SCH1' }],
    selectedAuditIndex: 0,
    testStatusDeep: 'ok',
    schemaToAudit: 'SCH1',
    DEFAULT_SCORING_CONFIG: { ownerWeight: 25 },
  }));
});
