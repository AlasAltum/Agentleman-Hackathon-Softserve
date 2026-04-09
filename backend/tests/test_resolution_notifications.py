from unittest.mock import Mock

from src.api.routes.incident_routes import _build_resolution_payload
from src.workflow.models import ResolutionPayload
from src.workflow.phases import resolution


def test_build_resolution_payload_extracts_reporter_email_from_adf_description():
    payload = {
        "user": {
            "displayName": "Jane Ops",
            "accountType": "atlassian",
        },
        "issue": {
            "key": "SRE-321",
            "fields": {
                "summary": "Checkout API returns 500 after payment confirmation",
                "status": {
                    "name": "Done",
                    "statusCategory": {"key": "done"},
                },
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Reporter email: reporter@example.com"}
                            ],
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Request ID: req-321"}
                            ],
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Original report:"}
                            ],
                        },
                    ],
                },
            },
        },
        "changelog": {
            "items": [
                {
                    "field": "status",
                    "fromString": "In Progress",
                    "toString": "Done",
                }
            ]
        },
    }

    result = _build_resolution_payload(payload)

    assert result.ticket_id == "SRE-321"
    assert result.reporter_email == "reporter@example.com"
    assert result.request_id == "req-321"
    assert result.resolution_notes.startswith("Jira webhook status transition: In Progress -> Done.")


def test_handle_resolution_saves_resolution_metadata(monkeypatch):
    save_to_knowledge_base = Mock()
    monkeypatch.setattr(resolution, "_save_to_knowledge_base", save_to_knowledge_base)

    payload = ResolutionPayload(
        ticket_id="SRE-900",
        resolved_by="Jane Ops",
        resolution_notes="Jira webhook status transition: In Progress -> Done.",
        reporter_email="reporter@example.com",
        request_id="req-900",
    )

    resolution.handle_resolution(payload)

    save_to_knowledge_base.assert_called_once_with(payload)


def test_handle_resolution_saves_without_reporter_email(monkeypatch):
    save_to_knowledge_base = Mock()
    monkeypatch.setattr(resolution, "_save_to_knowledge_base", save_to_knowledge_base)

    payload = ResolutionPayload(
        ticket_id="SRE-901",
        resolved_by="Jane Ops",
        resolution_notes="Jira webhook status transition: In Progress -> Done.",
    )

    resolution.handle_resolution(payload)

    save_to_knowledge_base.assert_called_once_with(payload)