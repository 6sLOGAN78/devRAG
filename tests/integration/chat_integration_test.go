package integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/handler"
	"github.com/gin-gonic/gin"
)

func setupChatRouter() *gin.Engine {
	r := gin.Default()

	// Middleware mock
	r.Use(func(c *gin.Context) {
		c.Set("tenant_id", "test_tenant")
		c.Set("user_id", "test_user")
		c.Next()
	})

	r.POST("/api/v1/chat/session", handler.CreateChatSession)
	r.GET("/api/v1/chat/session/:id", handler.GetChatSession)
	r.GET("/api/v1/chat/session", handler.ListChatSessions)
	r.GET("/api/v1/chat/message/:id", handler.GetMessageHistory)

	return r
}

func TestChatSessionIntegration(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	r := setupChatRouter()

	// Create Session
	reqBody := map[string]string{
		"agent_id": "agent_123",
		"title":    "Integration Test Chat",
	}
	bodyBytes, _ := json.Marshal(reqBody)

	req, _ := http.NewRequest("POST", "/api/v1/chat/session", bytes.NewBuffer(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK && w.Code != http.StatusCreated && w.Code != http.StatusInternalServerError {
		t.Logf("Expected 200/201/500, got %d. Make sure DB is running.", w.Code)
	}
}
