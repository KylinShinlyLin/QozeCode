#!/usr/bin/env bash
set -e

REPO_OWNER="${REPO_OWNER:-<your-github-username>}"
REPO_NAME="${REPO_NAME:-QozeCode}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.qoze}"
BIN_LINK="/usr/local/bin/qoze"  # macOS 常用可写路径（需 sudo 时提示）
SHELL_RC="${SHELL_RC:-$HOME/.zshrc}" # 默认 zsh；如用户是 bash 可改 ~/.bashrc

detect_os_arch() {
  OS=$(uname -s | tr '[:upper:]' '[:lower:]')   # darwin or linux
  ARCH=$(uname -m)                              # arm64 or x86_64
  echo "Detected: ${OS}/${ARCH}"
}

latest_release_asset_url() {
  detect_os_arch
  API="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
  # 需要 jq；如用户没装 jq 可改为 grep/sed 解析
  URL=$(curl -sL "$API" | jq -r ".assets[] | select(.name | test(\"Qoze-${OS}-${ARCH}.*\")) | .browser_download_url" | head -n1)
  if [[ -z "$URL" || "$URL" == "null" ]]; then
    echo "No asset for ${OS}/${ARCH} found in latest release."
    exit 1
  fi
  echo "$URL"
}

download_and_install() {
  URL=$(latest_release_asset_url)
  mkdir -p "$INSTALL_DIR"
  TMP_TGZ="$INSTALL_DIR/Qoze.tar.gz"
  echo "Downloading: $URL"
  curl -L "$URL" -o "$TMP_TGZ"
  echo "Extracting to $INSTALL_DIR"
  tar -xzf "$TMP_TGZ" -C "$INSTALL_DIR"
  rm -f "$TMP_TGZ"

  # 生成/更新可执行链接
  TARGET_BIN="$INSTALL_DIR/Qoze/Qoze"
  if [[ ! -x "$TARGET_BIN" ]]; then
    echo "Binary not found: $TARGET_BIN"
    exit 1
  fi

  if [[ -e "$BIN_LINK" ]]; then
    echo "Updating symlink: $BIN_LINK"
    sudo rm -f "$BIN_LINK"
  fi
  echo "Creating symlink: $BIN_LINK -> $TARGET_BIN"
  sudo ln -s "$TARGET_BIN" "$BIN_LINK"
}

write_env_vars() {
  echo "Configure required environment variables."
  # 按需询问；用户可直接回车跳过
  read -r -p "OPENAI_API_KEY: " OPENAI_API_KEY
  read -r -p "TAVILY_API_KEY: " TAVILY_API_KEY
  read -r -p "AWS_ACCESS_KEY_ID: " AWS_ACCESS_KEY_ID
  read -r -p "AWS_SECRET_ACCESS_KEY: " AWS_SECRET_ACCESS_KEY
  read -r -p "AWS_REGION (e.g. us-east-1): " AWS_REGION
  read -r -p "GOOGLE_APPLICATION_CREDENTIALS (path to JSON): " GOOGLE_APPLICATION_CREDENTIALS

  {
    echo ""
    echo "# Qoze env vars"
    [[ -n "$OPENAI_API_KEY" ]] && echo "export OPENAI_API_KEY=\"$OPENAI_API_KEY\""
    [[ -n "$TAVILY_API_KEY" ]] && echo "export TAVILY_API_KEY=\"$TAVILY_API_KEY\""
    [[ -n "$AWS_ACCESS_KEY_ID" ]] && echo "export AWS_ACCESS_KEY_ID=\"$AWS_ACCESS_KEY_ID\""
    [[ -n "$AWS_SECRET_ACCESS_KEY" ]] && echo "export AWS_SECRET_ACCESS_KEY=\"$AWS_SECRET_ACCESS_KEY\""
    [[ -n "$AWS_REGION" ]] && echo "export AWS_REGION=\"$AWS_REGION\""
    [[ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]] && echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$GOOGLE_APPLICATION_CREDENTIALS\""
  } >> "$SHELL_RC"

  echo "Environment exported to $SHELL_RC"
  echo "Please reload your shell: source $SHELL_RC"
}

usage() {
  echo "Usage: install.sh [--update] [--no-env]"
  echo "  --update  Reinstall from latest release and refresh symlink"
  echo "  --no-env  Skip environment variable prompts"
}

main() {
  UPDATE=0
  NO_ENV=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --update) UPDATE=1; shift ;;
      --no-env) NO_ENV=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown arg: $1"; usage; exit 1 ;;
    esac
  done

  download_and_install

  if [[ $NO_ENV -eq 0 ]]; then
    write_env_vars
  fi

  echo "Done. Run: qoze"
}

main "$@"