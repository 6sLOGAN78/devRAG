package integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/api"
	"github.com/6sLOGAN78/devRAG/internal/handler"
	"github.com/6sLOGAN78/devRAG/internal/middleware"
	"github.com/gin-gonic/gin"
)

func setupAdminRouter(role string) *gin.Engine {
	r := gin.Default()

	r.Use(func(c *gin.Context) {
		c.Set("tenant_id", "test_tenant")
		c.Set("user_id", "test_user")
		if role != "" {
			c.Set("role", role)
		}
		c.Next()
	})

	admin := r.Group("/api/v1/admin")
	admin.Use(middleware.RequireAdmin())
	{
		admin.GET("/stats", handler.AdminGetStats)
	}

	return r
}

func TestAdminRBAC(t *testing.T) {
	tests := []struct {
		name         string
		role         string
		expectedCode int
		expectedErr  string
	}{
		{"Admin Role", "admin", http.StatusInternalServerError, ""}, // Assuming DB not set up, it will fail fetching stats but pass RBAC
		{"Owner Role", "owner", http.StatusInternalServerError, ""},
		{"Normal Role", "normal", http.StatusForbidden, "FORBIDDEN"},
		{"Invite Role", "invite", http.StatusForbidden, "FORBIDDEN"},
		{"Missing Role", "", http.StatusUnauthorized, "UNAUTHORIZED"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := setupAdminRouter(tt.role)
			req, _ := http.NewRequest("GET", "/api/v1/admin/stats", nil)
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)

			if w.Code != tt.expectedCode {
				t.Errorf("Expected code %d, got %d", tt.expectedCode, w.Code)
			}
			
			if tt.expectedErr != "" {
				var resp api.ErrorResponse
				json.Unmarshal(w.Body.Bytes(), &resp)
				if resp.Error.Code != tt.expectedErr {
					t.Errorf("Expected error code %s, got %s", tt.expectedErr, resp.Error.Code)
				}
			}
		})
	}
}
