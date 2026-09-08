import type { Page } from '@playwright/test';

export async function configureFreshRequests(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  await cdp.send('Network.clearBrowserCache');
  await cdp.send('Network.clearBrowserCookies');
  await page.route('**/*', route => {
    const request = route.request();
    // Cache headers on cross-origin scripts trigger CORS preflights. Apply them
    // only to top-level navigations; CDP disables the cache for all resources.
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
      return route.continue({ headers: {
        ...request.headers(), 'cache-control': 'no-cache, no-store', pragma: 'no-cache',
      } });
    }
    return route.continue();
  });
}
