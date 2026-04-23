package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/pkg/auth"
)

// ----- login ----------------------------------------------------------------

func loginCmd() *cobra.Command {
	var (
		issuer   string
		clientID string
		devEmail string
		devRoles []string
	)
	cmd := &cobra.Command{
		Use:   "login",
		Short: "Start an SSO session (OIDC device-code flow)",
		Long: `Logs you in to the management server.

Default flow is the OIDC device-code grant: the CLI obtains a user-code
from the IdP, prints the verification URL, and polls until you finish
authenticating in your browser. The resulting access + refresh tokens
land in ~/.config/mgmt-ctl/session.json (mode 0600).

For local development without a real IdP, pass --dev-email to mint a
session JWT directly from the management server's /api/v1/auth/dev-login
endpoint (only available when the server runs with ENVIRONMENT=dev).`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if devEmail != "" {
				return runDevLogin(devEmail, devRoles)
			}
			if issuer == "" {
				return &userError{msg: "either --issuer (for OIDC) or --dev-email (for local dev) is required"}
			}
			return runDeviceLogin(issuer, clientID)
		},
	}
	cmd.Flags().StringVar(&issuer, "issuer", os.Getenv("MGMT_CTL_OIDC_ISSUER"), "OIDC issuer base URL")
	cmd.Flags().StringVar(&clientID, "client-id", os.Getenv("MGMT_CTL_OIDC_CLIENT_ID"), "OIDC client id")
	cmd.Flags().StringVar(&devEmail, "dev-email", "", "DEV ONLY: mint a session against /auth/dev-login")
	cmd.Flags().StringSliceVar(&devRoles, "dev-roles", []string{"operator"}, "DEV ONLY: roles for --dev-email")
	return cmd
}

func runDeviceLogin(issuer, clientID string) error {
	cfg := auth.DeviceCodeConfig{Issuer: issuer, ClientID: clientID}
	sess, err := auth.DeviceLogin(cfg, func(userCode, verificationURI string) {
		fmt.Fprintf(os.Stderr,
			"Open %s in your browser and enter code: %s\n\n",
			verificationURI, userCode,
		)
	})
	if err != nil {
		return err
	}
	sess.Server = flagServer
	if err := auth.Save(sess); err != nil {
		return err
	}
	fmt.Fprintln(os.Stderr, "Login succeeded.")
	return nil
}

func runDevLogin(email string, roles []string) error {
	body := map[string]any{"email": email, "roles": roles}
	buf, _ := json.Marshal(body)
	req, err := http.NewRequest(
		http.MethodPost,
		strings.TrimSuffix(flagServer, "/")+"/api/v1/auth/dev-login",
		bytes.NewReader(buf),
	)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return &userError{msg: fmt.Sprintf("dev-login failed (status=%d): %s", resp.StatusCode, string(raw))}
	}
	var out struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return err
	}
	sess := &auth.Session{
		Server:      flagServer,
		AccessToken: out.AccessToken,
		TokenType:   out.TokenType,
		Email:       email,
		// /auth/dev-login doesn't return exp; the server caps lifetime
		// independently. Leave ExpiresAt zero so silent refresh doesn't fire.
	}
	if err := auth.Save(sess); err != nil {
		return err
	}
	fmt.Fprintf(os.Stderr, "Logged in as %s (dev, roles=%s).\n", email, strings.Join(roles, ","))
	return nil
}

// ----- logout ---------------------------------------------------------------

func logoutCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "logout",
		Short: "Revoke the current session",
		RunE: func(cmd *cobra.Command, args []string) error {
			sess, err := auth.Load()
			if err != nil {
				return err
			}
			if sess == nil {
				fmt.Fprintln(os.Stderr, "Not logged in; nothing to do.")
				return nil
			}
			// Best-effort: call /auth/logout on the server. Not fatal if it fails.
			c, err := newClient()
			if err == nil {
				_ = c.Do(http.MethodPost, "/api/v1/auth/logout", nil, nil)
			}
			if err := auth.Clear(); err != nil {
				return err
			}
			fmt.Fprintln(os.Stderr, "Logged out.")
			return nil
		},
	}
}

// ----- whoami ---------------------------------------------------------------

type meResp struct {
	UserID             *string  `json:"user_id"`
	Email              string   `json:"email"`
	Roles              []string `json:"roles"`
	AssignedCustomerIDs []string `json:"assigned_customer_ids"`
	IsService          bool     `json:"is_service"`
}

func (m meResp) FormatHuman(w io.Writer) error {
	fmt.Fprintf(w, "%s (roles=%s, %d assigned customer%s)\n",
		m.Email,
		strings.Join(m.Roles, ","),
		len(m.AssignedCustomerIDs),
		pluralS(len(m.AssignedCustomerIDs)),
	)
	return nil
}

func whoamiCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "whoami",
		Short: "Print current user, roles, and assigned customers",
		RunE: func(cmd *cobra.Command, args []string) error {
			sess, err := auth.Load()
			if err != nil {
				return err
			}
			if sess == nil {
				return notLoggedIn()
			}
			c, err := newClient()
			if err != nil {
				return err
			}
			var m meResp
			if err := c.Do(http.MethodGet, "/api/v1/users/me", nil, &m); err != nil {
				return err
			}
			return newPrinter().Print(m)
		},
	}
}

func pluralS(n int) string {
	if n == 1 {
		return ""
	}
	return "s"
}

