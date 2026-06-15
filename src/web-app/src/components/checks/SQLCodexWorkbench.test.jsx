import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import SQLCodexWorkbench from './SQLCodexWorkbench.jsx';

vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('SQLCodexWorkbench renders transformation controls and detected variables', async () => {
  axios.post.mockImplementation((url) => {
    if (url === '/api/checks/transform-sql') {
      return Promise.resolve({
        data: {
          transformed_sql: 'SELECT * FROM demo WHERE created_at > TO_DATE(&START_AT, \'YYYY-MM-DD HH24:MI:SS\')',
          logs: [{ step: 'normalize vars', changed: true, details: 'ok' }],
        },
      });
    }
    return Promise.resolve({ data: {} });
  });

  render(<SQLCodexWorkbench originalSql={"DEFINE START_AT = '2026-04-10 08:00:00'\nSELECT * FROM demo WHERE created_at > TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')"} selectedProfile="E13DB" profiles={['E13DB', 'E13QA']} />);

  expect(await screen.findByText(/Codex Transformation Engine/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Entorn d'execució/i)).toBeInTheDocument();
  expect(screen.getByDisplayValue('E13DB')).toBeInTheDocument();
  expect(await screen.findByText(/Paràmetres detectats/i)).toBeInTheDocument();
  expect(screen.getByText('START_AT')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Executar SQL Developer/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Executar Codex Compatible/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Comparar resultats/i })).toBeInTheDocument();
});

test('SQLCodexWorkbench compares results and renders ai analysis', async () => {
  axios.post.mockImplementation((url) => {
    if (url === '/api/checks/transform-sql') {
      return Promise.resolve({
        data: {
          transformed_sql: 'SELECT ID FROM demo',
          logs: [],
        },
      });
    }
    if (url === '/api/checks/codex-engine/compare') {
      return Promise.resolve({
        data: {
          left: { success: true, columns: ['ID'], rows: [{ ID: 1 }], row_count: 1, execution_ms: 10, variables_used: {}, preview_limited: false },
          right: { success: true, columns: ['ID'], rows: [{ ID: 1 }], row_count: 1, execution_ms: 9, variables_used: {}, preview_limited: false },
          comparison: {
            status: 'warning',
            match: false,
            structure_match: true,
            row_count_match: true,
            content_match: true,
            order_match: false,
            only_in_left: [],
            only_in_right: [],
            value_differences: [],
            differences_found: 1,
            summary: 'Los resultados contienen los mismos datos pero en distinto orden.',
          },
        },
      });
    }
    if (url === '/api/checks/codex-engine/analyze') {
      return Promise.resolve({
        data: {
          ai_analysis: {
            status: 'ok',
            summary: 'El orden cambia pero el contenido es equivalente.',
            possible_causes: ['ORDER BY distinto'],
            recommendation: 'Ignora el orden o añade un ORDER BY consistente.',
          },
        },
      });
    }
    return Promise.resolve({ data: {} });
  });

  render(<SQLCodexWorkbench originalSql={'SELECT ID FROM demo'} selectedProfile="E13DB" profiles={['E13DB', 'E13QA']} />);

  expect(await screen.findByText(/Comparar resultats/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Entorn d'execució/i), { target: { value: 'E13QA' } });
  fireEvent.click(screen.getByRole('button', { name: /Comparar resultats/i }));

  expect(await screen.findByText(/Los resultados contienen los mismos datos pero en distinto orden/i)).toBeInTheDocument();
  expect(screen.getAllByText(/Coincideixen amb matisos/i).length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: /Analitzar diferències amb IA/i }));

  await waitFor(() => {
    expect(screen.getByText(/El orden cambia pero el contenido es equivalente/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/ORDER BY distinto/i)).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith('/api/checks/codex-engine/compare', expect.objectContaining({
    profile: 'E13QA',
  }));
});
