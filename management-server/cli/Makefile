# management-server/cli/Makefile
#
# `make build` produces a static-ish linux/amd64 binary at ./bin/mgmt-ctl.
# Cross-compiles for darwin/linux/windows × amd64/arm64 via `make release`.

BIN        := bin/mgmt-ctl
PKG        := github.com/sawyer-cloud/sawyer-cloud/management-server/cli
VERSION    ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS    := -s -w -X main.Version=$(VERSION)
GO         ?= go
# CGO disabled for portable binaries.
GOFLAGS    ?= -mod=mod
export GOSUMDB ?= off

.PHONY: help build install clean test tidy lint release

help:
	@echo "targets:"
	@echo "  build       build $(BIN) for the host platform"
	@echo "  install     go install into GOPATH/bin"
	@echo "  test        go test ./..."
	@echo "  tidy        go mod tidy"
	@echo "  lint        go vet ./..."
	@echo "  release     cross-compile for darwin/linux/windows × amd64/arm64"
	@echo "  clean       rm bin/"

build:
	CGO_ENABLED=0 $(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BIN) .
	@echo "built $(BIN) ($(VERSION))"

install:
	$(GO) install $(GOFLAGS) -ldflags "$(LDFLAGS)" .

test:
	$(GO) test $(GOFLAGS) ./...

tidy:
	$(GO) mod tidy

lint:
	$(GO) vet $(GOFLAGS) ./...

clean:
	rm -rf bin

# Release matrix. Each artifact is dropped in bin/release/.
release:
	@mkdir -p bin/release
	@for os in linux darwin windows; do \
	  for arch in amd64 arm64; do \
	    ext=""; \
	    if [ "$$os" = "windows" ]; then ext=".exe"; fi; \
	    out="bin/release/mgmt-ctl-$$os-$$arch$$ext"; \
	    echo "-> $$out"; \
	    CGO_ENABLED=0 GOOS=$$os GOARCH=$$arch $(GO) build $(GOFLAGS) \
	      -ldflags "$(LDFLAGS)" -o "$$out" . || exit 1; \
	  done; \
	done
