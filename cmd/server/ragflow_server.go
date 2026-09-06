package main

import (
	"fmt"
	"log"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/storage"
	"github.com/6sLOGAN78/devRAG/internal/router"
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

	// AutoMigrate tables for development
	dao.DB.AutoMigrate(&dao.Tenant{}, &dao.User{}, &dao.UserTenant{}, &dao.Dataset{}, &dao.Document{})

	if err := dao.InitRedis(cfg); err != nil {
		log.Fatalf("Failed to initialize Redis: %v", err)
	}
	defer dao.CloseRedis()

	if err := storage.InitMinIO(cfg); err != nil {
		log.Fatalf("Failed to initialize MinIO: %v", err)
	}

	r := router.InitRouter(cfg)

	port := cfg.RAGFlow.GoPort
	addr := fmt.Sprintf(":%d", port)
	log.Printf("Starting devRAG Go API server on %s", addr)

	if err := r.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
