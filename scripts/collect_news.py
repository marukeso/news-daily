#!/usr/bin/env python3
import re, json, html, time, urllib.parse
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

JST = timezone(timedelta(hours=9))
TITLE_MAX = 34
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / 'docs'
SITE_TITLE = 'ITトレンド Daily'

YT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
}

YOUTUBE_RETRY_PER_CHANNEL = 3
YOUTUBE_RETRY_SLEEP_SEC = 1.5
REUTERS_RETRY_COUNT = 4
REUTERS_RETRY_SLEEP_SEC = 5.0

YOUTUBE_CHANNELS = [
    ('AIまさおう（24時間以内・全投稿）', 'https://www.youtube.com/@ai_masaou/videos', 50, 'recent'),
    ('ニュースアーカイブ（24時間以内・全投稿）', 'https://www.youtube.com/@user-usnewsarchives/videos', 50, 'recent'),
    ('テレ東ビズ（24時間以内・再生回数順）', 'https://www.youtube.com/@tvtokyobiz/videos', 5, 'views'),
    ('ANNニュース（24時間以内・再生回数順）', 'https://www.youtube.com/channel/UCGCZAYq5Xxojl_tSXcVJhiQ/videos', 5, 'views'),
]


def fetch(url, headers=None):
    req = Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'ignore')


def trunc(s: str, n: int = TITLE_MAX) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'^\[[^\]]+\]\s*', '', s)
    s = re.sub(r'\s*[-｜|]\s*[^-｜|]+$', '', s)
    return s if len(s) <= n else s[: n - 1] + '…'


def get_hatena():
    txt = fetch('https://b.hatena.ne.jp/hotentry/it.rss', {'User-Agent': 'Mozilla/5.0'})
    items = []
    for url, body in re.findall(r'<item rdf:about="(.*?)">(.*?)</item>', txt, re.S):
        mt = re.search(r'<title>(.*?)</title>', body, re.S)
        mc = re.search(r'<hatena:bookmarkcount>(\d+)</hatena:bookmarkcount>', body)
        if mt and mc:
            title = html.unescape(mt.group(1)).strip()
            score = int(mc.group(1))
            items.append((trunc(title), url, score))
    items.sort(key=lambda x: x[2], reverse=True)
    return items[:5]


def get_chart_words():
    txt = fetch('https://chartnavi.com/scan/', {'User-Agent': 'Mozilla/5.0'})
    sec = txt[txt.find('過去24時間の急上昇ワード'):]
    words = re.findall(r'font-size:[^>]+>([^<]+)</span>', sec)
    out = []
    for w in words:
        w = w.strip()
        if w and w not in out:
            out.append(w)
    return out[:5]


def get_chart_stocks():
    txt = fetch('https://chartnavi.com/scan/wadai/wrank/_24/', {'User-Agent': 'Mozilla/5.0'})
    parts = txt.split('<div style="margin: 16px 10px 5px 10px;display: flex;">')
    out = []
    for part in parts[1:6]:
        mr = re.search(r'([0-9]+)位<br>\(([0-9,]+)\)', part)
        mn = re.search(r'href="/brand/code/_[^/]+/">([^<(]+)\(([0-9A-Z]+)\)</a>', part)
        if mr and mn:
            rank, count = mr.groups()
            name, code = mn.groups()
            out.append((rank, name.strip(), code, count))
    return out


def parse_reuters_site_once():
    txt = fetch('https://jp.reuters.com/', YT_HEADERS)
    idx = txt.find('globalContent')
    if idx == -1:
        return []
    chunk = txt[idx:]
    start = chunk.find('{')
    if start == -1:
        return []
    depth = 0
    end = start
    for i, c in enumerate(chunk[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    data = json.loads(chunk[start:end + 1])
    arts = data.get('result', {}).get('articles', [])
    cutoff = datetime.now(JST) - timedelta(hours=24)
    out = []
    for a in arts:
        pub = a.get('published_time', '')
        if not pub:
            continue
        norm = re.sub(r'(\.\d{1,6})\+00:00$', lambda m: m.group(1).ljust(7, '0') + '+00:00', pub.replace('Z', '+00:00'))
        try:
            dt = datetime.fromisoformat(norm).astimezone(JST)
        except Exception:
            continue
        if dt >= cutoff:
            out.append((trunc(a.get('title', '').strip()), 'https://jp.reuters.com' + a.get('canonical_url', ''), dt.strftime('%H:%M'), dt))
    out.sort(key=lambda x: x[3], reverse=True)
    return [(a, b, c) for a, b, c, _ in out[:5]]


def parse_reuters_google_news_once():
    q = urllib.parse.quote('site:jp.reuters.com')
    url = f'https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja'
    xml_text = fetch(url, {'User-Agent': 'Mozilla/5.0'})
    root = ET.fromstring(xml_text)
    cutoff = datetime.now(JST) - timedelta(hours=24)
    out = []
    for item in root.findall('./channel/item'):
        source = (item.findtext('source') or '').strip()
        if source and source.lower() not in ('reuters', 'ロイター'):
            continue
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub = (item.findtext('pubDate') or '').strip()
        if not title or not link or not pub:
            continue
        try:
            dt = datetime.fromtimestamp(__import__('email.utils').utils.parsedate_to_datetime(pub).timestamp(), tz=timezone.utc).astimezone(JST)
        except Exception:
            continue
        if dt < cutoff:
            continue
        title = re.sub(r'\s*-\s*(Reuters|ロイター)$', '', title)
        out.append((trunc(title), link, dt.strftime('%H:%M'), dt))
    out.sort(key=lambda x: x[3], reverse=True)
    dedup = []
    seen = set()
    for title, link, hhmm, dt in out:
        key = (title, hhmm)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((title, link, hhmm))
        if len(dedup) >= 5:
            break
    return dedup


def get_reuters():
    best = []
    for parser in (parse_reuters_site_once, parse_reuters_google_news_once):
        best = []
        for attempt in range(REUTERS_RETRY_COUNT):
            try:
                items = parser()
            except Exception:
                items = []
            if len(items) > len(best):
                best = items
            if best:
                break
            if attempt < REUTERS_RETRY_COUNT - 1:
                time.sleep(REUTERS_RETRY_SLEEP_SEC)
        if best:
            return best
    return []


def parse_relative_minutes(text):
    nums = re.findall(r'\d+', text or '')
    if '分前' in text and nums:
        return int(nums[0])
    if '時間前' in text and nums:
        return int(nums[0]) * 60
    if '日前' in text and nums:
        return int(nums[0]) * 1440
    return None


def parse_view_count(text):
    text = (text or '').replace(',', '').strip()
    if not text:
        return 0
    m = re.search(r'(\d+(?:\.\d+)?)\s*万', text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'(\d+(?:\.\d+)?)\s*億', text)
    if m:
        return int(float(m.group(1)) * 100000000)
    m = re.search(r'(\d+(?:\.\d+)?)\s*千', text)
    if m:
        return int(float(m.group(1)) * 1000)
    nums = re.findall(r'\d+', text)
    return int(''.join(nums) or '0')


def fetch_watch_view_count(video_id):
    try:
        txt = fetch(f'https://www.youtube.com/watch?v={video_id}', YT_HEADERS)
    except Exception:
        return '再生回数不明', 0

    patterns = [
        r'"viewCount":"(\d+)"',
        r'"shortViewCount":\{"simpleText":"([^"]+)"',
        r'"viewCountText":\{"simpleText":"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, txt)
        if not m:
            continue
        raw = m.group(1)
        if pat == patterns[0]:
            n = int(raw)
            return f'{n}回視聴', n
        n = parse_view_count(raw)
        if n > 0:
            return raw, n
    return '再生回数不明', 0


def pick_video_tab(data):
    tabs = data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
    for tab in tabs:
        tr = tab.get('tabRenderer', {})
        content = tr.get('content', {})
        if tr.get('title') == '動画' and 'richGridRenderer' in content:
            return content['richGridRenderer'].get('contents', [])
    for tab in tabs:
        tr = tab.get('tabRenderer', {})
        content = tr.get('content', {})
        if tr.get('selected') and 'richGridRenderer' in content:
            return content['richGridRenderer'].get('contents', [])
    return []


def parse_video_renderer(vr):
    title = vr.get('title', {}).get('runs', [{}])[0].get('text', '')
    video_id = vr.get('videoId', '')
    published = vr.get('publishedTimeText', {}).get('simpleText', '')
    views = vr.get('viewCountText', {}).get('simpleText', '') or vr.get('shortViewCountText', {}).get('simpleText', '') or '再生回数不明'
    minutes = parse_relative_minutes(published)
    if not title or not video_id or minutes is None or minutes > 24 * 60:
        return None
    return {
        'title': trunc(title),
        'url': f'https://www.youtube.com/watch?v={video_id}',
        'views': views,
        'view_num': parse_view_count(views),
        'minutes': minutes,
    }


def parse_lockup_view_model(vm):
    meta = vm.get('metadata', {}).get('lockupMetadataViewModel', {})
    title = meta.get('title', {}).get('content', '')
    rows = meta.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
    published = ''
    views = '再生回数不明'
    for row in rows:
        for part in row.get('metadataParts', []):
            text = part.get('text', {}).get('content', '')
            if not text:
                continue
            if ('分前' in text or '時間前' in text or '日前' in text) and not published:
                published = text
            if '視聴' in text and views == '再生回数不明':
                views = text
    if not published:
        label = vm.get('rendererContext', {}).get('accessibilityContext', {}).get('label', '')
        m = re.search(r'(\d+\s*分前|\d+\s*時間前|\d+\s*日前)', label)
        if m:
            published = m.group(1).replace(' ', '')
    minutes = parse_relative_minutes(published)
    video_id = vm.get('contentId', '')
    if not title or not video_id or minutes is None or minutes > 24 * 60:
        return None
    return {
        'title': trunc(title),
        'url': f'https://www.youtube.com/watch?v={video_id}',
        'views': views,
        'view_num': parse_view_count(views),
        'minutes': minutes,
    }


def parse_youtube_items(url):
    txt = fetch(url, YT_HEADERS)
    m = re.search(r'var ytInitialData = (.*?);</script>', txt, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    raw_items = pick_video_tab(data)
    items = []
    seen = set()
    for item in raw_items:
        rich = item.get('richItemRenderer', {}).get('content', {})
        parsed = None
        if 'videoRenderer' in rich:
            parsed = parse_video_renderer(rich['videoRenderer'])
        elif 'lockupViewModel' in rich:
            parsed = parse_lockup_view_model(rich['lockupViewModel'])
        if not parsed or parsed['url'] in seen:
            continue
        seen.add(parsed['url'])
        items.append(parsed)
    return items


def enrich_views(items, max_fetch):
    for item in items[:max_fetch]:
        video_id = item['url'].split('v=')[-1]
        view_text, view_num = fetch_watch_view_count(video_id)
        if view_num > 0:
            item['views'] = view_text
            item['view_num'] = view_num
    return items


def normalize_youtube_items(items, order_mode, limit):
    if order_mode == 'views':
        items.sort(key=lambda x: x['view_num'], reverse=True)
    else:
        items.sort(key=lambda x: x['minutes'])
    return [(x['title'], x['url'], x['views']) for x in items[:limit]]


def get_youtube_section(url, limit, order_mode, title_keyword=None):
    best = []
    saw_success = False
    last_error = None
    for attempt in range(YOUTUBE_RETRY_PER_CHANNEL):
        try:
            items = parse_youtube_items(url)
            saw_success = True
        except Exception as e:
            items = []
            last_error = e
        if title_keyword:
            items = [item for item in items if title_keyword in item['title']]
        if order_mode == 'views':
            items = enrich_views(items, max(limit * 3, 10))
        elif order_mode == 'recent':
            unknowns = [item for item in items if item['views'] == '再生回数不明']
            enrich_views(unknowns, min(5, len(unknowns)))
        if len(items) > len(best):
            best = items
        if len(best) >= limit:
            break
        if attempt < YOUTUBE_RETRY_PER_CHANNEL - 1:
            time.sleep(YOUTUBE_RETRY_SLEEP_SEC)
    normalized = normalize_youtube_items(best, order_mode, limit)
    if not saw_success:
        status = 'failed'
        note = '取得に失敗しました'
    elif not normalized:
        status = 'empty'
        note = '24時間以内の投稿なし'
    else:
        status = 'ok'
        note = ''
    return {
        'status': status,
        'items': normalized,
        'error': str(last_error) if last_error else '',
        'note': note,
    }


def collect_youtube_sections():
    out = {}
    for channel in YOUTUBE_CHANNELS:
        if len(channel) == 4:
            name, url, limit, order_mode = channel
            title_keyword = None
        else:
            name, url, limit, order_mode, title_keyword = channel
        out[name] = get_youtube_section(url, limit, order_mode, title_keyword)
    return out


def front_matter(title: str, date: str) -> str:
    return f'---\ntitle: "{title}"\ndate: {date}\n---\n\n'


def strip_front_matter(text: str) -> str:
    if text.startswith('---\n'):
        end = text.find('\n---\n', 4)
        if end != -1:
            return text[end + 5:].lstrip('\n')
    return text


DATE_FILE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\.md$')


def build_index():
    """docs/index.md を再生成する。最新分の本文＋月別アーカイブ一覧。"""
    dates = sorted(
        (f.stem for f in OUT_DIR.glob('*.md') if DATE_FILE_RE.match(f.name)),
        reverse=True,
    )
    out = [front_matter(SITE_TITLE, dates[0] if dates else datetime.now(JST).strftime('%Y-%m-%d')).rstrip('\n'), '']

    if dates:
        latest = strip_front_matter((OUT_DIR / f'{dates[0]}.md').read_text())
        # 最新分の見出しは h1 を残したまま丸ごと載せる
        out.append(latest.rstrip('\n'))
        out.append('')

    out.append('---')
    out.append('')
    out.append('## アーカイブ')
    out.append('')
    current_month = None
    for d in dates:
        month = d[:7]
        if month != current_month:
            current_month = month
            out.append('')
            out.append(f'### {month}')
            out.append('')
        out.append(f'- [{d}]({d}.html)')
    out.append('')

    (OUT_DIR / 'index.md').write_text('\n'.join(out) + '\n')


def main():
    today = datetime.now(JST).strftime('%Y-%m-%d')
    hatena = get_hatena()
    chart_words = get_chart_words()
    chart_stocks = get_chart_stocks()
    reuters = get_reuters()
    youtube = collect_youtube_sections()

    lines = []
    lines.append(f'# ITトレンド: {today}')
    lines.append('')
    lines.append('## はてブIT（日本市場）')
    lines.append('')
    for i, (title, url, users) in enumerate(hatena, 1):
        lines.append(f'{i}. [{title}]({url}) ({users} users)')
    lines.append('')
    for heading in ['AIまさおう（24時間以内・全投稿）']:
        lines.append(f'## {heading}')
        lines.append('')
        section = youtube[heading]
        if section['status'] != 'ok':
            lines.append(f"- {section['note']}")
        else:
            for i, (title, url, view) in enumerate(section['items'], 1):
                lines.append(f'{i}. [{title}]({url}) ({view})')
        lines.append('')
    lines.append('## チャートなび 急上昇ワード（24時間・注目度順）')
    lines.append('')
    for i, w in enumerate(chart_words, 1):
        lines.append(f'{i}. {w}')
    lines.append('')
    lines.append('## チャートなび 話題の銘柄ランキング（24時間）')
    lines.append('')
    for rank, name, code, count in chart_stocks:
        yurl = f'https://stocks.finance.yahoo.co.jp/stocks/detail/?code={code}'
        lines.append(f'{rank}. [{name}({code})]({yurl}) ({count}件)')
    lines.append('')
    lines.append('## ロイター（24時間以内・新着順）')
    lines.append('')
    for i, (title, url, t) in enumerate(reuters, 1):
        lines.append(f'{i}. [{title}]({url}) ({t})')
    lines.append('')
    for heading in ['ニュースアーカイブ（24時間以内・全投稿）', 'テレ東ビズ（24時間以内・再生回数順）', 'ANNニュース（24時間以内・再生回数順）']:
        lines.append(f'## {heading}')
        lines.append('')
        section = youtube[heading]
        if section['status'] != 'ok':
            lines.append(f"- {section['note']}")
        else:
            for i, (title, url, view) in enumerate(section['items'], 1):
                lines.append(f'{i}. [{title}]({url}) ({view})')
        lines.append('')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outpath = OUT_DIR / f'{today}.md'
    body = '\n'.join(lines) + '\n'
    outpath.write_text(front_matter(f'ITトレンド {today}', today) + body)
    build_index()
    print(outpath)


if __name__ == '__main__':
    main()
