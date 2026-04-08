# Coding Guidelines

Use this file as the implementation policy for code written in this repository.

## 1. Public Flows vs. Private Methods

Keep a strict separation between public flows and private methods.

Public flows:
- Include use cases, main orchestration functions, workflow entry points, and other top-level business flows.
- Must be declarative, easy to scan, and focused on what happens.
- Should describe the business sequence step by step.
- Should avoid low-level technical details when possible.

Private methods:
- Include helpers and implementation details called by the flow.
- Encapsulate technical complexity such as validations, transformations, provider calls, persistence, retries, parsing, and framework-specific logic.

Target shape for a public flow:
```python
def flow_interrogate_user(request):
    user_logged_in = _validate_user_is_logged_in(request)
    if not user_logged_in:
        _show_message_user_not_logged_in()
        return
    _start_conversation(request)

def _start_conversation(request):
     conversation_context = _create_context_form(request)
     while True:
         question = llm._choose_question(conversation_context)
         t2s._send_audio(question)
         audio_response = await _user_audio_response()
         text_response = s2t._transform_audio_to_text(audio_response)
         processed_ans = llm._process_text(text_response)
         # _process_text handles correctness, next question prep, DB save, and weakness checks.
         conversation_context._consider_new_response(processed_ans)
```

This pattern keeps orchestration immediately understandable while hiding technical complexity behind private helpers.

## 2. Idempotency and Reproducibility

- All use cases must be reproducible.
- Docker and docker-compose are part of the expected execution model.
- Mock data should be supported.
- Persistent Docker volumes are allowed, but if data is missing the same mock data should be generatable again.

## 3. Environment Variables and Security

- Use environment variables for API keys, database URLs, and other secrets or environment-specific configuration.
- Keep `.env.example` updated.
- Document each required environment variable in `.env.example`.

## 4. Quality Assurance and Testing

Repository expectations:
- Every new backend feature must include automated tests, for example with `pytest`.
- Backend tests must run quickly, require zero manual setup, and use isolated local dependencies or mocks unless the task is explicitly about integration-testing an adapter.
- The frontend must be verifiable through automated end-to-end browser tests such as Playwright or Cypress, runnable fully locally.

Execution guidance:
- Do not add tests unless the task explicitly calls for them or the change introduces feature work that should ship with required coverage.

## 5. Linting

- Use `ruff` for backend Python.
- Use a frontend linter consistent with the frontend stack. The final choice is still open.

## 6. Poetry

- This project uses Poetry.
- `__init__.py` files should stay empty.
- Do not add exports to `__init__.py` files.

## 7. Observability and Tracing

- All API calls should be wrapped with observability and tracing.
- Create one UUIDv7 per request.
- The UUIDv7 must be sortable by timestamp and must persist through the entire flow.
- Use structured logging with `structlog` and OTEL.
- Publish telemetry to Grafana.

## 8. Documentation Maintenance

- If you detect inconsistencies in `.agents` or `/docs`, update them proactively or ask the developer to update them.
