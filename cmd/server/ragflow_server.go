package main

import (
	"fmt"
	"log"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
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

	if err := dao.InitRedis(cfg); err != nil {
		log.Fatalf("Failed to initialize Redis: %v", err)
	}
	defer dao.CloseRedis()

	r := router.InitRouter(cfg)

	port := cfg.RAGFlow.GoPort
	addr := fmt.Sprintf(":%d", port)
	log.Printf("Starting devRAG Go API server on %s", addr)

	if err := r.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
