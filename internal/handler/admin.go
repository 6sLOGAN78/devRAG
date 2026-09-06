package handler

import (
	"net/http"

	"github.com/6sLOGAN78/devRAG/internal/api"
	"github.com/6sLOGAN78/devRAG/internal/service"
	"github.com/gin-gonic/gin"
)

func AdminListUsers(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	if tenantID == nil {
		api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "unauthorized")
		return
	}

	users, err := service.ListTenantUsers(tenantID.(string))
	if err != nil {
		api.RespondError(c, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to fetch users")
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": users})
}

func AdminUpdateUserRole(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	currentAdminID, _ := c.Get("user_id")
	targetUserID := c.Param("id")

	if tenantID == nil || currentAdminID == nil {
		api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "unauthorized")
		return
	}

	var req service.UpdateUserRoleReq
	if err := c.ShouldBindJSON(&req); err != nil {
		api.RespondError(c, http.StatusBadRequest, "INVALID_REQUEST", "Invalid role")
		return
	}

	err := service.UpdateUserRole(tenantID.(string), targetUserID, req.Role, currentAdminID.(string))
	if err != nil {
		if err.Error() == "user not found in tenant" {
			api.RespondError(c, http.StatusNotFound, "NOT_FOUND", err.Error())
		} else if err.Error() == "cannot remove your own administrative privileges" ||
			err.Error() == "cannot remove the last administrator from the tenant" {
			api.RespondError(c, http.StatusBadRequest, "VALIDATION_ERROR", err.Error())
		} else {
			api.RespondError(c, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func AdminRemoveUser(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	currentAdminID, _ := c.Get("user_id")
	targetUserID := c.Param("id")

	if tenantID == nil || currentAdminID == nil {
		api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "unauthorized")
		return
	}

	err := service.RemoveUserFromTenant(tenantID.(string), targetUserID, currentAdminID.(string))
	if err != nil {
		if err.Error() == "user not found in tenant" {
			api.RespondError(c, http.StatusNotFound, "NOT_FOUND", err.Error())
		} else if err.Error() == "cannot remove yourself from the tenant" ||
			err.Error() == "cannot remove the last administrator from the tenant" {
			api.RespondError(c, http.StatusBadRequest, "VALIDATION_ERROR", err.Error())
		} else {
			api.RespondError(c, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func AdminGetStats(c *gin.Context) {
	tenantID, _ := c.Get("tenant_id")
	if tenantID == nil {
		api.RespondError(c, http.StatusUnauthorized, "UNAUTHORIZED", "unauthorized")
		return
	}

	stats, err := service.GetTenantStats(tenantID.(string))
	if err != nil {
		api.RespondError(c, http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to fetch stats")
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": stats})
}
