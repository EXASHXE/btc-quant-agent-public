#!/usr/bin/env bash
# Invoke using unshare -n -- bash tools/qa.sh from the B4 root.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LC_ALL=C PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INDEX=1
unset PYTHONPATH
export SOURCE_DATE_EPOCH=1795132800
if [[ "$(readlink /proc/self/ns/net)" == "$(readlink /proc/1/ns/net)" ]]; then
  echo "QA requires a dedicated network namespace" >&2
  exit 2
fi
ip link set lo up
if [[ "$(ip -o link show | wc -l)" != 1 || -n "$(ip route show default)" || -n "$(ip -6 route show default)" ]]; then
  echo "QA requires loopback only" >&2
  exit 2
fi
mkdir -p .scratch evidence/wheel
run=$(mktemp -d "$PWD/.scratch/qa.XXXXXX")
export TMPDIR="$run"
trap 'echo "QA scratch: $run"' EXIT
set -x
{
  readlink /proc/self/ns/net
  ip -brief address
  ip route show table main
  ip -6 route show table main
  python3 --version
  openssl version
  python3 tools/preserve.py
} > evidence/preservation.log 2>&1
b1=(../*b1-01/evidence/wheel/*.whl)
b2=(../*b2-01/evidence/wheel/*.whl)
b3=(../*b3-01/evidence/wheel/*.whl)
r1=(../*layer1-public-01/evidence/wheel/*.whl)
printf '%s  %s\n' \
  19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f "${b1[0]}" \
  29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64 "${b2[0]}" \
  ed11906d6b23b74ef90984a44a7c6cadfff68543bee7f9715226af366f769c5f "${b3[0]}" \
  7f7877fe4b0efc5c1456ea02d91a91f78cbd99f2ee3ad8dd6853e87ea86f6fcc "${r1[0]}" \
  | sha256sum -c - > evidence/dependency-hashes.log
mkdir "$run/build-input"
cp pyproject.toml "$run/build-input/"
cp -R src/quant_personal_public_bridge_b4 "$run/build-input/src-tmp"
mkdir "$run/build-input/src"
mv "$run/build-input/src-tmp" "$run/build-input/src/quant_personal_public_bridge_b4"
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run" "$run/build-input" > evidence/build.log 2>&1
# Rebuild from the same sources and compare the wheel bytes.
mkdir "$run/rebuild"
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run/rebuild" "$run/build-input" >> evidence/build.log 2>&1
wheel="$run/quant_personal_public_bridge_b4-0.8.0b4-py3-none-any.whl"
cmp "$wheel" "$run/rebuild/$(basename "$wheel")" >> evidence/build.log
cp "$wheel" evidence/wheel/
(cd evidence/wheel && sha256sum ./*.whl) >> evidence/build.log
python3 -m venv "$run/venv"
py="$run/venv/bin/python"
cli="$run/venv/bin/quant-public-b4"
{
  "$py" -m pip install --no-index --no-cache-dir "$wheel" "${b1[0]}" "${b2[0]}"
  "$py" -m pip check
  "$py" -m pip list
} > evidence/install-clean.log 2>&1
"$py" -m unittest discover -s tests -v > evidence/b4-unittest.log 2>&1
"$cli" inspect > evidence/inspect.json
"$cli" readiness "$run/demo" > evidence/readiness.json
"$cli" dry-run "$run/chase" --chase > "$run/chase.json"
"$py" - "$run/chase.json" <<'PY' > evidence/no-chase.json
import json, sys
data = json.load(open(sys.argv[1]))
card = data["cards"][2]
assert card["market_status"] != "EXECUTABLE" and "MISSED_NO_CHASE" in card["reasons"]
print(json.dumps({key: card[key] for key in ("market_status", "reasons", "warnings", "reprice")}))
PY
mkdir -p evidence/replay-input
cp "$run/demo/trend_pullback-long/"{source,journal}.sqlite evidence/replay-input/
cat /dev/null > evidence/raw-to-card-replay.jsonl
for dir in "$run/demo/"*; do
  "$py" tools/rebuild_cards.py "$dir" "$run/replay-$(basename "$dir").sqlite" >> evidence/raw-to-card-replay.jsonl
done
"$cli" card evidence/replay-input/journal.sqlite > evidence/example-card.json
"$cli" replay evidence/replay-input/journal.sqlite evidence/replay-input/source.sqlite > evidence/cli-replay.json
printf '%s\n' '{"status":"ACTIVE","live_requests_enabled":true,"controller_activation":"fake"}' > "$run/copied-scope.json"
check_live_gate() {
  local py=$1 cli=$2
  for entry in console module; do
    for round in 1 2; do
      if [[ "$entry" == console ]]; then invoke=("$cli"); else invoke=("$py" -m quant_personal_public_bridge_b4); fi
      code=0
      result=$(env QUANT_B4_LIVE=1 B4_ACTIVATION="$run/copied-scope.json" BINANCE_API_KEY=fake BINANCE_API_SECRET=fake \
        HTTPS_PROXY=http://127.0.0.1:7 "${invoke[@]}" live-scan --config "$run/copied-scope.json" 2>&1) || code=$?
      [[ "$code" == 3 && "$result" == LIVE_CAPABILITY_NOT_ACTIVATED ]]
      printf '%s run %s: exit %s, %s\n' "$entry" "$round" "$code" "$result"
    done
  done
}

check_live_gate "$py" "$cli" > evidence/live-gate-clean.log
{
  crypto=(../../../quant-0.7.0/lt-program-j-realtime-advisory-01/release/wheelhouse/cryptography-45.0.7*.whl)
  printf '%s  %s\n' b6a0e535baec27b528cb07a119f321ac024592388c5681a5ced167ae98e9fff3 "${crypto[0]}" | sha256sum -c -
  python3 -m venv --system-site-packages "$run/mixed-venv"
  mixpy="$run/mixed-venv/bin/python"
  "$mixpy" -m pip install --no-index --no-cache-dir "$wheel" "${b1[0]}" "${b2[0]}" "${b3[0]}" "${r1[0]}" "${crypto[0]}"
  "$mixpy" -m pip check
  "$mixpy" -m pip list --local
  "$mixpy" - "$run" <<'PY'
from importlib import metadata
from pathlib import Path
import sys
from quant_personal_public_bridge_b4.demo import run
run(Path(sys.argv[1]) / "mixed", "early_continuation-short")
assert metadata.version("quant-personal-account-b3") == "0.8.0b3"
assert metadata.version("quant-advisory-platform") == "0.8.0"
assert not any(x.partition(".")[0] in {"quant_personal_account_b3", "btc_quant_agent", "program_c"}
               for x in sys.modules)
print("Mixed offline path passed with no B3 or legacy imports")
PY
} > evidence/install-mixed.log 2>&1
check_live_gate "$mixpy" "$run/mixed-venv/bin/quant-public-b4" > evidence/live-gate-mixed.log
# Run inherited suites against immutable tests and pinned installed B1/B2. Their test
# dependencies come from the mixed venv. These runs do not exercise legacy R1 or B3.

b1root=$(dirname "$(dirname "$(dirname "${b1[0]}")")")
b2root=$(dirname "$(dirname "$(dirname "${b2[0]}")")")
b1db=$(find "$b1root/evidence" -name '*.sqlite' -type f | sort | head -1)
[[ -n "$b1db" ]]
run_regression() {
  "$mixpy" -m pytest -q -p no:cacheprovider "$1"
}
run_regression "$b1root/tests" > evidence/b1-regression.log 2>&1
B2_ACCEPTED_B1_DB="$(realpath "$b1db")" run_regression "$b2root/tests" > evidence/b2-regression.log 2>&1
python3 tools/preserve.py >> evidence/preservation.log
