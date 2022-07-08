from typing import Tuple, Iterable

from string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

NORMAL_URL = "mixcloud.com"


@auto_str
class Mixcloud(ContentProviderAbs):
    @classmethod
    def url_matchers(cls) -> Iterable[str]:
        return [NORMAL_URL]

    def is_media_provider(self):
        return True

    def can_handle_url(self, url):
        if NORMAL_URL in url:
            return True
        return False

    def emit_links(self, url):
        return []

    def determine_duration_by_url(self, url: str) -> IntermediateMusicEntity:
        return IntermediateMusicEntity(Duration.unknown(), url)
