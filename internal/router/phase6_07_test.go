package router

import (
	"github.com/stretchr/testify/require"
	"net/http"
	"testing"
)

func TestBuiltinCatalogPublicCredentialIndependentAndReadOnly(t *testing.T) {
	e := healthy(t)
	for _, path := range []string{"/api/v1/pipelines?type=builtin", "/api/v1/pipelines/one"} {
		baseline := do(e, http.MethodGet, path, nil)
		require.Equal(t, http.StatusOK, baseline.Code, "public static catalog is missing")
		for _, headers := range []map[string]string{authed, {"Authorization": "Bearer invalid-test-value"}} {
			got := do(e, http.MethodGet, path, headers)
			require.Equal(t, baseline.Code, got.Code)
			require.Equal(t, baseline.Body.String(), got.Body.String())
		}
		require.Equal(t, http.StatusUnauthorized, do(e, http.MethodPost, path, nil).Code)
	}
	require.Equal(t, http.StatusBadRequest, do(e, http.MethodGet, "/api/v1/pipelines?type=private", nil).Code)
	require.Equal(t, http.StatusNotFound, do(e, http.MethodGet, "/api/v1/pipelines/unknown", nil).Code)
	require.Equal(t, http.StatusUnauthorized, do(e, http.MethodGet, "/api/v1/pipelines/one/secret", nil).Code)
}
