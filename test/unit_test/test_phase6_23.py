"""Dataset enrichment jobs have an explicit context separate from document tasks."""

import pytest

from api.db.services import dataset_job_service as jobs
from api.db.services import task_service
from api.db.services.service_errors import ServiceError

pytestmark = pytest.mark.unit


def test_dataset_job_context_has_a_separate_loader():
    # A queued dataset job cannot be resolved by joining Task.doc_id to Document.id.
    assert callable(getattr(task_service, "load_dataset_job_context", None))


def test_snapshot_digest_changes_with_source_and_configuration():
    source = [{"id": "a" * 32, "hash": "first", "source_tasks": ["b" * 32]}]
    config = {"auto_tags": True, "allowed_tags": ["lighthouse"]}
    fixed = jobs._digest(source, config)
    assert len(fixed) == 64 and fixed == jobs._digest(source, config)
    assert fixed != jobs._digest([{**source[0], "hash": "second"}], config)
    assert fixed != jobs._digest(source, {**config, "allowed_tags": ["calibration"]})


def test_unconfigured_run_is_refused_before_queue_or_model_use():
    with pytest.raises(ServiceError) as error:
        jobs._config({"auto_keywords": 0, "auto_tags": False, "auto_metadata": False})
    assert error.value.reason == "parser_config_invalid"
