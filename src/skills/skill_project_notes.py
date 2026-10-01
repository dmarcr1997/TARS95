"""Project-note command registration. Voice uses the deterministic early route."""

SKILL = {
    "name": "project_notes",
    "description": "Save dictated project notes locally (voice commands)",
    "followup": True,
    "prompt": "",  # Do not let an LLM rewrite or invent dictated note content.
}


def execute(parameters, context):
    from modules.module_note_commands import get_voice_note_commands
    if context.get("source") != "voice":
        return "Project note dictation is currently available by voice."
    return get_voice_note_commands().handle(context["user_input"], context.get("request_id"))
