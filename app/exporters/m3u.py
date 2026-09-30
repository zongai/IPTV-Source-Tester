def render_m3u(entries):
    lines = ['#EXTM3U']
    for e in entries:
        attrs = ' '.join(
            f'{k}="{str(v).replace(chr(34), "&quot;")}"'
            for k, v in e.get('attrs', {}).items() if v is not None
        )
        lines.append(f'#EXTINF:-1 {attrs},{e.get("name", "")}')
        for k, v in e.get('headers', {}).items():
            key = k.lower()
            if key == 'user-agent':
                lines.append('#EXTVLCOPT:http-user-agent=' + v)
            elif key == 'referer':
                lines.append('#EXTVLCOPT:http-referrer=' + v)
            elif key == 'origin':
                lines.append('#EXTVLCOPT:http-origin=' + v)
            elif key == 'cookie':
                lines.append('#EXTVLCOPT:http-cookie=' + v)
            elif key == 'authorization':
                lines.append('#EXTVLCOPT:http-authorization=' + v)
        lines.append(e['url'])
    return '\n'.join(lines) + '\n'
