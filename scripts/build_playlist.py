#!/usr/bin/env python3

import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

API_BASE = "https://iptv-org.github.io/api"

TARGET_COUNTRIES = {
    "CA": "🇨🇦 CANADA",
    "US": "🇺🇸 USA",
    "GT": "🇬🇹 GUATEMALA",
    "ES": "🇪🇸 ESPAÑA",
}

SPANISH = "spa"
FRENCH = "fra"

OUTPUT = Path("output/playlist.m3u")

# ------------------------------------------------------------
# Additional public playlists
# ------------------------------------------------------------

EXTERNAL_PLAYLISTS = {
    "🌎 WORLDWIDE • Free TV": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "🌎 WORLDWIDE • Sports": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "🌎 WORLDWIDE • Movies": "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "🌎 WORLDWIDE • Series": "https://iptv-org.github.io/iptv/categories/series.m3u",
    "🌎 WORLDWIDE • Entertainment": "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "🌎 WORLDWIDE • Documentary": "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "🌎 WORLDWIDE • Family": "https://iptv-org.github.io/iptv/categories/family.m3u",
    "🌎 WORLDWIDE • Kids": "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "🌎 WORLDWIDE • Music": "https://iptv-org.github.io/iptv/categories/music.m3u",
}

# ------------------------------------------------------------
# EPG sources
# ------------------------------------------------------------

EPG_URLS = [
    "https://iptv-org.github.io/epg/guides/us/epg.xml",
    "https://iptv-org.github.io/epg/guides/ca/epg.xml",
    "https://iptv-org.github.io/epg/guides/gt/epg.xml",
    "https://iptv-org.github.io/epg/guides/es/epg.xml",
]


# ------------------------------------------------------------
# Download helpers
# ------------------------------------------------------------

def download_text(url):
    print(f"Downloading {url}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IPTVPlaylistBuilder/4.0"
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(name):
    return json.loads(download_text(f"{API_BASE}/{name}.json"))


# ------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------

def clean_attribute(value):
    """Sanitize attribute values for M3U tags (preserves raw ampersands)."""
    if not value:
        return ""
    return str(value).replace('"', "'").replace("\n", " ").replace("\r", " ").strip()


def clean_display_name(value):
    """Sanitize channel display labels."""
    if not value:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


# ------------------------------------------------------------
# Country & Language detection
# ------------------------------------------------------------

def has_target_area(feed):
    for area in feed.get("broadcast_area", []):
        if area.startswith("c/"):
            country = area[2:].upper()
            if country in TARGET_COUNTRIES:
                return country
    return None


def is_spanish(feed):
    return SPANISH in feed.get("languages", [])


def is_french(feed):
    return FRENCH in feed.get("languages", [])


# ------------------------------------------------------------
# Category detection
# ------------------------------------------------------------

def get_category(channel):
    categories = {str(c).lower() for c in channel.get("categories", [])}

    if "sports" in categories:
        return "⚽ Sports"
    if "news" in categories:
        return "📰 News"
    if "movies" in categories:
        return "🎬 Movies"
    if "series" in categories:
        return "📺 Series"
    if "entertainment" in categories:
        return "🎭 Entertainment"
    if "documentary" in categories:
        return "📚 Documentary"
    if "family" in categories:
        return "👨‍👩‍👧 Family"
    if "kids" in categories:
        return "👦 Kids"
    if "music" in categories:
        return "🎵 Music"

    return "📺 General"


# ------------------------------------------------------------
# Stream filtering & Quality scoring
# ------------------------------------------------------------

def stream_is_allowed(stream):
    labels = {str(label).lower() for label in stream.get("labels", [])}

    if "geo-blocked" in labels or "not 24/7" in labels:
        return False

    url = stream.get("url", "")
    return url.startswith(("http://", "https://"))


def quality_score(stream):
    quality = stream.get("quality")
    if not quality:
        return 0

    text = str(quality).lower()
    if "2160" in text or "4k" in text:
        return 2160
    if "1440" in text:
        return 1440
    if "1080" in text:
        return 1080
    if "720" in text:
        return 720
    if "576" in text:
        return 576
    if "480" in text:
        return 480

    return 0


# ------------------------------------------------------------
# External M3U parsing
# ------------------------------------------------------------

def parse_m3u(text, default_group):
    entries = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    current_extinf = None

    for line in lines:
        if line.startswith("#EXTINF:"):
            current_extinf = line
            continue
        if line.startswith("#"):
            continue
        if current_extinf:
            if line.startswith(("http://", "https://")):
                entries.append({
                    "extinf": current_extinf,
                    "url": line,
                    "group": default_group
                })
            current_extinf = None

    return entries


def replace_group_title(extinf, group):
    new_group = clean_attribute(group)
    pattern = r'group-title="[^"]*"'
    replacement = f'group-title="{new_group}"'

    if re.search(pattern, extinf):
        return re.sub(pattern, replacement, extinf)

    return extinf.replace(
        "#EXTINF:-1 ",
        f'#EXTINF:-1 group-title="{new_group}" ',
        1
    )


def add_external_playlist(output_entries, seen_urls, name, url):
    try:
        text = download_text(url)
        entries = parse_m3u(text, name)
        added = 0

        for entry in entries:
            stream_url = entry["url"]
            if stream_url in seen_urls:
                continue

            seen_urls.add(stream_url)
            extinf = replace_group_title(entry["extinf"], name)
            output_entries.append((extinf, stream_url))
            added += 1

        print(f"{name}: added {added} unique streams.")
    except Exception as error:
        print(f"WARNING: Could not load {name}: {error}")


# ------------------------------------------------------------
# EXTINF construction
# ------------------------------------------------------------

def build_country_group(country_code, category, feed):
    country_name = TARGET_COUNTRIES[country_code]
    if is_spanish(feed):
        return f"{country_name} • {category} • Español"
    if is_french(feed):
        return f"{country_name} • {category} • Français"
    return f"{country_name} • {category}"


def build_extinf(channel, feed, logo, country_code):
    channel_id = channel["id"]
    channel_name = channel.get("name", channel_id)
    feed_name = feed.get("name")

    display_name = channel_name
    if feed_name and feed_name != channel_name:
        display_name = f"{channel_name} - {feed_name}"

    category = get_category(channel)
    group = build_country_group(country_code, category, feed)

    attributes = [
        f'tvg-id="{clean_attribute(channel_id)}"',
        f'tvg-name="{clean_attribute(display_name)}"',
        f'group-title="{clean_attribute(group)}"',
    ]

    if logo:
        attributes.append(f'tvg-logo="{clean_attribute(logo)}"')

    if is_spanish(feed):
        attributes.append('tvg-language="Español"')
    elif is_french(feed):
        attributes.append('tvg-language="Français"')
    else:
        attributes.append('tvg-language="English"')

    return f"#EXTINF:-1 {' '.join(attributes)},{clean_display_name(display_name)}"


# ------------------------------------------------------------
# Main execution
# ------------------------------------------------------------

def main():
    print("==========================================")
    print("MY TV PLAYLIST BUILDER")
    print("==========================================")
    print("\nLoading IPTV-org data...")

    channels = fetch_json("channels")
    feeds = fetch_json("feeds")
    streams = fetch_json("streams")
    logos = fetch_json("logos")

    channel_by_id = {c["id"]: c for c in channels}

    feeds_by_key = {}
    for feed in feeds:
        c_id = feed.get("channel")
        f_id = feed.get("id")
        if c_id and f_id:
            feeds_by_key[(c_id, f_id)] = feed

    logos_by_channel = {}
    for logo in logos:
        if logo.get("in_use") and logo.get("channel"):
            c_id = logo["channel"]
            if c_id not in logos_by_channel:
                logos_by_channel[c_id] = logo.get("url")

    selected = {}
    for stream in streams:
        c_id = stream.get("channel")
        f_id = stream.get("feed")
        if not c_id:
            continue

        channel = channel_by_id.get(c_id)
        if not channel or channel.get("is_nsfw") or not stream_is_allowed(stream):
            continue

        feed = feeds_by_key.get((c_id, f_id))
        if not feed:
            continue

        country = has_target_area(feed)
        if not country:
            continue

        key = (c_id, f_id)
        old = selected.get(key)

        if old is None or quality_score(stream) > quality_score(old["stream"]):
            selected[key] = {
                "stream": stream,
                "channel": channel,
                "feed": feed,
                "country": country,
            }

    print(f"\nSelected {len(selected)} country streams.")

    country_groups = defaultdict(list)
    for item in selected.values():
        country_groups[item["country"]].append(item)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    seen_urls = set()
    output_entries = []

    for country_code in ["CA", "US", "GT", "ES"]:
        items = country_groups.get(country_code, [])
        items.sort(
            key=lambda item: (
                get_category(item["channel"]),
                item["channel"].get("name", "").lower(),
                item["feed"].get("name", "").lower(),
            )
        )

        print(f"\n{TARGET_COUNTRIES[country_code]}: {len(items)} channels")

        for item in items:
            channel = item["channel"]
            stream = item["stream"]
            feed = item["feed"]
            logo = logos_by_channel.get(channel["id"])

            stream_url = stream["url"]
            if stream_url in seen_urls:
                continue

            seen_urls.add(stream_url)
            extinf = build_extinf(channel, feed, logo, country_code)
            output_entries.append((extinf, stream_url))

    print("\n==========================================")
    print("Loading worldwide playlists...")
    print("==========================================")

    for name, url in EXTERNAL_PLAYLISTS.items():
        add_external_playlist(output_entries, seen_urls, name, url)

    print("\nWriting final playlist...")
    
    # Corrected header construction
    epg_header = f'#EXTM3U x-tvg-url="{",".join(EPG_URLS)}"'

    with OUTPUT.open("w", encoding="utf-8", newline="\r\n") as file:
        file.write(f"{epg_header}\n")
        for extinf, stream_url in output_entries:
            file.write(f"{extinf}\n{stream_url}\n")

    print("==========================================")
    print("BUILD COMPLETE")
    print("==========================================")
    print(f"FINAL PLAYLIST: {len(output_entries)} unique streams")
    print(f"Playlist written to: {OUTPUT}\n")


if __name__ == "__main__":
    main()
