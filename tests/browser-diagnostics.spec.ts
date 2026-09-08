import { test, expect, chromium } from '@playwright/test';
import { collectDiagnostics, safeMessage, safeUrl } from './browser-diagnostics';
import { configureFreshRequests } from './fresh-requests';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';

test('diagnostic sanitization removes URL credentials and query values', () => {
  expect(safeUrl('https://user:password@example.com/script?token=secret#fragment'))
    .toBe('https://example.com/script?[redacted]');
  expect(safeUrl('data:text/plain,private')).toBe('data:[omitted]');
  expect(safeMessage('Failed https://example.com/a?token=secret Bearer credential'))
    .toBe('Failed https://example.com/a?[redacted] Bearer [redacted]');
});

test('fresh navigation headers do not trigger cross-origin script preflights', async () => {
  const seen: Array<{ method?: string; cache?: string; pragma?: string }> = [];
  const assetServer = createServer((request, response) => {
    seen.push({ method: request.method, cache: request.headers['cache-control'], pragma: request.headers.pragma });
    response.setHeader('Access-Control-Allow-Origin', '*');
    response.setHeader('Content-Type', 'application/javascript');
    response.end('window.challengeScriptLoaded = true;');
  });
  await new Promise<void>(resolve => assetServer.listen(0, '127.0.0.1', resolve));
  const assetPort = (assetServer.address() as AddressInfo).port;
  let navigationHeaders: { cache?: string; pragma?: string } = {};
  const mainServer = createServer((request, response) => {
    navigationHeaders = { cache: request.headers['cache-control'], pragma: request.headers.pragma };
    response.setHeader('Content-Type', 'text/html');
    response.end(`<script crossorigin="anonymous" src="http://127.0.0.1:${assetPort}/challenge.js"></script>`);
  });
  await new Promise<void>(resolve => mainServer.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await configureFreshRequests(page);
    await page.goto(`http://127.0.0.1:${(mainServer.address() as AddressInfo).port}/`);
    expect(await page.evaluate(() => (window as any).challengeScriptLoaded)).toBe(true);
    expect(navigationHeaders).toEqual({ cache: 'no-cache, no-store', pragma: 'no-cache' });
    // Chromium may add its own no-cache headers. Those are browser-managed and
    // do not cause the author-header preflight introduced by setExtraHTTPHeaders.
    expect(seen).toHaveLength(1);
    expect(seen[0].method).toBe('GET');
    expect(seen[0].cache).not.toBe('no-cache, no-store');
  } finally {
    await browser.close();
    await Promise.all([new Promise<void>(resolve => mainServer.close(() => resolve())),
      new Promise<void>(resolve => assetServer.close(() => resolve()))]);
  }
});

test('records browser failures and console errors before navigation', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const report = await collectDiagnostics(page, true);
    await page.route('https://diagnostics.example/**', route => route.abort('blockedbyclient'));
    const failed = page.waitForEvent('requestfailed');
    await page.setContent(`<script>
      console.error('diagnostic error token=synthetic-secret');
      fetch('https://diagnostics.example/script?token=synthetic-secret').catch(() => {});
    </script>`);
    await failed;
    expect(report.failedRequests).toEqual(expect.arrayContaining([
      expect.objectContaining({ url: 'https://diagnostics.example/script?[redacted]', error: expect.stringContaining('net::ERR_BLOCKED_BY_CLIENT') }),
    ]));
    expect(report.console).toEqual(expect.arrayContaining([
      expect.objectContaining({ text: 'diagnostic error token=[redacted]' }),
    ]));
    expect(JSON.stringify(report)).not.toContain('synthetic-secret');
  } finally {
    await browser.close();
  }
});
