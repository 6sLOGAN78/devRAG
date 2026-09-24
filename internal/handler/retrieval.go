package handler

import (
	"bytes"
	"io"
	"net/http"
	"fmt"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/gin-gonic/gin"
)

func RetrievalTest(cfg *config.Config) gin.HandlerFunc {
	return func(c *gin.Context) {
		tenantID := c.GetString("tenant_id")
		userID := c.GetString("user_id")

		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read request body"})
			return
		}

		// Proxy to python ML engine
		mlURL := fmt.Sprintf("http://127.0.0.1:%d/api/v1/ml/retrieval", cfg.RAGFlow.PythonPort)
		
		req, err := http.NewRequest("POST", mlURL, bytes.NewReader(body))
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create proxy request"})
			return
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Tenant-ID", tenantID)
		req.Header.Set("X-User-ID", userID)

		client := &http.Client{}
		resp, err := client.Do(req)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "ML engine request failed: " + err.Error()})
			return
		}
		defer resp.Body.Close()

		for k, v := range resp.Header {
			c.Header(k, v[0])
		}
		c.Status(resp.StatusCode)

		io.Copy(c.Writer, resp.Body)
	}
}
