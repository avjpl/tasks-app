export type Task = {
  id: string;
  title: string;
  completed: boolean;
  createdAt: string;
};

export type CreateTask = Pick<Task, 'title'>;

export interface TaskStore {
  create(input: CreateTask): Promise<Task>;
  list(): Promise<Task[]>;
}

export interface CacheStore {
  delete(key: string): Promise<void>;
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttlSeconds: number): Promise<void>;
}
