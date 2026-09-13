package main

import (
	"bytes"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func audioJSON(t *testing.T, value audioSettings) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestAudioSettingsFreshUserAndRoundTrip(t *testing.T) {
	path := filepath.Join(t.TempDir(), "PokemonNXT", "audio_settings.json")
	store, err := openAudioSettingsStore(path)
	if err != nil {
		t.Fatal(err)
	}
	value, message := store.snapshot()
	if value != defaultAudioSettings() || message != "" {
		t.Fatalf("fresh-user defaults: %+v, %q", value, message)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("loading absent preferences should not create a file")
	}
	first := audioSettings{Master: 0, Music: 1, Effects: .35, Cries: .7, Muted: true}
	if saved, message := store.save(first); !saved || message != "" {
		t.Fatalf("save failed: %q", message)
	}
	// A second launch does not share the launcher port or Edge profile.
	reopened, err := openAudioSettingsStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if got, _ := reopened.snapshot(); got != first {
		t.Fatalf("preferences did not survive launch: %+v", got)
	}
	second := defaultAudioSettings()
	second.Master = .25
	if saved, _ := reopened.save(second); !saved {
		t.Fatal("could not replace existing preferences")
	}
	reopened, err = openAudioSettingsStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if got, _ := reopened.snapshot(); got != second {
		t.Fatalf("replacement did not persist: %+v", got)
	}
	files, err := os.ReadDir(filepath.Dir(path))
	if err != nil || len(files) != 1 || files[0].Name() != "audio_settings.json" {
		t.Fatalf("unexpected leftover files: %v, %v", files, err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var public map[string]any
	if json.Unmarshal(data, &public) != nil || len(public) != 8 {
		t.Fatalf("only the eight audio preferences may be written: %s", data)
	}
	for _, key := range []string{"master", "music", "effects", "cries", "muted", "muteUnfocused", "lowHp", "chat"} {
		if _, ok := public[key]; !ok {
			t.Fatalf("missing public audio preference %q", key)
		}
	}
}

func TestAudioSettingsRejectInvalidInput(t *testing.T) {
	valid := string(audioJSON(t, defaultAudioSettings()))
	cases := map[string]string{
		"missing fields":    `{}`,
		"null object":       `null`,
		"array":             `[]`,
		"string":            `"settings"`,
		"unknown secret":    strings.TrimSuffix(valid, "}") + `,"password":"must-not-be-stored"}`,
		"negative volume":   strings.Replace(valid, `"master":0.8`, `"master":-0.1`, 1),
		"excess volume":     strings.Replace(valid, `"music":0.65`, `"music":1.1`, 1),
		"overflow volume":   strings.Replace(valid, `"effects":0.8`, `"effects":1e999`, 1),
		"nan volume":        strings.Replace(valid, `"cries":0.85`, `"cries":NaN`, 1),
		"null volume":       strings.Replace(valid, `"master":0.8`, `"master":null`, 1),
		"null checkbox":     strings.Replace(valid, `"muted":false`, `"muted":null`, 1),
		"string volume":     strings.Replace(valid, `"master":0.8`, `"master":"0.8"`, 1),
		"string checkbox":   strings.Replace(valid, `"muted":false`, `"muted":"false"`, 1),
		"numeric checkbox":  strings.Replace(valid, `"muted":false`, `"muted":0`, 1),
		"multiple objects":  valid + valid,
		"trailing garbage":  valid + "x",
		"truncated object":  strings.TrimSuffix(valid, "}"),
		"oversized payload": valid + strings.Repeat(" ", audioSettingsMaxBytes),
	}
	for name, data := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := parseAudioSettings([]byte(data)); err == nil {
				t.Fatalf("accepted invalid preferences: %s", data)
			}
		})
	}
	if value, err := parseAudioSettings([]byte(valid + " \r\n")); err != nil || value != defaultAudioSettings() {
		t.Fatalf("valid preferences rejected: %+v, %v", value, err)
	}
	boundary := audioSettings{Master: 0, Music: 1, Effects: 0, Cries: 1}
	if value, err := parseAudioSettings(audioJSON(t, boundary)); err != nil || value != boundary {
		t.Fatalf("valid boundary values rejected: %+v, %v", value, err)
	}
}

func TestAudioSettingsInvalidSavedFileUsesDefaultsWithoutOverwriting(t *testing.T) {
	for _, data := range [][]byte{[]byte("broken"), bytes.Repeat([]byte(" "), audioSettingsMaxBytes+1)} {
		path := filepath.Join(t.TempDir(), "audio_settings.json")
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		store, err := openAudioSettingsStore(path)
		if err == nil {
			t.Fatal("invalid saved settings were accepted")
		}
		if value, message := store.snapshot(); value != defaultAudioSettings() || message == "" {
			t.Fatalf("invalid settings should use defaults with a message: %+v, %q", value, message)
		}
		untouched, err := os.ReadFile(path)
		if err != nil || !bytes.Equal(untouched, data) {
			t.Fatal("loading invalid settings modified the user's file")
		}
		if saved, _ := store.save(defaultAudioSettings()); !saved {
			t.Fatal("changing settings should repair invalid saved preferences")
		}
	}
}

func TestAudioSettingsInvalidWritePreservesPreviousFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "audio_settings.json")
	before := audioJSON(t, defaultAudioSettings())
	if err := os.WriteFile(path, before, 0600); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []float64{math.NaN(), math.Inf(1), math.Inf(-1), -1, 2} {
		value := defaultAudioSettings()
		value.Master = invalid
		if err := writeAudioSettings(path, value); err == nil {
			t.Fatal("invalid write was accepted")
		}
		after, err := os.ReadFile(path)
		if err != nil || !bytes.Equal(before, after) {
			t.Fatal("invalid write damaged previous preferences")
		}
	}
}

func TestAudioSettingsEndpointPermissionsAndLimits(t *testing.T) {
	const origin = "http://127.0.0.1:41234"
	const nonce = "test-launcher-nonce"
	value := defaultAudioSettings()
	value.Master = .2
	valid := string(audioJSON(t, value))
	cases := []struct {
		name, method, query, origin, contentType, body string
		status                                       int
	}{
		{"get", "GET", "?token=" + nonce, origin, "application/json", valid, 405},
		{"put", "PUT", "?token=" + nonce, origin, "application/json", valid, 405},
		{"no token", "POST", "", origin, "application/json", valid, 403},
		{"wrong token", "POST", "?token=other", origin, "application/json", valid, 403},
		{"duplicate token", "POST", "?token=" + nonce + "&token=" + nonce, origin, "application/json", valid, 403},
		{"no origin", "POST", "?token=" + nonce, "", "application/json", valid, 403},
		{"remote origin", "POST", "?token=" + nonce, "https://example.com", "application/json", valid, 403},
		{"wrong port", "POST", "?token=" + nonce, "http://127.0.0.1:41235", "application/json", valid, 403},
		{"null origin", "POST", "?token=" + nonce, "null", "application/json", valid, 403},
		{"text body", "POST", "?token=" + nonce, origin, "text/plain", valid, 415},
		{"invalid body", "POST", "?token=" + nonce, origin, "application/json", `{}`, 400},
		{"oversized body", "POST", "?token=" + nonce, origin, "application/json", valid + strings.Repeat(" ", 4096), 413},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "audio_settings.json")
			store, err := openAudioSettingsStore(path)
			if err != nil {
				t.Fatal(err)
			}
			r := httptest.NewRequest(tc.method, origin+"/audio-settings"+tc.query, strings.NewReader(tc.body))
			r.Header.Set("Origin", tc.origin)
			r.Header.Set("Content-Type", tc.contentType)
			w := httptest.NewRecorder()
			audioSettingsHandler(store, origin, nonce)(w, r)
			if w.Code != tc.status {
				t.Fatalf("expected %d, got %d: %s", tc.status, w.Code, w.Body)
			}
			if got, _ := store.snapshot(); got != defaultAudioSettings() {
				t.Fatal("rejected request changed session preferences")
			}
			if _, err := os.Stat(path); !os.IsNotExist(err) {
				t.Fatal("rejected request created a preferences file")
			}
			if w.Header().Get("Cache-Control") != "no-store" {
				t.Fatal("audio response must not be cached")
			}
		})
	}
}

func TestAudioSettingsEndpointPersistsAndRecoversNonfatalFailures(t *testing.T) {
	const origin = "http://127.0.0.1:41234"
	const nonce = "test-launcher-nonce"
	for _, unavailable := range []bool{false, true} {
		dir := t.TempDir()
		path := filepath.Join(dir, "PokemonNXT", "audio_settings.json")
		if unavailable {
			// This fails consistently even when the test user is administrator.
			if err := os.WriteFile(filepath.Dir(path), []byte("not a directory"), 0600); err != nil {
				t.Fatal(err)
			}
		}
		store, _ := openAudioSettingsStore(path)
		value := defaultAudioSettings()
		value.Muted = true
		value.Chat = false
		r := httptest.NewRequest("POST", origin+"/audio-settings?token="+nonce, bytes.NewReader(audioJSON(t, value)))
		r.Header.Set("Origin", origin)
		r.Header.Set("Content-Type", "application/json; charset=utf-8")
		w := httptest.NewRecorder()
		audioSettingsHandler(store, origin, nonce)(w, r)
		if w.Code != http.StatusOK {
			t.Fatalf("preferences should remain usable: %d %s", w.Code, w.Body)
		}
		var result struct {
			Audio     audioSettings `json:"audio"`
			Persisted bool          `json:"persisted"`
			Message   string        `json:"message"`
		}
		if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		if result.Audio != value || result.Persisted == unavailable || (result.Message != "") != unavailable {
			t.Fatalf("unexpected response: %+v", result)
		}
		if got, _ := store.snapshot(); got != value {
			t.Fatal("settings did not apply to the current session")
		}
		if strings.Contains(w.Body.String(), dir) || strings.Contains(w.Body.String(), nonce) {
			t.Fatal("response exposed private paths or authorization token")
		}
		if unavailable {
			if err := os.Remove(filepath.Dir(path)); err != nil {
				t.Fatal(err)
			}
			if saved, message := store.save(value); !saved || message != "" {
				t.Fatalf("saving did not recover after storage became available: %q", message)
			}
		}
		reopened, err := openAudioSettingsStore(path)
		if err != nil {
			t.Fatal(err)
		}
		if got, _ := reopened.snapshot(); got != value {
			t.Fatal("saved settings did not survive reopening")
		}
	}
}
