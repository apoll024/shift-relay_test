import { ScreenState } from '@/features/common/ScreenState';

export function SharedModeRequired() {
  return (
    <ScreenState
      title="Shared workspace required"
      message="Tasks and scheduled reports are available when this app is connected to your team's shared service. This session uses fictional demo data."
    />
  );
}
