# PR / CI / Sonar Reader Skill Example

## 示例用户请求

```text
请复审 PR #43，检查 GitHub PR 状态、changed files、checks、SonarCloud，
并按主脑复审格式输出结论。不要 merge，不要 approve，不要 deploy。
```

或：

```text
repo: 2449673842/codex-auto-delivery-platform
pr_number: 43
expected_head: 6064473f6f8abcf8ddbe945a6bb83936eeba1d8a
expected_base: b5dfffc9ef7bfe44e1e8b616bcaf5e6ff3f524c4
```

## 示例 Tool 调用顺序

### 1. 读取 PR metadata

```bash
gh pr view 43 --repo 2449673842/codex-auto-delivery-platform \
  --json number,url,state,mergeable,headRefOid,baseRefOid,changedFiles,title,body
```

检查：

- `state` 是否为 `OPEN`
- `mergeable` 是否为 `MERGEABLE`
- `headRefOid` 是否等于用户给出的 expected_head
- `baseRefOid` 是否等于用户给出的 expected_base
- `changedFiles` 是否与 PR body 一致

### 2. 读取 changed files

```bash
gh pr diff 43 --repo 2449673842/codex-auto-delivery-platform --name-only
```

检查：

- 文件数量是否等于 `changedFiles`
- 是否存在超出范围的代码文件
- 如果 PR 声明只改文档，必须确认所有文件在 `docs/` 下

### 3. 读取 checks

```bash
gh pr checks 43 --repo 2449673842/codex-auto-delivery-platform
```

如果 `gh pr checks` 输出不完整，再读取 check-runs：

```bash
gh api repos/2449673842/codex-auto-delivery-platform/commits/<head_sha>/check-runs
```

检查：

- 是否所有必需 checks 完成
- 是否有 failure / cancelled / timed_out
- SonarCloud Code Analysis 是否 success

### 4. 读取 Sonar summary

优先解析 check-run output：

```bash
gh api repos/2449673842/codex-auto-delivery-platform/commits/<head_sha>/check-runs \
  --jq '.check_runs[] | select(.name=="SonarCloud Code Analysis") | {status, conclusion, output}'
```

可选读取 SonarCloud measures：

```bash
curl "https://sonarcloud.io/api/measures/component?component=2449673842_codex-auto-delivery-platform&pullRequest=43&metricKeys=new_duplicated_lines_density,new_violations,security_hotspots"
```

检查：

- Quality Gate 是否 Passed
- Security Hotspots 是否 0
- Duplication on New Code 是否在阈值内
- New Issues 是否 0

### 5. 检查 PR body

检查 PR body 是否中文，并包含：

- PR URL
- PR 编号
- head commit
- base commit
- changed files
- 验证结果
- SonarCloud
- 安全边界

如果 PR body 与 GitHub 实际结果不一致，应输出 `needs_update` 或 `blocked`。

## 示例复审输出

```text
复审结论：approved

PR:
- URL: https://github.com/2449673842/codex-auto-delivery-platform/pull/43
- 编号: #43
- state: OPEN
- mergeable: MERGEABLE
- head: 6064473f6f8abcf8ddbe945a6bb83936eeba1d8a
- base: b5dfffc9ef7bfe44e1e8b616bcaf5e6ff3f524c4
- changed files: 3

changed files:
- docs/mcp/mcp-bridge-quickstart.md
- docs/mcp/external-ai-handoff-example.md
- docs/strategy/skill-vs-platform-evaluation.md

验证结果：
- targeted backend pytest: 未运行，合理，只改文档
- full backend pytest: 未运行，合理，只改文档
- compileall: 未运行，合理，只改文档
- npm build: 未运行，合理，未改前端
- frontend tests: 未运行，合理，未改前端
- smoke test: 文档内容检查通过

SonarCloud：
- Quality Gate: Passed
- Security Hotspots: 0
- Duplication on New Code: 0.0%
- New Issues: 0

范围检查：
- changed files 与 GitHub 实际一致
- 均为 docs 文件
- 未发现 out-of-scope 修改

安全边界：
- 未新增 execute
- 未调用 provider
- 未写库
- 未创建 PR / CI / Sonar / Deploy
- 未自动 approve / merge
- 未读取 .env / secret_ref
- 未访问 Project.root_path 做真实修改

主脑建议：
- 可以合入 master
```

## blocked / missing 信息时如何回答

### Sonar pending

```text
复审结论：needs_update

原因：
- SonarCloud Code Analysis 尚未完成，无法确认 Quality Gate / Hotspots / Duplication / New Issues。

建议：
- 等待 SonarCloud 完成后重新复审。
- 不要在 Sonar pending 时批准合入。
```

### changed files 不一致

```text
复审结论：blocked

原因：
- PR body 声明 changed files=3，但 GitHub 实际 changedFiles=4。
- PR body 与 GitHub 现实不一致，按规则阻塞。

建议：
- 更新 PR body changed files 数量和文件列表。
- 重新确认是否存在 out-of-scope 修改。
```

### Sonar failed

```text
复审结论：blocked

原因：
- SonarCloud Quality Gate failed。
- Duplication on New Code 超过阈值。

建议：
- 修复 SonarCloud 报告的问题。
- 推送新 head 后重新复审。
```

### 缺少验证结果

```text
复审结论：needs_update

原因：
- PR body 未说明 targeted backend pytest / full backend pytest / npm build / frontend tests。
- 如果只改文档，应明确写“未运行，合理，只改文档”。

建议：
- 回填验证结果或跳过理由。
```

## 什么时候建议转平台化

如果 skill 使用中出现以下高频需求，说明可以考虑平台化：

- 每次复审结果都需要长期保存
- 需要把 PR / CI / Sonar 结果挂到 Task Timeline
- 需要跨多个 PR 比较 Sonar / CI 趋势
- 需要 Evidence Board 展示 PR 证据
- 需要把复审报告保存为 TaskArtifact
- 需要外部 AI 通过 MCP 读取历史 PR 复审记录

如果只是“读取当前 PR 并输出一次复审报告”，skill 足够，不建议做平台 S19。
