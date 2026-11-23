#!/usr/bin/env bash
# Run from an isolated H3 review copy with unshare -n -- bash tools/qa.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LC_ALL=C.UTF-8 SOURCE_DATE_EPOCH=1795219200
[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip route show default)" && -z "$(ip -6 route show default)" ]]
mkdir qa-isolated
scratch="$PWD/qa-isolated"
run_id=qa-field
state="$PWD/$run_id"
runtime=/usr/local/lib/hermes-agent
py="$runtime/venv/bin/python"
mkdir -p evidence/wheel "$scratch"/{home,tmp,config,data,state,src-tree/src,build-a,build-b}
export PYTHONDONTWRITEBYTECODE=1
export HOME="$scratch/home" TMPDIR="$scratch/tmp"
export XDG_CACHE_HOME="$scratch" XDG_CONFIG_HOME="$scratch/config"
export XDG_DATA_HOME="$scratch/data" XDG_STATE_HOME="$scratch/state"
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_CONFIG_FILE=/dev/null PIP_ROOT_USER_ACTION=ignore
unset PYTHONPATH
set -x

{
  readlink /proc/self/ns/net
  ip -br link
  ip -4 route
  ip -6 route
  python3 --version
  node --version
  "$py" --version
  python3 -B tools/preserve.py
  "$py" -I -B tools/hermes_lock.py > "$scratch/hermes-lock.json"
  cmp HERMES_RUNTIME_LOCK.json "$scratch/hermes-lock.json"
  sha256sum HERMES_RUNTIME_LOCK.json
} > evidence/preservation-pre.log 2>&1

ruff check --no-cache src tests tools > evidence/lint.log 2>&1
ruff format --check --no-cache src tests tools >> evidence/lint.log 2>&1

cp pyproject.toml "$scratch/src-tree/"
cp -R src/quant_hermes_h3 "$scratch/src-tree/src/"
for build in build-a build-b; do
  python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation \
    --wheel-dir "$scratch/$build" "$scratch/src-tree"
done > evidence/build.log 2>&1
wheel_name=quant_hermes_h3-0.8.0a3-py3-none-any.whl
wheel="$scratch/build-a/$wheel_name"
cmp "$wheel" "$scratch/build-b/$wheel_name"
cp "$wheel" "evidence/wheel/$wheel_name"
sha256sum "evidence/wheel/$wheel_name" >> evidence/build.log
for profile in clean mixed; do
  extra=()
  [[ "$profile" != mixed ]] || extra+=(--mixed)
  python3 -B tools/preserve.py --requirements "${extra[@]}" > "$scratch/$profile.txt"
  printf '%s --hash=sha256:%s\n' "$wheel" "$(sha256sum "$wheel" | cut -d' ' -f1)" >> "$scratch/$profile.txt"
  python3 -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
    -r "$scratch/$profile.txt" --target "$scratch/$profile" > "evidence/install-$profile.log" 2>&1
done

h1=../lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01
oracle=../../../quant-docs-engineering/docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json
node "$h1/tools/compare_goldens.ts" --export-dir "$h1/reference-export" --oracle "$oracle" > evidence/goldens-node.log
env PYTHONPATH="$scratch/clean" python3 -P -B -m quant_hermes_feishu_h2b verify-goldens \
  --h1-root "$h1" --oracle "$oracle" > evidence/goldens-python.log

clean_env=(
  "HOME=$HOME" "TMPDIR=$TMPDIR" "XDG_CACHE_HOME=$XDG_CACHE_HOME" "XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
  "XDG_DATA_HOME=$XDG_DATA_HOME" "XDG_STATE_HOME=$XDG_STATE_HOME" "HERMES_HOME=$state/hermes"
  "PATH=/usr/local/bin:/usr/bin:/bin" "LC_ALL=C.UTF-8" "PYTHONDONTWRITEBYTECODE=1"
)
for phase in demo resume replay; do
  env -i "${clean_env[@]}" "PYTHONPATH=$scratch/clean:$runtime" \
    "$py" -P -m quant_hermes_h3 "$phase" --run-id "$run_id"
done > evidence/runtime.log 2>&1

for profile in clean mixed; do
  env -i "${clean_env[@]}" "PYTHONPATH=$scratch/$profile:$runtime" \
    "H3_QA_RUN=$state" "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" \
    "$py" -P -m pytest -ra -v -p no:cacheprovider --basetemp="$scratch/test-$profile" tests/ \
    > "evidence/test-$profile.log" 2>&1
  rc=0
  env -i "${clean_env[@]}" "PYTHONPATH=$scratch/$profile:$runtime" \
    "$py" -P -m quant_hermes_h3 gate-status > "evidence/gate-$profile.log" 2>&1 || rc=$?
  [[ "$rc" == 3 ]]
  grep -q BLOCKED_LIVE_GATE "evidence/gate-$profile.log"
  env -i "${clean_env[@]}" "PYTHONPATH=$scratch/$profile:$runtime" \
    "$py" -P -m quant_hermes_h3 refresh-status >> "evidence/gate-$profile.log"
done

for report in actionability source-trace transcripts recovery raw-replay resume-measurements resume-latency pi-feedback; do
  cp "$state/$report.json" "evidence/$report.json"
done
python3 -B tools/preserve.py > evidence/preservation-post.log
echo ALL_H3_OFFLINE_QA_PASSED
