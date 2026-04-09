import mlflow
from llama_index.core.workflow import Context, StartEvent, StopEvent, Workflow, step

from src.utils.logger import logger, log_phase_start, log_phase_success, log_phase_failure
from src.workflow.events import (
    CandidatesRetrievedEvent,
    ContextEnrichedEvent,
    RankedCandidatesEvent,
    ToolCallEvent,
    ToolResultEvent,
    TriageCompleteEvent,
)
from src.workflow.models import PreprocessedIncident, ToolResult, TriageResult
from src.workflow.phases.classification import (
    classify_incident,
    rerank_candidates,
    retrieve_candidates,
)
from src.workflow.phases.routing import (
    _consolidate_triage,
    _dispatch_tools,
    _select_tools,
)
from src.workflow.phases.ticketing import _create_new_ticket, _notify_team


class SREIncidentWorkflow(Workflow):
    """Event-driven LlamaIndex workflow for SRE incident intake and triage.

    Retrieval pipeline (Steps 1–3):
        retrieve_candidates   — vector search against local Qdrant (Top-K)
        rerank_candidates     — score-based reranking to Top-N
        classify_incident     — cluster & time judge → Alert Storm / Regression / New

    Triage pipeline (Steps 4–5):
        router                — decides which tools to dispatch (event-driven loop)
        dispatch_tools        — executes selected tools in parallel, feeds back to router
        create_ticket_and_notify — ticket creation/update + team alerts

    Event flow:
        StartEvent
          → retrieve_candidates  (CandidatesRetrievedEvent)
          → rerank_candidates    (RankedCandidatesEvent)
          → classify_incident    (ContextEnrichedEvent)
          → router               (ToolCallEvent | TriageCompleteEvent)
          → dispatch_tools       (ToolResultEvent → router loop)
          → create_ticket_and_notify (StopEvent)
    """

    # ── Step 1: Candidate Retriever ───────────────────────────────────────────

    @step
    async def retrieve_candidates_step(
        self, ctx: Context, ev: StartEvent
    ) -> CandidatesRetrievedEvent:
        preprocessed: PreprocessedIncident = ev.preprocessed

        request_id = preprocessed.request_id or "unknown"
        log_phase_start("retrieve", component="workflow", request_id=request_id)

        # Tag the active MLflow trace with request_id — must happen inside the
        # workflow step so the LlamaIndex autolog trace is still open.
        mlflow.update_current_trace(tags={"request_id": request_id})

        # Initialise shared context for the triage loop
        await ctx.store.set("iteration", 0)
        await ctx.store.set("accumulated_results", [])
        await ctx.store.set("request_id", request_id)

        logger.info("retrieve_candidates_start", request_id=request_id)
        candidates = await retrieve_candidates(preprocessed)
        logger.info("retrieve_candidates_done", candidates_count=len(candidates), request_id=request_id)

        log_phase_success("retrieve", latency_ms=0, candidates_count=len(candidates), request_id=request_id)
        return CandidatesRetrievedEvent(preprocessed=preprocessed, candidates=candidates)

    # ── Step 2: Node Reranker ─────────────────────────────────────────────────

    @step
    async def rerank_candidates_step(
        self, ctx: Context, ev: CandidatesRetrievedEvent
    ) -> RankedCandidatesEvent:
        request_id = await ctx.store.get("request_id", default="unknown")
        log_phase_start("rerank", component="workflow", request_id=request_id)

        logger.info("rerank_candidates_start", candidates_count=len(ev.candidates), request_id=request_id)
        ranked = rerank_candidates(ev.candidates)
        logger.info("rerank_candidates_done", ranked_count=len(ranked), request_id=request_id)

        log_phase_success("rerank", latency_ms=0, ranked_count=len(ranked), request_id=request_id)
        return RankedCandidatesEvent(preprocessed=ev.preprocessed, candidates=ranked)

    # ── Step 3: Cluster & Time Judge ─────────────────────────────────────────

    @step
    async def classify_incident_step(
        self, ctx: Context, ev: RankedCandidatesEvent
    ) -> ContextEnrichedEvent:
        request_id = await ctx.store.get("request_id", default="unknown")
        log_phase_start("classify", component="workflow", request_id=request_id)

        classification = classify_incident(ev.candidates)
        logger.info("classify_incident_done", incident_type=classification.incident_type, request_id=request_id)

        log_phase_success("classify", latency_ms=0, incident_type=classification.incident_type, request_id=request_id)
        return ContextEnrichedEvent(
            preprocessed=ev.preprocessed,
            classification=classification,
        )

    # ── Step 4: Router / Orchestrator ─────────────────────────────────────────

    @step
    async def router(
        self, ctx: Context, ev: ContextEnrichedEvent | ToolResultEvent
    ) -> ToolCallEvent | TriageCompleteEvent:
        request_id = await ctx.store.get("request_id", default="unknown")
        log_phase_start("router", component="workflow", request_id=request_id)

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
            logger.info("router_iteration", iteration=iteration, results_count=len(accumulated_results), request_id=request_id)

        max_iterations: int = await ctx.store.get("max_iterations", default=3)

        if iteration >= max_iterations:
            logger.info("max_iterations_reached", phase="router", request_id=request_id)
            triage = _consolidate_triage(preprocessed, classification, accumulated_results)
            return TriageCompleteEvent(preprocessed=preprocessed, triage=triage)

        selected_tools = _select_tools(preprocessed, classification, accumulated_results)

        if not selected_tools:
            logger.info("no_tools_to_dispatch", phase="router", request_id=request_id)
            triage = _consolidate_triage(preprocessed, classification, accumulated_results)
            return TriageCompleteEvent(preprocessed=preprocessed, triage=triage)

        log_phase_success("router", latency_ms=0, tools=selected_tools, request_id=request_id)
        return ToolCallEvent(
            preprocessed=preprocessed,
            classification=classification,
            tools_to_dispatch=selected_tools,
            previous_results=accumulated_results,
            iteration=iteration,
        )

    # ── Step 5: Tool Dispatcher ───────────────────────────────────────────────

    @step
    async def dispatch_tools(
        self, ctx: Context, ev: ToolCallEvent
    ) -> ToolResultEvent:
        request_id = await ctx.store.get("request_id", default="unknown")
        log_phase_start("dispatch_tools", component="workflow", tools=ev.tools_to_dispatch, request_id=request_id)

        new_results = await _dispatch_tools(ev.tools_to_dispatch, ev.preprocessed)
        all_results = list(ev.previous_results) + list(new_results)

        log_phase_success("dispatch_tools", latency_ms=0, total_results=len(all_results), request_id=request_id)
        return ToolResultEvent(
            preprocessed=ev.preprocessed,
            classification=ev.classification,
            tool_results=all_results,
            iteration=ev.iteration + 1,
        )

    # ── Step 6: Ticket + Notification ────────────────────────────────────────

    @step
    async def create_ticket_and_notify(
        self, ctx: Context, ev: TriageCompleteEvent
    ) -> StopEvent:
        request_id = await ctx.store.get("request_id", default="unknown")
        log_phase_start("ticketing", component="workflow", request_id=request_id)
        reporter_email = ev.preprocessed.original.reporter_email
        ticket = await _create_new_ticket(ev.triage, reporter_email, ev.preprocessed)
        _notify_team(ticket, ev.triage, request_id)
        log_phase_success("ticketing", latency_ms=0, ticket_id=ticket.ticket_id, action=ticket.action, request_id=request_id)
        return StopEvent(result=ticket)
