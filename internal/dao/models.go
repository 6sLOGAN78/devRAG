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
