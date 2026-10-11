#!/bin/sh
set -eu

baseline="$1"
commit="$2"
stage=mount_access
trap 'echo "S4_FAILED_STAGE=$stage"' EXIT
mkdir -p /stage/home
export HOME=/stage/home
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TERMINAL_PROMPT=0
export GIT_NO_REPLACE_OBJECTS=1

echo "S4_STAGE=$stage"
test -r /trusted/.git/HEAD
test -r /input.bundle
test -w /stage
stage=git_init
echo "S4_STAGE=$stage"
git init --bare --quiet /stage/repository.git >/dev/null 2>&1
stage=baseline_fetch
echo "S4_STAGE=$stage"
git -c safe.directory=/trusted -C /stage/repository.git fetch --no-tags /trusted "$baseline" >/dev/null 2>&1
stage=bundle_unbundle
echo "S4_STAGE=$stage"
git -C /stage/repository.git bundle unbundle /input.bundle >/dev/null 2>&1
stage=fsck
echo "S4_STAGE=$stage"
git -C /stage/repository.git fsck --strict --no-reflogs "$commit" >/dev/null 2>&1
stage=commit_type
echo "S4_STAGE=$stage"
test "$(git -C /stage/repository.git cat-file -t "$commit")" = commit
trap - EXIT
echo "S4_GIT_VERSION=$(git --version)"
echo S4_VERIFIED
