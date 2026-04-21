package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"

	"github.com/sawyer-cloud/sawyer-cloud/management-server/cli/pkg/auth"
)

// configFile mirrors ~/.config/mgmt-ctl/config.yaml.
type configFile struct {
	Server        string `yaml:"server,omitempty"`
	DefaultOutput string `yaml:"default_output,omitempty"`
	Profiles      map[string]struct {
		Server string `yaml:"server"`
	} `yaml:"profiles,omitempty"`
}

func loadConfigFile() (*configFile, error) {
	p, err := configFilePath()
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return &configFile{}, nil
		}
		return nil, err
	}
	var c configFile
	if err := yaml.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("parse %s: %w", p, err)
	}
	return &c, nil
}

func configFilePath() (string, error) {
	if p := os.Getenv("MGMT_CTL_CONFIG"); p != "" {
		return p, nil
	}
	dir, err := auth.ConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "config.yaml"), nil
}

func resolveProfile(name string) (string, error) {
	c, err := loadConfigFile()
	if err != nil {
		return "", err
	}
	p, ok := c.Profiles[name]
	if !ok {
		return "", &userError{msg: fmt.Sprintf("no profile named %q in %s", name, mustConfigPath())}
	}
	if p.Server == "" {
		return "", &userError{msg: fmt.Sprintf("profile %q has no server set", name)}
	}
	return p.Server, nil
}

func mustConfigPath() string {
	p, err := configFilePath()
	if err != nil {
		return "(unknown)"
	}
	return p
}
