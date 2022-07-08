import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Set, Iterable, Dict, Any

from string_utils import auto_str

from musicmanager.common import Duration, CLI_LOG
from musicmanager.services.services import URLResolutionServices

LOG = logging.getLogger(__name__)


class MusicEntityType(Enum):
    MIX = "mix"
    TRACK = "track"
    UNKNOWN = "unknown"


@auto_str
class MusicEntity:
    def __init__(self, duration: Duration, url: str, entity_type: MusicEntityType):
        self.url = url
        self.duration: Duration = duration
        self.entity_type = entity_type

    @property
    def original_url(self):
        # TODO this could return incorrect URL
        return MusicEntityCreator._get_links_of_parsed_objs(self.data)


@dataclass
class GroupedMusicEntity:
    data: Any
    source_urls: Iterable[str]
    entities: List[MusicEntity] = field(default_factory=list)

    def add(self, entity):
        self.entities.append(entity)


@dataclass
class IntermediateMusicEntity:
    duration: Duration
    url: str
    src_url: str = None


@dataclass
class IntermediateMusicEntities:
    source_urls: Iterable[str]
    entities: List[IntermediateMusicEntity] = field(default_factory=list)

    def __post_init__(self):
        self._index = 0

    def extend(self, other):
        self.entities.extend(other.entities)

    def add(self, entity):
        self.entities.append(entity)

    def __len__(self):
        return self.entities

    def __iter__(self):
        return self

    def __next__(self):
        if self._index == len(self.entities):
            raise StopIteration
        result = self.entities[self._index]
        self._index += 1
        return result


class MusicEntityCreator:
    def __init__(self, content_providers):
        self.content_providers = content_providers

    def create_music_entities(self, parsed_objs) -> List[GroupedMusicEntity]:
        result: List[GroupedMusicEntity] = []
        for obj in parsed_objs:
            src_urls = MusicEntityCreator._get_links_of_parsed_objs(obj)
            LOG.info("Found links from source file: %s", src_urls)
            entities: IntermediateMusicEntities = IntermediateMusicEntities(src_urls)
            intermediate_entities: IntermediateMusicEntities = self.check_links_against_providers(entities, src_urls, src_url="unknown", allow_emit=True)
            grouped_entity = MusicEntityCreator.create_from_intermediate_entities(obj, intermediate_entities)
            result.append(grouped_entity)
        LOG.debug("Created grouped music entities: %s", result)
        return result

    @staticmethod
    def create_from_intermediate_entities(obj, intermediate_entities: IntermediateMusicEntities) -> GroupedMusicEntity:
        src_urls = MusicEntityCreator._get_links_of_parsed_objs(obj)
        if not intermediate_entities.entities:
            CLI_LOG.info("Found links for: %s: %s", src_urls, [])

        grouped_entity = GroupedMusicEntity(obj, src_urls)
        for i_entity in intermediate_entities:
            entity_type = MusicEntityCreator._determine_entity_type(i_entity.duration)
            entity = MusicEntity(i_entity.duration, i_entity.url, entity_type)
            grouped_entity.add(entity)
            CLI_LOG.info("Found links for: %s: %s", grouped_entity.source_urls, entity.url)
        return grouped_entity

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

    def check_links_against_providers(self, entities: IntermediateMusicEntities, links: Iterable[str], src_url: str, allow_emit=False) -> IntermediateMusicEntities:
        for url in links:
            link_handled = False
            for provider in self.content_providers:
                LOG.debug("Checking if provider '%s' can handle link: %s", provider, url)
                if provider.can_handle_url(url):
                    link_handled = True
                    if not provider.is_media_provider() and allow_emit:
                        emitted_links: Dict[str, None] = provider.emit_links(url)
                        LOG.debug("Emitted links: %s", emitted_links)
                        for em_link in emitted_links.copy():
                            resolved_url = URLResolutionServices.resolve_url_with_services(em_link)
                            if resolved_url:
                                emitted_links[resolved_url] = None
                                del emitted_links[em_link]
                        res: IntermediateMusicEntities = self.check_links_against_providers(entities, emitted_links, src_url=url, allow_emit=False)
                        if not res.entities:
                            LOG.error("No valid links found for URL '%s'", url)
                    else:
                        entity: IntermediateMusicEntity = provider.determine_duration_by_url(url)
                        entity.src_url = src_url
                        entities.add(entity)

            if not link_handled:
                # TODO Make a CLI option for this whether to store unknown links
                LOG.error("Found link that none of the providers can handle: %s", url)
        return entities
