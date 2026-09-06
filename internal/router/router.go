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

		document := v1.Group("/document")
		document.Use(middleware.Auth(cfg))
		{
			document.POST("/upload", handler.UploadDocument)
			document.GET("/list", handler.ListDocuments)
			document.GET("/status", handler.GetDocumentStatus)
			document.DELETE("/:id", handler.DeleteDocument)
		}
	}

	
		agent := v1.Group("/agent")
		agent.Use(middleware.Auth(cfg))
		{
			agent.POST("/canvas/save", handler.SaveCanvas)
			agent.GET("/canvas/:id", handler.GetCanvas)
		}

	
		chat := v1.Group("/chat")
		chat.Use(middleware.Auth(cfg))
		{
			chat.POST("/session", handler.CreateChatSession)
			chat.GET("/session", handler.ListChatSessions)
			chat.GET("/session/:id", handler.GetChatSession)
			chat.PUT("/session/:id", handler.UpdateChatSession)
			chat.DELETE("/session/:id", handler.DeleteChatSession)
			
			// message endpoints
			chat.GET("/message/:id", handler.GetMessageHistory)
			chat.POST("/message/:id", handler.AppendChatMessage)
		}

	return r
}
