package integration_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/router"
	"github.com/6sLOGAN78/devRAG/internal/service"
)

func setupTestApp(t *testing.T) (*config.Config, *http.ServeMux) {
	// Provide local config
	cfg := &config.Config{
		MySQL: config.MySQLConfig{
			Host:     "127.0.0.1",
			Port:     13306,
			User:     "ragflow",
			Password: "ragflow",
			DB:       "rag_flow",
		},
		Redis: config.RedisConfig{
			Host: "127.0.0.1",
			Port: 16379,
			DB:   1, // Use db 1 for tests
		},
		Auth: config.AuthConfig{
			JWTSecret:            "test-integration-secret",
			JWTExpirationMinutes: 10,
			SessionTTLMinutes:    10,
		},
	}

	err := dao.InitDB(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, DB not available: %v", err)
	}

	// Auto migrate
	dao.DB.AutoMigrate(&dao.User{})
	dao.DB.Where("1 = 1").Delete(&dao.User{}) // Clean up users

	err = dao.InitRedis(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, Redis not available: %v", err)
	}
	dao.RedisClient.FlushDB(context.Background())

	return cfg, nil
}

func TestAuthFlow(t *testing.T) {
	cfg, _ := setupTestApp(t)
	r := router.InitRouter(cfg)

	// 1. Register User
	registerReq := service.RegisterReq{
		Email:    "test@example.com",
		Password: "Password123",
		Nickname: "Test User",
	}
	body, _ := json.Marshal(registerReq)
	req, _ := http.NewRequest("POST", "/api/v1/user/register", bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("Expected 201 Created for register, got %d: %s", w.Code, w.Body.String())
	}

	// 2. Duplicate Registration
	w2 := httptest.NewRecorder()
	req2, _ := http.NewRequest("POST", "/api/v1/user/register", bytes.NewBuffer(body))
	req2.Header.Set("Content-Type", "application/json")
	r.ServeHTTP(w2, req2)
	if w2.Code != http.StatusConflict {
		t.Fatalf("Expected 409 Conflict for duplicate register, got %d", w2.Code)
	}

	// 3. Login User
	loginReq := service.LoginReq{
		Email:    "test@example.com",
		Password: "Password123",
	}
	bodyLogin, _ := json.Marshal(loginReq)
	req3, _ := http.NewRequest("POST", "/api/v1/user/login", bytes.NewBuffer(bodyLogin))
	req3.Header.Set("Content-Type", "application/json")
	w3 := httptest.NewRecorder()
	r.ServeHTTP(w3, req3)
	if w3.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for login, got %d: %s", w3.Code, w3.Body.String())
	}

	var loginRes service.LoginRes
	json.Unmarshal(w3.Body.Bytes(), &loginRes)
	if loginRes.Token == "" {
		t.Fatal("Expected JWT token in response")
	}

	// 4. Protected Route with Token
	req4, _ := http.NewRequest("GET", "/api/v1/user/me", nil)
	req4.Header.Set("Authorization", "Bearer "+loginRes.Token)
	w4 := httptest.NewRecorder()
	r.ServeHTTP(w4, req4)
	if w4.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for protected route, got %d", w4.Code)
	}

	// 5. Protected Route without Token
	req5, _ := http.NewRequest("GET", "/api/v1/user/me", nil)
	w5 := httptest.NewRecorder()
	r.ServeHTTP(w5, req5)
	if w5.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized for missing token, got %d", w5.Code)
	}

	// 6. Test Redis Session Expiry (manually delete it)
	dao.RedisClient.Del(context.Background(), "session:"+loginRes.UserID)
	w6 := httptest.NewRecorder()
	req6, _ := http.NewRequest("GET", "/api/v1/user/me", nil)
	req6.Header.Set("Authorization", "Bearer "+loginRes.Token)
	r.ServeHTTP(w6, req6)
	if w6.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 Unauthorized after session deleted, got %d", w6.Code)
	}

	// Cleanup
	dao.CloseDB()
	dao.CloseRedis()
}
