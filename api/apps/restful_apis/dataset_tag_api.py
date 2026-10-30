"""Tag reads and explicit association deletion through existing workspace authorization."""
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from quart import Blueprint,Response,current_app,g,request
from quart_schema import document_response,validate_request
from api.apps.service_errors import service_error_response
from api.db.services import dataset_tag_service as tags
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from api.utils.blocking import DOCSTORE_EXECUTOR,run_blocking

tag_bp=Blueprint("dataset_tags",__name__)


class TagItem(BaseModel):
    tag: str
    weight: float
    count: int


class TagPage(BaseModel):
    items: list[TagItem]
    total: int


class TagEnvelope(BaseModel):
    code: int
    message: str
    data: TagPage


class DeleteTagsBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    tags: list[StrictStr] = Field(min_length=1,max_length=128)


class DeletedTags(BaseModel):
    deleted: list[str]
    count: int


class DeletedTagsEnvelope(BaseModel):
    code: int
    message: str
    data: DeletedTags


@tag_bp.get("/api/v1/datasets/tags/aggregation")
@document_response(TagEnvelope,200)
async def aggregate() -> Response:
    settings,principal=current_app.extensions["ragflow_settings"],g.principal
    try:
        raw=request.args.get("dataset_ids","")
        if len(raw)>1056 or set(request.args)!={"dataset_ids"} or len(request.args.getlist("dataset_ids"))!=1:
            raise tags._invalid()
        result=await run_blocking(DOCSTORE_EXECUTOR,lambda:tags.aggregate_tags(settings,principal,raw.split(",")),timeout=65)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@tag_bp.get("/api/v1/datasets/<dataset_id>/tags")
@document_response(TagEnvelope,200)
async def list_tags(dataset_id: str) -> Response:
    settings,principal=current_app.extensions["ragflow_settings"],g.principal
    try:
        result=await run_blocking(DOCSTORE_EXECUTOR,lambda:tags.list_tags(settings,principal,dataset_id),timeout=65)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@tag_bp.delete("/api/v1/datasets/<dataset_id>/tags")
@validate_request(DeleteTagsBody)
@document_response(DeletedTagsEnvelope,200)
async def delete_tags(dataset_id: str,data: DeleteTagsBody) -> Response:
    settings,principal=current_app.extensions["ragflow_settings"],g.principal
    try:
        result=await run_blocking(DOCSTORE_EXECUTOR,lambda:tags.delete_tags(settings,principal,dataset_id,data.tags),timeout=65)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)
