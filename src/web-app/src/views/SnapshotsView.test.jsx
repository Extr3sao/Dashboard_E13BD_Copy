import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SnapshotsView from './SnapshotsView.jsx';

vi.mock('recharts', () => {
  const Mock = ({ children }) => children ?? null;
  return {
    ResponsiveContainer: Mock,
    PieChart: Mock,
    Pie: Mock,
    Cell: Mock,
    BarChart: Mock,
    Bar: Mock,
    XAxis: Mock,
    YAxis: Mock,
    CartesianGrid: Mock,
    Tooltip: Mock,
    ScatterChart: Mock,
    Scatter: Mock,
    ZAxis: Mock,
  };
});

const latestSnapshot = vi.fn();
const querySnapshot = vi.fn();
const exportSnapshotCsv = vi.fn();

vi.mock('../api/snapshots.js', () => ({
  latestSnapshot: (...args) => latestSnapshot(...args),
  querySnapshot: (...args) => querySnapshot(...args),
  exportSnapshotCsv: (...args) => exportSnapshotCsv(...args),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('SnapshotsView exports CSV for the active snapshot and reuses the cached blob on repeated export', async () => {
  latestSnapshot.mockResolvedValue({
    snapshot: { snapshot_id: 'snap-001' },
  });
  querySnapshot.mockResolvedValue({
    snapshot_id: 'snap-001',
    rows: [
      {
        schema: 'APP_USER',
        table_name: 'TMP_EXAMPLE',
        size_gb: 1.25,
        score: 80,
        recommendation: 'DROP',
      },
    ],
    summary: { total_objects: 1, total_gb: 1.25, avg_score: 80, drop_count: 1 },
    facets: { schemas: ['APP_USER'], recommendations: ['DROP'] },
  });
  exportSnapshotCsv.mockResolvedValue({
    data: new Blob(['schema,table\nAPP_USER,TMP_EXAMPLE\n'], { type: 'text/csv;charset=utf-8' }),
  });

  const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-snapshot');
  const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

  render(<SnapshotsView />);

  expect(await screen.findByText('snap-001')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/i }));

  await waitFor(() => {
    expect(exportSnapshotCsv).toHaveBeenCalledWith(expect.objectContaining({
      snapshot_id: 'snap-001',
      min_score: 0,
      limit: 1000,
      offset: 0,
      sort_by: 'score',
      sort_dir: 'desc',
    }));
  });

  await waitFor(() => {
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1);
    expect(anchorClickSpy).toHaveBeenCalledTimes(1);
  });

  fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/i }));

  await waitFor(() => {
    expect(anchorClickSpy).toHaveBeenCalledTimes(2);
  });
  expect(exportSnapshotCsv).toHaveBeenCalledWith(expect.objectContaining({
    snapshot_id: 'snap-001',
    min_score: 0,
    limit: 1000,
    offset: 0,
    sort_by: 'score',
    sort_dir: 'desc',
  }));

  createObjectUrlSpy.mockRestore();
  anchorClickSpy.mockRestore();
});
