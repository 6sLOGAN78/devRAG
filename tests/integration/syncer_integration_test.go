package integration

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
	"sync"
	"sync/atomic"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/syncer"
)

func TestSyncerConcurrency(t *testing.T) {
	// Initialize real database connection for integration tests
	cfg, err := config.LoadConfig("../../conf/service_conf.example.yaml")
	if err != nil {
		t.Fatalf("Failed to load config: %v", err)
	}
	
	// Override DB config for test if using test_db
	cfg.MySQL.DB = "rag_flow"
	if os.Getenv("TEST_DB_HOST") != "" {
		cfg.MySQL.Host = os.Getenv("TEST_DB_HOST")
	}

	err = dao.InitDB(cfg)
	if err != nil {
		t.Skipf("Skipping integration test: database unavailable: %v", err)
		return
	}
	defer dao.CloseDB()

	// Clear out existing tasks
	dao.DB.Exec("DELETE FROM document_task")

	// Insert 5 unstarted tasks
	for i := 0; i < 5; i++ {
		task := dao.DocumentTask{
			ID:         fmt.Sprintf("test-task-%d", i),
			DocumentID: fmt.Sprintf("doc-%d", i),
			TenantID:   "tenant-1",
			Status:     "unstart",
		}
		dao.DB.Create(&task)
	}

	// Mock python server
	var dispatchCount int32
	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&dispatchCount, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer mockServer.Close()

	var mockPort int
	fmt.Sscanf(mockServer.URL, "http://127.0.0.1:%d", &mockPort)
	if mockPort == 0 {
		fmt.Sscanf(mockServer.URL, "http://[::1]:%d", &mockPort)
	}
	cfg.RAGFlow.PythonPort = mockPort
	cfg.Syncer.PollIntervalSec = 1
	cfg.Syncer.BatchSize = 2
	cfg.Syncer.MaxInFlight = 5

	// Run multiple syncers simultaneously to test concurrency
	var wg sync.WaitGroup
	ctx, cancel := context.WithCancel(context.Background())

	numSyncers := 3
	for i := 0; i < numSyncers; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			s := syncer.NewSyncer(cfg)
			s.Run(ctx)
		}(i)
	}

	// Wait enough time for syncers to poll and dispatch tasks
	time.Sleep(3 * time.Second)
	
	// Shutdown syncers
	cancel()
	wg.Wait()

	// Verify all 5 tasks were dispatched exactly once
	if atomic.LoadInt32(&dispatchCount) != 5 {
		t.Errorf("Expected 5 dispatches, got %d", dispatchCount)
	}

	// Verify DB state
	var count int64
	dao.DB.Model(&dao.DocumentTask{}).Where("status = ?", "running").Count(&count)
	if count != 5 {
		t.Errorf("Expected 5 running tasks in DB, got %d", count)
	}
}
