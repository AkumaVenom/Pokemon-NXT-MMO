package main

import (
	"bytes"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"math"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"sync"
)

const audioSettingsMaxBytes = 4096

// Audio preferences belong to the Windows user, not the temporary Edge profile
// or the server configuration. Only these public preferences are persisted.
type audioSettings struct {
	Master        float64 `json:"master"`
	Music         float64 `json:"music"`
	Effects       float64 `json:"effects"`
	Cries         float64 `json:"cries"`
	Muted         bool    `json:"muted"`
	MuteUnfocused bool    `json:"muteUnfocused"`
	LowHP         bool    `json:"lowHp"`
	Chat          bool    `json:"chat"`
}

func defaultAudioSettings() audioSettings {
	return audioSettings{Master: .8, Music: .65, Effects: .8, Cries: .85, MuteUnfocused: true, LowHP: true, Chat: true}
}

func audioSettingsPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "PokemonNXT", "audio_settings.json"), nil
}

func validateAudioSettings(value audioSettings) error {
	for _, volume := range []float64{value.Master, value.Music, value.Effects, value.Cries} {
		if math.IsNaN(volume) || math.IsInf(volume, 0) || volume < 0 || volume > 1 {
			return errors.New("audio volumes must be finite numbers between 0 and 1")
		}
	}
	return nil
}

// Requiring every field makes a failed/partial request harmless: an omitted
// checkbox or volume must never silently become false or zero.
func parseAudioSettings(data []byte) (audioSettings, error) {
	if len(data) > audioSettingsMaxBytes {
		return audioSettings{}, errors.New("audio settings exceed the 4096-byte limit")
	}
	var incoming struct {
		Master        *float64 `json:"master"`
		Music         *float64 `json:"music"`
		Effects       *float64 `json:"effects"`
		Cries         *float64 `json:"cries"`
		Muted         *bool    `json:"muted"`
		MuteUnfocused *bool    `json:"muteUnfocused"`
		LowHP         *bool    `json:"lowHp"`
		Chat          *bool    `json:"chat"`
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&incoming); err != nil {
		return audioSettings{}, errors.New("audio settings must be a valid preferences object")
	}
	if decoder.Decode(new(any)) != io.EOF {
		return audioSettings{}, errors.New("audio settings must contain exactly one preferences object")
	}
	if incoming.Master == nil || incoming.Music == nil || incoming.Effects == nil || incoming.Cries == nil ||
		incoming.Muted == nil || incoming.MuteUnfocused == nil || incoming.LowHP == nil || incoming.Chat == nil {
		return audioSettings{}, errors.New("audio settings must include all volume and checkbox values")
	}
	value := audioSettings{
		Master: *incoming.Master, Music: *incoming.Music, Effects: *incoming.Effects, Cries: *incoming.Cries,
		Muted: *incoming.Muted, MuteUnfocused: *incoming.MuteUnfocused, LowHP: *incoming.LowHP, Chat: *incoming.Chat,
	}
	if err := validateAudioSettings(value); err != nil {
		return audioSettings{}, err
	}
	return value, nil
}

type audioSettingsStore struct {
	mu      sync.Mutex
	path    string
	value   audioSettings
	message string
}

func openAudioSettingsStore(path string) (*audioSettingsStore, error) {
	store := &audioSettingsStore{path: path, value: defaultAudioSettings()}
	if path == "" {
		store.message = "Audio preferences apply for this session; your user settings folder is unavailable."
		return store, errors.New("user audio settings path is unavailable")
	}
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return store, nil
	}
	if err == nil {
		defer file.Close()
		var data []byte
		data, err = io.ReadAll(io.LimitReader(file, audioSettingsMaxBytes+1))
		if err == nil {
			store.value, err = parseAudioSettings(data)
		}
	}
	if err != nil {
		store.value = defaultAudioSettings()
		store.message = "Saved audio preferences could not be loaded. Default settings are active; changing them will try saving again."
	}
	return store, err
}

func (store *audioSettingsStore) snapshot() (audioSettings, string) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.value, store.message
}

func writeAudioSettings(path string, value audioSettings) error {
	if path == "" {
		return errors.New("user audio settings path is unavailable")
	}
	if err := validateAudioSettings(value); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	if err = os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	// Stage beside the destination so replacement stays on the same volume.
	// A failed write never truncates the previous preferences file.
	file, err := os.CreateTemp(dir, ".audio-settings-*.tmp")
	if err != nil {
		return err
	}
	temporary := file.Name()
	defer os.Remove(temporary)
	defer file.Close()
	if err = file.Chmod(0600); err != nil {
		return err
	}
	if _, err = file.Write(append(data, '\n')); err != nil {
		return err
	}
	if err = file.Sync(); err != nil {
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	return os.Rename(temporary, path)
}

func (store *audioSettingsStore) save(value audioSettings) (bool, string) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.value = value
	if err := writeAudioSettings(store.path, value); err != nil {
		// Keep session controls usable even on a read-only/full disk. Filesystem
		// paths and unrelated configuration are never returned to the browser.
		store.message = "Audio preferences apply for this session, but could not be saved. Check that your user settings folder is writable and has free space."
		return false, store.message
	}
	store.message = ""
	return true, ""
}

func audioSettingsHandler(store *audioSettingsStore, origin, nonce string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			rejectLauncherRequest(w, r, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		tokens := r.URL.Query()["token"]
		if r.Header.Get("Origin") != origin || len(tokens) != 1 ||
			subtle.ConstantTimeCompare([]byte(tokens[0]), []byte(nonce)) != 1 {
			rejectLauncherRequest(w, r, "Forbidden", http.StatusForbidden)
			return
		}
		contentType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if err != nil || contentType != "application/json" {
			rejectLauncherRequest(w, r, "Audio settings require application/json", http.StatusUnsupportedMediaType)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, audioSettingsMaxBytes)
		defer r.Body.Close()
		data, err := io.ReadAll(r.Body)
		if err != nil {
			var tooLarge *http.MaxBytesError
			if errors.As(err, &tooLarge) {
				http.Error(w, "Audio settings exceed the 4096-byte limit", http.StatusRequestEntityTooLarge)
			} else {
				http.Error(w, "Could not read audio settings", http.StatusBadRequest)
			}
			return
		}
		value, err := parseAudioSettings(data)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		persisted, message := store.save(value)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(struct {
			Audio     audioSettings `json:"audio"`
			Persisted bool          `json:"persisted"`
			Message   string        `json:"message,omitempty"`
		}{value, persisted, message})
	}
}
