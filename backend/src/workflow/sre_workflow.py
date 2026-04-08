from llama_index.core.workflow import Context, StartEvent, StopEvent, Workflow, step

from src.utils.logger import logger
from src.workflow.events import (
    ContextEnrichedEvent,
    ToolCallEvent,
    ToolResultEvent,
    TriageCompleteEvent,
)
from src.workflow.models import PreprocessedIncident, ToolResult, TriageResult
from src.workflow.phases.classification import (
    _classify_incident,
    _rerank_candidates,
    _retrieve_candidates,
)
from src.workflow.phases.routing import (
    _consolidate_triage,
    _dispatch_tools,
    _select_tools,
)
from src.workflow.phases.ticketing import _create_or_update_ticket, _notify_team


class SREIncidentWorkflow(Workflow):
    """Event-driven LlamaIndex workflow for SRE incident intake and triage.

    Phases (executed INSIDE workflow):
        1. classify       — vector retrieval + reranking + incident classification
        2. router         — decides which tools to dispatch (event-driven loop)
        3. dispatch_tools — executes selected tools in parallel
        4. process_results — consolidates tool results and emits back to router
        5. create_ticket  — ticket creation/update + team alerts

    Phases (executed BEFORE workflow):
        - Guardrails validation (NeMo/input guardrails)
        - Dynamic preprocessing (file routing, content consolidation)

    Event Flow (per Mermaid diagram):
        StartEvent
          → classify(ContextEnrichedEvent)
          → router(ToolCallEvent | TriageCompleteEvent)
          → dispatch_tools(ToolResultEvent)
          → process_results(ToolResultEvent)
          → [loops back to router via ToolResultEvent]
          → create_ticket_and_notify(StopEvent)
    """

    @step
    async def classify(
        self, ctx: Context, ev: StartEvent
    ) -> ContextEnrichedEvent:
        preprocessed: PreprocessedIncident = ev.preprocessed
        logger.info("[classification] Retrieving and reranking historical candidates")
        
        candidates = _retrieve_candidates(preprocessed)
        reranked = _rerank_candidates(candidates)
        classification = _classify_incident(reranked)
        
        await ctx.store.set("iteration", 0)
        await ctx.store.set("accumulated_results", [])
        
        logger.info("[classification] Classified as %s", classification.incident_type)
        return ContextEnrichedEvent(
            preprocessed=preprocessed, 
            classification=classification
        )

    @step
    async def router(
        self, ctx: Context, ev: ContextEnrichedEvent | ToolResultEvent
    ) -> ToolCallEvent | TriageCompleteEvent:
        logger.info("[router] Evaluating context and deciding next tools")
        
        preprocessed = ev.preprocessed
        classification = ev.classification
        
        accumulated_results: list[ToolResult] = await ctx.store.get(
            "accumulated_results", default=[]
        )
        iteration: int = await ctx.store.get("iteration", default=0)
        
        if isinstance(ev, ToolResultEvent):
            accumulated_results = list(ev.tool_results)
            iteration = ev.iteration
            await ctx.store.set("iteration", iteration)
            await ctx.store.set("accumulated_results", accumulated_results)
            logger.info("[router] Iteration %d with %d accumulated results", iteration, len(accumulated_results))
        
        max_iterations: int = await ctx.store.get("max_iterations", default=3)
        
        if iteration >= max_iterations:
            logger.info("[router] Max iterations reached, proceeding to ticketing")
            triage = _consolidate_triage(preprocessed, classification, accumulated_results)
            return TriageCompleteEvent(preprocessed=preprocessed, triage=triage)
        
        selected_tools = _select_tools(preprocessed, classification, accumulated_results)
        
        if not selected_tools:
            logger.info("[router] No more tools to dispatch, proceeding to ticketing")
            triage = _consolidate_triage(preprocessed, classification, accumulated_results)
            return TriageCompleteEvent(preprocessed=preprocessed, triage=triage)
        
        logger.info("[router] Dispatching tools: %s", selected_tools)
        return ToolCallEvent(
            preprocessed=preprocessed,
            classification=classification,
            tools_to_dispatch=selected_tools,
            previous_results=accumulated_results,
            iteration=iteration,
        )

    @step
    async def dispatch_tools(
        self, ctx: Context, ev: ToolCallEvent
    ) -> ToolResultEvent:
        logger.info("[dispatch] Executing tools: %s", ev.tools_to_dispatch)
        
        new_results = await _dispatch_tools(ev.tools_to_dispatch, ev.preprocessed)
        
        all_results = list(ev.previous_results) + list(new_results)
        
        logger.info("[dispatch] Tools completed: %d total results", len(all_results))
        
        return ToolResultEvent(
            preprocessed=ev.preprocessed,
            classification=ev.classification,
            tool_results=all_results,
            iteration=ev.iteration + 1,
        )

    @step
    async def process_results(
        self, ctx: Context, ev: ToolResultEvent
    ) -> ToolResultEvent:
        logger.info("[process_results] Consolidating tool results")
        
        logger.info(
            "[process_results] Processed %d tool results, returning to router",
            len(ev.tool_results)
        )
        
        return ToolResultEvent(
            preprocessed=ev.preprocessed,
            classification=ev.classification,
            tool_results=ev.tool_results,
            iteration=ev.iteration,
        )

    @step
    async def create_ticket_and_notify(
        self, ctx: Context, ev: TriageCompleteEvent
    ) -> StopEvent:
        logger.info("[ticketing] Creating ticket and alerting team")
        reporter_email = ev.preprocessed.original.reporter_email
        ticket = _create_or_update_ticket(ev.triage, reporter_email)
        _notify_team(ticket, ev.triage)
        logger.info(
            "[ticketing] Done — ticket=%s action=%s",
            ticket.ticket_id,
            ticket.action,
        )
        return StopEvent(result=ticket)