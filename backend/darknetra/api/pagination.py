import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, tuple_

from darknetra.errors import Validation


async def page_rows(
    db, statement, model, *, limit: int = 50, cursor: str | None = None, newest_by=None
):
    """UUID keyset paging over an already authorized, filtered query."""
    if not 1 <= limit <= 200:
        raise Validation("Limit must be between 1 and 200")
    total = await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    if cursor:
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
            if newest_by is not None:
                timestamp, identifier = json.loads(decoded)
                at, value = datetime.fromisoformat(timestamp), UUID(identifier)
                if at.tzinfo is None:
                    raise ValueError("Missing timezone")
            else:
                value = UUID(decoded)
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            raise Validation("Invalid pagination cursor") from None
        statement = (
            statement.where(tuple_(newest_by, model.id) < tuple_(at, value))
            if newest_by is not None
            else statement.where(model.id > value)
        )
    ordering = [newest_by.desc(), model.id.desc()] if newest_by is not None else [model.id]
    rows = list(
        (await db.scalars(statement.order_by(None).order_by(*ordering).limit(limit + 1))).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        last = rows[-1]
        key = (
            json.dumps([getattr(last, newest_by.key).isoformat(), str(last.id)])
            if newest_by is not None
            else str(last.id)
        )
        next_cursor = base64.urlsafe_b64encode(key.encode()).decode()
    return rows, next_cursor, total
