"""Opt-in synthetic benchmark; never reads a real strategy outcome artifact."""
from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from btc_quant_agent.h40 import discovery_evidence as science
from btc_quant_agent.h40.search_space import materialize_h40_search_space_production


def reconstruction_scales():
    import h40_runtime_reference as reference
    samples = []
    for count in (264, 2048, 8192, 15312):
        start = datetime(2021, 1, 1, tzinfo=UTC)
        bars = {}
        for i in range(count + 96):
            t = start + timedelta(hours=i)
            close = 100 * math.exp(0.003 * math.sin(i / 9) + 0.001 * math.cos(i / 3))
            bars[(t, 'ETHUSDT')] = science._Bar(t, 'ETHUSDT', close * 0.999, close * 1.005, close * 0.995, close)
        slot = SimpleNamespace(direction_contract_id='D1_V1_RETURN_4H', primary_horizon='4h')
        kwargs = {'candidate_id': 'synthetic-scale', 'slot': slot, 'partition_id': 'WF1_TRAIN', 'product': 'ETHUSDT', 'bars': bars, 'source_evidence_hash': f'synthetic-scale-{count}'}
        for mode in ('indexed', 'reference') if count <= 2048 else ('indexed',):
            reference._PREFIT_CACHE.clear()
            reference._TRAINING_REFS.clear()
            science.clear_prefit_caches()
            clock = time.perf_counter()
            with science._reconstruction_scope() as state:
                function = science._reconstruct_prefit_cached if mode == 'indexed' else reference._reconstruct_prefit_cached
                values = [function(t=start + timedelta(hours=i), **kwargs) for i in range(96, count + 96)]
                stats = state.statistics()
            elapsed = time.perf_counter() - clock
            samples.append({'train_hours':count,'mode':mode,'seconds':elapsed,'cache_cardinality':stats})
            if mode == 'indexed':
                indexed = values
            else:
                assert values == indexed
    return samples


def full_roundtrip(root: Path):
    from test_v051_h40_m3a_production_discovery_producer import (
        _producer,
        _synthetic_authority,
        _verifier,
    )
    start = datetime(2021, 1, 1, tzinfo=UTC)
    end = datetime(2023, 2, 1, tzinfo=UTC)
    hours = int((end-start).total_seconds()/3600)
    total = time.perf_counter()
    with pytest.MonkeyPatch.context() as patch:
        clock = time.perf_counter()
        authority = _synthetic_authority(root, patch, segments=((start, hours),))
        setup = time.perf_counter()-clock
        print(json.dumps({"phase":"source_seal_setup","seconds":setup}),flush=True)
        science.clear_prefit_caches()
        clock = time.perf_counter()
        result = _producer(authority).produce()
        producer_stats = dict(science._LAST_RECONSTRUCTION_STATS)
        producer = time.perf_counter()-clock
        print(json.dumps({"phase":"producer","seconds":producer}),flush=True)
        verifier = _verifier(authority)
        clock = time.perf_counter()
        verifier.verify_discovery_manifest(result.evidence, result.entries)
        verifier_stats = dict(science._LAST_RECONSTRUCTION_STATS)
        manifest = time.perf_counter()-clock
        print(json.dumps({"phase":"verifier_manifest","seconds":manifest}),flush=True)
        clock = time.perf_counter()
        outputs = [verifier.verify_candidate(entry, run_authority_id=result.evidence.run_authority_id,
                   correction_manifest_hash=result.evidence.correction_input_evidence_manifest_hash) for entry in result.entries]
        candidate = time.perf_counter()-clock
        print(json.dumps({"phase":"candidate_verifications","seconds":candidate}),flush=True)
        assert len(outputs)==18
        counts = {}
        for entry in result.entries:
            payload = json.loads((authority.root / entry.candidate_result_input_evidence_hash[:2] / f'{entry.candidate_result_input_evidence_hash}.json').read_bytes())
            for name in ('training_evidence_hash','calibration_evidence_hash'):
                digest = payload[name]
                rows = json.loads((authority.root / digest[:2] / f'{digest}.json').read_bytes())['rows']
                counts.setdefault(name, len(rows))
                assert len(rows)==counts[name]
        assert counts == {'training_evidence_hash':15312,'calibration_evidence_hash':2184}, counts
        return {'synthetic_only':True,'source_hours':hours,'train_hours':15312,'calibration_hours':2184,'candidate_rows':314928,
                'setup_wall_seconds':setup,'producer_wall_seconds':producer,'verifier_manifest_wall_seconds':manifest,
                'candidate_verify_wall_seconds':candidate,'total_wall_seconds':time.perf_counter()-total,
                'roundtrip_only_wall_seconds':producer+manifest+candidate,
                'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                'evidence_objects':len(result.dependency_digests),
                'evidence_disk_mib':sum(p.stat().st_size for p in authority.root.rglob('*.json'))/1024**2,
                'producer_cache_cardinality':producer_stats,'verifier_cache_cardinality':verifier_stats,
                'released_cache_state':science._ACTIVE_RECONSTRUCTION.get() is None,
                'discovery_evidence_hash':result.evidence.evidence_sha256,
                'fit_status_counts':{status:sum(json.loads((authority.root/e.candidate_result_input_evidence_hash[:2]/f'{e.candidate_result_input_evidence_hash}.json').read_bytes())['fit_status']==status for e in result.entries) for status in ('COMPLETE','FIT_INVALID')},
                'registered_slots':len([s for s in materialize_h40_search_space_production().slots if getattr(s.status,'value',s.status)=='REGISTERED'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('full','scales'),required=True)
    parser.add_argument('--root',type=Path)
    arguments = parser.parse_args()
    print(json.dumps({'python_executable':sys.executable,'science_module':science.__file__},sort_keys=True),flush=True)
    if arguments.mode=='full':
        if arguments.root is None or not arguments.root.is_dir() or any(arguments.root.iterdir()):
            parser.error('full benchmark requires an existing empty synthetic root')
        measurements = full_roundtrip(arguments.root)
    else:
        measurements = reconstruction_scales()
    print(json.dumps(measurements,indent=2,sort_keys=True),flush=True)
