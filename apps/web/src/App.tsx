import { type FormEvent, useCallback, useEffect, useState } from 'react';

type Task = {
  id: string;
  title: string;
  completed: boolean;
  createdAt: string;
};

export function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('Loading tasks…');

  const loadTasks = useCallback(async () => {
    const response = await fetch('/api/tasks');

    if (!response.ok) throw new Error('Could not load tasks');

    const nextTasks = (await response.json()) as Task[];

    setTasks(nextTasks);

    setMessage(nextTasks.length === 0 ? 'No tasks yet.' : '');
  }, []);

  useEffect(() => {
    loadTasks().catch(() => setMessage('The API is unavailable.'));
  }, [loadTasks]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const response = await fetch('/api/tasks', {
      body: JSON.stringify({ title }),
      headers: { 'content-type': 'application/json' },
      method: 'POST',
    });

    if (!response.ok) {
      setMessage('Enter a task title before saving.');
      return;
    }

    setTitle('');
    await loadTasks();
  }

  return (
    <main>
      <p className="eyebrow">Kubernetes · Argo CD · TypeScript</p>
      <h1>Homelab tasks</h1>
      <p className="intro">MongoDB remembers them. Redis makes repeat reads fast.</p>

      <form onSubmit={submit}>
        <label htmlFor="title">New task</label>
        <div className="form-row">
          <input
            id="title"
            maxLength={120}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Test the next GitOps release"
            value={title}
          />
          <button type="submit">Add task</button>
        </div>
      </form>

      {message && <p role="status">{message}</p>}

      <ul>
        {tasks.map((task) => (
          <li key={task.id}>{task.title}</li>
        ))}
      </ul>
    </main>
  );
}
