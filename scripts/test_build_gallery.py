import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
import zipfile

from build_gallery import build_pages, capture_files_from_zip, retained_captures


def capture(run, attempt, created, expired=False):
    return {"id": run * 10 + attempt, "name": f"gallery-capture-{run}-{attempt}",
            "created_at": created, "expired": expired, "workflow_run": {"id": run}}


def archive(value=b"\xff\xd8\xffcapture", names=None, extra=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        for name in names or [f"site-{site}.jpg" for site in range(1, 5)]:
            output.writestr(name, value)
        for name, contents in (extra or {}).items():
            output.writestr(name, contents)
    return data.getvalue()


class GalleryTests(unittest.TestCase):
    def test_retention_boundary_expiration_and_unrelated_artifacts(self):
        now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        keep = capture(3, 1, "2026-09-07T00:00:00Z")
        artifacts = [keep, capture(1, 1, "2026-09-01T00:00:00Z"),
                     capture(2, 1, "2026-09-06T00:00:00Z", expired=True),
                     {"name": "github-pages"}]
        self.assertEqual(retained_captures(artifacts, now), [keep])

    def test_runs_and_attempts_keep_distinct_images_and_relative_links(self):
        captures = [capture(22, 2, "2026-09-08T00:00:00Z"),
                    capture(22, 1, "2026-09-07T00:00:00Z"),
                    capture(21, 1, "2026-09-06T00:00:00Z")]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            build_pages(output, captures, lambda item: archive(b"\xff\xd8\xff" + item["name"].encode()), "org/repo")
            self.assertEqual(len(list(output.glob("runs/*/attempt-*/index.html"))), 3)
            first = output / "runs/22/attempt-1/site-1.jpg"
            second = output / "runs/22/attempt-2/site-1.jpg"
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            page = (second.parent / "index.html").read_text(encoding="utf-8")
            self.assertIn('src="site-1.jpg"', page)
            self.assertNotIn("camo.githubusercontent.com", page)
            self.assertIn('href="runs/21/attempt-1/"', (output / "index.html").read_text())

    def test_empty_retention_publishes_empty_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            build_pages(output, [], lambda _: self.fail("No downloads expected"), "org/repo")
            self.assertIn("No retained captures", (output / "index.html").read_text())
            self.assertFalse((output / "runs").exists())

    def test_rejects_paths_missing_images_and_wrong_content(self):
        for data in [archive(names=["../site-1.jpg", "site-2.jpg", "site-3.jpg", "site-4.jpg"]),
                     archive(names=["site-1.jpg"]), archive(value=b"<html>not an image</html>")]:
            with self.assertRaises(ValueError):
                capture_files_from_zip(data)

    def test_json_is_fully_expanded_escaped_and_available_as_a_file(self):
        payload = {"responseHeaders": {"test": '</code></pre><script>alert(1)</script>',
                                       "set-cookie": "[REDACTED]"}, "long": "x" * 5000}
        name = "site-1-request-response-headers.json"
        data = archive(extra={name: json.dumps(payload)})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            build_pages(output, [capture(22, 1, "2026-09-08T00:00:00Z")], lambda _: data, "org/repo")
            directory = output / "runs/22/attempt-1"
            page = (directory / "index.html").read_text(encoding="utf-8")
            self.assertIn('<pre><code>', page)
            self.assertNotIn('<details', page)
            self.assertNotIn('<script>', page)
            self.assertIn('&lt;script&gt;', page)
            self.assertIn("x" * 5000, page)
            self.assertIn('[REDACTED]', page)
            self.assertEqual(json.loads((directory / name).read_text()), payload)

    def test_invalid_json_and_unrecognized_files_are_rejected(self):
        for extra in [{"site-1-network-address.json": "invalid"},
                      {"site-1-network-address.json": "[]"},
                      {"secret.json": "{}"}]:
            with self.assertRaises(ValueError):
                capture_files_from_zip(archive(extra=extra))

    def test_existing_output_cannot_silently_retain_expired_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_pages(temporary, [], lambda _: b"", "org/repo")


if __name__ == "__main__":
    unittest.main()
