#!/usr/bin/env bash
# Run from H1 P0 fix workroot as: unshare -n -- bash tools/qa.sh
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LC_ALL=C PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INDEX=1
unset PYTHONPATH
export SOURCE_DATE_EPOCH=1795132800

[[ "$(readlink /proc/self/ns/net)" != "$(readlink /proc/1/ns/net)" ]]
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 && -z "$(ip route show default)" && -z "$(ip -6 route show default)" ]]

mkdir -p evidence/wheel evidence/demo reference-export
run=$(mktemp -d /tmp/h1q.XXXX)
export TMPDIR="$run"
trap 'rm -rf "$run"' EXIT

set -x
{
  readlink /proc/self/ns/net
  ip -brief address
  ip route show table main
  ip -6 route show table main
  python3 --version
  node --version
  /usr/local/lib/hermes-agent/venv/bin/python --version
  python3 tools/preserve.py
} > evidence/preservation.log 2>&1

b1=(../*b1-01/evidence/wheel/*.whl)
b2=(../*b2-01/evidence/wheel/*.whl)
b4=(../*b4-01/evidence/wheel/*.whl)
b5=(../*b5-01/evidence/wheel/*.whl)
b3=(../*b3-01/evidence/wheel/*.whl)
r1=(../*layer1-public-01/evidence/wheel/*.whl)
crypto=(../../../quant-0.7.0/lt-program-j-realtime-advisory-01/release/wheelhouse/cryptography-45.0.7*.whl)
orig_h1_wheel="../lt-v080-gemini-neon-hermes-quant-feishu-h1-01/evidence/wheel/quant_hermes_feishu_h1-0.8.0-py3-none-any.whl"

printf '%s  %s\n' \
  19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f "${b1[0]}" \
  29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64 "${b2[0]}" \
  c30332d0028b14f2c7ee89ef941be3e9d51f1ff500231bb9cbcaae95a63c7710 "${b4[0]}" \
  eb6076a3a98f3fa82512a2b748d8cbf44333ca9f56dec265b163c6f6857ddab3 "${b5[0]}" \
  ed11906d6b23b74ef90984a44a7c6cadfff68543bee7f9715226af366f769c5f "${b3[0]}" \
  7f7877fe4b0efc5c1456ea02d91a91f78cbd99f2ee3ad8dd6853e87ea86f6fcc "${r1[0]}" \
  b6a0e535baec27b528cb07a119f321ac024592388c5681a5ced167ae98e9fff3 "${crypto[0]}" \
  aed14d03ee51cafc34b89f5d30adf9ca2a676d7b851863c644c59b57ff4b81cc "$orig_h1_wheel" \
  | sha256sum -c - > evidence/dependency-hashes.log

mkdir -p "$run/src-tree/src" "$run/rebuild"
cp pyproject.toml "$run/src-tree/"
cp -R src/quant_hermes_feishu_h1 "$run/src-tree/src/"
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run" "$run/src-tree" > evidence/build.log 2>&1
python3 -m pip wheel --no-index --no-deps --no-cache-dir --no-build-isolation --wheel-dir "$run/rebuild" "$run/src-tree" >> evidence/build.log 2>&1
wheel="$run/quant_hermes_feishu_h1-0.8.0.post1-py3-none-any.whl"
cmp "$wheel" "$run/rebuild/$(basename "$wheel")"
rm -f evidence/wheel/*.whl
cp "$wheel" evidence/wheel/
(cd evidence/wheel && sha256sum ./*.whl) >> evidence/build.log

ruff check --no-cache src tests fixtures tools hermes-plugin > evidence/ruff.log 2>&1

# Before-fix P0 reproduction & regression failure proof against untouched original H1
ORIG_H1="../lt-v080-gemini-neon-hermes-quant-feishu-h1-01"
python3 tools/reproduce_original_p0.py --output evidence/p0-before-repro.json > evidence/p0-before-repro.log 2>&1
orig_rc=0
H1_SKIP_SUBPROCESS_EXPORT=1 PYTHONPATH="$ORIG_H1/src:$PWD" \
  python3 -m pytest -v -p no:cacheprovider --basetemp="$run/t0" tests/test_p0_remediation.py \
  > evidence/p0-regression-fails-on-original.log 2>&1 || orig_rc=$?
[[ "$orig_rc" != 0 ]]

# Canonical Python P0-C03 export reproducibility + Node 24 TypeScript cross-language comparison
rm -rf reference-export "$run/ref-a" "$run/ref-b"
python3 tools/export_reference_goldens.py --output "$run/ref-a" > evidence/reference-export.log 2>&1
python3 tools/export_reference_goldens.py --output "$run/ref-b" >> evidence/reference-export.log 2>&1
diff -ru "$run/ref-a" "$run/ref-b" >> evidence/reference-export.log
mkdir -p reference-export && cp -R "$run/ref-a/." reference-export/
ORACLE_JSON="../../../quant-docs-engineering/docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json"
node tools/compare_goldens.ts --export-dir reference-export --oracle "$ORACLE_JSON" > evidence/node-cross-language-compare.log 2>&1

# Clean Python 3.12 venv install + compileall + live gate + demo + pytest (Clean 6 modules)
python3 -m venv --system-site-packages "$run/clean"
py="$run/clean/bin/python"
cli="$run/clean/bin/quant-hermes-h1"
{
  "$py" -m pip install --no-index --no-deps --no-cache-dir "$wheel" "${b1[0]}" "${b2[0]}" "${b4[0]}" "${b5[0]}"
  "$py" -m pip check
  "$py" -m pip list --local
  mkdir -p "$run/compile-check"
  cp -R src tests fixtures tools hermes-plugin "$run/compile-check/"
  "$py" -m compileall -q "$run/compile-check"
  "$py" - "$wheel" <<'PY'
import zipfile, sys
from importlib.metadata import entry_points, version
assert version("quant-hermes-feishu-h1") == "0.8.0.post1"
eps = entry_points().select(group="hermes_agent.plugins")
assert any(e.name == "quant-v080-readonly" for e in eps)
with zipfile.ZipFile(sys.argv[1]) as zf:
    names = zf.namelist()
assert all(not n.startswith(("quant_personal_account_b3", "quant_personal_live_public_b5", "quant_personal_decision_b2", "btc_quant_agent")) for n in names)
print("Clean wheel entries verified:", len(names))
PY
} > evidence/install-clean.log 2>&1

{
  for target in feishu-live binance-live model-oauth; do
    rc=0
    out=$("$cli" check-live-gate --target "$target" 2>&1) || rc=$?
    [[ "$rc" == 3 && "$out" == "LIVE_CAPABILITY_NOT_AUTHORIZED" ]]
    printf 'cli %s: exit %s %s\n' "$target" "$rc" "$out"
  done
} > evidence/gate-clean.log

rm -rf evidence/demo
"$cli" demo \
  --output evidence/demo \
  --journal "b5_pullback_long=../lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite" \
  --journal "b2_pullback_short=../lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo/pullback-short/decision.sqlite" \
  --journal "b2_early_long=../lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo/early-long/decision.sqlite" \
  --journal "b2_early_short=../lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo/early-short/decision.sqlite" \
  > evidence/demo-cli.log 2>&1

PYTHONPATH="$PWD" "$py" -m pytest -v -p no:cacheprovider --basetemp="$run/t1" \
  tests/test_contract_and_facade.py \
  tests/test_isolation_and_acl.py \
  tests/test_outbox_and_rendering.py \
  tests/test_feishu_chat_and_explainer.py \
  tests/test_metrics_and_preservation.py \
  tests/test_p0_remediation.py \
  > evidence/h1-py312-clean-pytest.log 2>&1

# Mixed Python 3.12 venv (with B3, R1, cryptography present; verify H1 never imports B3/legacy)
python3 -m venv --system-site-packages "$run/mixed"
mixpy="$run/mixed/bin/python"
{
  "$mixpy" -m pip install --no-index --no-deps --no-cache-dir \
    "$wheel" "${b1[0]}" "${b2[0]}" "${b3[0]}" "${b4[0]}" "${b5[0]}" "${r1[0]}" "${crypto[0]}"
  "$mixpy" -m pip check
  "$mixpy" - <<'PY'
import sys
from importlib.metadata import version
import quant_hermes_feishu_h1.cli
assert version("quant-personal-account-b3") == "0.8.0b3"
assert version("quant-advisory-platform") == "0.8.0"
assert all(
    name.partition(".")[0] not in {"quant_personal_account_b3", "btc_quant_agent", "program_c"}
    for name in sys.modules
)
print("Mixed install verified: zero B3/legacy runtime imports")
PY
} > evidence/install-mixed.log 2>&1

PYTHONPATH="$PWD" "$mixpy" -m pytest -v -p no:cacheprovider --basetemp="$run/t2" \
  tests/test_contract_and_facade.py \
  tests/test_isolation_and_acl.py \
  tests/test_outbox_and_rendering.py \
  tests/test_feishu_chat_and_explainer.py \
  tests/test_metrics_and_preservation.py \
  tests/test_p0_remediation.py \
  > evidence/h1-py312-mixed-pytest.log 2>&1

# Isolated Hermes v0.16.0 (Python 3.11) integration run using wheel target dir and scratch HERMES_HOME
mkdir -p "$run/hermes-site" "$run/hermes-home"
python3 -m pip install --no-index --no-deps --no-cache-dir --target "$run/hermes-site" "$wheel" > evidence/install-hermes-py311.log 2>&1
env -u FEISHU_APP_ID -u FEISHU_APP_SECRET -u FEISHU_ALLOWED_USERS -u OPENAI_API_KEY -u GEMINI_API_KEY -u ANTHROPIC_API_KEY \
  H1_REQUIRE_ENTRYPOINT=1 HERMES_HOME="$run/hermes-home" PYTHONPATH="$run/hermes-site:$PWD" \
  /usr/local/lib/hermes-agent/venv/bin/python -m pytest -v -p no:cacheprovider --basetemp="$run/t3" tests/ \
  > evidence/h1-hermes-py311-pytest.log 2>&1

python3 tools/preserve.py >> evidence/preservation.log 2>&1
echo "ALL_H1_P0_QA_PASSED"
