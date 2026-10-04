// Provider strings from stage events: `<provider>:<model>` or a bare `<provider>`.

/** The method part of a provider string, before `:`. */
export function methodOf(provider: string): string {
  return provider.split(":")[0];
}

/** The model part of a provider string, after the first `:`; empty when there is none. */
export function modelOf(provider: string): string {
  const at = provider.indexOf(":");
  return at < 0 ? "" : provider.slice(at + 1);
}

/** True when the provider that ran names a different method than the configured one. */
export function isFallback(configured: string | undefined, ran: string | undefined): boolean {
  if (!configured || !ran) return false;
  return methodOf(configured) !== methodOf(ran);
}
