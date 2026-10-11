"""Read-only authenticated R3/R31 public caches; no new network service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.sources import source_plan
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.gaps import (
    ALLOWED_DAYS,
    compose_gap_month,
    parse_daily,
)
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.monthly import load_all

ROOT = Path(__file__).resolve().parents[3]
OLD = Path('/tmp/btc-two-lead-funding-mark-r3')
GAP = Path('/tmp/btc-two-lead-mark-gap-r31')
SCRATCH = Path('/tmp/btc-exit-horizon-r1')
EP = ROOT / 'evidence/v0.6/b_line/g2_exit_horizon_r1'
R31_EP = ROOT / 'evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31'


def guarded(path, base):
    if path.parent != base or base.is_symlink() or path.is_symlink():
        raise ValueError('Unauthorized or symlinked public cache path')
    if base.parent == GAP and GAP.is_symlink():
        raise ValueError('Symlinked R31 parent')
    return path


def load():
    if not __debug__:
        raise ValueError("Optimized Python forbidden before any source inspection")
    # Preflight every approved exact filename so inherited load_all cannot take
    # its download fallback or write the previous task scratch.
    for y in (2021, 2022, 2023):
        for m in range(1, 13):
            for kind in ('last', 'mark', 'funding'):
                p = source_plan(y, m, kind)
                for suffix in ('', '.CHECKSUM'):
                    q = guarded(OLD / (kind+'-'+p['zip_name']+suffix), OLD)
                    if not q.is_file():
                        raise ValueError('Required signed R3 cache unavailable; no new source retry')
    arrays, rates, receipt = load_all()
    reference = json.loads((R31_EP/'R31_COMPOSITE_SOURCE_MANIFEST.json').read_text())
    days = {}
    for d in ALLOWED_DAYS:
        ref = next(x for x in reference['gap_source_receipts'] if x['day'] == d)
        folder = GAP / d
        name = f'BTCUSDT-1m-{d}.zip'
        raw = guarded(folder/name, folder).read_bytes()
        check = guarded(folder/(name+'.CHECKSUM'), folder).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref['daily_parse']['zip_sha256']
        assert hashlib.sha256(check).hexdigest() == ref['daily_parse']['checksum_sha256']
        days[d], proof = parse_daily(raw, check, d)
        assert len(days[d]) == 1440 and proof['csv_sha256'] == ref['daily_parse']['csv_sha256']
    proofs = []
    for (y, m), a in arrays['mark'].items():
        extra = [days[d] for d in ALLOWED_DAYS if d.startswith(f'{y}-{m:02d}-')]
        arrays['mark'][y,m], p = compose_gap_month(a, extra, y, m)
        original = next(x for x in reference['composites'] if (x['year'],x['month']) == (y,m))
        assert p['dense'] and p['composite_sha256'] == original['composite_sha256']
        proofs.append({'year':y,'month':m,**p})
    assert sum(map(len,arrays['mark'].values())) == 1576800
    receipt.update({'R31_source_manifest_sha256':reference['source_manifest_sha256'],
                    'source_manifest_sha256':reference['source_manifest_sha256'],
                    'composites':proofs,'daily_receipts':reference['gap_source_receipts'],'network_calls':0,'old_scratch_writes':0,
                    'allowed_cache_roots':[str(OLD),str(GAP)],
                    'known_at':'UNKNOWN; retrospective sources not entry signals',
                    'settlement_Mark':'latest completed 1m close approximation'})
    return arrays, rates, receipt
