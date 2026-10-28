// Package pipeline exposes finite build metadata. It never reads tenant or runtime state.
package pipeline

import (
	_ "embed"
	"encoding/json"
)

//go:embed templates.json
var templates []byte

// Template describes code shipped with this binary, not tenant provider availability.
type Template struct {
	ID           string         `json:"id"`
	Name         string         `json:"name"`
	Description  string         `json:"description"`
	ParserID     string         `json:"parser_id"`
	ParserConfig map[string]any `json:"parser_config"`
	Available    bool           `json:"available"`
}

// Builtins decodes fresh copies so a caller cannot mutate the embedded catalog.
func Builtins() []Template {
	var result []Template
	if err := json.Unmarshal(templates, &result); err != nil {
		panic("invalid embedded pipeline catalog")
	}
	return result
}

// Builtin resolves only a finite documented identifier.
func Builtin(id string) (Template, bool) {
	for _, template := range Builtins() {
		if template.ID == id {
			return template, true
		}
	}
	return Template{}, false
}
