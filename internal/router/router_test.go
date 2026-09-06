package router_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/router"
)

func TestHealthRoute(t *testing.T) {
	engine := router.InitRouter()

	req, _ := http.NewRequest("GET", "/api/v1/health", nil)
	w := httptest.NewRecorder()
	engine.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
	}

	expectedBody := `{"status":"ok"}`
	if w.Body.String() != expectedBody {
		t.Errorf("Expected body %s, got %s", expectedBody, w.Body.String())
	}
}
