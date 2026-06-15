import { fireEvent, render, screen } from '@testing-library/react';

import AppShellChrome from './AppShellChrome.jsx';

function renderAppShellChrome(overrides = {}) {
  const props = {
    showProfileSelector: true,
    selectedProfile: 'E13DB',
    onProfileChange: vi.fn(),
    profiles: ['E13DB', 'E13QA'],
    activeTab: 'Auditoria BBDD',
    onSelectMainTab: vi.fn(),
    ...overrides,
  };

  render(
    <>
      <AppShellChrome {...props} />
      <main id="main-content" tabIndex={-1}>Main target</main>
    </>
  );

  return props;
}

beforeEach(() => {
  window.location.hash = '';
});

test('AppShellChrome moves focus with skip-link and wires main navigation', () => {
  const props = renderAppShellChrome();

  fireEvent.click(screen.getByRole('link', { name: /Salta al contingut/i }));

  expect(document.activeElement).toBe(document.getElementById('main-content'));
  expect(window.location.hash).toBe('#main-content');

  fireEvent.click(screen.getByRole('button', { name: /Arquitectura/i }));
  fireEvent.click(screen.getByRole('button', { name: /Auditoria BBDD/i }));

  expect(props.onSelectMainTab).toHaveBeenCalledWith('Arquitectura');
  expect(props.onSelectMainTab).toHaveBeenCalledWith('Auditoria BBDD');
  expect(screen.getByRole('button', { name: /Configuraci./i })).toBeDisabled();
});

test('AppShellChrome renders the profile selector only when enabled', () => {
  const props = renderAppShellChrome();

  fireEvent.change(screen.getByDisplayValue('E13DB'), { target: { value: 'E13QA' } });
  expect(props.onProfileChange).toHaveBeenCalledWith('E13QA');

  renderAppShellChrome({ showProfileSelector: false });
  expect(screen.queryByText(/Connexi.. activa/i)).not.toBeInTheDocument();
});
