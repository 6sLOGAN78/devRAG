package router

import (
	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/handler"
	"github.com/6sLOGAN78/devRAG/internal/middleware"
	"github.com/gin-gonic/gin"
)

func InitRouter(cfg *config.Config) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(gin.Logger())
	r.Use(middleware.CORS())

	v1 := r.Group("/api/v1")
	{
		v1.GET("/health", handler.Health)

		user := v1.Group("/user")
		{
			user.POST("/register", handler.RegisterUser)
			user.POST("/login", handler.LoginUser(cfg))

			// User info route
			user.GET("/info", middleware.Auth(cfg), handler.GetUserInfo)
		}

		dataset := v1.Group("/dataset")
		dataset.Use(middleware.Auth(cfg))
		{
			dataset.POST("", handler.CreateDataset)
			dataset.GET("/list", handler.ListDatasets)
			dataset.DELETE("/:id", handler.DeleteDataset)
		}
	}

	return r
}
