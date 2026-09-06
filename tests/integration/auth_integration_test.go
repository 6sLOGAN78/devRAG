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
			DB:   1, 
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

	dao.DB.AutoMigrate(&dao.User{}, &dao.Tenant{}, &dao.UserTenant{})
	dao.DB.Where("1 = 1").Delete(&dao.UserTenant{})
	dao.DB.Where("1 = 1").Delete(&dao.Tenant{})
	dao.DB.Where("1 = 1").Delete(&dao.User{})

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

	// Login to get user ID
	loginReq := service.LoginReq{
		Email:    "test@example.com",
		Password: "Password123",
	}
	bodyLogin, _ := json.Marshal(loginReq)
	req3, _ := http.NewRequest("POST", "/api/v1/user/login", bytes.NewBuffer(bodyLogin))
	req3.Header.Set("Content-Type", "application/json")
	w3 := httptest.NewRecorder()
	r.ServeHTTP(w3, req3)
	
	var loginRes service.LoginRes
	json.Unmarshal(w3.Body.Bytes(), &loginRes)

	// Inject a Tenant manually for this user to pass Tenant membership validation
	dao.DB.Create(&dao.Tenant{ID: "tenant-123", Name: "Test Tenant"})
	dao.DB.Create(&dao.UserTenant{UserID: loginRes.UserID, TenantID: "tenant-123", Role: "owner"})

	// Protected Route with Token
	req4, _ := http.NewRequest("GET", "/api/v1/user/info", nil)
	req4.Header.Set("Authorization", "Bearer "+loginRes.Token)
	w4 := httptest.NewRecorder()
	r.ServeHTTP(w4, req4)
	if w4.Code != http.StatusOK {
		t.Fatalf("Expected 200 OK for protected route, got %d", w4.Code)
	}

	// Test cross-tenant access rejection (if requested invalid tenant)
	req5, _ := http.NewRequest("GET", "/api/v1/user/info", nil)
	req5.Header.Set("Authorization", "Bearer "+loginRes.Token)
	req5.Header.Set("X-Tenant-ID", "tenant-999") // invalid
	w5 := httptest.NewRecorder()
	r.ServeHTTP(w5, req5)
	if w5.Code != http.StatusForbidden {
		t.Fatalf("Expected 403 Forbidden for cross-tenant access, got %d", w5.Code)
	}

	// Cleanup
	dao.CloseDB()
	dao.CloseRedis()
}
