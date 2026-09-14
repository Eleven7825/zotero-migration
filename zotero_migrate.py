#!/usr/bin/env python3
"""
Migrate an entire Zotero library (collections, items, notes, attachments)
from one Zotero account/library to another using pyzotero.

Install dependency first:
    pip install pyzotero

Copy config.example.py to config.py, fill in your library IDs and API
keys, then run:
    python zotero_migrate.py

Recommended: set DRY_RUN = True first to see what would happen without
writing anything to the destination library.

Notes / limitations:
  - Not idempotent: running this twice will create duplicate items in the
    destination. Test on a copy or small subset first.
  - Rate limiting is handled with a fixed sleep between batches, not by
    reading Zotero's Backoff/Retry-After headers. If you hit 429s, increase
    SLEEP_BETWEEN_BATCHES.
  - Standalone linked-URL attachments (linkMode 'linked_url') and notes are
    copied as metadata only (no file to move). Stored file attachments
    (linkMode 'imported_file' / 'imported_url') are downloaded from the
    source and re-uploaded to the destination.
  - If `upload_attachments` behaves differently on your installed pyzotero
    version, check `pip show pyzotero` and the library's source/docs — the
    attachment upload call signature has changed across versions.
"""

import time
from pathlib import Path

from pyzotero import zotero

import config

DRY_RUN = config.DRY_RUN
SLEEP_BETWEEN_BATCHES = config.SLEEP_BETWEEN_BATCHES
BATCH_SIZE = config.BATCH_SIZE
DOWNLOAD_DIR = Path(config.DOWNLOAD_DIR)

src = zotero.Zotero(config.SOURCE_LIBRARY_ID, config.SOURCE_LIBRARY_TYPE, config.SOURCE_API_KEY)
dst = zotero.Zotero(config.DEST_LIBRARY_ID, config.DEST_LIBRARY_TYPE, config.DEST_API_KEY)

DOWNLOAD_DIR.mkdir(exist_ok=True)


def batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def migrate_collections():
    """Recreate the collection hierarchy in dest. Returns {old_key: new_key}."""
    print("Fetching source collections...")
    all_cols = src.everything(src.collections())
    print(f"  found {len(all_cols)} collections")

    key_map = {}
    remaining = {c["key"]: c for c in all_cols}
    while remaining:
        progressed = False
        for key, col in list(remaining.items()):
            parent = col["data"].get("parentCollection")
            if not parent or parent in key_map:
                new_data = {"name": col["data"]["name"]}
                if parent:
                    new_data["parentCollection"] = key_map[parent]
                if not DRY_RUN:
                    resp = dst.create_collections([new_data])
                    new_key = resp["successful"]["0"]["key"]
                else:
                    new_key = f"DRYRUN-{key}"
                key_map[key] = new_key
                del remaining[key]
                progressed = True
        if not progressed:
            print("  WARNING: could not resolve remaining collection parents, skipping rest")
            break
    print(f"  created {len(key_map)} collections in destination")
    return key_map


def strip_item(data, collection_key_map):
    """Drop server-managed fields and remap collection membership to new keys."""
    data = dict(data)
    old_collections = data.get("collections", [])
    data["collections"] = [collection_key_map[c] for c in old_collections if c in collection_key_map]
    for field in ("key", "version", "dateAdded", "dateModified", "relations"):
        data.pop(field, None)
    return data


def migrate_items(collection_key_map):
    """Copy all items (regular items, notes, attachments, PDF annotations),
    processing them in dependency waves so a child (e.g. an annotation
    whose parent is an attachment, whose own parent is a regular item) is
    only created after its parent exists in the destination, regardless of
    how many levels of nesting are involved."""
    print("Fetching all source items...")
    all_items = src.everything(src.items())
    print(f"  found {len(all_items)} items")

    item_key_map = {}
    remaining = {i["key"]: i for i in all_items}

    while remaining:
        ready = [
            it for it in remaining.values()
            if not it["data"].get("parentItem") or it["data"]["parentItem"] in item_key_map
        ]
        if not ready:
            print(f"  WARNING: {len(remaining)} items have unresolved parents (orphaned?), skipping:")
            for it in remaining.values():
                print(f"    {it['key']} -> missing parent {it['data'].get('parentItem')}")
            break

        for batch in batched(ready, BATCH_SIZE):
            new_batch = []
            for it in batch:
                data = strip_item(it["data"], collection_key_map)
                old_parent = it["data"].get("parentItem")
                if old_parent:
                    data["parentItem"] = item_key_map[old_parent]
                new_batch.append(data)
            if not DRY_RUN:
                resp = dst.create_items(new_batch)
                for idx, old_item in enumerate(batch):
                    res = resp["successful"].get(str(idx))
                    if res:
                        item_key_map[old_item["key"]] = res["key"]
                    else:
                        print(f"  FAILED to create item {old_item['key']}: {resp['failed'].get(str(idx))}")
            else:
                for old_item in batch:
                    item_key_map[old_item["key"]] = f"DRYRUN-{old_item['key']}"
            time.sleep(SLEEP_BETWEEN_BATCHES)

        for it in ready:
            remaining.pop(it["key"], None)

    print(f"  created {len(item_key_map)} items in destination")
    return item_key_map, all_items


def migrate_attachment_files(item_key_map, all_items):
    """Download stored attachment files from source and upload them to the new items in dest."""
    attachments = [
        i for i in all_items
        if i["data"].get("itemType") == "attachment"
        and i["data"].get("linkMode") in ("imported_file", "imported_url")
    ]
    print(f"Migrating {len(attachments)} attachment files...")
    for att in attachments:
        old_key = att["key"]
        new_key = item_key_map.get(old_key)
        filename = att["data"].get("filename")
        if not new_key or not filename:
            continue

        local_dir = DOWNLOAD_DIR / old_key
        local_dir.mkdir(exist_ok=True)
        local_path = local_dir / filename
        try:
            if not local_path.exists():
                src.dump(old_key, filename, str(local_dir))
        except Exception as e:
            print(f"  FAILED to download {old_key} ({filename}): {e}")
            continue

        if DRY_RUN:
            continue

        try:
            new_item = dst.item(new_key)  # fresh copy with current version for upload
            # upload_attachments needs the flat item dict (filename/md5/key at
            # top level), not the {key, version, data: {...}} wrapper dst.item()
            # returns. Keep md5: create_items() already copied the source
            # file's md5/mtime onto this item's metadata, so the server treats
            # it as "a file is already registered" -- sending that same md5
            # back (If-Match) lets us attach the real upload to it. Stripping
            # md5 instead sends If-None-Match, which 412s with "file exists".
            dst.upload_attachments([new_item["data"]], basedir=str(local_dir))
        except Exception as e:
            print(f"  FAILED to upload attachment for {new_key} ({filename}): {e}")
        time.sleep(SLEEP_BETWEEN_BATCHES)


def main():
    if DRY_RUN:
        print("=== DRY RUN: nothing will be written to the destination library ===")
    col_map = migrate_collections()
    item_key_map, all_items = migrate_items(col_map)
    migrate_attachment_files(item_key_map, all_items)
    print("Done.")


if __name__ == "__main__":
    main()
