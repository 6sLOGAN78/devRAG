package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/6sLOGAN78/devRAG/internal/config"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "missing config path")
		os.Exit(1)
	}

	cfg, err := config.LoadConfig(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	out, _ := json.MarshalIndent(cfg, "", "  ")
	fmt.Println(string(out))
}
