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
unset PYTHONPATH
[[ ! -L .qa ]]
mkdir -p .qa
scratch=$(mktemp -d "$PWD/.qa/run.XXXXXX")
log="$scratch/logs"
mkdir "$log" "$scratch"/{home,tmp,config,data,state,uid-mount,workspaces}
printf 'QA_RUN=%s\n' "$scratch"
export HOME="$scratch/home" TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch"
export XDG_CONFIG_HOME="$scratch/config" XDG_DATA_HOME="$scratch/data" XDG_STATE_HOME="$scratch/state"
chmod 0711 "$scratch/uid-mount"
mount --bind "$scratch/uid-mount" /mnt
trap 'umount /mnt' EXIT
runtime=/usr/local/lib/hermes-agent
py="$runtime/venv/bin/python"
h3=$(realpath ../lt-v080-sol62-h3-hermes-quant-field-trial-01)
h3b=$(realpath ../lt-v080-sol62-h3b-live-gate-a-readiness-01)
h2a=$(realpath ../lt-v080-sol62-h2a-b5-phaseb-activation-01)
h2b=$(realpath ../lt-v080-neon-h2b-hermes-feishu-readiness-01)
h1=$(realpath ../lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01)
a1=$(realpath ../lt-v080-sol62-a1-b5-local-derivative-offline-01)
b1=$(realpath ../lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01)
b2=$(realpath ../lt-v080-sol62-personal-mvp-market-decision-b2-01)
b4=$(realpath ../lt-v080-personal-mvp-public-source-bridge-b4-01)
b5=$(realpath ../lt-v080-personal-mvp-live-public-b5-01)
oracle=../../../quant-docs-engineering/docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json

{
  date --iso-8601=seconds
  readlink /proc/self/ns/net /proc/self/ns/mnt
  ip -br link
  ip -4 route
  ip -6 route
  "$py" --version
  if [[ -f SHA256SUMS ]]; then python3 -B tools/verify_seal.py; fi
  python3 -B tools/preserve.py
  "$py" -I -B "$h3/tools/hermes_lock.py" > "$scratch/hermes-lock.json"
  cmp "$h3/HERMES_RUNTIME_LOCK.json" "$scratch/hermes-lock.json"
  if [[ "${1:-}" != "--bootstrap" ]]; then
    python3 -B tools/runtime_snapshot.py "$scratch/hermes-code"
    cp tools/runtime_sitecustomize.py "$scratch/hermes-code/sitecustomize.py"
  fi
} > "$log/preservation-before.log" 2>&1

for build in first second; do
  mkdir -p "$scratch/$build"/{h4,b5,wheel}
  cp -a pyproject.toml src "$scratch/$build/h4/"
  cp -a b5/pyproject.toml b5/src "$scratch/$build/b5/"
  for pkg in h4 b5; do
    python3 -m pip wheel --no-deps --no-index --no-cache-dir --no-build-isolation \
      --wheel-dir "$scratch/$build/wheel" "$scratch/$build/$pkg"
  done
done > "$log/build.log" 2>&1
for wheel in "$scratch/first/wheel/"*.whl; do
  name=${wheel##*/}
  cmp "$wheel" "$scratch/second/wheel/$name"
  if [[ "${1:-}" != "--bootstrap" ]]; then cmp "$wheel" "evidence/wheel/$name"; fi
  sha256sum "$wheel"
done > "$log/reproducible-wheels.log"
h4wheel=("$scratch/first/wheel/"quant_h4_readiness*.whl)
canarywheel=("$scratch/first/wheel/"quant_personal_live_public_b5*.whl)
if [[ "${1:-}" == "--bootstrap" ]]; then
  printf 'BOOTSTRAP_WHEELS=%s\n' "$scratch/first/wheel"
  exit 0
fi

python3 -B tools/h4_dependency.py "${h4wheel[0]}" > "$log/lock.log"
"$runtime/venv/bin/ruff" check --no-cache src tools tests > "$log/lint.log"
"$runtime/venv/bin/ruff" format --check --no-cache src tools tests >> "$log/lint.log"

for profile in hermes-clean hermes-mixed canary-clean canary-mixed; do
  wheels=("${h4wheel[0]}")
  if [[ "$profile" == canary-* ]]; then wheels+=("${canarywheel[0]}"); fi
  python3 -B tools/preserve.py --profile "$profile" "${wheels[@]}" > "$scratch/$profile.txt"
  python3 -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
    --target "$scratch/$profile" -r "$scratch/$profile.txt"
done > "$log/install.log" 2>&1

base=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "TMPDIR=$TMPDIR"
      "XDG_CACHE_HOME=$XDG_CACHE_HOME" "XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
      "XDG_DATA_HOME=$XDG_DATA_HOME" "XDG_STATE_HOME=$XDG_STATE_HOME"
      "PYTHONDONTWRITEBYTECODE=1" "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" "LC_ALL=C.UTF-8")
for profile in canary-clean canary-mixed; do
  trace=()
  if [[ "$profile" == canary-clean ]]; then trace=("A1_TRACE_OUTPUT=$log/s2-mock-trace.json"); fi
  env -i "${base[@]}" "${trace[@]}" "PYTHONPATH=$scratch/$profile:$a1/tests" \
    "A1_WHEEL=${canarywheel[0]}" "$py" -P tests/test_s2.py > "$log/test-$profile.log" 2>&1
done

h3replay="$scratch/workspaces/.lt-v080-h3-h4-offline-review"
state="$h3replay/qa-dress"
mkdir -p "$h3replay"/{home,tmp,cache,config,data,state}
for profile in hermes-clean hermes-mixed; do
  common=("PYTHONPATH=$scratch/$profile:$scratch/hermes-code:$h3b/tools" "HERMES_HOME=$state/hermes"
          "H3_QA_RUN=$state" "H3B_UID_MOUNT_SOURCE=$scratch/uid-mount"
          "H3B_WITNESS_DIR=$log" "H4_WHEEL=${h4wheel[0]}" "H4_EVIDENCE=$log")
  if [[ "$profile" == hermes-clean ]]; then
    (
      cd "$h3replay"
      for mode in demo resume replay; do
        entry=(-m quant_hermes_h3)
        if [[ "$mode" == demo ]]; then entry=("$workroot/tools/h3_warm_rehearsal.py"); fi
        env -i "${base[@]:0:8}" "LC_ALL=C.UTF-8" "PYTHONPATH=$scratch/$profile:$scratch/hermes-code" \
          "HERMES_HOME=$state/hermes" "HOME=$h3replay/home" "TMPDIR=$h3replay/tmp" \
          "XDG_CACHE_HOME=$h3replay/cache" "XDG_CONFIG_HOME=$h3replay/config" \
          "XDG_DATA_HOME=$h3replay/data" "XDG_STATE_HOME=$h3replay/state" \
          "$py" -P "${entry[@]}" "$mode" --run-id qa-dress
      done
    ) > "$log/h3-rehearsal.log" 2>&1
  fi
  env -i "${base[@]}" "${common[@]}" "$py" -P -m pytest -v -ra -p no:cacheprovider \
    --basetemp="/mnt/$profile-tests" tests/test_h4.py > "$log/test-$profile.log" 2>&1
done
if [[ "${1:-}" == "--focus" ]]; then exit 0; fi

run() { env -i "${base[@]}" "${common[@]}" "$py" -P "$@"; }
pytest_run() { run -m pytest -v -ra -p no:cacheprovider "$@"; }
run -m unittest discover -s "$h2a/tests" -p test_h2a.py -v > "$log/test-h2a.log" 2>&1
run -m unittest discover -s "$b4/tests" -v > "$log/test-b4.log" 2>&1
qa_b5wheel=("$b5/evidence/wheel/"*.whl)
python3 -B tools/preserve.py --profile canary-clean "${qa_b5wheel[0]}" > "$scratch/original-b5.txt"
python3 -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
  --target "$scratch/original-b5" -r "$scratch/original-b5.txt" >> "$log/install.log" 2>&1
env -i "${base[@]}" "PYTHONPATH=$scratch/original-b5" \
  "$py" -P -m unittest discover -s "$b5/tests" -v > "$log/test-b5.log" 2>&1
pytest_run --basetemp="$scratch/b1-tests" "$b1/tests" > "$log/test-b1.log" 2>&1
env -i "${base[@]}" "${common[@]}" "B2_ACCEPTED_B1_DB=$b1/evidence/demo/fixture.sqlite" \
  "$py" -P -m pytest -v -ra -p no:cacheprovider --basetemp="$scratch/b2-tests" "$b2/tests" \
  > "$log/test-b2.log" 2>&1
pytest_run --basetemp="$scratch/h3-tests" "$h3/tests" > "$log/test-h3.log" 2>&1
pytest_run --basetemp=/mnt/h2b-tests "$h2b/tests/test_d_outbox_and_single_sender.py" \
  "$h2b/tests/test_c_inbound_identity_and_session.py" > "$log/test-h2b.log" 2>&1
pytest_run --basetemp="$scratch/uid-tests" "$h3b/tests/test_uid_boundary.py" > "$log/test-uds.log" 2>&1
node "$h1/tools/compare_goldens.ts" --export-dir "$h1/reference-export" --oracle "$oracle" \
  > "$log/node-goldens.log"
run -m quant_hermes_feishu_h2b verify-goldens --h1-root "$h1" --oracle "$oracle" \
  > "$log/python-goldens.log"
run -m quant_h4 market-plan > "$log/market-plan.json"

deny() {
  local result code=0 expected=$1
  shift
  result=$(run "$@" 2>&1) || code=$?
  [[ "$code" == 3 && "$result" == *"$expected"* ]]
  printf 'PASS exit=%s %s %s\n' "$code" "$*" "$result"
}
{
  deny BLOCKED_LIVE_GATE -m quant_h4 status
  deny BLOCKED_LIVE_GATE -m quant_hermes_h3 gate-status
  for verb in preflight live-once revoke; do
    deny LIVE_CAPABILITY_NOT_ACTIVATED -m quant_personal_live_public_b5 "$verb"
  done
  for cap in feishu-outbound feishu-inbound feishu-recurring; do
    deny LIVE_FEISHU_GATE_NOT_AUTHORIZED -m quant_hermes_feishu_h2b check-live-gate --target "$cap"
  done
  deny LIVE_MODEL_GATE_NOT_AUTHORIZED -m quant_hermes_feishu_h2b check-live-gate --target model-oauth
  run -m quant_hermes_h3 refresh-status
} > "$log/default-deny.log" 2>&1
{
  python3 -B tools/preserve.py
  if [[ -f SHA256SUMS ]]; then python3 -B tools/verify_seal.py; fi
} > "$log/preservation-after.log" 2>&1
date --iso-8601=seconds > "$log/completed-at.txt"
printf 'ALL_H4_OFFLINE_QA_PASSED\n'
