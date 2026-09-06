package handler

import (
	"errors"
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/gin-gonic/gin"
)

func UploadDocument(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	userID := c.GetString("user_id")

	datasetID := c.PostForm("dataset_id")
	if datasetID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "dataset_id is required"})
		return
	}

	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "file is required"})
		return
	}
	
	// Max upload size 50MB (could come from config, we hardcode 50MB for now or rely on gin's max multipart)
	if file.Size > 50*1024*1024 {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "file size exceeds 50MB limit"})
		return
	}

	doc, err := service.UploadDocument(c.Request.Context(), tenantID, userID, datasetID, file)
	if err != nil {
		if err.Error() == "dataset not found or access denied" {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to upload document", "details": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, doc)
}

func ListDocuments(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	datasetID := c.Query("dataset_id")
	
	if datasetID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "dataset_id is required"})
		return
	}

	docs, err := service.ListDocuments(tenantID, datasetID)
	if err != nil {
		if err.Error() == "dataset not found or access denied" {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to list documents"})
		return
	}
	
	if docs == nil {
		docs = []service.DocumentDTO{}
	}

	c.JSON(http.StatusOK, gin.H{"documents": docs})
}

func DeleteDocument(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	docID := c.Param("id")

	if docID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "document ID is required"})
		return
	}

	err := service.DeleteDocument(c.Request.Context(), tenantID, docID)
	if err != nil {
		if errors.Is(err, dao.ErrDocumentNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "document not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete document"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "document deleted successfully"})
}
