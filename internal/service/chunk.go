package service

import (
	"time"
	"github.com/6sLOGAN78/devRAG/internal/dao"
)

type ChunkDTO struct {
	ID             string    `json:"id"`
	DocumentID     string    `json:"document_id"`
	Content        string    `json:"content"`
	ChunkIndex     int       `json:"chunk_index"`
	ContentType    string    `json:"content_type"`
	PageNumbers    string    `json:"page_numbers"`
	SourceRegions  string    `json:"source_regions"`
	SourceBlockIDs string    `json:"source_block_ids"`
	Metadata       string    `json:"metadata"`
	TokenCount     int       `json:"token_count"`
	Available      int       `json:"available"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

func mapChunkToDTO(c *dao.DocumentChunk) ChunkDTO {
	return ChunkDTO{
		ID:             c.ID,
		DocumentID:     c.DocumentID,
		Content:        c.Content,
		ChunkIndex:     c.ChunkIndex,
		ContentType:    c.ContentType,
		PageNumbers:    c.PageNumbers,
		SourceRegions:  c.SourceRegions,
		SourceBlockIDs: c.SourceBlockIDs,
		Metadata:       c.Metadata,
		TokenCount:     c.TokenCount,
		Available:      c.Available,
		CreatedAt:      c.CreatedAt,
		UpdatedAt:      c.UpdatedAt,
	}
}

func ListChunks(documentID, tenantID string) ([]ChunkDTO, error) {
	chunks, err := dao.ListChunksByDocument(documentID, tenantID)
	if err != nil {
		return nil, err
	}

	dtos := make([]ChunkDTO, len(chunks))
	for i, c := range chunks {
		dtos[i] = mapChunkToDTO(&c)
	}
	return dtos, nil
}

type UpdateChunkReq struct {
	Content string `json:"content" binding:"required"`
}

func UpdateChunk(chunkID, tenantID string, req UpdateChunkReq) error {
	return dao.UpdateChunkContent(chunkID, tenantID, req.Content)
	// TODO: Trigger ML worker to update vector index. For now, this just updates DB.
}

func DeleteChunk(chunkID, tenantID string) error {
	return dao.DeleteChunk(chunkID, tenantID)
	// TODO: Trigger ML worker to delete from vector index.
}
