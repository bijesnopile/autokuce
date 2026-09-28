"""Simple offset pagination for SQLAlchemy select() statements."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


@dataclass
class Page:
    items: list
    total: int
    page: int
    per_page: int
    pages: int = field(init=False)

    def __post_init__(self) -> None:
        self.pages = max(1, math.ceil(self.total / self.per_page)) if self.per_page else 1

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def first_index(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        return min(self.page * self.per_page, self.total)

    def page_numbers(self, around: int = 2) -> list[int | None]:
        """Page numbers with gaps (None), e.g. [1, None, 4, 5, 6, None, 12]."""
        numbers: list[int | None] = []
        for number in range(1, self.pages + 1):
            if number in (1, self.pages) or abs(number - self.page) <= around:
                numbers.append(number)
            elif numbers and numbers[-1] is not None:
                numbers.append(None)
        return numbers


def parse_page(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def paginate(db: Session, stmt: Select, page: int, per_page: int) -> Page:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    items = list(db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)))
    return Page(items=items, total=total, page=page, per_page=per_page)
