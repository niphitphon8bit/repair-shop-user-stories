"""Start an isolated demo with the nine documented shop scenarios."""

import os

os.environ.setdefault("SHOP_DB", ".data/demo.sqlite3")
os.environ.setdefault("SHOP_TEST_MODE", "1")
# Explicitly a local demo password; real databases use random bootstrap passwords.
os.environ.setdefault("SHOP_INITIAL_PASSWORD", "SomdeeDemo2026!")
from . import server


def main():
    server.init()
    with server.connect() as db:
        if not db.execute("SELECT 1 FROM jobs LIMIT 1").fetchone():
            server.set_setting(db, "test_now", "2026-11-11T12:00")
            server.seed(db)
    server.main()


if __name__ == "__main__":
    main()
