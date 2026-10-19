"""Chat assistants: record the creator and the sharing level on ``dialog`` (plan 05-07; CHAT-01..04, D-09, D-10).

``created_by`` (VARCHAR 32, default empty) is the user who made the assistant and ``permission`` (VARCHAR 16, default ``me``) is
``me`` or ``team``, as on a dataset. Rows that exist before this migration get the defaults, so they read as private to nobody
(an empty creator matches no caller). Idempotent (R-75): MySQL commits DDL implicitly, so a rerun after a partial failure skips
what exists. A database built from the current models already has both columns and both indexes; this is then a no-op.
"""
from __future__ import annotations

import peewee

from api.db.migrations.runner import add_column_if_missing, add_index_if_missing

VERSION = "0003"

TABLE = "dialog"


def upgrade(db) -> None:
    add_column_if_missing(db, TABLE, "created_by", peewee.CharField(max_length=32, null=False, default=""))
    add_column_if_missing(db, TABLE, "permission", peewee.CharField(max_length=16, null=False, default="me"))
    add_index_if_missing(db, TABLE, ("created_by",))
    add_index_if_missing(db, TABLE, ("permission",))
