import re
from typing import Iterable

from string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs, HtmlParser

SOUNDCLOUD_NORMAL_URL = "soundcloud.com"
SOUNDCLOUD_GOOGLE_URL = "soundcloud.app.goo.gl"


@auto_str
class SoundCloud(ContentProviderAbs):
    HTML_TITLE_PATTERN = re.compile(r"Stream (.*) by(.*) \| Listen online for free on SoundCloud")

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
        duration = self._determine_duration_by_url(url)
        ent_type = self._determine_entity_type(duration)
        return IntermediateMusicEntity(title, duration, ent_type, url)

    def _determine_title_by_url(self, url: str) -> str:
        # Example HTML title:
        # Stream Worlds Within Mix [Endangered] 040722_Berlin by Brian Cid | Listen online for free on SoundCloud
        # Where title is: 'Worlds Within Mix [Endangered] 040722_Berlin'
        html_title = HtmlParser.get_title_from_url(url)
        m = re.match(SoundCloud.HTML_TITLE_PATTERN, html_title)
        if len(m.groups()) != 2:
            raise ValueError("Unexpected Soundcloud HTML title: {}".format(html_title))
        title = m.group(1)
        author = m.group(2)
        return title

    def _determine_duration_by_url(self, url: str) -> Duration:
        return Duration.unknown()
