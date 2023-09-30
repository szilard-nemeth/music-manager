import re
from typing import Iterable

from pythoncommons.string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs, HtmlParser

import logging

CURRENT_TRACK_PREFIX = "Current track: "
LOG = logging.getLogger(__name__)

UNKNOWN_TITLE = "unknown_title"
UNKNOWN_CONTENT = "unknown_content"
SOUNDCLOUD_NORMAL_URL = "soundcloud.com"
SOUNDCLOUD_GOOGLE_URL = "soundcloud.app.goo.gl"


@auto_str
class SoundCloud(ContentProviderAbs):
    HTML_TITLE_PATTERN = re.compile(r"Stream (.*) by(.*) \| Listen online for free on SoundCloud")

    def __init__(self):
        # Build a cache of url to title
        self._title_cache = {}

    @classmethod
    def url_matchers(cls) -> Iterable[str]:
        return [SOUNDCLOUD_NORMAL_URL, SOUNDCLOUD_GOOGLE_URL]

    def is_media_provider(self):
        return True

    def can_handle_url(self, url):
        if SOUNDCLOUD_NORMAL_URL in url or SOUNDCLOUD_GOOGLE_URL in url:
            return True
        return False

    def emit_links(self, url):
        return []

    def create_intermediate_entity(self, url: str) -> IntermediateMusicEntity:
        title = self._determine_title_by_url(url)
        if not title:
            return IntermediateMusicEntity.not_found(url)
        duration = self._determine_duration_by_url(url)
        ent_type = self._determine_entity_type(duration)
        return IntermediateMusicEntity(title, duration, ent_type, url)

    def _determine_title_by_url(self, url: str) -> str or None:
        # Example HTML title:
        # Stream Worlds Within Mix [Endangered] 040722_Berlin by Brian Cid | Listen online for free on SoundCloud
        # Where title is: 'Worlds Within Mix [Endangered] 040722_Berlin'
        soup = HtmlParser.create_bs_from_url(url)
        html_title = HtmlParser.get_title_from_url(url)
        track_not_found = HtmlParser.find_divs_with_class(soup, "blockedTrackMessage")
        if track_not_found or html_title.startswith("SoundCloud - Hear the world"):
            return None
        m = re.match(SoundCloud.HTML_TITLE_PATTERN, html_title)
        if len(m.groups()) != 2:
            raise ValueError("Unexpected Soundcloud HTML title: {}".format(html_title))
        title = m.group(1)
        author = m.group(2)
        self._title_cache[url] = title
        return title

    def _determine_duration_by_url(self, url: str) -> Duration:
        if self._title_cache[url]:
            main_title = self._title_cache[url]
        else:
            main_title = self._determine_title_by_url(url)
        title_at_bottom_player, soup = self._get_title_of_bottom_player(url)
        if title_at_bottom_player == UNKNOWN_TITLE:
            LOG.error("Cannot determine title from the bottom player for URL: '%s', therefore duration is unknown!", url)
            return Duration.unknown()
        elif title_at_bottom_player != main_title:
            LOG.error("Conflicting titles! Main title: '%s', title in the bottom player: '%s'", main_title, title_at_bottom_player)
            return Duration.unknown()

        # Safe to determine duration
        playback_divs = HtmlParser.find_divs_with_class(soup, "playbackTimeline__duration")
        if len(playback_divs) != 1:
            return Duration.unknown()

        raw_duration = self._get_content_from_span(playback_divs[0])
        return Duration.of_string(raw_duration)

    def _get_title_of_bottom_player(self, url):
        """
        <div class="playbackSoundBadge__title">
            <a href="<link>" class="playbackSoundBadge__titleLink sc-truncate sc-text-h5 sc-link-primary" title="$$TITLE$$">
                <span class="sc-visuallyhidden">Current track: $$TITLE$$</span>
                <span aria-hidden="true">$$TITLE$$</span>
             </a>
        </div>
        Args:
            url:

        Returns:

        """
        soup = HtmlParser.js_renderer.render_with_javascript(url, force_use_requests=True)
        title_divs = HtmlParser.find_divs_with_class(soup, "playbackSoundBadge__title")
        if len(title_divs) != 1:
            return UNKNOWN_TITLE, None

        raw_title = self._get_content_from_span(title_divs[0])
        if raw_title == UNKNOWN_CONTENT:
            return UNKNOWN_TITLE, None
        if raw_title.startswith(CURRENT_TRACK_PREFIX):
            title = raw_title[len(CURRENT_TRACK_PREFIX):]
            return title, soup
        else:
            return raw_title, soup

    @staticmethod
    def _get_content_from_span(tag):
        spans = tag.find_all("span", attrs={"sc-visuallyhidden"})
        if len(spans) != 1:
            return UNKNOWN_CONTENT

        span_without_class = spans[0].find_next()
        if len(span_without_class) != 1:
            return UNKNOWN_CONTENT

        raw_text = span_without_class.text
        return raw_text.lstrip().rstrip()
