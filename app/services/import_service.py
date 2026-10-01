import json
import logging
from urllib.parse import urlsplit

from sqlalchemy import delete, select

from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.exporters.logo import is_broken_logo, resolve_tvg_logo
from app.matcher.channel_matcher import resolve_channel
from app.parser.normalizer import (
    normalize_header,
    normalize_url,
    source_identity_key,
)

logger = logging.getLogger(__name__)


def _headers_from_entry(e) -> dict:
    raw = e.headers or {}
    return {
        "user_agent": normalize_header(
            raw.get("user-agent") or raw.get("http-user-agent")
        ),
        "referer": normalize_header(
            raw.get("referer") or raw.get("http-referrer") or raw.get("http-referer")
        ),
        "origin": normalize_header(raw.get("origin") or raw.get("http-origin")),
        "cookie": normalize_header(raw.get("cookie") or raw.get("http-cookie")),
        "authorization": normalize_header(
            raw.get("authorization") or raw.get("http-authorization")
        ),
    }


def _load_identity_index(session) -> dict:
    """Map source identity → source id. None and empty headers compare equal."""
    index = {}
    for row in session.execute(
        select(
            SourceDB.id,
            SourceDB.normalized_url,
            SourceDB.user_agent,
            SourceDB.referer,
            SourceDB.origin,
            SourceDB.cookie,
            SourceDB.authorization,
        )
    ):
        key = source_identity_key(
            row.normalized_url,
            row.user_agent,
            row.referer,
            row.origin,
            row.cookie,
            row.authorization,
        )
        index[key] = row.id
    return index


def dedupe_sources(session) -> int:
    """Remove duplicate sources that differ only by None vs empty headers.

    Keeps the lowest id in each identity group; reassigns test results and
    deletes the rest. Returns the number of deleted source rows.
    """
    groups: dict[tuple, list[int]] = {}
    for row in session.execute(
        select(
            SourceDB.id,
            SourceDB.normalized_url,
            SourceDB.user_agent,
            SourceDB.referer,
            SourceDB.origin,
            SourceDB.cookie,
            SourceDB.authorization,
        )
    ):
        key = source_identity_key(
            row.normalized_url,
            row.user_agent,
            row.referer,
            row.origin,
            row.cookie,
            row.authorization,
        )
        groups.setdefault(key, []).append(row.id)

    deleted = 0
    for ids in groups.values():
        if len(ids) < 2:
            continue
        ids_sorted = sorted(ids)
        keep, drop = ids_sorted[0], ids_sorted[1:]
        for old_id in drop:
            session.execute(
                TestResultDB.__table__.update()
                .where(TestResultDB.source_id == old_id)
                .values(source_id=keep)
            )
            src = session.get(SourceDB, old_id)
            if src is not None:
                session.delete(src)
                deleted += 1
    if deleted:
        session.flush()
        empty_ids = list(
            session.scalars(select(ChannelDB.id).where(~ChannelDB.sources.any()))
        )
        if empty_ids:
            session.execute(delete(ChannelDB).where(ChannelDB.id.in_(empty_ids)))
        logger.warning("dedupe_sources removed %s duplicate source rows", deleted)
    return deleted


def import_entries(session, entries, playlist_name=None):
    added = skipped = relinked = 0
    # Identity index must treat DB NULL headers and missing import headers as equal.
    seen = _load_identity_index(session)

    for e in entries:
        blocked_names = {"更新日期"}
        if any((v or "").strip() in blocked_names for v in (e.tvg_id, e.tvg_name, e.name)):
            skipped += 1
            continue

        try:
            normalized = normalize_url(e.url)
        except Exception:
            skipped += 1
            continue
        if not normalized:
            skipped += 1
            continue

        try:
            p = urlsplit(normalized)
            # Illegal / missing host → skip this entry only.
            if not p.scheme or not p.hostname:
                skipped += 1
                continue
            try:
                port = p.port
            except ValueError:
                skipped += 1
                continue
        except Exception:
            skipped += 1
            continue

        # Canonical key / dictionary display / rule group — not playlist labels.
        ident = resolve_channel(
            tvg_id=e.tvg_id, tvg_name=e.tvg_name, display_name=e.name
        )
        cid = ident.key
        display = ident.display_name
        rule_group = ident.group
        logo = resolve_tvg_logo(display or cid, e.tvg_logo)
        c = session.get(ChannelDB, cid)
        if not c:
            c = ChannelDB(
                id=cid,
                canonical_name=cid,
                display_name=display,
                tvg_id=e.tvg_id,
                tvg_logo=logo,
                group_name=rule_group,
                language=e.tvg_language,
                country=e.tvg_country,
                aliases_json=json.dumps([], ensure_ascii=False),
            )
            session.add(c)
            session.flush()
        else:
            # Always refresh to dictionary name + rule group (stable, not source-driven).
            c.display_name = display
            c.group_name = rule_group
            if e.tvg_id:
                c.tvg_id = e.tvg_id
            if logo and (not c.tvg_logo or is_broken_logo(c.tvg_logo) or e.tvg_logo):
                c.tvg_logo = logo
            if e.tvg_language:
                c.language = e.tvg_language
            if e.tvg_country:
                c.country = e.tvg_country

        hdrs = _headers_from_entry(e)
        key = source_identity_key(
            normalized,
            hdrs["user_agent"],
            hdrs["referer"],
            hdrs["origin"],
            hdrs["cookie"],
            hdrs["authorization"],
        )
        if key in seen:
            skipped += 1
            continue

        session.add(SourceDB(
            channel_id=cid,
            url=normalized,
            normalized_url=normalized,
            source_playlist=playlist_name,
            # Export grouping uses channel rules; keep same on source for consistency.
            group_name=rule_group,
            user_agent=hdrs["user_agent"],
            referer=hdrs["referer"],
            origin=hdrs["origin"],
            cookie=hdrs["cookie"],
            authorization=hdrs["authorization"],
            protocol=p.scheme or "",
            host=p.hostname,
            port=port,
            status="active",
        ))
        seen[key] = None  # reserved for this import batch
        added += 1

    session.flush()
    empty_ids = list(session.scalars(select(ChannelDB.id).where(~ChannelDB.sources.any())))
    if empty_ids:
        session.execute(delete(ChannelDB).where(ChannelDB.id.in_(empty_ids)))

    session.commit()
    return {"added": added, "skipped": skipped, "relinked": relinked}
