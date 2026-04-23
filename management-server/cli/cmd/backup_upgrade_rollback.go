package cmd

import (
	"fmt"
	"io"
	"net/http"

	"github.com/spf13/cobra"
)

// All three commands here enqueue a command on the management server and
// return whatever the server echoes back. Polling for command completion
// is a future enhancement (MGMT_CTL_CLI_SPEC.md §upgrade mentions it).

type commandQueued struct {
	ID    string `json:"id"`
	State string `json:"state"`
	Kind  string `json:"kind"`
}

func (c commandQueued) FormatHuman(w io.Writer) error {
	fmt.Fprintf(w, "queued command %s (kind=%s, state=%s)\n", c.ID, c.Kind, c.State)
	return nil
}

// ----- backup ---------------------------------------------------------------

func backupCmd() *cobra.Command {
	var label string
	cmd := &cobra.Command{
		Use:   "backup <slug>",
		Short: "Trigger a borg backup now",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := newClient()
			if err != nil {
				return err
			}
			body := map[string]any{}
			if label != "" {
				body["label"] = label
			}
			path := fmt.Sprintf("/api/v1/customers/%s/backups", args[0])
			var out commandQueued
			if err := c.Do(http.MethodPost, path, body, &out); err != nil {
				return err
			}
			return newPrinter().Print(out)
		},
	}
	cmd.Flags().StringVar(&label, "label", "", "free-form label stored with the archive")
	return cmd
}

// ----- restore (stubbed fully in Phase 3; left as a clear wrapper) ----------

func restoreCmd() *cobra.Command {
	var archive string
	cmd := &cobra.Command{
		Use:   "restore <slug> --archive <id>",
		Short: "Restore from a named backup archive (irreversible)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if archive == "" {
				return &userError{msg: "--archive is required"}
			}
			if !confirm(fmt.Sprintf("Restore %s from archive %s? This overwrites current state.", args[0], archive)) {
				return &userError{msg: "aborted"}
			}
			c, err := newClient()
			if err != nil {
				return err
			}
			// NOTE: the server also wants `X-Confirm: restore-overwrites-state`
			// on the wire; our thin client does not yet expose per-call
			// custom headers. The server route is still 501-stubbed in
			// Phase 3, so the missing header is not observable today.
			// Follow-up: add Client.DoWithHeaders when the route lands.
			path := fmt.Sprintf("/api/v1/customers/%s/backups/%s/restore", args[0], archive)
			var out commandQueued
			if err := c.Do(http.MethodPost, path, nil, &out); err != nil {
				return err
			}
			return newPrinter().Print(out)
		},
	}
	cmd.Flags().StringVar(&archive, "archive", "", "archive id (see `mgmt-ctl backups list <slug>`)")
	return cmd
}

// ----- rollback -------------------------------------------------------------

func rollbackCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "rollback <slug>",
		Short: "Revert to the previous image tag for this customer",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !confirm(fmt.Sprintf("Roll %s back to its previous image tag?", args[0])) {
				return &userError{msg: "aborted"}
			}
			c, err := newClient()
			if err != nil {
				return err
			}
			path := fmt.Sprintf("/api/v1/customers/%s/rollback", args[0])
			var out commandQueued
			if err := c.Do(http.MethodPost, path, nil, &out); err != nil {
				return err
			}
			return newPrinter().Print(out)
		},
	}
}

// ----- upgrade --------------------------------------------------------------

func upgradeCmd() *cobra.Command {
	var toTag string
	var noBackupOverride bool
	cmd := &cobra.Command{
		Use:   "upgrade <slug> --to <tag>",
		Short: "Upgrade a customer to a named image tag",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if toTag == "" {
				return &userError{msg: "--to <tag> is required"}
			}
			if !confirm(fmt.Sprintf("Upgrade %s to %s?", args[0], toTag)) {
				return &userError{msg: "aborted"}
			}
			c, err := newClient()
			if err != nil {
				return err
			}
			path := fmt.Sprintf("/api/v1/customers/%s/upgrade", args[0])
			body := map[string]any{
				"to_tag":              toTag,
				"no_backup_override":  noBackupOverride,
			}
			var out commandQueued
			if err := c.Do(http.MethodPost, path, body, &out); err != nil {
				return err
			}
			return newPrinter().Print(out)
		},
	}
	cmd.Flags().StringVar(&toTag, "to", "", "target image tag (must be >= current)")
	cmd.Flags().BoolVar(&noBackupOverride, "no-backup-override", false, "skip the 'recent backup exists' check (requires OVERRIDE)")
	return cmd
}
