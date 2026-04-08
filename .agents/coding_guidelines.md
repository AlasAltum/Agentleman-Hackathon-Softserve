## Design Principles: Public Flows vs. Private Methods

In the core domain design, we must strictly separate **public flows** from **private methods**. 
- **Public flows** (e.g., Use Cases, main orchestration functions) must be purely declarative and highly readable. They describe *what* happens step-by-step, mainly focused on business logic.
- **Private methods** (the implementations or helpers called by the flow) encapsulate the technical complexity.

**Example of an ideal public flow:**
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
This ensures the orchestration logic is immediately understood, while complex mechanisms remain hidden under the hood.