from src.utils.logger import logger
from src.workflow.models import ToolResult


async def check_business_impact(incident_text: str) -> ToolResult:
    """Estimate financial and customer impact via SQL analytics.

    Stub: returns placeholder until analytics DB integration is wired.
    """
    logger.info("tool_execution", tool="business_impact", status="stub")
    return ToolResult(
        tool_name="business_impact",
        findings="Business impact assessment pending integration with analytics DB.",
        severity_hint=None,
    )
