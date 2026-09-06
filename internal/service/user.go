package service

import (
	"context"
	"errors"
	"strings"

	"github.com/6sLOGAN78/devRAG/internal/auth"
	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/6sLOGAN78/devRAG/internal/session"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrUserExists   = errors.New("user already exists")
	ErrUserNotFound = errors.New("invalid credentials")
	ErrInvalidCreds = errors.New("invalid credentials")
)

type RegisterReq struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=8"`
	Nickname string `json:"nickname"`
}

type LoginReq struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

type LoginRes struct {
	Token    string `json:"token"`
	ID       string `json:"id"`
	Email    string `json:"email"`
	Nickname string `json:"nickname"`
	TenantID string `json:"tenant_id"`
	Role     string `json:"role"`
}

func Register(req RegisterReq) error {
	email := strings.ToLower(strings.TrimSpace(req.Email))

	var existing dao.User
	if err := dao.DB.Where("email = ?", email).First(&existing).Error; err == nil {
		return ErrUserExists
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}

	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		return err
	}

	user := dao.User{
		ID:           uuid.New().String(),
		Email:        email,
		PasswordHash: hash,
		Nickname:     req.Nickname,
	}

	return dao.DB.Create(&user).Error
}

func Login(ctx context.Context, req LoginReq, cfg *config.Config) (*LoginRes, error) {
	email := strings.ToLower(strings.TrimSpace(req.Email))

	var user dao.User
	if err := dao.DB.Where("email = ?", email).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrInvalidCreds
		}
		return nil, err
	}

	if !auth.CheckPasswordHash(req.Password, user.PasswordHash) {
		return nil, ErrInvalidCreds
	}

	sessionID := uuid.New().String()
	token, err := auth.GenerateToken(user.ID, sessionID, cfg.Auth.JWTSecret, cfg.Auth.JWTExpirationMinutes)
	if err != nil {
		return nil, err
	}

	if err := session.CreateSession(ctx, user.ID, sessionID, cfg.Auth.SessionTTLMinutes); err != nil {
		return nil, err
	}

	tenantID, role, _ := ResolveTenantContext(user.ID, "")

	return &LoginRes{
		Token:    token,
		ID:       user.ID,
		Email:    user.Email,
		Nickname: user.Nickname,
		TenantID: tenantID,
		Role:     role,
	}, nil
}
