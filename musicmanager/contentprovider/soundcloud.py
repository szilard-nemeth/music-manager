from typing import Iterable

from string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs, HtmlParser

SOUNDCLOUD_NORMAL_URL = "soundcloud.com"
SOUNDCLOUD_GOOGLE_URL = "soundcloud.app.goo.gl"


@auto_str
class SoundCloud(ContentProviderAbs):
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
        return IntermediateMusicEntity(title, duration, url)

    def _determine_title_by_url(self, url: str) -> str:
        return HtmlParser.get_title_from_url(url)

    def _determine_duration_by_url(self, url: str) -> Duration:
        return Duration.unknown()
