"""What a participant affords *this* caller.

Not a filter applied to a list that already existed. There is no "what this participant can
do" to filter: a grant is what brings an affordance into existence for a caller, so a
projection with no grant has nothing to describe.

Everything a caller cannot invoke stays out of the description entirely — not the name, not
the schema, not the examples. A tool list that advertises what it will refuse is both a lie
and a map of the walls.

Imported for typing only, so a projection never depends on the runtime at import time; all
it needs from a grant is `permits`.
"""

from typing import TYPE_CHECKING

from maiku.descriptor.affordance import Affordance
from maiku.descriptor.participant import ParticipantDescriptor

if TYPE_CHECKING:
    from maiku.runtime.grants import Grant


def visible(descriptor: ParticipantDescriptor, grant: "Grant") -> list[Affordance]:
    return [
        affordance
        for affordance in descriptor.affordances
        if grant.permits(
            descriptor.handle,
            affordance.name,
            side_effect=affordance.side_effects,
            scopes=set(affordance.scopes),
        )
    ]
