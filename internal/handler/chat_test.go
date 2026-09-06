package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/gin-gonic/gin"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

// setupTestDB creates an in-memory SQLite database for testing
func setupTestDB() {
	db, _ := gorm.Open(sqlite.Open("file::memory:?cache=shared"), &gorm.Config{})
	db.AutoMigrate(&dao.ChatSession{}, &dao.ChatMessage{}, &dao.AgentCanvas{})
	dao.DB = db
}

// mockAuthMiddleware skips actual JWT verification and injects test user
func mockAuthMiddleware(userID, tenantID string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Set("user_id", userID)
		c.Set("tenant_id", tenantID)
		c.Next()
	}
}

func setupTestRouter(userID, tenantID string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	
	// Create chat endpoints
	chat := r.Group("/chat")
	chat.Use(mockAuthMiddleware(userID, tenantID))
	{
		chat.POST("/session", CreateChatSession)
		chat.GET("/session", ListChatSessions)
		chat.GET("/session/:id", GetChatSession)
		chat.PUT("/session/:id", UpdateChatSession)
		chat.DELETE("/session/:id", DeleteChatSession)
		
		chat.GET("/message/:id", GetMessageHistory)
		chat.POST("/message/:id", AppendChatMessage)
	}
	
	return r
}

func TestChatSessionLifecycle(t *testing.T) {
	setupTestDB()
	
	// Create mock agent canvas
	dao.DB.Create(&dao.AgentCanvas{
		ID: "agent-1",
		TenantID: "tenant-1",
		Name: "Test Agent",
		GraphDefinition: "{}",
		CreatedBy: "user-1",
	})

	r := setupTestRouter("user-1", "tenant-1")

	// 1. Create Session
	createPayload := map[string]interface{}{
		"agent_id": "agent-1",
		"title": "My First Chat",
	}
	body, _ := json.Marshal(createPayload)
	req, _ := http.NewRequest(http.MethodPost, "/chat/session", bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK, got %d, body: %s", w.Code, w.Body.String())
	}

	var createResp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &createResp)
	data := createResp["data"].(map[string]interface{})
	sessionID := data["id"].(string)

	if data["title"] != "My First Chat" {
		t.Errorf("Expected title 'My First Chat', got %v", data["title"])
	}

	// 2. Append Message (User)
	msgPayload := map[string]interface{}{
		"role": "user",
		"content": "Hello world",
	}
	body, _ = json.Marshal(msgPayload)
	req, _ = http.NewRequest(http.MethodPost, "/chat/message/"+sessionID, bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	w = httptest.NewRecorder()
	r.ServeHTTP(w, req)
	
	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for append, got %d", w.Code)
	}
	
	time.Sleep(10 * time.Millisecond) // ensure time ordering

	// 3. Append Message (Assistant)
	msgPayload2 := map[string]interface{}{
		"role": "assistant",
		"content": "Hello user",
		"citations": map[string]interface{}{"source": "doc-1"},
	}
	body, _ = json.Marshal(msgPayload2)
	req, _ = http.NewRequest(http.MethodPost, "/chat/message/"+sessionID, bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	w = httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// 4. Get History
	req, _ = http.NewRequest(http.MethodGet, "/chat/message/"+sessionID, nil)
	w = httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for history, got %d", w.Code)
	}

	var historyResp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &historyResp)
	history := historyResp["data"].([]interface{})
	if len(history) != 2 {
		t.Fatalf("Expected 2 messages, got %d", len(history))
	}
	firstMsg := history[0].(map[string]interface{})
	if firstMsg["role"] != "user" {
		t.Errorf("Ordering failed, expected user first, got %v", firstMsg["role"])
	}

	// 5. Test Authorization Barrier
	// Create another user router
	r2 := setupTestRouter("user-2", "tenant-1")
	req, _ = http.NewRequest(http.MethodGet, "/chat/message/"+sessionID, nil)
	w = httptest.NewRecorder()
	r2.ServeHTTP(w, req)
	if w.Code != http.StatusNotFound { // Due to ErrChatSessionNotFound
		t.Errorf("Expected 404 Not Found for unauthorized access, got %d", w.Code)
	}

	// 6. Delete Session
	req, _ = http.NewRequest(http.MethodDelete, "/chat/session/"+sessionID, nil)
	w = httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Errorf("Expected 200 OK for delete, got %d", w.Code)
	}

	// Verify messages deleted via Transaction/Cascade
	var count int64
	dao.DB.Model(&dao.ChatMessage{}).Where("session_id = ?", sessionID).Count(&count)
	if count != 0 {
		t.Errorf("Expected 0 messages after session delete, got %d", count)
	}
}
