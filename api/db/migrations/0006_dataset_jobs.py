"""Create explicit dataset-job ownership and generation mapping."""
from api.db.migrations.runner import add_index_if_missing
from api.db.models.base import index_specs
from api.db.models.knowledge import DatasetJob

VERSION = "0006"


def upgrade(db) -> None:
    with db.bind_ctx([DatasetJob]):
        DatasetJob.create_table(safe=True)
        for _, columns, unique in index_specs(DatasetJob):
            add_index_if_missing(db, DatasetJob._meta.table_name, columns, unique)
