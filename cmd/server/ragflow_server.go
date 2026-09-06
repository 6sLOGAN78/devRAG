package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/router"
	"github.com/6sLOGAN78/devRAG/internal/storage"
	"github.com/6sLOGAN78/devRAG/internal/syncer"
)

func main() {
	cfg, err := config.LoadConfig("conf/service_conf.yaml")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	if err := dao.InitDB(cfg); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer dao.CloseDB()

	dao.DB.AutoMigrate(&dao.User{}, &dao.Tenant{}, &dao.UserTenant{}, &dao.Dataset{}, &dao.Document{}, &dao.DocumentTask{}, &dao.DocumentChunk{}, &dao.AgentCanvas{}, &dao.ChatSession{}, &dao.ChatMessage{})

	if err := dao.InitRedis(cfg); err != nil {
		log.Fatalf("Failed to initialize Redis: %v", err)
	}
	defer dao.CloseRedis()

	if err := storage.InitMinIO(cfg); err != nil {
		log.Fatalf("Failed to initialize MinIO: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Start Syncer Worker
	syncWorker := syncer.NewSyncer(cfg)
	go syncWorker.Run(ctx)

	r := router.InitRouter(cfg)

	port := cfg.RAGFlow.GoPort
	addr := fmt.Sprintf(":%d", port)
	
	srv := &http.Server{
		Addr:    addr,
		Handler: r,
	}

	go func() {
		log.Printf("Starting devRAG Go API server on %s", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %s\n", err)
		}
	}()

	<-ctx.Done()
	stop()
	log.Println("Shutting down server...")

	ctxTimeout, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctxTimeout); err != nil {
		log.Fatal("Server forced to shutdown: ", err)
	}

	log.Println("Server exiting")
}
