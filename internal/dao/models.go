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
