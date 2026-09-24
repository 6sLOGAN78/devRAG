package handler

import (
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/gin-gonic/gin"
)

func ListChunks(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	documentID := c.Query("document_id")

	if documentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "document_id is required"})
		return
	}

	chunks, err := service.ListChunks(documentID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, chunks)
}

func UpdateChunk(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	chunkID := c.Param("id")

	var req service.UpdateChunkReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := service.UpdateChunk(chunkID, tenantID, req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "success"})
}

func DeleteChunk(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	chunkID := c.Param("id")

	if err := service.DeleteChunk(chunkID, tenantID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "success"})
}
