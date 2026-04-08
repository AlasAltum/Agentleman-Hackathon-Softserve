from llama_index.core.workflow import Context, StartEvent, StopEvent, Workflow, step

from src.utils.logger import logger
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
from src.workflow.phases.ticketing import _create_or_update_ticket, _notify_team


class SREIncidentWorkflow(Workflow):
    """Event-driven LlamaIndex workflow for SRE incident intake and triage.

    Retrieval pipeline (Steps 1–3):
        retrieve_candidates   — vector search against local Qdrant (Top-K)
        rerank_candidates     — score-based reranking to Top-N
        classify_incident     — cluster & time judge → Alert Storm / Regression / New

    Triage pipeline (Steps 4–6):
        router                — decides which tools to dispatch (event-driven loop)
        dispatch_tools        — executes selected tools in parallel
        create_ticket_and_notify — ticket creation/update + team alerts

    Event flow:
        StartEvent
          → retrieve_candidates  (CandidatesRetrievedEvent)
          → rerank_candidates    (RankedCandidatesEvent)
          → classify_incident    (ContextEnrichedEvent)
          → router               (ToolCallEvent | TriageCompleteEvent)
          → dispatch_tools       (ToolResultEvent)
          → [loops back to router via ToolResultEvent]
          → create_ticket_and_notify (StopEvent)
    """

    # ── Step 1: Candidate Retriever ───────────────────────────────────────────

    @step
    async def retrieve_candidates_step(
        self, ctx: Context, ev: StartEvent
    ) -> CandidatesRetrievedEvent:
        preprocessed: PreprocessedIncident = ev.preprocessed

        # Initialise shared context for the triage loop
        await ctx.store.set("iteration", 0)
        await ctx.store.set("accumulated_results", [])

        logger.info("[retrieve] Querying Qdrant for similar historical incidents")
        candidates = await retrieve_candidates(preprocessed)

        logger.info("[retrieve] Got %d raw candidates from Qdrant", len(candidates))
        return CandidatesRetrievedEvent(preprocessed=preprocessed, candidates=candidates)

    # ── Step 2: Node Reranker ─────────────────────────────────────────────────

    @step
    async def rerank_candidates_step(
        self, ctx: Context, ev: CandidatesRetrievedEvent
    ) -> RankedCandidatesEvent:
        logger.info("[rerank] Reranking %d candidates", len(ev.candidates))
        ranked = rerank_candidates(ev.candidates)
        logger.info("[rerank] Kept top-%d after reranking", len(ranked))
        return RankedCandidatesEvent(preprocessed=ev.preprocessed, candidates=ranked)

    # ── Step 3: Cluster & Time Judge ─────────────────────────────────────────

    @step
    async def classify_incident_step(
        self, ctx: Context, ev: RankedCandidatesEvent
    ) -> ContextEnrichedEvent:
        classification = classify_incident(ev.candidates)
        logger.info("[classify] Incident type: %s", classification.incident_type)
        return ContextEnrichedEvent(
            preprocessed=ev.preprocessed,
            classification=classification,
        )

    # ── Step 4: Router / Orchestrator ─────────────────────────────────────────

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
            logger.info(
                "[router] Iteration %d with %d accumulated results",
                iteration,
                len(accumulated_results),
            )

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

    # ── Step 5: Tool Dispatcher ───────────────────────────────────────────────

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

    # ── Step 6: Results Processor ─────────────────────────────────────────────

    @step
    async def process_results(
        self, ctx: Context, ev: ToolResultEvent
    ) -> ToolResultEvent:
        logger.info(
            "[process_results] Processed %d tool results, returning to router",
            len(ev.tool_results),
        )
        return ToolResultEvent(
            preprocessed=ev.preprocessed,
            classification=ev.classification,
            tool_results=ev.tool_results,
            iteration=ev.iteration,
        )

    # ── Step 7: Ticket + Notification ────────────────────────────────────────

    @step
    async def create_ticket_and_notify(
        self, ctx: Context, ev: TriageCompleteEvent
    ) -> StopEvent:
        logger.info("[ticketing] Creating ticket and alerting team")
        reporter_email = ev.preprocessed.original.reporter_email
        ticket = _create_or_update_ticket(ev.triage, reporter_email, ev.preprocessed)
        _notify_team(ticket, ev.triage)
        logger.info(
            "[ticketing] Done — ticket=%s action=%s",
            ticket.ticket_id,
            ticket.action,
        )
        return StopEvent(result=ticket)
