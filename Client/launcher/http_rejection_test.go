package main

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Send headers separately from the JSON, like urllib's Windows smoke request.
// Checking when the handler returns makes this regression deterministic even
// on systems whose TCP stack happens to preserve the premature error response.
func TestAudioSettingsRejectedCloseRequestsConsumeSplitBody(t *testing.T) {
	const origin = "http://127.0.0.1:41234"
	const nonce = "test-launcher-nonce"
	value := defaultAudioSettings()
	value.Master = .2
	body := string(audioJSON(t, value))
	cases := []struct {
		name, method, query, origin, contentType string
		status                                 int
	}{
		{"missing origin", "POST", "?token=" + nonce, "", "application/json", 403},
		{"foreign origin", "POST", "?token=" + nonce, "https://example.com", "application/json", 403},
		{"missing token", "POST", "", origin, "application/json", 403},
		{"wrong token", "POST", "?token=incorrect", origin, "application/json", 403},
		{"duplicate token", "POST", "?token=" + nonce + "&token=" + nonce, origin, "application/json", 403},
		{"wrong method", "PUT", "?token=" + nonce, origin, "application/json", 405},
		{"wrong content type", "POST", "?token=" + nonce, origin, "text/plain", 415},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "audio_settings.json")
			store, err := openAudioSettingsStore(path)
			if err != nil {
				t.Fatal(err)
			}
			entered := make(chan struct{}, 1)
			returned := make(chan struct{}, 1)
			handler := audioSettingsHandler(store, origin, nonce)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				entered <- struct{}{}
				handler(w, r)
				returned <- struct{}{}
			}))
			defer server.Close()
			conn, err := net.DialTimeout("tcp", server.Listener.Addr().String(), 3*time.Second)
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			if err := conn.SetDeadline(time.Now().Add(3 * time.Second)); err != nil {
				t.Fatal(err)
			}
			headers := fmt.Sprintf("%s /audio-settings%s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\nContent-Type: %s\r\nContent-Length: %d\r\n", tc.method, tc.query, server.Listener.Addr(), tc.contentType, len(body))
			if tc.origin != "" {
				headers += "Origin: " + tc.origin + "\r\n"
			}
			if _, err := io.WriteString(conn, headers+"\r\n"); err != nil {
				t.Fatal(err)
			}
			select {
			case <-entered:
			case <-time.After(2 * time.Second):
				t.Fatal("server did not receive request headers")
			}
			for _, part := range []string{body[:len(body)/2], body[len(body)/2:]} {
				select {
				case <-returned:
					t.Fatal("rejection returned before the declared request body was consumed")
				case <-time.After(20 * time.Millisecond):
				}
				if _, err := io.WriteString(conn, part); err != nil {
					t.Fatalf("request body was reset before completion: %v", err)
				}
			}
			response, err := http.ReadResponse(bufio.NewReader(conn), &http.Request{Method: tc.method})
			if err != nil {
				t.Fatalf("rejected request lost its HTTP response: %v", err)
			}
			defer response.Body.Close()
			responseBody, err := io.ReadAll(response.Body)
			if err != nil {
				t.Fatalf("rejection response was truncated: %v", err)
			}
			if response.StatusCode != tc.status || len(responseBody) == 0 {
				t.Fatalf("wanted complete HTTP %d, received %d: %q", tc.status, response.StatusCode, responseBody)
			}
			if got, _ := store.snapshot(); got != defaultAudioSettings() {
				t.Fatal("rejected request changed session preferences")
			}
			if _, err := os.Stat(path); !os.IsNotExist(err) {
				t.Fatal("rejected request wrote preferences")
			}
		})
	}
}

type countingRequestBody struct {
	io.Reader
	read int
}

func (body *countingRequestBody) Read(data []byte) (int, error) {
	n, err := body.Reader.Read(data)
	body.read += n
	return n, err
}

func (body *countingRequestBody) Close() error { return nil }

func TestLauncherRejectedBodyDrainIsBounded(t *testing.T) {
	body := &countingRequestBody{Reader: strings.NewReader(strings.Repeat("x", rejectedRequestDrainBytes*8))}
	r := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/audio-settings", nil)
	r.Body = body
	w := httptest.NewRecorder()
	rejectLauncherRequest(w, r, "Forbidden", http.StatusForbidden)
	// MaxBytesReader reads one extra byte to distinguish a body at the limit
	// from an oversized body; it never consumes the unbounded remainder.
	if body.read != rejectedRequestDrainBytes+1 {
		t.Fatalf("drained %d bytes; want %d", body.read, rejectedRequestDrainBytes+1)
	}
	if w.Code != http.StatusForbidden || w.Header().Get("Connection") != "close" {
		t.Fatalf("oversized rejected request lost its status/close: %d %v", w.Code, w.Header())
	}
}

func TestLauncherRejectedIncompleteBodyHasDeadline(t *testing.T) {
	returned := make(chan struct{}, 1)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rejectLauncherRequest(w, r, "Forbidden", http.StatusForbidden)
		returned <- struct{}{}
	}))
	// Exercise the explicit one-second drain deadline, not an unrelated
	// default server timeout. The production launcher has a longer timeout.
	server.Config.ReadTimeout = 15 * time.Second
	server.Start()
	defer server.Close()
	conn, err := net.DialTimeout("tcp", server.Listener.Addr().String(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if _, err := fmt.Fprintf(conn, "POST / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\nContent-Length: 100\r\n\r\nx", server.Listener.Addr()); err != nil {
		t.Fatal(err)
	}
	select {
	case <-returned:
	case <-time.After(3 * time.Second):
		t.Fatal("incomplete rejected upload was not bounded by the drain deadline")
	}
}
