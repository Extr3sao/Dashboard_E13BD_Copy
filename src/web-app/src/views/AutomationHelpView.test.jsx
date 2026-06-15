import { fireEvent, render, screen } from '@testing-library/react';
import AutomationHelpView from './AutomationHelpView.jsx';

vi.mock('../components/AutomationGuide.jsx', () => ({
  default: () => (
    <div>
      <h2>Guia mock</h2>
      <p>Fluxos interns i tra?abilitat</p>
    </div>
  ),
}));

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/dashboard?automation-help=1&tab=automation');
});

test('AutomationHelpView renders shell actions and fallback help state', async () => {
  render(<AutomationHelpView />);

  expect(screen.getByRole('heading', { name: /Guia visual d.Automatitzacions/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Obre l.aplicaci./i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Tanca ajuda/i })).toBeInTheDocument();
  expect(screen.getByText(/Carregant ajuda contextual/i)).toBeInTheDocument();
});

test('AutomationHelpView opens the app without the automation-help query param', async () => {
  const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

  render(<AutomationHelpView />);
  fireEvent.click(screen.getByRole('button', { name: /Obre l.aplicaci./i }));

  expect(openSpy).toHaveBeenCalledWith(
    'http://localhost:3000/dashboard?tab=automation',
    '_blank',
    'noopener,noreferrer'
  );
});
