package dao

import (
	"context"
	"fmt"
	"log"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/redis/go-redis/v9"
)

var RedisClient *redis.Client

func InitRedis(cfg *config.Config) error {
	addr := fmt.Sprintf("%s:%d", cfg.Redis.Host, cfg.Redis.Port)
	RedisClient = redis.NewClient(&redis.Options{
		Addr: addr,
		DB:   cfg.Redis.DB,
	})

	ctx := context.Background()
	_, err := RedisClient.Ping(ctx).Result()
	if err != nil {
		return fmt.Errorf("failed to connect to redis: %w", err)
	}

	log.Println("Redis connected.")
	return nil
}

func CloseRedis() {
	if RedisClient != nil {
		RedisClient.Close()
	}
}
