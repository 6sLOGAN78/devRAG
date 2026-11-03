"""Add content-free derived-index deletion audit history."""
from api.db.migrations.runner import add_index_if_missing
from api.db.models.base import index_specs
from api.db.models.knowledge import DatasetAlteration

VERSION = "0007"


def upgrade(db) -> None:
    with db.bind_ctx([DatasetAlteration]):
        DatasetAlteration.create_table(safe=True)
        for _, columns, unique in index_specs(DatasetAlteration):
            add_index_if_missing(db, DatasetAlteration._meta.table_name, columns, unique)
