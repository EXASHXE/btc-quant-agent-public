#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
[[ "$(id -u)" == 0 ]]
[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
[[ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ]]
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip -4 route show default)" && -z "$(ip -6 route show default)" ]]
workroot=$PWD
export LC_ALL=C.UTF-8
export PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
export PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1795219200 GIT_NO_LAZY_FETCH=1
unset PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONSTARTUP PYTHONINSPECT
[[ ! -L .qa ]]
mkdir -p .qa
scratch=$(mktemp -d "$PWD/.qa/run.XXXXXX")
log="$scratch/logs"
mkdir "$log" "$scratch"/{home,tmp,config,data,state}
printf 'QA_RUN=%s\n' "$scratch"
export HOME="$scratch/home" TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch"
export XDG_CONFIG_HOME="$scratch/config" XDG_DATA_HOME="$scratch/data" XDG_STATE_HOME="$scratch/state"

{
  date --iso-8601=seconds
  readlink /proc/self/ns/net /proc/self/ns/mnt
  ip -br link
  ip -4 route
  ip -6 route
  python3 --version
  if [[ -f SHA256SUMS ]]; then python3 -B tools/verify_seal.py; fi
  python3 -B tools/preserve.py
} > "$log/preservation-before.log" 2>&1

ruff check --no-cache src tests tools > "$log/lint.log"
ruff format --check --no-cache src tests tools >> "$log/lint.log"
mkdir -p "$scratch/compilecheck"
cp -a src tests tools "$scratch/compilecheck/"
python3 -B -m compileall -q "$scratch/compilecheck"

for build in first second; do
  mkdir -p "$scratch/$build"/{pkg,wheel}
  cp -a pyproject.toml src "$scratch/$build/pkg/"
  python3 -m pip wheel --no-deps --no-index --no-cache-dir --no-build-isolation \
    --wheel-dir "$scratch/$build/wheel" "$scratch/$build/pkg"
done > "$log/build.log" 2>&1

for wheel in "$scratch/first/wheel/"*.whl; do
  name=${wheel##*/}
  cmp "$wheel" "$scratch/second/wheel/$name"
  if [[ "${1:-}" != "--bootstrap" ]]; then
    cmp "$wheel" "evidence/wheel/$name"
  fi
  sha256sum "$wheel"
done > "$log/reproducible-wheels.log"
built_wheel=$(ls "$scratch/first/wheel/"*.whl | head -n 1)

for profile in core full; do
  python3 -B tools/preserve.py --wheels "$profile" --extra-wheel "$built_wheel" > "$scratch/$profile.txt"
  python3 -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
    --target "$scratch/$profile-site" -r "$scratch/$profile.txt"
done > "$log/install.log" 2>&1

base=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "TMPDIR=$TMPDIR"
      "XDG_CACHE_HOME=$XDG_CACHE_HOME" "XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
      "XDG_DATA_HOME=$XDG_DATA_HOME" "XDG_STATE_HOME=$XDG_STATE_HOME"
      "PYTHONDONTWRITEBYTECODE=1" "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" "LC_ALL=C.UTF-8")

env -i "${base[@]}" \
  "PYTHONPATH=$scratch/full-site" \
  "CORE_CLI_SITE=$scratch/core-site" \
  "FULL_CLI_SITE=$scratch/full-site" \
  "OPT_RISK_WORKROOT=$workroot" \
  "OPT_RISK_EVIDENCE_OUT=$log" \
  python3 -P -m pytest -v -ra -p no:cacheprovider \
  --basetemp="$scratch/pytest-tmp" \
  tests/test_optional_risk_config.py \
  tests/test_synthetic_risk_boundaries.py \
  tests/test_local_cli_and_source_integrity.py \
  > "$log/test-suite.log" 2>&1

run_core() { env -i "${base[@]}" "PYTHONPATH=$scratch/core-site" python3 -P "$@"; }
run_full() { env -i "${base[@]}" "PYTHONPATH=$scratch/full-site" python3 -P "$@"; }

deny_exit() {
  local expected_code=$1 expected_str=$2 runner=$3 code=0 out
  shift 3
  out=$("$runner" "$@" 2>&1) || code=$?
  [[ "$code" == "$expected_code" && "$out" == *"$expected_str"* ]]
  printf 'PASS exit=%s %s %s\n' "$code" "$*" "$out"
}

{
  for target in layer2-private layer3-trade binance-live feishu-live; do
    deny_exit 3 BLOCKED_OFFLINE_ONLY run_core -m quant_optional_risk_cli check-live-gate --target "$target"
  done
  deny_exit 2 PRIVATE_CONNECTION_NOT_ACTIVATED run_full -m quant_personal_account_b3 live-connect
  deny_exit 3 LIVE_CAPABILITY_NOT_ACTIVATED run_full -m quant_personal_live_public_b5 preflight --wheel "$scratch/x" --scope "$scratch/x" --activation "$scratch/x"
} > "$log/default-deny.log" 2>&1

python3 -B tools/sanitize_check.py > "$log/sanitize.log" 2>&1
{
  python3 -B tools/preserve.py
  if [[ -f SHA256SUMS ]]; then python3 -B tools/verify_seal.py; fi
} > "$log/preservation-after.log" 2>&1
date --iso-8601=seconds > "$log/completed-at.txt"
printf 'ALL_OPTIONAL_RISK_LOCAL_CLI_QA_PASSED\n'
