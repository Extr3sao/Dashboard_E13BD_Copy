from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Tuple


_DATE_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)


def default_comparison_options() -> Dict[str, Any]:
    return {
        "trim_whitespace": True,
        "null_equals_empty": False,
        "ignore_case": False,
        "ignore_row_order": False,
        "normalize_dates": True,
        "normalize_numbers": True,
        "compare_by_column_name": True,
        "normalize_column_aliases": True,
        "sample_limit": 25,
        "comparison_key": [],
    }


def compare_query_results(
    left: Dict[str, Any],
    right: Dict[str, Any],
    options: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_options = {**default_comparison_options(), **(options or {})}
    sample_limit = max(1, int(normalized_options.get("sample_limit") or 25))

    if not left.get("success") or not right.get("success"):
        return _build_error_comparison(left, right)

    left_columns = list(left.get("columns") or [])
    right_columns = list(right.get("columns") or [])
    left_rows = list(left.get("rows") or [])
    right_rows = list(right.get("rows") or [])

    column_mapping = _build_column_mapping(left_columns, right_columns, normalized_options)
    structure_match = (
        len(column_mapping["left_only_columns"]) == 0
        and len(column_mapping["right_only_columns"]) == 0
        and len(left_columns) == len(right_columns)
    )
    row_count_match = int(left.get("row_count") or len(left_rows)) == int(right.get("row_count") or len(right_rows))

    left_sequence = _build_sequence(left_rows, column_mapping["pairs"], side="left", options=normalized_options)
    right_sequence = _build_sequence(right_rows, column_mapping["pairs"], side="right", options=normalized_options)
    order_match = left_sequence == right_sequence

    left_counter = Counter(left_sequence)
    right_counter = Counter(right_sequence)
    content_match = left_counter == right_counter

    only_in_left = _counter_difference(left_counter, right_counter, sample_limit)
    only_in_right = _counter_difference(right_counter, left_counter, sample_limit)
    value_differences = _detect_value_differences(
        left_rows,
        right_rows,
        column_mapping["pairs"],
        normalized_options,
        sample_limit,
    )

    differences_found = (
        len(column_mapping["left_only_columns"])
        + len(column_mapping["right_only_columns"])
        + (0 if row_count_match else 1)
        + len(only_in_left)
        + len(only_in_right)
        + len(value_differences)
        + (0 if order_match else 1)
    )

    if structure_match and row_count_match and content_match and order_match:
        status = "match"
    elif structure_match and row_count_match and content_match:
        status = "warning"
    else:
        status = "mismatch"

    match = bool(
        structure_match
        and row_count_match
        and content_match
        and (normalized_options.get("ignore_row_order") or order_match)
    )

    return {
        "match": match,
        "status": status,
        "structure_match": structure_match,
        "row_count_match": row_count_match,
        "content_match": content_match,
        "order_match": order_match,
        "column_pairs": column_mapping["pairs"],
        "left_only_columns": column_mapping["left_only_columns"],
        "right_only_columns": column_mapping["right_only_columns"],
        "only_in_left": only_in_left,
        "only_in_right": only_in_right,
        "value_differences": value_differences,
        "differences_found": differences_found,
        "summary": _build_summary(
            status=status,
            structure_match=structure_match,
            row_count_match=row_count_match,
            content_match=content_match,
            order_match=order_match,
            ignore_row_order=bool(normalized_options.get("ignore_row_order")),
            left_only_columns=column_mapping["left_only_columns"],
            right_only_columns=column_mapping["right_only_columns"],
            only_in_left_count=sum((left_counter - right_counter).values()),
            only_in_right_count=sum((right_counter - left_counter).values()),
            value_difference_count=len(value_differences),
        ),
    }


def _build_error_comparison(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_error = left.get("error")
    right_error = right.get("error")
    if left_error and right_error:
        summary = "Ambas consultas han fallado y no se pueden comparar resultados."
    elif left_error:
        summary = "La consulta izquierda ha fallado y la derecha no."
    else:
        summary = "La consulta derecha ha fallado y la izquierda no."
    return {
        "match": False,
        "status": "mismatch",
        "structure_match": False,
        "row_count_match": False,
        "content_match": False,
        "order_match": False,
        "column_pairs": [],
        "left_only_columns": list(left.get("columns") or []),
        "right_only_columns": list(right.get("columns") or []),
        "only_in_left": [],
        "only_in_right": [],
        "value_differences": [],
        "differences_found": 1,
        "summary": summary,
    }


def _build_column_mapping(
    left_columns: List[str],
    right_columns: List[str],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    compare_by_name = bool(options.get("compare_by_column_name"))
    normalize_aliases = bool(options.get("normalize_column_aliases"))

    if not compare_by_name:
        pairs = []
        for index, (left_name, right_name) in enumerate(zip(left_columns, right_columns)):
            pairs.append({"left": left_name, "right": right_name, "key": f"POS_{index + 1}"})
        return {
            "pairs": pairs,
            "left_only_columns": left_columns[len(pairs):],
            "right_only_columns": right_columns[len(pairs):],
        }

    left_map = {_canonical_column_name(name, normalize_aliases): name for name in left_columns}
    right_map = {_canonical_column_name(name, normalize_aliases): name for name in right_columns}
    shared_keys = [key for key in left_map.keys() if key in right_map]
    pairs = [{"left": left_map[key], "right": right_map[key], "key": key} for key in shared_keys]
    left_only = [left_map[key] for key in left_map.keys() if key not in right_map]
    right_only = [right_map[key] for key in right_map.keys() if key not in left_map]
    return {"pairs": pairs, "left_only_columns": left_only, "right_only_columns": right_only}


def _build_sequence(
    rows: Iterable[Dict[str, Any]],
    pairs: List[Dict[str, str]],
    *,
    side: str,
    options: Dict[str, Any],
) -> List[str]:
    sequence: List[str] = []
    for row in rows:
        projected = {}
        for pair in pairs:
            column_name = pair["left"] if side == "left" else pair["right"]
            projected[pair["key"]] = _normalize_scalar(row.get(column_name), options)
        sequence.append(json.dumps(projected, ensure_ascii=False, sort_keys=True))
    return sequence


def _counter_difference(primary: Counter, secondary: Counter, sample_limit: int) -> List[Dict[str, Any]]:
    diff = primary - secondary
    samples: List[Dict[str, Any]] = []
    for raw_row, count in diff.items():
        row_payload = json.loads(raw_row)
        for _ in range(count):
            samples.append(row_payload)
            if len(samples) >= sample_limit:
                return samples
    return samples


def _detect_value_differences(
    left_rows: List[Dict[str, Any]],
    right_rows: List[Dict[str, Any]],
    pairs: List[Dict[str, str]],
    options: Dict[str, Any],
    sample_limit: int,
) -> List[Dict[str, Any]]:
    key_columns = list(options.get("comparison_key") or [])
    if not key_columns or not pairs:
        return []

    pair_by_key = {pair["key"]: pair for pair in pairs}
    resolved_key_columns = []
    for requested in key_columns:
        canonical = _canonical_column_name(str(requested), bool(options.get("normalize_column_aliases")))
        pair = pair_by_key.get(canonical)
        if pair:
            resolved_key_columns.append(pair)
    if not resolved_key_columns:
        return []

    left_index = _index_rows_by_key(left_rows, pairs, resolved_key_columns, side="left", options=options)
    right_index = _index_rows_by_key(right_rows, pairs, resolved_key_columns, side="right", options=options)
    shared_keys = [key for key in left_index.keys() if key in right_index]

    differences: List[Dict[str, Any]] = []
    for shared_key in shared_keys:
        left_row = left_index[shared_key]
        right_row = right_index[shared_key]
        per_row_diff = []
        for pair in pairs:
            left_value = _normalize_scalar(left_row.get(pair["left"]), options)
            right_value = _normalize_scalar(right_row.get(pair["right"]), options)
            if left_value != right_value:
                per_row_diff.append(
                    {
                        "column": pair["key"],
                        "left": left_row.get(pair["left"]),
                        "right": right_row.get(pair["right"]),
                    }
                )
        if per_row_diff:
            differences.append({"comparison_key": shared_key, "differences": per_row_diff})
            if len(differences) >= sample_limit:
                break
    return differences


def _index_rows_by_key(
    rows: List[Dict[str, Any]],
    pairs: List[Dict[str, str]],
    key_pairs: List[Dict[str, str]],
    *,
    side: str,
    options: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key_payload = {}
        for pair in key_pairs:
            column_name = pair["left"] if side == "left" else pair["right"]
            key_payload[pair["key"]] = _normalize_scalar(row.get(column_name), options)
        key = json.dumps(key_payload, ensure_ascii=False, sort_keys=True)
        index.setdefault(key, row)
    return index


def _normalize_scalar(value: Any, options: Dict[str, Any]) -> Any:
    null_equals_empty = bool(options.get("null_equals_empty"))
    trim_whitespace = bool(options.get("trim_whitespace"))
    ignore_case = bool(options.get("ignore_case"))
    normalize_dates = bool(options.get("normalize_dates"))
    normalize_numbers = bool(options.get("normalize_numbers"))

    if value is None:
        return "" if null_equals_empty else None

    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _normalize_decimal(value) if normalize_numbers else str(value)
    if isinstance(value, (int, float)):
        return _normalize_decimal(Decimal(str(value))) if normalize_numbers else value

    text = str(value)
    if trim_whitespace:
        text = text.strip()
    if null_equals_empty and text == "":
        return ""
    if normalize_dates:
        parsed_date = _try_parse_date(text)
        if parsed_date is not None:
            return parsed_date
    if normalize_numbers:
        parsed_number = _try_parse_number(text)
        if parsed_number is not None:
            return parsed_number
    if ignore_case:
        text = text.upper()
    return text


def _try_parse_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("T", " ")
    for pattern in _DATE_PATTERNS:
        try:
            parsed = datetime.strptime(normalized, pattern)
            if "H" in pattern:
                return parsed.isoformat(sep=" ", timespec="seconds")
            return parsed.date().isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None


def _try_parse_number(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return _normalize_decimal(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _normalize_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _canonical_column_name(name: str, normalize_aliases: bool) -> str:
    text = unicodedata.normalize("NFD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    text = text.strip().upper()
    if normalize_aliases:
        text = re.sub(r"[^A-Z0-9]", "", text)
    return text


def _build_summary(
    *,
    status: str,
    structure_match: bool,
    row_count_match: bool,
    content_match: bool,
    order_match: bool,
    ignore_row_order: bool,
    left_only_columns: List[str],
    right_only_columns: List[str],
    only_in_left_count: int,
    only_in_right_count: int,
    value_difference_count: int,
) -> str:
    if status == "match":
        return "Los resultados coinciden completamente."
    if status == "warning" and content_match and not order_match:
        if ignore_row_order:
            return "Los resultados contienen los mismos datos y el orden se ha ignorado en la comparación."
        return "Los resultados contienen los mismos datos pero en distinto orden."
    messages = []
    if not structure_match:
        messages.append("La estructura de columnas no coincide.")
        if left_only_columns:
            messages.append(f"Solo en izquierda: {', '.join(left_only_columns[:5])}.")
        if right_only_columns:
            messages.append(f"Solo en derecha: {', '.join(right_only_columns[:5])}.")
    if not row_count_match:
        messages.append("El número de filas es distinto.")
    if not content_match:
        messages.append(
            f"Hay filas solo presentes en izquierda ({only_in_left_count}) y/o derecha ({only_in_right_count})."
        )
    if value_difference_count:
        messages.append(f"Se han detectado {value_difference_count} diferencias de valores para claves compartidas.")
    if not order_match and not ignore_row_order:
        messages.append("El orden de las filas también difiere.")
    return " ".join(messages) or "Se han detectado diferencias entre ambos resultados."
