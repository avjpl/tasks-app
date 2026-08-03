import { buildApp } from './app.js';
import { readConfig } from './config.js';
import { connectStores } from './stores.js';

const config = readConfig();
const stores = await connectStores(config.MONGODB_URI, config.MONGODB_DB, config.REDIS_URL);
const app = buildApp(stores);

const shutdown = async (signal: string) => {
  app.log.info({ signal }, 'shutting down');
  await app.close();
  await stores.close();
  process.exit(0);
};

process.on('SIGINT', () => void shutdown('SIGINT'));
process.on('SIGTERM', () => void shutdown('SIGTERM'));

await app.listen({ host: config.HOST, port: config.PORT });
