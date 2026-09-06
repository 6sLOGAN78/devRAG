package api

import (
	"github.com/gin-gonic/gin"
)

type APIError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	RequestID string `json:"request_id,omitempty"`
}

type ErrorResponse struct {
	Error APIError `json:"error"`
}

func RespondError(c *gin.Context, status int, code, message string) {
	reqID := c.GetString("request_id")
	c.JSON(status, ErrorResponse{
		Error: APIError{
			Code:      code,
			Message:   message,
			RequestID: reqID,
		},
	})
	c.Abort()
}
