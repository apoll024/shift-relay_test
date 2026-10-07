import { useState } from 'react';
import { View } from 'react-native';

import { Button, Card, Input, makeStyles, Text } from '@/design-system';
import { selectSharedUser } from '@/features/auth/sessionSlice';
import { useAppSelector } from '@/store/hooks';
import { workspaceError } from '@/features/workspace/client';
import type { ReportSchedule } from '@/features/workspace/types';
import { useSaveScheduleMutation } from '@/features/workspace/workspaceApi';

export function ScheduleEditor({ schedule }: { schedule: ReportSchedule | undefined }) {
  const styles = useStyles();
  const user = useAppSelector(selectSharedUser);
  const [title, setTitle] = useState(schedule?.title ?? 'Morning operations report');
  const [timezone, setTimezone] = useState(
    schedule?.timezone ?? user?.timezone ?? 'America/Los_Angeles',
  );
  const [start, setStart] = useState(schedule?.overnightStart ?? '17:00');
  const [end, setEnd] = useState(schedule?.overnightEnd ?? '08:00');
  const [deliveryTime, setDeliveryTime] = useState(schedule?.deliveryTime ?? '08:05');
  const [recipients, setRecipients] = useState(schedule?.recipients.join(', ') ?? '');
  const [enabled, setEnabled] = useState(schedule?.enabled ?? false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveSchedule, state] = useSaveScheduleMutation();
  const save = async () => {
    setError(null);
    setMessage(null);
    try {
      await saveSchedule({
        id: 'daily',
        title,
        timezone,
        overnightStart: start,
        overnightEnd: end,
        deliveryTime,
        recipients: recipients.split(/[,;\s]+/).filter(Boolean),
        enabled,
        updatedAt: schedule?.updatedAt ?? '',
      }).unwrap();
      setMessage(
        enabled
          ? 'Daily delivery enabled. The server will generate and email the report at the configured local time.'
          : 'Schedule saved with delivery disabled.',
      );
    } catch (failure) {
      setError(workspaceError(failure));
    }
  };
  return (
    <Card testID="schedule-editor">
      <View style={styles.content}>
        <Text variant="title">Daily email schedule</Text>
        <Text tone="muted">
          The shared service sends reports even when the app is closed. Your administrator
          configures the mail server separately.
        </Text>
        <Input label="Scheduled report title" value={title} onChangeText={setTitle} />
        <Input
          label="Schedule timezone"
          value={timezone}
          onChangeText={setTimezone}
          autoCapitalize="none"
        />
        <Input label="Scheduled overnight start (HH:MM)" value={start} onChangeText={setStart} />
        <Input label="Scheduled overnight end (HH:MM)" value={end} onChangeText={setEnd} />
        <Input
          label="Daily delivery time (HH:MM)"
          value={deliveryTime}
          onChangeText={setDeliveryTime}
          testID="schedule-time"
        />
        <Input
          label="Recipient email addresses"
          value={recipients}
          onChangeText={setRecipients}
          autoCapitalize="none"
          autoCorrect={false}
          helperText="Separate addresses with commas. Saving an enabled schedule authorizes daily delivery to these recipients."
          testID="schedule-recipients"
        />
        <Button
          variant={enabled ? 'secondary' : 'outline'}
          onPress={() => setEnabled(!enabled)}
          accessibilityLabel="Toggle daily email delivery"
          testID="schedule-enabled"
        >
          {enabled ? 'Delivery enabled' : 'Delivery disabled'}
        </Button>
        {error ? (
          <View accessibilityLiveRegion="polite">
            <Text tone="error">{error}</Text>
          </View>
        ) : null}
        {message ? (
          <View accessibilityLiveRegion="polite">
            <Text>{message}</Text>
          </View>
        ) : null}
        <Button
          variant="outline"
          onPress={() => void save()}
          loading={state.isLoading}
          testID="save-schedule"
        >
          Save schedule
        </Button>
      </View>
    </Card>
  );
}

const useStyles = makeStyles((t) => ({ content: { gap: t.spacing[3] } }));
