"""Custom validators for pydantic models"""

from dataclasses import dataclass
from typing import Any

from pydantic_core import PydanticCustomError

__all__ = ["MutexFieldGroup", "DependentFieldGroup"]


@dataclass
class FieldGroup:
    """Base class for field groups"""

    tag: str


class MutexFieldGroup(FieldGroup):
    """A field group where only one of the fields can be present"""

    @staticmethod
    def validate(cls, data: Any) -> Any:
        """Validate that only one of the fields in a mutex group is present"""
        print(f"MutexFieldGroup: {cls=}, {data=}")
        mutex_groups = {}
        for field_name, annotation in cls.model_fields.items():
            for m in annotation.metadata:
                if isinstance(m, MutexFieldGroup):
                    mutex_groups.setdefault(m.tag, []).append(field_name)
        print(f"{mutex_groups=}")

        for fields in mutex_groups.values():
            if len(conflicting_fields := set(data) & set(fields)) > 1:
                raise PydanticCustomError(
                    "mutex_field_groups",
                    '"Only one of the following fields can be present: {fields}"',
                    dict(fields=conflicting_fields),
                )
        return data


class DependentFieldGroup(FieldGroup):
    """A field group where all the fields must be present together"""

    @staticmethod
    def validate(cls, data: Any) -> Any:
        """Validate that all the fields in a dependent group are present together"""
        print(f"DependentFieldGroup: {cls=}, {data=}")
        dependent_groups = {}
        for field_name, annotation in cls.model_fields.items():
            for m in annotation.metadata:
                if isinstance(m, DependentFieldGroup):
                    dependent_groups.setdefault(m.tag, []).append(field_name)

        print(f"{dependent_groups=}")
        for field_names in dependent_groups.values():
            for field_name in field_names:
                if field_name in data and set(data) & set(field_names) != set(
                    field_names
                ):
                    raise PydanticCustomError(
                        "dependent_field_groups",
                        '"Fields {fields} must be present together"',
                        dict(fields=field_names),
                    )
        return data
