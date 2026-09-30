from app.parser.m3u import parse_m3u

def test_parse_m3u_preserves_unknown_attributes_and_header():
    text = """#EXTM3U
#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV-1" tvg-logo="logo" group-title="央视" foo="bar",CCTV1综合
#EXTVLCOPT:http-user-agent=TestAgent
https://EXAMPLE.com/live/cctv1/
"""
    item = parse_m3u(text)[0]
    assert item.tvg_id == "cctv1"
    assert item.unknown_attributes["foo"] == "bar"
    assert item.headers["http-user-agent"] == "TestAgent"
    assert item.url == "https://example.com/live/cctv1"

def test_parse_multiple_entries():
    text = "#EXTM3U\n#EXTINF:-1,CCTV1\nhttps://a.test/1\n#EXTINF:-1,CCTV2\nhttps://a.test/2\n"
    assert len(parse_m3u(text)) == 2


def test_import_drops_existing_and_in_batch_duplicate_urls():
    from types import SimpleNamespace
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, SourceDB
    from app.services.import_service import import_entries

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    Entry = lambda name, url: SimpleNamespace(name=name, url=url, tvg_id='', tvg_name=name,
                                                tvg_logo='', group='', tvg_language='', tvg_country='', headers={})
    with Session() as s:
        first = import_entries(s, [Entry('CCTV1', 'http://example.test/1')], 'one')
        second = import_entries(s, [Entry('CCTV2', 'http://example.test/1'),
                                    Entry('CCTV3', 'http://example.test/2'),
                                    Entry('CCTV3', 'http://example.test/2')], 'two')
        rows = list(s.scalars(select(SourceDB)))
        assert first['added'] == 1
        assert second['added'] == 1
        assert second['skipped'] == 2
        assert len(rows) == 2
        assert {r.channel_id for r in rows} == {'cctv-1', 'cctv-3'}


def test_import_repeated_tvg_id_uses_channel_name_not_tvg_id():
    from types import SimpleNamespace
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, ChannelDB, SourceDB
    from app.services.import_service import import_entries

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    Entry = lambda name, url: SimpleNamespace(name=name, url=url, tvg_id='1', tvg_name=name,
                                                tvg_logo='', group='', tvg_language='', tvg_country='', headers={})
    with Session() as s:
        result = import_entries(s, [
            Entry('北京卫视4K', 'http://example.test/beijing'),
            Entry('IPTV法治', 'http://example.test/fazhi'),
            Entry('CCTV5', 'http://example.test/cctv5'),
        ], 'repeat-id')
        channels = list(s.scalars(select(ChannelDB)))
        sources = list(s.scalars(select(SourceDB)))
        assert result['added'] == 3
        assert len(channels) == 3
        assert {x.channel_id for x in sources} == {'北京卫视4k', 'iptv法治', 'cctv-5'}
