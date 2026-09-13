package main

import (
	"io"
	"net/http"
	"time"
)

const rejectedRequestDrainBytes = 4096
const rejectedRequestDrainTimeout = time.Second

// A small rejected POST must still receive its HTTP error on Windows. With
// Connection: close, net/http does not automatically drain a fixed-length body;
// closing the socket with unread bytes can reset the connection and discard the
// response. Consume only a bounded amount before replying, without parsing or
// applying rejected input. The deadline also bounds slow or incomplete uploads.
func rejectLauncherRequest(w http.ResponseWriter, r *http.Request, message string, status int) {
	if r.Body != nil && r.Body != http.NoBody {
		// The real HTTP server supports this controller. Recorder-based unit
		// tests do not; their request bodies are finite in-memory readers.
		_ = http.NewResponseController(w).SetReadDeadline(time.Now().Add(rejectedRequestDrainTimeout))
		body := http.MaxBytesReader(w, r.Body, rejectedRequestDrainBytes)
		if _, err := io.Copy(io.Discard, body); err != nil {
			// Keep the original rejection status, but never reuse a connection
			// whose body could not be consumed. MaxBytesReader also notifies
			// net/http to use its guarded close for oversized uploads.
			w.Header().Set("Connection", "close")
		}
		// net/http owns and closes Request.Body after the handler returns.
	}
	http.Error(w, message, status)
}
