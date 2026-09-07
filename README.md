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

## Docker

The Docker image is based on the official Playwright image and includes Chromium, browser dependencies, Node.js, and the test project:

```powershell
docker build -t darkedges/four-site-browser-screenshot:latest .
docker run --rm `
  -e SITE_URLS='https://signon.sso.cba/identity/.well-known/openid-configuration,https://signon.sso.cba/pa/heartbeat.pf,https://proxy.sso.cba/pa/heartbeat.pf,https://radar.cloudflare.com/ip' `
  -v "${PWD}/artifacts:/app/test-results" `
  darkedges/four-site-browser-screenshot:latest
```

The container runs Chromium headlessly and writes screenshots, `network-addresses.json`, and `request-response-headers.json` to `test-results/site-screenshots/`. Each site uses a new browser process and context with service workers, HTTP cache, cookies, and browser-level DNS cache disabled or cleared; requests also carry `Cache-Control: no-cache, no-store`. Request and response headers are uploaded with sensitive values redacted.

## GitHub Actions

The `Four-site Playwright test` workflow is manually runnable with `workflow_dispatch` on the dedicated ARC scale set labeled `four-site-runner-set`. Add these repository secrets before running it:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

The workflow pulls the published public image `docker.io/darkedges/four-site-browser-screenshot:latest`, runs the test on the ARC runner, uploads each screenshot as an individual Actions artifact (`site-1-screenshot` through `site-4-screenshot`), uploads the network/header data separately, and adds the redacted headers to the job summary. Docker Hub credentials are not required for this workflow.

For a visible run, use `npm run test:headed` after setting `SITE_URLS`. The test launches four separate Chromium processes so each site appears in its own browser window.
