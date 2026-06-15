import { fireEvent, render, screen } from '@testing-library/react';

import AppPageHeader from './AppPageHeader.jsx';

vi.mock('./PageHelpButton.jsx', () => ({
  default: ({ helpKey, className }) => <button className={className}>help:{helpKey}</button>,
}));

test('AppPageHeader renders help, subtab and global report controls', () => {
  const onRefresh = vi.fn();
  const onGenerateReport = vi.fn();

  render(
    <AppPageHeader
      activeTab="Auditoria BBDD"
      subtabLabel="Auditoria de canvis"
      helpKey="postCrqAudit"
      showGlobalReportControls={true}
      loading={false}
      onRefresh={onRefresh}
      onGenerateReport={onGenerateReport}
    />
  );

  expect(screen.getByRole('heading', { name: 'Auditoria BBDD' })).toBeInTheDocument();
  expect(screen.getByText('Auditoria de canvis')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'help:postCrqAudit' })).toBeInTheDocument();
  expect(screen.getByText(/Arquitectura d'auditoria governada per Agents IA/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Refresca/i }));
  fireEvent.click(screen.getByRole('button', { name: /Generar Informe/i }));

  expect(onRefresh).toHaveBeenCalled();
  expect(onGenerateReport).toHaveBeenCalled();
});

test('AppPageHeader hides report controls and shows loading state when needed', () => {
  const onRefresh = vi.fn();
  const onGenerateReport = vi.fn();

  const { rerender } = render(
    <AppPageHeader
      activeTab="Arquitectura"
      subtabLabel={null}
      helpKey="architecture"
      showGlobalReportControls={false}
      loading={false}
      onRefresh={onRefresh}
      onGenerateReport={onGenerateReport}
    />
  );

  expect(screen.queryByRole('button', { name: /Refresca/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Generar Informe/i })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'help:architecture' })).toBeInTheDocument();

  rerender(
    <AppPageHeader
      activeTab="Arquitectura"
      subtabLabel={null}
      helpKey="architecture"
      showGlobalReportControls={true}
      loading={true}
      onRefresh={onRefresh}
      onGenerateReport={onGenerateReport}
    />
  );

  expect(screen.getByRole('button', { name: /Generant/i })).toBeDisabled();
});
