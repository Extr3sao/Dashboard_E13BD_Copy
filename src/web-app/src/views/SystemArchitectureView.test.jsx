import { fireEvent, render, screen } from '@testing-library/react';
import SystemArchitectureView from './SystemArchitectureView.jsx';

test('SystemArchitectureView shows node details and switches to flow mode', () => {
  render(<SystemArchitectureView />);

  expect(screen.getByText('Architecture Explorer')).toBeInTheDocument();
  expect(screen.getByText('Detalls del Component')).toBeInTheDocument();
  expect(screen.getByText(/Selecciona un objecte del mapa/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /useDeepScan/i }));

  expect(screen.getByRole('heading', { name: 'useDeepScan' })).toBeInTheDocument();
  expect(screen.getByText(/Gestió de l'Estat/i)).toBeInTheDocument();
  expect(screen.getByText(/runDeepAudit = async/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Flow: Execució d'Auditoria/i }));

  expect(screen.getByText(/Click "Auditar"/i)).toBeInTheDocument();
  expect(screen.getByText(/POST \/audit\/deep/i)).toBeInTheDocument();
  expect(screen.getByText(/Flow: Execució d'Auditoria/i)).toBeInTheDocument();
});
