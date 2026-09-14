"""
Defaults and placeholders for the migration scripts.

Create config_local.py next to this file (it's gitignored) with just the
fields you need to change -- typically your two API keys and two library
IDs -- and it overrides the corresponding defaults below. You don't need to
repeat every field, only the ones that differ from these defaults.

Example config_local.py:

    SOURCE_LIBRARY_ID = "12345"
    SOURCE_API_KEY = "abc123..."

    DEST_LIBRARY_ID = "67890"
    DEST_API_KEY = "def456..."
"""

SOURCE_LIBRARY_ID = "SOURCE_USER_OR_GROUP_ID"
SOURCE_LIBRARY_TYPE = "user"   # "user" or "group"
SOURCE_API_KEY = "SOURCE_API_KEY"

DEST_LIBRARY_ID = "DEST_USER_OR_GROUP_ID"
DEST_LIBRARY_TYPE = "user"     # "user" or "group"
DEST_API_KEY = "DEST_API_KEY"

DOWNLOAD_DIR = "./zotero_migration_files"
DRY_RUN = True           # set False once a dry run looks correct
SLEEP_BETWEEN_BATCHES = 1.0
BATCH_SIZE = 50          # Zotero API max items per create call

try:
    from config_local import *  # noqa: F401,F403 -- optional, gitignored overrides
except ImportError:
    pass
