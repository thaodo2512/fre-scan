#!/usr/bin/env bash
# Set up a Freqtrade development environment with Docker Compose.

set -euo pipefail

trap 'rc=$?; printf "[ERROR] %s: line %d returned %d\n" "${BASH_SOURCE[0]}" "${LINENO}" "${rc}" >&2; exit "${rc}"' ERR

readonly COMPOSE_FILE_URL="https://raw.githubusercontent.com/freqtrade/freqtrade/stable/docker-compose.yml"
readonly USERDATA_DIR="ft_userdata"
readonly IMAGE_NAME="freqtradeorg/freqtrade:develop"

log() {
  printf "[INFO] %s\n" "$*"
}

warn() {
  printf "[WARN] %s\n" "$*" >&2
}

require_sudo() {
  if (( EUID != 0 )) && ! command -v sudo >/dev/null 2>&1; then
    printf "[ERROR] This script needs root privileges or sudo.\n" >&2
    exit 1
  fi
}

is_ubuntu() {
  [[ -f /etc/os-release ]] || return 1
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]]
}

ensure_ubuntu() {
  if ! is_ubuntu; then
    warn "Automatic installation is only implemented for Ubuntu. Install Docker and Docker Compose manually."
    exit 1
  fi
}

install_docker_suite() {
  ensure_ubuntu
  require_sudo
  log "Installing Docker Engine and Docker Compose via apt..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg lsb-release

  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  fi

  if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  fi

  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Docker not found. Installing..."
    install_docker_suite
  else
    log "Docker already installed."
  fi
}

ensure_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin already available."
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    log "docker-compose standalone detected."
    return
  fi

  log "Docker Compose not found. Installing..."
  install_docker_suite

  if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
    printf "[ERROR] Docker Compose installation failed.\n" >&2
    exit 1
  fi
}

download_compose_file() {
  local target="docker-compose.yml"
  log "Downloading official Freqtrade docker-compose.yml..."
  curl -fsSL "${COMPOSE_FILE_URL}" -o "${target}"
}

pull_freqtrade_image() {
  log "Pulling ${IMAGE_NAME} image..."
  docker pull "${IMAGE_NAME}"
}

create_userdata_dir() {
  if [[ -d "${USERDATA_DIR}" ]]; then
    log "Directory ${USERDATA_DIR} already exists."
  else
    log "Creating directory ${USERDATA_DIR}..."
    mkdir -p "${USERDATA_DIR}"
  fi
}

main() {
  ensure_docker
  ensure_docker_compose
  create_userdata_dir
  download_compose_file
  pull_freqtrade_image
  log "Freqtrade development environment bootstrap complete."
}

main "$@"
