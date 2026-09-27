#!/usr/bin/env python3

import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path


API_BASE = "https://iptv-org.github.io/api"

TARGET_COUNTRIES = {
    "US": "🇺🇸 USA",
    "CA": "🇨🇦 Canada",
    "GT": "🇬🇹 Guatemala",
    "ES": "🇪🇸 España",
}

SPANISH = "spa"
FRENCH = "fra"
SPORTS = "sports"

OUTPUT = Path("output/playlist.m3u")


# ------------------------------------------------------------
# External public playlists
# ------------------------------------------------------------

EXTERNAL_PLAYLISTS = {
    "🌎 Worldwide - Free TV":
        "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",

    "🌎 Worldwide - Sports":
        "https://iptv-org.github.io/iptv/categories/sports.m3u",

    "🌎 Worldwide - Movies":
        "https://iptv-org.github.io/iptv/categories/movies.m3u",

    "🌎 Worldwide - Series":
        "https://iptv-org.github.io/iptv/categories/series.m3u",

    "🌎 Worldwide - Entertainment":
        "https://iptv-org.github.io/iptv/categories/entertainment.m3u",

    "🌎 Worldwide - Documentary":
        "https://iptv-org.github.io/iptv/categories/documentary.m3u",

    "🌎 Worldwide - Family":
        "https://iptv-org.github.io/iptv/categories/family.m3u",

    "🌎 Worldwide - Kids":
        "https://iptv-org.github.io/iptv/categories/kids.m3u",

    "🌎 Worldwide - Music":
        "https://iptv-org.github.io/iptv/categories/music.m3u",
}


# ------------------------------------------------------------
# EPG sources
# ------------------------------------------------------------

EPG_URLS = [
    "https://iptv-org.github.io/epg/guides/us/tvtv.us.epg.xml",
    "https://iptv-org.github.io/epg/guides/ca/tvtv.us.epg.xml",
    "https://iptv-org.github.io/epg/guides/gt/gatotv.com.epg.xml",
    "https://iptv-org.github.io/epg/guides/es/ontvtonight.com.epg.xml",
]


# ------------------------------------------------------------
# Download helpers
# ------------------------------------------------------------

def download_text(url):

    print(f"Downloading {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "my-tv-playlist-builder/3.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=90
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def fetch_json(name):

    return json.loads(
        download_text(
            f"{API_BASE}/{name}.json"
        )
    )


# ------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------

def clean_text(value):

    if not value:
        return ""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


# ------------------------------------------------------------
# Feed helpers
# ------------------------------------------------------------

def has_target_area(feed):

    for area in feed.get(
        "broadcast_area",
        []
    ):

        if area.startswith("c/"):

            country = area[2:].upper()

            if country in TARGET_COUNTRIES:
                return country

    return None


def is_spanish(feed):

    return SPANISH in feed.get(
        "languages",
        []
    )


def is_french(feed):

    return FRENCH in feed.get(
        "languages",
        []
    )


# ------------------------------------------------------------
# Channel categories
# ------------------------------------------------------------

def get_category(channel):

    categories = channel.get(
        "categories",
        []
    )

    # Priority order matters.
    # A channel can belong to more than one category.

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
# Stream filtering
# ------------------------------------------------------------

def stream_is_allowed(stream):

    labels = {
        str(label).lower()
        for label in stream.get(
            "labels",
            []
        )
    }

    if "geo-blocked" in labels:
        return False

    if "not 24/7" in labels:
        return False

    url = stream.get(
        "url",
        ""
    )

    if not url.startswith(
        ("http://", "https://")
    ):
        return False

    return True


def quality_score(stream):

    quality = stream.get(
        "quality"
    )

    if not quality:
        return 0

    text = str(
        quality
    ).lower()

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
# External M3U parser
# ------------------------------------------------------------

def parse_m3u(
    text,
    default_group
):

    entries = []

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    current_extinf = None

    for line in lines:

        if line.startswith(
            "#EXTINF:"
        ):

            current_extinf = line
            continue

        if line.startswith("#"):
            continue

        if current_extinf:

            url = line

            if url.startswith(
                ("http://", "https://")
            ):

                entries.append({
                    "extinf": current_extinf,
                    "url": url,
                    "group": default_group
                })

            current_extinf = None

    return entries


def replace_group_title(
    extinf,
    group
):

    new_group = clean_text(
        group
    )

    pattern = r'group-title="[^"]*"'

    replacement = (
        f'group-title="{new_group}"'
    )

    if re.search(
        pattern,
        extinf
    ):

        return re.sub(
            pattern,
            replacement,
            extinf
        )

    return extinf.replace(
        "#EXTINF:-1 ",
        f'#EXTINF:-1 group-title="{new_group}" ',
        1
    )


def add_external_playlist(
    output_entries,
    seen_urls,
    name,
    url
):

    try:

        text = download_text(
            url
        )

        entries = parse_m3u(
            text,
            name
        )

        added = 0

        for entry in entries:

            stream_url = entry["url"]

            if stream_url in seen_urls:
                continue

            seen_urls.add(
                stream_url
            )

            extinf = replace_group_title(
                entry["extinf"],
                name
            )

            output_entries.append(
                (
                    extinf,
                    stream_url
                )
            )

            added += 1

        print(
            f"{name}: added {added} unique streams."
        )

    except Exception as error:

        print(
            f"WARNING: Could not load {name}: {error}"
        )


# ------------------------------------------------------------
# Build channel EXTINF
# ------------------------------------------------------------

def build_extinf(
    channel,
    feed,
    logo,
    country
):

    channel_id = channel[
        "id"
    ]

    channel_name = channel.get(
        "name",
        channel_id
    )

    feed_name = feed.get(
        "name"
    )

    display_name = channel_name

    if (
        feed_name
        and feed_name != channel_name
    ):

        display_name = (
            f"{channel_name} - {feed_name}"
        )

    category = get_category(
        channel
    )

    # Language-specific grouping

    if is_spanish(feed):

        group = (
            f"{TARGET_COUNTRIES[country]} - "
            f"{category} - Español"
        )

    elif is_french(feed):

        group = (
            f"{TARGET_COUNTRIES[country]} - "
            f"{category} - Français"
        )

    else:

        group = (
            f"{TARGET_COUNTRIES[country]} - "
            f"{category}"
        )

    attributes = [
        f'tvg-id="{clean_text(channel_id)}"',
        f'tvg-name="{clean_text(display_name)}"',
        f'group-title="{clean_text(group)}"',
    ]

    if logo:

        attributes.append(
            f'tvg-logo="{clean_text(logo)}"'
        )

    if is_spanish(feed):

        attributes.append(
            'tvg-language="Español"'
        )

    elif is_french(feed):

        attributes.append(
            'tvg-language="Français"'
        )

    else:

        attributes.append(
            'tvg-language="English"'
        )

    return (
        "#EXTINF:-1 "
        + " ".join(attributes)
        + ","
        + clean_text(display_name)
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print(
        "Loading iptv-org data..."
    )

    channels = fetch_json(
        "channels"
    )

    feeds = fetch_json(
        "feeds"
    )

    streams = fetch_json(
        "streams"
    )

    logos = fetch_json(
        "logos"
    )

    channel_by_id = {
        channel["id"]: channel
        for channel in channels
    }

    feeds_by_key = {}

    for feed in feeds:

        channel_id = feed.get(
            "channel"
        )

        feed_id = feed.get(
            "id"
        )

        if channel_id and feed_id:

            feeds_by_key[
                (channel_id, feed_id)
            ] = feed

    logos_by_channel = {}

    for logo in logos:

        if not logo.get(
            "in_use"
        ):
            continue

        channel_id = logo.get(
            "channel"
        )

        if (
            channel_id
            and channel_id not in logos_by_channel
        ):

            logos_by_channel[
                channel_id
            ] = logo.get("url")

    # --------------------------------------------------------
    # Select streams
    # --------------------------------------------------------

    selected = {}

    for stream in streams:

        channel_id = stream.get(
            "channel"
        )

        feed_id = stream.get(
            "feed"
        )

        if not channel_id:
            continue

        channel = channel_by_id.get(
            channel_id
        )

        if not channel:
            continue

        if channel.get(
            "is_nsfw"
        ):
            continue

        if not stream_is_allowed(
            stream
        ):
            continue

        feed = feeds_by_key.get(
            (
                channel_id,
                feed_id
            )
        )

        if not feed:
            continue

        country = has_target_area(
            feed
        )

        if not country:
            continue

        key = (
            channel_id,
            feed_id
        )

        old = selected.get(
            key
        )

        if (
            old is None
            or quality_score(stream)
            > quality_score(
                old["stream"]
            )
        ):

            selected[key] = {
                "stream": stream,
                "channel": channel,
                "feed": feed,
                "country": country,
            }

    print(
        f"Selected {len(selected)} country streams."
    )

    # --------------------------------------------------------
    # Group streams
    # --------------------------------------------------------

    country_groups = defaultdict(
        list
    )

    for item in selected.values():

        country_groups[
            item["country"]
        ].append(item)

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    seen_urls = set()

    output_entries = []

    # --------------------------------------------------------
    # Country channels
    # --------------------------------------------------------

    for country_code in [
        "CA",
        "US",
        "GT",
        "ES"
    ]:

        items = country_groups.get(
            country_code,
            []
        )

        items.sort(
            key=lambda item: (
                get_category(
                    item["channel"]
                ),
                item["channel"].get(
                    "name",
                    ""
                ),
                item["feed"].get(
                    "name",
                    ""
                ),
            )
        )

        for item in items:

            channel = item[
                "channel"
            ]

            stream = item[
                "stream"
            ]

            feed = item[
                "feed"
            ]

            logo = logos_by_channel.get(
                channel["id"]
            )

            extinf = build_extinf(
                channel,
                feed,
                logo,
                country_code
            )

            stream_url = stream[
                "url"
            ]

            if stream_url in seen_urls:
                continue

            seen_urls.add(
                stream_url
            )

            output_entries.append(
                (
                    extinf,
                    stream_url
                )
            )

    # --------------------------------------------------------
    # Worldwide public playlists
    # --------------------------------------------------------

    print(
        "\nLoading additional public playlists..."
    )

    for name, url in EXTERNAL_PLAYLISTS.items():

        add_external_playlist(
            output_entries,
            seen_urls,
            name,
            url
        )

    # --------------------------------------------------------
    # Write playlist
    # --------------------------------------------------------

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="\r\n"
    ) as file:

        file.write(
            "#EXTM3U\n"
        )

        # Multiple EPG sources.
        # Sparkle can use these to match guide data
        # against the tvg-id values in the playlist.

        file.write(
            'x-tvg-url="'
            + ",".join(EPG_URLS)
            + '"\n'
        )

        for extinf, stream_url in output_entries:

            file.write(
                extinf + "\n"
            )

            file.write(
                stream_url + "\n"
            )

    print()
    print(
        f"FINAL PLAYLIST: "
        f"{len(output_entries)} unique streams"
    )

    print(
        f"Playlist written to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
