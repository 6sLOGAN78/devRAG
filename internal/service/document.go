package service

import (
	"context"
	"errors"
	"fmt"
	"mime/multipart"
	"path/filepath"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/storage"
)

type DocumentDTO struct {
	ID          string    `json:"id"`
	DatasetID   string    `json:"dataset_id"`
	TenantID    string    `json:"tenant_id"`
	Name        string    `json:"name"`
	Size        int64     `json:"size"`
	Type        string    `json:"type"`
	MinioPath   string    `json:"minio_path"`
	ParseStatus string    `json:"parse_status"`
	CreatedBy   string    `json:"created_by"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

func mapDocumentToDTO(doc *dao.Document) DocumentDTO {
	return DocumentDTO{
		ID:          doc.ID,
		DatasetID:   doc.DatasetID,
		TenantID:    doc.TenantID,
		Name:        doc.Name,
		Size:        doc.Size,
		Type:        doc.Type,
		MinioPath:   doc.MinioPath,
		ParseStatus: doc.ParseStatus,
		CreatedBy:   doc.CreatedBy,
		CreatedAt:   doc.CreatedAt,
		UpdatedAt:   doc.UpdatedAt,
	}
}

func UploadDocument(ctx context.Context, tenantID, userID, datasetID string, file *multipart.FileHeader) (*DocumentDTO, error) {
	// 1. Verify Dataset belongs to current tenant
	_, err := dao.GetDatasetByIDAndTenant(datasetID, tenantID)
	if err != nil {
		if errors.Is(err, dao.ErrDatasetNotFound) {
			return nil, errors.New("dataset not found or access denied")
		}
		return nil, err
	}

	// 2. Validate file
	filename := filepath.Base(file.Filename)
	if filename == "" {
		return nil, errors.New("invalid filename")
	}

	contentType := file.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	src, err := file.Open()
	if err != nil {
		return nil, err
	}
	defer src.Close()

	// 3. Generate IDs and Minio Path
	docID := uuid.New().String()
	minioPath := fmt.Sprintf("tenant/%s/dataset/%s/document/%s/original", tenantID, datasetID, docID)

	// 4. Upload object to MinIO
	if err := storage.PutObject(ctx, minioPath, src, file.Size, contentType); err != nil {
		return nil, fmt.Errorf("failed to upload to storage: %w", err)
	}

	// 5. Create DB Document record
	doc := &dao.Document{
		ID:          docID,
		DatasetID:   datasetID,
		TenantID:    tenantID,
		Name:        strings.TrimSpace(filename),
		Size:        file.Size,
		Type:        contentType,
		MinioPath:   minioPath,
		ParseStatus: "pending",
		CreatedBy:   userID,
	}

	taskID := uuid.New().String()
	task := &dao.DocumentTask{
		ID:         taskID,
		DocumentID: docID,
		TenantID:   tenantID,
		Status:     "unstart",
		Progress:   0,
	}

	if err := dao.CreateDocumentWithTask(doc, task); err != nil {
		// Attempt to cleanup MinIO on DB failure
		_ = storage.DeleteObject(context.Background(), minioPath)
		return nil, fmt.Errorf("failed to create document record: %w", err)
	}

	dto := mapDocumentToDTO(doc)
	return &dto, nil
}

func ListDocuments(tenantID, datasetID string) ([]DocumentDTO, error) {
	// Validate dataset ownership
	_, err := dao.GetDatasetByIDAndTenant(datasetID, tenantID)
	if err != nil {
		return nil, errors.New("dataset not found or access denied")
	}

	docs, err := dao.ListDocuments(tenantID, datasetID)
	if err != nil {
		return nil, err
	}

	dtos := make([]DocumentDTO, len(docs))
	for i, doc := range docs {
		dtos[i] = mapDocumentToDTO(&doc)
	}
	return dtos, nil
}

func DeleteDocument(ctx context.Context, tenantID, docID string) error {
	doc, err := dao.GetDocumentByIDAndTenant(docID, tenantID)
	if err != nil {
		return err
	}

	// Delete from Minio first (or DB first) - choosing Minio first. If Minio succeeds but DB fails, it's a soft-orphaned DB record.
	// The instructions suggest: "If DB deletion happens before object deletion, the orphan-object implications must be explicitly considered."
	// Let's delete DB first. If it succeeds, the document is logically deleted. Then we delete from Minio.
	// If Minio fails, we have an orphaned object but the app continues correctly.
	err = dao.DeleteDocumentByIDAndTenant(docID, tenantID)
	if err != nil {
		return err
	}

	err = storage.DeleteObject(ctx, doc.MinioPath)
	if err != nil {
		// Log cleanup failure - in real app would use a logger, here just return or ignore
		fmt.Printf("Failed to delete minio object %s: %v\n", doc.MinioPath, err)
	}

	return nil
}
