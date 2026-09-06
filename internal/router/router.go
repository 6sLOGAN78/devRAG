package router

import (
	"github.com/6sLOGAN78/devRAG/internal/handler"
	"github.com/6sLOGAN78/devRAG/internal/middleware"
	"github.com/gin-gonic/gin"
)

func InitRouter() *gin.Engine {
	// Use gin.New() to have full control over middlewares
	r := gin.New()

	// Recovery middleware
	r.Use(gin.Recovery())

	// Basic Logging middleware
	r.Use(gin.Logger())

	// CORS middleware
	r.Use(middleware.CORS())

	v1 := r.Group("/api/v1")
	{
		v1.GET("/health", handler.Health)
	}

	return r
}
