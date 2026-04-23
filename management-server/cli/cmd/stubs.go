package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

// stubCmd returns a leaf command that exits 1 with a clear message.
// Used for every command in MGMT_CTL_CLI_SPEC.md that isn't part of the
// Phase 3 required-implemented list.
func stubCmd(name, short string) *cobra.Command {
	return &cobra.Command{
		Use:   name,
		Short: short + " (not implemented in Phase 3)",
		RunE: func(cmd *cobra.Command, args []string) error {
			return &userError{msg: fmt.Sprintf("%s: not implemented in Phase 3", name)}
		},
	}
}

// stubGroup returns a parent command whose children are all stubs. Used
// for `mgmt-ctl agents`, `mgmt-ctl features`, etc — the shape of the
// command tree is visible via --help even before real impls land.
func stubGroup(name, short string) *cobra.Command {
	parent := &cobra.Command{
		Use:   name,
		Short: short + " (skeleton)",
		RunE: func(cmd *cobra.Command, args []string) error {
			return cmd.Help()
		},
	}
	// Populate sub-commands based on the name — matches the MGMT_CTL_CLI_SPEC.md
	// tree under each group.
	switch name {
	case "agents":
		parent.AddCommand(
			stubCmd("list", "List agents for a customer"),
			stubCmd("rotate", "Rotate the agent's mTLS cert"),
			stubCmd("revoke", "Revoke the agent's mTLS cert"),
		)
	case "features":
		parent.AddCommand(
			stubCmd("list", "List features"),
			stubCmd("enable", "Enable a feature on a customer"),
			stubCmd("disable", "Disable a feature on a customer"),
		)
	case "images":
		parent.AddCommand(
			stubCmd("list", "List base images"),
			stubCmd("show", "Show one image's metadata"),
			stubCmd("promote", "Promote a tag to staging-green or production"),
		)
	case "audit":
		parent.AddCommand(
			stubCmd("list", "Search the audit log"),
			stubCmd("export", "Stream the audit log as CSV or NDJSON"),
		)
	case "backups":
		parent.AddCommand(
			stubCmd("list", "List archives for a customer"),
			stubCmd("pause", "Pause scheduled backups for a customer"),
			stubCmd("resume", "Resume scheduled backups for a customer"),
			stubCmd("set-target", "Set the backup target (local path or s3 bucket)"),
		)
	case "ollama":
		parent.AddCommand(
			stubCmd("pull", "Pull a model into the customer's Ollama cache"),
			stubCmd("list", "List models pulled on the customer's Ollama"),
		)
	case "litellm":
		parent.AddCommand(
			stubCmd("rotate", "Rotate a provider key in the LiteLLM container"),
			stubCmd("reload", "Re-read LiteLLM's config.yaml"),
		)
	case "break-glass":
		parent.AddCommand(
			stubCmd("request", "Request temporary privilege elevation"),
			stubCmd("approve", "Approve a pending break-glass request"),
		)
	}
	return parent
}
