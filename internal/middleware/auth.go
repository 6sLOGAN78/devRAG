package middleware

import (
	"net/http"
	"strings"

	"github.com/6sLOGAN78/devRAG/internal/api"
	"github.com/6sLOGAN78/devRAG/internal/auth"
	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/6sLOGAN78/devRAG/internal/session"
	"github.com/gin-gonic/gin"
)

func Auth(cfg *config.Config) gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "Missing Authorization header")
			return
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "Invalid Authorization format")
			return
		}

		tokenString := parts[1]
		claims, err := auth.ValidateToken(tokenString, cfg.Auth.JWTSecret)
		if err != nil {
			api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "Invalid or expired token")
			return
		}

		valid, err := session.ValidateSession(c.Request.Context(), claims.UserID, claims.SessionID)
		if err != nil || !valid {
			api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "Session inactive or expired")
			return
		}

		requestedTenantID := c.GetHeader("X-Tenant-ID")
		tenantID, role, err := service.ResolveTenantContext(claims.UserID, requestedTenantID)
		if err != nil {
			api.RespondError(c, http.StatusForbidden, "FORBIDDEN", "Unauthorized tenant access")
			return
		}

		c.Set("user_id", claims.UserID)
		c.Set("tenant_id", tenantID)
		c.Set("role", role)
		c.Next()
	}
}
