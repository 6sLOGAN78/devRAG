package dao

import (
	"time"
)

type Tenant struct {
	ID        string    `gorm:"column:id;type:varchar(36);primaryKey"`
	Name      string    `gorm:"column:name;type:varchar(255);not null"`
	LLMID     string    `gorm:"column:llm_id;type:varchar(255)"`
	CreatedAt time.Time `gorm:"column:created_at;autoCreateTime"`
}

func (Tenant) TableName() string {
	return "tenant"
}

type User struct {
	ID           string `gorm:"column:id;type:varchar(36);primaryKey"`
	Email        string `gorm:"column:email;type:varchar(255);uniqueIndex;not null"`
	PasswordHash string `gorm:"column:password_hash;type:varchar(255);not null"`
	Nickname     string `gorm:"column:nickname;type:varchar(255)"`
}

func (User) TableName() string {
	return "user"
}

type UserTenant struct {
	UserID   string `gorm:"column:user_id;type:varchar(36);not null;uniqueIndex:idx_user_tenant"`
	TenantID string `gorm:"column:tenant_id;type:varchar(36);not null;uniqueIndex:idx_user_tenant"`
	Role     string `gorm:"column:role;type:enum('owner','admin','normal','invite');not null"`
}

func (UserTenant) TableName() string {
	return "user_tenant"
}

type Dataset struct {
	ID          string    `gorm:"column:id;type:varchar(36);primaryKey"`
	Name        string    `gorm:"column:name;type:varchar(255);not null"`
	Description string    `gorm:"column:description;type:text"`
	TenantID    string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	CreatedBy   string    `gorm:"column:created_by;type:varchar(36);not null;index"`
	Status      string    `gorm:"column:status;type:varchar(50);not null;default:'active'"`
	CreatedAt   time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt   time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (Dataset) TableName() string {
	return "dataset"
}

type Document struct {
	ID          string    `gorm:"column:id;type:varchar(36);primaryKey"`
	DatasetID   string    `gorm:"column:dataset_id;type:varchar(36);not null;index"`
	TenantID    string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	Name        string    `gorm:"column:name;type:varchar(255);not null"`
	Size        int64     `gorm:"column:size;not null"`
	Type        string    `gorm:"column:type;type:varchar(100);not null"`
	MinioPath   string    `gorm:"column:minio_path;type:varchar(500);not null"`
	ParseStatus string    `gorm:"column:parse_status;type:varchar(50);not null;default:'pending'"`
	CreatedBy   string    `gorm:"column:created_by;type:varchar(36);not null;index"`
	CreatedAt   time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt   time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (Document) TableName() string {
	return "document"
}

type DocumentTask struct {
	ID         string    `gorm:"column:id;type:varchar(36);primaryKey"`
	DocumentID string    `gorm:"column:document_id;type:varchar(36);not null;index"`
	TenantID   string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	Status     string    `gorm:"column:status;type:varchar(50);not null;default:'unstart'"`
	Progress   int       `gorm:"column:progress;not null;default:0"`
	ErrorMsg   string    `gorm:"column:error_msg;type:text"`
	CreatedAt  time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt  time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (DocumentTask) TableName() string {
	return "document_task"
}

type DocumentChunk struct {
	ID               string    `gorm:"column:id;type:varchar(36);primaryKey"`
	DocumentID       string    `gorm:"column:document_id;type:varchar(36);not null;index:idx_doc_chunk"`
	TenantID         string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	Content          string    `gorm:"column:content;type:longtext;not null"`
	ChunkIndex       int       `gorm:"column:chunk_index;not null;index:idx_doc_chunk"`
	ContentType      string    `gorm:"column:content_type;type:varchar(50);not null;default:'text'"`
	PageNumbers      string    `gorm:"column:page_numbers;type:json"`
	SourceRegions    string    `gorm:"column:source_regions;type:json"`
	SourceBlockIDs   string    `gorm:"column:source_block_ids;type:json"`
	Metadata         string    `gorm:"column:metadata;type:json"`
	TokenCount       int       `gorm:"column:token_count;not null;default:0"`
	CreatedAt        time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt        time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (DocumentChunk) TableName() string {
	return "document_chunk"
}
