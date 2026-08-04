import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from './App.js';

afterEach(() => vi.restoreAllMocks());

it('loads and creates tasks', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: '1' }), { status: 201 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify([{ id: '1', title: 'Deploy safely' }]), { status: 200 }),
    );

  render(<App />);
  await screen.findByText('No tasks yet.');
  fireEvent.change(screen.getByLabelText('New task'), { target: { value: 'Deploy safely' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add task' }));

  await screen.findByText('Deploy safely');
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
});
