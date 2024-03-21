from ..validate import DependentFieldGroup, MutexFieldGroup
from pydantic import BaseModel, Field, PositiveInt, model_validator, ValidationError
from typing import Annotated, Optional


class User(BaseModel):
    """A model with mutually exclusive and dependent fields"""

    id: Annotated[
        Optional[PositiveInt],
        DependentFieldGroup("1"),
        MutexFieldGroup("a"),
        Field(default_factory=type(None)),
    ]
    name: Annotated[
        Optional[str],
        MutexFieldGroup("a"),
        MutexFieldGroup("b"),
        Field(default_factory=type(None)),
    ]
    user: Annotated[
        Optional[str], MutexFieldGroup("a"), Field(default_factory=type(None))
    ]
    account: Annotated[
        Optional[str],
        DependentFieldGroup("1"),
        MutexFieldGroup("b"),
        Field(default_factory=type(None)),
    ]
    thing: Annotated[
        Optional[str], DependentFieldGroup("2"), Field(default_factory=type(None))
    ]
    bing: Annotated[
        Optional[str], DependentFieldGroup("2"), Field(default_factory=type(None))
    ]
    cat: Optional[str] = None

    check_mutex_field_groups = model_validator(mode="before")(MutexFieldGroup.validate)
    check_dependent_field_groups = model_validator(mode="before")(
        DependentFieldGroup.validate
    )


def test_mutex_field_group():
    try:
        _ = User(id=1, name="a", account="b")
    except ValidationError as e:
        assert "mutex_field_groups" in {t.get("type") for t in e.errors()}

    try:
        _ = User(id=1, account="b")
    except ValidationError as e:
        assert "mutex_field_groups" not in {t.get("type") for t in e.errors()}


def test_dependent_field_group():
    try:
        _ = User(id=1)
    except ValidationError as e:
        assert "dependent_field_groups" in {t.get("type") for t in e.errors()}

    try:
        _ = User(id=1, account="b", thing="c", bing="d")
    except ValidationError as e:
        assert "dependent_field_groups" not in {x.get("type") for x in e.errors()}
