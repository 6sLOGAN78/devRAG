package dao

import (
	"errors"
)

func ListChunksByDocument(documentID, tenantID string) ([]DocumentChunk, error) {
	var chunks []DocumentChunk
	err := DB.Where("document_id = ? AND tenant_id = ?", documentID, tenantID).Order("chunk_index ASC").Find(&chunks).Error
	return chunks, err
}

func GetChunkByID(chunkID, tenantID string) (*DocumentChunk, error) {
	var chunk DocumentChunk
	err := DB.Where("id = ? AND tenant_id = ?", chunkID, tenantID).First(&chunk).Error
	if err != nil {
		return nil, err
	}
	return &chunk, nil
}

func UpdateChunkContent(chunkID, tenantID, content string) error {
	result := DB.Model(&DocumentChunk{}).Where("id = ? AND tenant_id = ?", chunkID, tenantID).Update("content", content)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return errors.New("chunk not found or unauthorized")
	}
	return nil
}

func DeleteChunk(chunkID, tenantID string) error {
	result := DB.Where("id = ? AND tenant_id = ?", chunkID, tenantID).Delete(&DocumentChunk{})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return errors.New("chunk not found or unauthorized")
	}
	return nil
}
