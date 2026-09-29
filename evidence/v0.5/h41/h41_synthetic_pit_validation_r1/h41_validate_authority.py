import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

IMPL = 'a3235fbc39667ca2a624faebd3cf9ee8a4b442de'
DOCS = 'c44ffb6af2930c88a2b013ffb963bd06317032ff'
ACCEPT = 'ae135999e5928eae4b7741ce17ddecc4514f24fc'
PROD = {
'src/btc_quant_agent/h41/__init__.py':'ad1d3480f811965455dd3587e69361133339c375',
'src/btc_quant_agent/h41/authority.py':'ac8889faba3dd9bf7da6be452f0d93472c7cce58',
'src/btc_quant_agent/h41/frozen_bindings.py':'80499b954e80680f5c9afb90522f7e3ab593aa9d',
'src/btc_quant_agent/h41/inference.py':'13be97f375e860463de387a46425c15e21a36e37',
'src/btc_quant_agent/h41/outcomes.py':'74b2704765a5880d3172b922792990efa881887f',
'src/btc_quant_agent/h41/science.py':'d3ce28f6e479c8d4d911d4075c78c5bfbbab2b6a',
'src/btc_quant_agent/h41/selection.py':'422c112b353e5f1ddfc50533d88244246203ee77',
'src/btc_quant_agent/h41/source.py':'739603b1a7f123cf61eeb7c4aed89a2c6c8ec294',
'src/btc_quant_agent/h41/testability.py':'d1432a9bb418527dd0ccb774cd822b9295b9f999',
}
TEST = {
'tests/h41/r2_reference.py':'c8c727a379a5c80c8de5b7f0ec7f387c27b11f2e',
'tests/h41/test_authority_and_signals.py':'b83d7126e6391976d59e40bbafb5ce88f094d712',
'tests/h41/test_inference_and_ranking.py':'b4e0f84adb80c20bf87689873ca51b98ff1ab890',
'tests/h41/test_source_and_outcomes.py':'e50ab8c93cd2f9548f8d1c9a4b260a9150603e65',
}
def git(*args):
    return subprocess.check_output(['git',*args])
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
actual = {p:git('rev-parse',f'{IMPL}:{p}').decode().strip() for p in PROD|TEST}
blob_mismatch = {p:{'expected':exp,'actual':actual[p]} for p,exp in (PROD|TEST).items() if actual[p]!=exp}
docs=json.loads(git('show',f'{DOCS}:evidence/v0.5/h41/V0.5.1_H41_FROZEN_PROTOCOL_AUTHORITY_R1.json'))
accept=json.loads(git('show',f'{ACCEPT}:evidence/v0.5/h41/V0.5.1_H41_SOURCE_AUTHORITY_CONTROLLER_ACCEPTANCE.json'))
source=git('show',f'{IMPL}:src/btc_quant_agent/h41/frozen_bindings.py').decode()
assign=next(node for node in ast.parse(source).body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FROZEN_BINDINGS_JSON' for t in node.targets))
pack=json.loads(ast.literal_eval(assign.value))
child={'candidate_ledger_hash':digest(docs['frozen_candidate_universe']['candidates'])}
for key,val in docs['frozen_contracts'].items(): child[f'{key}_hash']=digest(val)
root=digest(child)
root_expected=docs['authority_hashes']['frozen_h41_semantic_root_hash']
fields=['candidate_ledger_hash','event_pit_contract_hash','endpoint_contract_hash','inference_contract_hash','source_requirements_hash','validation_lifecycle_contract_hash']
contract_comparison={key:{'recomputed':child[key],'docs':docs['authority_hashes'][key],'package':pack['authority_hashes'][key]} for key in fields}
ledger_docs=docs['frozen_candidate_universe']['candidates']
ledger_package=pack['candidates']
counts=Counter(row['family'] for row in ledger_docs)
source_accept=accept['canonical_source_authority']
source_comparison={
'joint_root':{'docs':source_accept['joint_source_authority_root'],'package':pack['source']['joint_root']},
'projection_hashes':{'docs':source_accept['canonical_projection_hashes'],'package':pack['source']['projection_hashes']},
'receipt_hashes':{'docs':source_accept['canonical_receipt_hashes'],'package':pack['source']['receipt_hashes']},
'archive_set_hashes':{'docs':source_accept['source_archive_set_hashes'],'package':pack['source']['archive_set_hashes']},
'membership_hashes':{'docs':source_accept['timestamp_membership_hashes'],'package':pack['source']['membership_hashes']},
}
result={'implementation_sha':IMPL,'blob_hashes':actual,'blob_mismatch':blob_mismatch,'contract_comparison':contract_comparison,'recomputed_semantic_root':root,'docs_semantic_root':root_expected,'package_semantic_root':pack['authority_hashes']['frozen_h41_semantic_root_hash'],'ledger_exact_ordered':ledger_docs==ledger_package,'candidate_count':len(ledger_docs),'family_counts':dict(counts),'horizons':sorted({row['horizon_hours'] for row in ledger_docs}),'source_comparison':source_comparison,'authority_exact':not blob_mismatch and all(len(set(v.values()))==1 for v in contract_comparison.values()) and root==root_expected==pack['authority_hashes']['frozen_h41_semantic_root_hash'] and ledger_docs==ledger_package and all(v['docs']==v['package'] for v in source_comparison.values())}
Path('/tmp/h41_authority_result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('blob_mismatch','recomputed_semantic_root','ledger_exact_ordered','candidate_count','family_counts','horizons','authority_exact')},sort_keys=True))
