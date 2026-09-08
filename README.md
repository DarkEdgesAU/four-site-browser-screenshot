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

The container runs Chromium headlessly and writes screenshots plus `site-<n>-network-address.json` and `site-<n>-request-response-headers.json` files to `test-results/site-screenshots/`. Each site uses a new browser process and context with service workers blocked, HTTP cache disabled through CDP, and browser cache/cookies cleared. Top-level navigations carry `Cache-Control: no-cache, no-store` and `Pragma: no-cache`; these headers are deliberately not injected into cross-origin subresources because they can trigger CORS preflights and prevent challenge scripts from loading. A new browser process avoids reusing its DNS cache, but does not flush Kubernetes or upstream DNS caches. Request and response headers are uploaded with sensitive values redacted.

## GitHub Actions

The `Four-site Playwright test` workflow is manually runnable with `workflow_dispatch` on the dedicated ARC scale set labeled `four-site-runner-set`. Docker Hub credentials are not required: the workflow pulls the public image `docker.io/darkedges/four-site-browser-screenshot:latest` and runs the checked-out test code on the ARC runner.

Open the run's **Summary** page to see per-site network JSON, collapsible redacted request/response headers, and direct links to the run's gallery and four individual JPEGs. There are no inline images in the Actions summary, so it does not request screenshots through `camo.githubusercontent.com`. The gallery uses relative image URLs on `darkedgesau.github.io`, which must be permitted by your proxy. Step logs display source text; rendered content is on the Summary page. Each JSON code fence is explicitly separated from the file contents by a newline, including when the JSON file has no trailing newline.

The four JPEGs (`site-1.jpg` through `site-4.jpg`) and eight JSON files remain separate downloadable artifacts retained for seven days. An additional `gallery-capture-<run-id>-<attempt>` ZIP artifact stores the four images for rebuilding the site, also for seven days. The Pages deployment bundle is retained for one day. Screenshots are never committed to Git history.

Each capture has a stable folder: `runs/<run-id>/attempt-<attempt>/`, containing `index.html` and four JPEGs. New runs and reruns do not overwrite older captures. The root gallery lists retained runs. This starts with runs using this workflow version; earlier latest-only deployments are not automatically migrated.

On every capture and daily at 16:17 UTC, the GitHub-hosted deployment job rebuilds the entire Pages site from unexpired capture artifacts created within the last seven days. Scheduled runs only rebuild the gallery; they do not run browsers on ARC. Older folders are omitted from the next successful deployment, and an empty index is published when nothing remains. Retention cleanup therefore has daily granularity and depends on successful workflow execution; expiring an artifact alone does not delete a deployed page. Expired run links return 404 after cleanup.

The capture bundle uploads after a successful capture even if an individual artifact upload failed. Deployment depends on that bundle being available; unrelated upload failures still leave the workflow failed. Runs are serialized to prevent concurrent Pages updates. If a retained bundle cannot be downloaded or validated, deployment fails and preserves the previous site rather than silently losing history.

The builder uses Python's standard library and the GitHub CLI available on the hosted runner. Its retention, per-attempt isolation, and ZIP validation checks can be run locally with `python -m unittest discover -s scripts -p 'test_*.py'`.

## Browser diagnostics

Each capture also uploads `site-<n>-browser-diagnostics.json` for seven days. These record response statuses and Cloudflare challenge markers, failed requests, console warnings/errors, page exceptions, and Chromium network blocking reasons. Collection starts before navigation and reports are written before browser shutdown, including on navigation failure. Events are bounded and `droppedEvents` indicates truncation. URL credentials, query values, long opaque path segments, and common credential patterns in messages are redacted; console message redaction is best-effort. No request/response bodies or console object arguments are collected. Diagnostic JSON is kept in Actions artifacts, not the public Pages gallery.

A challenge response is not proof of a network block: inspect the challenge script/frame requests and their errors. Cloudflare's production challenges do not support automated Playwright clients. Expected challenge probe failures and Private Access Token 401 responses should not automatically be treated as the cause. The collector does not attempt to solve or bypass a challenge.

For a visible run, use `npm run test:headed` after setting `SITE_URLS`. The test launches four separate Chromium processes so each site appears in its own browser window.
