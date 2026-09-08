import { test, chromium, type Browser, type Page } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs/promises';
import { collectDiagnostics, safeMessage } from './browser-diagnostics';

const defaultSites = [
  'https://signon.sso.cba/identity/.well-known/openid-configuration',
  'https://signon.sso.cba/pa/heartbeat.ping',
  'https://proxy.sso.cba/pa/heartbeat.ping',
  'https://radar.cloudflare.com/ip',
];

function redactHeaders(headers: Record<string, string> | undefined): Record<string, string> {
  const sensitiveHeader = /authorization|cookie|set-cookie|proxy-authorization|api[-_]key/i;
  return Object.fromEntries(
    Object.entries(headers ?? {}).map(([name, value]) => [
      name,
      sensitiveHeader.test(name) ? '[REDACTED]' : value,
    ]),
  );
}

function getSites(): string[] {
  const configured = process.env.SITE_URLS
    ?.split(',')
    .map((site) => site.trim())
    .filter(Boolean);

  const sites = configured ?? defaultSites;
  if (sites.length !== 4) {
    throw new Error(
      `Expected exactly 4 site URLs. Received ${sites.length}. ` +
        'Set SITE_URLS to four comma-separated URLs.',
    );
  }

  return sites;
}

test('opens four browser windows and captures a screenshot for each site', async () => {
  const sites = getSites();
  const headless = process.env.HEADLESS === 'true';
  const screenshotDirectory = path.resolve('test-results', 'site-screenshots');
  await fs.mkdir(screenshotDirectory, { recursive: true });

  const browsers: Browser[] = [];
  const pages: Page[] = [];
  const diagnostics: Awaited<ReturnType<typeof collectDiagnostics>>[] = [];
  const networkAddresses: Array<{
    site: string;
    httpStatus: number | null;
    ipAddress: string | null;
    port: number | null;
  }> = [];
  const requestResponses: Array<{
    site: string;
    httpStatus: number | null;
    ipAddress: string | null;
    port: number | null;
    requestHeaders: Record<string, string>;
    responseHeaders: Record<string, string>;
  }> = [];

  try {
    for (const site of sites) {
      const browser = await chromium.launch({
        headless,
        devtools: !headless,
        args: [
          '--disable-http-cache',
          '--disable-dns-cache',
          '--disk-cache-size=0',
          '--media-cache-size=0',
        ],
      });
      const context = await browser.newContext({ serviceWorkers: 'block' });
      await context.setExtraHTTPHeaders({
        'cache-control': 'no-cache, no-store',
        pragma: 'no-cache',
      });
      const page = await context.newPage({ viewport: { width: 1440, height: 900 } });
      const cdp = await context.newCDPSession(page);
      await cdp.send('Network.clearBrowserCache').catch(() => undefined);
      await cdp.send('Network.clearBrowserCookies').catch(() => undefined);
      browsers.push(browser);
      pages.push(page);
      const diagnostic = await collectDiagnostics(page, headless);
      diagnostics.push(diagnostic);

      const response = await page.goto(site, { waitUntil: 'domcontentloaded' }).catch(error => {
        diagnostic.mainNavigationError = safeMessage(String(error));
        throw error;
      });
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined);
      await page.waitForTimeout(1_000);
      const serverAddress = await response?.serverAddr();
      const request = response?.request();
      const networkAddress = {
        site,
        httpStatus: response?.status() ?? null,
        ipAddress: serverAddress?.ipAddress ?? null,
        port: serverAddress?.port ?? null,
      };
      networkAddresses.push(networkAddress);
      console.log(
        `${site} [HTTP ${networkAddress.httpStatus ?? 'unknown'}] -> ` +
          `${networkAddress.ipAddress ?? 'IP unavailable'}:${networkAddress.port ?? ''}`,
      );

      await page.evaluate(
        ({ ipAddress, port, httpStatus }) => {
          const overlay = document.createElement('div');
          overlay.textContent =
            `Request IP: ${ipAddress ?? 'unavailable'}:${port ?? ''} | ` +
            `HTTP ${httpStatus ?? 'unknown'}`;
          overlay.style.cssText = [
            'position: fixed',
            'top: 12px',
            'right: 12px',
            'z-index: 2147483647',
            'padding: 10px 14px',
            'border-radius: 6px',
            'background: #111827',
            'color: #f9fafb',
            'font: 600 14px/1.2 Arial, sans-serif',
            'box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35)',
          ].join(';');
          document.documentElement.appendChild(overlay);
        },
        networkAddress,
      );
      requestResponses.push({
        ...networkAddress,
        requestHeaders: redactHeaders(await request?.allHeaders()),
        responseHeaders: redactHeaders(await response?.allHeaders()),
      });
    }

    for (let index = 0; index < pages.length; index += 1) {
      await pages[index].screenshot({
        path: path.join(screenshotDirectory, `site-${index + 1}.jpg`),
        type: 'jpeg',
        quality: 70,
        fullPage: true,
      });
    }

    for (let index = 0; index < networkAddresses.length; index += 1) {
      await fs.writeFile(
        path.join(screenshotDirectory, `site-${index + 1}-network-address.json`),
        JSON.stringify(networkAddresses[index], null, 2),
        'utf8',
      );
      await fs.writeFile(
        path.join(screenshotDirectory, `site-${index + 1}-request-response-headers.json`),
        JSON.stringify(requestResponses[index], null, 2),
        'utf8',
      );
    }
  } finally {
    // Write before closing browsers so shutdown cancellations do not pollute the report.
    try {
      await Promise.all(diagnostics.map((diagnostic, index) => {
        diagnostic.finishedAt = new Date().toISOString();
        return fs.writeFile(
          path.join(screenshotDirectory, `site-${index + 1}-browser-diagnostics.json`),
          JSON.stringify(diagnostic, null, 2) + '\n', 'utf8',
        );
      }));
    } finally {
      await Promise.all(browsers.map((browser) => browser.close()));
    }
  }
});
