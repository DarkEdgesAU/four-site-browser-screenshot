"""Rebuild Pages from retained capture artifacts; no image commits or dependencies."""

import html
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
import zipfile


CAPTURE_NAME = re.compile(r"gallery-capture-(\d+)-(\d+)\Z")
IMAGE_NAMES = {f"site-{site}.jpg" for site in range(1, 5)}
JSON_KINDS = {
    "network-address": "Network details",
    "request-response-headers": "Request and response headers",
    "browser-diagnostics": "Browser diagnostics",
}
JSON_NAMES = {f"site-{site}-{kind}.json" for site in range(1, 5) for kind in JSON_KINDS}
RETENTION_DAYS = 7


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def retained_captures(artifacts, now):
    """Ignore unrelated/expired artifacts and deduplicate re-uploaded attempts."""
    selected = {}
    for artifact in artifacts:
        match = CAPTURE_NAME.fullmatch(artifact["name"])
        if not match or artifact.get("expired"):
            continue
        created = timestamp(artifact["created_at"])
        if created <= now - timedelta(days=RETENTION_DAYS):
            continue
        if artifact.get("expires_at") and timestamp(artifact["expires_at"]) <= now:
            continue
        run_id, attempt = match.groups()
        if str(artifact.get("workflow_run", {}).get("id")) != run_id:
            raise ValueError("Capture name does not match its source workflow run")
        key = (run_id, attempt)
        if key not in selected or created > timestamp(selected[key]["created_at"]):
            selected[key] = artifact
    return sorted(selected.values(), key=lambda item: item["created_at"], reverse=True)


def capture_files_from_zip(data):
    # Never extract archive paths: accept only exact JPEG/JSON names. Older
    # screenshot-only capture bundles remain valid, without inventing their JSON.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        names = {member.filename for member in members}
        if (len(names) != len(members) or not IMAGE_NAMES <= names
                or not names <= IMAGE_NAMES | JSON_NAMES):
            raise ValueError("A capture must contain four JPEGs and only recognized per-site JSON files")
        files = {}
        for member in members:
            limit = 20 if member.filename in IMAGE_NAMES else 5
            if member.file_size > limit * 1024 * 1024:
                raise ValueError(f"Capture file exceeds its {limit} MiB limit")
            contents = archive.read(member)
            if member.filename in IMAGE_NAMES and not contents.startswith(b"\xff\xd8\xff"):
                raise ValueError("Capture contains a non-JPEG file")
            if member.filename in JSON_NAMES:
                parsed = json.loads(contents.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("Per-site JSON must contain an object")
                contents = (json.dumps(parsed, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
            files[member.filename] = contents
        return files


def site_section(site, files):
    sections = [f'<section id="site-{site}"><h2>Site {site}</h2>',
                f'<p><a href="site-{site}.jpg">Open full-size image</a></p>',
                f'<a href="site-{site}.jpg"><img src="site-{site}.jpg" width="960" '
                f'alt="Site {site} screenshot"></a>']
    for kind, title in JSON_KINDS.items():
        filename = f"site-{site}-{kind}.json"
        sections.append(f'<h3>{title}</h3>')
        if filename in files:
            # JSON remains plain text, even if a URL or header contains HTML.
            contents = html.escape(files[filename].decode('utf-8'))
            sections.append(f'<p><a href="{filename}">Open JSON file</a></p>'
                            f'<pre><code>{contents}</code></pre>')
        else:
            sections.append('<p>This capture did not include this JSON file.</p>')
    sections.append('</section>')
    return ''.join(sections)


def document(title, body):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1080px;margin:32px auto;padding:0 20px;background:#f8fafc;color:#172033}}a{{color:#1745ab}}img{{max-width:100%;height:auto;border:1px solid #ccd5e2}}section{{background:white;padding:20px;margin:24px 0;border-radius:8px}}li{{margin:12px 0}}small{{color:#465166}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f7;padding:16px;border-radius:6px;font-size:13px}}nav a{{margin-right:16px}}</style>
</head><body>{body}</body></html>
"""


def build_pages(output, artifacts, download, repository):
    output = Path(output)
    # Fail closed rather than retaining stale directories from a previous build.
    if output.exists():
        raise ValueError("Pages output must be a fresh directory")
    output.mkdir(parents=True)
    links = []
    for artifact in artifacts:
        run_id, attempt = CAPTURE_NAME.fullmatch(artifact["name"]).groups()
        relative = f"runs/{run_id}/attempt-{attempt}"
        files = capture_files_from_zip(download(artifact))
        directory = output / relative
        directory.mkdir(parents=True)
        for filename, contents in files.items():
            (directory / filename).write_bytes(contents)
        title = f"Run {run_id} · attempt {attempt}"
        created = html.escape(artifact["created_at"])
        source = f"https://github.com/{repository}/actions/runs/{run_id}/attempts/{attempt}"
        sections = "".join(site_section(site, files) for site in range(1, 5))
        body = (f'<nav><a href="../../../">All retained runs</a></nav>'
                f'<h1>{html.escape(title)}</h1><p>Captured {created} (UTC).</p>'
                f'<p><a href="{html.escape(source, quote=True)}">Source Actions run</a></p>'
                '<p>Retained for seven days. Images in this folder belong to this capture only.</p>'
                '<p>JSON is shown in full with the capture’s existing redactions. '
                'Browser diagnostic collection has per-event limits.</p>'
                '<nav aria-label="Requests">' + ''.join(f'<a href="#site-{site}">Site {site}</a>' for site in range(1, 5)) + '</nav>'
                + sections)
        (directory / "index.html").write_text(document(title, body), encoding="utf-8")
        links.append(f'<li><a href="{relative}/">{html.escape(title)}</a> — <small>{created}</small></li>')
    body = ('<h1>Browser screenshot galleries</h1>'
            '<p>Each run and attempt has its own gallery. Open a run to view all four images.</p>'
            '<p>Captures are retained for seven days. Cleanup runs daily and after each new capture; '
            'expired galleries disappear on the next successful deployment.</p>')
    body += '<ul>' + ''.join(links) + '</ul>' if links else '<p>No retained captures are available.</p>'
    (output / "index.html").write_text(document("Browser screenshot galleries", body), encoding="utf-8")
    (output / ".nojekyll").touch()


def gh_api(*args):
    for attempt in range(3):
        try:
            return subprocess.check_output(["gh", "api", *args])
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    pages = json.loads(gh_api(f"repos/{repository}/actions/artifacts?per_page=100", "--paginate", "--slurp"))
    captures = retained_captures(
        [artifact for page in pages for artifact in page["artifacts"]],
        datetime.now(timezone.utc),
    )
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        expected = f'gallery-capture-{os.environ["GITHUB_RUN_ID"]}-{os.environ["CAPTURE_ATTEMPT"]}'
        if not any(capture["name"] == expected for capture in captures):
            raise ValueError("Current capture is missing; refusing to publish misleading gallery links")
    build_pages("pages", captures,
                lambda artifact: gh_api(f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip'),
                repository)
    print(f"Built {len(captures)} retained galleries")


if __name__ == "__main__":
    main()
