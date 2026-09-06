package service

import (
	"errors"

	"github.com/6sLOGAN78/devRAG/internal/dao"
)

var (
	ErrTenantNotFound = errors.New("tenant not found")
	ErrUnauthorizedTenant = errors.New("unauthorized tenant access")
)

func ResolveTenantContext(userID, requestedTenantID string) (string, error) {
	var userTenants []dao.UserTenant
	if err := dao.DB.Where("user_id = ?", userID).Find(&userTenants).Error; err != nil {
		return "", err
	}

	if len(userTenants) == 0 {
		return "", ErrUnauthorizedTenant
	}

	if requestedTenantID != "" {
		for _, ut := range userTenants {
			if ut.TenantID == requestedTenantID {
				return requestedTenantID, nil
			}
		}
		return "", ErrUnauthorizedTenant
	}

	// Default to first tenant if none requested
	return userTenants[0].TenantID, nil
}
