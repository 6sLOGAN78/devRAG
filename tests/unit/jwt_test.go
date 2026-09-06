package unit_test

import (
	"testing"

	"github.com/6sLOGAN78/devRAG/internal/auth"
)

func TestJWTGenerationAndValidation(t *testing.T) {
	secret := "test-secret"
	userID := "user-123"
	sessionID := "sess-123"

	token, err := auth.GenerateToken(userID, sessionID, secret, 1)
	if err != nil {
		t.Fatalf("Failed to generate token: %v", err)
	}

	claims, err := auth.ValidateToken(token, secret)
	if err != nil {
		t.Fatalf("Failed to validate token: %v", err)
	}

	if claims.UserID != userID || claims.SessionID != sessionID {
		t.Fatal("Claims do not match the expected values")
	}

	// Test invalid signature
	_, err = auth.ValidateToken(token, "wrong-secret")
	if err == nil {
		t.Fatal("Expected error for wrong secret")
	}

	// Test expiration
	expiredToken, _ := auth.GenerateToken(userID, sessionID, secret, -1) // expired 1 minute ago
	_, err = auth.ValidateToken(expiredToken, secret)
	if err == nil {
		t.Fatal("Expected error for expired token")
	}
}
