# Four-site browser screenshot test

This project opens four visible Chromium browser windows with DevTools open, navigates each one to a different URL, waits for the page to settle, and saves one full-page screenshot per site under `test-results/site-screenshots/`. It also records each site's main document HTTP status, server IP, port, and redacted request/response headers in per-site JSON files.

The default sites are:

1. `https://signon.sso.cba/identity/.well-known/openid-configuration`
2. `https://signon.sso.cba/pa/heartbeat.ping`
3. `https://proxy.sso.cba/pa/heartbeat.ping`
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
  -e SITE_URLS='https://signon.sso.cba/identity/.well-known/openid-configuration,https://signon.sso.cba/pa/heartbeat.ping,https://proxy.sso.cba/pa/heartbeat.ping,https://radar.cloudflare.com/ip' `
  -v "${PWD}/artifacts:/app/test-results" `
  darkedges/four-site-browser-screenshot:latest
```

The container runs Chromium headlessly and writes screenshots plus `site-<n>-network-address.json` and `site-<n>-request-response-headers.json` files to `test-results/site-screenshots/`. Each site uses a new browser process and context with service workers, HTTP cache, cookies, and browser-level DNS cache disabled or cleared; requests also carry `Cache-Control: no-cache, no-store`. Request and response headers are uploaded with sensitive values redacted.

## GitHub Actions

The `Four-site Playwright test` workflow is manually runnable with `workflow_dispatch` on the dedicated ARC scale set labeled `four-site-runner-set`. Docker Hub credentials are not required: the workflow pulls the public image `docker.io/darkedges/four-site-browser-screenshot:latest` and runs the checked-out test code on the ARC runner.

Open the run's **Summary** page to see per-site network JSON, collapsible redacted request/response headers, and four individual image previews at 480 pixels wide. Step logs display source text; rendered content is on the Summary page. Each JSON code fence is explicitly separated from the file contents by a newline, including when the JSON file has no trailing newline.

The four JPEGs (`site-1.jpg` through `site-4.jpg`) and eight JSON files are separate downloadable artifacts retained for seven days. The Pages deployment bundle is retained for one day. GitHub Pages hosts only the latest four images and a gallery identifying their source run; each deployment replaces that content without committing images to Git history. The hosted site itself does not expire after one day.

Inline previews are labelled **Latest published screenshots** because their URLs are reused. A run/attempt query parameter prevents reuse of the previous run's image-proxy cache entry, but does not preserve historical images. Use each run's own artifacts for historical evidence. Full-size image links and the latest gallery link are included in the summary.

Pages preparation and upload run after a successful capture even if an individual artifact upload failed. The deployment job checks the Pages upload outcome rather than requiring every artifact upload to succeed; upload failures still leave the workflow failed. Runs are serialized to prevent concurrent Pages updates. A capture or Pages upload failure leaves the previous published gallery in place.

For a visible run, use `npm run test:headed` after setting `SITE_URLS`. The test launches four separate Chromium processes so each site appears in its own browser window.
