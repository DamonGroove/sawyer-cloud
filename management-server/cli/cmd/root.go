// Package cmd holds the mgmt-ctl cobra command tree. main.go just calls
// Execute(). Each file here maps to a single §5-ish command group from
// MGMT_CTL_CLI_SPEC.md.
package cmd

import (
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/pkg/auth"
	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/pkg/client"
	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/pkg/output"
)

// Version is injected from main.go (stamped by the Makefile at link time).
var Version = "dev"

// Global flags. Populated by cobra before RunE fires.
var (
	flagServer  string
	flagProfile string
	flagJSON    bool
	flagYes     bool
)

// root is the top-level cobra command. Export-only via Execute().
var root = &cobra.Command{
	Use:   "mgmt-ctl",
	Short: "sawyer-cloud operator CLI",
	Long: `mgmt-ctl is the thin operator CLI for the sawyer-cloud management
server. Every command maps 1:1 to a management-server API call.

See management-server/CLI_SPEC.md for the full command surface.`,
	SilenceUsage:  true,
	SilenceErrors: true,
}

func init() {
	root.PersistentFlags().StringVar(&flagServer, "server", defaultServer(),
		"management-server base URL (env: MGMT_CTL_SERVER)")
	root.PersistentFlags().StringVar(&flagProfile, "profile", "",
		"named profile from ~/.config/mgmt-ctl/config.yaml (overrides --server)")
	root.PersistentFlags().BoolVar(&flagJSON, "json", false,
		"emit raw JSON instead of the human summary")
	root.PersistentFlags().BoolVarP(&flagYes, "yes", "y", false,
		"skip interactive confirmation on destructive commands")

	root.AddCommand(
		loginCmd(),
		logoutCmd(),
		whoamiCmd(),
		customersGroup(),
		enrollCmd(),
		backupCmd(),
		restoreCmd(),
		rollbackCmd(),
		upgradeCmd(),
		// Stubs — implemented just enough to exit cleanly with a "not
		// implemented in Phase 3" message and the right exit code.
		stubCmd("apply", "Re-run bootstrap against a running instance."),
		stubCmd("apply-branding", "Upload + apply a branding bundle."),
		stubCmd("status", "One-liner per customer: state, version, last-seen."),
		stubCmd("health", "Detailed health report."),
		stubCmd("logs", "Tail container logs."),
		stubCmd("occ", "Run an allow-listed occ command."),
		stubGroup("agents", "Agent management."),
		stubGroup("features", "Feature enable/disable."),
		stubGroup("images", "Base image catalog."),
		stubGroup("audit", "Audit log search."),
		stubGroup("backups", "Backup schedule & target."),
		stubGroup("ollama", "Per-customer Ollama operations."),
		stubGroup("litellm", "Per-customer LiteLLM operations."),
		stubGroup("break-glass", "Temporary privilege elevation."),
		stubCmd("restart", "Restart containers."),
		stubCmd("start", "Start a named container."),
		stubCmd("stop", "Stop a named container."),
	)
}

// Execute runs the root command.
func Execute() error { return root.Execute() }

// ExitCodeFor maps errors produced by command RunE to exit codes per
// MGMT_CTL_CLI_SPEC.md §Exit codes.
func ExitCodeFor(err error) int {
	if err == nil {
		return 0
	}
	var apiErr *client.APIError
	if errors.As(err, &apiErr) {
		return apiErr.ExitCode()
	}
	var ue *userError
	if errors.As(err, &ue) {
		return 1
	}
	var ae *authError
	if errors.As(err, &ae) {
		return 2
	}
	return 1
}

// ---------- helpers ----------

func defaultServer() string {
	if s := os.Getenv("MGMT_CTL_SERVER"); s != "" {
		return s
	}
	return "https://mgmt.internal.example.com"
}

func newClient() (*client.Client, error) {
	serverURL := flagServer
	if flagProfile != "" {
		s, err := resolveProfile(flagProfile)
		if err != nil {
			return nil, err
		}
		serverURL = s
	}
	return client.New(serverURL, auth.TokenProvider), nil
}

func newPrinter() *output.Printer {
	fmtMode := output.FormatHuman
	if flagJSON {
		fmtMode = output.FormatJSON
	}
	return output.New(fmtMode)
}

func confirm(prompt string) bool {
	if flagYes {
		return true
	}
	fmt.Fprintf(os.Stderr, "%s [y/N] ", prompt)
	var ans string
	_, _ = fmt.Fscanln(os.Stdin, &ans)
	return ans == "y" || ans == "Y"
}

// ---------- error types ----------

type userError struct{ msg string }

func (e *userError) Error() string { return e.msg }

type authError struct{ msg string }

func (e *authError) Error() string { return e.msg }

func notLoggedIn() error {
	return &authError{msg: "not logged in — run `mgmt-ctl login` first"}
}
