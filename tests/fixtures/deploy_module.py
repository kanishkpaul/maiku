"""A participant that gates itself mid-call rather than at the door.

Deliberately carries no participant-level approval policy, so the only escalation here is
the one the function asks for.
"""

from maiku.adapters.context import CallContext
from maiku.adapters.decorator import affordance, participant
from maiku.descriptor.enums import Kind, SideEffect


@participant(handle="test/deploy", kind=Kind.AGENT)
@affordance(side_effects=SideEffect.EXTERNAL)
async def deploy(target: str, ctx: CallContext) -> str:
    """Check in with a human before doing the scary part."""
    if not await ctx.approve(f"deploy to {target}", side_effects="irreversible", timeout=2.0):
        return "aborted"
    return f"deployed to {target}"


@affordance(side_effects=SideEffect.READ)
async def dry_run(target: str, ctx: CallContext) -> str:
    """Report what a deploy would do, asking nobody."""
    return f"would deploy to {target}"
