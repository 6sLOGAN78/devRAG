"""Add document-scoped image/artifact ownership; idempotent on an interrupted DDL run."""
from api.db.migrations.runner import add_index_if_missing
from api.db.models.base import index_specs
from api.db.models.knowledge import DocumentAsset

VERSION = "0004"


def upgrade(db) -> None:
    with db.bind_ctx([DocumentAsset]):
        DocumentAsset.create_table(safe=True)
        for _, columns, unique in index_specs(DocumentAsset):
            add_index_if_missing(db, DocumentAsset._meta.table_name, columns, unique)
