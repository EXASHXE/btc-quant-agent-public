"""Cross-check the exact independent intake, publisher checksums and rights bytes.

This is source QA, never an acceptance writer or a source-signature claim.
"""

from datetime import datetime

from ..exploratory_public_raw_v1 import require
from ..exploratory_public_raw_v1.contract import keys, utc, window
from ..exploratory_public_raw_v1.native import MINUTE
from ..exploratory_public_raw_v1.safeio import file_info, load, path, read_exact

CONTROLLER_HASHES = {
    'intake': '2df5d9db04ea54728c61a86b4c5134935af99744aa875dd69d6fe1de6a1cd203',
    'identity': '92207f200791e8b927818db246921e8011dd684eac2ad59e6a97223bbc218fa0',
    'clock': '77cdf37f92329f7353abd2f5da538f1d3e02a241302e15b7a7d1a6e93c071926',
}
ORIGINS = ['2021-04-02T00:00:00Z', '2021-06-25T00:00:00Z']
SUPPORT = ['2021-03-01T00:00:00Z', '2021-07-01T00:00:00Z']
MONTH_BOUNDARIES = ['2021-03-01T00:00:00Z', '2021-04-01T00:00:00Z',
                    '2021-05-01T00:00:00Z', '2021-06-01T00:00:00Z',
                    '2021-07-01T00:00:00Z']
RIGHTS_SCOPE = 'PERSONAL_NONCOMMERCIAL_HISTORICAL_RESEARCH_ONLY_NO_LIVE_NO_REDISTRIBUTION'


def bytes_ref(ref):
    keys(ref, 'path sha256 stat')
    return read_exact(path(ref['path']), ref['sha256'], ref['stat'], cap=4 * 1024 * 1024)


def validate_proof(r, m, a, proof):
    """No market payload reads. All metadata comes from accepted proof bytes."""
    keys(proof, 'schema controller_receipts rights catalog files')
    require(proof['schema'] == 'exact-public-source-proof.v2', 'SOURCE_PROOF_SCHEMA')
    require(r['origins'] == ORIGINS and r['support'] == SUPPORT
            and r['use_oi'] is False and r['economics'] == 'PARTIAL_EXECUTION_SENSITIVITY'
            and r['complete_net_claim'] is False, 'EXACT_PRICE_ONLY_SCOPE')
    receipts = proof['controller_receipts']
    keys(receipts, 'intake identity clock')
    docs = {}
    for name, ref in receipts.items():
        require(ref['sha256'] == CONTROLLER_HASHES[name], 'CONTROLLER_RECEIPT_PIN')
        docs[name] = load(bytes_ref(ref))
    intake, identity, clock = (docs[k] for k in ('intake', 'identity', 'clock'))
    require(identity['input_intake_sha256'] == CONTROLLER_HASHES['intake']
            and clock['input_source_proof_sha256'] == CONTROLLER_HASHES['identity']
            and identity['source_hashes_all_match'] is True and clock['complete'] is True,
            'CONTROLLER_PROOF_CHAIN')
    require(intake['candidate_origin_utc'] == r['origins']
            and intake['proposed_whole_source_window_utc'] == r['support'], 'CONTROLLER_SCOPE')
    rights = proof['rights']
    keys(rights, 'assessment publisher_terms publisher_receipt r2_recorded_terms_sha256 '
         'mapping scope')
    ir = intake['acquisition_rights_evidence']
    require(rights['scope'] == RIGHTS_SCOPE
            and rights['mapping'] == ir['licence_mapping'], 'RIGHTS_MAPPING')
    for key, expected_path, expected_sha in (
        ('assessment', ir['rights_assessment_path'], ir['rights_assessment_sha256']),
        ('publisher_terms', None, ir['publisher_snapshot_sha256']),
        ('publisher_receipt', ir['publisher_document_receipt_path'],
         ir['publisher_document_receipt_sha256']),
    ):
        ref = rights[key]
        require(ref['sha256'] == expected_sha
                and (expected_path is None or ref['path'] == expected_path), 'RIGHTS_IDENTITY')
    assessment = load(bytes_ref(rights['assessment']))
    terms = bytes_ref(rights['publisher_terms'])
    receipt = load(bytes_ref(rights['publisher_receipt']))
    recorded = assessment['binance']
    require(recorded['terms_sha256'] == rights['r2_recorded_terms_sha256']
            and recorded['terms_commit'] == ir['publisher_terms_commit']
            and recorded['state'] == 'PERSONAL_ARCHIVE_RESEARCH_ALLOWED', 'R2_RIGHTS_IDENTITY')
    term_records = [d for d in receipt['documents']
                    if d['file'] == path(rights['publisher_terms']['path']).name]
    require(len(term_records) == 1, 'PUBLISHER_TERMS_RECEIPT')
    term_record = term_records[0]
    require(term_record['sha256'] == rights['publisher_terms']['sha256']
            and term_record['url'] == ir['publisher_snapshot_url']
            and term_record['status'] == 200 and len(terms) == term_record['bytes'],
            'PUBLISHER_TERMS_RECEIPT')
    require(a['rights']['document_sha256'] == rights['publisher_terms']['sha256']
            and a['rights']['publisher_reference'] == ir['publisher_snapshot_url']
            and a['rights']['applicability'] == RIGHTS_SCOPE
            and a['rights']['acquisition_evidence'] == rights['mapping'], 'ACCEPTED_RIGHTS_MAPPING')
    files = proof['files']
    require(len(files) == len(m['files']) == len(identity['source_files'])
            == len(clock['checks']) == len(intake['selected_exact_files']) == 4,
            'EXACT_FOUR_SOURCES')
    require(proof['catalog']['table'] == 'archives'
            and proof['catalog']['path'].endswith('/bline-r2-20261019/catalog.sqlite'),
            'CATALOG_IDENTITY')
    require([f['coverage'] for f in m['files']] == [MONTH_BOUNDARIES[i:i+2] for i in range(4)],
            'EXACT_MONTHLY_SUPPORT')
    for f, evidence, source, checked, coverage in zip(
        m['files'], files, intake['selected_exact_files'], identity['source_files'],
        clock['checks'], strict=True,
    ):
        keys(evidence, 'path catalog_record publisher_checksum')
        record = evidence['catalog_record']
        require(f['path'] == evidence['path'] == source['path'] == checked['path']
                == record['path'], 'EXACT_SOURCE_IDENTITY')
        require(f['sha256'] == source['reported_sha256']
                == source['publisher_sha256_at_acquisition'] == checked['sha256']
                == coverage['source_sha256'] == record['sha256'] == record['publisher_sha256'],
                'PUBLISHER_SOURCE_HASH')
        require(record['status'] == 'DOWNLOADED_VERIFIED'
                and record['venue'] == f['venue'] == 'binance'
                and record['product'] == f['product'] == 'USD_M_PERPETUAL'
                and record['symbol'] == f['symbol'] == 'BTCUSDT'
                and record['family'] == 'klines' and f['family'] == 'price_1m'
                and record['interval'] == '1m' and record['period'] == coverage['month']
                and record['publisher_checksum_required'] is True, 'CATALOG_SOURCE_IDENTITY')
        require(f['publisher_url'] == source['publisher_url'] == checked['publisher_url']
                == record['url'] == 'https://data.binance.vision/data/futures/um/monthly/'
                f"klines/BTCUSDT/1m/BTCUSDT-1m-{record['period']}.zip", 'PUBLISHER_IDENTITY')
        require(f['stat'] == checked['stat'] == file_info(path(f['path']))
                and f['stat'][2] == record['bytes'] == checked['bytes'], 'CONTROLLER_STAT_IDENTITY')
        require(f['format'] == 'zip' and checked['row_format'] == 'HEADERLESS'
                and checked['zip_member'] == f"BTCUSDT-1m-{record['period']}.csv",
                'NATIVE_ARCHIVE_IDENTITY')
        lo, hi = window(f['coverage'])
        require(coverage['full_month_utc_coverage'] is True and coverage['gap_minutes'] == 0
                and coverage['first_open_ms'] == lo and coverage['last_open_ms'] == hi-MINUTE
                and coverage['rows'] == (hi-lo)//MINUTE
                and coverage['native_clock'] == 'INCLUSIVE_CLOSE_OPEN_PLUS_59999',
                'CONTROLLER_CLOCK_COVERAGE')
        sidecar = evidence['publisher_checksum']
        require(sidecar['path'] == record['publisher_checksum_path'], 'PUBLISHER_SIDECAR_IDENTITY')
        parts = bytes_ref(sidecar).decode('ascii').split()
        require(parts == [f['sha256'], path(f['path']).name], 'PUBLISHER_SIDECAR_HASH')
        acquired = datetime.fromisoformat(source['acquired_at_utc'])
        checked_at = datetime.fromisoformat(source['checked_at_utc'])
        require(record['downloaded_at_utc'] == source['acquired_at_utc']
                and checked['acquired_at_utc'] == source['acquired_at_utc']
                and record['checked_at_utc'] == source['checked_at_utc']
                and checked_at <= acquired
                and hi <= int(acquired.timestamp()*1000) < utc(r['registered_at']),
                'SOURCE_CHRONOLOGY')
        require(f['availability_delay_ms'] == 60000, 'CONSERVATIVE_EVENT_AVAILABILITY')


def complete_coverage(manifest, tables, qa):
    """V1 allows sparse inputs; this exact repair requires every native minute."""
    for f, q in zip(manifest['files'], qa, strict=True):
        lo, hi = window(f['coverage'])
        require(q['rows'] == (hi-lo)//MINUTE and q['first_event_ms'] == lo
                and q['last_event_ms'] == hi-MINUTE
                and all(t in tables['price_1m'] for t in range(lo, hi, MINUTE)),
                'FULL_NATIVE_MINUTE_COVERAGE_REQUIRED')
