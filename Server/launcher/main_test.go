package main

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"testing"
)

func TestLauncherExitHelper(t *testing.T) {
	value := os.Getenv("NXT_CONSOLE_TEST_EXIT")
	if value == "" {
		return
	}
	code, err := strconv.Atoi(value)
	if err != nil {
		os.Exit(99)
	}
	os.Exit(code)
}
func childExit(code int) error {
	cmd := exec.Command(os.Args[0], "-test.run=^TestLauncherExitHelper$")
	cmd.Env = append(os.Environ(), "NXT_CONSOLE_TEST_EXIT="+strconv.Itoa(code))
	return cmd.Run()
}
func TestExplicitCleanRestartRunsAnotherChild(t *testing.T) {
	calls := 0
	var out bytes.Buffer
	err := runWorld(func() error {
		calls++
		if calls == 1 {
			return childExit(75)
		}
		return childExit(0)
	}, &out)
	if err != nil || calls != 2 || !strings.Contains(out.String(), "Restarting") {
		t.Fatalf("restart failed: calls=%d err=%v output=%s", calls, err, out.String())
	}
}
func TestFailuresAreNotAutomaticallyRestarted(t *testing.T) {
	for _, code := range []int{1, 2, 76} {
		calls := 0
		err := runWorld(func() error { calls++; return childExit(code) }, &bytes.Buffer{})
		if err == nil || calls != 1 {
			t.Fatalf("failure %d retried or swallowed: calls=%d err=%v", code, calls, err)
		}
	}
}
func TestStartFailureIsNotRetried(t *testing.T) {
	wanted := errors.New("could not start interpreter")
	calls := 0
	err := runWorld(func() error { calls++; return wanted }, &bytes.Buffer{})
	if !errors.Is(err, wanted) || calls != 1 {
		t.Fatalf("unexpected retry: %v calls=%d", err, calls)
	}
}
