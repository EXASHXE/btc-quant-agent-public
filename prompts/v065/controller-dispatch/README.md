# quant v0.6.5 — Controller dispatch prompts (docs/engineering)

Owner directive (2026-10-18): **new prompts authored by the Controller are published in this existing GitHub documentation branch, not stored as local task-prompt files.** This branch remains a separate documentation history and is NOT the `v0.6.5` engineering integration branch. No pull request or merge is implied. Independent source rights, testnet, Alpha, live trading and protected data gates remain unchanged.

These seven historical dispatch artifacts were byte-for-byte preserved from the previously used local controller control directories, then made available here. Their revision numbers and earlier task states are historical; a link to a Prompt does not authorize repeating an already completed task or starting a collector. Review/decision receipts and data remain in their original custody; **no market payload or account secrets were uploaded**.

| Prompt | Original SHA-256 | Bytes | Role |
|---|---|---:|---|
| [`LOCAL_AGENT_PREFLIGHT_PROMPT.md`](LOCAL_AGENT_PREFLIGHT_PROMPT.md) | `8cd92458485e3877d57f026401f208455bf0d33e5719cac098c91c8aa653a718` | 3911 | historical |
| [`ACTIVE_DOWNLOAD_CUTOVER_TASK_R1.md`](ACTIVE_DOWNLOAD_CUTOVER_TASK_R1.md) | `2799a9e89a5244e698bb7e33cc0821f133370f691d1f4186dd06430376ef0357` | 8701 | historical |
| [`ACTIVE_DOWNLOAD_CUTOVER_TASK_R2.md`](ACTIVE_DOWNLOAD_CUTOVER_TASK_R2.md) | `8daa22ccd237b58192e588fb529881e3b60690ec176fa74e9af2689b7167a82a` | 8782 | historical |
| [`ACTIVE_DOWNLOAD_CUTOVER_TASK_R3.md`](ACTIVE_DOWNLOAD_CUTOVER_TASK_R3.md) | `dcc897027b11e913ae9d27d767eaeb73ea35bf690218fb420a6fcb39f8a1d0e3` | 8961 | historical |
| [`ACTIVE_DATA_CUTOVER_LOCAL_AGENT_PROMPT_R2.md`](ACTIVE_DATA_CUTOVER_LOCAL_AGENT_PROMPT_R2.md) | `dd3279019c12b387fe1f4e7d37d7e6577caf321b78206ab7801d6e42a2053e37` | 6492 | historical |
| [`MICROSTRUCTURE_GRACEFUL_STOP_LOCAL_AGENT_PROMPT_R3.md`](MICROSTRUCTURE_GRACEFUL_STOP_LOCAL_AGENT_PROMPT_R3.md) | `e9324148ce648fd933eeb84f0b37f974218f4c96b25aafe214f8e00e13029f0d` | 5191 | completed synthetic R3 |
| [`MICROSTRUCTURE_GRACEFUL_STOP_1A_REVIEW_PROMPT_R1.md`](MICROSTRUCTURE_GRACEFUL_STOP_1A_REVIEW_PROMPT_R1.md) | `accf43d3265ed84b9c78bc5d0c6f9901c7b3dca18f4830cb434b1a361d931b3d` | 4953 | current 1-A handoff pending |

### Current independent review

[Microstructure R3 synthetic non-kill policy — 1-A independent challenge](MICROSTRUCTURE_GRACEFUL_STOP_1A_REVIEW_PROMPT_R1.md). This requires only an offline/read-only consequential review of the previously frozen R3 synthetic report. No production drop-in install, real service stop, active data cutover or new SOURCE_QA subscription is approved by this dispatch.

For future tasks, Controller should upload new/updated immutable prompts here, freeze exact commit SHA + blob and give agents the GitHub blob URL. Prompt files need not be copied to the host; agent may fetch via permitted GitHub reading. A report may cite the frozen prompt GitHub link and its exact SHA-256.
