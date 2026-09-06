package dao

import (
	"errors"
	"gorm.io/gorm"
)

var ErrCanvasNotFound = errors.New("canvas not found")

func SaveAgentCanvas(canvas *AgentCanvas) error {
	// Upsert semantics based on ID
	var existing AgentCanvas
	err := DB.Where("id = ? AND tenant_id = ?", canvas.ID, canvas.TenantID).First(&existing).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			// Create
			return DB.Create(canvas).Error
		}
		return err
	}

	// Update existing
	canvas.Version = existing.Version + 1
	canvas.CreatedAt = existing.CreatedAt // Preserve creation time
	return DB.Save(canvas).Error
}

func GetAgentCanvasByIDAndTenant(id, tenantID string) (*AgentCanvas, error) {
	var canvas AgentCanvas
	if err := DB.Where("id = ? AND tenant_id = ?", id, tenantID).First(&canvas).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrCanvasNotFound
		}
		return nil, err
	}
	return &canvas, nil
}
