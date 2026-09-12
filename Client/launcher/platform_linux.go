package main

import (
	"fmt"
	"os"
	"os/exec"
)

func findEdge() string {
	for _, name := range []string{"microsoft-edge", "chromium", "google-chrome"} {
		if p, e := exec.LookPath(name); e == nil {
			return p
		}
	}
	return ""
}
func showError(message string) { fmt.Fprintln(os.Stderr, message) }
