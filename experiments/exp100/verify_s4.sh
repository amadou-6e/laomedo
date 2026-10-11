#!/bin/sh
set -eu

# Trusted fixed invocation; source and bundle mounts are read-only, and every
# Git object written during this check stays on a capped disposable tmpfs.
baseline="$1"
commit="$2"
mkdir -p /stage/home
export HOME=/stage/home
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TERMINAL_PROMPT=0
export GIT_NO_REPLACE_OBJECTS=1

git init --bare --quiet /stage/repository.git
git -c safe.directory=/trusted -C /stage/repository.git fetch --no-tags /trusted "$baseline" >/dev/null 2>&1
git -C /stage/repository.git bundle unbundle /input.bundle >/dev/null 2>&1
git -C /stage/repository.git fsck --strict --no-reflogs "$commit" >/dev/null 2>&1
test "$(git -C /stage/repository.git cat-file -t "$commit")" = commit
echo "S4_GIT_VERSION=$(git --version)"
echo S4_VERIFIED
