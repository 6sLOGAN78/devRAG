package storage

import (
	"context"
	"fmt"
	"io"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

var Client *minio.Client
var BucketName = "devrag-documents"

func InitMinIO(cfg *config.Config) error {
	useSSL := false 
	client, err := minio.New(cfg.MinIO.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIO.AccessKey, cfg.MinIO.SecretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return fmt.Errorf("failed to initialize MinIO client: %w", err)
	}

	Client = client

	// Ensure bucket exists
	ctx := context.Background()
	exists, err := Client.BucketExists(ctx, BucketName)
	if err != nil {
		return fmt.Errorf("failed to check if bucket exists: %w", err)
	}
	
	if !exists {
		err = Client.MakeBucket(ctx, BucketName, minio.MakeBucketOptions{})
		if err != nil {
			return fmt.Errorf("failed to create bucket: %w", err)
		}
	}

	return nil
}

func PutObject(ctx context.Context, objectName string, reader io.Reader, objectSize int64, contentType string) error {
	_, err := Client.PutObject(ctx, BucketName, objectName, reader, objectSize, minio.PutObjectOptions{
		ContentType: contentType,
	})
	return err
}

func GetObject(ctx context.Context, objectName string) (*minio.Object, error) {
	return Client.GetObject(ctx, BucketName, objectName, minio.GetObjectOptions{})
}

func DeleteObject(ctx context.Context, objectName string) error {
	return Client.RemoveObject(ctx, BucketName, objectName, minio.RemoveObjectOptions{})
}

func ObjectExists(ctx context.Context, objectName string) (bool, error) {
	_, err := Client.StatObject(ctx, BucketName, objectName, minio.StatObjectOptions{})
	if err != nil {
		if minio.ToErrorResponse(err).Code == "NoSuchKey" {
			return false, nil
		}
		return false, err
	}
	return true, nil
}
