"""Safe ADQL construction for TAP services.

ADQL is SQL-shaped, and the NASA Exoplanet Archive is a shared public service.
Two things follow:

1. **No user-supplied SQL fragment ever reaches the service.** A caller supplies
   a table name, column names and typed predicates. This module builds the query
   string; the caller cannot inject one.
2. **Everything is whitelisted.** Table names, column names and operators are
   checked against explicit allow-lists, so a typo fails locally with a clear
   message rather than becoming an `ORA-00904` from the archive.

String literals are escaped by doubling single quotes, which is the SQL-standard
escape and the only quoting ADQL string literals need.
"""

import re
from enum import Enum
from typing import Any, Iterable, List, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "AdqlError",
    "Comparison",
    "Predicate",
    "AdqlQuery",
    "quote_literal",
    "IDENTIFIER_PATTERN",
]


class AdqlError(ValueError):
    """Raised when a query cannot be built safely."""


#: TAP identifiers are alphanumeric plus underscore. Nothing else is accepted —
#: no dots, no spaces, no parentheses, no comment markers.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _check_identifier(name: str, kind: str) -> str:
    text = str(name).strip()
    if not IDENTIFIER_PATTERN.match(text):
        raise AdqlError(
            "{0} {1!r} is not a valid ADQL identifier; only letters, digits and "
            "underscores are allowed".format(kind, name)
        )
    return text


def quote_literal(value: str) -> str:
    """Quote a string as an ADQL literal, escaping embedded quotes.

    ``O'Brien`` -> ``'O''Brien'``. Control characters are rejected rather than
    escaped, since no legitimate identifier contains them.
    """
    text = str(value)
    if "\x00" in text or "\n" in text or "\r" in text:
        raise AdqlError("string literals must not contain control characters")
    return "'{0}'".format(text.replace("'", "''"))


class Comparison(str, Enum):
    """Operators a predicate may use. Anything else is rejected."""

    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    LIKE = "like"
    IN = "in"
    IS_NULL = "is null"
    IS_NOT_NULL = "is not null"


class Predicate(BaseModel):
    """One `column operator value` condition."""

    model_config = ConfigDict(extra="forbid")

    column: str
    operator: Comparison = Comparison.EQ
    #: Ignored for IS NULL / IS NOT NULL; a sequence for IN.
    value: Optional[Any] = None

    @field_validator("column")
    @classmethod
    def _valid_column(cls, value: str) -> str:
        return _check_identifier(value, "column")

    @model_validator(mode="after")
    def _check(self) -> "Predicate":
        nullary = (Comparison.IS_NULL, Comparison.IS_NOT_NULL)
        if self.operator in nullary:
            if self.value is not None:
                raise AdqlError("{0} takes no value".format(self.operator.value))
            return self
        if self.value is None:
            raise AdqlError("{0} requires a value".format(self.operator.value))
        if self.operator is Comparison.IN:
            if isinstance(self.value, (str, bytes)) or not isinstance(
                self.value, (list, tuple, set)
            ):
                raise AdqlError("IN requires a list of values")
            if not self.value:
                raise AdqlError("IN requires at least one value")
        return self

    def render(self) -> str:
        if self.operator in (Comparison.IS_NULL, Comparison.IS_NOT_NULL):
            return "{0} {1}".format(self.column, self.operator.value)
        if self.operator is Comparison.IN:
            rendered = ", ".join(self._render_value(item) for item in self.value)
            return "{0} in ({1})".format(self.column, rendered)
        return "{0} {1} {2}".format(
            self.column, self.operator.value, self._render_value(self.value)
        )

    @staticmethod
    def _render_value(value: Any) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return repr(value)
        return quote_literal(value)


class AdqlQuery(BaseModel):
    """A validated ADQL SELECT.

    Every part is built from whitelisted pieces. There is deliberately no way to
    pass a raw WHERE clause: that is the whole point.
    """

    model_config = ConfigDict(extra="forbid")

    table: str
    columns: List[str] = Field(min_length=1)
    predicates: List[Predicate] = Field(default_factory=list)
    order_by: Optional[str] = None
    descending: bool = False
    #: Emitted as `select top N`, which is ADQL's row limit.
    limit: Optional[int] = Field(default=None, ge=1, le=10000)

    @field_validator("table")
    @classmethod
    def _valid_table(cls, value: str) -> str:
        return _check_identifier(value, "table")

    @field_validator("columns")
    @classmethod
    def _valid_columns(cls, value: List[str]) -> List[str]:
        return [_check_identifier(column, "column") for column in value]

    @field_validator("order_by")
    @classmethod
    def _valid_order(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _check_identifier(value, "order-by column")

    def validate_against(self, allowed_columns: Iterable[str]) -> None:
        """Check every referenced column against a table's allow-list."""
        allowed = {str(column).lower() for column in allowed_columns}
        referenced = list(self.columns)
        referenced.extend(predicate.column for predicate in self.predicates)
        if self.order_by:
            referenced.append(self.order_by)
        unknown = sorted(
            {column for column in referenced if column.lower() not in allowed}
        )
        if unknown:
            raise AdqlError(
                "column(s) {0} are not in the allow-list for table {1!r}".format(
                    ", ".join(unknown), self.table
                )
            )

    def render(self) -> str:
        """Build the ADQL string."""
        select = "select"
        if self.limit is not None:
            select += " top {0}".format(int(self.limit))
        query = "{0} {1} from {2}".format(select, ", ".join(self.columns), self.table)
        if self.predicates:
            query += " where " + " and ".join(
                predicate.render() for predicate in self.predicates
            )
        if self.order_by:
            query += " order by {0} {1}".format(
                self.order_by, "desc" if self.descending else "asc"
            )
        return query
