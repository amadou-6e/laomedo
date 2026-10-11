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
test -r /baseline.bundle
test -r /input.bundle
test -w /stage
stage=git_init
echo "S4_STAGE=$stage"
git init --bare --quiet /stage/repository.git >/dev/null 2>&1
stage=baseline_unbundle
echo "S4_STAGE=$stage"
git -C /stage/repository.git bundle unbundle /baseline.bundle >/dev/null 2>&1
test "$(git -C /stage/repository.git cat-file -t "$baseline")" = commit
stage=candidate_unbundle
echo "S4_STAGE=$stage"
git -C /stage/repository.git bundle unbundle /input.bundle >/dev/null 2>&1
test "$(git -C /stage/repository.git cat-file -t "$commit")" = commit
stage=fsck
echo "S4_STAGE=$stage"
git -C /stage/repository.git fsck --strict --no-reflogs "$commit" >/dev/null 2>&1
stage=ancestry
echo "S4_STAGE=$stage"
git -C /stage/repository.git merge-base --is-ancestor "$baseline" "$commit" >/dev/null 2>&1
trap - EXIT
echo "S4_GIT_VERSION=$(git --version)"
echo S4_VERIFIED
