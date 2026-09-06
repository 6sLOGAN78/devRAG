package dao

import (
	"errors"

	"gorm.io/gorm"
)

var ErrChatSessionNotFound = errors.New("chat session not found")

func CreateChatSession(session *ChatSession) error {
	return DB.Create(session).Error
}

func GetSessionByIDAndUser(id, userID, tenantID string) (*ChatSession, error) {
	var session ChatSession
	if err := DB.Where("id = ? AND user_id = ? AND tenant_id = ?", id, userID, tenantID).First(&session).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrChatSessionNotFound
		}
		return nil, err
	}
	return &session, nil
}

func ListSessionsByUser(userID, tenantID string) ([]ChatSession, error) {
	var sessions []ChatSession
	err := DB.Where("user_id = ? AND tenant_id = ?", userID, tenantID).Order("updated_at desc").Find(&sessions).Error
	return sessions, err
}

func UpdateSession(session *ChatSession) error {
	return DB.Save(session).Error
}

func DeleteSession(id, userID, tenantID string) error {
	return DB.Transaction(func(tx *gorm.DB) error {
		// Verify ownership
		var session ChatSession
		if err := tx.Where("id = ? AND user_id = ? AND tenant_id = ?", id, userID, tenantID).First(&session).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrChatSessionNotFound
			}
			return err
		}

		// Delete messages first to maintain integrity
		if err := tx.Where("session_id = ? AND tenant_id = ?", id, tenantID).Delete(&ChatMessage{}).Error; err != nil {
			return err
		}

		// Delete session
		if err := tx.Delete(&session).Error; err != nil {
			return err
		}

		return nil
	})
}

func AppendMessage(message *ChatMessage) error {
	return DB.Create(message).Error
}

func GetMessagesBySession(sessionID, tenantID string) ([]ChatMessage, error) {
	var messages []ChatMessage
	// Ordering by created_at ensures deterministic conversation order
	err := DB.Where("session_id = ? AND tenant_id = ?", sessionID, tenantID).Order("created_at asc").Find(&messages).Error
	return messages, err
}
