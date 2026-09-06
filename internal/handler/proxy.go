package handler

import (
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/gin-gonic/gin"
)

func PythonProxy(cfg *config.Config) gin.HandlerFunc {
	// Simple reverse proxy to Python backend
	target := fmt.Sprintf("http://127.0.0.1:%d", cfg.RAGFlow.PythonPort)
	// For docker environments, this might be "http://python_backend:9381"
	// but we'll stick to localhost for now or use config.
	remote, err := url.Parse(target)
	if err != nil {
		panic(err)
	}

	proxy := httputil.NewSingleHostReverseProxy(remote)

	// Pass correlation IDs to Python
	director := proxy.Director
	proxy.Director = func(req *http.Request) {
		director(req)

		// If using gin context values, we can't easily access them here without the gin context
		// So we just rely on the headers set by our middleware
	}

	// Custom error handler to standardize 502/504 errors
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		reqID := r.Header.Get("X-Request-ID")
		w.Header().Set("Content-Type", "application/json")

		status := http.StatusBadGateway
		if strings.Contains(err.Error(), "context deadline exceeded") {
			status = http.StatusGatewayTimeout
		}

		w.WriteHeader(status)
		w.Write([]byte(fmt.Sprintf(`{"error":{"code":"UPSTREAM_ERROR","message":"Python backend unavailable","request_id":"%s"}}`, reqID)))
	}

	return func(c *gin.Context) {
		// Forward headers
		reqID := c.GetString("request_id")
		userID, _ := c.Get("user_id")
		tenantID, _ := c.Get("tenant_id")

		c.Request.Header.Set("X-Request-ID", reqID)
		if userID != nil {
			c.Request.Header.Set("X-User-ID", userID.(string))
		}
		if tenantID != nil {
			c.Request.Header.Set("X-Tenant-ID", tenantID.(string))
		}

		proxy.ServeHTTP(c.Writer, c.Request)
	}
}
