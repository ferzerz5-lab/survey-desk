"""survey-desk: exact survey computation and plan plotting for Hermes."""
from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent


def register(ctx) -> None:
    from . import schemas, tools

    for schema, handler, emoji in (
        (schemas.TRAVERSE, tools.survey_traverse, "\U0001F4D0"),
        (schemas.PLAN, tools.survey_plan, "\U0001F5FA"),
        (schemas.CONVERT, tools.survey_convert, "\U0001F9ED"),
        (schemas.INVERSE, tools.survey_inverse, "\U0001F4CF"),
    ):
        ctx.register_tool(name=schema["name"], toolset="survey_desk", schema=schema, handler=handler,
                          description=schema["description"], emoji=emoji)
    ctx.register_command("survey", tools.survey_command,
                         description="Compute a closed traverse from a field book and send the plan (PNG, PDF, DXF, KML)",
                         args_hint="<field book>")
    skill = _HERE / "skills" / "field-book" / "SKILL.md"
    if skill.exists():
        ctx.register_skill("field-book", skill, description="How to use the survey_* tools and read a field book")
