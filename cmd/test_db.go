package main

import (
	"fmt"
	"log"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
)

func main() {
	cfg, err := config.LoadConfig("conf/service_conf.yaml")
	if err != nil {
		log.Fatal(err)
	}

	err = dao.InitDB(cfg)
	if err != nil {
		log.Fatal(err)
	}

	// Auto Migrate
	err = dao.DB.AutoMigrate(&dao.Tenant{}, &dao.User{}, &dao.UserTenant{})
	if err != nil {
		log.Fatal("AutoMigrate failed: ", err)
	}

	// Insert test data
	tenant := dao.Tenant{ID: "t-go", Name: "Go Tenant"}
	dao.DB.Create(&tenant)

	user := dao.User{ID: "u-go", Email: "go@devrag.local", PasswordHash: "hash"}
	dao.DB.Create(&user)

	ut := dao.UserTenant{UserID: "u-go", TenantID: "t-go", Role: "owner"}
	dao.DB.Create(&ut)

	fmt.Println("Go migration and insertion successful.")
}
