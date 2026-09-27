#!/usr/bin/env python3

import json
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


def fetch_json(name):
    url = f"{API_BASE}/{name}.json"

    print(f"Downloading {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "my-tv-playlist-builder/1.0"
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


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
    """
    A feed can have broadcast areas such as:
        c/US
        c/CA
        c/GT
        c/ES

    We only keep the four countries we want.
    """

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
    """
    Prefer higher quality streams when several are available.
    """

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
    # Select streams
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

        feed = feeds_by_key.get((channel_id, feed_id))

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
            if quality_score(stream) > quality_score(old["stream"]):
                selected[key] = {
                    "stream": stream,
                    "channel": channel,
                    "feed": feed,
                    "country": country,
                }

    print(f"Selected {len(selected)} streams.")

    # ------------------------------------------------------------
    # Sort channels
    # ------------------------------------------------------------

    country_groups = defaultdict(list)
    sports = []

    for item in selected.values():

        channel = item["channel"]
        feed = item["feed"]

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
    # Write M3U
    # ------------------------------------------------------------

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8", newline="\r\n") as file:

        file.write("#EXTM3U\n")

        file.write(
            'x-tvg-url="https://iptv-org.github.io/epg/guides/us/epg.xml"\n'
        )

        # --------------------------------------------------------
        # Country sections
        # --------------------------------------------------------

        for country_code in ["US", "CA", "GT", "ES"]:

            items = country_groups.get(country_code, [])

            if not items:
                continue

            country_name = TARGET_COUNTRIES[country_code]

            for item in items:

                channel = item["channel"]
                stream = item["stream"]
                feed = item["feed"]

                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)
                feed_name = feed.get("name")

                display_name = channel_name

                if feed_name and feed_name != channel_name:
                    display_name = f"{channel_name} - {feed_name}"

                logo = logos_by_channel.get(channel_id)

                spanish = is_spanish(feed)

                language = " Español" if spanish else ""

                attributes = [
                    'tvg-id="{}"'.format(clean_text(channel_id)),
                    'group-title="{}"'.format(
                        clean_text(TARGET_COUNTRIES[country_code])
                    ),
                ]

                if logo:
                    attributes.append(
                        'tvg-logo="{}"'.format(clean_text(logo))
                    )

                if language:
                    attributes.append(
                        'tvg-language="Español"'
                    )

                file.write(
                    "#EXTINF:-1 "
                    + " ".join(attributes)
                    + ","
                    + clean_text(display_name)
                    + "\n"
                )

                file.write(stream["url"] + "\n")

        # --------------------------------------------------------
        # Sports section
        # --------------------------------------------------------

        if sports:

            for item in sports:

                channel = item["channel"]
                stream = item["stream"]
                feed = item["feed"]

                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)
                feed_name = feed.get("name")

                display_name = channel_name

                if feed_name and feed_name != channel_name:
                    display_name = f"{channel_name} - {feed_name}"

                logo = logos_by_channel.get(channel_id)

                country = item["country"]

                spanish = is_spanish(feed)

                # Sports group
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
                    'tvg-id="{}"'.format(clean_text(channel_id)),
                    'group-title="{}"'.format(clean_text(group)),
                ]

                if logo:
                    attributes.append(
                        'tvg-logo="{}"'.format(clean_text(logo))
                    )

                if spanish:
                    attributes.append(
                        'tvg-language="Español"'
                    )

                file.write(
                    "#EXTINF:-1 "
                    + " ".join(attributes)
                    + ","
                    + clean_text(display_name)
                    + "\n"
                )

                file.write(stream["url"] + "\n")

    print(f"Playlist written to {OUTPUT}")


if __name__ == "__main__":
    main()
