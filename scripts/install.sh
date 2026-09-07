#!/usr/bin/env bash
# Installs agent definitions from this repository into a supported tool's
# agent directory.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh --tool <name> [--categories cat1,cat2,...]

Options:
  --tool <name>          Target tool to install agents for.
                          Supported: claude-code
  --categories <list>    Comma-separated list of category directories to
                          install (default: all categories in the repo)
  -h, --help              Show this help and exit

Examples:
  ./scripts/install.sh --tool claude-code
  ./scripts/install.sh --tool claude-code --categories engineering,design
EOF
}

tool=""
categories_arg=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tool)
      tool="${2:-}"
      shift 2
      ;;
    --categories)
      categories_arg="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$tool" ]]; then
  echo "Error: --tool is required" >&2
  usage
  exit 1
fi

case "$tool" in
  claude-code)
    target_dir="$HOME/.claude/agents"
    ;;
  *)
    echo "Error: unsupported tool '$tool' (supported: claude-code)" >&2
    exit 1
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

categories=()
if [[ -n "$categories_arg" ]]; then
  IFS=',' read -ra categories <<< "$categories_arg"
else
  while IFS= read -r dir; do
    categories+=("$(basename "$dir")")
  done < <(find "$repo_root" -mindepth 1 -maxdepth 1 -type d \
             ! -name '.git' ! -name 'scripts' | sort)
fi

mkdir -p "$target_dir"

installed=0
for category in "${categories[@]}"; do
  category_dir="$repo_root/$category"
  if [[ ! -d "$category_dir" ]]; then
    echo "Warning: category '$category' not found, skipping" >&2
    continue
  fi

  shopt -s nullglob
  files=("$category_dir"/*.md)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    continue
  fi

  for file in "${files[@]}"; do
    cp "$file" "$target_dir/"
    echo "Installed $(basename "$file") (from $category)"
    installed=$((installed + 1))
  done
done

echo ""
if [[ "$installed" -eq 0 ]]; then
  echo "No agents installed. Check that --categories names match directories in the repo."
  exit 1
fi

echo "Installed $installed agent(s) to $target_dir"
echo
echo 'Activate any agent in a Claude Code session, e.g.:'
echo '  "Hey Claude, activate Frontend Developer mode and help me build a React component"'
