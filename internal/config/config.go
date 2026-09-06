package config

import (
	"fmt"
	"os"
	"regexp"

	"gopkg.in/yaml.v3"
)

type Config struct {
	MySQL    MySQLConfig    `yaml:"mysql" json:"mysql"`
	Redis    RedisConfig    `yaml:"redis" json:"redis"`
	MinIO    MinIOConfig    `yaml:"minio" json:"minio"`
	Infinity InfinityConfig `yaml:"infinity" json:"infinity"`
	NATS     NATSConfig     `yaml:"nats" json:"nats"`
	RAGFlow  RAGFlowConfig  `yaml:"ragflow" json:"ragflow"`
	Auth     AuthConfig     `yaml:"auth" json:"auth"`
	Syncer   SyncerConfig   `yaml:"syncer" json:"syncer"`
}

type SyncerConfig struct {
	PollIntervalSec int `yaml:"poll_interval_sec" json:"poll_interval_sec"`
	BatchSize       int `yaml:"batch_size" json:"batch_size"`
	MaxInFlight     int `yaml:"max_in_flight" json:"max_in_flight"`
}

type MySQLConfig struct {
	Host     string `yaml:"host" json:"host"`
	Port     int    `yaml:"port" json:"port"`
	User     string `yaml:"user" json:"user"`
	Password string `yaml:"password" json:"password"`
	DB       string `yaml:"db" json:"db"`
}

type RedisConfig struct {
	Host string `yaml:"host" json:"host"`
	Port int    `yaml:"port" json:"port"`
	DB   int    `yaml:"db" json:"db"`
}

type MinIOConfig struct {
	Endpoint  string `yaml:"endpoint" json:"endpoint"`
	AccessKey string `yaml:"access_key" json:"access_key"`
	SecretKey string `yaml:"secret_key" json:"secret_key"`
}

type InfinityConfig struct {
	Host string `yaml:"host" json:"host"`
	Port int    `yaml:"port" json:"port"`
}

type NATSConfig struct {
	Endpoints string `yaml:"endpoints" json:"endpoints"`
}

type AuthConfig struct {
	JWTSecret            string `yaml:"jwt_secret" json:"jwt_secret"`
	JWTExpirationMinutes int    `yaml:"jwt_expiration_minutes" json:"jwt_expiration_minutes"`
	SessionTTLMinutes    int    `yaml:"session_ttl_minutes" json:"session_ttl_minutes"`
}

type RAGFlowConfig struct {
	GoPort     int `yaml:"go_port" json:"go_port"`
	PythonPort int `yaml:"python_port" json:"python_port"`
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("could not read config file: %v", err)
	}

	expanded := expandEnv(string(data))

	var cfg Config
	if err := yaml.Unmarshal([]byte(expanded), &cfg); err != nil {
		return nil, fmt.Errorf("could not unmarshal yaml: %v", err)
	}

	if err := validate(&cfg); err != nil {
		return nil, fmt.Errorf("configuration error: %v", err)
	}

	return &cfg, nil
}

func expandEnv(s string) string {
	re := regexp.MustCompile(`\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}`)
	return re.ReplaceAllStringFunc(s, func(match string) string {
		sub := re.FindStringSubmatch(match)
		key := sub[1]
		defaultVal := sub[2]

		val := os.Getenv(key)
		if val == "" {
			return defaultVal
		}
		return val
	})
}

func validate(c *Config) error {
	if c.MySQL.Host == "" {
		return fmt.Errorf("mysql.host is required")
	}
	if c.MySQL.Port <= 0 || c.MySQL.Port > 65535 {
		return fmt.Errorf("mysql.port must be valid port")
	}
	if c.MySQL.User == "" {
		return fmt.Errorf("mysql.user is required")
	}
	if c.MySQL.Password == "" {
		return fmt.Errorf("mysql.password is required")
	}
	if c.MySQL.DB == "" {
		return fmt.Errorf("mysql.db is required")
	}

	if c.Redis.Host == "" {
		return fmt.Errorf("redis.host is required")
	}
	if c.Redis.Port <= 0 || c.Redis.Port > 65535 {
		return fmt.Errorf("redis.port must be valid port")
	}

	if c.MinIO.Endpoint == "" {
		return fmt.Errorf("minio.endpoint is required")
	}
	if c.MinIO.AccessKey == "" {
		return fmt.Errorf("minio.access_key is required")
	}
	if c.MinIO.SecretKey == "" {
		return fmt.Errorf("minio.secret_key is required")
	}

	if c.Infinity.Host == "" {
		return fmt.Errorf("infinity.host is required")
	}
	if c.Infinity.Port <= 0 || c.Infinity.Port > 65535 {
		return fmt.Errorf("infinity.port must be valid port")
	}

	if c.NATS.Endpoints == "" {
		return fmt.Errorf("nats.endpoints is required")
	}

	if c.RAGFlow.GoPort <= 0 || c.RAGFlow.GoPort > 65535 {
		return fmt.Errorf("ragflow.go_port must be valid port")
	}
	if c.RAGFlow.PythonPort <= 0 || c.RAGFlow.PythonPort > 65535 {
		return fmt.Errorf("ragflow.python_port must be valid port")
	}

	if c.Auth.JWTSecret == "" {
		return fmt.Errorf("auth.jwt_secret is required")
	}
	if c.Auth.JWTExpirationMinutes <= 0 {
		return fmt.Errorf("auth.jwt_expiration_minutes must be > 0")
	}
	if c.Auth.SessionTTLMinutes <= 0 {
		return fmt.Errorf("auth.session_ttl_minutes must be > 0")
	}

	if c.Syncer.PollIntervalSec <= 0 {
		c.Syncer.PollIntervalSec = 5 // default 5 seconds
	}
	if c.Syncer.BatchSize <= 0 {
		c.Syncer.BatchSize = 10 // default batch size
	}
	if c.Syncer.MaxInFlight <= 0 {
		c.Syncer.MaxInFlight = 50 // default concurrency
	}

	return nil
}
