#!/usr/bin/env bash
# Run from H2-A work root as unshare -n -- bash tools/qa.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LC_ALL=C PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INDEX=1
unset PYTHONPATH
export SOURCE_DATE_EPOCH=1795132800
[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip route show default)" && -z "$(ip -6 route show default)" ]]
mkdir -p .scratch evidence/wheel evidence/dependencies evidence/replay-input
run=$(mktemp -d "$PWD/.scratch/qa.XXXXXX")
export TMPDIR="$run"
trap 'echo "H2-A QA scratch: $run"' EXIT
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
b4=(../*b4-01/evidence/wheel/*.whl)
b5=(../*b5-01/evidence/wheel/*.whl)
b3=(../*b3-01/evidence/wheel/*.whl)
r1=(../*layer1-public-01/evidence/wheel/*.whl)
crypto=(../../../quant-0.7.0/lt-program-j-realtime-advisory-01/release/wheelhouse/cryptography-45.0.7*.whl)
printf '%s  %s\n' \
  19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f "${b1[0]}" \
  29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64 "${b2[0]}" \
  c30332d0028b14f2c7ee89ef941be3e9d51f1ff500231bb9cbcaae95a63c7710 "${b4[0]}" \
  eb6076a3a98f3fa82512a2b748d8cbf44333ca9f56dec265b163c6f6857ddab3 "${b5[0]}" \
  ed11906d6b23b74ef90984a44a7c6cadfff68543bee7f9715226af366f769c5f "${b3[0]}" \
  7f7877fe4b0efc5c1456ea02d91a91f78cbd99f2ee3ad8dd6853e87ea86f6fcc "${r1[0]}" \
  b6a0e535baec27b528cb07a119f321ac024592388c5681a5ced167ae98e9fff3 "${crypto[0]}" \
  | sha256sum -c - > evidence/dependency-hashes.log
cp "${b1[0]}" "${b2[0]}" "${b4[0]}" evidence/dependencies/
mkdir -p "$run/src-tree/src" "$run/rebuild"
cp pyproject.toml "$run/src-tree/"
cp -R src/quant_personal_live_public_b5 "$run/src-tree/src/"
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run" "$run/src-tree" > evidence/build.log 2>&1
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run/rebuild" "$run/src-tree" >> evidence/build.log 2>&1
wheel="$run/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl"
cmp "$wheel" "$run/rebuild/$(basename "$wheel")"
cp "$wheel" evidence/wheel/
(cd evidence/wheel && sha256sum ./*.whl) >> evidence/build.log
pins=(evidence/dependencies/*.whl)
python3 -m venv "$run/clean"
py="$run/clean/bin/python"
cli="$run/clean/bin/quant-public-b5"
{
  "$py" -m pip install --no-index --no-cache-dir "$wheel" "${pins[@]}"
  "$py" -m pip check
  "$py" -m pip list
  "$py" - "$wheel" <<'PY'
import hashlib
import sys
from pathlib import Path
from quant_personal_live_public_b5.release import verify_release
from quant_personal_public_b1.policy import SourceBlocked
wheel=Path(sys.argv[1])
verify_release(wheel,hashlib.sha256(wheel.read_bytes()).hexdigest())
try:
    verify_release(wheel,"0"*64)
except SourceBlocked as error:
    assert error.code=="RELEASE_WHEEL_DIGEST_MISMATCH"
else:
    raise AssertionError("Bad wheel fingerprint was accepted")
print("Exact H2-A installed release and upstream module bytes verified")
PY
} > evidence/install-clean.log 2>&1
"$cli" inspect > evidence/inspect.json
"$cli" dry-run > evidence/prospective-request-plan.json
"$cli" readiness "$run/demo" > evidence/offline-readiness.json
"$py" tools/staged_replay.py "$run/staged" > evidence/staged-replay.jsonl
mkdir -p evidence/staged-input
cp "$run/staged/conditional-market/"{source,journal}.sqlite evidence/staged-input/
"$cli" dry-run --fixture-directory "$run/chase" --chase > "$run/chase.json"
"$py" - "$run/chase.json" <<'PY' > evidence/no-chase.json
import json,sys
card=json.load(open(sys.argv[1]))["cards"][2]
assert card["market_status"]=="INVALID" and "MISSED_NO_CHASE" in card["reasons"]
print(json.dumps({k:card[k] for k in ("market_status","reasons","reprice","evidence")}))
PY
cp "$run/demo/trend_pullback-long/"{source,journal}.sqlite evidence/replay-input/
"$cli" card --journal evidence/replay-input/journal.sqlite > evidence/card-example.json
"$cli" replay --journal evidence/replay-input/journal.sqlite --source evidence/replay-input/source.sqlite > evidence/replay-probe.json
: > evidence/raw-to-card.jsonl
for path in "$run/demo/"*; do
  "$py" tools/rebuild_cards.py "$path" "$run/replay-$(basename "$path").sqlite" >> evidence/raw-to-card.jsonl
done
printf '%s\n' '{"status":"ACTIVE","live_permitted":true,"signature":"forged","claims":{"controller":"0-C"}}' > "$run/forged.json"
check_gate() {
  local py=$1 cli=$2
  for mode in console module; do
    for cmd in preflight live-once revoke; do
      if [[ "$mode" == console ]]; then invoke=("$cli"); else invoke=("$py" -m quant_personal_live_public_b5); fi
      rc=0
      output=$(env B5_ENABLED=1 BINANCE_API_KEY=fake BINANCE_API_SECRET=fake HTTPS_PROXY=http://127.0.0.1:7 \
        SSL_CERT_FILE="$run/forged.json" "${invoke[@]}" "$cmd" --scope "$run/forged.json" \
        --activation "$run/forged.json" --wheel "$wheel" 2>&1) || rc=$?
      [[ "$rc" == 3 && "$output" == LIVE_CAPABILITY_NOT_ACTIVATED ]]
      printf '%s %s: exit %s %s\n' "$mode" "$cmd" "$rc" "$output"
    done
  done
}
check_gate "$py" "$cli" > evidence/gate-clean.log
{
  python3 -m venv --system-site-packages "$run/mixed"
  mixpy="$run/mixed/bin/python"
  "$mixpy" -m pip install --no-index --no-cache-dir "$wheel" "${pins[@]}" "${b3[0]}" "${r1[0]}" "${crypto[0]}"
  "$mixpy" -m pip check
  "$mixpy" -m pip list --local
  "$mixpy" - "$run" <<'PY'
import sys
from pathlib import Path
from importlib.metadata import version
from quant_personal_live_public_b5.offline import run_case
run_case(Path(sys.argv[1])/"mixed-case","early_continuation-short")
assert version("quant-personal-account-b3")=="0.8.0b3"
assert version("quant-advisory-platform")=="0.8.0"
assert all(name.partition(".")[0] not in {"quant_personal_account_b3","btc_quant_agent","program_c"}
           for name in sys.modules)
print("Mixed B5 market path passed without B3 or legacy runtime imports")
PY
} > evidence/install-mixed.log 2>&1
check_gate "$mixpy" "$run/mixed/bin/quant-public-b5" > evidence/gate-mixed.log
"$mixpy" -m unittest discover -s tests -v > evidence/h2a-unittest.log 2>&1
b1root=$(dirname "$(dirname "$(dirname "${b1[0]}")")")
b2root=$(dirname "$(dirname "$(dirname "${b2[0]}")")")
b4root=$(dirname "$(dirname "$(dirname "${b4[0]}")")")
b5root=$(dirname "$(dirname "$(dirname "${b5[0]}")")")
"$mixpy" -m pytest -q -p no:cacheprovider "$b1root/tests" > evidence/b1-regression.log 2>&1
B2_ACCEPTED_B1_DB="$(realpath "$b1root/evidence/demo/fixture.sqlite")" \
  "$mixpy" -m pytest -q -p no:cacheprovider "$b2root/tests" > evidence/b2-regression.log 2>&1
"$mixpy" -m unittest discover -s "$b4root/tests" -v > evidence/b4-regression.log 2>&1
"$mixpy" -m unittest discover -s "$b5root/tests" -v > evidence/b5-candidate-compatibility.log 2>&1
{
  python3 -m venv --system-site-packages "$run/b5-sealed"
  oldpy="$run/b5-sealed/bin/python"
  "$oldpy" -m pip install --no-index --no-cache-dir "${b5[0]}" "${pins[@]}" "${crypto[0]}"
  "$oldpy" -m pip check
} > evidence/install-sealed-b5.log 2>&1
"$oldpy" -m unittest discover -s "$b5root/tests" -v > evidence/b5-sealed-regression.log 2>&1
for cmd in preflight live-once; do
  rc=0
  reply=$(env B5_ENABLED=1 "$run/b5-sealed/bin/quant-public-b5" "$cmd" --activation "$run/forged.json" 2>&1) || rc=$?
  [[ "$rc" == 3 && "$reply" == LIVE_CAPABILITY_NOT_ACTIVATED ]]
  printf '%s: exit %s %s\n' "$cmd" "$rc" "$reply"
done > evidence/b5-sealed-gate.log
python3 tools/preserve.py >> evidence/preservation.log
