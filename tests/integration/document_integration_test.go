package integration_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/router"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/6sLOGAN78/devRAG/internal/storage"
)

func setupDocumentTestApp(t *testing.T) (*config.Config, *http.ServeMux) {
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
			JWTSecret:            "test-document-secret",
			JWTExpirationMinutes: 10,
			SessionTTLMinutes:    10,
		},
		MinIO: config.MinIOConfig{
			Endpoint:  "127.0.0.1:19000",
			AccessKey: "admin",
			SecretKey: "password",
		},
	}

	err := dao.InitDB(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, DB not available: %v", err)
	}

	dao.DB.AutoMigrate(&dao.User{}, &dao.Tenant{}, &dao.UserTenant{}, &dao.Dataset{}, &dao.Document{}, &dao.DocumentTask{}, &dao.DocumentChunk{})
	dao.DB.Where("1 = 1").Delete(&dao.Document{})
	dao.DB.Where("1 = 1").Delete(&dao.Dataset{})
	dao.DB.Where("1 = 1").Delete(&dao.UserTenant{})
	dao.DB.Where("1 = 1").Delete(&dao.Tenant{})
	dao.DB.Where("1 = 1").Delete(&dao.User{})

	err = dao.InitRedis(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, Redis not available: %v", err)
	}
	dao.RedisClient.FlushDB(context.Background())

	err = storage.InitMinIO(cfg)
	if err != nil {
		t.Skipf("Skipping integration test, MinIO not available: %v", err)
	}

	return cfg, nil
}

func doDocLogin(t *testing.T, r http.Handler, email, password string) string {
	loginReq := service.LoginReq{
		Email:    email,
		Password: password,
	}
	bodyLogin, _ := json.Marshal(loginReq)
	req, _ := http.NewRequest("POST", "/api/v1/user/login", bytes.NewBuffer(bodyLogin))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	
	var loginRes service.LoginRes
	json.Unmarshal(w.Body.Bytes(), &loginRes)
	return loginRes.Token
}

func TestDocumentUploadPipeline(t *testing.T) {
	cfg, _ := setupDocumentTestApp(t)
	r := router.InitRouter(cfg)

	// Users & Tenants
	service.Register(service.RegisterReq{Email: "userdocA@test.com", Password: "Password123", Nickname: "User A"})
	service.Register(service.RegisterReq{Email: "userdocB@test.com", Password: "Password123", Nickname: "User B"})

	var userA, userB dao.User
	dao.DB.Where("email = ?", "userdoca@test.com").First(&userA)
	dao.DB.Where("email = ?", "userdocb@test.com").First(&userB)

	tenantA := "tenant-doc-A"
	tenantB := "tenant-doc-B"
	dao.DB.Create(&dao.Tenant{ID: tenantA, Name: "Tenant Doc A"})
	dao.DB.Create(&dao.Tenant{ID: tenantB, Name: "Tenant Doc B"})
	dao.DB.Create(&dao.UserTenant{UserID: userA.ID, TenantID: tenantA, Role: "owner"})
	dao.DB.Create(&dao.UserTenant{UserID: userB.ID, TenantID: tenantB, Role: "owner"})

	tokenA := doDocLogin(t, r, "userdocA@test.com", "Password123")
	tokenB := doDocLogin(t, r, "userdocB@test.com", "Password123")

	// Create Dataset A
	reqBody, _ := json.Marshal(map[string]string{"name": "Dataset A"})
	req, _ := http.NewRequest("POST", "/api/v1/dataset", bytes.NewBuffer(reqBody))
	req.Header.Set("Authorization", "Bearer "+tokenA)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	var dsA service.DatasetDTO
	json.Unmarshal(w.Body.Bytes(), &dsA)

	// Create Dataset B
	reqBodyB, _ := json.Marshal(map[string]string{"name": "Dataset B"})
	reqB, _ := http.NewRequest("POST", "/api/v1/dataset", bytes.NewBuffer(reqBodyB))
	reqB.Header.Set("Authorization", "Bearer "+tokenB)
	wB := httptest.NewRecorder()
	r.ServeHTTP(wB, reqB)
	var dsB service.DatasetDTO
	json.Unmarshal(wB.Body.Bytes(), &dsB)

	// 1. Upload Document A to Dataset A (Happy Path)
	bodyBuf := new(bytes.Buffer)
	writer := multipart.NewWriter(bodyBuf)
	writer.WriteField("dataset_id", dsA.ID)
	part, _ := writer.CreateFormFile("file", "test_file.txt")
	part.Write([]byte("This is a test document content for tenant A"))
	writer.Close()

	reqUpload, _ := http.NewRequest("POST", "/api/v1/document/upload", bodyBuf)
	reqUpload.Header.Set("Authorization", "Bearer "+tokenA)
	reqUpload.Header.Set("Content-Type", writer.FormDataContentType())
	wUpload := httptest.NewRecorder()
	r.ServeHTTP(wUpload, reqUpload)
	
	if wUpload.Code != http.StatusCreated {
		t.Fatalf("Expected 201 for document upload, got %d, %s", wUpload.Code, wUpload.Body.String())
	}

	var docA service.DocumentDTO
	json.Unmarshal(wUpload.Body.Bytes(), &docA)
	
	// Verify MinIO Upload
	exists, err := storage.ObjectExists(context.Background(), docA.MinioPath)
	if err != nil || !exists {
		t.Fatalf("MinIO object does not exist for %s", docA.MinioPath)
	}
	
	// 2. Upload Document A to Dataset B (Cross-Tenant Rejected)
	bodyBuf2 := new(bytes.Buffer)
	writer2 := multipart.NewWriter(bodyBuf2)
	writer2.WriteField("dataset_id", dsB.ID) // Token A trying to use Dataset B
	part2, _ := writer2.CreateFormFile("file", "test_file.txt")
	part2.Write([]byte("Malicious content"))
	writer2.Close()

	reqUpload2, _ := http.NewRequest("POST", "/api/v1/document/upload", bodyBuf2)
	reqUpload2.Header.Set("Authorization", "Bearer "+tokenA)
	reqUpload2.Header.Set("Content-Type", writer2.FormDataContentType())
	wUpload2 := httptest.NewRecorder()
	r.ServeHTTP(wUpload2, reqUpload2)
	
	if wUpload2.Code != http.StatusNotFound {
		t.Fatalf("Expected 404 for cross-tenant upload, got %d", wUpload2.Code)
	}

	// 3. List Documents
	reqList, _ := http.NewRequest("GET", fmt.Sprintf("/api/v1/document/list?dataset_id=%s", dsA.ID), nil)
	reqList.Header.Set("Authorization", "Bearer "+tokenA)
	wList := httptest.NewRecorder()
	r.ServeHTTP(wList, reqList)
	
	var listResp map[string][]service.DocumentDTO
	json.Unmarshal(wList.Body.Bytes(), &listResp)
	if len(listResp["documents"]) != 1 {
		t.Fatalf("Expected 1 document, got %d", len(listResp["documents"]))
	}

	// 4. Delete Document
	reqDel, _ := http.NewRequest("DELETE", "/api/v1/document/"+docA.ID, nil)
	reqDel.Header.Set("Authorization", "Bearer "+tokenA)
	wDel := httptest.NewRecorder()
	r.ServeHTTP(wDel, reqDel)
	if wDel.Code != http.StatusOK {
		t.Fatalf("Expected 200 for deletion, got %d", wDel.Code)
	}

	// Verify Minio cleanup
	time.Sleep(100 * time.Millisecond) // Give minio a fraction of a second just in case
	exists, _ = storage.ObjectExists(context.Background(), docA.MinioPath)
	if exists {
		t.Fatalf("MinIO object was not cleaned up!")
	}
}
