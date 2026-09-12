package service

import (
	"encoding/json"
	"strings"
	"time"
	"github.com/google/uuid"
	"github.com/6sLOGAN78/devRAG/internal/dao"
)

type CreateDatasetReq struct {
	Name        string `json:"name" binding:"required,max=255"`
	Description string `json:"description" binding:"max=1000"`
	EmbdID      string `json:"embd_id" binding:"max=128"`
	ParserID    string `json:"parser_id" binding:"max=32"`
	ParserConfig map[string]interface{} `json:"parser_config"`
}

type DatasetDTO struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	EmbdID      string    `json:"embd_id"`
	ParserID    string    `json:"parser_id"`
	ParserConfig string    `json:"parser_config"`
	TenantID    string    `json:"tenant_id"`
	CreatedBy   string    `json:"created_by"`
	Status      string    `json:"status"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

func mapDatasetToDTO(ds *dao.Dataset) DatasetDTO {
	return DatasetDTO{
		ID:          ds.ID,
		Name:        ds.Name,
		Description: ds.Description,
		EmbdID:      ds.EmbdID,
		ParserID:    ds.ParserID,
		ParserConfig: ds.ParserConfig,
		TenantID:    ds.TenantID,
		CreatedBy:   ds.CreatedBy,
		Status:      ds.Status,
		CreatedAt:   ds.CreatedAt,
		UpdatedAt:   ds.UpdatedAt,
	}
}

func CreateDataset(tenantID, userID string, req CreateDatasetReq) (DatasetDTO, error) {
	parserID := strings.TrimSpace(req.ParserID)
	if parserID == "" {
		parserID = "naive"
	}
	
	parserConfigStr := "{}"
	if req.ParserConfig != nil {
		b, _ := json.Marshal(req.ParserConfig)
		parserConfigStr = string(b)
	} else {
		parserConfigStr = `{"pages": [[1, 1000000]]}`
	}

	ds := &dao.Dataset{
		ID:          uuid.New().String(),
		Name:        strings.TrimSpace(req.Name),
		Description: strings.TrimSpace(req.Description),
		EmbdID:      strings.TrimSpace(req.EmbdID),
		ParserID:    parserID,
		ParserConfig: parserConfigStr,
		TenantID:    tenantID,
		CreatedBy:   userID,
		Status:      "active",
	}

	if err := dao.CreateDataset(ds); err != nil {
		return DatasetDTO{}, err
	}

	return mapDatasetToDTO(ds), nil
}

func ListDatasets(tenantID string) ([]DatasetDTO, error) {
	datasets, err := dao.ListDatasetsByTenant(tenantID)
	if err != nil {
		return nil, err
	}
	
	dtos := make([]DatasetDTO, len(datasets))
	for i, ds := range datasets {
		dtos[i] = mapDatasetToDTO(&ds)
	}
	return dtos, nil
}

func DeleteDataset(tenantID, datasetID string) error {
	return dao.DeleteDatasetByIDAndTenant(datasetID, tenantID)
}
