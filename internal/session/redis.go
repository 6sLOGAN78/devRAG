package session

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/6sLOGAN78/devRAG/internal/dao"
)

type SessionData struct {
	SessionID string `json:"session_id"`
}

func CreateSession(ctx context.Context, userID, sessionID string, ttlMinutes int) error {
	key := fmt.Sprintf("session:%s", userID)
	data := SessionData{SessionID: sessionID}
	bytes, err := json.Marshal(data)
	if err != nil {
		return err
	}

	return dao.RedisClient.Set(ctx, key, string(bytes), time.Duration(ttlMinutes)*time.Minute).Err()
}

func ValidateSession(ctx context.Context, userID, sessionID string) (bool, error) {
	key := fmt.Sprintf("session:%s", userID)
	val, err := dao.RedisClient.Get(ctx, key).Result()
	if err != nil {
		return false, err // key not found or redis error
	}

	var data SessionData
	if err := json.Unmarshal([]byte(val), &data); err != nil {
		return false, err
	}

	return data.SessionID == sessionID, nil
}
