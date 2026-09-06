package handler

import (
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/gin-gonic/gin"
)

func SaveCanvas(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	userID, _ := c.Get("user_id")

	if tenantID == nil || userID == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	var req service.SaveCanvasReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := service.SaveCanvas(tenantID.(string), userID.(string), &req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": service.SaveCanvasResp{Success: true}})
}

func GetCanvas(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	id := c.Param("id")

	if tenantID == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	resp, err := service.GetCanvas(id, tenantID.(string))
	if err != nil {
		if err == dao.ErrCanvasNotFound {
			c.JSON(http.StatusNotFound, gin.H{"error": "canvas not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": resp})
}
