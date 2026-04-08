import asyncio
import random
from llama_index.core.workflow import (
    step,
    Context,
    Workflow,
    StartEvent,
    StopEvent,
)

from backend.src.workflow.events import ProcessEvent, ResultEvent

class ParallelWorkflow(Workflow):
    @step
    async def start(self, ctx: Context, ev: StartEvent) -> ProcessEvent:
        data_list = ["A", "B", "C"]
        await ctx.store.set("num_to_collect", len(data_list))
        for item in data_list:
            ctx.send_event(ProcessEvent(data=item))
        return None

    @step(num_workers=3)
    async def process_data(self, ev: ProcessEvent) -> ResultEvent:
        # Simulate some time-consuming processing
        processing_time = 2 + random.random()
        await asyncio.sleep(processing_time)
        result = f"Processed: {ev.data}"
        print(f"Completed processing: {ev.data}")
        return ResultEvent(result=result)

    @step
    async def combine_results(
        self, ctx: Context, ev: ResultEvent
    ) -> StopEvent | None:
        num_to_collect = await ctx.store.get("num_to_collect")
        results = ctx.collect_events(ev, [ResultEvent] * num_to_collect)
        if results is None:
            return None

        combined_result = ", ".join([event.result for event in results])
        return StopEvent(result=combined_result)    
    
async def main():
    import time
    
    parallel_workflow = ParallelWorkflow()

    print(
        "Start a parallel workflow with setting num_workers in the step of process_data"
    )
    start_time = time.time()
    result = await parallel_workflow.run()
    end_time = time.time()
    print(f"Workflow result: {result}")
    print(f"Time taken: {end_time - start_time} seconds")

if __name__ == '__main__':
    asyncio.run(main())