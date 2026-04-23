package cmd

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
)

type customer struct {
	ID                string  `json:"id"`
	Slug              string  `json:"slug"`
	DisplayName       string  `json:"display_name"`
	Domain            string  `json:"domain"`
	FlavorSlug        string  `json:"flavor_slug"`
	SiteMode          string  `json:"site_mode"`
	State             string  `json:"state"`
	DeployedImageTag  *string `json:"deployed_image_tag"`
	LastSeenAt        *string `json:"last_seen_at"`
}

type customerList []customer

func (l customerList) FormatHuman(w io.Writer) error {
	rows := make([][]string, 0, len(l))
	for _, c := range l {
		tag := ""
		if c.DeployedImageTag != nil {
			tag = *c.DeployedImageTag
		}
		lastSeen := ""
		if c.LastSeenAt != nil {
			lastSeen = *c.LastSeenAt
		}
		rows = append(rows, []string{c.Slug, c.FlavorSlug, c.State, lastSeen, tag})
	}
	fmt.Fprintln(w, joinTabs([]string{"SLUG", "FLAVOR", "STATE", "LAST SEEN", "VERSION"}))
	for _, r := range rows {
		fmt.Fprintln(w, joinTabs(r))
	}
	return nil
}

func (c customer) FormatHuman(w io.Writer) error {
	tag := "(none)"
	if c.DeployedImageTag != nil {
		tag = *c.DeployedImageTag
	}
	lastSeen := "(never)"
	if c.LastSeenAt != nil {
		lastSeen = *c.LastSeenAt
	}
	fmt.Fprintf(w, "%s (%s)\n", c.DisplayName, c.Slug)
	fmt.Fprintf(w, "  flavor:    %s\n", c.FlavorSlug)
	fmt.Fprintf(w, "  domain:    %s\n", c.Domain)
	fmt.Fprintf(w, "  site mode: %s\n", c.SiteMode)
	fmt.Fprintf(w, "  state:     %s\n", c.State)
	fmt.Fprintf(w, "  version:   %s\n", tag)
	fmt.Fprintf(w, "  last seen: %s\n", lastSeen)
	return nil
}

func customersGroup() *cobra.Command {
	cmd := &cobra.Command{Use: "customers", Short: "Customer onboarding and queries"}
	cmd.AddCommand(customersListCmd(), customersShowCmd(), customersCreateCmd())
	cmd.AddCommand(stubCmd("decommission", "Mark customer decommissioned. Irreversible."))
	cmd.AddCommand(stubCmd("diff", "Compare two customers' feature bindings and versions."))
	return cmd
}

func customersListCmd() *cobra.Command {
	var flavor, state string
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List all customers",
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := newClient()
			if err != nil {
				return err
			}
			q := url.Values{}
			if flavor != "" {
				q.Set("flavor", flavor)
			}
			if state != "" {
				q.Set("state", state)
			}
			var list customerList
			if err := c.DoQuery(http.MethodGet, "/api/v1/customers", q, nil, &list); err != nil {
				return err
			}
			return newPrinter().Print(list)
		},
	}
	cmd.Flags().StringVar(&flavor, "flavor", "", "filter by flavor slug")
	cmd.Flags().StringVar(&state, "state", "", "filter by state (pending|healthy|degraded|offline|decommissioned)")
	return cmd
}

func customersShowCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "show <slug>",
		Short: "Show one customer's full state",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := newClient()
			if err != nil {
				return err
			}
			var cust customer
			if err := c.Do(http.MethodGet, "/api/v1/customers/"+args[0], nil, &cust); err != nil {
				return err
			}
			return newPrinter().Print(cust)
		},
	}
}

type createOut struct {
	Customer          customer `json:"customer"`
	RegistrationToken string   `json:"registration_token"`
}

func (o createOut) FormatHuman(w io.Writer) error {
	if err := o.Customer.FormatHuman(w); err != nil {
		return err
	}
	fmt.Fprintf(w, "\nRegistration token (one-time, store in customer.env.secret.age):\n  %s\n",
		o.RegistrationToken)
	return nil
}

func customersCreateCmd() *cobra.Command {
	var displayName, domain, flavor, siteMode string
	cmd := &cobra.Command{
		Use:   "create <slug>",
		Short: "Onboard a new customer",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			slug := args[0]
			if displayName == "" || domain == "" || flavor == "" {
				return &userError{msg: "--display-name, --domain, and --flavor are required"}
			}
			if siteMode == "" {
				siteMode = "docker"
			}
			body := map[string]any{
				"slug":         slug,
				"display_name": displayName,
				"domain":       domain,
				"flavor":       flavor,
				"site_mode":    siteMode,
			}
			c, err := newClient()
			if err != nil {
				return err
			}
			var out createOut
			if err := c.Do(http.MethodPost, "/api/v1/customers", body, &out); err != nil {
				return err
			}
			return newPrinter().Print(out)
		},
	}
	cmd.Flags().StringVar(&displayName, "display-name", "", "human-readable name")
	cmd.Flags().StringVar(&domain, "domain", "", "customer-facing domain (e.g. cloud.acme.example.com)")
	cmd.Flags().StringVar(&flavor, "flavor", "default", "flavor slug")
	cmd.Flags().StringVar(&siteMode, "site-mode", "docker", "docker | vm")
	return cmd
}

// ----- enroll (re-issue a registration token for an existing customer) ---

func enrollCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "enroll <slug>",
		Short: "Generate a one-time registration token for the customer's agent",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			c, err := newClient()
			if err != nil {
				return err
			}
			var out struct {
				RegistrationToken string `json:"registration_token"`
			}
			if err := c.Do(http.MethodPost, "/api/v1/customers/"+args[0]+"/enroll", nil, &out); err != nil {
				return err
			}
			if flagJSON {
				return newPrinter().Print(out)
			}
			fmt.Println(out.RegistrationToken)
			return nil
		},
	}
}

// ---------- table helper ----------

func joinTabs(cols []string) string {
	return strings.Join(cols, "\t")
}
