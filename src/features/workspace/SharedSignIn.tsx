import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Button, Card, Input, makeStyles, Text } from '@/design-system';
import { sharedSignIn } from '@/features/auth/sessionSlice';
import { useAppDispatch } from '@/store/hooks';

import { sharedFetch, workspaceError } from './client';
import type { WorkspaceUser } from './types';
import { configureOperationalTimezone } from './operationalClock';

export function SharedSignIn() {
  const styles = useStyles();
  const dispatch = useAppDispatch();
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signIn = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await sharedFetch('/api/session', token.trim());
      const result: unknown = await response.json();
      if (!response.ok) throw new Error(workspaceError(result));
      const user = result as WorkspaceUser;
      if (!['jordan', 'avery', 'elena'].includes(user.id))
        throw new Error('The server returned an unsupported account.');
      if (user.timezone) configureOperationalTimezone(user.timezone);
      dispatch(sharedSignIn({ user, token: token.trim() }));
      setToken('');
      router.replace('/');
    } catch (failure) {
      setError(workspaceError(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <View style={styles.content}>
        <Text variant="title">Shared workspace</Text>
        <Text tone="muted">
          Sign in with the private access token supplied by your workspace administrator.
        </Text>
        <Input
          label="Access token"
          value={token}
          onChangeText={setToken}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          testID="shared-token"
        />
        {error ? (
          <View accessibilityLiveRegion="polite">
            <Text tone="error">{error}</Text>
          </View>
        ) : null}
        <Button
          onPress={() => void signIn()}
          loading={busy}
          disabled={!token.trim()}
          testID="shared-sign-in"
        >
          Sign in
        </Button>
      </View>
    </Card>
  );
}

const useStyles = makeStyles((t) => ({ content: { gap: t.spacing[3] } }));
