# Restore original refs — procedure and actual proof

Before any remote deletion, V065-M1 created a nonpublic local Git bundle from **all fetched public-repository refs**, 220 branch heads / 229 stored refs (bundle lists 230 including HEAD). File: `pre-v065-m1-allrefs.bundle`, 39,800,031 bytes. SHA-256:

`1d3c6b5b869ca855fff5e983ba7007371a5c283f164f40c634f962da40b52707`

Local backup directory: `/workspace/scratch/d35900fca7ef/m1-backup/` (mode 0700). The bundle is not committed or uploaded to this public repository. Scratch persistence is not guaranteed: preserve the verified bundle privately before ending the workspace lifetime. Original Git object history is also preserved remotely wherever the final ledger proves ancestry.

Actual checks: `git bundle verify` in a new empty bare repository PASSED with complete history / no prerequisites. An independent clone of the bundle recovered all 220 original branch heads; connectivity fsck returned success. Dangling test PR-merge commits are expected because an ordinary bundle clone materializes branch heads rather than GitHub's synthetic pull refs. In a separate **local-only bare rollback target**, `git push <local-target> 803a4173717ace9c03ff97051b7696210e183bef:refs/heads/feature/v06-r11-d2-binance-core-pilot-r1` succeeded; rev-parse returned the exact original D2 SHA. No extra public branch was created for this test.

For an explicitly authorized restoration after a real deletion:

```bash
git clone --bare /private/backup/pre-v065-m1-allrefs.bundle restore.git
git -C restore.git cat-file -e <original-40-char-sha>^{commit}
# First verify old ref is vacant, current permissions and protection rules.
git -C restore.git push https://github.com/EXASHXE/btc-quant-agent-public.git <original-40-char-sha>:refs/heads/<exact-original-name>
```

Use the exact ledger entry; no wildcard, reset or force push. A later moved ref is never overwritten. A local rollback test proves object recovery and Git ref recreation, **not authenticated remote write permission**. This cloud Git client currently has no authenticated push channel; required protection details also return 403. No deletion is eligible until those runbook gates are independently satisfied. A SHA list alone is not the backup; do not claim branch-list reduction shrinks object storage.
