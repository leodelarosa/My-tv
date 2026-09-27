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
    "🌎 WORLDWIDE • Free TV":
        "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",

    "🌎 WORLDWIDE • Sports":
        "https://iptv-org.github.io/iptv/categories/sports.m3u",

    "🌎 WORLDWIDE • Movies":
        "https://iptv-org.github.io/iptv/categories/movies.m3u",

    "🌎 WORLDWIDE • Series":
        "https://iptv-org.github.io/iptv/categories/series.m3u",

    "🌎 WORLDWIDE • Entertainment":
        "https://iptv-org.github.io/iptv/categories/entertainment.m3u",

    "🌎 WORLDWIDE • Documentary":
        "https://iptv-org.github.io/iptv/categories/documentary.m3u",

    "🌎 WORLDWIDE • Family":
        "https://iptv-org.github.io/iptv/categories/family.m3u",

    "🌎 WORLDWIDE • Kids":
        "https://iptv-org.github.io/iptv/categories/kids.m3u",

    "🌎 WORLDWIDE • Music":
        "https://iptv-org.github.io/iptv/categories/music.m3u",
}


# ------------------------------------------------------------
# EPG sources
#
# These are used by Sparkle through the x-tvg-url header.
# The tvg-id values on the individual channels are preserved.
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
            "User-Agent": "my-tv-playlist-builder/4.0"
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
# Country detection
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


# ------------------------------------------------------------
# Language detection
# ------------------------------------------------------------

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
# Category detection
# ------------------------------------------------------------

def get_category(channel):

    categories = {
        str(category).lower()
        for category in channel.get(
            "categories",
            []
        )
    }

    # Sports
    if "sports" in categories:
        return "⚽ Sports"

    # News
    if "news" in categories:
        return "📰 News"

    # Movies
    if "movies" in categories:
        return "🎬 Movies"

    # Series
    if "series" in categories:
        return "📺 Series"

    # Entertainment
    if "entertainment" in categories:
        return "🎭 Entertainment"

    # Documentary
    if "documentary" in categories:
        return "📚 Documentary"

    # Family
    if "family" in categories:
        return "👨‍👩‍👧 Family"

    # Kids
    if "kids" in categories:
        return "👦 Kids"

    # Music
    if "music" in categories:
        return "🎵 Music"

    # Default
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

    # Skip known problematic streams
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


# ------------------------------------------------------------
# Stream quality
# ------------------------------------------------------------

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
# Parse external M3U playlists
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


# ------------------------------------------------------------
# Replace group-title in external playlists
# ------------------------------------------------------------

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
        (
            f'#EXTINF:-1 '
            f'group-title="{new_group}" '
        ),
        1
    )


# ------------------------------------------------------------
# Add external playlist
# ------------------------------------------------------------

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

            # Prevent duplicate streams
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
# Build country group
# ------------------------------------------------------------

def build_country_group(
    country_code,
    category,
    feed
):

    country_name = TARGET_COUNTRIES[
        country_code
    ]

    # Spanish channels
    if is_spanish(feed):

        return (
            f"{country_name} • "
            f"{category} • Español"
        )

    # French channels
    if is_french(feed):

        return (
            f"{country_name} • "
            f"{category} • Français"
        )

    # Normal channels
    return (
        f"{country_name} • "
        f"{category}"
    )


# ------------------------------------------------------------
# Build EXTINF line
# ------------------------------------------------------------

def build_extinf(
    channel,
    feed,
    logo,
    country_code
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
            f"{channel_name} - "
            f"{feed_name}"
        )

    category = get_category(
        channel
    )

    group = build_country_group(
        country_code,
        category,
        feed
    )

    attributes = [
        f'tvg-id="{clean_text(channel_id)}"',
        f'tvg-name="{clean_text(display_name)}"',
        f'group-title="{clean_text(group)}"',
    ]

    # Logo
    if logo:

        attributes.append(
            f'tvg-logo="{clean_text(logo)}"'
        )

    # Language
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
        "=========================================="
    )

    print(
        "MY TV PLAYLIST BUILDER"
    )

    print(
        "=========================================="
    )

    print()

    print(
        "Loading IPTV-org data..."
    )

    # --------------------------------------------------------
    # Download IPTV-org API data
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Channel lookup
    # --------------------------------------------------------

    channel_by_id = {
        channel["id"]: channel
        for channel in channels
    }

    # --------------------------------------------------------
    # Feed lookup
    # --------------------------------------------------------

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
                (
                    channel_id,
                    feed_id
                )
            ] = feed

    # --------------------------------------------------------
    # Logo lookup
    # --------------------------------------------------------

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
            ] = logo.get(
                "url"
            )

    # --------------------------------------------------------
    # Select best streams
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

        # Skip NSFW channels
        if channel.get(
            "is_nsfw"
        ):
            continue

        # Skip blocked/bad streams
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

        # Keep the highest-quality stream
        if (
            old is None
            or quality_score(stream)
            >
            quality_score(
                old["stream"]
            )
        ):

            selected[key] = {
                "stream": stream,
                "channel": channel,
                "feed": feed,
                "country": country,
            }

    print()

    print(
        f"Selected {len(selected)} "
        f"country streams."
    )

    # --------------------------------------------------------
    # Organize by country
    # --------------------------------------------------------

    country_groups = defaultdict(
        list
    )

    for item in selected.values():

        country_groups[
            item["country"]
        ].append(
            item
        )

    # --------------------------------------------------------
    # Prepare output
    # --------------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    seen_urls = set()

    output_entries = []

    # --------------------------------------------------------
    # Add country channels
    #
    # Order:
    # Canada
    # USA
    # Guatemala
    # Spain
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

        # Sort by category first,
        # then channel name.
        items.sort(
            key=lambda item: (
                get_category(
                    item["channel"]
                ),
                item["channel"].get(
                    "name",
                    ""
                ).lower(),
                item["feed"].get(
                    "name",
                    ""
                ).lower(),
            )
        )

        print()

        print(
            f"{TARGET_COUNTRIES[country_code]}: "
            f"{len(items)} channels"
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

            # Prevent duplicate URLs
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
    # Add worldwide public playlists
    # --------------------------------------------------------

    print()

    print(
        "=========================================="
    )

    print(
        "Loading worldwide playlists..."
    )

    print(
        "=========================================="
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

    print()

    print(
        "Writing final playlist..."
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="\r\n"
    ) as file:

        file.write(
            "#EXTM3U\n"
        )

        # EPG sources
        file.write(
            'x-tvg-url="'
            + ",".join(
                EPG_URLS
            )
            + '"\n'
        )

        # Channels
        for extinf, stream_url in output_entries:

            file.write(
                extinf + "\n"
            )

            file.write(
                stream_url + "\n"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()

    print(
        "=========================================="
    )

    print(
        "BUILD COMPLETE"
    )

    print(
        "=========================================="
    )

    print(
        f"FINAL PLAYLIST: "
        f"{len(output_entries)} unique streams"
    )

    print(
        f"Playlist written to: {OUTPUT}"
    )

    print()


if __name__ == "__main__":
    main()
