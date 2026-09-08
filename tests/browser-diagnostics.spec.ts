import { test, expect, chromium } from '@playwright/test';
import { collectDiagnostics, safeMessage, safeUrl } from './browser-diagnostics';

test('diagnostic sanitization removes URL credentials and query values', () => {
  expect(safeUrl('https://user:password@example.com/script?token=secret#fragment'))
    .toBe('https://example.com/script?[redacted]');
  expect(safeUrl('data:text/plain,private')).toBe('data:[omitted]');
  expect(safeMessage('Failed https://example.com/a?token=secret Bearer credential'))
    .toBe('Failed https://example.com/a?[redacted] Bearer [redacted]');
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
