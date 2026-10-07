let operationalTimezone: string | null = null;

export function configureOperationalTimezone(timezone: string) {
  // Validate the server's timezone before using it in daily sheet lookups.
  new Intl.DateTimeFormat('en-CA', { timeZone: timezone }).format(new Date());
  operationalTimezone = timezone;
}

export function operationalDateKey(): string | null {
  if (!operationalTimezone) return null;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: operationalTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((value) => value.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
