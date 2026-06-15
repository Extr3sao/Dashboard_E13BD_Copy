import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ObsoletsRegistryView from './ObsoletsRegistryView.jsx';
import { createObsolet, listObsolets } from '../api/obsolets.js';

vi.mock('../api/obsolets.js', () => ({
  listObsolets: vi.fn(),
  createObsolet: vi.fn(),
  updateObsolet: vi.fn(),
}));

const firstLoad = {
  items: [
    {
      id: 1,
      schema_name: 'APP_USER',
      object_name: 'TMP_OLD',
      object_type: 'TABLE',
      risk_level: 'HIGH',
      recommendation: 'Revisar',
      source: 'manual',
      reason: 'Sense ús',
    },
  ],
};

const afterCreateLoad = {
  items: [
    ...firstLoad.items,
    {
      id: 2,
      schema_name: 'CORE_DB',
      object_name: 'VW_UNUSED',
      object_type: 'VIEW',
      risk_level: 'MEDIUM',
      recommendation: 'Eliminar',
      source: 'manual',
      reason: 'Vista obsoleta',
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  listObsolets.mockResolvedValue(firstLoad);
  createObsolet.mockResolvedValue({ id: 2 });
  window.alert = vi.fn();
});

test('ObsoletsRegistryView loads registry entries and refreshes after manual creation', async () => {
  listObsolets
    .mockResolvedValueOnce(firstLoad)
    .mockResolvedValueOnce(afterCreateLoad);

  render(<ObsoletsRegistryView />);

  expect(await screen.findByText("Registre d'Obsolets (SQLite)")).toBeInTheDocument();
  expect(listObsolets).toHaveBeenCalledWith({ only_obsolete: true, limit: 200, offset: 0 });
  expect(await screen.findByText('TMP_OLD')).toBeInTheDocument();
  expect(screen.getByText('Entrades (1)')).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText(/SCHEMA/i), { target: { value: 'core_db' } });
  fireEvent.change(screen.getByPlaceholderText(/OBJECTE/i), { target: { value: 'VW_UNUSED' } });
  fireEvent.change(screen.getByDisplayValue('TABLE'), { target: { value: 'VIEW' } });
  fireEvent.change(screen.getByDisplayValue('LOW'), { target: { value: 'MEDIUM' } });
  fireEvent.change(screen.getByPlaceholderText(/Recomanaci/i), { target: { value: 'Eliminar' } });
  fireEvent.change(screen.getByPlaceholderText(/Descripci/i), { target: { value: 'No es referencia des de cap job' } });
  fireEvent.change(screen.getByPlaceholderText(/Motiu/i), { target: { value: 'Vista obsoleta' } });

  fireEvent.click(screen.getByRole('button', { name: /Afegir al registre/i }));

  await waitFor(() => {
    expect(createObsolet).toHaveBeenCalledWith({
      schema_name: 'CORE_DB',
      object_name: 'VW_UNUSED',
      object_type: 'VIEW',
      reason: 'Vista obsoleta',
      risk_level: 'MEDIUM',
      recommendation: 'Eliminar',
      description: 'No es referencia des de cap job',
    });
  });

  await waitFor(() => {
    expect(listObsolets).toHaveBeenCalledTimes(2);
  });

  expect(await screen.findByText('VW_UNUSED')).toBeInTheDocument();
  expect(screen.getByText('Entrades (2)')).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/SCHEMA/i)).toHaveValue('');
});

test('ObsoletsRegistryView blocks submit when required fields are missing', async () => {
  render(<ObsoletsRegistryView />);

  expect(await screen.findByText('TMP_OLD')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Afegir al registre/i }));

  expect(window.alert).toHaveBeenCalledWith('Falten camps obligatoris (schema, objecte, tipus, motiu, risc).');
  expect(createObsolet).not.toHaveBeenCalled();
});
