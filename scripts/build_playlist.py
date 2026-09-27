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
SPORTS = "sports"

OUTPUT = Path("output/playlist.m3u")

# ------------------------------------------------------------
# Additional public playlists
# ------------------------------------------------------------

EXTERNAL_PLAYLISTS = {
    "🌎 Free TV Worldwide": (
        "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"
    ),

    "⚽ Sports Worldwide": (
        "https://iptv-org.github.io/iptv/categories/sports.m3u"
    ),

    "🎬 Movies Worldwide": (
        "https://iptv-org.github.io/iptv/categories/movies.m3u"
    ),

    "📺 Series Worldwide": (
        "https://iptv-org.github.io/iptv/categories/series.m3u"
    ),

    "🎭 Entertainment Worldwide": (
        "https://iptv-org.github.io/iptv/categories/entertainment.m3u"
    ),

    "📚 Documentary Worldwide": (
        "https://iptv-org.github.io/iptv/categories/documentary.m3u"
    ),

    "👨‍👩‍👧 Family Worldwide": (
        "https://iptv-org.github.io/iptv/categories/family.m3u"
    ),

    "👦 Kids Worldwide": (
        "https://iptv-org.github.io/iptv/categories/kids.m3u"
    ),

    "🎵 Music Worldwide": (
        "https://iptv-org.github.io/iptv/categories/music.m3u"
    ),
}


def download_text(url):
    print(f"Downloading {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "my-tv-playlist-builder/2.0"
        },
    )

    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(name):
    return json.loads(
        download_text(f"{API_BASE}/{name}.json")
    )


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


def has_target_area(feed):

    for area in feed.get("broadcast_area", []):
        if area.startswith("c/"):
            country = area[2:].upper()

            if country in TARGET_COUNTRIES:
                return country

    return None


def is_spanish(feed):
    return SPANISH in feed.get("languages", [])


def is_sports(channel):
    return SPORTS in channel.get("categories", [])


def stream_is_allowed(stream):

    labels = {
        str(label).lower()
        for label in stream.get("labels", [])
    }

    if "geo-blocked" in labels:
        return False

    if "not 24/7" in labels:
        return False

    url = stream.get("url", "")

    if not url.startswith(("http://", "https://")):
        return False

    return True


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
# Parse external M3U playlists
# ------------------------------------------------------------

def parse_m3u(text, default_group):

    entries = []

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    current_extinf = None

    for line in lines:

        if line.startswith("#EXTINF:"):
            current_extinf = line
            continue

        if line.startswith("#"):
            continue

        if current_extinf:

            url = line

            if url.startswith(("http://", "https://")):

                entries.append({
                    "extinf": current_extinf,
                    "url": url,
                    "group": default_group,
                })

            current_extinf = None

    return entries


def replace_group_title(extinf, group):

    new_group = clean_text(group)

    pattern = r'group-title="[^"]*"'

    replacement = f'group-title="{new_group}"'

    if re.search(pattern, extinf):
        return re.sub(pattern, replacement, extinf)

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

        text = download_text(url)

        entries = parse_m3u(text, name)

        added = 0

        for entry in entries:

            stream_url = entry["url"]

            # Prevent duplicates
            if stream_url in seen_urls:
                continue

            seen_urls.add(stream_url)

            extinf = replace_group_title(
                entry["extinf"],
                name
            )

            output_entries.append(
                (extinf, stream_url)
            )

            added += 1

        print(
            f"{name}: added {added} unique streams."
        )

    except Exception as error:

        print(
            f"WARNING: Could not load {name}: {error}"
        )


def main():

    print("Loading iptv-org data...")

    channels = fetch_json("channels")
    feeds = fetch_json("feeds")
    streams = fetch_json("streams")
    logos = fetch_json("logos")

    channel_by_id = {
        channel["id"]: channel
        for channel in channels
    }

    feeds_by_key = {}

    for feed in feeds:

        channel_id = feed.get("channel")
        feed_id = feed.get("id")

        if channel_id and feed_id:
            feeds_by_key[(channel_id, feed_id)] = feed

    logos_by_channel = {}

    for logo in logos:

        if not logo.get("in_use"):
            continue

        channel_id = logo.get("channel")

        if channel_id and channel_id not in logos_by_channel:
            logos_by_channel[channel_id] = logo.get("url")

    # ------------------------------------------------------------
    # Select original country streams
    # ------------------------------------------------------------

    selected = {}

    for stream in streams:

        channel_id = stream.get("channel")
        feed_id = stream.get("feed")

        if not channel_id:
            continue

        channel = channel_by_id.get(channel_id)

        if not channel:
            continue

        if channel.get("is_nsfw"):
            continue

        if not stream_is_allowed(stream):
            continue

        feed = feeds_by_key.get(
            (channel_id, feed_id)
        )

        if not feed:
            continue

        country = has_target_area(feed)

        if not country:
            continue

        key = (channel_id, feed_id)

        old = selected.get(key)

        if old is None:

            selected[key] = {
                "stream": stream,
                "channel": channel,
                "feed": feed,
                "country": country,
            }

        else:

            if (
                quality_score(stream)
                >
                quality_score(old["stream"])
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

    # ------------------------------------------------------------
    # Organize country channels
    # ------------------------------------------------------------

    country_groups = defaultdict(list)
    sports = []

    for item in selected.values():

        channel = item["channel"]

        if is_sports(channel):
            sports.append(item)

        country = item["country"]

        country_groups[country].append(item)

    for country in country_groups:

        country_groups[country].sort(
            key=lambda item: (
                item["channel"].get("name", ""),
                item["feed"].get("name", ""),
            )
        )

    sports.sort(
        key=lambda item: (
            item["country"],
            item["channel"].get("name", ""),
        )
    )

    # ------------------------------------------------------------
    # Build output
    # ------------------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Keep URLs unique across the entire playlist
    seen_urls = set()

    output_entries = []

    # ------------------------------------------------------------
    # Country sections
    # ------------------------------------------------------------

    for country_code in [
        "US",
        "CA",
        "GT",
        "ES"
    ]:

        items = country_groups.get(
            country_code,
            []
        )

        for item in items:

            channel = item["channel"]
            stream = item["stream"]
            feed = item["feed"]

            channel_id = channel["id"]

            channel_name = channel.get(
                "name",
                channel_id
            )

            feed_name = feed.get("name")

            display_name = channel_name

            if (
                feed_name
                and feed_name != channel_name
            ):
                display_name = (
                    f"{channel_name} - {feed_name}"
                )

            logo = logos_by_channel.get(
                channel_id
            )

            spanish = is_spanish(feed)

            language = (
                " Español"
                if spanish
                else ""
            )

            group = TARGET_COUNTRIES[
                country_code
            ]

            attributes = [
                f'tvg-id="{clean_text(channel_id)}"',
                f'group-title="{clean_text(group)}"',
            ]

            if logo:

                attributes.append(
                    f'tvg-logo="{clean_text(logo)}"'
                )

            if language:

                attributes.append(
                    'tvg-language="Español"'
                )

            extinf = (
                "#EXTINF:-1 "
                + " ".join(attributes)
                + ","
                + clean_text(display_name)
            )

            stream_url = stream["url"]

            if stream_url not in seen_urls:

                seen_urls.add(stream_url)

                output_entries.append(
                    (extinf, stream_url)
                )

    # ------------------------------------------------------------
    # Sports from original country selection
    # ------------------------------------------------------------

    for item in sports:

        channel = item["channel"]
        stream = item["stream"]
        feed = item["feed"]

        channel_id = channel["id"]

        channel_name = channel.get(
            "name",
            channel_id
        )

        feed_name = feed.get("name")

        display_name = channel_name

        if (
            feed_name
            and feed_name != channel_name
        ):
            display_name = (
                f"{channel_name} - {feed_name}"
            )

        logo = logos_by_channel.get(
            channel_id
        )

        country = item["country"]

        spanish = is_spanish(feed)

        if spanish:

            group = (
                "⚽ Sports - Español - "
                + TARGET_COUNTRIES[country]
            )

        else:

            group = (
                "⚽ Sports - "
                + TARGET_COUNTRIES[country]
            )

        attributes = [
            f'tvg-id="{clean_text(channel_id)}"',
            f'group-title="{clean_text(group)}"',
        ]

        if logo:

            attributes.append(
                f'tvg-logo="{clean_text(logo)}"'
            )

        if spanish:

            attributes.append(
                'tvg-language="Español"'
            )

        extinf = (
            "#EXTINF:-1 "
            + " ".join(attributes)
            + ","
            + clean_text(display_name)
        )

        stream_url = stream["url"]

        if stream_url not in seen_urls:

            seen_urls.add(stream_url)

            output_entries.append(
                (extinf, stream_url)
            )

    # ------------------------------------------------------------
    # External public playlists
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Write final playlist
    # ------------------------------------------------------------

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="\r\n"
    ) as file:

        file.write("#EXTM3U\n")

        file.write(
            'x-tvg-url="https://iptv-org.github.io/epg/guides/us/epg.xml"\n'
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
        f"FINAL PLAYLIST: {len(output_entries)} unique streams"
    )

    print(
        f"Playlist written to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
