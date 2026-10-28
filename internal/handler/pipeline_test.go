package handler

import (
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"net/http/httptest"
	"testing"
)

func TestCatalogRejectsMissingUnknownAndDuplicateTypeWithoutReflection(t *testing.T) {
	e := gin.New()
	e.GET("/pipelines", BuiltinPipelines)
	for _, query := range []string{"", "?type=private", "?type=builtin&type=private", "?type=builtin&tenant_id=other"} {
		w := httptest.NewRecorder()
		e.ServeHTTP(w, httptest.NewRequest("GET", "/pipelines"+query, nil))
		require.Equal(t, 400, w.Code)
		require.JSONEq(t, `{"code":400,"message":"invalid pipeline type","data":null}`, w.Body.String())
	}
}
