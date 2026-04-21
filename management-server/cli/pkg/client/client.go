// Package client is the thin HTTP client for the sawyer-cloud management
// server. Every mgmt-ctl command uses exactly one Client method — keeps
// authz enforcement on the server per MGMT_CTL_CLI_SPEC.md principle #1.
package client

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client is safe for concurrent use; all state is read-only after construction.
type Client struct {
	ServerURL  string
	HTTP       *http.Client
	TokenFn    func() (string, error) // called per-request to support silent refresh
	UserAgent  string
}

// New constructs a Client. serverURL may be an https URL or a host:port.
func New(serverURL string, tokenFn func() (string, error)) *Client {
	if !strings.HasPrefix(serverURL, "http://") && !strings.HasPrefix(serverURL, "https://") {
		serverURL = "https://" + serverURL
	}
	return &Client{
		ServerURL: strings.TrimSuffix(serverURL, "/"),
		HTTP:      &http.Client{Timeout: 60 * time.Second},
		TokenFn:   tokenFn,
		UserAgent: "mgmt-ctl",
	}
}

// Do performs one request. `body` is JSON-encoded when non-nil; `out` is
// JSON-decoded from the response when non-nil and the status is 2xx.
// Non-2xx responses are returned as an *APIError.
func (c *Client) Do(method, path string, body, out any) error {
	req, err := c.newRequest(method, path, body, nil)
	if err != nil {
		return err
	}
	return c.do(req, out)
}

// DoQuery is Do with URL query parameters.
func (c *Client) DoQuery(method, path string, query url.Values, body, out any) error {
	req, err := c.newRequest(method, path, body, query)
	if err != nil {
		return err
	}
	return c.do(req, out)
}

func (c *Client) newRequest(method, path string, body any, query url.Values) (*http.Request, error) {
	u := c.ServerURL + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}

	var reader io.Reader
	if body != nil {
		buf, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("marshal request body: %w", err)
		}
		reader = bytes.NewReader(buf)
	}

	req, err := http.NewRequest(method, u, reader)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.UserAgent)
	req.Header.Set("X-Request-ID", newRequestID())
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
		// Match MANAGEMENT_SERVER.md §5: write endpoints require an
		// idempotency key. Reuse the request-id as the key; retry logic
		// keeps the same id across attempts.
		if methodIsWrite(method) {
			req.Header.Set("X-Idempotency-Key", req.Header.Get("X-Request-ID"))
		}
	}

	if c.TokenFn != nil {
		tok, err := c.TokenFn()
		if err != nil {
			return nil, fmt.Errorf("fetch auth token: %w", err)
		}
		if tok != "" {
			req.Header.Set("Authorization", "Bearer "+tok)
		}
	}
	return req, nil
}

func (c *Client) do(req *http.Request, out any) error {
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read body: %w", err)
	}

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		if out != nil && len(raw) > 0 {
			if err := json.Unmarshal(raw, out); err != nil {
				return fmt.Errorf("decode response: %w (body: %s)", err, truncateForLog(raw))
			}
		}
		return nil
	}

	return parseAPIError(resp.StatusCode, resp.Header.Get("X-Request-ID"), raw)
}

func methodIsWrite(m string) bool {
	switch strings.ToUpper(m) {
	case http.MethodPost, http.MethodPut, http.MethodPatch, http.MethodDelete:
		return true
	}
	return false
}

func newRequestID() string {
	// UUIDv7-ish: 48 bits of time + 80 bits of random. Good enough for
	// request correlation; the server treats it as an opaque string.
	var buf [16]byte
	ms := time.Now().UnixMilli()
	buf[0] = byte(ms >> 40)
	buf[1] = byte(ms >> 32)
	buf[2] = byte(ms >> 24)
	buf[3] = byte(ms >> 16)
	buf[4] = byte(ms >> 8)
	buf[5] = byte(ms)
	if _, err := rand.Read(buf[6:]); err != nil {
		// Extremely unlikely; fall back to time-only.
		return fmt.Sprintf("%x", buf[:6])
	}
	// Set version=7, variant=RFC4122.
	buf[6] = (buf[6] & 0x0F) | 0x70
	buf[8] = (buf[8] & 0x3F) | 0x80
	s := hex.EncodeToString(buf[:])
	return fmt.Sprintf("%s-%s-%s-%s-%s", s[0:8], s[8:12], s[12:16], s[16:20], s[20:32])
}

func truncateForLog(b []byte) string {
	const max = 512
	if len(b) > max {
		return string(b[:max]) + "…"
	}
	return string(b)
}
