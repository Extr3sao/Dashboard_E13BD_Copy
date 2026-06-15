import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChecksAdminView from './ChecksAdminView.jsx';
import axios from 'axios';


vi.mock('axios', () => ({

  default: {

    get: vi.fn(),

    post: vi.fn(),

    put: vi.fn(),

    delete: vi.fn(),

  },

}));



vi.mock('framer-motion', async () => {
  const React = await import('react');
  return {
    AnimatePresence: ({ children }) => <>{children}</>,

    motion: new Proxy({}, {

      get: (_target, key) => React.forwardRef(({ children, layout, ...props }, ref) => React.createElement(key, { ref, ...props }, children)),

    }),

  };
});

vi.mock('../components/post-crq/PostCrqOperationalDocsPanel.jsx', () => ({
  default: ({ refreshNonce }) => (
    <div data-testid="post-crq-operational-docs-panel">
      Panel docs nonce:{refreshNonce}
    </div>
  ),
}));


const checksList = [
  {

    check_id: 'CHECK_ALPHA',

    titol: 'Alpha check',

    severitat_base: 'CrÃ­tic',

    versio_vigent: 3,

    estat_explicacio: 'PENDENT',

    estat_sync_md: 'OK',

    estat_sync_txt: 'PENDENT',

    ai_enabled: 1,

    sql_vigent: 'select * from dual',

    context_check: 'Context alpha',

  },

  {

    check_id: 'CHECK_BETA',

    titol: 'Beta check',

    severitat_base: 'Baix',

    versio_vigent: 1,

    estat_explicacio: 'VIGENT',

    estat_sync_md: 'OK',

    estat_sync_txt: 'OK',

    ai_enabled: 0,

    sql_vigent: 'select 2 from dual',

    context_check: '',

  },
];

const markdownChecks = [
  {
    check_id: 'CHECK_ALPHA',
    title: 'Alpha check from markdown',
    criteri: 'Criteri alpha des del markdown',
    sql: '-- markdown alpha\nselect * from markdown_alpha',
  },
  {
    check_id: 'CHECK_BETA',
    title: 'Beta check from markdown',
    criteri: 'Criteri beta des del markdown',
    sql: '-- markdown beta\nselect 2 from markdown_beta',
  },
];

function mockAxiosForChecksView() {
  axios.get.mockImplementation((url) => {
    if (url === '/api/checks') {
      return Promise.resolve({ data: checksList });
    }
    if (url === '/api/audit/post-crq/checks') {
      return Promise.resolve({ data: { checks: markdownChecks } });
    }
    if (url === '/api/checks/CHECK_ALPHA/history') {
      return Promise.resolve({
        data: [{
          id: 1,

          versio: 3,

          es_vigent: true,

          creat_per: 'tester',

          creat_en: '2026-03-25T08:00:00Z',

          estat_explicacio: 'VIGENT',

          model_utilitzat: 'gpt-4o-mini',

          nivell_confianca: 0.82,

        }],

      });

    }

    if (url === '/api/checks/CHECK_ALPHA/sync-status') {

      return Promise.resolve({

        data: [

          { fitxer: 'auditoria_post_crq.md', estat: 'OK', darrera_sync: '2026-03-25T08:05:00Z' },

          { fitxer: 'consultes_post_crq.txt', estat: 'PENDENT', darrera_sync: null },

        ],

      });

    }

    return Promise.resolve({ data: [] });

  });

}



beforeEach(() => {

  vi.clearAllMocks();

  mockAxiosForChecksView();

});



test('ChecksAdminView filters checks and shows detail tabs with regenerate action', async () => {

  axios.post.mockResolvedValue({ data: { status: 'ok' } });



  render(<ChecksAdminView selectedProfile="E13DB" />);


  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();

  expect(screen.getByText('CHECK_BETA')).toBeInTheDocument();



  fireEvent.change(screen.getByPlaceholderText(/Cercar check/i), { target: { value: 'beta' } });

  expect(screen.queryByText('CHECK_ALPHA')).not.toBeInTheDocument();

  expect(screen.getByText('CHECK_BETA')).toBeInTheDocument();



  fireEvent.change(screen.getByPlaceholderText(/Cercar check/i), { target: { value: '' } });

  fireEvent.change(screen.getByDisplayValue('Tots els estats'), { target: { value: 'PENDENT' } });

  expect(screen.getByText('CHECK_ALPHA')).toBeInTheDocument();

  expect(screen.queryByText('CHECK_BETA')).not.toBeInTheDocument();



  fireEvent.change(screen.getByDisplayValue('Pendent IA'), { target: { value: '' } });
  fireEvent.click(screen.getByText('CHECK_ALPHA'));

  await waitFor(() => {
    expect(document.querySelector('textarea[spellcheck="false"]')?.value).toContain('markdown_alpha');
  });
  expect(await screen.findByText(/Criteri alpha des del markdown/i)).toBeInTheDocument();


  fireEvent.click(screen.getByRole('button', { name: 'Historial' }));

  expect((await screen.findAllByText('v3')).length).toBeGreaterThan(0);
  expect(screen.getByText(/gpt-4o-mini/i)).toBeInTheDocument();

  expect(screen.getByText(/conf: 82%/i)).toBeInTheDocument();



  fireEvent.click(screen.getByRole('button', { name: 'Sync' }));

  await waitFor(() => { expect(screen.getAllByText('auditoria_post_crq.md').length).toBeGreaterThan(1); });

  expect(screen.getAllByText('consultes_post_crq.txt').length).toBeGreaterThan(1);



  fireEvent.click(screen.getByRole('button', { name: /Generar Explicaci|Regenerar explicaci/i }));



  await waitFor(() => {
    expect(axios.post).toHaveBeenCalledWith('/api/checks/CHECK_ALPHA/regenerate');
  });
});

test('ChecksAdminView edits existing checks using the SQL currently parsed from markdown', async () => {
  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  fireEvent.click(screen.getAllByTitle('Editar')[0]);

  expect(await screen.findByText(/Mostrant la consulta activa de/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(document.querySelector('textarea[spellcheck="false"]')?.value).toContain('markdown_alpha');
  });
  expect(screen.getByDisplayValue('Alpha check from markdown')).toBeInTheDocument();
});


test('ChecksAdminView creates a new check with normalized payload', async () => {
  axios.post.mockImplementation((url) => {
    if (url === '/api/checks/validate-preview') {
      return Promise.resolve({
        data: {
          status: 'ok',
          profile: 'E13DB',
          time_filter: {
            mode: 'range',
            start_date: '2026-04-03',
            end_date: '2026-04-10',
            range_start_at: '2026-04-03T08:15',
            range_end_at: '2026-04-10T09:45',
          },
          validation: {
            status: 'ok',
            row_count: 1,
            preview_row_count: 1,
            rows: [{ ESQUEMA: 'APP' }],
            columns: ['ESQUEMA'],
            rendered_sql: 'select * from gamma_table',
            duration_ms: 12,
            time_filter_pushed: true,
          },
          ai_preview: {
            status: 'ok',
            model_utilitzat: 'fake-model',
            resum_executiu: 'Resum executiu de prova amb prou longitud.',
            explicacio_funcional: 'Explicació funcional de prova.',
            explicacio_tecnica: 'Explicació tècnica de prova prou llarga per validar la UI.',
            explicacio_preview_text: 'CHECK_GAMMA ? Gamma check\n\nQu? detecta: Detecta un patr? de prova.\n\nPer qu? ?s important: Aporta context suficient per decidir si cal intervenir.\n\nImpacte sobre el lot: Pot afectar la validaci? del lliurament.\n\nCom revisar:\nPrioritzar la l?gica principal.\n\nCom corregir:\nAplicar una correcci? prudent.\n\nValidaci? posterior: Reexecutar el check i comprovar el comportament funcional.',
            nivell_confianca: 0.8,
          },
        },
      });
    }
    if (url === '/api/checks') {
      return Promise.resolve({ data: { status: 'created' } });
    }
    return Promise.resolve({ data: { status: 'ok' } });
  });


  render(<ChecksAdminView selectedProfile="E13DB" />);


  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Nou check/i }));



  fireEvent.change(screen.getByPlaceholderText('CHECK_14'), { target: { value: 'check_gamma' } });

  fireEvent.change(screen.getByPlaceholderText(/WHEN OTHERS/i), { target: { value: 'Gamma check' } });

  fireEvent.change(screen.getByDisplayValue('0'), { target: { value: '5' } });

  fireEvent.change(screen.getByPlaceholderText(/Descripci/i), { target: { value: 'Context gamma' } });
  fireEvent.change(screen.getByLabelText(/Inici prevalidació/i), { target: { value: '2026-04-03T08:15' } });
  fireEvent.change(screen.getByLabelText(/Final prevalidació/i), { target: { value: '2026-04-10T09:45' } });
  fireEvent.change(document.querySelector('textarea[spellcheck="false"]'), {

    target: { value: 'select * from gamma_table' },

  });



  expect(screen.getByRole('button', { name: /Crear i Regenerar IA/i })).toBeDisabled();

  fireEvent.click(screen.getByRole('button', { name: /Validar consulta i previsualitzar IA/i }));

  await waitFor(() => {
    expect(axios.post).toHaveBeenCalledWith('/api/checks/validate-preview', expect.objectContaining({
      check_id: 'CHECK_GAMMA',
      profile: 'E13DB',
      sql_text: 'select * from gamma_table',
      validation_start_at: '2026-04-03T08:15',
      validation_end_at: '2026-04-10T09:45',
    }));
  });

  await waitFor(() => {
    expect(screen.getByText(/Validació correcta sobre E13DB/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/Finestra temporal utilitzada/i)).toBeInTheDocument();
  expect(screen.getByText(/2026-04-03T08:15 -> 2026-04-10T09:45/i)).toBeInTheDocument();
  expect(screen.getByText(/Informe ampliat del check/i)).toBeInTheDocument();
  expect(screen.getByText(/CHECK_GAMMA/i)).toBeInTheDocument();
  expect(screen.getByText(/Reexecutar el check/i)).toBeInTheDocument();

  expect(screen.getByRole('button', { name: /Crear i Regenerar IA/i })).not.toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: /Crear i Regenerar IA/i }));


  await waitFor(() => {

    expect(axios.post).toHaveBeenCalledWith('/api/checks', expect.objectContaining({

      check_id: 'CHECK_GAMMA',

      titol: 'Gamma check',

      ordre: 5,

      parametres: 'days_back',
      context_check: 'Context gamma',

      sql_text: 'select * from gamma_table',

    }));

  });



  await waitFor(() => {
    expect(screen.queryByRole('button', { name: /Crear i Regenerar IA/i })).not.toBeInTheDocument();
  });
});

test('ChecksAdminView keeps save disabled for changed SQL until validation succeeds', async () => {
  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  fireEvent.click(screen.getAllByTitle('Editar')[0]);

  await waitFor(() => {
    expect(document.querySelector('textarea[spellcheck="false"]')?.value).toContain('markdown_alpha');
  });

  fireEvent.change(document.querySelector('textarea[spellcheck="false"]'), {
    target: { value: 'select * from changed_alpha' },
  });

  expect(screen.getByRole('button', { name: /Desar i Regenerar IA/i })).toBeDisabled();
});

test('ChecksAdminView renders the operational document panel inside gestio de controls', async () => {
  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  expect(screen.getByTestId('post-crq-operational-docs-panel')).toBeInTheDocument();
});

test('ChecksAdminView shows a visible prevalidation reminder on the main screen', async () => {
  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  expect(screen.getByText(/Desar requereix prevalidació/i)).toBeInTheDocument();
  expect(screen.getByText(/s'ha de validar amb Oracle i la previsualització IA abans de poder desar/i)).toBeInTheDocument();
});

test('ChecksAdminView shows editable validation window fields and helper text', async () => {
  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Nou check/i }));

  expect(screen.getByText(/pots fer servir/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Inici prevalidació/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Final prevalidació/i)).toBeInTheDocument();
  expect(screen.getByText(/Finestra actual:/i)).toBeInTheDocument();
});

test('ChecksAdminView shows explicit progress while validation is running', async () => {
  let resolveValidation;
  axios.post.mockImplementation((url) => {
    if (url === '/api/checks/validate-preview') {
      return new Promise((resolve) => {
        resolveValidation = () => resolve({
          data: {
            status: 'ok',
            profile: 'E13DB',
            time_filter: {
              mode: 'range',
              start_date: '2026-04-03',
              end_date: '2026-04-10',
              range_start_at: '2026-04-03T08:15',
              range_end_at: '2026-04-10T09:45',
            },
            validation: {
              status: 'ok',
              row_count: 0,
              preview_row_count: 0,
              rows: [],
              columns: ['ESQUEMA'],
              rendered_sql: 'select * from epsilon_table',
              duration_ms: 12,
              time_filter_pushed: true,
            },
            ai_preview: {
              status: 'ok',
              model_utilitzat: 'fake-model',
              resum_executiu: 'Resum.',
              explicacio_funcional: 'Funcional.',
              explicacio_tecnica: 'Tecnica.',
              nivell_confianca: 0.8,
            },
          },
        });
      });
    }
    return Promise.resolve({ data: { status: 'ok' } });
  });

  render(<ChecksAdminView selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Nou check/i }));
  fireEvent.change(screen.getByPlaceholderText('CHECK_14'), { target: { value: 'check_epsilon' } });
  fireEvent.change(screen.getByPlaceholderText(/WHEN OTHERS/i), { target: { value: 'Epsilon check' } });
  fireEvent.change(screen.getByLabelText(/Inici prevalidació/i), { target: { value: '2026-04-03T08:15' } });
  fireEvent.change(screen.getByLabelText(/Final prevalidació/i), { target: { value: '2026-04-10T09:45' } });
  fireEvent.change(document.querySelector('textarea[spellcheck="false"]'), {
    target: { value: 'select * from epsilon_table' },
  });

  fireEvent.click(screen.getByRole('button', { name: /Validar consulta i previsualitzar IA/i }));

  expect(await screen.findByRole('status')).toHaveTextContent(/Executant prevalidació a Oracle/i);
  expect(screen.getByRole('button', { name: /Validant consulta i previsualització IA/i })).toBeDisabled();

  resolveValidation();

  await waitFor(() => {
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

test('ChecksAdminView allows choosing a different environment for prevalidation', async () => {
  axios.post.mockImplementation((url) => {
    if (url === '/api/checks/validate-preview') {
      return Promise.resolve({
        data: {
          status: 'ok',
          profile: 'E13QA',
          time_filter: {
            mode: 'range',
            start_date: '2026-04-03',
            end_date: '2026-04-10',
            range_start_at: '2026-04-03T08:15',
            range_end_at: '2026-04-10T09:45',
          },
          validation: {
            status: 'ok',
            row_count: 0,
            preview_row_count: 0,
            rows: [],
            columns: ['ESQUEMA'],
            rendered_sql: 'select * from gamma_table',
            duration_ms: 9,
            time_filter_pushed: true,
          },
          ai_preview: {
            status: 'ok',
            model_utilitzat: 'fake-model',
            resum_executiu: 'Resum QA.',
            explicacio_funcional: 'Funcional QA.',
            explicacio_tecnica: 'Tecnica QA.',
            nivell_confianca: 0.75,
          },
        },
      });
    }
    return Promise.resolve({ data: { status: 'ok' } });
  });

  render(<ChecksAdminView profiles={['E13DB', 'E13QA']} selectedProfile="E13DB" />);

  expect(await screen.findByText('CHECK_ALPHA')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Nou check/i }));

  fireEvent.change(screen.getByPlaceholderText('CHECK_14'), { target: { value: 'check_delta' } });
  fireEvent.change(screen.getByPlaceholderText(/WHEN OTHERS/i), { target: { value: 'Delta check' } });
  fireEvent.change(screen.getByLabelText(/Inici prevalidació/i), { target: { value: '2026-04-03T08:15' } });
  fireEvent.change(screen.getByLabelText(/Final prevalidació/i), { target: { value: '2026-04-10T09:45' } });
  fireEvent.change(document.querySelector('textarea[spellcheck="false"]'), {
    target: { value: 'select * from gamma_table' },
  });
  fireEvent.change(screen.getByLabelText(/Entorn prevalidació/i), { target: { value: 'E13QA' } });

  fireEvent.click(screen.getByRole('button', { name: /Validar consulta i previsualitzar IA/i }));

  await waitFor(() => {
    expect(axios.post).toHaveBeenCalledWith('/api/checks/validate-preview', expect.objectContaining({
      check_id: 'CHECK_DELTA',
      profile: 'E13QA',
      validation_start_at: '2026-04-03T08:15',
      validation_end_at: '2026-04-10T09:45',
    }));
  });

  expect(await screen.findByText(/Validaci.*sobre E13QA/i)).toBeInTheDocument();
});


