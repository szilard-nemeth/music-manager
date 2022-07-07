from typing import Tuple, Iterable

from string_utils import auto_str

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

SOUNDCLOUD_URL = "soundcloud.com"


@auto_str
class SoundCloud(ContentProviderAbs):
    def url_matchers(self) -> Iterable[str]:
        return [SOUNDCLOUD_URL]

    def is_media_provider(self):
        return True

    def can_handle_url(self, url):
        if SOUNDCLOUD_URL in url:
            return True
        return False

    def emit_links(self, url):
        return []

    def determine_duration_by_url(self, url: str) -> Tuple[Duration, str]:
        return Duration.unknown(), url
