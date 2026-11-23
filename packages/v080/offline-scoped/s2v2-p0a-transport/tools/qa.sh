#!/usr/bin/env bash
# Root configures only private namespaces and disposable files under this workroot.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
[[ "$(id -u)" == 0 ]]
[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
[[ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ]]
[[ "$(findmnt -n -o PROPAGATION -T /)" == private ]]
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip -4 route show default)$(ip -6 route show default)" ]]
if awk -F: '$3==64201{found=1} END{exit !found}' /etc/passwd /etc/group; then
  echo FIXTURE_UID_COLLISION
  exit 3
fi
exec 8< "$PWD"
flock -n 8
[[ ! -L .qa ]]
mkdir -p .qa
run=$(mktemp -d "$PWD/.qa/run.XXXXXX")
log="$run/logs"
mkdir "$log" "$run"/{home,tmp,config,cache,data,state,visible,build1,build2}
mkdir "$run/visible"/{inputs,cases,qa}
printf 'QA_RUN=%s\n' "${run##*/}"
export HOME="$run/home" TMPDIR="$run/tmp" XDG_CONFIG_HOME="$run/config" XDG_CACHE_HOME="$run/cache"
export XDG_DATA_HOME="$run/data" XDG_STATE_HOME="$run/state" LC_ALL=C.UTF-8
export GIT_NO_LAZY_FETCH=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_CONFIG_FILE=/dev/null PIP_ROOT_USER_ACTION=ignore
export SOURCE_DATE_EPOCH=1795219200
unset PYTHONPATH PYTHONHOME PYTHONUSERBASE HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
unset http_proxy https_proxy all_proxy no_proxy SSLKEYLOGFILE
parent="$PWD/../lt-v080-sol62-personal-wsl2-s2v2-offline-01"
{
  date --iso-8601=seconds
  echo 'PASS private mount and network namespaces, loopback only, no IPv4/IPv6 default route'
  python3 --version
  if [[ -f SHA256SUMS ]]; then python3 -B tools/preserve.py --seal; fi
  python3 -B tools/preserve.py
  python3 -B tools/inherit.py --check
  echo 'PASS reproducible inherited source and dependency pins'
} > "$log/preservation-before.log"
for variant in build1 build2; do
  cp -a S2V2_RELEASE_BOUND_IMPLEMENTATION "$run/$variant/source"
  python3 -B -m pip wheel --no-index --no-cache-dir --no-deps --no-build-isolation     --wheel-dir "$run/$variant" "$run/$variant/source"
done > "$log/build.log" 2>&1
wheel=("$run/build1/"*.whl)
name=$(basename "${wheel[0]}")
cmp "${wheel[0]}" "$run/build2/$name"
if [[ -f "evidence/wheel/$name" ]]; then cmp "${wheel[0]}" "evidence/wheel/$name"; fi
sha256sum "${wheel[0]}" > "$log/reproducible-wheel.log"
install -m 644 "${wheel[0]}" "$run/visible/inputs/$name"
install -m 644 "$parent"/evidence/wheel/*.whl "$run/visible/inputs/"
install -m 644 tests/qa_entry.py "$run/visible/qa/"
python3 -B tools/preserve.py --wheels canary > "$run/requirements.txt"
python3 -B - "${wheel[0]}" >> "$run/requirements.txt" <<'PY'
import hashlib
import sys
from pathlib import Path
wheel = Path(sys.argv[1]).resolve(strict=True)
print(f"{wheel.as_uri()} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}")
PY
python3 -B -m pip install --no-index --no-cache-dir --no-deps --no-compile --require-hashes   -r "$run/requirements.txt" --target "$run/visible/site" > "$log/install.log" 2>&1
chmod 755 "$run/visible" "$run/visible/inputs" "$run/visible/cases" "$run/visible/qa"
chmod -R go+rX,go-w -- "$run/visible/site"
mount --bind "$run/visible" /mnt
trap 'umount /mnt' EXIT
# This link is private to the test namespace; no host interface is changed.
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip -4 route show default)$(ip -6 route show default)" ]]
export PYTHONPATH="/mnt/site:$PWD/tests:$parent/tests"
rb=0
RB_TRACE="$log/loopback-canary.json" python3 -P -s -B -m pytest -v -ra -p no:cacheprovider   --basetemp="$run/pytest-rb" tests > "$log/test-transport.log" 2>&1 || rb=$?
parent_rc=0
V2_TRACE="$log/parent-v2-canary.json" python3 -P -s -B -m pytest -v -ra -p no:cacheprovider   --basetemp="$run/pytest-parent" "$parent/tests" > "$log/test-parent-v2.log" 2>&1 || parent_rc=$?
{
  for entry in manual-once qa-console live-once preflight revoke resume s3 s4; do
    code=0
    result=$(QUANT_S2RB_QA=1 QUANT_S2V2_LIVE=1 python3 -P -s -B -m quant_s2rb "$entry" 2>&1) || code=$?
    [[ "$code" == 3 && "$result" == REAL_S2_CANARY_NOT_AUTHORIZED ]]
    printf 'PASS candidate %s exit=3 REAL_S2_CANARY_NOT_AUTHORIZED\n' "$entry"
  done
  for entry in preflight live-once revoke; do
    code=0
    result=$(python3 -P -s -B -m quant_personal_live_public_b5 "$entry" 2>&1) || code=$?
    [[ "$code" == 3 && "$result" == *LIVE_CAPABILITY_NOT_ACTIVATED* ]]
    printf 'PASS post3 %s exit=3 LIVE_CAPABILITY_NOT_ACTIVATED\n' "$entry"
  done
} > "$log/default-deny.log" 2>&1
{
  python3 -B tools/preserve.py
  if [[ -f SHA256SUMS ]]; then python3 -B tools/preserve.py --seal; fi
} > "$log/preservation-after.log"
date --iso-8601=seconds > "$log/completed-at.txt"
if (( rb || parent_rc )); then
  printf 'OFFLINE_QA_FAILED transport_exit=%d parent_exit=%d\n' "$rb" "$parent_rc"
  exit 1
fi
echo ALL_S2V2_RELEASE_BOUND_OFFLINE_QA_PASSED
