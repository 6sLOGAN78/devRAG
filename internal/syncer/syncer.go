package syncer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

type Syncer struct {
	cfg        *config.Config
	httpClient *http.Client
	wg         sync.WaitGroup
	semaphore  chan struct{}
}

func NewSyncer(cfg *config.Config) *Syncer {
	return &Syncer{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: 10 * time.Second, // Timeout for the API dispatch request (not the entire parsing process)
		},
		semaphore: make(chan struct{}, cfg.Syncer.MaxInFlight),
	}
}

func (s *Syncer) Run(ctx context.Context) {
	log.Printf("Starting Task Syncer. Poll interval: %ds, Batch size: %d, Max concurrency: %d\n",
		s.cfg.Syncer.PollIntervalSec, s.cfg.Syncer.BatchSize, s.cfg.Syncer.MaxInFlight)

	ticker := time.NewTicker(time.Duration(s.cfg.Syncer.PollIntervalSec) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("Syncer context cancelled, waiting for in-flight tasks to complete...")
			s.wg.Wait()
			log.Println("Syncer gracefully stopped.")
			return
		case <-ticker.C:
			s.poll(ctx)
		}
	}
}

func (s *Syncer) poll(ctx context.Context) {
	// Attempt to claim tasks
	var tasks []dao.DocumentTask
	err := dao.DB.Transaction(func(tx *gorm.DB) error {
		// We use FOR UPDATE SKIP LOCKED to ensure atomic claiming of tasks without waiting for locks held by other workers
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).
			Where("status = ?", "unstart").
			Limit(s.cfg.Syncer.BatchSize).
			Find(&tasks).Error; err != nil {
			return err
		}

		if len(tasks) == 0 {
			return nil
		}

		var ids []string
		for _, t := range tasks {
			ids = append(ids, t.ID)
		}

		// Transition claimed tasks to RUNNING
		if err := tx.Model(&dao.DocumentTask{}).Where("id IN ?", ids).Update("status", "running").Error; err != nil {
			return err
		}

		return nil
	})

	if err != nil {
		log.Printf("[Syncer] Error claiming tasks: %v\n", err)
		return
	}

	if len(tasks) > 0 {
		log.Printf("[Syncer] Claimed %d tasks for processing.\n", len(tasks))
	}

	for _, task := range tasks {
		// Acquire semaphore token to bound concurrency
		select {
		case s.semaphore <- struct{}{}:
			s.wg.Add(1)
			go s.dispatch(task)
		case <-ctx.Done():
			// Context cancelled before we could process all claimed tasks
			log.Printf("[Syncer] Context cancelled. Leaving task %s in 'running' state (requires stale task recovery).\n", task.ID)
			return
		}
	}
}

type ParseRequest struct {
	TaskID     string `json:"task_id"`
	DocumentID string `json:"document_id"`
}

func (s *Syncer) dispatch(task dao.DocumentTask) {
	defer s.wg.Done()
	defer func() { <-s.semaphore }()

	url := fmt.Sprintf("http://127.0.0.1:%d/api/v1/ml/parse_document", s.cfg.RAGFlow.PythonPort)
	
	payload := ParseRequest{
		TaskID:     task.ID,
		DocumentID: task.DocumentID,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		s.failTask(task.ID, fmt.Sprintf("Failed to marshal request: %v", err))
		return
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(body))
	if err != nil {
		s.failTask(task.ID, fmt.Sprintf("Failed to create request: %v", err))
		return
	}

	req.Header.Set("Content-Type", "application/json")
	// If internal API requires a key, it would be added here

	resp, err := s.httpClient.Do(req)
	if err != nil {
		s.failTask(task.ID, fmt.Sprintf("HTTP dispatch failed: %v", err))
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		s.failTask(task.ID, fmt.Sprintf("Python API returned non-200 status: %d", resp.StatusCode))
		return
	}

	log.Printf("[Syncer] Successfully dispatched task %s (DocID: %s) to Python ML worker.\n", task.ID, task.DocumentID)
}

func (s *Syncer) failTask(taskID string, errorMsg string) {
	log.Printf("[Syncer] Task %s failed dispatch: %s\n", taskID, errorMsg)
	err := dao.DB.Model(&dao.DocumentTask{}).Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":    "failed",
		"error_msg": errorMsg,
	}).Error

	if err != nil {
		log.Printf("[Syncer] CRITICAL: Failed to update task %s status to failed: %v\n", taskID, err)
	}
}
