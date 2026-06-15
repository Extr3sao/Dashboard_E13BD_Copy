import { fireEvent, render, screen } from '@testing-library/react';

import AppPageHeader from './components/AppPageHeader.jsx';

function renderHeader({ activeTab = 'Auditoria BBDD', helpKey, subtabLabel }) {
  return render(
    <AppPageHeader
      activeTab={activeTab}
      subtabLabel={subtabLabel}
      helpKey={helpKey}
      showGlobalReportControls={false}
      loading={false}
      onRefresh={() => {}}
      onGenerateReport={() => {}}
    />,
  );
}

test('App shows contextual help for active database audit and architecture pages', async () => {
  const view = renderHeader({ helpKey: 'deepScan', subtabLabel: 'Anàlisi obsolets' });

  fireEvent.click(await screen.findByRole('button', { name: /Ajuda: An.*lisi obsolets/i }));
  expect(await screen.findByRole('dialog', { name: /An.*lisi obsolets/i })).toBeInTheDocument();
  expect(screen.getByText(/360/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Tanca ajuda/i }));
  view.rerender(
    <AppPageHeader
      activeTab="Auditoria BBDD"
      subtabLabel="Gestió de controls"
      helpKey="checksAdmin"
      showGlobalReportControls={false}
      loading={false}
      onRefresh={() => {}}
      onGenerateReport={() => {}}
    />,
  );

  fireEvent.click(await screen.findByRole('button', { name: /Ajuda: Gesti.* de controls/i }));
  expect(await screen.findByRole('dialog', { name: /Gesti.* de controls/i })).toBeInTheDocument();
  expect(screen.getByText(/Administra els checks SQL del sistema/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Tanca ajuda/i }));
  view.rerender(
    <AppPageHeader
      activeTab="Arquitectura"
      subtabLabel={null}
      helpKey="architecture"
      showGlobalReportControls={false}
      loading={false}
      onRefresh={() => {}}
      onGenerateReport={() => {}}
    />,
  );

  fireEvent.click(await screen.findByRole('button', { name: /Ajuda: Arquitectura/i }));
  expect(await screen.findByRole('dialog', { name: /Arquitectura/i })).toBeInTheDocument();
  expect(screen.getByText(/Explorador visual de capas/i)).toBeInTheDocument();
});
