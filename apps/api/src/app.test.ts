import { describe, expect, it } from 'vitest';

import { buildApp } from './app.js';

import type { CacheStore, CreateTask, Task, TaskStore } from './types.js';

class MemoryTasks implements TaskStore {
  public tasks: Task[] = [];

  public async create(input: CreateTask): Promise<Task> {
    const task = {
      completed: false,
      createdAt: '2026-01-01T00:00:00.000Z',
      id: String(this.tasks.length + 1),
      title: input.title,
    };

    this.tasks.unshift(task);

    return task;
  }

  public async list(): Promise<Task[]> {
    return this.tasks;
  }
}

class MemoryCache implements CacheStore {
  private values = new Map<string, string>();

  public async delete(key: string): Promise<void> {
    this.values.delete(key);
  }

  public async get(key: string): Promise<string | null> {
    return this.values.get(key) ?? null;
  }

  public async set(key: string, value: string): Promise<void> {
    this.values.set(key, value);
  }
}

describe('tasks API', () => {
  it('rejects an empty task', async () => {
    const app = buildApp({ cacheStore: new MemoryCache(), taskStore: new MemoryTasks() });
    const response = await app.inject({
      method: 'POST',
      url: '/api/tasks',
      payload: { title: '' },
    });

    expect(response.statusCode).toBe(400);

    await app.close();
  });

  it('creates and lists a task', async () => {
    const app = buildApp({ cacheStore: new MemoryCache(), taskStore: new MemoryTasks() });
    const created = await app.inject({
      method: 'POST',
      url: '/api/tasks',
      payload: { title: 'Ship through GitOps' },
    });
    const listed = await app.inject({ method: 'GET', url: '/api/tasks' });

    expect(created.statusCode).toBe(201);
    expect(listed.json()).toEqual([expect.objectContaining({ title: 'Ship through GitOps' })]);

    await app.close();
  });

  it('serves repeated reads from the cache', async () => {
    const app = buildApp({ cacheStore: new MemoryCache(), taskStore: new MemoryTasks() });
    const first = await app.inject({ method: 'GET', url: '/api/tasks' });
    const second = await app.inject({ method: 'GET', url: '/api/tasks' });

    expect(first.headers['x-cache']).toBe('MISS');
    expect(second.headers['x-cache']).toBe('HIT');

    await app.close();
  });
});
