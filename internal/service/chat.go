package service

import (
	"encoding/json"
	"errors"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/google/uuid"
)

type CreateSessionReq struct {
	AgentID string `json:"agent_id" binding:"required"`
	Title   string `json:"title"`
}

type UpdateSessionReq struct {
	Title string `json:"title" binding:"required"`
}

type AppendMessageReq struct {
	Role      string          `json:"role" binding:"required"`
	Content   string          `json:"content" binding:"required"`
	Citations json.RawMessage `json:"citations"` // Optional JSON payload
}

type ChatSessionResp struct {
	ID        string    `json:"id"`
	AgentID   string    `json:"agent_id"`
	Title     string    `json:"title"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ChatMessageResp struct {
	ID        string          `json:"id"`
	Role      string          `json:"role"`
	Content   string          `json:"content"`
	Citations json.RawMessage `json:"citations,omitempty"`
	CreatedAt time.Time       `json:"created_at"`
}

func CreateChatSession(userID, tenantID string, req *CreateSessionReq) (*ChatSessionResp, error) {
	// Optionally validate agent_id exists and is accessible
	_, err := dao.GetAgentCanvasByIDAndTenant(req.AgentID, tenantID)
	if err != nil {
		return nil, errors.New("agent not found or unauthorized")
	}

	title := req.Title
	if title == "" {
		title = "New Chat"
	}

	session := &dao.ChatSession{
		ID:       uuid.New().String(),
		UserID:   userID,
		TenantID: tenantID,
		AgentID:  req.AgentID,
		Title:    title,
	}

	if err := dao.CreateChatSession(session); err != nil {
		return nil, err
	}

	return &ChatSessionResp{
		ID:        session.ID,
		AgentID:   session.AgentID,
		Title:     session.Title,
		CreatedAt: session.CreatedAt,
		UpdatedAt: session.UpdatedAt,
	}, nil
}

func ListChatSessions(userID, tenantID string) ([]ChatSessionResp, error) {
	sessions, err := dao.ListSessionsByUser(userID, tenantID)
	if err != nil {
		return nil, err
	}

	resp := make([]ChatSessionResp, len(sessions))
	for i, s := range sessions {
		resp[i] = ChatSessionResp{
			ID:        s.ID,
			AgentID:   s.AgentID,
			Title:     s.Title,
			CreatedAt: s.CreatedAt,
			UpdatedAt: s.UpdatedAt,
		}
	}
	return resp, nil
}

func GetChatSession(id, userID, tenantID string) (*ChatSessionResp, error) {
	s, err := dao.GetSessionByIDAndUser(id, userID, tenantID)
	if err != nil {
		return nil, err
	}
	return &ChatSessionResp{
		ID:        s.ID,
		AgentID:   s.AgentID,
		Title:     s.Title,
		CreatedAt: s.CreatedAt,
		UpdatedAt: s.UpdatedAt,
	}, nil
}

func UpdateChatSession(id, userID, tenantID string, req *UpdateSessionReq) (*ChatSessionResp, error) {
	s, err := dao.GetSessionByIDAndUser(id, userID, tenantID)
	if err != nil {
		return nil, err
	}

	s.Title = req.Title
	if err := dao.UpdateSession(s); err != nil {
		return nil, err
	}

	return &ChatSessionResp{
		ID:        s.ID,
		AgentID:   s.AgentID,
		Title:     s.Title,
		CreatedAt: s.CreatedAt,
		UpdatedAt: s.UpdatedAt,
	}, nil
}

func DeleteChatSession(id, userID, tenantID string) error {
	return dao.DeleteSession(id, userID, tenantID)
}

func AppendMessage(sessionID, userID, tenantID string, req *AppendMessageReq) (*ChatMessageResp, error) {
	// Role validation
	if req.Role != "user" && req.Role != "assistant" && req.Role != "system" && req.Role != "tool" {
		return nil, errors.New("invalid message role")
	}

	// Verify session ownership
	_, err := dao.GetSessionByIDAndUser(sessionID, userID, tenantID)
	if err != nil {
		return nil, err
	}

	var citationsStr string
	if len(req.Citations) > 0 {
		citationsStr = string(req.Citations)
	}

	msg := &dao.ChatMessage{
		ID:        uuid.New().String(),
		SessionID: sessionID,
		TenantID:  tenantID,
		Role:      req.Role,
		Content:   req.Content,
		Citations: citationsStr,
	}

	if err := dao.AppendMessage(msg); err != nil {
		return nil, err
	}

	return &ChatMessageResp{
		ID:        msg.ID,
		Role:      msg.Role,
		Content:   msg.Content,
		Citations: req.Citations,
		CreatedAt: msg.CreatedAt,
	}, nil
}

func GetMessageHistory(sessionID, userID, tenantID string) ([]ChatMessageResp, error) {
	// Verify session ownership first
	_, err := dao.GetSessionByIDAndUser(sessionID, userID, tenantID)
	if err != nil {
		return nil, err
	}

	messages, err := dao.GetMessagesBySession(sessionID, tenantID)
	if err != nil {
		return nil, err
	}

	resp := make([]ChatMessageResp, len(messages))
	for i, m := range messages {
		resp[i] = ChatMessageResp{
			ID:        m.ID,
			Role:      m.Role,
			Content:   m.Content,
			CreatedAt: m.CreatedAt,
		}
		if m.Citations != "" && m.Citations != "null" {
			resp[i].Citations = json.RawMessage(m.Citations)
		}
	}
	return resp, nil
}
