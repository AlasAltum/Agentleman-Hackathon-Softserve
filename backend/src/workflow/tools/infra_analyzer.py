from src.utils.logger import logger
from src.workflow.models import ToolResult


async def analyze_infrastructure(incident_text: str) -> ToolResult:
    """Inspect Terraform and Kubernetes configurations for infrastructure issues.

    Stub: returns placeholder until IaC repository access is wired.
    """
    logger.info("[tool/infra_analyzer] Analyzing infrastructure (stub)")
    return ToolResult(
        tool_name="infra_analyzer",
        findings="Infrastructure analysis pending integration with IaC repository.",
        severity_hint=None,
    )
