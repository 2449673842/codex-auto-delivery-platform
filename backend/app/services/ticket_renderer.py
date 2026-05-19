from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task


async def render_ticket(db: AsyncSession, task: Task) -> str:
    project = await db.scalar(select(Project).where(Project.id == task.project_id))
    project_name = project.display_name or project.name if project else "Unknown"
    repo = project.repo_url or "N/A" if project else "N/A"

    lines = [
        f"# 执行任务单: {task.title}",
        "",
        "---",
        "",
        "## 项目信息",
        f"- **项目**: {project_name}",
        f"- **仓库**: {repo}",
        f"- **分支**: {project.current_branch if project else 'main'}",
        "",
        "## 任务信息",
        f"- **任务 ID**: #{task.id}",
        f"- **优先级**: {task.priority}",
        f"- **规划者**: {task.planner or 'N/A'}",
        f"- **执行者**: {task.executor or 'N/A'}",
        "",
        "## 需求描述",
        "",
        task.description or "（无描述）",
        "",
        "## 执行步骤",
        "",
        "1. 拉取最新代码",
        "2. 创建功能分支",
        "3. 根据上述描述实现代码修改",
        "4. 运行测试确保通过",
        "5. 提交代码并生成 diff",
        "",
        "## 输出要求",
        "",
        "- 执行日志（execution_log）",
        "- 代码变更 diff",
        "- 结果摘要",
        "",
        "---",
        f"*由 Codex 自动化平台生成 · Task #{task.id}*",
    ]
    return "\n".join(lines)
