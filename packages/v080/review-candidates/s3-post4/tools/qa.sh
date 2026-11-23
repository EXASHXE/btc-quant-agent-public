#!/usr/bin/env bash
# Run from workroot as:
#   unshare -n -m --propagation private -- bash tools/qa.sh
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077

# 1. Hard isolation verification: private netns, private mntns, lo-only, zero default routes.
[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
[[ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ]]
[[ "$(findmnt -n -o PROPAGATION -T /)" == "private" ]]
ip link set lo up
[[ "$(ip -o link show | wc -l)" == "1" ]]
[[ -z "$(ip -4 route show default)" && -z "$(ip -6 route show default)" ]]

exec 9< "$PWD"
flock -n 9

[[ ! -L .qa ]]
mkdir -p .qa evidence/wheel
run=$(mktemp -d "$PWD/.qa/run.XXXXXX")
mkdir -p "$run"/{home,tmp,config,cache,data,state,build-1/src,build-2/src,wheels-1,wheels-2}
printf 'QA_RUN=%s\n' "$run"

export HOME="$run/home" TMPDIR="$run/tmp"
export XDG_CONFIG_HOME="$run/config" XDG_CACHE_HOME="$run/cache"
export XDG_DATA_HOME="$run/data" XDG_STATE_HOME="$run/state"
export LC_ALL=C.UTF-8 GIT_NO_LAZY_FETCH=1 PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore PIP_CONFIG_FILE=/dev/null
export SOURCE_DATE_EPOCH=1795392000
unset PYTHONPATH HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

# 2. Preservation check BEFORE any build or test.
{
  date --iso-8601=seconds
  echo "netns_self=$(readlink /proc/self/ns/net) netns_init=$(readlink /proc/1/ns/net)"
  echo "mntns_self=$(readlink /proc/self/ns/mnt) mntns_init=$(readlink /proc/1/ns/mnt)"
  echo "mount_propagation=$(findmnt -n -o PROPAGATION -T /)"
  ip -brief link
  ip -brief address
  printf 'IPv4 default routes: [%s]\n' "$(ip -4 route show default)"
  printf 'IPv6 default routes: [%s]\n' "$(ip -6 route show default)"
  python3 --version
  python3 -B -m pytest --version
  openssl version
  python3 -B tools/preserve.py
} > evidence/preservation-before.log 2>&1

# 3. Two independent reproducible wheel builds from clean source copies.
{
  for n in 1 2; do
    cp pyproject.toml "$run/build-$n/"
    cp -R src/quant_personal_live_public_b5 "$run/build-$n/src/"
    python3 -B -m pip wheel --no-deps --no-index --no-cache-dir --no-build-isolation \
      --wheel-dir "$run/wheels-$n" "$run/build-$n"
  done
  wheel_name="quant_personal_live_public_b5-0.8.0b5.post4-py3-none-any.whl"
  cmp "$run/wheels-1/$wheel_name" "$run/wheels-2/$wheel_name"
  echo "PASS reproducible 2x build byte-identical: $wheel_name"
  sha256sum "$run/wheels-1/$wheel_name" "$run/wheels-2/$wheel_name"
} > evidence/build.log 2>&1

wheel_name="quant_personal_live_public_b5-0.8.0b5.post4-py3-none-any.whl"
wheel="$PWD/evidence/wheel/$wheel_name"
cp "$run/wheels-1/$wheel_name" "$wheel"
wheel_sha=$(sha256sum "$wheel" | awk '{print $1}')

ws=$(realpath ..)
h2a="$ws/lt-v080-sol62-h2a-b5-phaseb-activation-01"
b1="$ws/lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01"
b2="$ws/lt-v080-sol62-personal-mvp-market-decision-b2-01"
b3="$ws/lt-v080-personal-mvp-account-aware-b3-01"
b4="$ws/lt-v080-personal-mvp-public-source-bridge-b4-01"
b5="$ws/lt-v080-personal-mvp-live-public-b5-01"
r1="$ws/lt-v080-sol62-personal-mvp-layer1-public-01"
s3="$ws/lt-v080-sol62-s3-market-offline-readiness-01"
crypto="$ws/../../quant-0.7.0/lt-program-j-realtime-advisory-01/release/wheelhouse/cryptography-45.0.7-cp311-abi3-manylinux_2_34_x86_64.whl"

{
  sha256sum \
    "$wheel" \
    "$h2a/evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl" \
    "$b5/evidence/wheel/quant_personal_live_public_b5-0.8.0b5-py3-none-any.whl" \
    "$b1/evidence/wheel/quant_personal_public_b1-0.8.0b1-py3-none-any.whl" \
    "$b2/evidence/wheel/quant_personal_decision_b2-0.8.0b2-py3-none-any.whl" \
    "$b4/evidence/wheel/quant_personal_public_bridge_b4-0.8.0b4-py3-none-any.whl" \
    "$b3/evidence/wheel/quant_personal_account_b3-0.8.0b3-py3-none-any.whl" \
    "$r1/evidence/wheel/quant_advisory_platform-0.8.0-py3-none-any.whl" \
    "$crypto"
} > evidence/wheel-checksums.sha256

# 4. Create clean venv, clean target (for system pytest), mixed venv, and separate legacy targets.
for profile in clean mixed; do
  args=()
  [[ "$profile" != "mixed" ]] || args+=(--system-site-packages)
  python3 -B -m venv "${args[@]}" "$run/$profile"
  python3 -B tools/preserve.py --requirements "$profile" --wheel "$wheel" > "$run/$profile.txt"
  py="$run/$profile/bin/python"
  cli="$run/$profile/bin/quant-public-b5"
  {
    "$py" -B -m pip install --no-index --no-cache-dir --no-deps --require-hashes -r "$run/$profile.txt"
    "$py" -B -m pip check
    "$py" -B -m pip list --local
    "$py" -B - "$profile" "$wheel" "$wheel_sha" "$h2a/evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl" <<'PY'
import hashlib, sys
from importlib.metadata import version
from pathlib import Path
from quant_personal_live_public_b5.release import verify_release
from quant_personal_public_b1.policy import SourceBlocked

profile, wheel_path, wheel_sha, h2a_wheel_path = sys.argv[1:]
wheel = Path(wheel_path)
h2a_wheel = Path(h2a_wheel_path)
assert version("quant-personal-live-public-b5") == "0.8.0b5.post4"
verify_release(wheel, wheel_sha)

# Negative: wrong digest must fail closed.
try:
    verify_release(wheel, "0" * 64)
except SourceBlocked as exc:
    assert exc.code == "RELEASE_WHEEL_DIGEST_MISMATCH", exc.code
else:
    raise AssertionError("Bad wheel sha accepted")

# Negative: V1 post1 wheel against installed V2 post4 must fail closed.
h2a_sha = hashlib.sha256(h2a_wheel.read_bytes()).hexdigest()
try:
    verify_release(h2a_wheel, h2a_sha)
except SourceBlocked as exc:
    assert exc.code == "INSTALLED_RELEASE_MISMATCH", exc.code
else:
    raise AssertionError("Mixed V1 wheel accepted against V2 install")

if profile == "mixed":
    assert version("quant-personal-account-b3") == "0.8.0b3"
    assert version("quant-advisory-platform") == "0.8.0"
from quant_personal_live_public_b5.offline import plan
assert plan()["authorization"] == "NOT_AUTHORIZED"
assert not {"quant_personal_account_b3", "btc_quant_agent", "program_c"}.intersection(
    name.split(".")[0] for name in sys.modules
)
print(f"PASS {profile} install, release hash verify, mixed-wheel denial, zero private/legacy imports")
PY
  } > "evidence/install-$profile.log" 2>&1

  # Default-deny real entry points (console + module) under hostile env vars.
  printf '{"status":"ACTIVE","live_permitted":true,"signature":"forged"}\n' > "$run/forged.json"
  {
    for mode in console module; do
      invoke=("$py" -B -m quant_personal_live_public_b5)
      [[ "$mode" != "console" ]] || invoke=("$cli")
      for cmd in preflight live-once revoke; do
        rc=0
        out=$(env B5_ENABLED=1 ACTIVATION_APPROVED=1 BINANCE_API_KEY=fake BINANCE_API_SECRET=fake \
          HTTPS_PROXY=http://127.0.0.1:7 SSL_CERT_FILE="$run/forged.json" \
          "${invoke[@]}" "$cmd" --wheel "$wheel" --scope "$run/forged.json" --activation "$run/forged.json" 2>&1) || rc=$?
        [[ "$rc" == "3" && "$out" == "LIVE_CAPABILITY_NOT_ACTIVATED" ]]
        printf 'PASS %s %s %s: exit=%s %s\n' "$profile" "$mode" "$cmd" "$rc" "$out"
      done
    done
    "$cli" inspect > "$run/inspect-$profile.json"
    "$py" -B - "$run/inspect-$profile.json" <<'PY'
import json, sys
data = json.loads(open(sys.argv[1]).read())
assert data["production_state"] == "LIVE_CAPABILITY_NOT_ACTIVATED", data
assert data["funding_weight"] == "ACTIVATION_REVIEW_REQUIRED", data
assert data["methods"] == ["GET"]
print("PASS inspect default-deny:", json.dumps(data, sort_keys=True))
PY
  } > "evidence/gate-$profile.log" 2>&1
done

# Clean site-packages target (no B3/R1, with pinned cryptography==45.0.7 verifier) for clean isolated suites.
python3 -B tools/preserve.py --requirements clean-verifier --wheel "$wheel" > "$run/clean-verifier.txt"
python3 -B -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
  --target "$run/clean-target" -r "$run/clean-verifier.txt" > evidence/install-targets.log 2>&1

# Separate legacy V1 targets (H2-A post1 and original B5 0.8.0b5).
for legacy in legacy-h2a legacy-b5; do
  python3 -B tools/preserve.py --requirements "$legacy" > "$run/$legacy.txt"
  python3 -B -m pip install --no-index --no-cache-dir --no-deps --require-hashes \
    --target "$run/$legacy" -r "$run/$legacy.txt" >> evidence/install-targets.log 2>&1
done

{
  for pair in \
    "legacy-h2a:$h2a/evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl" \
    "legacy-b5:$b5/evidence/wheel/quant_personal_live_public_b5-0.8.0b5-py3-none-any.whl"; do
    prof="${pair%%:*}"
    whl="${pair#*:}"
    PYTHONPATH="$run/$prof" python3 -P -B - "$whl" "$wheel" <<'PY'
import hashlib, sys
from pathlib import Path
from quant_personal_live_public_b5.release import verify_release
from quant_personal_public_b1.policy import SourceBlocked

own_wheel = Path(sys.argv[1])
cand_wheel = Path(sys.argv[2])
verify_release(own_wheel, hashlib.sha256(own_wheel.read_bytes()).hexdigest())
try:
    verify_release(cand_wheel, hashlib.sha256(cand_wheel.read_bytes()).hexdigest())
except SourceBlocked as exc:
    assert exc.code == "INSTALLED_RELEASE_MISMATCH", exc.code
else:
    raise AssertionError("Candidate wheel accepted inside legacy install")
print(f"PASS legacy target {own_wheel.name} verified & rejected candidate wheel")
PY
    rc=0
    out=$(PYTHONPATH="$run/$prof" env B5_ENABLED=1 python3 -P -B -m quant_personal_live_public_b5 preflight 2>&1) || rc=$?
    [[ "$rc" == "3" && "$out" == "LIVE_CAPABILITY_NOT_ACTIVATED" ]]
    printf 'PASS %s preflight default-deny: exit=%s %s\n' "$prof" "$rc" "$out"
  done
} > evidence/gate-legacy.log 2>&1

# 5. Source diff audit & deterministic Plan A/B/C JSON gate generation (2x compare).
cleanpy="$run/clean/bin/python"
mixpy="$run/mixed/bin/python"
"$cleanpy" -B tools/s3_plan_gate.py --audit-diff --write-patch evidence/source-diff.patch > evidence/source-diff-audit.json
"$cleanpy" -B tools/s3_plan_gate.py --emit-gate --wheel-sha256 "$wheel_sha" > "$run/gate-1.json"
"$cleanpy" -B tools/s3_plan_gate.py --emit-gate --wheel-sha256 "$wheel_sha" > "$run/gate-2.json"
cmp "$run/gate-1.json" "$run/gate-2.json"
cp "$run/gate-1.json" S3_PLAN_A_B_C_AND_FUNDING_WEIGHT_GATE.json

# 6. Execute ALL frozen suites + NEW S3 Release-Bound Zero-Retry V2 negative QA suites.
: > "$run/groups.tsv"
failure=0
group() {
  local label=$1 rc=0
  shift
  "$@" > "evidence/test-$label.log" 2>&1 || rc=$?
  printf '%s\t%s\n' "$label" "$rc" >> "$run/groups.tsv"
  if [[ "$rc" != "0" ]]; then failure=1; fi
}

# Frozen upstream suites against candidate post4 (clean isolated target / pure clean venv)
group b1 env "PYTHONPATH=$run/clean-target" python3 -P -B -m pytest -v -ra -p no:cacheprovider \
  --basetemp="$run/b1-tests" "$b1/tests"
group b2 env "PYTHONPATH=$run/clean-target" "B2_ACCEPTED_B1_DB=$b1/evidence/demo/fixture.sqlite" \
  python3 -P -B -m pytest -v -ra -p no:cacheprovider --basetemp="$run/b2-tests" "$b2/tests"
group b4 "$cleanpy" -B -m unittest discover -s "$b4/tests" -v
group h2a-candidate env "PYTHONPATH=$run/clean-target" python3 -P -B -m unittest discover -s "$h2a/tests" -v
group b5-candidate-compat env "PYTHONPATH=$run/clean-target" python3 -P -B -m unittest discover -s "$b5/tests" -v
group s3-readiness-candidate env "PYTHONPATH=$run/clean-target:$s3/tools:$h2a/tests" \
  python3 -P -B -m pytest -v -ra -p no:cacheprovider --basetemp="$run/s3-cand-tests" "$s3/tests/test_s3.py"

# Frozen legacy V1 golden suites against untouched original H2-A post1 and B5 0.8.0b5 wheels
group h2a-legacy-v1 env "PYTHONPATH=$run/legacy-h2a" python3 -P -B -m unittest discover -s "$h2a/tests" -v
group b5-legacy-original env "PYTHONPATH=$run/legacy-b5" python3 -P -B -m unittest discover -s "$b5/tests" -v
group s3-readiness-legacy-v1 env "PYTHONPATH=$run/legacy-h2a:$s3/tools:$h2a/tests" \
  python3 -P -B -m pytest -v -ra -p no:cacheprovider --basetemp="$run/s3-leg-tests" "$s3/tests/test_s3.py"

# New comprehensive S3 Release-Bound Zero-Retry V2 Negative & Functional QA suite (clean-target + mixed venv)
common_v2_env=(
  "S3_CANDIDATE_WHEEL=$wheel"
  "S3_CANDIDATE_WHEEL_SHA256=$wheel_sha"
  "S3_H2A_WHEEL=$h2a/evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post1-py3-none-any.whl"
  "S3_B5_WHEEL=$b5/evidence/wheel/quant_personal_live_public_b5-0.8.0b5-py3-none-any.whl"
  "S3_LEGACY_H2A_TARGET=$run/legacy-h2a"
  "S3_LEGACY_B5_TARGET=$run/legacy-b5"
  "S3_CLEAN_TARGET=$run/clean-target"
)

group s3-v2-clean env "${common_v2_env[@]}" "PYTHONPATH=$run/clean-target:$PWD/tools:$h2a/tests" \
  python3 -P -B -m unittest discover -s tests -p "test_s3_zero_retry_v2.py" -v
group s3-v2-mixed env "${common_v2_env[@]}" "PYTHONPATH=$PWD/tools:$h2a/tests" \
  "$mixpy" -B -m unittest discover -s tests -p "test_s3_zero_retry_v2.py" -v

cp "$run/groups.tsv" evidence/groups.tsv

# 7. Preservation check AFTER all builds and tests (proving H2-A 69/69 & all baselines untouched).
{
  date --iso-8601=seconds
  python3 -B tools/preserve.py
} > evidence/preservation-after.log 2>&1

# 8. Summarize true PASS/FAIL/SKIP counts from raw logs.
python3 -B - "$wheel_sha" <<'PY' > evidence/qa-summary.json
import json, re, sys
from pathlib import Path

wheel_sha = sys.argv[1]
ev = Path("evidence")
groups = {}
for line in (ev / "groups.tsv").read_text().splitlines():
    label, rc = line.split("\t")
    text = (ev / f"test-{label}.log").read_text(encoding="utf-8", errors="replace")
    passed = failed = skipped = errors = 0
    # pytest summary parser
    m_pytest = re.search(r"=+\s+([^\n=]+)\s+in\s+[0-9.]+s\s+=+", text)
    # unittest summary parser
    m_unit = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+[0-9.]+s", text)
    if m_pytest:
        summary = m_pytest.group(1)
        for key, target in (("passed", "p"), ("failed", "f"), ("skipped", "s"), ("error", "e")):
            mm = re.search(rf"(\d+)\s+{key}", summary)
            val = int(mm.group(1)) if mm else 0
            if target == "p": passed = val
            elif target == "f": failed = val
            elif target == "s": skipped = val
            elif target == "e": errors = val
    elif m_unit:
        ran = int(m_unit.group(1))
        m_fail = re.search(r"failures=(\d+)", text)
        m_err = re.search(r"errors=(\d+)", text)
        m_skip = re.search(r"skipped=(\d+)", text)
        failed = int(m_fail.group(1)) if m_fail else 0
        errors = int(m_err.group(1)) if m_err else 0
        skipped = int(m_skip.group(1)) if m_skip else 0
        passed = ran - failed - errors - skipped
    groups[label] = {
        "exit_code": int(rc),
        "pass": passed,
        "fail": failed + errors,
        "skip": skipped,
        "log": f"evidence/test-{label}.log",
    }

summary = {
    "schema": "S3_ZERO_RETRY_QA_SUMMARY_V1",
    "candidate_wheel": "evidence/wheel/quant_personal_live_public_b5-0.8.0b5.post4-py3-none-any.whl",
    "candidate_wheel_sha256": wheel_sha,
    "reproducible_2x_build_identical": True,
    "groups": groups,
    "totals": {
        "pass": sum(g["pass"] for g in groups.values()),
        "fail": sum(g["fail"] for g in groups.values()),
        "skip": sum(g["skip"] for g in groups.values()),
        "nonzero_exit_groups": sum(1 for g in groups.values() if g["exit_code"] != 0),
    },
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

if [[ "$failure" == "0" ]]; then
  echo "ALL_S3_ZERO_RETRY_OFFLINE_QA_PASSED wheel_sha256=$wheel_sha"
else
  echo "S3_ZERO_RETRY_OFFLINE_QA_FAILED"
fi
exit "$failure"
