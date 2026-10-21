"""Explicit offline execution, requiring a persisted out-of-band pinned scope."""

import csv
import hashlib
import io
from pathlib import Path

from .contract import LABELS, OUTPUTS, acceptance, validate
from .evaluate import evaluate
from .native import feature_masks, read_sources
from .safeio import canonical, digest, load, path, publish, read_exact


def execute(registration_path, manifest_path, registry_id):
    # Resolve trust FIRST: a random CLI input must not cause even a metadata read.
    a, pin = acceptance(registry_id)
    rp, mp = path(str(registration_path)), path(str(manifest_path))
    from . import require
    require(str(rp) == a['registration_path'] and str(mp) == a['manifest_path'], 'INPUT_IDENTITY')
    r = load(read_exact(rp))
    m = load(read_exact(mp))
    validate(r, m, a, pin, rp, mp)
    tables, qa = read_sources(m)
    masks = feature_masks(r, tables)
    mask_sha = digest(masks)
    ledger, metrics, missing = evaluate(r, tables, masks)
    # Revalidate accepted state, paths and source identities before publishing.
    a2, pin2 = acceptance(registry_id)
    require(a2 == a and pin2 == pin, 'ACCEPTANCE_CHANGED')
    require(load(read_exact(rp)) == r and load(read_exact(mp)) == m, 'INPUT_MUTATED')
    validate(r, m, a, pin, rp, mp)
    for f in m['files']:
        read_exact(path(f['path']), f['sha256'], f['stat'])
    output = Path(r['output_dir'])
    receipt = {'schema': r['schema'], 'registration_sha256': digest(r),
               'manifest_sha256': digest(m), 'acceptance_sha256': digest(a),
               'trusted_registry_pin': pin, 'feature_masks_sha256': mask_sha,
               'labels': LABELS, 'source': 'SOURCE_ADMITTED_FOR_EXACT_EXPERIMENT_ONLY',
               'cost': 'COST_INCOMPLETE', 'funding': 'UNRESOLVED_NOT_ZERO',
               'complete_modeled_net_pnl': False, 'trades': len(ledger),
               'result_status': 'PARTIAL_COST_ADJUSTED_EXPLORATORY_ONLY',
               'protected_panels_used': 0, 'network_calls': 0}
    text = io.StringIO(newline='')
    columns = list(ledger[0]) if ledger else [
        'arm', 'origin_ms', 'entry_ms', 'exit_ms', 'gross_return',
        'partial_cost_adjusted_return', 'modeled_net_return', 'cost_status']
    writer = csv.DictWriter(text, columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(ledger)
    artifacts = {
        'EXPERIMENT_REGISTRATION.json': canonical(r),
        'ACCEPTED_SCOPE_RECORD.json': canonical(a), 'SOURCE_MANIFEST.json': canonical(m),
        'SOURCE_QA.json': canonical({'files': qa, 'feature_masks': masks}),
        'BTC_TRADE_LEDGER.csv': text.getvalue().encode(),
        'BTC_ECONOMICS.json': canonical({'labels': LABELS, 'cost_status': 'COST_INCOMPLETE',
                                       'complete_net_pnl': False, 'arms': metrics}),
        'LOSS_AND_MISSINGNESS.json': canonical({'counts': missing,
            'funding': 'MISSING_VERIFIED_CALENDAR_AND_MARK_MAPPING',
            'matched_populations_frozen_before_outcomes': True,
            'executed_populations_may_differ_due_to_each_arm_concurrency': True}),
        'RUN_RECEIPT.json': canonical(receipt),
        'DECISION.md': ('EXPLORATORY_ONLY\n\nPartial execution-cost sensitivity only. '
                        'COST_INCOMPLETE; funding unresolved. No complete net PnL.\n\n'
                        + '\n'.join(LABELS.values())+'\n').encode(),
    }
    artifacts['HASH_MANIFEST.json'] = canonical({
        name: hashlib.sha256(payload).hexdigest() for name, payload in artifacts.items()})
    require(set(artifacts) == set(OUTPUTS), 'OUTPUT_CONTRACT')
    for name in OUTPUTS:
        publish(output/name, artifacts[name])
    return receipt
