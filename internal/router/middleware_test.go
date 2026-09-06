package router_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/router"
	"github.com/gin-gonic/gin"
)

func TestRecoveryMiddleware(t *testing.T) {
	engine := router.InitRouter()
	engine.GET("/panic", func(c *gin.Context) {
		panic("test panic")
	})

	req, _ := http.NewRequest("GET", "/panic", nil)
	w := httptest.NewRecorder()
	engine.ServeHTTP(w, req)

	// Recovery middleware should convert panic to 500
	if w.Code != http.StatusInternalServerError {
		t.Errorf("Expected status 500, got %d", w.Code)
	}
}

func TestCORSMiddleware(t *testing.T) {
	engine := router.InitRouter()

	req, _ := http.NewRequest("OPTIONS", "/api/v1/health", nil)
	req.Header.Set("Origin", "http://example.com")
	w := httptest.NewRecorder()
	engine.ServeHTTP(w, req)

	if w.Code != http.StatusNoContent && w.Code != http.StatusOK {
		t.Errorf("Expected status for OPTIONS to be 204 or 200, got %d", w.Code)
	}

	allowOrigin := w.Header().Get("Access-Control-Allow-Origin")
	if allowOrigin != "*" && allowOrigin != "http://example.com" {
		t.Errorf("CORS failed: expected Origin to be allowed, got: %s", allowOrigin)
	}
}
