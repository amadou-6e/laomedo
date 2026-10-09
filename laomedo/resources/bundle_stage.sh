#!/bin/sh
set -eu

baseline="$1"
commit="$2"
stage=mount_access
trap 'echo "STAGE_FAILED=$stage"' EXIT
mkdir -p /stage/home
export HOME=/stage/home
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TERMINAL_PROMPT=0
export GIT_NO_REPLACE_OBJECTS=1

test -r /baseline.bundle
test -r /input.bundle
test -w /stage
stage=git_init
git init --bare --quiet /stage/repository.git >/dev/null 2>&1
stage=baseline_import
git -C /stage/repository.git bundle unbundle /baseline.bundle >/dev/null 2>&1
test "$(git -C /stage/repository.git cat-file -t "$baseline")" = commit
stage=candidate_import
git -C /stage/repository.git bundle unbundle /input.bundle >/dev/null 2>&1
test "$(git -C /stage/repository.git cat-file -t "$commit")" = commit
stage=integrity
git -C /stage/repository.git fsck --strict --no-reflogs "$commit" >/dev/null 2>&1
stage=ancestry
git -C /stage/repository.git merge-base --is-ancestor "$baseline" "$commit" >/dev/null 2>&1
stage=export
git -C /stage/repository.git update-ref refs/heads/validated "$commit" >/dev/null 2>&1
git -C /stage/repository.git bundle create /stage/verified.bundle refs/heads/validated >/dev/null 2>&1
trap - EXIT
echo STAGE_VERIFIED
