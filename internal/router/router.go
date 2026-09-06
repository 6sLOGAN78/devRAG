package router

import (
	"log/slog"
	"os"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/handler"
	"github.com/6sLOGAN78/devRAG/internal/middleware"
	"github.com/gin-gonic/gin"
)

func InitRouter(cfg *config.Config) *gin.Engine {
	r := gin.New()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())
	r.Use(middleware.StructuredLogger(logger))
	r.Use(middleware.CORS())

	// Unauthenticated / lightly protected routes
	v1 := r.Group("/api/v1")
	{
		v1.GET("/health", handler.Health)

		user := v1.Group("/user")
		{
			user.POST("/register", handler.RegisterUser)
			user.POST("/login", handler.LoginUser(cfg))
		}
	}

	// Authenticated routes
	authV1 := r.Group("/api/v1")
	authV1.Use(middleware.Auth(cfg))
	authV1.Use(middleware.RateLimit(cfg, logger))
	{
		userAuth := authV1.Group("/user")
		{
			userAuth.GET("/info", handler.GetUserInfo)
		}

		dataset := authV1.Group("/dataset")
		{
			dataset.POST("", handler.CreateDataset)
			dataset.GET("/list", handler.ListDatasets)
			dataset.DELETE("/:id", handler.DeleteDataset)
		}

		document := authV1.Group("/document")
		{
			document.POST("/upload", handler.UploadDocument)
			document.GET("/list", handler.ListDocuments)
			document.GET("/status", handler.GetDocumentStatus)
			document.DELETE("/:id", handler.DeleteDocument)
		}

		agent := authV1.Group("/agent")
		{
			agent.POST("/canvas/save", handler.SaveCanvas)
			agent.GET("/canvas/:id", handler.GetCanvas)
		}

		chat := authV1.Group("/chat")
		{
			chat.POST("/session", handler.CreateChatSession)
			chat.GET("/session", handler.ListChatSessions)
			chat.GET("/session/:id", handler.GetChatSession)
			chat.PUT("/session/:id", handler.UpdateChatSession)
			chat.DELETE("/session/:id", handler.DeleteChatSession)

			// proxy endpoints
			chat.POST("/completions", handler.PythonProxy(cfg))
			// message endpoints
			chat.GET("/message/:id", handler.GetMessageHistory)
			chat.POST("/message/:id", handler.AppendChatMessage)
		}
	}

	return r
}
