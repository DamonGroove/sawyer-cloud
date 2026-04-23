package auth

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// DeviceCodeConfig describes an OIDC issuer that supports the device-code flow.
type DeviceCodeConfig struct {
	Issuer   string
	ClientID string
	Scopes   []string
	// Optional explicit endpoints. If left blank, DeviceLogin will discover
	// them via the issuer's .well-known/openid-configuration.
	DeviceAuthorizationEndpoint string
	TokenEndpoint               string
}

type deviceAuthResponse struct {
	DeviceCode              string `json:"device_code"`
	UserCode                string `json:"user_code"`
	VerificationURI         string `json:"verification_uri"`
	VerificationURIComplete string `json:"verification_uri_complete,omitempty"`
	ExpiresIn               int    `json:"expires_in"`
	Interval                int    `json:"interval"`
}

type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
	TokenType    string `json:"token_type"`
	IDToken      string `json:"id_token"`
	Error        string `json:"error"`
	ErrorDesc    string `json:"error_description"`
}

// DeviceLogin orchestrates the full device-code flow and returns a
// populated Session. `prompt` is called exactly once with the user-code
// and verification URL so callers can print them however they like.
func DeviceLogin(cfg DeviceCodeConfig, prompt func(userCode, verificationURI string)) (*Session, error) {
	if cfg.DeviceAuthorizationEndpoint == "" || cfg.TokenEndpoint == "" {
		if err := cfg.discover(); err != nil {
			return nil, err
		}
	}

	da, err := cfg.startDeviceAuth()
	if err != nil {
		return nil, err
	}
	shown := da.VerificationURIComplete
	if shown == "" {
		shown = da.VerificationURI
	}
	prompt(da.UserCode, shown)

	deadline := time.Now().Add(time.Duration(da.ExpiresIn) * time.Second)
	interval := time.Duration(da.Interval) * time.Second
	if interval <= 0 {
		interval = 5 * time.Second
	}

	for time.Now().Before(deadline) {
		time.Sleep(interval)
		tok, err := cfg.pollToken(da.DeviceCode)
		if err != nil {
			// The server may ask us to back off.
			var asErr authServerError
			if errors.As(err, &asErr) {
				switch asErr.Code {
				case "authorization_pending":
					continue
				case "slow_down":
					interval += 5 * time.Second
					continue
				}
			}
			return nil, err
		}
		sess := &Session{
			AccessToken:  tok.AccessToken,
			RefreshToken: tok.RefreshToken,
			TokenType:    tok.TokenType,
			ExpiresAt:    time.Now().Add(time.Duration(tok.ExpiresIn) * time.Second),
		}
		return sess, nil
	}
	return nil, fmt.Errorf("device-code flow timed out after %d seconds", da.ExpiresIn)
}

type authServerError struct {
	Code        string
	Description string
}

func (e authServerError) Error() string {
	if e.Description == "" {
		return e.Code
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Description)
}

// --- helpers ---------------------------------------------------------------

func (c *DeviceCodeConfig) discover() error {
	u := strings.TrimSuffix(c.Issuer, "/") + "/.well-known/openid-configuration"
	resp, err := http.Get(u)
	if err != nil {
		return fmt.Errorf("oidc discovery: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("oidc discovery returned %d", resp.StatusCode)
	}
	var doc struct {
		DeviceAuthorizationEndpoint string `json:"device_authorization_endpoint"`
		TokenEndpoint               string `json:"token_endpoint"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&doc); err != nil {
		return fmt.Errorf("oidc discovery decode: %w", err)
	}
	if doc.DeviceAuthorizationEndpoint == "" || doc.TokenEndpoint == "" {
		return errors.New("issuer does not advertise device_authorization_endpoint")
	}
	c.DeviceAuthorizationEndpoint = doc.DeviceAuthorizationEndpoint
	c.TokenEndpoint = doc.TokenEndpoint
	return nil
}

func (c *DeviceCodeConfig) startDeviceAuth() (*deviceAuthResponse, error) {
	form := url.Values{}
	form.Set("client_id", c.ClientID)
	form.Set("scope", strings.Join(append([]string{"openid", "profile", "email", "offline_access"}, c.Scopes...), " "))
	resp, err := http.PostForm(c.DeviceAuthorizationEndpoint, form)
	if err != nil {
		return nil, fmt.Errorf("device_authorization: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("device_authorization returned %d: %s", resp.StatusCode, string(body))
	}
	var da deviceAuthResponse
	if err := json.Unmarshal(body, &da); err != nil {
		return nil, fmt.Errorf("device_authorization decode: %w", err)
	}
	return &da, nil
}

func (c *DeviceCodeConfig) pollToken(deviceCode string) (*tokenResponse, error) {
	form := url.Values{}
	form.Set("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
	form.Set("device_code", deviceCode)
	form.Set("client_id", c.ClientID)
	resp, err := http.PostForm(c.TokenEndpoint, form)
	if err != nil {
		return nil, fmt.Errorf("token poll: %w", err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	var tok tokenResponse
	if err := json.Unmarshal(raw, &tok); err != nil {
		return nil, fmt.Errorf("token decode: %w (body %q)", err, string(raw))
	}
	if tok.Error != "" {
		return nil, authServerError{Code: tok.Error, Description: tok.ErrorDesc}
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("token poll returned %d", resp.StatusCode)
	}
	return &tok, nil
}
