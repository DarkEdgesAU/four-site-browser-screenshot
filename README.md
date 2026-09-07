# Four-site browser screenshot test

This project opens four visible Chromium browser windows with DevTools open, navigates each one to a different URL, waits for the page to settle, and saves one full-page screenshot per site under `test-results/site-screenshots/`. It also records the main document HTTP status, server IP, and port in `network-addresses.json` and prints them in the test output.

The default sites are:

1. `https://signon.sso.cba/identity/.well-known/openid-configuration`
2. `https://signon.sso.cba/pa/heartbeat.pf`
3. `https://proxy.sso.cba/pa/heartbeat.pf`
4. `https://radar.cloudflare.com/ip`

Run the test with the defaults:

```powershell
npm install
npx playwright install chromium
npm test
```

You can override the sites by supplying all four at runtime as a comma-separated `SITE_URLS` value.

DevTools opens automatically for each browser window. Playwright can read and record the response IP through its API, but Chrome DevTools is a separate UI, so the test does not programmatically select the Network request or expand its Remote address details. Cloudflare Radar may return an anti-bot verification page (HTTP 403) in automated Chromium; in that case the screenshot will show the verification page rather than Radar's IP data.

For a visible run, use `npm run test:headed` after setting `SITE_URLS`. The test launches four separate Chromium processes so each site appears in its own browser window.
