from abc import ABC, abstractmethod
from app.models.agent_run import AgentRun
from app.schemas.ai_provider import AgentRunResult


class AiProviderBase(ABC):
    """Abstract base class for AI providers.

    Each provider implements execute() which takes an AgentRun
    and produces an AgentRunResult. Providers must NOT:
    - Call external AI APIs
    - Read secret_ref values
    - Execute shell/subprocess/os.system
    - Access Project.root_path
    - Write to project directories
    - Create git commits/pushes
    - Create GitHub PRs
    - Call CI/Sonar APIs
    """

    @abstractmethod
    async def execute(self, run: AgentRun, code_context: dict | None = None) -> AgentRunResult:
        """Execute the AgentRun and return results.
        
        Args:
            run: The AgentRun to execute.
            code_context: Optional dict with files array (path, content, language).
                          This data comes from TaskArtifacts, not from file system.
        """
        ...
