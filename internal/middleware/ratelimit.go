package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"
	"log/slog"

	"github.com/6sLOGAN78/devRAG/internal/config"
	"github.com/6sLOGAN78/devRAG/internal/dao"
	"github.com/gin-gonic/gin"
)

// tokenBucketScript uses Redis Lua to atomically update the token bucket.
const tokenBucketScript = `
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local state = redis.call('HMGET', bucket_key, 'tokens', 'last_refill')
local tokens = tonumber(state[1])
local last_refill = tonumber(state[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

if last_refill == nil then
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
local refill_tokens = math.floor(elapsed * refill_rate)

if refill_tokens > 0 then
    tokens = math.min(capacity, tokens + refill_tokens)
    last_refill = now
end

local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

-- Expire the key if unused for twice the time it takes to fully refill
local expire_time = math.ceil((capacity / refill_rate) * 2)

redis.call('HMSET', bucket_key, 'tokens', tokens, 'last_refill', last_refill)
redis.call('EXPIRE', bucket_key, expire_time)

return {allowed, tokens, capacity}
`

type LimitPolicy struct {
	Capacity   int
	RefillRate float64 // tokens per second
	Cost       int
}

func GetPolicy(path string, cfg *config.Config) LimitPolicy {
	if strings.Contains(path, "/chat/session") || strings.Contains(path, "/message") {
		return LimitPolicy{Capacity: 10, RefillRate: 1, Cost: 1} // Stricter chat policy
	}
	if strings.Contains(path, "/chat/completions") {
		return LimitPolicy{Capacity: 10, RefillRate: 1, Cost: 1} // Stricter chat policy
	}
	if strings.Contains(path, "/document/upload") {
		return LimitPolicy{Capacity: 5, RefillRate: 0.5, Cost: 1} // Stricter upload policy
	}
	// Default
	return LimitPolicy{Capacity: 100, RefillRate: 10, Cost: 1}
}

// RateLimit middleware
func RateLimit(cfg *config.Config, logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		reqID := c.GetString("request_id")
		userID, exists := c.Get("user_id")
		
		var identity string
		if exists {
			identity = userID.(string)
		} else {
			identity = c.ClientIP()
		}

		policy := GetPolicy(c.Request.URL.Path, cfg)
		bucketKey := fmt.Sprintf("ratelimit:%s:%s", identity, c.Request.URL.Path)

		// Short bounded timeout for Redis operation
		ctx, cancel := context.WithTimeout(c.Request.Context(), 100*time.Millisecond)
		defer cancel()

		now := time.Now().Unix()

		res, err := dao.RedisClient.Eval(ctx, tokenBucketScript, []string{bucketKey}, policy.Capacity, policy.RefillRate, policy.Cost, now).Result()
		if err != nil {
			// Fail-open policy if Redis goes down, we log and proceed to protect availability.
			logger.Warn("Rate limiter Redis failure, failing open",
				slog.String("request_id", reqID),
				slog.String("error", err.Error()),
			)
			c.Next()
			return
		}

		result := res.([]interface{})
		allowed := result[0].(int64) == 1
		remaining := result[1].(int64)
		limit := result[2].(int64)

		c.Header("X-RateLimit-Limit", strconv.FormatInt(limit, 10))
		c.Header("X-RateLimit-Remaining", strconv.FormatInt(remaining, 10))

		if !allowed {
			// Compute retry-after in seconds based on cost and refill rate
			retryAfter := int(float64(policy.Cost) / policy.RefillRate)
			if retryAfter < 1 {
				retryAfter = 1
			}
			c.Header("Retry-After", strconv.Itoa(retryAfter))
			
			logger.Warn("Rate limit exceeded",
				slog.String("request_id", reqID),
				slog.String("identity", identity),
				slog.String("route", c.Request.URL.Path),
				slog.Int("limit", policy.Capacity),
			)
			
			// Standardized JSON error response
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": gin.H{
					"code":       "RATE_LIMITED",
					"message":    "Too many requests",
					"request_id": reqID,
				},
			})
			c.Abort()
			return
		}

		c.Next()
	}
}
