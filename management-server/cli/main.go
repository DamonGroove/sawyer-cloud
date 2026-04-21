// mgmt-ctl — sawyer-cloud operator CLI.
//
// Thin wrapper around the management-server API. Every command maps 1:1
// to an API call (MGMT_CTL_CLI_SPEC.md design principle #1). See
// management-server/CLI_SPEC.md for the full command surface.
package main

import (
	"fmt"
	"os"

	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/cmd"
)

// Version gets stamped at link time by the Makefile (`-ldflags "-X main.Version=..."`).
var Version = "dev"

func main() {
	cmd.Version = Version
	if err := cmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(cmd.ExitCodeFor(err))
	}
}
