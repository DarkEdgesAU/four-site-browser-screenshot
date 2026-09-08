import type { Page } from '@playwright/test';

// Keep request destinations useful without publishing query values or challenge tokens.
export function safeUrl(value: string): string {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) return `${url.protocol}[omitted]`;
    const pathname = url.pathname.split('/').map(part =>
      part.length > 40 ? '[opaque-segment]' : part).join('/');
    return `${url.origin}${pathname}${url.search ? '?[redacted]' : ''}`;
  } catch {
    return '[unavailable URL]';
  }
}

export function safeMessage(value: string): string {
  return value
    .replace(/https?:\/\/[^\s<>"']+/g, safeUrl)
    .replace(/\b(Bearer|Basic)\s+[^\s,;]+/gi, '$1 [redacted]')
    .replace(/\b(authorization|cookie|token|api[-_]?key|password)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .replace(/[A-Za-z0-9_+\/=.-]{80,}/g, '[opaque-value]')
    .slice(0, 2000);
}

export async function collectDiagnostics(page: Page, headless: boolean) {
  const report = {
    startedAt: new Date().toISOString(),
    finishedAt: '',
    headless,
    extensionsConfigured: false,
    serviceWorkers: 'block',
    mainNavigationError: null as string | null,
    droppedEvents: 0,
    responses: [] as object[],
    failedRequests: [] as object[],
    console: [] as object[],
    pageErrors: [] as object[],
    networkFailures: [] as object[],
  };
  const append = (target: object[], value: object, limit = 100) => {
    if (target.length < limit) target.push({ at: new Date().toISOString(), ...value });
    else report.droppedEvents++;
  };
  page.on('response', response => {
    const headers = response.headers();
    append(report.responses, {
      url: safeUrl(response.url()), status: response.status(),
      resourceType: response.request().resourceType(),
      server: headers.server, contentType: headers['content-type'],
      cloudflareMitigation: headers['cf-mitigated'], rayId: headers['cf-ray'],
    }, 400);
  });
  page.on('requestfailed', request => append(report.failedRequests, {
    url: safeUrl(request.url()), resourceType: request.resourceType(),
    error: safeMessage(request.failure()?.errorText ?? 'Unknown failure'),
  }));
  page.on('console', message => {
    if (!['warning', 'error'].includes(message.type())) return;
    append(report.console, {
      type: message.type(), text: safeMessage(message.text()),
      source: safeUrl(message.location().url), line: message.location().lineNumber,
    });
  });
  page.on('pageerror', error => append(report.pageErrors, { message: safeMessage(error.message) }));
  const session = await page.context().newCDPSession(page);
  const requests = new Map<string, string>();
  session.on('Network.requestWillBeSent', event => requests.set(event.requestId, safeUrl(event.request.url)));
  session.on('Network.loadingFinished', event => requests.delete(event.requestId));
  session.on('Network.loadingFailed', event => {
    append(report.networkFailures, {
      url: requests.get(event.requestId) ?? '[unmapped request]',
      resourceType: event.type, error: safeMessage(event.errorText),
      blockedReason: event.blockedReason, canceled: event.canceled,
      corsError: event.corsErrorStatus?.corsError,
    });
    requests.delete(event.requestId);
  });
  await session.send('Network.enable');
  return report;
}
