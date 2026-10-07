import type { DemoAccountId } from '@/features/auth/types';

export interface WorkspaceUser {
  id: DemoAccountId;
  name: string;
  role: 'manager' | 'shiftManager';
  timezone?: string;
}

export type TaskStatus = 'new' | 'inProgress' | 'waiting' | 'done';
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';

export interface TaskActivity {
  actor: string;
  at: string;
  message: string;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  assigneeId: DemoAccountId | null;
  dueDate: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  sourceIssueId: string | null;
  sourceKey: string | null;
  sourceReference: string | null;
  sourceObservedAt: string | null;
  createdBy: DemoAccountId;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  version: number;
  activity: TaskActivity[];
}

export interface TaskInput {
  title: string;
  description: string;
  assigneeId: DemoAccountId | null;
  dueDate: string | null;
  priority: TaskPriority;
  sourceIssueId?: string | null;
}

export interface TaskUpdate extends TaskInput {
  id: string;
  version: number;
  status: TaskStatus;
  note: string;
}

export interface ReportOptions {
  date: string;
  timezone: string;
  overnightStart: string;
  overnightEnd: string;
  title: string;
}

export interface ReportItem {
  id: string;
  kind: 'task' | 'issue';
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignee: string;
  dueDate: string | null;
  firstSeenAt: string;
  updatedAt: string;
  completedAt: string | null;
  reference: string | null;
}

export interface ReportSection {
  key: string;
  title: string;
  items: ReportItem[];
}

export interface Report extends ReportOptions {
  id: string;
  generatedAt: string;
  generatedBy: string;
  windowStart: string;
  windowEnd: string;
  openCount: number;
  scope: string;
  sections: ReportSection[];
}

export interface ReportSchedule extends Omit<ReportOptions, 'date'> {
  id: string;
  deliveryTime: string;
  recipients: string[];
  enabled: boolean;
  updatedAt: string;
}

export interface Delivery {
  id: string;
  scheduleId: string;
  date: string;
  reportId: string;
  recipients: string[];
  status: 'queued' | 'sending' | 'sent' | 'failed' | 'unknown';
  attempts: number;
  createdAt: string;
  updatedAt: string;
  error: string | null;
}

export interface Workspace {
  users: WorkspaceUser[];
  tasks: Task[];
  reports: Report[];
  schedules: ReportSchedule[];
  deliveries: Delivery[];
}

export interface SharedApiError {
  status: number;
  data: { message: string };
}

export interface OperationRequest {
  operation: string;
  input?: object;
}

export interface AuthSession {
  user: WorkspaceUser;
  token: string;
}
