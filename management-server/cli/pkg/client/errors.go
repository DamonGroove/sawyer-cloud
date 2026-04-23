package client

import (
	"encoding/json"
	"fmt"
)

// APIError is returned for non-2xx responses. Maps to mgmt-ctl exit codes:
//
//	400–499 (except 401/403)  →  exit 1 (user error)
//	401 / 403                  →  exit 2 (auth error)
//	500–599                    →  exit 3 (server error)
//	408 / 504                  →  exit 5 (timeout)
//
// Per MGMT_CTL_CLI_SPEC.md §Exit codes.
type APIError struct {
	StatusCode int
	RequestID  string
	Detail     string // server's `detail` field, or raw body if not JSON
	Raw        []byte
}

func (e *APIError) Error() string {
	rid := ""
	if e.RequestID != "" {
		rid = fmt.Sprintf(" (request-id: %s)", e.RequestID)
	}
	return fmt.Sprintf("server returned %d: %s%s", e.StatusCode, e.Detail, rid)
}

// ExitCode maps the API status to the CLI exit code spec.
func (e *APIError) ExitCode() int {
	switch {
	case e.StatusCode == 401 || e.StatusCode == 403:
		return 2
	case e.StatusCode == 408 || e.StatusCode == 504:
		return 5
	case e.StatusCode >= 500:
		return 3
	case e.StatusCode == 501:
		return 3 // not-implemented counts as server-side for the CLI's purposes
	default:
		return 1
	}
}

func parseAPIError(status int, requestID string, body []byte) *APIError {
	e := &APIError{StatusCode: status, RequestID: requestID, Raw: body}
	var shape struct {
		Detail any `json:"detail"`
	}
	if err := json.Unmarshal(body, &shape); err == nil && shape.Detail != nil {
		switch v := shape.Detail.(type) {
		case string:
			e.Detail = v
		default:
			// Pydantic-style validation errors are a list; flatten to a
			// readable line.
			b, _ := json.Marshal(v)
			e.Detail = string(b)
		}
	} else {
		e.Detail = truncateForLog(body)
	}
	return e
}
