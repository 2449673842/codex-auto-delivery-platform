"""STUB: CI 客户端接口定义 — MVP 阶段不实现"""


async def trigger_ci(task_id: int) -> dict:
    return {
        "success": False,
        "data": None,
        "message": "CI trigger not implemented in MVP. See Project.ci_provider for planned provider.",
    }
