# AGENTS_USE.md

For each Agent you've implemented provide the following information:

# Agent #1
## 1. Agent Overview

**Agent Name:** [Name of your agent]
**Purpose:** [One-paragraph summary of what the agent does and the problem it solves]
**Tech Stack:** [Languages, frameworks, LLM provider, model(s) used]

---

## 2. Agents & Capabilities

List each agent (or sub-agent) in your system. For single-agent architectures, describe the one agent in detail. For multi-agent systems, document each agent separately.

### Agent: [Agent Name]

| Field | Description |
|-------|-------------|
| **Role** | What is this agent responsible for? |
| **Type** | Autonomous / Semi-autonomous / Human-in-the-loop |
| **LLM** | Which model powers this agent? |
| **Inputs** | What data does this agent receive? (text, images, logs, etc.) |
| **Outputs** | What does this agent produce? (tickets, summaries, notifications, etc.) |
| **Tools** | Which tools or integrations does this agent use? |

*Remember: Repeat this block for each agent in your system.*

---

## 3. Architecture & Orchestration

Describe how your agents are orchestrated and how data flows through the system.

- **Architecture diagram:** [Include an image or ASCII/SVG diagram showing the agentic flow]
- **Orchestration approach:** [How are agents coordinated? Sequential pipeline, event-driven, supervisor pattern, etc.]
- **State management:** [How is state maintained between steps? In-memory, database, message queue, etc.]
- **Error handling:** [What happens when an agent fails or produces unexpected output?]
- **Handoff logic:** [If multi-agent: how do agents pass work to each other?]

---

## 4. Context Engineering

Explain how your agents manage context to produce accurate and relevant results.

- **Context sources:** [What information is fed to the agent? Code files, documentation, logs, user input, etc.]
- **Context strategy:** [How do you select, filter, or prioritize context? RAG, summarization, windowing, etc.]
- **Token management:** [How do you handle context window limits?]
- **Grounding:** [How do you ensure the agent's output is grounded in actual data rather than hallucinated?]

---

## 5. Use Cases

Describe the main use cases your agent supports. For each use case, walk through the flow from trigger to resolution.

### Use Case 1: [Name]

- **Trigger:** [What initiates this flow?]
- **Steps:** [Step-by-step description of what happens]
- **Expected outcome:** [What is the end result?]

### Use Case 2: [Name]

*(Repeat as needed)*

---

## 6. Observability

Document how you implemented observability across your agent pipeline.

- **Logging:** [What is logged? Structured/unstructured? Where are logs stored?]
- **Tracing:** [Are agent steps traced end-to-end? What tool is used? (e.g., OpenTelemetry, Langfuse, LangSmith)]
- **Metrics:** [What metrics are collected? Latency, token usage, success/failure rates, etc.]
- **Dashboards:** [Are there any dashboards? Screenshots or links appreciated.]

### Evidence

Provide screenshots, log samples, or trace exports that demonstrate your observability implementation is functional and covers the main agent stages (ingest → triage → ticket → notify → resolved).

---

## 7. Security & Guardrails

Document the security measures implemented in your agent.

- **Prompt injection defense:** [What techniques are used? Input sanitization, system prompt hardening, output validation, etc.]
- **Input validation:** [How are user inputs (text, files, images) validated before processing?]
- **Tool use safety:** [How do you prevent the agent from performing unintended or dangerous actions?]
- **Data handling:** [How are API keys, user data, and sensitive information protected?]

### Evidence

Provide test results or examples showing your guardrails in action — e.g., attempted prompt injections and how the agent responded.

---

## 8. Scalability

Summarize how your solution is designed to scale. Reference your `SCALING.md` for the full analysis.

- **Current capacity:** [What can the current implementation handle?]
- **Scaling approach:** [Horizontal, vertical, queue-based, etc.]
- **Bottlenecks identified:** [What are the known limitations?]

---

## 9. Lessons Learned & Team Reflections

- **What worked well:** [Approaches, tools, or decisions that paid off]
- **What you would do differently:** [With more time or resources]
- **Key technical decisions:** [Trade-offs you made and why]

---
