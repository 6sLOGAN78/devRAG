package integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
	"sync"
	"log/slog"
	"os"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/middleware"
	"github.com/gin-gonic/gin"
)

func TestRateLimitIntegration(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	// Setup Redis
	cfg := &config.Config{
		Redis: config.RedisConfig{Host: "127.0.0.1", Port: 16379, DB: 1},
	}
	err := dao.InitRedis(cfg)
	if err != nil {
		t.Skip("Redis not available, skipping rate limit integration test")
	}
	defer dao.CloseRedis()
	
	dao.RedisClient.FlushDB(context.Background())

	gin.SetMode(gin.TestMode)
	r := gin.New()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	
	// Add mock request ID middleware
	r.Use(func(c *gin.Context) {
		c.Set("request_id", "test-req-1")
		c.Set("user_id", "test_user_limit")
		c.Next()
	})
	
	r.Use(middleware.RateLimit(cfg, logger))
	r.POST("/api/v1/chat/completions", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// Test 1: Chat Completion limit is 10. We send 11 requests.
	// We should get 10 OK and 1 HTTP 429
	
	var wg sync.WaitGroup
	results := make(chan int, 15)
	
	for i := 0; i < 11; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			req, _ := http.NewRequest("POST", "/api/v1/chat/completions", nil)
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			results <- w.Code
		}()
	}
	
	wg.Wait()
	close(results)
	
	successCount := 0
	limitCount := 0
	
	for code := range results {
		if code == 200 {
			successCount++
		} else if code == http.StatusTooManyRequests {
			limitCount++
		}
	}
	
	if successCount != 10 {
		t.Errorf("Expected 10 successful requests, got %d", successCount)
	}
	if limitCount != 1 {
		t.Errorf("Expected 1 rate limited request, got %d", limitCount)
	}
	
	// Test 2: Refill
	time.Sleep(1100 * time.Millisecond) // chat policy refills 1 token per sec
	
	req, _ := http.NewRequest("POST", "/api/v1/chat/completions", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Errorf("Expected request to succeed after refill, got %d", w.Code)
	}
}
