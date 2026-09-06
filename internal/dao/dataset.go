package dao

import (
	"errors"
	"gorm.io/gorm"
)

var ErrDatasetNotFound = errors.New("dataset not found")

func CreateDataset(ds *Dataset) error {
	return DB.Create(ds).Error
}

func ListDatasetsByTenant(tenantID string) ([]Dataset, error) {
	var datasets []Dataset
	err := DB.Where("tenant_id = ?", tenantID).Order("created_at desc").Find(&datasets).Error
	return datasets, err
}

func GetDatasetByIDAndTenant(datasetID, tenantID string) (*Dataset, error) {
	var ds Dataset
	if err := DB.Where("id = ? AND tenant_id = ?", datasetID, tenantID).First(&ds).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrDatasetNotFound
		}
		return nil, err
	}
	return &ds, nil
}

func DeleteDatasetByIDAndTenant(datasetID, tenantID string) error {
	res := DB.Where("id = ? AND tenant_id = ?", datasetID, tenantID).Delete(&Dataset{})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrDatasetNotFound
	}
	return nil
}
