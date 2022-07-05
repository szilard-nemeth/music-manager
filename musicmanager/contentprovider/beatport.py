import logging
from typing import Tuple

from string_utils import auto_str

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

BEATPORT_URL = "beatport.com"
LOG = logging.getLogger(__name__)


@auto_str
class Beatport(ContentProviderAbs):
    def is_media_provider(self):
        return True

    def can_handle_url(self, url):
        if BEATPORT_URL in url:
            return True
        return False

    def emit_links(self, url):
        return []

    def determine_duration_by_url(self, url: str) -> Tuple[Duration, str]:
        return Duration.unknown(), url
