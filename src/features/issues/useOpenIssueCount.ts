import { useGetIssuesQuery } from '@/features/logs/logsApi';
import { selectDemoAccountId } from '@/features/auth/sessionSlice';
import { sharedMode } from '@/features/workspace/client';
import { useAppSelector } from '@/store/hooks';

/** Open issues right now, for badges outside the Issues screen. */
export function useOpenIssueCount(): number {
  const accountId = useAppSelector(selectDemoAccountId);
  const { data } = useGetIssuesQuery(undefined, {
    skip: !accountId,
    pollingInterval: sharedMode ? 15_000 : 0,
  });
  return data?.filter((issue) => issue.status === 'open').length ?? 0;
}
