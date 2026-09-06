package service

import (
	"errors"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

type TenantLLMDTO struct {
	ID        string    `json:"id"`
	Factory   string    `json:"llm_factory"`
	Name      string    `json:"llm_name"`
	APIBase   string    `json:"api_base"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type UpdateTenantLLMReq struct {
	Factory string `json:"llm_factory" binding:"required"`
	Name    string `json:"llm_name" binding:"required"`
	APIKey  string `json:"api_key" binding:"required"`
	APIBase string `json:"api_base"`
}

func ListTenantLLMs(tenantID string) ([]TenantLLMDTO, error) {
	var llms []dao.TenantLLM
	if err := dao.DB.Where("tenant_id = ?", tenantID).Find(&llms).Error; err != nil {
		return nil, err
	}

	res := make([]TenantLLMDTO, len(llms))
	for i, l := range llms {
		res[i] = TenantLLMDTO{
			ID:        l.ID,
			Factory:   l.Factory,
			Name:      l.Name,
			APIBase:   l.APIBase,
			CreatedAt: l.CreatedAt,
			UpdatedAt: l.UpdatedAt,
		}
	}
	return res, nil
}

func UpdateTenantLLM(tenantID string, req UpdateTenantLLMReq) (TenantLLMDTO, error) {
	var llm dao.TenantLLM
	err := dao.DB.Where("tenant_id = ? AND llm_factory = ? AND llm_name = ?", tenantID, req.Factory, req.Name).First(&llm).Error

	if errors.Is(err, gorm.ErrRecordNotFound) {
		// Create new
		llm = dao.TenantLLM{
			ID:       uuid.New().String(),
			TenantID: tenantID,
			Factory:  req.Factory,
			Name:     req.Name,
			APIKey:   req.APIKey,
			APIBase:  req.APIBase,
		}
		if err := dao.DB.Create(&llm).Error; err != nil {
			return TenantLLMDTO{}, err
		}
	} else if err == nil {
		// Update existing
		llm.APIKey = req.APIKey
		llm.APIBase = req.APIBase
		if err := dao.DB.Save(&llm).Error; err != nil {
			return TenantLLMDTO{}, err
		}
	} else {
		return TenantLLMDTO{}, err
	}

	return TenantLLMDTO{
		ID:        llm.ID,
		Factory:   llm.Factory,
		Name:      llm.Name,
		APIBase:   llm.APIBase,
		CreatedAt: llm.CreatedAt,
		UpdatedAt: llm.UpdatedAt,
	}, nil
}

func DeleteTenantLLM(tenantID, id string) error {
	res := dao.DB.Where("id = ? AND tenant_id = ?", id, tenantID).Delete(&dao.TenantLLM{})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return errors.New("not found")
	}
	return nil
}
