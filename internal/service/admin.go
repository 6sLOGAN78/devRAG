package service

import (
	"errors"

	"github.com/6sLOGAN78/devRAG/internal/dao"
)

type AdminUserResp struct {
	ID       string `json:"id"`
	Email    string `json:"email"`
	Nickname string `json:"nickname"`
	Role     string `json:"role"`
}

type AdminStatsResp struct {
	TotalUsers     int64 `json:"total_users"`
	TotalDocuments int64 `json:"total_documents"`
	TotalDatasets  int64 `json:"total_datasets"`
	TotalChats     int64 `json:"total_chats"`
}

type UpdateUserRoleReq struct {
	Role string `json:"role" binding:"required,oneof=owner admin normal invite"`
}

func ListTenantUsers(tenantID string) ([]AdminUserResp, error) {
	type result struct {
		ID       string
		Email    string
		Nickname string
		Role     string
	}
	var results []result

	err := dao.DB.Table("user_tenant").
		Select("user.id, user.email, user.nickname, user_tenant.role").
		Joins("left join user on user_tenant.user_id = user.id").
		Where("user_tenant.tenant_id = ?", tenantID).
		Scan(&results).Error

	if err != nil {
		return nil, err
	}

	resp := make([]AdminUserResp, len(results))
	for i, r := range results {
		resp[i] = AdminUserResp{
			ID:       r.ID,
			Email:    r.Email,
			Nickname: r.Nickname,
			Role:     r.Role,
		}
	}
	return resp, nil
}

func UpdateUserRole(tenantID, targetUserID, newRole, currentAdminID string) error {
	var targetUserTenant dao.UserTenant
	if err := dao.DB.Where("tenant_id = ? AND user_id = ?", tenantID, targetUserID).First(&targetUserTenant).Error; err != nil {
		return errors.New("user not found in tenant")
	}

	// Admin Self-Protection: prevent removing own admin role
	if targetUserID == currentAdminID && (newRole != "admin" && newRole != "owner") {
		return errors.New("cannot remove your own administrative privileges")
	}

	// Last-Admin Invariant: ensure at least one owner/admin remains
	if targetUserTenant.Role == "owner" || targetUserTenant.Role == "admin" {
		if newRole != "admin" && newRole != "owner" {
			var adminCount int64
			dao.DB.Model(&dao.UserTenant{}).
				Where("tenant_id = ? AND (role = 'owner' OR role = 'admin')", tenantID).
				Count(&adminCount)

			if adminCount <= 1 {
				return errors.New("cannot remove the last administrator from the tenant")
			}
		}
	}

	return dao.DB.Model(&dao.UserTenant{}).
		Where("tenant_id = ? AND user_id = ?", tenantID, targetUserID).
		Update("role", newRole).Error
}

func RemoveUserFromTenant(tenantID, targetUserID, currentAdminID string) error {
	var targetUserTenant dao.UserTenant
	if err := dao.DB.Where("tenant_id = ? AND user_id = ?", tenantID, targetUserID).First(&targetUserTenant).Error; err != nil {
		return errors.New("user not found in tenant")
	}

	if targetUserID == currentAdminID {
		return errors.New("cannot remove yourself from the tenant")
	}

	if targetUserTenant.Role == "owner" || targetUserTenant.Role == "admin" {
		var adminCount int64
		dao.DB.Model(&dao.UserTenant{}).
			Where("tenant_id = ? AND (role = 'owner' OR role = 'admin')", tenantID).
			Count(&adminCount)

		if adminCount <= 1 {
			return errors.New("cannot remove the last administrator from the tenant")
		}
	}

	return dao.DB.Where("tenant_id = ? AND user_id = ?", tenantID, targetUserID).Delete(&dao.UserTenant{}).Error
}

func GetTenantStats(tenantID string) (*AdminStatsResp, error) {
	var users int64
	var docs int64
	var datasets int64
	var chats int64

	// Since we are tenant-scoped, we query resources belonging to this tenant
	dao.DB.Model(&dao.UserTenant{}).Where("tenant_id = ?", tenantID).Count(&users)
	dao.DB.Model(&dao.Document{}).Where("tenant_id = ?", tenantID).Count(&docs)
	dao.DB.Model(&dao.Dataset{}).Where("tenant_id = ?", tenantID).Count(&datasets)
	dao.DB.Model(&dao.ChatSession{}).Where("tenant_id = ?", tenantID).Count(&chats)

	return &AdminStatsResp{
		TotalUsers:     users,
		TotalDocuments: docs,
		TotalDatasets:  datasets,
		TotalChats:     chats,
	}, nil
}
