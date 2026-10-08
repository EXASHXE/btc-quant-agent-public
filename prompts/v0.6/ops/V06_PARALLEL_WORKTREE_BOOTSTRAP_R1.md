# v0.6 Local Parallel Worktrees Bootstrap R1 — Agent execution contract

**Task:** 为已派发且彼此独立的 **G1 Engineering Preview** 和 **G2 Strategy Discovery** 准备本地 Git worktree 工作目录，建立一个仅供审查的第三工作树。**本任务只初始化本地文件系统和 Git worktree，不修改业务代码，不开始 G1/G2 回测或执行，不读取任何 protected 数据。**

| 不可变字段 | 值 |
|---|---|
| TASK_ID | `V06_PARALLEL_LOCAL_WORKTREE_BOOTSTRAP_R1` |
| REPOSITORY | `EXASHXE/btc-quant-agent-public` |
| CONTROLLER_WORKSPACE_OVERRIDE_SHA | `595d0b87cdad43f924f1e0040b8d6b33ae241237` |
| 位置覆盖授权 | [WORKSPACE_OVERRIDE_AUTHORITY.json](https://github.com/EXASHXE/btc-quant-agent-public/blob/595d0b87cdad43f924f1e0040b8d6b33ae241237/evidence/v0.6/controller/B_LINE_V06_PARALLEL_WORKSPACE_OVERRIDE_AUTHORITY.json) |
| 项目源 checkout（**只读检查，不切换分支**） | `/root/workspace/project/rc2-tactical-successor` |
| 新工作区根目录 | `/root/workspace/project/quant-v0.6` |
| v0.6 code exact START_SHA | `d6500140f3141d179181f2360ad815b5bfe9c954` |
| G1 原 dispatch | `8f0ccb2dbbc0612e3218ea554309d123959118f7` |
| G2 原 dispatch | `0cc3d6e14d5c4e301c987b9e760fabb393e8141a` |
| G1 分支 | `feature/v06-bline-engineering-preview-r1` |
| G2 分支 | `feature/v06-bline-g2-strategy-discovery-r1` |
| Terminal | `WORKSPACE_BOOTSTRAP_READY` / `WORKSPACE_ALREADY_READY` / `WORKSPACE_BOOTSTRAP_BLOCKED` |

**授权优先级：** 此 `CONTROLLER_WORKSPACE_OVERRIDE_SHA` **仅覆盖原 G1/G2 Prompt 中的本地独立 worktree 位置**，不改变各自原始 `CONTROLLER_DISPATCH_SHA`、基线 SHA、策略/候选数量、保护样本、代码所有权、读写或执行授权、推送规则。旧目录位置仍为历史记录。严禁借助目录变更提升权限。

## 1. 本次创建的目录结构

```text
/root/workspace/project/
├── rc2-tactical-successor/                   # 现有仓库！不得 checkout/reset/clean/stash/覆盖
└── quant-v0.6/                               # 普通目录，不是新的仓库；不运行 git init
    ├── g1-engineering-preview/               # Git worktree: G1 feature branch
    ├── g2-strategy-discovery/                 # Git worktree: G2 feature branch
    ├── controller-review/                    # Git worktree: detached exact v0.6 baseline（只读惯例）
    ├── _artifacts/
    │   ├── g1/                              # 本地离线日志/临时结果，非 Git
    │   ├── g2/
    │   └── review/
    ├── _venvs/                               # 可选的各任务隔离虚拟环境（现在只建父目录）
    └── _meta/
        ├── WORKSPACE_LAYOUT.md               # 本地使用约定
        └── WORKSPACE_SETUP_RECEIPT.json      # 可复核、无敏感信息的初始化收据
```

**不创建第三个开发分支；不创建 G3/TESTNET/实盘工作树。** G1/G2 由不同 Agent 或不同会话分别在各自的 feature worktree 内开发，各自产生自己的 git index、未提交状态、日志和 venv。共享的只是 Git object store 与受控远端，不共享可写业务源代码树。

## 2. 先做严格只读预检，任何冲突先停

使用 shell/terminal 工具检查真实本地文件系统。开始前：

```bash
set -euo pipefail
ENTRY=/root/workspace/project/rc2-tactical-successor
ROOT=/root/workspace/project/quant-v0.6
BASE=d6500140f3141d179181f2360ad815b5bfe9c954
G1="$ROOT/g1-engineering-preview"
G2="$ROOT/g2-strategy-discovery"
REVIEW="$ROOT/controller-review"

test -d "$ENTRY" || { echo BLOCKED_ENTRY_NOT_FOUND; exit 2; }
test "$(git -C "$ENTRY" rev-parse --show-toplevel)" = "$ENTRY" || { echo BLOCKED_WRONG_ROOT; exit 2; }
git -C "$ENTRY" rev-parse HEAD
git -C "$ENTRY" branch --show-current
git -C "$ENTRY" status --porcelain=v1 --untracked-files=all
git -C "$ENTRY" worktree list --porcelain
# git remote -v 可在本地检查，但任何输出给用户前都要隐藏 URL 中的 token/userinfo
```

- 核对预设远端 fetch/push URL **确实** 属于 `EXASHXE/btc-quant-agent-public`。允许 SSH 和 HTTPS，但不得改写 remote URL，不得将代码推到私有或其他同名仓库；不确定 ⇒ `BLOCKED_REMOTE_IDENTITY`。
- 使用 `git ls-remote --heads <VERIFIED_REMOTE> v0.6 v0.6-docs` 核对真实远端 `v0.6` HEAD 为 `d6500140f3141d179181f2360ad815b5bfe9c954`；且 trusted docs 包含 `595d0b87cdad43f924f1e0040b8d6b33ae241237`，其中 JSON 的 G1/G2 branch/path 与本任务一致。只允许 **fetch** 需要的 refs/object，不允许 checkout ENTRY、pull/rebase、切换分支或修改其文件。
- **检查旧预定 worktree**：`/root/workspace/project/rc2-tactical-successor-v06-preview-r1` 与 `/root/workspace/project/rc2-tactical-successor-v06-g2-r1`。若任何一个已经存在，或旧/新 G1/G2 分支已关联别的工作树（哪怕它是干净的），**立即停止并报告** `BLOCKED_EXISTING_TASK_WORKTREE`，不能移动/删除/覆盖；另行协调进行安全迁移。正在运行的 Agent 或工作任务绝不可被抢占。
- 检查根目录 `$ROOT`。若 `$ROOT` 自身是 Git checkout、挂载敏感路径或其 `g1/g2/controller-review` 子路径已经包含用户文件/未知 Git 工作树，停止；**不得复用非空未知目录或递归删除**。如果已有完全匹配的三个 worktree，则只读核验并返回 `WORKSPACE_ALREADY_READY`，不重新建树。
- 检查 G1/G2 本地分支是否存在、是否关联其他 worktree、远端是否已有未接收提交。不能假设分支不存在，也不能 reset 现有分支。在任何冲突下停机，不要擅自新增同名分支或把已完成的工作回退到旧 START_SHA。
- 不要运行 `git worktree prune`、`git worktree remove`、`git clean`、`git reset --hard`、`git stash`、`git checkout -f`、`rm -rf`、`push --force`，也不要修改 global Git config。**只读预检发现 dirty 文件不是授权删除这些文件的理由。**

只有三个目标工作树的位置、分支和其他 Agent 占用均无冲突，且权限/容量可用，才进入创建阶段。尽量全局预检后再创建，避免中途半成品。

## 3. 创建步骤——仅在新路径全部可用、分支尚未使用时

使用已经核验的 `ENTRY` Git 仓库（共享 .git objects），无需另一个 clone：

```bash
# 仅在上节所有校验通过后执行，并使用真实 verified remote 名称
mkdir -p "$ROOT"
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-engineering-preview-r1 \
  "$G1" "$BASE"
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-g2-strategy-discovery-r1 \
  "$G2" "$BASE"
git -C "$ENTRY" worktree add --detach "$REVIEW" "$BASE"
mkdir -p "$ROOT/_artifacts/g1" "$ROOT/_artifacts/g2" \
  "$ROOT/_artifacts/review" "$ROOT/_meta" "$ROOT/_venvs"
```

上面命令是**参考执行序列**，不是跳过前置校验的许可。若 Agent 发现目标路径/分支已存在，不能盲目执行 `-b`；也不能以 `-B`、`--force` 替代。如果执行到一半失败，保留已创建目录，不清理破坏，返回 `PARTIAL_SETUP_REQUIRES_REVIEW` 和完整现状，后续只允许显式恢复。

`controller-review` 的 Git HEAD 为 **detached** `d6500140f3141d179181f2360ad815b5bfe9c954`，供只读 diff、lint、参考，不允许从这里 commit/push/构造发布对象。未来进行集成时需 Controller 另行开任务分支及授权；不要自行使用 `v0.6` 当前分支开发。

**资源隔离：** 不要共用同一 `.venv`、pytest 缓存、SQLite 状态数据库、下载缓存或 replay fixture 目录；建议将各任务 Python 环境分别放在 `$ROOT/_venvs/g1` 与 `$ROOT/_venvs/g2`，各自日志放在 `_artifacts/g1`、`_artifacts/g2`；本次只建立父目录，不安装依赖、不下载网络数据。

## 4. 创建后核验与本地收据

核验每个工作树路径真实解析位置、关联分支/HEAD 与 Git repository root：

```bash
git -C "$ENTRY" worktree list --porcelain
test "$(git -C "$G1" rev-parse HEAD)" = "$BASE"
test "$(git -C "$G2" rev-parse HEAD)" = "$BASE"
test "$(git -C "$REVIEW" rev-parse HEAD)" = "$BASE"
test "$(git -C "$G1" branch --show-current)" = feature/v06-bline-engineering-preview-r1
test "$(git -C "$G2" branch --show-current)" = feature/v06-bline-g2-strategy-discovery-r1
test -z "$(git -C "$REVIEW" branch --show-current)"
git -C "$G1" status --porcelain=v1
git -C "$G2" status --porcelain=v1
git -C "$REVIEW" status --porcelain=v1
```

同时比对 **原 ENTRY checkout** 的分支、HEAD、tracked/untracked 计数与预检收据，必须完全一致；不要把输出中的用户文件名、Token、可能敏感的目录内容写进项目报告。若原有 dirty 文件存在，只应记录数量并确认未改动，不允许隐式清理。

写入 `$ROOT/_meta/WORKSPACE_LAYOUT.md`：三处 worktree 路径、G1/G2 所属任务/branch、共享仓库与相互隔离规则、两份原 dispatch 链接、此 override SHA。写入 `$ROOT/_meta/WORKSPACE_SETUP_RECEIPT.json`：任务 ID、时区感知时间、代码基线/远端身份（URL 去除 credentials）、pre/post 原 ENTRY branch/HEAD/dirty-untracked count、每个新 worktree HEAD/branch/clean 状态、检查命令结果、旧目录占用检查、Protected reads=0、Exchange writes=0。不记录账号/秘钥/绝对敏感文件路径内容。

**不需要推送 GitHub：本任务仅创建本地工作目录与根目录内的本地收据，没有授权 Git 内容变更。** 旧的“任务完成主动 push”规则继续对 **G1/G2 后续代码、测试、项目文档变更** 生效：在各自分支通过检查后自主 `commit → push → 核验远端 SHA`；不要误把工作区初始化当作要空提交或直接 push v0.6。

## 5. 严格任务边界与最终答复

- 此初始化任务**不得**运行 G1、G2 的策略/工程实现、Python pytest、大规模文件扫描、回测、外部 OpenAI/Feishu 访问、Binance API、TESTNET/实盘，也不得读取 RC2 protected target/h40/h41 outcomes/任何用户凭据。
- 不改变 A-line 和 CI 文件，G1/G2 原工作分支、Controller SHA、冻结策略预算不变；只是 worktree 实际目录由旧路径覆盖为 `$ROOT/g1-engineering-preview` 和 `$ROOT/g2-strategy-discovery`。
- 两个 Agent 后续每次启动必须分别 `cd "$G1"` / `cd "$G2"`；不要在 ENTRY 运行会修改文件的命令。不得跨任务编辑另一个工作树。

成功后返回以下结构，不要只写“已完成”：

```yaml
task_id: V06_PARALLEL_LOCAL_WORKTREE_BOOTSTRAP_R1
decision: WORKSPACE_BOOTSTRAP_READY | WORKSPACE_ALREADY_READY | WORKSPACE_BOOTSTRAP_BLOCKED
controller_workspace_override_sha: 595d0b87cdad43f924f1e0040b8d6b33ae241237
entry_checkout: /root/workspace/project/rc2-tactical-successor
entry_branch_head_before: <branch + SHA>
entry_branch_head_after: <branch + SHA>
entry_dirty_untracked_counts_unchanged: true | false
workspace_root: /root/workspace/project/quant-v0.6
g1_worktree: /root/workspace/project/quant-v0.6/g1-engineering-preview
g1_branch: feature/v06-bline-engineering-preview-r1
g1_head: <actual SHA>
g2_worktree: /root/workspace/project/quant-v0.6/g2-strategy-discovery
g2_branch: feature/v06-bline-g2-strategy-discovery-r1
g2_head: <actual SHA>
controller_review_worktree: /root/workspace/project/quant-v0.6/controller-review
review_head_mode: DETACHED
workspace_setup_receipt: /root/workspace/project/quant-v0.6/_meta/WORKSPACE_SETUP_RECEIPT.json
remote_verified: true | false
existing_old_task_worktree_collision: false | true
protected_reads: 0
exchange_writes: 0
github_push_required_for_this_local_only_task: false
blocker: NONE | <exact collision or mismatch>
next_action: G1/G2_EXECUTORS_RUN_IN_THEIR_RESPECTIVE_NEW_WORKTREES
```

**Do not claim verified creation without actual terminal results.** If the machine is inaccessible, say so and only return a reproducible plan; no remote GitHub action can create this local folder.
