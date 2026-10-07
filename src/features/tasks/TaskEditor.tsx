import { useState } from 'react';
import { View } from 'react-native';

import { Button, Card, Input, makeStyles, Text } from '@/design-system';
import { selectDemoAccountId } from '@/features/auth/sessionSlice';
import { workspaceError } from '@/features/workspace/client';
import type {
  Task,
  TaskInput,
  TaskPriority,
  TaskStatus,
  WorkspaceUser,
} from '@/features/workspace/types';
import { useCreateTaskMutation, useUpdateTaskMutation } from '@/features/workspace/workspaceApi';
import { useAppSelector } from '@/store/hooks';

import { taskPriorities, taskStatuses, taskStatusLabels } from './taskLabels';

export function TaskEditor({
  task,
  users,
  onClose,
}: {
  task: Task | null;
  users: WorkspaceUser[];
  onClose: () => void;
}) {
  const styles = useStyles();
  const accountId = useAppSelector(selectDemoAccountId);
  const [title, setTitle] = useState(task?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? '');
  const [assigneeId, setAssigneeId] = useState(task?.assigneeId ?? null);
  const [dueDate, setDueDate] = useState(task?.dueDate ?? '');
  const [priority, setPriority] = useState<TaskPriority>(task?.priority ?? 'normal');
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? 'new');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [createTask, createState] = useCreateTaskMutation();
  const [updateTask, updateState] = useUpdateTaskMutation();
  const busy = createState.isLoading || updateState.isLoading;
  const save = async () => {
    setError(null);
    const input: TaskInput = {
      title,
      description,
      assigneeId,
      dueDate: dueDate.trim() || null,
      priority,
    };
    try {
      if (task)
        await updateTask({ ...input, id: task.id, version: task.version, status, note }).unwrap();
      else await createTask(input).unwrap();
      onClose();
    } catch (failure) {
      setError(workspaceError(failure));
    }
  };
  return (
    <Card testID="task-editor">
      <View style={styles.form}>
        <Text variant="title">{task ? 'Update task' : 'Create task'}</Text>
        <Input
          label="Task title"
          value={title}
          onChangeText={setTitle}
          testID="task-title"
          maxLength={200}
        />
        <Input
          label="Description"
          value={description}
          onChangeText={setDescription}
          multiline
          testID="task-description"
        />
        <Text variant="bodySm" weight="medium">
          Assignee
        </Text>
        <View style={styles.choices}>
          {[{ id: null, name: 'Unassigned' }, ...users].map((user) => (
            <Button
              key={user.id ?? 'none'}
              variant={assigneeId === user.id ? 'secondary' : 'outline'}
              size="sm"
              onPress={() => setAssigneeId(user.id)}
              disabled={
                busy ||
                (accountId !== 'elena' &&
                  (task !== null || (user.id !== null && user.id !== accountId)))
              }
              accessibilityLabel={`Assign to ${user.name}`}
              testID={`assignee-${user.id ?? 'none'}`}
            >
              {`${user.name}${assigneeId === user.id ? ' (selected)' : ''}`}
            </Button>
          ))}
        </View>
        <Input
          label="Due date (YYYY-MM-DD)"
          value={dueDate}
          onChangeText={setDueDate}
          placeholder="2026-10-15"
          testID="task-due"
        />
        <Text variant="bodySm" weight="medium">
          Priority
        </Text>
        <View style={styles.choices}>
          {taskPriorities.map((value) => (
            <Button
              key={value}
              variant={priority === value ? 'secondary' : 'outline'}
              size="sm"
              onPress={() => setPriority(value)}
              accessibilityLabel={`Priority ${value}`}
            >
              {`${value}${priority === value ? ' (selected)' : ''}`}
            </Button>
          ))}
        </View>
        {task ? (
          <>
            <Text variant="bodySm" weight="medium">
              Status
            </Text>
            <View style={styles.choices}>
              {taskStatuses.map((value) => (
                <Button
                  key={value}
                  variant={status === value ? 'secondary' : 'outline'}
                  size="sm"
                  onPress={() => setStatus(value)}
                  accessibilityLabel={`Set status ${taskStatusLabels[value]}`}
                >
                  {`${taskStatusLabels[value]}${status === value ? ' (selected)' : ''}`}
                </Button>
              ))}
            </View>
            <Input
              label="Update or completion note"
              value={note}
              onChangeText={setNote}
              multiline
              helperText="A note is required when completing a task."
              testID="task-note"
            />
            <Text variant="bodySm" weight="medium">
              Activity
            </Text>
            {task.activity.map((event, index) => (
              <Text
                key={`${event.at}-${index}`}
                variant="caption"
                tone="muted"
              >{`${event.actor} · ${event.at} · ${event.message}`}</Text>
            ))}
          </>
        ) : null}
        {error ? (
          <View accessibilityLiveRegion="polite">
            <Text tone="error">{error}</Text>
          </View>
        ) : null}
        <View style={styles.choices}>
          <Button
            onPress={() => void save()}
            loading={busy}
            disabled={!title.trim()}
            testID="save-task"
          >
            {task ? 'Save task' : 'Create task'}
          </Button>
          <Button variant="ghost" onPress={onClose} disabled={busy}>
            Cancel
          </Button>
        </View>
      </View>
    </Card>
  );
}

const useStyles = makeStyles((t) => ({
  form: { gap: t.spacing[3] },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing[2] },
}));
