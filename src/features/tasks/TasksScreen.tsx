import { useState } from 'react';
import { FlatList, View } from 'react-native';

import { Badge, Button, Card, Input, makeStyles, Text } from '@/design-system';
import { selectDemoAccountId } from '@/features/auth/sessionSlice';
import { LoadingState, ScreenState } from '@/features/common/ScreenState';
import { sharedMode, workspaceError } from '@/features/workspace/client';
import { SharedModeRequired } from '@/features/workspace/SharedModeRequired';
import type { Task } from '@/features/workspace/types';
import { useGetWorkspaceQuery } from '@/features/workspace/workspaceApi';
import { useAppSelector } from '@/store/hooks';

import { TaskEditor } from './TaskEditor';
import { taskStatusLabels } from './taskLabels';

export function TasksScreen() {
  const styles = useStyles();
  const accountId = useAppSelector(selectDemoAccountId);
  const query = useGetWorkspaceQuery(undefined, {
    skip: !sharedMode || !accountId,
    pollingInterval: 15_000,
  });
  const [editor, setEditor] = useState<{ task: Task | null } | null>(null);
  const [filter, setFilter] = useState('Open');
  const [search, setSearch] = useState('');
  if (!sharedMode) return <SharedModeRequired />;
  if (query.isLoading) return <LoadingState label="Loading tasks" />;
  if (!query.data)
    return (
      <ScreenState
        title="Couldn't load tasks"
        message={workspaceError(query.error)}
        actionLabel="Retry"
        onAction={() => void query.refetch()}
      />
    );
  const { tasks, users } = query.data;
  const filtered = tasks.filter(
    (task) =>
      (filter === 'All' ||
        (filter === 'Done'
          ? task.status === 'done'
          : filter === 'Mine'
            ? task.assigneeId === accountId && task.status !== 'done'
            : filter === 'Unassigned'
              ? task.assigneeId === null && task.status !== 'done'
              : task.status !== 'done')) &&
      `${task.title} ${task.description}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={filtered}
      keyExtractor={(task) => task.id}
      testID="screen-tasks"
      refreshing={query.isFetching}
      onRefresh={() => void query.refetch()}
      ListHeaderComponent={
        <View style={styles.header}>
          <Text variant="heading">Tasks</Text>
          <Text tone="muted">Assign work, set deadlines, and record progress across shifts.</Text>
          {query.isError ? (
            <>
              <Text tone="error">Showing saved results. Refresh failed.</Text>
              <Button variant="outline" onPress={() => void query.refetch()}>
                Retry refresh
              </Button>
            </>
          ) : null}
          {editor ? (
            <TaskEditor
              key={editor.task?.id ?? 'new'}
              task={editor.task}
              users={users}
              onClose={() => setEditor(null)}
            />
          ) : (
            <Button onPress={() => setEditor({ task: null })} testID="new-task">
              New task
            </Button>
          )}
          <Input label="Search tasks" value={search} onChangeText={setSearch} />
          <View style={styles.filters}>
            {['Open', 'Mine', 'Unassigned', 'Done', 'All'].map((value) => (
              <Button
                key={value}
                variant={filter === value ? 'secondary' : 'outline'}
                size="sm"
                onPress={() => setFilter(value)}
                accessibilityLabel={`Filter ${value} tasks`}
              >
                {`${value}${filter === value ? ' (selected)' : ''}`}
              </Button>
            ))}
          </View>
        </View>
      }
      ListEmptyComponent={
        <ScreenState title="No matching tasks" message="Create a task or choose another filter." />
      }
      renderItem={({ item: task }) => {
        const owner = users.find((user) => user.id === task.assigneeId)?.name ?? 'Unassigned';
        const editable =
          accountId === 'elena' ||
          task.assigneeId === accountId ||
          (task.assigneeId === null && task.createdBy === accountId);
        return (
          <Card testID={`task-${task.id}`}>
            <View style={styles.card}>
              <Text variant="title">{task.title}</Text>
              <View style={styles.filters}>
                <Badge variant={task.status === 'done' ? 'success' : 'warning'}>
                  {taskStatusLabels[task.status]}
                </Badge>
                <Text variant="bodySm">{`${task.priority} priority · ${owner}`}</Text>
              </View>
              {task.description ? <Text>{task.description}</Text> : null}
              <Text
                variant="caption"
                tone="muted"
              >{`Due: ${task.dueDate ?? 'Not set'} · Updated: ${task.updatedAt}`}</Text>
              {task.sourceIssueId ? (
                <Text variant="caption" tone="muted">{`Linked issue: ${task.sourceIssueId}`}</Text>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                onPress={() => setEditor({ task })}
                disabled={!editable}
                accessibilityLabel={`Update task ${task.title}`}
              >
                Update task
              </Button>
            </View>
          </Card>
        );
      }}
    />
  );
}

const useStyles = makeStyles((t) => ({
  screen: { flex: 1, backgroundColor: t.color.bg },
  content: {
    width: '100%',
    maxWidth: t.size.content,
    alignSelf: 'center',
    padding: t.spacing[4],
    paddingBottom: t.spacing[16],
    gap: t.spacing[3],
  },
  header: { gap: t.spacing[3], marginBottom: t.spacing[3] },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing[2], alignItems: 'center' },
  card: { gap: t.spacing[2] },
}));
