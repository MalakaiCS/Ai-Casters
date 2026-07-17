"""Tests for the RBAC role hierarchy and permission helpers."""

from __future__ import annotations

import pytest

from ai_caster.auth.roles import (
    Role,
    assignable_roles,
    at_least,
    can_assign,
    can_manage_roles,
    can_train,
    rank,
    role_label,
)


def test_hierarchy_is_strictly_ordered():
    order = [Role.OWNER, Role.FOUNDER, Role.ADMIN, Role.STAFF, Role.PARTNER, Role.USER]
    ranks = [rank(r) for r in order]
    assert ranks == sorted(ranks, reverse=True)  # Owner highest, User lowest
    assert rank(Role.USER) == 0


def test_coerce_defaults_to_user():
    assert Role.coerce("nonsense") is Role.USER
    assert Role.coerce("ADMIN") is Role.ADMIN
    assert Role.coerce(Role.STAFF) is Role.STAFF
    assert Role.coerce(None) is Role.USER


def test_at_least():
    assert at_least(Role.ADMIN, Role.STAFF)
    assert at_least(Role.STAFF, Role.STAFF)
    assert not at_least(Role.PARTNER, Role.STAFF)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.OWNER, True),
        (Role.FOUNDER, True),
        (Role.ADMIN, True),
        (Role.STAFF, True),
        (Role.PARTNER, False),
        (Role.USER, False),
    ],
)
def test_can_train_is_staff_and_above(role, expected):
    assert can_train(role) is expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.OWNER, True),
        (Role.FOUNDER, True),
        (Role.ADMIN, True),
        (Role.STAFF, False),
        (Role.USER, False),
    ],
)
def test_can_manage_roles_is_admin_and_above(role, expected):
    assert can_manage_roles(role) is expected


@pytest.mark.parametrize(
    ("role", "sees_train", "sees_team"),
    [
        (Role.USER, False, False),  # plain user: no Admin section at all
        (Role.PARTNER, False, False),
        (Role.STAFF, True, False),  # can train, but not manage the team
        (Role.ADMIN, True, True),
        (Role.OWNER, True, True),
    ],
)
def test_admin_section_visibility_contract(role, sees_train, sees_team):
    # The sidebar shows "Train the AI" via can_train and "Team & Roles" via
    # can_manage_roles; a User sees neither (the Admin section is hidden entirely).
    assert can_train(role) is sees_train
    assert can_manage_roles(role) is sees_team


def test_assignable_roles_are_strictly_below_actor():
    # An admin can assign Staff/Partner/User but not Admin/Founder/Owner.
    assignable = assignable_roles(Role.ADMIN)
    assert Role.STAFF in assignable and Role.USER in assignable
    assert Role.ADMIN not in assignable
    assert Role.OWNER not in assignable
    # Owner can assign everything below Owner.
    assert Role.FOUNDER in assignable_roles(Role.OWNER)
    assert Role.OWNER not in assignable_roles(Role.OWNER)
    # Non-managers can assign nothing.
    assert assignable_roles(Role.STAFF) == []


def test_can_assign():
    assert can_assign(Role.OWNER, Role.ADMIN)
    assert not can_assign(Role.ADMIN, Role.OWNER)
    assert not can_assign(Role.STAFF, Role.USER)


def test_role_label():
    assert role_label(Role.OWNER) == "Owner"
    assert role_label("staff") == "Staff"
