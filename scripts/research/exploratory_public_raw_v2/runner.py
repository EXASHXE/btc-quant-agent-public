"""Exact price-only deployment using unchanged V1 security and accounting checks."""

import csv
import hashlib
import io
from pathlib import Path

from ..exploratory_public_raw_v1 import require
from ..exploratory_public_raw_v1.contract import LABELS, OUTPUTS, validate
from ..exploratory_public_raw_v1.evaluate import evaluate
from ..exploratory_public_raw_v1.native import feature_masks, read_sources
from ..exploratory_public_raw_v1.safeio import canonical, digest, load, path, publish, read_exact
from .proof import complete_coverage, validate_proof
from .trust import resolve


def admitted(registry_id, registration_path, manifest_path):
    a, pin, proof, audit = resolve(registry_id)  # Trust FIRST; no manifest-driven authority.
    rp, mp = path(str(registration_path)), path(str(manifest_path))
    require(str(rp) == a['registration_path'] and str(mp) == a['manifest_path'], 'INPUT_IDENTITY')
    r, m = load(read_exact(rp)), load(read_exact(mp))
    # V1 digests use canonical bytes. V2 additionally requires the exact file bytes.
    require(read_exact(rp, a['registration_sha256']) == canonical(r), 'REGISTRATION_BYTES')
    require(read_exact(mp, a['manifest_sha256']) == canonical(m), 'MANIFEST_BYTES')
    validate(r, m, a, pin, rp, mp)
    validate_proof(r, m, a, proof)
    return r, m, a, pin, proof, audit


def concentration(metrics):
    for values in metrics.values():
        weeks, years = values['iso_week_counts'], values['years']
        count = sum(weeks.values())
        hhi = sum((n/count)**2 for n in weeks.values()) if count else None
        values.update(
            cluster_basis='UTC_ISO_WEEK_ENTRY_COUNTS_DESCRIPTIVE_ONLY',
            occupied_week_clusters=len(weeks),
            effective_week_clusters=1/hhi if hhi else None,
            year_trade_shares={y: n/count for y, n in years.items()} if count else {},
            effective_clusters_are_not_independent_sample_size=True,
        )


def execute(registration_path, manifest_path, registry_id):
    state = admitted(registry_id, registration_path, manifest_path)
    r, m, a, pin, _proof, audit = state
    tables, qa = read_sources(m)
    complete_coverage(m, tables, qa)
    masks = feature_masks(r, tables)
    ledger, metrics, missing = evaluate(r, tables, masks)
    concentration(metrics)
    # Recheck externally anchored authority, evidence, paths and bytes before publication.
    require(admitted(registry_id, registration_path, manifest_path) == state,
            'ACCEPTED_STATE_CHANGED')
    for f in m['files']:
        read_exact(path(f['path']), f['sha256'], f['stat'])
    receipt = {
        'schema': 'exact-public-raw-run.v2', 'registration_sha256': digest(r),
        'manifest_sha256': digest(m), 'acceptance_file_sha256': pin['sha256'],
        'deployment_evidence': audit, 'feature_masks_sha256': digest(masks),
        'labels': LABELS, 'source': 'SOURCE_QUALIFIED_EXACT_PUBLIC_RAW',
        'terminal': 'REAL_PUBLIC_RAW_X_EXPLORATORY_PARTIAL_ECONOMICS_READY',
        'result_status': 'PARTIAL_COST_ADJUSTED_EXPLORATORY_ONLY', 'trades': len(ledger),
        'cost': 'COST_INCOMPLETE', 'funding': 'UNKNOWN_NOT_ZERO',
        'complete_modeled_net_pnl': False, 'protected_panels_used': 0, 'network_calls': 0,
    }
    stream = io.StringIO(newline='')
    columns = list(ledger[0]) if ledger else [
        'arm', 'origin_ms', 'entry_ms', 'exit_ms', 'gross_return',
        'partial_cost_adjusted_return', 'funding_return', 'modeled_net_return', 'cost_status']
    writer = csv.DictWriter(stream, columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(ledger)
    artifacts = {
        'EXPERIMENT_REGISTRATION.json': canonical(r),
        'SOURCE_MANIFEST.json': canonical(m), 'ACCEPTED_SCOPE_RECORD.json': canonical(a),
        'SOURCE_QA.json': canonical({'files': qa, 'feature_masks': masks,
                                     'source_proof_sha256': audit['source_proof_sha256']}),
        'BTC_TRADE_LEDGER.csv': stream.getvalue().encode(),
        'BTC_ECONOMICS.json': canonical({'labels': LABELS, 'cost_status': 'COST_INCOMPLETE',
                                       'complete_net_pnl': False, 'arms': metrics}),
        'LOSS_AND_MISSINGNESS.json': canonical({'counts': missing,
            'funding': 'MISSING_VERIFIED_CALENDAR_AND_MARK_MAPPING',
            'matched_populations_frozen_before_outcomes': True}),
        'RUN_RECEIPT.json': canonical(receipt),
        'DECISION.md': ('REAL_PUBLIC_RAW_X_EXPLORATORY_PARTIAL_ECONOMICS_READY\n\n'
                        'EXPLORATORY_ONLY; partial execution-cost sensitivities. '
                        'Funding unknown, never zero; modeled_net_return NULL. '
                        'No complete net PnL or Alpha.\n\n' + '\n'.join(LABELS.values())+'\n').encode(),
    }
    artifacts['HASH_MANIFEST.json'] = canonical({
        name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()})
    require(set(artifacts) == set(OUTPUTS), 'OUTPUT_CONTRACT')
    for name in OUTPUTS:
        publish(Path(r['output_dir'])/name, artifacts[name])
    return receipt
