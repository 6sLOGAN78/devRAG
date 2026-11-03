"""Derived deletion and artifact access must have an owned service path."""
import importlib.util
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_owned_dataset_artifact_service_exists():
    assert importlib.util.find_spec("api.db.services.dataset_artifact_service") is not None, "derived deletion and download have no owned service"


@pytest.mark.parametrize("filename", ["../../etc/passwd", "a" * 32 + ".txt", "%2F" + "a" * 32 + ".json", "A" * 32 + ".json"])
def test_artifact_filename_refuses_paths_and_unregistered_shapes(filename):
    from api.db.services import dataset_artifact_service as artifacts
    from api.db.services.service_errors import Kind, ServiceError

    with pytest.raises(ServiceError) as error:
        artifacts.read_artifact(None, None, filename)
    assert error.value.kind is Kind.NOT_FOUND


def test_only_explicit_derived_type_can_be_deleted():
    from api.db.services import dataset_artifact_service as artifacts
    from api.db.services.service_errors import Kind, ServiceError

    with pytest.raises(ServiceError) as error:
        artifacts.delete_derived_index(None, None, "a" * 32, "all")
    assert error.value.kind is Kind.NOT_FOUND


@pytest.mark.parametrize("page,size", [(0, 20), (101, 20), (1, 0), (1, 51), (True, 20)])
def test_history_page_is_bounded_before_query(monkeypatch, page, size):
    from api.db.services import dataset_artifact_service as artifacts
    from api.db.services.service_errors import Kind, ServiceError

    monkeypatch.setattr(artifacts.datasets, "load_visible_dataset", lambda *_args: SimpleNamespace(scope=SimpleNamespace(tenant_id="t")))
    with pytest.raises(ServiceError) as error:
        artifacts.list_alterations(None, "a" * 32, page=page, size=size)
    assert error.value.kind is Kind.INVALID
