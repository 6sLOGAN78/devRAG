package handler

import (
	"errors"
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

func GetUserInfo(c *gin.Context) {
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}
	
	tenantID, exists := c.Get("tenant_id")
	if !exists {
		c.JSON(http.StatusForbidden, gin.H{"error": "Forbidden"})
		return
	}

	var user dao.User
	if err := dao.DB.Where("id = ?", userID).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "User not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal server error"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"user": gin.H{
			"id":        user.ID,
			"email":     user.Email,
			"nickname":  user.Nickname,
			"tenant_id": tenantID,
			"role":      c.GetString("role"),
		},
	})
}
