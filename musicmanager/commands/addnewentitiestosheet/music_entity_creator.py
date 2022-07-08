import logging
from enum import Enum
from typing import List, Tuple, Set, Iterable, Dict

from string_utils import auto_str

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

LOG = logging.getLogger(__name__)


class MusicEntityType(Enum):
    MIX = "mix"
    TRACK = "track"
    UNKNOWN = "unknown"


@auto_str
class MusicEntity:
    def __init__(self, data, duration: Duration, url: str, entity_type: MusicEntityType):
        self.url = url
        self.data = data
        self.duration: Duration = duration
        self.entity_type = entity_type

    @property
    def original_url(self):
        # TODO this could return incorrect URL
        return MusicEntityCreator._get_links_of_parsed_objs(self.data)


class MusicEntityCreator:
    def __init__(self, content_providers: List[ContentProviderAbs]):
        self.content_providers = content_providers

    def create_music_entities(self, parsed_objs):
        music_entities = []
        for obj in parsed_objs:
            links = MusicEntityCreator._get_links_of_parsed_objs(obj)
            LOG.info("Found links from source file: %s", links)
            durations: List[Tuple[Duration, str]] = self.check_links_against_providers(links, allow_emit=True)
            for duration_tup in durations:
                entity_type = MusicEntityCreator._determine_entity_type(duration_tup[0])
                entity = MusicEntity(obj, duration_tup[0], duration_tup[1], entity_type)
                music_entities.append(entity)
        LOG.debug("Created music entities: %s, ", music_entities)
        return music_entities

    @staticmethod
    def _get_links_of_parsed_objs(obj):
        links = [obj.link_1, obj.link_2, obj.link_3]
        links = list(filter(None, links))
        return links

    @staticmethod
    def _determine_entity_type(duration):
        entity_type = MusicEntityType.UNKNOWN
        if 0 < duration.minutes <= 12:
            entity_type = MusicEntityType.TRACK
        elif duration.minutes > 12:
            entity_type = MusicEntityType.MIX
        return entity_type

    def check_links_against_providers(self, links: Iterable[str], allow_emit=False) -> List[Tuple[Duration, str]]:
        all_links: List[Tuple[Duration, str]] = []
        for link in links:
            link_handled = False
            for provider in self.content_providers:
                LOG.debug("Checking if provider '%s' can handle link: %s", provider, link)
                if provider.can_handle_url(link):
                    link_handled = True
                    if not provider.is_media_provider() and allow_emit:
                        emitted_links: Dict[str, None] = provider.emit_links(link)
                        LOG.debug("Emitted links: %s", emitted_links)
                        res = self.check_links_against_providers(emitted_links, allow_emit=False)
                        if not res:
                            LOG.error("No valid links found for URL '%s'", link)
                        all_links.extend(res)
                    else:
                        all_links.append(provider.determine_duration_by_url(link))

            if not link_handled:
                # TODO Make a CLI option for this whether to store unknown links
                LOG.error("Found link that none of the providers can handle: %s", link)
        return all_links
