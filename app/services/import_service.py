import json
from urllib.parse import urlsplit
from sqlalchemy import select, delete
from app.database.models import ChannelDB, SourceDB
from app.matcher.channel_matcher import channel_id_for
from app.parser.normalizer import normalize_url


def import_entries(session, entries, playlist_name=None):
    added = skipped = relinked = 0
    # Load URL identities once. SQLAlchemy sessions in this project deliberately
    # use autoflush=False, so relying on a query to see newly-added SourceDB rows
    # would miss duplicate URLs occurring twice in the same M3U import.
    seen_urls = set(session.scalars(select(SourceDB.normalized_url)).all())
    for e in entries:
        # Ignore known metadata/noise entries rather than creating fake channels.
        blocked_names = {"更新日期"}
        if any((v or "").strip() in blocked_names for v in (e.tvg_id, e.tvg_name, e.name)):
            skipped += 1
            continue

        cid = channel_id_for(tvg_id=e.tvg_id, tvg_name=e.tvg_name, display_name=e.name)
        c = session.get(ChannelDB, cid)
        if not c:
            c = ChannelDB(
                id=cid,
                canonical_name=cid,
                # The display name is the authoritative playlist channel name.
                # tvg-id is intentionally stored as metadata only because it is
                # frequently reused across unrelated channels.
                display_name=e.name or e.tvg_name,
                tvg_id=e.tvg_id,
                tvg_logo=e.tvg_logo,
                group_name=e.group,
                language=e.tvg_language,
                country=e.tvg_country,
                aliases_json=json.dumps([], ensure_ascii=False),
            )
            session.add(c)
            session.flush()
        else:
            if e.tvg_name or e.name:
                c.display_name = e.name or e.tvg_name
            if e.tvg_id:
                c.tvg_id = e.tvg_id
            if e.tvg_logo:
                c.tvg_logo = e.tvg_logo
            if e.group:
                c.group_name = e.group
            if e.tvg_language:
                c.language = e.tvg_language
            if e.tvg_country:
                c.country = e.tvg_country

        normalized = normalize_url(e.url)
        p = urlsplit(normalized)
        headers = e.headers or {}
        # URL identity is authoritative for import deduplication. If the URL
        # already exists anywhere in the database, discard this playlist entry
        # entirely. In particular, do NOT relink an existing source to a new
        # channel just because the incoming M3U has different metadata. This
        # prevents a duplicate URL from silently moving between channels.
        if normalized in seen_urls:
            skipped += 1
            continue

        session.add(SourceDB(
            channel_id=cid,
            url=normalized,
            normalized_url=normalized,
            source_playlist=playlist_name,
            user_agent=headers.get('user-agent') or headers.get('http-user-agent'),
            referer=headers.get('referer') or headers.get('http-referrer'),
            origin=headers.get('origin'),
            cookie=headers.get('cookie'),
            authorization=headers.get('authorization'),
            protocol=p.scheme,
            host=p.hostname,
            port=p.port,
            status='active',
        ))
        seen_urls.add(normalized)
        added += 1

    # Old incorrect channel buckets can become empty after a repair/re-import.
    session.flush()
    empty_ids = list(session.scalars(
        select(ChannelDB.id).where(~ChannelDB.sources.any())
    ))
    if empty_ids:
        session.execute(delete(ChannelDB).where(ChannelDB.id.in_(empty_ids)))

    session.commit()
    return {'added': added, 'skipped': skipped, 'relinked': relinked}
