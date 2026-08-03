import { type Collection, MongoClient, ObjectId } from 'mongodb';
import { createClient } from 'redis';
import type { CacheStore, CreateTask, Task, TaskStore } from './types.js';

type TaskDocument = {
  _id: ObjectId;
  title: string;
  completed: boolean;
  createdAt: Date;
};

function toTask(document: TaskDocument): Task {
  return {
    id: document._id.toHexString(),
    title: document.title,
    completed: document.completed,
    createdAt: document.createdAt.toISOString(),
  };
}

export class MongoTaskStore implements TaskStore {
  public constructor(private readonly collection: Collection<TaskDocument>) {}

  public async create(input: CreateTask): Promise<Task> {
    const document: TaskDocument = {
      _id: new ObjectId(),
      title: input.title,
      completed: false,
      createdAt: new Date(),
    };

    await this.collection.insertOne(document);

    return toTask(document);
  }

  public async list(): Promise<Task[]> {
    const documents = await this.collection.find().sort({ createdAt: -1 }).limit(100).toArray();

    return documents.map(toTask);
  }
}

export class RedisCacheStore implements CacheStore {
  public constructor(private readonly client: ReturnType<typeof createClient>) {}

  public async delete(key: string): Promise<void> {
    await this.client.del(key);
  }

  public async get(key: string): Promise<string | null> {
    return this.client.get(key);
  }

  public async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    await this.client.set(key, value, { EX: ttlSeconds });
  }
}

export async function connectStores(mongodbUri: string, database: string, redisUrl: string) {
  const mongo = new MongoClient(mongodbUri);
  const redis = createClient({ url: redisUrl });

  redis.on('error', (error) => console.error('Redis error', error));

  await Promise.all([mongo.connect(), redis.connect()]);
  const collection = mongo.db(database).collection<TaskDocument>('tasks');
  await collection.createIndex({ createdAt: -1 });

  return {
    cacheStore: new RedisCacheStore(redis),
    close: async () => {
      await Promise.all([mongo.close(), redis.quit()]);
    },
    taskStore: new MongoTaskStore(collection),
  };
}
