import { render, screen } from '@testing-library/react';
import TutorialView from './TutorialView.jsx';

test('TutorialView renders the main architecture and flow sections', () => {
  render(<TutorialView />);

  expect(screen.getByRole('heading', { name: 'Tutorial' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Arquitectura' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Fluxos principals (diagrames)' })).toBeInTheDocument();
  expect(screen.getByText(/FastAPI parla amb Oracle/i)).toBeInTheDocument();
  expect(screen.getAllByText('FastAPI').length).toBeGreaterThan(0);
  expect(screen.getAllByText('src/api/main.py').length).toBeGreaterThan(0);
  expect(screen.getByText('/api/ai/chat')).toBeInTheDocument();
  expect(screen.getByText(/No enganxis contrasenyes/i)).toBeInTheDocument();
});

test('TutorialView exposes menu cards and end-to-end examples for active modules', () => {
  render(<TutorialView />);

  expect(screen.getByRole('heading', { name: /Mapa de Men.s/i })).toBeInTheDocument();
  expect(screen.getAllByText('Deep Scan').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Repositori').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Obsolets').length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Configuraci./i).length).toBeGreaterThan(0);
  expect(screen.getByText('/api/obsolets')).toBeInTheDocument();
  expect(screen.getByText(/Importar TXT Bulk/i)).toBeInTheDocument();
  expect(screen.getByText(/Triage .* Deep Scan .* Report PDF/i)).toBeInTheDocument();
  expect(screen.getByText(/registrar a Obsolets/i)).toBeInTheDocument();
});
