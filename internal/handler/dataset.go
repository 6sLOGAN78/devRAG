package handler

import (
	"errors"
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/gin-gonic/gin"
)

func CreateDataset(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	userID := c.GetString("user_id")

	var req service.CreateDatasetReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request payload", "details": err.Error()})
		return
	}

	ds, err := service.CreateDataset(tenantID, userID, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create dataset"})
		return
	}

	c.JSON(http.StatusCreated, ds)
}

func ListDatasets(c *gin.Context) {
	tenantID := c.GetString("tenant_id")

	datasets, err := service.ListDatasets(tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to list datasets"})
		return
	}

	// Make sure we always return an empty list instead of null if no datasets
	if datasets == nil {
		datasets = []service.DatasetDTO{}
	}
	
	c.JSON(http.StatusOK, gin.H{"datasets": datasets})
}

func DeleteDataset(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	datasetID := c.Param("id")

	if datasetID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Dataset ID is required"})
		return
	}

	err := service.DeleteDataset(tenantID, datasetID)
	if err != nil {
		if errors.Is(err, dao.ErrDatasetNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "Dataset not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete dataset"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Dataset deleted successfully"})
}
