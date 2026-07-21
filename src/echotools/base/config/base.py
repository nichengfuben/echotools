from __future__ import annotations

"""配置数据类基类，提供自动 from_dict 反序列化。"""

from dataclasses import MISSING, fields, is_dataclass
from typing import (
    Any,
    Literal,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

__all__ = ["ConfigBase"]

T = TypeVar("T", bound="ConfigBase")

_type_hints_cache: dict[type, dict[str, Any]] = {}


class ConfigBase:
    """配置类基类，提供 from_dict 自动反序列化。"""

    @classmethod
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        """从字典构造实例。"""
        if not isinstance(data, dict):
            raise TypeError(
                "Expected a dict, got {}".format(type(data).__name__)
            )
        init_args: dict[str, Any] = {}
        type_hints = _get_type_hints(cls)
        for f in fields(cls):  # type: ignore[arg-type]
            field_name = f.name
            field_type = type_hints.get(field_name, f.type)
            if field_name.startswith("_"):
                continue
            if not f.init:
                continue
            if field_name not in data:
                if f.default is not MISSING:
                    init_args[field_name] = f.default
                    continue
                if f.default_factory is not MISSING:  # type: ignore[misc]
                    init_args[field_name] = f.default_factory()  # type: ignore[misc]
                    continue
                raise ValueError(
                    "Missing required field: '{}'".format(field_name)
                )
            value = data[field_name]
            init_args[field_name] = cls._convert_field(value, field_type)
        return cls(**init_args)

    @classmethod
    def _convert_field(cls, value: Any, field_type: Any) -> Any:
        """转换单个字段。"""
        if isinstance(field_type, type) and is_dataclass(field_type):
            return field_type.from_dict(value)  # type: ignore[attr-defined]
        origin = get_origin(field_type)
        args = get_args(field_type)
        if origin is list:
            item_type = args[0] if args else Any
            return _convert_list_field(cls, value, item_type)
        if origin is set:
            item_type = args[0] if args else Any
            return _convert_set_field(cls, value, item_type)
        if origin is tuple:
            return _convert_tuple_field(cls, value, args)
        if origin is dict:
            key_type, val_type = args if len(args) == 2 else (Any, Any)
            return _convert_dict_field(cls, value, key_type, val_type)
        if origin is Union:
            return _convert_union_field(cls, value, args)
        if origin is Literal:
            return _convert_literal_field(value, field_type)
        if isinstance(field_type, type):
            return _convert_scalar_field(value, field_type)
        return value

    def __str__(self) -> str:
        field_strs = [
            "{}={!r}".format(f.name, getattr(self, f.name))
            for f in fields(self)  # type: ignore[arg-type]
        ]
        return "{}({})".format(
            self.__class__.__name__, ", ".join(field_strs)
        )


def _get_type_hints(cls: type) -> dict[str, Any]:
    """带缓存的 get_type_hints。"""
    if cls not in _type_hints_cache:
        try:
            _type_hints_cache[cls] = get_type_hints(cls)
        except Exception:
            _type_hints_cache[cls] = {}
    return _type_hints_cache[cls]


def _convert_list_field(cls: type, value: Any, item_type: Any) -> list:
    if not isinstance(value, list):
        raise TypeError("Expected list, got {}".format(type(value).__name__))
    return [cls._convert_field(i, item_type) for i in value]


def _convert_set_field(cls: type, value: Any, item_type: Any) -> set:
    if not isinstance(value, list):
        raise TypeError("Expected list, got {}".format(type(value).__name__))
    return {cls._convert_field(i, item_type) for i in value}


def _convert_tuple_field(cls: type, value: Any, args: tuple) -> tuple:
    return tuple(cls._convert_field(i, a) for i, a in zip(value, args))


def _convert_dict_field(cls: type, value: Any, key_type: Any, val_type: Any) -> dict:
    if not isinstance(value, dict):
        raise TypeError("Expected dict, got {}".format(type(value).__name__))
    result = {}
    for k, v in value.items():
        ck = cls._convert_field(k, key_type)
        try:
            cv = cls._convert_field(v, val_type)
        except (TypeError, ValueError):
            cv = v
        result[ck] = cv
    return result


def _convert_union_field(cls: type, value: Any, args: tuple) -> Any:
    if value is None:
        return None
    real_type = next((a for a in args if a is not type(None)), Any)
    return cls._convert_field(value, real_type)


def _convert_literal_field(value: Any, field_type: Any) -> Any:
    allowed = get_args(field_type)
    if value not in allowed:
        raise TypeError("Value '{}' not in allowed values {}".format(value, allowed))
    return value


def _convert_scalar_field(value: Any, field_type: type) -> Any:
    if isinstance(value, field_type):
        return value
    try:
        return field_type(value)
    except (ValueError, TypeError) as e:
        raise TypeError(
            "Cannot convert {} to {}".format(type(value).__name__, field_type.__name__)
        ) from e
