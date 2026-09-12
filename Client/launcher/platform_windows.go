package main

import (
	"os"
	"path/filepath"
	"syscall"
	"unsafe"
)

func findEdge() string {
	for _, k := range []string{"ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"} {
		p := filepath.Join(os.Getenv(k), "Microsoft", "Edge", "Application", "msedge.exe")
		if st, e := os.Stat(p); e == nil && !st.IsDir() {
			return p
		}
	}
	return ""
}
func showError(message string) {
	text, _ := syscall.UTF16PtrFromString(message)
	title, _ := syscall.UTF16PtrFromString("Pokemon NXT MMO - Startup error")
	syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0x10)
}
