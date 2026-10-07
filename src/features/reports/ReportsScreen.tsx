import { useState } from 'react';
import { FlatList, Platform, View } from 'react-native';

import { Button, Card, Input, makeStyles, Text } from '@/design-system';
import {
  selectAccessToken,
  selectDemoAccountId,
  selectSharedUser,
} from '@/features/auth/sessionSlice';
import { LoadingState, ScreenState } from '@/features/common/ScreenState';
import { taskStatusLabels } from '@/features/tasks/taskLabels';
import { todayKey } from '@/features/logs/logTemplates';
import { exportReport, sharedMode, workspaceError } from '@/features/workspace/client';
import { SharedModeRequired } from '@/features/workspace/SharedModeRequired';
import type { ReportOptions } from '@/features/workspace/types';
import {
  useGetWorkspaceQuery,
  usePreviewReportMutation,
  useRetryDeliveryMutation,
  useSaveReportMutation,
} from '@/features/workspace/workspaceApi';
import { useAppSelector } from '@/store/hooks';

import { ScheduleEditor } from './ScheduleEditor';

export function ReportsScreen() {
  const styles = useStyles();
  const accountId = useAppSelector(selectDemoAccountId);
  const token = useAppSelector(selectAccessToken);
  const user = useAppSelector(selectSharedUser);
  const query = useGetWorkspaceQuery(undefined, {
    skip: !sharedMode || accountId !== 'elena',
    pollingInterval: 15_000,
  });
  const [title, setTitle] = useState('Morning operations report');
  const [date, setDate] = useState(todayKey());
  const [timezone, setTimezone] = useState(user?.timezone ?? 'America/Los_Angeles');
  const [start, setStart] = useState('17:00');
  const [end, setEnd] = useState('08:00');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [preview, previewState] = usePreviewReportMutation();
  const [save, saveState] = useSaveReportMutation();
  const [retry, retryState] = useRetryDeliveryMutation();
  if (!sharedMode) return <SharedModeRequired />;
  if (accountId !== 'elena')
    return (
      <ScreenState
        title="Operations Manager access required"
        message="Report building and delivery schedules are managed by the Operations Manager."
      />
    );
  if (query.isLoading) return <LoadingState label="Loading reports" />;
  if (!query.data)
    return (
      <ScreenState
        title="Couldn't load reports"
        message={workspaceError(query.error)}
        actionLabel="Retry"
        onAction={() => void query.refetch()}
      />
    );
  const workspace = query.data;
  const report = selectedId
    ? (workspace.reports.find((item) => item.id === selectedId) ??
      (saveState.data?.id === selectedId ? saveState.data : undefined))
    : previewState.data;
  const reportSaved =
    report && (selectedId !== null || workspace.reports.some((item) => item.id === report.id));
  const options: ReportOptions = {
    title,
    date,
    timezone,
    overnightStart: start,
    overnightEnd: end,
  };
  const build = async (persist: boolean) => {
    setError(null);
    try {
      const result = await (persist ? save(options) : preview(options)).unwrap();
      setSelectedId(persist ? result.id : null);
    } catch (failure) {
      setError(workspaceError(failure));
    }
  };
  const download = async (format: 'html' | 'csv') => {
    if (!report || !token || Platform.OS !== 'web') return;
    setDownloading(true);
    setError(null);
    try {
      const content = await exportReport(report.id, format, token);
      const url = URL.createObjectURL(
        new Blob([content], { type: format === 'html' ? 'text/html' : 'text/csv' }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = `shift-relay-${report.date}.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setError(workspaceError(failure));
    } finally {
      setDownloading(false);
    }
  };
  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={report?.sections ?? []}
      keyExtractor={(section) => section.key}
      testID="screen-reports"
      refreshing={query.isFetching}
      onRefresh={() => void query.refetch()}
      ListHeaderComponent={
        <View style={styles.contentGroup}>
          <Text variant="heading">Report builder</Text>
          <Text tone="muted">
            Build a snapshot of outstanding work, overnight changes, deadlines, and assignments.
          </Text>
          {query.isError ? (
            <>
              <Text tone="error">Showing saved results. Refresh failed.</Text>
              <Button variant="outline" onPress={() => void query.refetch()}>
                Retry refresh
              </Button>
            </>
          ) : null}
          <Card>
            <View style={styles.contentGroup}>
              <Input
                label="Report title"
                value={title}
                onChangeText={setTitle}
                testID="report-title"
              />
              <Input
                label="Report date (YYYY-MM-DD)"
                value={date}
                onChangeText={setDate}
                testID="report-date"
              />
              <Input
                label="Report timezone"
                value={timezone}
                onChangeText={setTimezone}
                autoCapitalize="none"
              />
              <Input
                label="Overnight start on previous day (HH:MM)"
                value={start}
                onChangeText={setStart}
              />
              <Input
                label="Overnight end on report date (HH:MM)"
                value={end}
                onChangeText={setEnd}
              />
              <View style={styles.actions}>
                <Button
                  onPress={() => void build(false)}
                  loading={previewState.isLoading}
                  disabled={saveState.isLoading}
                  testID="preview-report"
                >
                  Preview report
                </Button>
                <Button
                  variant="outline"
                  onPress={() => void build(true)}
                  loading={saveState.isLoading}
                  disabled={previewState.isLoading}
                  testID="save-report"
                >
                  Build and save report
                </Button>
              </View>
            </View>
          </Card>
          {error ? (
            <View accessibilityLiveRegion="polite">
              <Text tone="error">{error}</Text>
            </View>
          ) : null}
          {report ? (
            <Card>
              <View style={styles.contentGroup}>
                <Text variant="title">{report.title}</Text>
                <Text>{`${report.date} · ${report.openCount} open items · ${report.timezone}`}</Text>
                <Text
                  variant="caption"
                  tone="muted"
                >{`Generated: ${report.generatedAt} · By ${report.generatedBy}`}</Text>
                <Text variant="caption" tone="muted">
                  {report.scope}
                </Text>
                {Platform.OS === 'web' ? (
                  <View style={styles.actions}>
                    <Button
                      variant="outline"
                      onPress={() => void download('html')}
                      disabled={!reportSaved || downloading}
                      testID="download-html"
                    >
                      Download HTML
                    </Button>
                    <Button
                      variant="outline"
                      onPress={() => void download('csv')}
                      disabled={!reportSaved || downloading}
                      testID="download-csv"
                    >
                      Download CSV
                    </Button>
                  </View>
                ) : (
                  <Text variant="caption" tone="muted">
                    Open the web app to download HTML or CSV. Preview and scheduling work here.
                  </Text>
                )}
                <Text variant="caption" tone="muted">
                  {reportSaved
                    ? 'Saved snapshot. Downloaded HTML can be printed to PDF in your browser.'
                    : 'Preview only. Build and save a report to export it.'}
                </Text>
              </View>
            </Card>
          ) : null}
        </View>
      }
      ListEmptyComponent={
        <ScreenState
          title="No report selected"
          message="Preview a report or open a saved snapshot below."
        />
      }
      renderItem={({ item: section }) => (
        <Card>
          <View style={styles.contentGroup}>
            <Text variant="title">{`${section.title} (${section.items.length})`}</Text>
            {section.items.length === 0 ? (
              <Text tone="muted">No items.</Text>
            ) : (
              section.items.map((item) => (
                <View key={item.id} style={styles.reportItem}>
                  <Text weight="semibold">{item.title}</Text>
                  <Text variant="bodySm">{`${item.priority} · ${taskStatusLabels[item.status]} · ${item.assignee} · Due ${item.dueDate ?? 'not set'}`}</Text>
                  {item.description ? (
                    <Text variant="bodySm" tone="muted">
                      {item.description}
                    </Text>
                  ) : null}
                  <Text variant="caption" tone="muted">{`First seen: ${item.firstSeenAt}`}</Text>
                </View>
              ))
            )}
          </View>
        </Card>
      )}
      ListFooterComponent={
        <View style={styles.contentGroup}>
          <Text variant="title">Saved reports</Text>
          {workspace.reports.length === 0 ? (
            <Text tone="muted">No saved reports yet.</Text>
          ) : (
            workspace.reports.map((item) => (
              <Button
                key={item.id}
                variant="outline"
                onPress={() => setSelectedId(item.id)}
                accessibilityLabel={`Open saved report ${item.title} ${item.generatedAt}`}
              >{`${item.title} · ${item.date}`}</Button>
            ))
          )}
          <ScheduleEditor key="daily" schedule={workspace.schedules[0]} />
          <Text variant="title">Delivery history</Text>
          {workspace.deliveries.length === 0 ? (
            <Text tone="muted">No delivery attempts yet.</Text>
          ) : (
            workspace.deliveries.map((delivery) => (
              <Card key={delivery.id}>
                <View style={styles.contentGroup}>
                  <Text weight="semibold">{`${delivery.date} · ${delivery.status} · ${delivery.attempts} attempt(s)`}</Text>
                  <Text variant="caption" tone="muted">
                    {delivery.recipients.join(', ')}
                  </Text>
                  {delivery.error ? <Text tone="error">{delivery.error}</Text> : null}
                  {delivery.status === 'failed' ? (
                    <Button
                      variant="outline"
                      loading={retryState.isLoading}
                      onPress={() => {
                        setError(null);
                        void retry(delivery.id)
                          .unwrap()
                          .catch((failure: unknown) => setError(workspaceError(failure)));
                      }}
                    >
                      Retry failed delivery
                    </Button>
                  ) : null}
                </View>
              </Card>
            ))
          )}
        </View>
      }
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
  contentGroup: { gap: t.spacing[3] },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing[2] },
  reportItem: {
    gap: t.spacing[1],
    paddingBottom: t.spacing[2],
    borderBottomWidth: 1,
    borderBottomColor: t.color.border,
  },
}));
