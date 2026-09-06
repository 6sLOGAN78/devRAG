package middleware

import (
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/api"
	"github.com/gin-gonic/gin"
)

func RequireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Must be executed after Auth middleware which sets the role
		role := c.GetString("role")

		if role == "" {
			// This means Auth middleware wasn't run or failed silently (shouldn't happen)
			api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "Authentication required")
			return
		}

		if role != "admin" && role != "owner" {
			api.RespondError(c, http.StatusForbidden, "FORBIDDEN", "Administrative privileges required")
			return
		}

		c.Next()
	}
}
