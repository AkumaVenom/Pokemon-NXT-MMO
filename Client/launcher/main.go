// Pokemon NXT MMO desktop app shell. No remote scripts, CDN, ROM or node runtime.
// Edge supplies the Windows GPU compositor, native text and per-monitor DPI handling.
package main

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"log"
	"math"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

func readINI(path string) (map[string]string, error) {
	f, e := os.Open(path)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	m := map[string]string{}
	section := ""
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := strings.TrimSpace(strings.TrimPrefix(s.Text(), "\ufeff"))
		if line == "" || strings.HasPrefix(line, ";") || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.ToLower(strings.TrimSpace(line[1 : len(line)-1]))
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("invalid config line: %s", line)
		}
		m[section+"."+strings.ToLower(strings.TrimSpace(k))] = strings.TrimSpace(v)
	}
	return m, s.Err()
}
func number(m map[string]string, key string, def, lo, hi float64) (float64, error) {
	v := def
	if s, ok := m[key]; ok {
		n, e := strconv.ParseFloat(s, 64)
		if e != nil || math.IsNaN(n) || math.IsInf(n, 0) {
			return 0, fmt.Errorf("invalid %s", key)
		}
		v = n
	}
	if v < lo || v > hi {
		return 0, fmt.Errorf("%s must be %.1f to %.1f", key, lo, hi)
	}
	return v, nil
}
func run() error {
	rootFlag := flag.String("root", "", "Client folder (development only)")
	headless := flag.Bool("headless", false, "serve the app without launching Edge (development only)")
	flag.Parse()
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(exe)
	if *rootFlag != "" {
		root, e = filepath.Abs(*rootFlag)
		if e != nil {
			return e
		}
	}
	cfg, e := readINI(filepath.Join(root, "config.ini"))
	if e != nil {
		return fmt.Errorf("cannot read Client/config.ini: %w", e)
	}
	host := cfg["server.host"]
	if host == "" {
		return errors.New("set server.host in config.ini")
	}
	if net.ParseIP(host) == nil && !regexp.MustCompile(`^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$`).MatchString(host) {
		return errors.New("server.host must be an IP address or hostname, without http:// or a path")
	}
	port, e := number(cfg, "server.port", 7777, 1024, 65535)
	if e != nil || port != float64(int(port)) {
		return errors.New("server.port must be an integer from 1024 to 65535")
	}
	secure := strings.EqualFold(cfg["server.tls"], "true")
	if cfg["server.tls"] != "true" && cfg["server.tls"] != "false" {
		return errors.New("server.tls must be true or false")
	}
	scheme := "ws"
	if secure {
		scheme = "wss"
	}
	endpoint := scheme + "://" + net.JoinHostPort(host, strconv.Itoa(int(port))) + "/world"
	pixel, e := number(cfg, "display.pixel_scale", 0, 0, 8)
	if e != nil || pixel != float64(int(pixel)) {
		return errors.New("display.pixel_scale must be an integer from 0 to 8")
	}
	ui, e := number(cfg, "display.ui_scale", 0, 0, 2)
	if e != nil {
		return e
	}
	if ui > 0 && ui < .8 {
		return errors.New("display.ui_scale must be 0 (automatic) or 0.8 to 2.0")
	}
	idle, e := number(cfg, "launcher.idle_shutdown_seconds", 90, 30, 600)
	if e != nil {
		return e
	}
	app := filepath.Join(root, "app")
	if _, e = os.Stat(filepath.Join(app, "index.html")); e != nil {
		return errors.New("Client/app/index.html is missing; extract the complete Client folder first")
	}
	ln, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		return e
	}
	defer ln.Close()
	base := "http://" + ln.Addr().String()
	var heartbeat atomic.Int64
	heartbeat.Store(time.Now().Unix())
	nonceBytes := make([]byte, 24)
	if _, e = rand.Read(nonceBytes); e != nil {
		return e
	}
	nonce := hex.EncodeToString(nonceBytes)
	audioPath, audioPathError := audioSettingsPath()
	audioStore, audioLoadError := openAudioSettingsStore(audioPath)
	if audioPathError != nil {
		log.Printf("Audio preferences will use session settings: %v", audioPathError)
	} else if audioLoadError != nil {
		log.Printf("Audio preferences could not be loaded; using defaults: %v", audioLoadError)
	}
	stop := make(chan struct{}, 1)
	// Windows registry associations must not change executable module or audio
	// MIME types; the app deliberately enables X-Content-Type-Options: nosniff.
	mime.AddExtensionType(".js", "text/javascript")
	mime.AddExtensionType(".mjs", "text/javascript")
	mime.AddExtensionType(".ogg", "audio/ogg")
	mime.AddExtensionType(".wav", "audio/wav")
	mime.AddExtensionType(".json", "application/json")
	fileServer := http.FileServer(http.Dir(app))
	mux := http.NewServeMux()
	mux.HandleFunc("/bootstrap", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			rejectLauncherRequest(w, r, "Method not allowed", 405)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		audio, audioMessage := audioStore.snapshot()
		json.NewEncoder(w).Encode(map[string]any{"endpoint": endpoint, "host": host, "port": int(port), "tls": secure, "pixelScale": int(pixel), "uiScale": ui, "nonce": nonce, "version": "0.2.0-alpha", "audio": audio, "audioPersistenceMessage": audioMessage})
	})
	mux.HandleFunc("/audio-settings", audioSettingsHandler(audioStore, base, nonce))
	mux.HandleFunc("/heartbeat", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Query().Get("token") != nonce || r.Header.Get("Origin") != base {
			rejectLauncherRequest(w, r, "Forbidden", 403)
			return
		}
		heartbeat.Store(time.Now().Unix())
		w.WriteHeader(204)
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" && r.Method != "HEAD" {
			rejectLauncherRequest(w, r, "Method not allowed", 405)
			return
		}
		p, e := url.PathUnescape(r.URL.Path)
		if e != nil || strings.Contains(p, "\\") {
			http.NotFound(w, r)
			return
		}
		if p != "/" {
			clean := strings.TrimPrefix(p, "/")
			if !fs.ValidPath(clean) {
				http.NotFound(w, r)
				return
			}
			st, e := os.Stat(filepath.Join(app, filepath.FromSlash(clean)))
			if e != nil || st.IsDir() {
				http.NotFound(w, r)
				return
			}
		}
		if strings.HasPrefix(p, "/assets/") {
			w.Header().Set("Cache-Control", "public, max-age=3600")
		} else {
			w.Header().Set("Cache-Control", "no-cache")
		}
		fileServer.ServeHTTP(w, r)
	})
	srv := &http.Server{ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 45 * time.Second, Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Host != ln.Addr().String() {
			rejectLauncherRequest(w, r, "Forbidden host", 403)
			return
		}
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Cross-Origin-Resource-Policy", "same-origin")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self' "+scheme+"://"+net.JoinHostPort(host, strconv.Itoa(int(port)))+"; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
		mux.ServeHTTP(w, r)
	})}
	errc := make(chan error, 1)
	go func() {
		if e := srv.Serve(ln); e != nil && e != http.ErrServerClosed {
			errc <- e
		}
	}()
	fmt.Println("Pokemon NXT MMO app:", base)
	if !*headless {
		edge := cfg["launcher.edge_path"]
		if edge == "" {
			edge = findEdge()
		}
		if edge == "" {
			return errors.New("Microsoft Edge was not found. Install Microsoft Edge, or set launcher.edge_path in Client/config.ini")
		}
		profile, e := os.MkdirTemp("", "PokemonNXT-Edge-")
		if e != nil {
			return e
		}
		defer func() { os.RemoveAll(profile) }()
		args := []string{"--app=" + base, "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check", "--disable-features=msEdgeSidebarV2"}
		if cfg["display.start_maximized"] != "false" {
			args = append(args, "--start-maximized")
		}
		cmd := exec.Command(edge, args...)
		if e = cmd.Start(); e != nil {
			return fmt.Errorf("could not start Edge app window: %w", e)
		}
		go cmd.Wait()
	}
	tick := time.NewTicker(5 * time.Second)
	defer tick.Stop()
	for {
		select {
		case e := <-errc:
			return e
		case <-stop:
			return nil
		case <-tick.C:
			if time.Now().Unix()-heartbeat.Load() > int64(idle) {
				ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
				defer cancel()
				srv.Shutdown(ctx)
				return nil
			}
		}
	}
}
func main() {
	if e := run(); e != nil {
		log.Print(e)
		showError(e.Error())
		os.Exit(1)
	}
}
