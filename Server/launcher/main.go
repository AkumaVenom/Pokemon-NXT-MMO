// Native Windows console launcher. The actual authoritative service is server.py.
package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
)

func pause() {
	fmt.Print("\nPress Enter to close this console...")
	bufio.NewReader(os.Stdin).ReadString('\n')
}
func main() {
	exe, e := os.Executable()
	if e != nil {
		fmt.Println(e)
		pause()
		os.Exit(1)
	}
	root := filepath.Dir(exe)
	python := filepath.Join(root, ".venv", "Scripts", "python.exe")
	if _, e = os.Stat(python); e != nil {
		fmt.Println("Pokemon NXT MMO: server dependencies are not installed.\nRun 1 - Install Server Dependencies.cmd, then 2 - Configure MySQL.cmd.")
		pause()
		os.Exit(1)
	}
	args := []string{"-u", filepath.Join(root, "server.py"), "--config", filepath.Join(root, "config.ini")}
	args = append(args, os.Args[1:]...)
	cmd := exec.Command(python, args...)
	cmd.Dir = root
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	// Let the child handle Ctrl+C and finish saving; keep the parent console alive.
	interrupts := make(chan os.Signal, 1)
	signal.Notify(interrupts, os.Interrupt)
	go func() {
		for range interrupts {
		}
	}()
	if e = cmd.Run(); e != nil {
		fmt.Println("\nWorld server exited:", e)
		pause()
		os.Exit(1)
	}
	fmt.Println("\nWorld server stopped cleanly.")
	pause()
}
