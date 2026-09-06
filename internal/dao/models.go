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
	EmbdID      string    `gorm:"column:embd_id;type:varchar(128)"`
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

type AgentCanvas struct {
	ID              string    `gorm:"column:id;type:varchar(36);primaryKey"`
	TenantID        string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	Name            string    `gorm:"column:name;type:varchar(255);not null"`
	Description     string    `gorm:"column:description;type:varchar(1000)"`
	GraphDefinition string    `gorm:"column:graph_definition;type:text;not null"`
	Version         int       `gorm:"column:version;not null;default:1"`
	CreatedBy       string    `gorm:"column:created_by;type:varchar(36);not null"`
	CreatedAt       time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt       time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (AgentCanvas) TableName() string {
	return "agent_canvas"
}

type ChatSession struct {
	ID        string    `gorm:"column:id;type:varchar(36);primaryKey"`
	UserID    string    `gorm:"column:user_id;type:varchar(36);not null;index:idx_user_session"`
	TenantID  string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	AgentID   string    `gorm:"column:agent_id;type:varchar(36);not null;index"`
	Title     string    `gorm:"column:title;type:varchar(255)"`
	CreatedAt time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (ChatSession) TableName() string {
	return "chat_session"
}

type ChatMessage struct {
	ID        string    `gorm:"column:id;type:varchar(36);primaryKey"`
	SessionID string    `gorm:"column:session_id;type:varchar(36);not null;index:idx_session_msg"`
	TenantID  string    `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	Role      string    `gorm:"column:role;type:varchar(50);not null"`
	Content   string    `gorm:"column:content;type:longtext;not null"`
	Citations string    `gorm:"column:citations;type:json"`
	CreatedAt time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (ChatMessage) TableName() string {
	return "chat_message"
}

type TenantLLM struct {
	ID        string    `gorm:"column:id;type:varchar(36);primaryKey"`
	TenantID  string    `gorm:"column:tenant_id;type:varchar(36);not null;index:idx_tenant_llm,unique"`
	Factory   string    `gorm:"column:llm_factory;type:varchar(128);not null;index:idx_tenant_llm,unique"`
	Name      string    `gorm:"column:llm_name;type:varchar(128);not null;index:idx_tenant_llm,unique"`
	APIKey    string    `gorm:"column:api_key;type:text"`
	APIBase   string    `gorm:"column:api_base;type:varchar(255)"`
	CreatedAt time.Time `gorm:"column:created_at;autoCreateTime"`
	UpdatedAt time.Time `gorm:"column:updated_at;autoUpdateTime"`
}

func (TenantLLM) TableName() string {
	return "tenant_llm"
}
