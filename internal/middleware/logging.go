package middleware

import (
	"log/slog"
	"time"

	"github.com/gin-gonic/gin"
)

func StructuredLogger(logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		reqID := c.GetString("request_id")

		c.Next()

		duration := time.Since(start)
		
		userID, _ := c.Get("user_id")
		tenantID, _ := c.Get("tenant_id")
		
		status := c.Writer.Status()
		
		lvl := slog.LevelInfo
		if status >= 500 {
			lvl = slog.LevelError
		} else if status >= 400 {
			lvl = slog.LevelWarn
		}
		
		logger.LogAttrs(c.Request.Context(), lvl, "HTTP Request",
			slog.String("request_id", reqID),
			slog.String("method", c.Request.Method),
			slog.String("route", path),
			slog.Int("status", status),
			slog.Duration("duration_ms", duration),
			slog.Any("user_id", userID),
			slog.Any("tenant_id", tenantID),
			slog.String("client_ip", c.ClientIP()),
		)
	}
}
