package unit_test

import (
	"github.com/6sLOGAN78/devRAG/internal/auth"
	"testing"
)

func TestPasswordHashing(t *testing.T) {
	password := "SecretP@ssword1"

	hash, err := auth.HashPassword(password)
	if err != nil {
		t.Fatalf("Failed to hash password: %v", err)
	}

	if hash == password {
		t.Fatal("Hash should not be equal to plaintext password")
	}

	if !auth.CheckPasswordHash(password, hash) {
		t.Fatal("Valid password should match the hash")
	}

	if auth.CheckPasswordHash("WrongPassword", hash) {
		t.Fatal("Invalid password should not match the hash")
	}

	hash2, _ := auth.HashPassword(password)
	if hash == hash2 {
		t.Fatal("Two hashes of the same password should differ due to salting")
	}
}
