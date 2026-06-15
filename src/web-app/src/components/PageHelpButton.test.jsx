import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import PageHelpButton from './PageHelpButton.jsx';

test('PageHelpButton opens and closes contextual help', async () => {
  render(
    <PageHelpButton
      helpContent={{
        title: 'Pantalla de prova',
        summary: 'Resum curt de la pantalla.',
        sections: [
          { title: 'Què fa', items: ['Mostra dades', 'Permet revisar resultats'] },
        ],
      }}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /Ajuda: Pantalla de prova/i }));

  expect(await screen.findByRole('dialog', { name: /Pantalla de prova/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Resum curt de la pantalla/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Mostra dades/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Tanca ajuda/i }));
  expect(screen.queryByRole('dialog', { name: /Pantalla de prova/i })).not.toBeInTheDocument();
});

test('PageHelpButton closes with Escape', async () => {
  render(
    <PageHelpButton
      helpContent={{
        title: 'Pantalla de prova',
        summary: 'Resum curt de la pantalla.',
        sections: [
          { title: 'QuÃ¨ fa', items: ['Mostra dades'] },
        ],
      }}
    />,
  );

  const triggerButton = screen.getByRole('button', { name: /Ajuda: Pantalla de prova/i });
  triggerButton.focus();
  fireEvent.click(triggerButton);
  expect(await screen.findByRole('dialog', { name: /Pantalla de prova/i })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /Tanca ajuda/i })).toHaveFocus();
  });

  fireEvent.keyDown(window, { key: 'Escape' });
  await waitFor(() => {
    expect(screen.queryByRole('dialog', { name: /Pantalla de prova/i })).not.toBeInTheDocument();
    expect(triggerButton).toHaveFocus();
  });
});
