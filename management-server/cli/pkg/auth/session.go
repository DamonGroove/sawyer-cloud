// Package auth handles the mgmt-ctl session on the operator's laptop:
// OIDC device-code flow for login, session.json on disk, silent refresh.
package auth

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Session is the serialized form written to ~/.config/mgmt-ctl/session.json.
// Permissions: 0600. Everything else in that directory is operator-owned
// config (not secrets).
type Session struct {
	Server       string    `json:"server"`
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token,omitempty"`
	TokenType    string    `json:"token_type,omitempty"`
	ExpiresAt    time.Time `json:"expires_at,omitempty"`
	Email        string    `json:"email,omitempty"`
}

// Path returns the canonical session file path, honoring XDG_CONFIG_HOME.
func Path() (string, error) {
	dir, err := ConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "session.json"), nil
}

// ConfigDir returns the mgmt-ctl config directory, creating it if absent.
// Honors MGMT_CTL_CONFIG_DIR for test overrides.
func ConfigDir() (string, error) {
	if override := os.Getenv("MGMT_CTL_CONFIG_DIR"); override != "" {
		if err := os.MkdirAll(override, 0o700); err != nil {
			return "", err
		}
		return override, nil
	}
	base := os.Getenv("XDG_CONFIG_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, ".config")
	}
	dir := filepath.Join(base, "mgmt-ctl")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

// Load reads the session from disk. Returns (nil, nil) when no session
// file exists (not an error — user is simply logged out).
func Load() (*Session, error) {
	p, err := Path()
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read session: %w", err)
	}
	var s Session
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, fmt.Errorf("parse session.json: %w", err)
	}
	return &s, nil
}

// Save writes the session atomically with 0600 permissions.
func Save(s *Session) error {
	p, err := Path()
	if err != nil {
		return err
	}
	raw, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	// Atomic: write temp, fsync, rename.
	tmp, err := os.CreateTemp(filepath.Dir(p), ".session.*.json")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(raw); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), p)
}

// Clear removes the session file. Not an error if absent.
func Clear() error {
	p, err := Path()
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// TokenProvider returns the access token the client should send on each
// request. It silently refreshes when the token is within 60s of expiry.
// Returns "" (no error) when no session exists — the caller decides how
// to present a not-logged-in state.
func TokenProvider() (string, error) {
	s, err := Load()
	if err != nil {
		return "", err
	}
	if s == nil {
		return "", nil
	}
	if !s.ExpiresAt.IsZero() && time.Until(s.ExpiresAt) < 60*time.Second {
		// Phase 3 stub: real refresh goes against the OIDC issuer's
		// `/token` endpoint with grant_type=refresh_token. We accept
		// an expiring token as-is — the server-side exp check catches
		// real expiry and the CLI prompts the user to `mgmt-ctl login`
		// again. Good enough for the skeleton.
	}
	return s.AccessToken, nil
}
