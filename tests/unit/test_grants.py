import time

import pytest

from maiku.descriptor.enums import SideEffect
from maiku.runtime.grants import (
    Capability,
    Denied,
    Escalation,
    Grant,
    root_grant,
    verify_chain,
)


def test_capability_parsing_and_wildcards():
    assert Capability.parse("local/sentiment#classify").affordance == "classify"
    assert Capability.parse("local/sentiment").affordance == "*"
    assert Capability.parse("*").covers(Capability.parse("anything#at_all"))
    assert not Capability.parse("a/b#x").covers(Capability.parse("a/b#y"))


def test_root_grant_permits_everything():
    grant = root_grant("orchestrator")
    assert grant.permits("any/thing", "act", side_effect=SideEffect.IRREVERSIBLE)


def test_side_effect_ceiling_is_enforced():
    grant = Grant(
        issuer="user",
        subject="worker",
        capabilities=[Capability()],
        max_side_effect=SideEffect.READ,
    )
    assert grant.permits("a/b", "peek", side_effect=SideEffect.READ)
    assert not grant.permits("a/b", "publish", side_effect=SideEffect.EXTERNAL)
    with pytest.raises(Denied):
        grant.check("a/b", "publish", side_effect=SideEffect.EXTERNAL)


def test_expiry_revokes():
    grant = root_grant("worker").model_copy(update={"expires_at": time.time() - 1})
    assert grant.expired
    assert not grant.permits("a/b", "act")


def test_scopes_must_be_held():
    grant = Grant(
        issuer="user",
        subject="worker",
        capabilities=[Capability()],
        scopes={"fs:read"},
        max_side_effect=SideEffect.READ,
    )
    assert grant.permits("a/b", "act", scopes={"fs:read"})
    assert not grant.permits("a/b", "act", scopes={"fs:write"})


def test_attenuation_narrows():
    parent = root_grant("orchestrator")
    child = parent.attenuate(
        "worker",
        capabilities=[Capability.parse("local/sentiment#classify")],
        max_side_effect=SideEffect.READ,
    )
    assert child.parent_id == parent.id
    assert child.issuer == "orchestrator"
    assert child.permits("local/sentiment", "classify", side_effect=SideEffect.READ)
    assert not child.permits("other/thing", "classify")


@pytest.mark.parametrize(
    "escalation",
    [
        {"capabilities": [Capability.parse("other/agent#act")]},
        {"scopes": {"fs:write"}},
        {"max_side_effect": SideEffect.IRREVERSIBLE},
        {"artifacts": {"sha256:" + "0" * 64}},
    ],
)
def test_attenuation_refuses_to_widen(escalation):
    parent = Grant(
        issuer="user",
        subject="orchestrator",
        capabilities=[Capability.parse("local/sentiment#classify")],
        scopes={"fs:read"},
        max_side_effect=SideEffect.READ,
    )
    with pytest.raises(Escalation):
        parent.attenuate("worker", **escalation)


def test_child_cannot_outlive_parent():
    deadline = time.time() + 60
    parent = root_grant("orchestrator").model_copy(update={"expires_at": deadline})
    parent.attenuate("worker", expires_at=deadline - 10)
    with pytest.raises(Escalation):
        parent.attenuate("worker", expires_at=deadline + 10)
    with pytest.raises(Escalation):
        parent.attenuate("worker", expires_at=None)


def test_chain_verification():
    root = root_grant("a")
    mid = root.attenuate("b", max_side_effect=SideEffect.WRITE)
    leaf = mid.attenuate("c", max_side_effect=SideEffect.READ)
    verify_chain([root, mid, leaf])

    forged = leaf.model_copy(update={"max_side_effect": SideEffect.IRREVERSIBLE})
    with pytest.raises(Escalation):
        verify_chain([root, mid, forged])
