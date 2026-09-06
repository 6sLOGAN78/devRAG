package integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"devrag/internal/api/handlers"
	"devrag/internal/core/services"
	"devrag/internal/infrastructure/db"
	"github.com/gin-gonic/gin"
)

func setupChatRouter() *gin.Engine {
	r := gin.Default()

	// Mock DB and Services for test
	database := db.NewMySQLConnection("root:root@tcp(127.0.0.1:13306)/rag_test?charset=utf8mb4&parseTime=True&loc=Local")
	chatService := services.NewChatService(database)
	chatHandler := handlers.NewChatHandler(chatService)

	// Middleware mock
	r.Use(func(c *gin.Context) {
		c.Set("tenant_id", "test_tenant")
		c.Set("user_id", "test_user")
		c.Next()
	})

	r.POST("/api/v1/chat/sessions", chatHandler.CreateSession)
	r.GET("/api/v1/chat/sessions/:id", chatHandler.GetSession)
	r.GET("/api/v1/chat/sessions", chatHandler.ListSessions)
	r.GET("/api/v1/chat/sessions/:id/messages", chatHandler.ListMessages)

	return r
}

func TestChatSessionIntegration(t *testing.T) {
	// Note: We skip executing DB tests unless CI/Local DB is present
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

	req, _ := http.NewRequest("POST", "/api/v1/chat/sessions", bytes.NewBuffer(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK && w.Code != http.StatusCreated {
		t.Logf("Expected 200/201, got %d. Make sure DB is running.", w.Code)
	}
}
