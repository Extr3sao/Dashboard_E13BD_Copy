import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MailConfigView from './MailConfigView.jsx';
import {
  getDeliveryConfig,
  getDeliveryRoutes,
  updateDeliveryConfig,
  updateDeliveryRoutes,
  testDeliveryEmail,
} from '../api/automation.js';

vi.mock('../api/automation.js', () => ({
  getDeliveryConfig: vi.fn(() => Promise.resolve({
    smtp_host: 'smtp.local',
    smtp_port: 587,
    smtp_username: 'demo',
    smtp_password: 'secret',
    smtp_use_tls: true,
    from_email: 'oracle-audit@example.com',
    default_recipients: ['dba@example.com'],
    failure_notification_recipients: ['suport@example.com'],
    auto_purge_enabled: true,
    history_retention_days: 30,
    retry_retention_days: 15,
    last_auto_purge_at: '2026-03-21T01:00:00Z',
  })),
  getDeliveryRoutes: vi.fn(() => Promise.resolve({
    tic_summary_recipients: ['tic@example.com'],
    providers: [{ provider_code: 'LOT_APP', label: 'Aplicacions', emails: ['app@example.com'], enabled: true }],
  })),
  updateDeliveryConfig: vi.fn(() => Promise.resolve({ status: 'success' })),
  updateDeliveryRoutes: vi.fn(() => Promise.resolve({ status: 'success' })),
  testDeliveryEmail: vi.fn(() => Promise.resolve({ message: 'Correu de prova enviat!' })),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

async function waitForLoadedView() {
  render(<MailConfigView />);
  expect(await screen.findByDisplayValue('smtp.local')).toBeInTheDocument();
}

test('MailConfigView saves normalized delivery config and provider routes', async () => {
  await waitForLoadedView();

  fireEvent.change(screen.getByDisplayValue('dba@example.com'), {
    target: { value: 'dba@example.com, ops@example.com ' },
  });
  fireEvent.change(screen.getByDisplayValue('suport@example.com'), {
    target: { value: 'suport@example.com, guardia@example.com ' },
  });
  fireEvent.click(screen.getByRole('button', { name: /^Afegir$/i }));

  const ticInputs = screen.getAllByPlaceholderText('correu@exemple.com');
  fireEvent.change(ticInputs[0], {
    target: { value: 'tic@example.com' },
  });
  fireEvent.change(ticInputs[ticInputs.length - 1], {
    target: { value: 'cap@example.com' },
  });

  fireEvent.click(screen.getByRole('button', { name: /Afegir ruta/i }));

  const providerInputs = screen.getAllByPlaceholderText('LOT_APP');
  const labelInputs = screen.getAllByPlaceholderText('Nom visible');
  const emailInputs = screen.getAllByPlaceholderText('proveidor@exemple.com, suport@exemple.com');

  fireEvent.change(providerInputs[providerInputs.length - 1], { target: { value: 'lot_aux' } });
  fireEvent.change(labelInputs[labelInputs.length - 1], { target: { value: ' Auxiliar ' } });
  fireEvent.change(emailInputs[emailInputs.length - 1], {
    target: { value: 'aux@example.com, aux2@example.com ' },
  });

  fireEvent.click(screen.getByRole('button', { name: /Desar Configuraci/i }));

  await waitFor(() => {
    expect(updateDeliveryConfig).toHaveBeenCalledWith(expect.objectContaining({
      smtp_port: 587,
      default_recipients: ['dba@example.com', 'ops@example.com'],
      failure_notification_recipients: ['suport@example.com', 'guardia@example.com'],
      history_retention_days: 30,
      retry_retention_days: 15,
    }));
  });

  expect(updateDeliveryRoutes).toHaveBeenCalledWith({
    tic_summary_recipients: [
      { email: 'tic@example.com', enabled: true },
      { email: 'cap@example.com', enabled: true },
    ],
    providers: expect.arrayContaining([
      expect.objectContaining({
        provider_code: 'LOT_APP',
        label: 'Aplicacions',
        emails: ['app@example.com'],
        enabled: true,
      }),
      expect.objectContaining({
        provider_code: 'LOT_AUX',
        label: 'Auxiliar',
        emails: ['aux@example.com', 'aux2@example.com'],
        enabled: true,
      }),
    ]),
  });

  expect(await screen.findByText(/desada correctament/i)).toBeInTheDocument();
});

test('MailConfigView validates SMTP test recipient and surfaces backend errors', async () => {
  testDeliveryEmail.mockRejectedValueOnce({
    response: { data: { detail: 'SMTP KO' } },
  });

  await waitForLoadedView();

  fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));
  expect(await screen.findByText(/Introdueix un correu per al test/i)).toBeInTheDocument();
  expect(testDeliveryEmail).not.toHaveBeenCalled();

  fireEvent.change(screen.getByPlaceholderText('Correu de test'), {
    target: { value: 'test@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));

  await waitFor(() => {
    expect(testDeliveryEmail).toHaveBeenCalledWith(expect.objectContaining({
      smtp_host: 'smtp.local',
      smtp_port: 587,
      recipient: 'test@example.com',
      default_recipients: ['dba@example.com'],
    }));
  });

  expect(await screen.findByText(/Error en el test: SMTP KO/i)).toBeInTheDocument();
  expect(getDeliveryConfig).toHaveBeenCalledTimes(1);
  expect(getDeliveryRoutes).toHaveBeenCalledTimes(1);
});
