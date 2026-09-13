# Codex Agent Routing Configuration — Apply Task

Repository: `EXASHXE/btc-quant-agent`

Target branch: `v0.4`

This is a configuration-application task, not a design task.

The policy and role contents have already been defined. Do not redesign the model-routing strategy, rewrite the instructions, or invent additional agents unless required solely for compatibility with the installed Codex version.

## Source templates

Use the following repository templates as the authoritative content:

- AGENTS.md template:
  - path: `prompts/v0.4/codex_agent_config/templates/AGENTS.md`
  - GitHub: https://github.com/EXASHXE/btc-quant-agent/blob/v0.4/prompts/v0.4/codex_agent_config/templates/AGENTS.md

- project Codex config template:
  - path: `prompts/v0.4/codex_agent_config/templates/config.toml`
  - GitHub: https://github.com/EXASHXE/btc-quant-agent/blob/v0.4/prompts/v0.4/codex_agent_config/templates/config.toml

- mechanical agent template:
  - path: `prompts/v0.4/codex_agent_config/templates/mechanical.toml`
  - GitHub: https://github.com/EXASHXE/btc-quant-agent/blob/v0.4/prompts/v0.4/codex_agent_config/templates/mechanical.toml

- explorer agent template:
  - path: `prompts/v0.4/codex_agent_config/templates/explorer.toml`
  - GitHub: https://github.com/EXASHXE/btc-quant-agent/blob/v0.4/prompts/v0.4/codex_agent_config/templates/explorer.toml

- reviewer agent template:
  - path: `prompts/v0.4/codex_agent_config/templates/reviewer.toml`
  - GitHub: https://github.com/EXASHXE/btc-quant-agent/blob/v0.4/prompts/v0.4/codex_agent_config/templates/reviewer.toml

## Target files

Install/merge the templates into:

- `<repo>/AGENTS.md`
- `<repo>/.codex/config.toml`
- `<repo>/.codex/agents/mechanical.toml`
- `<repo>/.codex/agents/explorer.toml`
- `<repo>/.codex/agents/reviewer.toml`

## 1. Inspect before modifying

First determine:

- current Codex CLI/Desktop version;
- actual `$CODEX_HOME` / `~/.codex` path;
- whether CLI and Desktop use the same effective config;
- existing global `config.toml`;
- existing repo-local `AGENTS.md`, `AGENTS.override.md`, `.codex/config.toml`, `.codex/agents/*`;
- uncommitted repository changes.

Do not overwrite unrelated configuration.

Do not use `git reset`, `git clean`, or other destructive operations.

## 2. AGENTS.md

If root `AGENTS.md` does not exist, copy the authoritative template content.

If it already exists:

- preserve existing project-specific rules that remain necessary;
- merge the supplied routing/context policy;
- remove obvious duplicate rules only;
- do not materially change the supplied policy;
- keep the result concise rather than turning it into a project encyclopedia.

## 3. .codex/config.toml

Install the supplied project-local config.

If a repo-local `.codex/config.toml` already exists, merge instead of replacing it.

Preserve unrelated valid settings.

Do NOT add a root-level `model` or root-level `model_reasoning_effort` simply to implement this task. The model manually selected for the root/session must remain authoritative.

The intended routing semantics are:

- generic subagent default: `gpt-5.6-terra` / `low`;
- maximum concurrent agent threads: 3;
- `mechanical` named role;
- `explorer` named role;
- `reviewer` named role.

## 4. Role configs

Install the three supplied role templates without redesigning their responsibilities.

Intended effective routing:

- `mechanical` -> `gpt-5.6-luna`, low reasoning;
- `explorer` -> `gpt-5.6-terra`, low reasoning, read-only;
- `reviewer` -> `gpt-5.6-sol`, high reasoning, read-only.

## 5. Installed-version compatibility

Before finalizing, verify the actual Codex configuration schema accepted by the installed build.

The supplied templates represent the required semantics, but Codex configuration syntax may differ by installed version.

You may make only the minimum syntax/path adaptation required for the installed build, while preserving the intended semantics.

Examples of things to verify rather than assume:

- `[agents]` namespace and `enabled` support;
- `default_subagent_model`;
- `default_subagent_reasoning_effort`;
- `max_concurrent_threads_per_session`;
- named-role syntax;
- `config_file` path resolution;
- role-level `model`;
- `model_reasoning_effort`;
- `model_verbosity`;
- `developer_instructions`;
- `sandbox_mode`.

If relative `config_file` paths are not accepted by the installed build, convert only those paths to the correct form required by the installed version.

Do not replace the routing design with a different one.

## 6. Luna compatibility rule

The preferred mechanical worker is:

`gpt-5.6-luna` / `low`.

Perform an actual minimal spawn/config smoke test where supported.

If the installed Codex build explicitly rejects Luna as a spawned subagent, or runtime evidence clearly shows the mechanical model override cannot work, the only permitted fallback is:

`mechanical -> gpt-5.6-terra / low`.

Do not fallback mechanical work to Sol.

Keep the mechanical developer instructions unchanged.

Report concrete evidence for any Luna fallback.

## 7. Parent-model behavior

Do not configure this project in a way that forces a specific root model.

Expected behavior:

- if the user starts the session with Astra, the parent remains Astra;
- if the user starts the session with Sol, the parent remains Sol;
- named subagents may use the cheaper configured models;
- `AGENTS.md` is routing/execution policy, not a mechanism that mutates the parent model in place.

## 8. Validation

Validate through Codex itself where possible, not merely with a generic TOML parser.

Confirm:

- config loads without parse/unknown-field errors;
- root `AGENTS.md` is recognized;
- `mechanical` role is discoverable;
- `explorer` role is discoverable;
- `reviewer` role is discoverable.

Run minimal non-destructive smoke tests:

### mechanical
Spawn the role on a trivial probe that does not create business-code changes.

### explorer
Ask it to locate one existing repository symbol and return concise read-only evidence.

### reviewer
Ask it to review a very small existing code/diff fragment without modifying files.

If the product exposes the spawned model/reasoning level, record it.

If runtime model selection is not externally observable, report that distinction honestly:

- configuration accepted;
- role discovered;
- runtime model not externally proven.

## 9. Scope

This task must not modify:

- quant strategy logic;
- research logic;
- production application behavior;
- CI behavior;
- tests solely to accommodate this configuration.

Do not introduce third-party token-saving middleware or new orchestration frameworks.

Do not run the full business pytest suite merely for this configuration task unless an unexpected business-file modification occurs.

## 10. Git hygiene

Before finishing, inspect:

- `git status`
- `git diff --stat`
- relevant `git diff`

Preserve all unrelated user changes.

Do not commit or push unless explicitly instructed by the user in the execution session.

## 11. Final report

Report only:

1. Codex version;
2. effective Codex config path(s);
3. created/modified files;
4. whether the root parent remains user-selected;
5. generic subagent default model/reasoning;
6. mechanical actual model/reasoning;
7. explorer actual model/reasoning;
8. reviewer actual model/reasoning;
9. configured max concurrency;
10. config-load validation result;
11. role-discovery result;
12. smoke-test results;
13. whether Luna fallback was required;
14. any minimal installed-version compatibility adaptations;
15. `git diff --stat`.

Do not propose a replacement routing design.
