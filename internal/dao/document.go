package dao

import (
	"errors"
	"gorm.io/gorm"
)

var ErrDocumentNotFound = errors.New("document not found")

func CreateDocument(doc *Document) error {
	return DB.Create(doc).Error
}

func ListDocuments(tenantID, datasetID string) ([]Document, error) {
	var docs []Document
	err := DB.Where("tenant_id = ? AND dataset_id = ?", tenantID, datasetID).Order("created_at desc").Find(&docs).Error
	return docs, err
}

func GetDocumentByIDAndTenant(docID, tenantID string) (*Document, error) {
	var doc Document
	if err := DB.Where("id = ? AND tenant_id = ?", docID, tenantID).First(&doc).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrDocumentNotFound
		}
		return nil, err
	}
	return &doc, nil
}

func DeleteDocumentByIDAndTenant(docID, tenantID string) error {
	res := DB.Where("id = ? AND tenant_id = ?", docID, tenantID).Delete(&Document{})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrDocumentNotFound
	}
	return nil
}
