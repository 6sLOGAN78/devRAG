"""Describe Go-owned public metadata in the combined API schema; registers no controller."""

from quart_schema.openapi import OpenAPIProvider


class CatalogOpenAPIProvider(OpenAPIProvider):
    def schema(self):
        document = super().schema()
        template = {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "name", "description", "parser_id", "parser_config", "available"],
            "properties": {
                **{name: {"type": "string"} for name in ["id", "name", "description", "parser_id"]},
                "parser_config": {"type": "object", "additionalProperties": True},
                "available": {"type": "boolean"},
            },
        }
        document["components"]["schemas"]["BuiltinPipelineTemplate"] = template
        ref = {"$ref": "#/components/schemas/BuiltinPipelineTemplate"}
        for path, data, parameters in [
            ("/api/v1/pipelines", {"type": "array", "items": ref}, [{"name": "type", "in": "query", "required": True, "schema": {"type": "string", "enum": ["builtin"]}}]),
            ("/api/v1/pipelines/{id}", ref, [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}]),
        ]:
            document["paths"][path] = {
                "get": {
                    "operationId": "listBuiltinPipelines" if path.endswith("pipelines") else "getBuiltinPipeline",
                    "description": "Public static build metadata served by Go. No tenant or runtime state.",
                    "security": [],
                    "x-api-owner": "go",
                    "parameters": parameters,
                    "responses": {
                        "200": {
                            "description": "Static template metadata",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["code", "message", "data"],
                                        "properties": {"code": {"type": "integer", "const": 0}, "message": {"type": "string"}, "data": data},
                                    }
                                }
                            },
                        },
                        ("400" if path.endswith("pipelines") else "404"): {"description": "Fixed refusal"},
                    },
                }
            }
        return document
