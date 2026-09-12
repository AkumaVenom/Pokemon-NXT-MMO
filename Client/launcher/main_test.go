package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadINI(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.ini")
	os.WriteFile(p, []byte("\ufeff; example\r\n[SERVER]\r\nhost = 127.0.0.1\r\nport=7777\r\n[other]\r\nsecret=a=b?\r\n"), 0600)
	m, e := readINI(p)
	if e != nil || m["server.host"] != "127.0.0.1" || m["other.secret"] != "a=b?" {
		t.Fatalf("INI parse: %v, %v", m, e)
	}
}
func TestBadINI(t *testing.T) {
	p := filepath.Join(t.TempDir(), "config.ini")
	os.WriteFile(p, []byte("[server]\ninvalidline\n"), 0600)
	if _, e := readINI(p); e == nil {
		t.Fatal("invalid line accepted")
	}
}
func TestNumbersAreFiniteAndBounded(t *testing.T) {
	for _, s := range []string{"NaN", "Inf", "-Inf", "1e400", "-1", "9", "bad"} {
		if _, e := number(map[string]string{"a": s}, "a", 0, 0, 8); e == nil {
			t.Fatalf("accepted %q", s)
		}
	}
	v, e := number(map[string]string{"a": "3"}, "a", 0, 0, 8)
	if e != nil || v != 3 {
		t.Fatal("valid scale rejected")
	}
}
