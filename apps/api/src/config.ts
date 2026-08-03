import { z } from 'zod';

const schema = z.object({
  HOST: z.string().default('0.0.0.0'),
  MONGODB_DB: z.string().default('tasks'),
  MONGODB_URI: z.string().min(1),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  REDIS_URL: z.string().min(1),
});

export type Config = z.infer<typeof schema>;

export function readConfig(environment: NodeJS.ProcessEnv = process.env): Config {
  return schema.parse(environment);
}
