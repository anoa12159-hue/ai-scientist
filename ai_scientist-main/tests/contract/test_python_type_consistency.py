"""Recursive field-shape consistency between JSON Schema and Python TypedDicts.

The checker requires exact basic types, array elements, nested required sets,
constants, enums, and references. It deliberately does not claim that a broad
TypedDict encodes JSON Schema cross-field conditionals; those remain runtime
Schema invariants covered by Golden branch and counterexample fixtures.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict, get_args, get_origin, get_type_hints, is_typeddict

from conftest import CATALOG_SCHEMA_NAMES

from ai_scientist_mvp.domain.types import SCHEMA_TYPE_MAP


def _is_list(annotation: Any) -> bool:
    return get_origin(annotation) is list


def _is_dict(annotation: Any) -> bool:
    return get_origin(annotation) is dict


def _is_literal(annotation: Any) -> bool:
    return get_origin(annotation) is Literal


def _is_typeddict(annotation: Any) -> bool:
    return isinstance(annotation, type) and is_typeddict(annotation)


def _json_pointer(document: Any, pointer: str) -> Any:
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        document = document[part]
    return document


def _resolve_ref(subschema: dict, by_id: dict, current_root: dict) -> dict:
    base, _, fragment = subschema["$ref"].partition("#")
    target = by_id[base] if base else current_root
    if fragment:
        target = _json_pointer(target, fragment)
    return target


def _check_field(
    subschema: dict, annotation: Any, by_id: dict, current_root: dict, path: str
) -> list[str]:
    if "$ref" in subschema:
        target = _resolve_ref(subschema, by_id, current_root)
        return _check_field(target, annotation, by_id, current_root, path)
    if "const" in subschema:
        if not _is_literal(annotation):
            return [f"{path}: const requires an exact Literal, got {annotation!r}"]
        if get_args(annotation) != (subschema["const"],):
            return [
                f"{path}: const mismatch: "
                f"{get_args(annotation)} != {subschema['const']!r}"
            ]
        return []
    if "enum" in subschema:
        if not _is_literal(annotation):
            return [f"{path}: enum requires an exact Literal, got {annotation!r}"]
        if set(get_args(annotation)) != set(subschema["enum"]):
            return [
                f"{path}: enum mismatch: {get_args(annotation)} != {subschema['enum']}"
            ]
        return []
    schema_type = subschema.get("type")
    if schema_type == "string":
        if annotation is str:
            return []
        return [f"{path}: expected str, got {annotation!r}"]
    if schema_type == "integer":
        if annotation is int:
            return []
        return [f"{path}: expected int, got {annotation!r}"]
    if schema_type == "boolean":
        if annotation is bool:
            return []
        return [f"{path}: expected bool, got {annotation!r}"]
    if schema_type == "array":
        if not _is_list(annotation):
            return [f"{path}: expected list, got {annotation!r}"]
        item_schema = subschema.get("items", {})
        return _check_field(item_schema, get_args(annotation)[0], by_id, current_root, path + "[]")
    if schema_type == "object":
        properties = subschema.get("properties", {})
        if not properties:
            if _is_dict(annotation) and get_args(annotation) == (str, Any):
                return []
            return [f"{path}: open object requires dict[str, Any], got {annotation!r}"]
        if _is_typeddict(annotation):
            hints = get_type_hints(annotation)
            errors: list[str] = []
            if set(hints) != set(properties):
                errors.append(f"{path}: nested field-name drift {set(hints) ^ set(properties)}")
            expected_required = set(subschema.get("required", []))
            if set(annotation.__required_keys__) != expected_required:
                errors.append(
                    f"{path}: nested required drift "
                    f"{set(annotation.__required_keys__) ^ expected_required}"
                )
            for field, field_schema in properties.items():
                if field in hints:
                    errors += _check_field(
                        field_schema, hints[field], by_id, current_root, f"{path}.{field}"
                    )
            return errors
        return [f"{path}: structured object requires TypedDict, got {annotation!r}"]
    return []


def _typed_dict_errors(name: str, schema: dict, by_id: dict) -> list[str]:
    typed_dict = SCHEMA_TYPE_MAP[name]
    errors: list[str] = []
    props = schema.get("properties", {})
    annot = get_type_hints(typed_dict)
    if set(annot) != set(props):
        errors.append(f"{name}: field-name drift {set(annot) ^ set(props)}")
    if set(typed_dict.__required_keys__) != set(schema.get("required", [])):
        errors.append(
            f"{name}: required drift "
            f"{set(typed_dict.__required_keys__) ^ set(schema.get('required', []))}"
        )
    for field, subschema in props.items():
        if field in annot:
            errors += _check_field(subschema, annot[field], by_id, schema, f"{name}.{field}")
    return errors


def test_every_catalog_schema_has_a_type() -> None:
    missing = [name for name in CATALOG_SCHEMA_NAMES if name not in SCHEMA_TYPE_MAP]
    assert not missing, f"schemas without a TypedDict: {missing}"


def test_recursive_type_consistency_all_clean(schemas: dict) -> None:
    by_id = {schema["$id"]: schema for schema in schemas.values()}
    errors: list[str] = []
    for name in CATALOG_SCHEMA_NAMES:
        errors += _typed_dict_errors(name, schemas[name], by_id)
    assert not errors, "\n".join(errors)


# --- mutation-style proofs: the checker must fail on drift --------------------

def test_field_type_mutation_is_detected() -> None:
    assert _check_field({"type": "string"}, int, {}, {}, "id")
    assert _check_field({"type": "integer"}, str, {}, {}, "n")
    assert _check_field({"type": "boolean"}, int, {}, {}, "flag")


def test_enum_mutation_is_detected() -> None:
    assert _check_field({"type": "string", "enum": ["A", "B"]}, Literal["C"], {}, {}, "e")
    assert _check_field({"type": "string", "enum": ["A", "B"]}, Literal["A", "C"], {}, {}, "e")
    assert _check_field({"type": "string", "enum": ["A", "B"]}, Literal["A"], {}, {}, "e")
    assert _check_field({"type": "string", "enum": ["A", "B"]}, str, {}, {}, "e")


def test_const_mutation_is_detected() -> None:
    assert _check_field({"const": "NOT_EVALUATED"}, Literal["SUPPORTED"], {}, {}, "v")
    assert _check_field({"const": "NOT_EVALUATED"}, str, {}, {}, "v")


def test_any_widening_is_detected() -> None:
    assert _check_field({"type": "string"}, Any, {}, {}, "value")


def test_array_element_mutation_is_detected() -> None:
    assert _check_field({"type": "array", "items": {"type": "string"}}, list[int], {}, {}, "xs")


def test_object_field_mutation_is_detected(schemas: dict) -> None:
    class MutatedVRef(TypedDict):
        id: int
        schema_version: str
        content_hash: str

    by_id = {schema["$id"]: schema for schema in schemas.values()}
    vref_schema = schemas["versioned-ref"]
    # sanity: the real mapping is clean
    assert _typed_dict_errors("versioned-ref", vref_schema, by_id) == []
    # the mutated TypedDict's "id" is int, not str -> detected
    field_schema = vref_schema["properties"]["id"]
    assert _check_field(field_schema, MutatedVRef.__annotations__["id"], by_id, vref_schema, "id")


def test_nested_type_and_required_mutations_are_detected() -> None:
    class WrongType(TypedDict):
        code: int

    class WrongRequired(TypedDict, total=False):
        code: str

    nested_schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
        "additionalProperties": False,
    }
    assert _check_field(nested_schema, WrongType, {}, {}, "nested")
    assert _check_field(nested_schema, WrongRequired, {}, {}, "nested")
