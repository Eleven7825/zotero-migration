#!/usr/bin/env python3
"""
One-off recovery: the main migration already created all 233 items in the
destination, but the attachment file upload step failed (wrong payload shape
passed to pyzotero's upload_attachments, and a stale md5 that made it look
like a file-replace instead of a first-time upload).

This script re-matches source <-> destination attachments by content
signature (filename/md5/mtime/etc, all of which the main script copied over
unchanged) since no old-key -> new-key mapping was persisted, then uploads
the actual file content correctly.
"""

import time
from collections import defaultdict
from pathlib import Path

from pyzotero import zotero

import config

DOWNLOAD_DIR = Path(config.DOWNLOAD_DIR)
DOWNLOAD_DIR.mkdir(exist_ok=True)

src = zotero.Zotero(config.SOURCE_LIBRARY_ID, config.SOURCE_LIBRARY_TYPE, config.SOURCE_API_KEY)
dst = zotero.Zotero(config.DEST_LIBRARY_ID, config.DEST_LIBRARY_TYPE, config.DEST_API_KEY)


def sig(data):
    return (
        data.get("filename"),
        data.get("md5"),
        data.get("mtime"),
        data.get("title"),
        data.get("url"),
        data.get("note"),
        data.get("contentType"),
        data.get("charset"),
        data.get("linkMode"),
    )


def is_stored_attachment(item):
    return item["data"].get("itemType") == "attachment" and item["data"].get("linkMode") in (
        "imported_file",
        "imported_url",
    )


def main():
    print("Fetching source items...")
    src_items = src.everything(src.items())
    src_atts = [i for i in src_items if is_stored_attachment(i)]

    print("Fetching destination items...")
    dst_items = dst.everything(dst.items())
    dst_atts = [i for i in dst_items if is_stored_attachment(i)]

    print(f"source attachments: {len(src_atts)}, destination attachments: {len(dst_atts)}")

    dst_buckets = defaultdict(list)
    for it in dst_atts:
        dst_buckets[sig(it["data"])].append(it)

    pairs, unmatched = [], []
    for it in src_atts:
        bucket = dst_buckets.get(sig(it["data"]))
        if bucket:
            pairs.append((it, bucket.pop(0)))
        else:
            unmatched.append(it)

    print(f"matched {len(pairs)} pairs, {len(unmatched)} unmatched")
    for it in unmatched:
        print(f"  UNMATCHED source attachment {it['key']}: {it['data'].get('filename')}")

    ok, failed = 0, 0
    for src_item, dst_item in pairs:
        old_key = src_item["key"]
        new_key = dst_item["key"]
        filename = src_item["data"].get("filename")
        if not filename:
            continue

        local_dir = DOWNLOAD_DIR / old_key
        local_dir.mkdir(exist_ok=True)
        local_path = local_dir / filename
        try:
            if not local_path.exists():
                src.dump(old_key, filename, str(local_dir))
        except Exception as e:
            print(f"  FAILED download {old_key} ({filename}): {e}")
            failed += 1
            continue

        payload_item = dict(dst_item["data"])
        # Keep md5: the destination item's metadata already has it set (copied
        # verbatim when the item was created), so the server thinks a file is
        # already registered. Sending it back as If-Match lets us "replace"
        # that phantom file with the real upload, which has the same hash.

        try:
            result = dst.upload_attachments([payload_item], basedir=str(local_dir))
            if result.get("failure"):
                print(f"  FAILED upload {new_key} ({filename}): {result['failure']}")
                failed += 1
            else:
                status = "unchanged (already present)" if result.get("unchanged") else "uploaded"
                print(f"  OK [{status}] {new_key} ({filename})")
                ok += 1
        except Exception as e:
            print(f"  FAILED upload {new_key} ({filename}): {e}")
            failed += 1
        time.sleep(0.5)

    print(f"Done. {ok} succeeded, {failed} failed, {len(unmatched)} unmatched.")


if __name__ == "__main__":
    main()
