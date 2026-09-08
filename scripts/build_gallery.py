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


def images_from_zip(data):
    # Never extract archive paths: only four exact expected JPEG names are accepted.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) != 4 or {member.filename for member in members} != IMAGE_NAMES:
            raise ValueError("A capture must contain exactly site-1.jpg through site-4.jpg")
        images = {}
        for member in members:
            if member.file_size > 20 * 1024 * 1024:
                raise ValueError("Screenshot exceeds the 20 MiB per-image limit")
            contents = archive.read(member)
            if not contents.startswith(b"\xff\xd8\xff"):
                raise ValueError("Capture contains a non-JPEG file")
            images[member.filename] = contents
        return images


def document(title, body):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1080px;margin:32px auto;padding:0 20px;background:#f8fafc;color:#172033}}a{{color:#1745ab}}img{{max-width:100%;height:auto;border:1px solid #ccd5e2}}section{{background:white;padding:20px;margin:24px 0;border-radius:8px}}li{{margin:12px 0}}small{{color:#465166}}</style>
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
        images = images_from_zip(download(artifact))
        directory = output / relative
        directory.mkdir(parents=True)
        for filename, contents in images.items():
            (directory / filename).write_bytes(contents)
        title = f"Run {run_id} · attempt {attempt}"
        created = html.escape(artifact["created_at"])
        source = f"https://github.com/{repository}/actions/runs/{run_id}/attempts/{attempt}"
        sections = "".join(
            f'<section id="site-{site}"><h2>Site {site}</h2>'
            f'<p><a href="site-{site}.jpg">Open full-size image</a></p>'
            f'<a href="site-{site}.jpg"><img src="site-{site}.jpg" width="960" '
            f'alt="Site {site} screenshot"></a></section>'
            for site in range(1, 5)
        )
        body = (f'<nav><a href="../../../">All retained runs</a></nav>'
                f'<h1>{html.escape(title)}</h1><p>Captured {created} (UTC).</p>'
                f'<p><a href="{html.escape(source, quote=True)}">Source Actions run</a></p>'
                '<p>Retained for seven days. Images in this folder belong to this capture only.</p>'
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
