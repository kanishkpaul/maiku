"""A participant with teeth: side effects, approval gates, artifacts and a human question."""

from maiku.adapters.context import CallContext
from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Approval, Kind, SideEffect
from maiku.descriptor.participant import Permissions


@participant(
    handle="test/effects",
    kind=Kind.TOOL,
    permissions=Permissions(approval=Approval.ON_SCOPE, side_effects=SideEffect.IRREVERSIBLE),
)
@affordance(side_effects=SideEffect.IRREVERSIBLE, scopes=["publish"], idempotent=False)
def publish(message: str) -> str:
    """Send something nobody can unsend."""
    return f"published: {message}"


@affordance(side_effects=SideEffect.READ)
def summarise(digest: str, ctx: CallContext) -> str:
    """Read a granted artifact and describe it."""
    return f"read {len(ctx.artifacts.readable)} granted artifact(s)"


@affordance(side_effects=SideEffect.WRITE)
async def render(text: str, ctx: CallContext) -> str:
    """Write an artifact and return its digest."""
    ref = await ctx.artifacts.write(text.encode(), media_type="text/plain", name="render.txt")
    return ref.digest


async def consult(question: str, ctx: CallContext) -> str:
    """Ask whoever is listening, then use the answer."""
    return f"they said: {await ctx.ask(question, timeout=2.0)}"
