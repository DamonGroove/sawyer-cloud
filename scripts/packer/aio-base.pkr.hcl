#
# scripts/packer/aio-base.pkr.hcl
#
# Packer template for the sawyer-cloud VM image. Produces qcow2 (KVM/
# Proxmox), vmdk (VMware), and raw artifacts that boot into a systemd
# host with Docker, the aio-base image pre-pulled, and a one-shot
# first-boot.service that reads the customer's /mnt/sawyer-config/
# (provided by the hypervisor as a cloud-init config drive or 9p mount)
# and runs bootstrap-aio.
#
# Build:
#   packer init scripts/packer/aio-base.pkr.hcl
#   packer build scripts/packer/aio-base.pkr.hcl
#
# Outputs land in scripts/packer/output-<format>/ (relative to repo root).
#

packer {
  required_version = ">= 1.9.0"

  required_plugins {
    qemu = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

# --- variables -------------------------------------------------------------
variable "aio_image_tag" {
  type        = string
  default     = "latest"
  description = "ghcr.io/sawyer-cloud/aio-base tag to bake into the image."
}

variable "output_formats" {
  type        = list(string)
  default     = ["qcow2", "vmdk", "raw"]
  description = "Qemu output formats to produce."
}

variable "disk_size" {
  type    = string
  default = "40G"
}

variable "iso_url" {
  type        = string
  default     = "https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso"
  description = "Base ISO. Ubuntu 24.04 LTS — supported through 2029."
}

variable "iso_checksum" {
  type        = string
  # Placeholder: operators must pin to the SHA-256 of the ISO they build
  # against. `none` is rejected by Packer ≥ 1.7 so keep this set via CLI.
  default     = "file:https://releases.ubuntu.com/24.04/SHA256SUMS"
  description = "ISO checksum or a URL to a SHA-256 SUMS file."
}

# --- source ---------------------------------------------------------------
# One source per output format so Packer produces parallel artifacts.

source "qemu" "aio-base-qcow2" {
  iso_url          = var.iso_url
  iso_checksum     = var.iso_checksum
  output_directory = "scripts/packer/output-qcow2"
  disk_size        = var.disk_size
  format           = "qcow2"
  accelerator      = "kvm"
  ssh_username     = "sawyer"
  ssh_timeout      = "30m"
  shutdown_command = "sudo systemctl poweroff"
  memory           = 4096
  cpus             = 2
  http_directory   = "scripts/packer/files"
  boot_wait        = "5s"
  boot_command = [
    "<esc><wait>c<wait>",
    "linux /casper/vmlinuz autoinstall ",
    "ds='nocloud-net;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/'",
    "<enter>",
    "initrd /casper/initrd<enter>",
    "boot<enter>",
  ]
}

source "qemu" "aio-base-vmdk" {
  iso_url          = var.iso_url
  iso_checksum     = var.iso_checksum
  output_directory = "scripts/packer/output-vmdk"
  disk_size        = var.disk_size
  format           = "raw"
  # VMDK produced via post-processor; see build block below.
  accelerator      = "kvm"
  ssh_username     = "sawyer"
  ssh_timeout      = "30m"
  shutdown_command = "sudo systemctl poweroff"
  memory           = 4096
  cpus             = 2
  http_directory   = "scripts/packer/files"
  boot_wait        = "5s"
  boot_command = [
    "<esc><wait>c<wait>",
    "linux /casper/vmlinuz autoinstall ",
    "ds='nocloud-net;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/'",
    "<enter>",
    "initrd /casper/initrd<enter>",
    "boot<enter>",
  ]
}

# --- build ----------------------------------------------------------------
build {
  name = "aio-base"
  sources = [
    "source.qemu.aio-base-qcow2",
    "source.qemu.aio-base-vmdk",
  ]

  # Common host prep: install docker, preload the aio-base image.
  provisioner "shell" {
    execute_command = "echo 'sawyer' | sudo -S -E bash -c '{{ .Vars }} {{ .Path }}'"
    inline = [
      "export DEBIAN_FRONTEND=noninteractive",
      "apt-get update -y",
      "apt-get install -y ca-certificates curl gnupg age",
      # Docker via the official convenience script.
      "curl -fsSL https://get.docker.com | sh",
      "systemctl enable --now docker",
      # Preload base image so first boot isn't held up by an image pull.
      "docker pull ghcr.io/sawyer-cloud/aio-base:${var.aio_image_tag}",
      # Housekeeping
      "apt-get autoremove -y",
      "apt-get clean",
      "rm -rf /var/lib/apt/lists/*",
    ]
  }

  # First-boot systemd unit + its script.
  provisioner "file" {
    source      = "scripts/packer/files/first-boot.sh"
    destination = "/tmp/first-boot.sh"
  }

  provisioner "file" {
    source      = "scripts/packer/files/first-boot.service"
    destination = "/tmp/first-boot.service"
  }

  # Cloud-init datasource customization.
  provisioner "file" {
    source      = "scripts/packer/files/90-customer.cfg"
    destination = "/tmp/90-customer.cfg"
  }

  provisioner "shell" {
    execute_command = "echo 'sawyer' | sudo -S -E bash -c '{{ .Vars }} {{ .Path }}'"
    inline = [
      "install -m 0755 /tmp/first-boot.sh /usr/local/bin/first-boot.sh",
      "install -m 0644 /tmp/first-boot.service /etc/systemd/system/first-boot.service",
      "install -m 0644 /tmp/90-customer.cfg /etc/cloud/cloud.cfg.d/90-customer.cfg",
      "systemctl enable first-boot.service",
      "rm -f /tmp/first-boot.sh /tmp/first-boot.service /tmp/90-customer.cfg",
    ]
  }

  # Convert the raw output of the vmdk source into an actual vmdk via qemu-img.
  post-processor "shell-local" {
    only = ["qemu.aio-base-vmdk"]
    inline = [
      "raw=scripts/packer/output-vmdk/packer-aio-base-vmdk",
      "qemu-img convert -f raw -O vmdk \"$raw\" scripts/packer/output-vmdk/aio-base.vmdk",
    ]
  }
}
