// Package output centralizes mgmt-ctl's human/json output split.
// Every command calls Print() once with the API response; the --json
// global flag flips the formatter from human text to the raw JSON body.
package output

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"text/tabwriter"
)

// Format controls the formatter's output mode.
type Format int

const (
	FormatHuman Format = iota
	FormatJSON
)

// Printer renders values to w in the selected format.
type Printer struct {
	W      io.Writer
	Format Format
}

func New(format Format) *Printer { return &Printer{W: os.Stdout, Format: format} }

// Print emits a value. Human mode delegates to the type-specific
// formatters below; JSON mode indents with two spaces.
func (p *Printer) Print(v any) error {
	if p.Format == FormatJSON {
		enc := json.NewEncoder(p.W)
		enc.SetIndent("", "  ")
		return enc.Encode(v)
	}
	if f, ok := v.(HumanFormatter); ok {
		return f.FormatHuman(p.W)
	}
	// Fallback: pretty-print JSON so at least nothing is lost.
	enc := json.NewEncoder(p.W)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

// HumanFormatter is implemented by response types that want a human layout
// richer than pretty-JSON (tables, one-liners, etc).
type HumanFormatter interface {
	FormatHuman(w io.Writer) error
}

// Table is a small helper for tabular human output.
type Table struct {
	Columns []string
	Rows    [][]string
}

// WriteTo writes the table with tab-aligned columns.
func (t Table) WriteTo(w io.Writer) (int64, error) {
	tw := tabwriter.NewWriter(w, 0, 2, 2, ' ', 0)
	if _, err := fmt.Fprintln(tw, strings.Join(t.Columns, "\t")); err != nil {
		return 0, err
	}
	for _, row := range t.Rows {
		if _, err := fmt.Fprintln(tw, strings.Join(row, "\t")); err != nil {
			return 0, err
		}
	}
	if err := tw.Flush(); err != nil {
		return 0, err
	}
	return 0, nil
}
