package main

import (
	"log"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/google/uuid"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func main() {
	dsn := "ragflow:ragflow@tcp(127.0.0.1:13306)/rag_flow?charset=utf8mb4&parseTime=True&loc=Local"
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		log.Fatal(err)
	}

	tenantID := uuid.NewString()
	tenant := dao.Tenant{
		ID:   tenantID,
		Name: "Demo Tenant",
	}
	if err := db.Create(&tenant).Error; err != nil {
		log.Println("Tenant exist or err:", err)
	}

	var user dao.User
	if err := db.Where("email = ?", "test@example.com").First(&user).Error; err != nil {
		log.Fatal("User not found")
	}

	userTenant := dao.UserTenant{
		UserID: user.ID,
		TenantID: tenantID,
		Role: "admin",
	}
	db.Create(&userTenant)
	log.Println("User updated with TenantID:", tenantID)
}
