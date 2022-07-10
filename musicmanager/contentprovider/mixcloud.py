import re
from typing import Iterable

from string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity, MusicEntityType
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs, HtmlParser

NORMAL_URL = "mixcloud.com"


@auto_str
class Mixcloud(ContentProviderAbs):
    HTML_TITLE_PATTERN = re.compile(r"(.*) by(.*) \| Mixcloud")

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

    def create_intermediate_entity(self, url: str) -> IntermediateMusicEntity:
        title = self._determine_title_by_url(url)
        duration = self._determine_duration_by_url(url)
        return IntermediateMusicEntity(title, duration, MusicEntityType.MIX, url)

    def _determine_title_by_url(self, url: str) -> str:
        html_title = HtmlParser.get_title_from_url(url)
        if html_title == "Mixcloud":
            html_title = HtmlParser.get_title_from_url_with_js(url)

        # Example HTML title:
        # Steve March - Music Is My Religion // Episode 5 (2022-02-04) by Steve March | Mixcloud
        # Where title is: 'Steve March - Music Is My Religion // Episode 5 (2022-02-04)'
        m = re.match(Mixcloud.HTML_TITLE_PATTERN, html_title)
        if len(m.groups()) != 2:
            raise ValueError("Unexpected Mixcloud HTML title: {}".format(html_title))
        title = m.group(1)
        author = m.group(2)
        return title

    def _determine_duration_by_url(self, url: str) -> Duration:
        return Duration.unknown()
