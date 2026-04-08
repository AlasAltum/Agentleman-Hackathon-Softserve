from llama_index.core.workflow import Event

class ProcessEvent(Event):
    data: str


class ResultEvent(Event):
    result: str