package handler

import (
	"devrag/internal/common"
	"devrag/internal/pipeline"
	"github.com/gin-gonic/gin"
	"net/http"
)

// BuiltinPipelines returns static binary metadata, with no identity or DB lookup.
func BuiltinPipelines(c *gin.Context) {
	query := c.Request.URL.Query()
	if len(query) != 1 || len(query["type"]) != 1 || query.Get("type") != "builtin" {
		common.Fail(c, http.StatusBadRequest, common.CodeBadRequest, "invalid pipeline type")
		return
	}
	common.OK(c, pipeline.Builtins())
}

// BuiltinPipeline never reflects an unknown identifier in an error.
func BuiltinPipeline(c *gin.Context) {
	template, ok := pipeline.Builtin(c.Param("id"))
	if !ok {
		common.Fail(c, http.StatusNotFound, common.CodeNotFound, "not found")
		return
	}
	common.OK(c, template)
}
