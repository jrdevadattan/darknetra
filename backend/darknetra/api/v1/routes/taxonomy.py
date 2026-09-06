"""Versioned mutable lexicon configuration; extracted observations are immutable."""

import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.pagination import page_rows
from darknetra.api.v1.schemas import entities as dto
from darknetra.api.v1.schemas.common import Page
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.authz.deps import require
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import Conflict, NotFound, Validation
from darknetra.extract.models import TaxonomyTerm

router = APIRouter(prefix="/admin/taxonomy", tags=["taxonomy"])


def clean(body: dto.TaxonomyTermCreate) -> dto.TaxonomyTermCreate:
    canonical = unicodedata.normalize("NFC", body.canonical.strip())
    if not 1 <= len(canonical) <= 200 or not 1 <= len(body.variants) <= 100:
        raise Validation("Canonical term and between 1 and 100 variants are required")
    variants = []
    for variant in body.variants:
        values = {
            key: unicodedata.normalize("NFC", value.strip())
            for key, value in variant.model_dump().items()
            if value is not None
        }
        if (
            not 1 <= len(values["term"]) <= 200
            or not 1 <= len(values["language"]) <= 32
            or not 1 <= len(values["script"]) <= 32
            or len(values.get("note", "")) > 2000
        ):
            raise Validation("Invalid taxonomy variant bounds")
        variants.append(dto.TaxonomyVariant(**values))
    if len({(v.term, v.language, v.script) for v in variants}) != len(variants):
        raise Validation("Taxonomy variants must be unique")
    return dto.TaxonomyTermCreate(
        canonical=canonical, type=body.type, variants=variants, active=body.active
    )


def term_dto(rows: list[TaxonomyTerm]) -> dto.TaxonomyTerm:
    head = rows[0]
    return dto.TaxonomyTerm(
        id=head.id,
        canonical=head.canonical,
        type=head.type,
        active=head.active,
        variants=[
            dto.TaxonomyVariant(
                term=row.term, language=row.language, script=row.script, note=row.note
            )
            for row in rows
        ],
    )


async def group_rows(db: AsyncSession, head: TaxonomyTerm) -> list[TaxonomyTerm]:
    return list(
        await db.scalars(
            select(TaxonomyTerm)
            .where(TaxonomyTerm.canonical == head.canonical, TaxonomyTerm.type == head.type)
            .order_by(TaxonomyTerm.created_at, TaxonomyTerm.id)
        )
    )


@router.get("", response_model=Page[dto.TaxonomyTerm])
async def list_terms(
    q: str | None = Query(None, max_length=200),
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(require(Permission.ADMIN_TAXONOMY)),
    db: AsyncSession = Depends(get_session, scope="function"),
) -> Page[dto.TaxonomyTerm]:
    ranked = select(
        TaxonomyTerm.id,
        func.row_number()
        .over(
            partition_by=(TaxonomyTerm.canonical, TaxonomyTerm.type),
            order_by=(TaxonomyTerm.created_at, TaxonomyTerm.id),
        )
        .label("position"),
    ).subquery()
    statement = (
        select(TaxonomyTerm)
        .join(ranked, ranked.c.id == TaxonomyTerm.id)
        .where(ranked.c.position == 1)
    )
    if q:
        statement = statement.where(TaxonomyTerm.canonical.ilike("%" + q + "%"))
    if active is not None:
        statement = statement.where(TaxonomyTerm.active.is_(active))
    rows, next_cursor, total = await page_rows(
        db, statement, TaxonomyTerm, cursor=cursor, limit=limit
    )
    return Page(
        items=[term_dto(await group_rows(db, row)) for row in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.post("", response_model=dto.TaxonomyTerm, status_code=201)
async def create_term(
    body: dto.TaxonomyTermCreate,
    actor: Actor = Depends(require(Permission.ADMIN_TAXONOMY)),
    db: AsyncSession = Depends(get_session, scope="function"),
) -> dto.TaxonomyTerm:
    body = clean(body)
    await db.execute(select(func.pg_advisory_xact_lock(1700000998)))
    if await db.scalar(
        select(TaxonomyTerm.id).where(TaxonomyTerm.canonical == body.canonical).limit(1)
    ):
        raise Conflict("Canonical taxonomy term already exists")
    rows = [
        TaxonomyTerm(
            canonical=body.canonical,
            type=body.type,
            active=body.active,
            version=1,
            **variant.model_dump(),
        )
        for variant in body.variants
    ]
    db.add_all(rows)
    await db.flush()
    rows = await group_rows(db, rows[0])
    result = term_dto(rows)
    await record(
        db,
        actor=actor,
        action="taxonomy.create",
        target_type="taxonomy",
        target_id=result.id,
        detail={"after": result.model_dump(mode="json"), "version": 1},
    )
    return result


@router.patch("/{term_id}", response_model=dto.TaxonomyTerm)
async def patch_term(
    term_id: UUID,
    body: dto.TaxonomyTermPatch,
    actor: Actor = Depends(require(Permission.ADMIN_TAXONOMY)),
    db: AsyncSession = Depends(get_session, scope="function"),
) -> dto.TaxonomyTerm:
    await db.execute(select(func.pg_advisory_xact_lock(1700000998)))
    head = await db.get(TaxonomyTerm, term_id)
    if head is None:
        raise NotFound("Taxonomy term not found")
    rows = await group_rows(db, head)
    before = term_dto(rows)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    updated = clean(
        dto.TaxonomyTermCreate.model_validate({**before.model_dump(exclude={"id"}), **changes})
    )
    if await db.scalar(
        select(TaxonomyTerm.id)
        .where(
            TaxonomyTerm.canonical == updated.canonical,
            TaxonomyTerm.id.not_in([row.id for row in rows]),
        )
        .limit(1)
    ):
        raise Conflict("Canonical taxonomy term already exists")
    if updated.model_dump() == before.model_dump(exclude={"id"}):
        return before
    version = max(row.version for row in rows) + 1
    # Retain the group anchor while replacing mutable configuration variants. Full
    # before/after snapshots are audited; evidence and observations never change.
    retained = rows[: len(updated.variants)]
    for row in rows[len(updated.variants) :]:
        await db.delete(row)
    # Move variant keys aside within this transaction to permit reordering without
    # transient unique-key collisions; these temporary values are never committed.
    for row in retained:
        row.term = "__pending_taxonomy_" + str(row.id)
    await db.flush()
    while len(retained) < len(updated.variants):
        retained.append(TaxonomyTerm())
        db.add(retained[-1])
    for row, variant in zip(retained, updated.variants, strict=True):
        row.canonical, row.type, row.active, row.version = (
            updated.canonical,
            updated.type,
            updated.active,
            version,
        )
        for key, value in variant.model_dump().items():
            setattr(row, key, value)
    await db.flush()
    result = term_dto(await group_rows(db, retained[0]))
    await record(
        db,
        actor=actor,
        action="taxonomy.update",
        target_type="taxonomy",
        target_id=result.id,
        detail={
            "before": before.model_dump(mode="json"),
            "after": result.model_dump(mode="json"),
            "version": version,
        },
    )
    return result
