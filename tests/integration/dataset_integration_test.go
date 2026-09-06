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

func setupDatasetTestApp(t *testing.T) (*config.Config, *http.ServeMux) {
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
			JWTSecret:            "test-dataset-secret",
			JWTExpirationMinutes: 10,
			SessionTTLMinutes:    10,
		},
	}

	err := dao.InitDB(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, DB not available: %v", err)
	}

	dao.DB.AutoMigrate(&dao.User{}, &dao.Tenant{}, &dao.UserTenant{}, &dao.Dataset{})
	dao.DB.Where("1 = 1").Delete(&dao.Dataset{})
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

func doLogin(t *testing.T, r http.Handler, email, password string) string {
	loginReq := service.LoginReq{
		Email:    email,
		Password: password,
	}
	bodyLogin, _ := json.Marshal(loginReq)
	req, _ := http.NewRequest("POST", "/api/v1/user/login", bytes.NewBuffer(bodyLogin))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	
	if w.Code != http.StatusOK {
		t.Fatalf("Failed to login %s, code %d", email, w.Code)
	}

	var loginRes service.LoginRes
	json.Unmarshal(w.Body.Bytes(), &loginRes)
	return loginRes.Token
}

func TestDatasetCRUD_Isolation(t *testing.T) {
	cfg, _ := setupDatasetTestApp(t)
	r := router.InitRouter(cfg)

	// Create users
	service.Register(service.RegisterReq{Email: "userA@test.com", Password: "Password123", Nickname: "User A"})
	service.Register(service.RegisterReq{Email: "userB@test.com", Password: "Password123", Nickname: "User B"})

	var userA, userB dao.User
	dao.DB.Where("email = ?", "usera@test.com").First(&userA)
	dao.DB.Where("email = ?", "userb@test.com").First(&userB)

	// Create tenants and associations
	tenantA := "tenant-A"
	tenantB := "tenant-B"
	dao.DB.Create(&dao.Tenant{ID: tenantA, Name: "Tenant A"})
	dao.DB.Create(&dao.Tenant{ID: tenantB, Name: "Tenant B"})

	dao.DB.Create(&dao.UserTenant{UserID: userA.ID, TenantID: tenantA, Role: "owner"})
	dao.DB.Create(&dao.UserTenant{UserID: userB.ID, TenantID: tenantB, Role: "owner"})

	tokenA := doLogin(t, r, "userA@test.com", "Password123")
	tokenB := doLogin(t, r, "userB@test.com", "Password123")

	// 1. Create Dataset in Tenant A
	reqBody, _ := json.Marshal(map[string]string{"name": "Dataset A1", "description": "Desc A1"})
	req, _ := http.NewRequest("POST", "/api/v1/dataset", bytes.NewBuffer(reqBody))
	req.Header.Set("Authorization", "Bearer "+tokenA)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("Expected 201 for dataset creation, got %d", w.Code)
	}
	var dsA1 service.DatasetDTO
	json.Unmarshal(w.Body.Bytes(), &dsA1)

	if dsA1.TenantID != tenantA {
		t.Fatalf("Dataset bound to wrong tenant: expected %s, got %s", tenantA, dsA1.TenantID)
	}

	// Create another in A
	reqBody2, _ := json.Marshal(map[string]string{"name": "Dataset A2"})
	req2, _ := http.NewRequest("POST", "/api/v1/dataset", bytes.NewBuffer(reqBody2))
	req2.Header.Set("Authorization", "Bearer "+tokenA)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	// Create Dataset in Tenant B
	reqBody3, _ := json.Marshal(map[string]string{"name": "Dataset B1"})
	req3, _ := http.NewRequest("POST", "/api/v1/dataset", bytes.NewBuffer(reqBody3))
	req3.Header.Set("Authorization", "Bearer "+tokenB)
	w3 := httptest.NewRecorder()
	r.ServeHTTP(w3, req3)

	// 2. List Datasets for A (Should see A1, A2)
	reqList, _ := http.NewRequest("GET", "/api/v1/dataset/list", nil)
	reqList.Header.Set("Authorization", "Bearer "+tokenA)
	wList := httptest.NewRecorder()
	r.ServeHTTP(wList, reqList)
	if wList.Code != http.StatusOK {
		t.Fatalf("Expected 200 for list, got %d", wList.Code)
	}
	var listResp map[string][]service.DatasetDTO
	json.Unmarshal(wList.Body.Bytes(), &listResp)
	if len(listResp["datasets"]) != 2 {
		t.Fatalf("Expected 2 datasets for Tenant A, got %d", len(listResp["datasets"]))
	}

	// 3. Delete Dataset A1 (Success)
	reqDel, _ := http.NewRequest("DELETE", "/api/v1/dataset/"+dsA1.ID, nil)
	reqDel.Header.Set("Authorization", "Bearer "+tokenA)
	wDel := httptest.NewRecorder()
	r.ServeHTTP(wDel, reqDel)
	if wDel.Code != http.StatusOK {
		t.Fatalf("Expected 200 for deletion, got %d", wDel.Code)
	}

	// 4. Attempt to Delete Dataset B1 using token A (Fail - Cross-Tenant)
	// Find B1 ID first via direct DB for testing purpose
	var dsB1 dao.Dataset
	dao.DB.Where("tenant_id = ?", tenantB).First(&dsB1)

	reqDelCross, _ := http.NewRequest("DELETE", "/api/v1/dataset/"+dsB1.ID, nil)
	reqDelCross.Header.Set("Authorization", "Bearer "+tokenA)
	wDelCross := httptest.NewRecorder()
	r.ServeHTTP(wDelCross, reqDelCross)
	if wDelCross.Code != http.StatusNotFound {
		t.Fatalf("Expected 404 Not Found for cross-tenant deletion attempt, got %d", wDelCross.Code)
	}

	// Verify B1 still exists
	if err := dao.DB.Where("id = ?", dsB1.ID).First(&dao.Dataset{}).Error; err != nil {
		t.Fatalf("Dataset B1 should not have been deleted!")
	}

	// Unauthenticated test
	reqUnauth, _ := http.NewRequest("GET", "/api/v1/dataset/list", nil)
	wUnauth := httptest.NewRecorder()
	r.ServeHTTP(wUnauth, reqUnauth)
	if wUnauth.Code != http.StatusUnauthorized {
		t.Fatalf("Expected 401 for unauthenticated list, got %d", wUnauth.Code)
	}

	dao.CloseDB()
	dao.CloseRedis()
}
