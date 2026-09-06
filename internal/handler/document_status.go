package handler

import (
	"net/http"
	"strings"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/gin-gonic/gin"
)

func GetDocumentStatus(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	docIDsParam := c.Query("document_ids")
	
	if docIDsParam == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "document_ids is required"})
		return
	}

	docIDs := strings.Split(docIDsParam, ",")
	if len(docIDs) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid document_ids"})
		return
	}

	// Fetch tasks for these documents belonging to the tenant
	var tasks []dao.DocumentTask
	err := dao.DB.Where("tenant_id = ? AND document_id IN ?", tenantID, docIDs).Find(&tasks).Error
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch task statuses"})
		return
	}

	// Group by document ID, taking the latest if multiple exist (order by created_at desc)
	// We can just fetch them ordered by created_at desc in the DB query
	var orderedTasks []dao.DocumentTask
	err = dao.DB.Where("tenant_id = ? AND document_id IN ?", tenantID, docIDs).Order("created_at desc").Find(&orderedTasks).Error
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch task statuses"})
		return
	}

	statusMap := make(map[string]map[string]interface{})
	for _, task := range orderedTasks {
		if _, exists := statusMap[task.DocumentID]; !exists {
			statusMap[task.DocumentID] = map[string]interface{}{
				"document_id": task.DocumentID,
				"task_id":     task.ID,
				"status":      task.Status,
				"progress":    task.Progress,
				"error_msg":   task.ErrorMsg,
				"updated_at":  task.UpdatedAt,
			}
		}
	}

	c.JSON(http.StatusOK, gin.H{"statuses": statusMap})
}
