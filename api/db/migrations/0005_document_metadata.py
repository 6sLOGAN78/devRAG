"""Add bounded document metadata, preserving existing documents on an interrupted DDL run."""
from api.db.migrations.runner import add_column_if_missing
from api.db.models.base import JSONField
from api.db.models.knowledge import Document

VERSION = "0005"


def upgrade(db) -> None:
    # MySQL cannot add a non-null LONGTEXT column to a populated table without a
    # default. Make the DDL restartable, fill old rows, then enforce the model rule.
    add_column_if_missing(db, "document", "meta_fields", JSONField(null=True))
    with db.bind_ctx([Document]):
        Document.update(meta_fields={}).where(Document.meta_fields.is_null()).execute()
    column = next(c for c in db.get_columns("document") if c.name == "meta_fields")
    if column.null:
        db.execute_sql("ALTER TABLE document MODIFY COLUMN meta_fields LONGTEXT NOT NULL")
