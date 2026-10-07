import type { TaskPriority, TaskStatus } from '@/features/workspace/types';

export const taskStatuses: readonly TaskStatus[] = ['new', 'inProgress', 'waiting', 'done'];
export const taskPriorities: readonly TaskPriority[] = ['low', 'normal', 'high', 'urgent'];
export const taskStatusLabels: Record<TaskStatus, string> = {
  new: 'New',
  inProgress: 'In progress',
  waiting: 'Waiting',
  done: 'Done',
};
