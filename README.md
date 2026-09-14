# Zotero Migration

Copy an entire Zotero library — collections, items, notes, PDF attachments,
and nested annotations — from one Zotero account/library to another, using
the Zotero Web API via [pyzotero](https://github.com/urschrei/pyzotero).

## Setup

1. Create a virtual environment and install the dependency:

   ```
   python3 -m venv .venv
   .venv/bin/pip install pyzotero
   ```

2. Get an API key for each account at https://zotero.org/settings/keys. The
   source key only needs read access; the destination key needs write
   access. Also note each account's numeric library ID, shown on that same
   page (this is **not** the username).

3. Create `config_local.py` next to `config.py` (it's gitignored, so your
   keys never get committed) with just the fields you need to fill in:

   ```python
   SOURCE_LIBRARY_ID = "12345"
   SOURCE_API_KEY = "abc123..."

   DEST_LIBRARY_ID = "67890"
   DEST_API_KEY = "def456..."
   ```

   Everything else (library type, batch size, rate-limit delay, dry-run
   flag) has a sensible default in `config.py` — only add a field to
   `config_local.py` if you need to override it (e.g. set
   `SOURCE_LIBRARY_TYPE = "group"` if migrating from a group library).

## Usage

Dry run first — prints what would happen without writing anything:

```
.venv/bin/python zotero_migrate.py
```

`config.py` defaults to `DRY_RUN = True`. Once the dry-run output looks
right, add `DRY_RUN = False` to `config_local.py` and run again for real.

## How it works

1. **Collections** are recreated in dependency order (parents before
   children) so nested collection hierarchies are preserved.
2. **Items** are copied in dependency waves: regular items first, then
   attachments (children of regular items), then annotations (children of
   attachments) — any depth of nesting resolves correctly.
3. **Attachment files** (PDFs etc.) are downloaded from the source and
   uploaded to the newly created destination items. Zotero deduplicates
   storage by file hash, so if the same file content is already known to
   Zotero's storage, the "upload" is instant with no bytes transferred.

## Limitations

- **Not idempotent.** Running it twice creates duplicate items in the
  destination. There's no dry-run-then-resume checkpoint — test on a
  disposable destination (e.g. a scratch group library) first if you want
  to validate changes to the script.
- Rate limiting is a fixed sleep between batches (`SLEEP_BETWEEN_BATCHES`
  in config), not real backoff/retry-after handling.
- Items whose parent is in the source library's trash are skipped, with a
  warning, rather than migrated.
- `upload_attachments`'s exact behavior has shifted across pyzotero
  versions; if file uploads fail, check `pip show pyzotero` and the
  installed version's source.
