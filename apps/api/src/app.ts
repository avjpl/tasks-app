import Fastify from 'fastify';
import { z } from 'zod';
import type { CacheStore, Task, TaskStore } from './types.js';

const taskInput = z.object({
  title: z.string().trim().min(1).max(120),
});

const tasksCacheKey = 'tasks:v1';

export type AppDependencies = {
  cacheStore: CacheStore;
  taskStore: TaskStore;
};

export function buildApp(dependencies: AppDependencies) {
  const app = Fastify({ logger: process.env.NODE_ENV !== 'test' });

  app.get('/api/health', async () => ({ service: 'tasks-api', status: 'ok' }));

  app.get('/api/tasks', async (_request, reply) => {
    const cached = await dependencies.cacheStore.get(tasksCacheKey);

    if (cached) {
      reply.header('x-cache', 'HIT');

      return JSON.parse(cached) as Task[];
    }

    const tasks = await dependencies.taskStore.list();

    await dependencies.cacheStore.set(tasksCacheKey, JSON.stringify(tasks), 30);

    reply.header('x-cache', 'MISS');

    return tasks;
  });

  app.post('/api/tasks', async (request, reply) => {
    const result = taskInput.safeParse(request.body);

    if (!result.success) {
      return reply.code(400).send({ message: 'A title between 1 and 120 characters is required' });
    }

    const task = await dependencies.taskStore.create(result.data);

    await dependencies.cacheStore.delete(tasksCacheKey);

    return reply.code(201).send(task);
  });

  return app;
}
