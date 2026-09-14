"""
Copy this file to config.py and fill in real values. config.py is
gitignored so your API keys never get committed.
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
