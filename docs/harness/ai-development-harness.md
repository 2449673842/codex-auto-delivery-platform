# AI Development Harness

> AI agent 开发工作流说明 — 用于 AI1 / Codex / 主脑之间的协同

---

## 1. 接任务

1. 主脑下发任务描述
2. AI1 确认理解：
   - 任务目标
   - 允许修改的文件
   - 禁止修改的范围
   - 安全边界约束
   - 验证要求
3. 如不确定，立即停止并请求主脑澄清

## 2. 开分支

```bash
# 确保本地 master 最新
git checkout master
git pull origin master

# 根据任务类型选择分支名
git checkout -b feature/<name>   # 新功能
git checkout -b fix/<name>        # 修复
git checkout -b test/<name>       # 测试
git checkout -b docs/<name>       # 文档
```

### 分支原则

- 从最新 master 开分支
- 一次任务一个分支
- 分支名简短且有语义
- 不直接在 master 上修改

## 3. 实施变更

### 编码前

1. 阅读相关文件理解代码规范
2. 检查已有测试风格
3. 如有较大功能，等待主脑 Reference Brief

### 编码中

- 遵循项目代码风格
- 不做越界修改
- 不突破安全边界
- 不复制外部受版权保护的代码
- 如需使用外部库，先检查是否已存在于项目中

### 编码后

1. 运行 `python -m compileall backend/app` — 确认无语法错误
2. 运行 `python -m pytest backend/tests/ -v --rootdir backend` — 确认无回归
3. 如涉及前端：`cd frontend && npx vite build`
4. 如涉及 UI：`cd frontend && npx playwright test`

## 4. 提交 PR

### Commit

```bash
git add <files>
git commit -m "type: short description"
```

- commit message 用英文
- 首行小写，不超过 72 字符
- 空行后写详细说明（可选）

### Push

```bash
git push origin <branch-name>
```

### Create PR

使用 GitHub CLI 或在 GitHub 上创建：

```bash
gh pr create --base master --head <branch> --title "<title>" --body "<body>"
```

## 5. 写 PR Body

### 必须字段

| 字段 | 说明 |
|------|------|
| PR URL | 创建后填写 |
| PR number | 创建后填写 |
| head commit | 完整 SHA（40 字符），不可用短 hash |
| base commit | master 当前 commit |
| changed files | 数量 + 列表，必须与 GitHub 一致 |
| pytest | 完整结果（如 `283 passed, 0 failed`） |
| compileall | 通过 / 未运行 |
| npm build | 通过 / 未运行 / 无前端变更 |
| Playwright | 通过 / 未运行 / 无 UI 变更 |
| SonarCloud | Passed / Failed / 待 CI |
| Security Hotspots | 数字 |
| Duplication | 百分比 |
| DB migration? | 有 / 无 |
| Frontend changes? | 有 / 无 |
| Backend changes? | 有 / 无 |
| New real GitHub/CI/Sonar/Deploy? | 必须 "无" 除非明确规划 |
| Project.root_path? | 必须 "否" |
| shell/subprocess? | 必须 "否" |
| secret_ref? | 必须 "否" |
| Safety self-check | 逐项确认 |
| Known risks | 如实列出 |

### 规则

- **PR body 必须与 GitHub 真实数据一致**
- `changed_files` 数量必须等于 GitHub PR 页面的实际数量
- pytest 结果必须从终端输出复制
- Sonar 状态必须从 SonarCloud 复制
- 不一致即阻塞合入

## 6. 回报主脑

PR 创建后向主脑汇报：

```
PR URL: <url>
PR number: #<n>
head commit: <full SHA>
changed files: <count>
pytest: <result>
compileall: <result>
SonarCloud: <status>
安全边界: 已自查，无突破
```

## 7. 处理主脑 Blocker

主脑审核可能返回：

| 状态 | 含义 | 处理 |
|------|------|------|
| `blocked` | 有硬阻塞 | 按 blocker list 逐一修复 |
| `needs_update` | PR 口径或文档需更新 | 更新 PR body 或修复问题 |
| `changes_requested` | 需要修改代码 | 按要求修改 |
| `approved` | 审核通过，可合入 | 等待主脑合入或授权 |

### 常见 Blocker 处理

**SonarCloud failed**
- 查看 SonarCloud 报告找到具体问题
- 修复代码质量问题
- 重新 push，等待 Sonar 重新分析
- SonarCloud Passed 后才可请求合入

**pytest count mismatch**
- 重新本地运行 pytest
- 复制真实输出到 PR body
- 确认数字准确

**changed files mismatch**
- 在 GitHub PR Files 标签页确认真实文件列表
- 更新 PR body 中的列表和计数

**PR body stale**
- 检查是否复制了旧 PR 的内容
- 逐字段刷新到当前状态

**Out-of-scope files**
- 检查 `git diff master...HEAD` 列出所有变更
- 移除越界修改
- 如确需越界修改，向主脑申请并说明理由

**Safety boundary broken**
- 立即审查新增代码中是否有违规调用
- 移除或替换违规代码
- 如无法避免，停止并报告主脑

## 8. 避免常见错误

### 测试相关

| 错误 | 正确做法 |
|------|---------|
| `def test_x(): pass` | 绝不允许提交空测试 |
| `assert True` | 必须做有意义的断言 |
| `# TODO` 占位 | 要么实现，要么不提交 |
| "测试除外" 未解释 | 必须说明理由 |
| monkeypatch 未说明 | 必须说明为何需要 |
| 跳过关键断言 | 宁可不加测试也不放宽 |

### 报告相关

| 错误 | 正确做法 |
|------|---------|
| 猜 changed files | 查 GitHub PR Files 标签 |
| 复制旧 pytest 数 | 重新运行并复制 |
| 写短 hash | 用完整 40 字符 SHA |
| 图省事写 "待 CI" | 等实际结果 |
| 忽略 Sonar 警告 | 修复到 0 Hotspots |

### 范围相关

| 错误 | 正确做法 |
|------|---------|
| 修改了未要求的文件 | 只改任务指定范围 |
| 修了无关的 bug | 另开分支和 PR |
| 顺手改格式 | 除非明确要求 |
| 引入额外依赖 | 先确认是否已存在 |

## 9. 安全边界自查清单

提交前逐项确认：

- [ ] 未访问 `Project.root_path`
- [ ] 未执行 shell / subprocess / os.system
- [ ] 未读取 `secret_ref`
- [ ] 未读取 `.env` / tokens / API keys
- [ ] 未 git clone / commit / push（除 PR 流程）
- [ ] 未直接 push master
- [ ] 未创建真实 GitHub PR
- [ ] 未调用真实 CI API
- [ ] 未调用真实 Sonar API
- [ ] 未部署
- [ ] 未自动 approve `human_required`
- [ ] 未自动 approve high/critical risk
- [ ] 未在 archived 任务后写业务数据
- [ ] 未实现未设计的模块

## 10. 进入下一阶段

1. PR 已合入 master
2. 运行 `git checkout master && git pull origin master`
3. 确认 master commit
4. 报告主脑当前状态
5. 等待下一阶段任务

## 11. 何时必须停止并请求主脑决策

- 任务范围不明确
- 需要突破安全边界
- 需要访问外部真实 API
- 需要新增未设计的模块
- 需要修改 AGENTS.md 或项目核心规则
- 发现已有设计与任务目标冲突
- 不确定如何满足 DoD
- 测试结果与预期不一致
