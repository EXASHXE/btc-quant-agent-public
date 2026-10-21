"""Read separately issued Controller scope, registry and provenance using pinned bytes.

Only an independently reviewed deployment may install an anchor. Hashes authenticate
the installed bytes, not publisher signatures or the human issuer's identity.
"""

import hashlib
from pathlib import Path
from types import MappingProxyType

from ..exploratory_public_raw_v1 import require
from ..exploratory_public_raw_v1.contract import keys
from ..exploratory_public_raw_v1.safeio import load, path, read_exact

# No environment, CLI, experiment, V1 fixture or mutable file can install an anchor.
# Shape: {id: {path, sha256, accepted_by, authenticity_reference}}.
DEPLOYMENT_ANCHORS = MappingProxyType({})
CODE_ROOT = Path(__file__).resolve().parents[3]


def document(p, sha):
    from ..exploratory_public_raw_v1.safeio import hash_value
    hash_value(sha)
    return load(read_exact(path(p), sha, cap=4 * 1024 * 1024))


def resolve(registry_id):
    require(registry_id in DEPLOYMENT_ANCHORS, 'CONTROLLER_DEPLOYMENT_NOT_INSTALLED')
    anchor = dict(DEPLOYMENT_ANCHORS[registry_id])
    keys(anchor, 'path sha256 accepted_by authenticity_reference')
    require(anchor['accepted_by'] and anchor['authenticity_reference'], 'AUTHENTICITY_REQUIRED')
    require(not path(anchor['path']).is_relative_to(CODE_ROOT), 'DEPLOYMENT_IN_CODE_ROOT')
    d = document(anchor['path'], anchor['sha256'])
    keys(d, 'schema experiment_root scope_path scope_sha256 provenance_path provenance_sha256 '
         'source_proof_path source_proof_sha256')
    require(d['schema'] == 'controller-public-raw-deployment.v2', 'DEPLOYMENT_SCHEMA')
    experiment = path(d['experiment_root'])
    require(experiment != Path('/'), 'EXPERIMENT_ROOT')
    for name in ('scope_path', 'provenance_path'):
        p = path(d[name])
        require(not p.is_relative_to(CODE_ROOT) and not p.is_relative_to(experiment),
                'ACCEPTANCE_NOT_INDEPENDENT')
    require(not path(anchor['path']).is_relative_to(experiment), 'ACCEPTANCE_NOT_INDEPENDENT')
    require(len({anchor['path'], d['scope_path'], d['provenance_path'],
                 d['source_proof_path']}) == 4, 'DISTINCT_TRUST_DOCUMENTS_REQUIRED')
    a = document(d['scope_path'], d['scope_sha256'])
    p = document(d['provenance_path'], d['provenance_sha256'])
    keys(p, 'schema issuing_role state accepted_by authenticity_reference scope_sha256 '
         'source_proof_sha256')
    require(p['schema'] == 'controller-public-raw-provenance.v2'
            and p['issuing_role'] == 'Controller B' and p['state'] == 'ACCEPTED',
            'INDEPENDENT_CONTROLLER_PROVENANCE_REQUIRED')
    require(a['accepted_by'] == p['accepted_by'] == anchor['accepted_by']
            and a['authenticity_reference'] == p['authenticity_reference']
            == anchor['authenticity_reference'], 'PROVENANCE_IDENTITY')
    require(a['state'] == 'ACCEPTED' and p['scope_sha256'] == d['scope_sha256']
            and p['source_proof_sha256'] == d['source_proof_sha256'], 'PROVENANCE_BINDING')
    for value in (a['registration_path'], a['manifest_path'], a['output_dir'],
                  d['source_proof_path']):
        require(path(value).is_relative_to(experiment) and path(value) != experiment,
                'EXPERIMENT_ROOT')
    for root in a['roots'].values():
        for value in (anchor['path'], d['scope_path'], d['provenance_path']):
            require(not path(value).is_relative_to(path(root['path'])),
                    'ACCEPTANCE_NOT_INDEPENDENT')
    proof = document(d['source_proof_path'], d['source_proof_sha256'])
    pin = {'path': d['scope_path'], 'sha256': d['scope_sha256'],
           'accepted_by': anchor['accepted_by'],
           'authenticity_reference': anchor['authenticity_reference']}
    audit = {'anchor': anchor, 'deployment': d, 'provenance': p,
             'source_proof_sha256': d['source_proof_sha256'],
             'scope_file_sha256': hashlib.sha256(read_exact(
                 path(d['scope_path']), d['scope_sha256'])).hexdigest()}
    return a, pin, proof, audit
