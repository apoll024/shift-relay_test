import { Stack } from 'expo-router';
import { MenuButton } from '@/features/shell/ShellMenu';
import { useStackScreenOptions } from '@/features/shell/useStackScreenOptions';

export default function ReportsLayout() {
  return (
    <Stack screenOptions={useStackScreenOptions()}>
      <Stack.Screen name="index" options={{ title: 'Reports', headerLeft: () => <MenuButton /> }} />
    </Stack>
  );
}
