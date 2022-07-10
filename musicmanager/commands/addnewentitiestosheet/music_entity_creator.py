import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Iterable, Dict, Any, Set

from string_utils import auto_str

from musicmanager.common import Duration, CLI_LOG
from musicmanager.services.services import URLResolutionServices

LOG = logging.getLogger(__name__)


class MusicEntityType(Enum):
    MIX = "mix"
    TRACK = "track"
    UNKNOWN = "unknown"
    NOT_FOUND = "not_found"


@auto_str
class MusicEntity:
    def __init__(self, title: str, duration: Duration, url: str, src_url: str, entity_type: MusicEntityType):
        self.title = title
        self.duration: Duration = duration
        self.url = url
        self.src_url = src_url
        self.entity_type = entity_type

    @property
    def original_url(self):
        # TODO this could return incorrect URL
        # return MusicEntityCreator.get_links_of_parsed_objs(self.data)
        return self.src_url


@dataclass
class GroupedMusicEntity:
    data: Any
    source_urls: Iterable[str]
    entities: List[MusicEntity] = field(default_factory=list)
    title: str = None
    type: MusicEntityType = None
    links: Set[str] = field(default_factory=set)

    def add(self, entity):
        self.entities.append(entity)

    def finalize_and_validate(self):
        self._validate_entity_type()
        self._validate_title()
        self._finalize_links()

    def _validate_entity_type(self):
        entity_types = set(map(lambda e: e.entity_type, self.entities))
        if len(entity_types) > 1:
            raise ValueError("Conflicting entity type for {}. Entities: {}".format(self.__class__, self.entities))
        self.entity_type = list(entity_types)[0]

    def _validate_title(self):
        titles = set(map(lambda e: e.title, self.entities))
        # TODO Titles can be different, example: Post main content is a mix, but another mix / track found in the comments section
        # if len(titles) > 1:
        #     raise ValueError("Conflicting entity titles for {}. Entities: {}".format(self.__class__, self.entities))
        self.entity_title = list(titles)[0]

    def _finalize_links(self):
        self.links = set(map(lambda e: e.url, self.entities))


@dataclass
class IntermediateMusicEntity:
    title: str
    duration: Duration
    type: MusicEntityType
    url: str
    src_url: str = None

    @classmethod
    def not_found(cls, src_url):
        return IntermediateMusicEntity("N/A", Duration.unknown(), MusicEntityType.NOT_FOUND, "N/A", src_url)


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
            src_urls = MusicEntityCreator.get_links_of_parsed_objs(obj)
            LOG.info("Found links from source file: %s", src_urls)
            entities: IntermediateMusicEntities = IntermediateMusicEntities(src_urls)
            intermediate_entities: IntermediateMusicEntities = self.check_links_against_providers(entities, src_urls, src_url="unknown", allow_emit=True)
            # TODO Also group for same title / same URL --> e.g. file with duplicated lines
            grouped_entity = MusicEntityCreator.create_from_intermediate_entities(obj, intermediate_entities)
            CLI_LOG.info("Found links for: %s: %s", grouped_entity.source_urls, grouped_entity.entities)
            result.append(grouped_entity)
        LOG.debug("Created grouped music entities: %s", result)
        return result

    @staticmethod
    def create_from_intermediate_entities(obj, intermediate_entities: IntermediateMusicEntities) -> GroupedMusicEntity:
        src_urls = MusicEntityCreator.get_links_of_parsed_objs(obj)
        grouped_entity = GroupedMusicEntity(obj, src_urls)
        for ie in intermediate_entities:
            # TODO MusicEntity vs. IntermediateMusicEntity: Could be merged?
            entity = MusicEntity(ie.title, ie.duration, ie.url, ie.src_url, ie.type)
            grouped_entity.add(entity)
        return grouped_entity

    @staticmethod
    def get_links_of_parsed_objs(obj):
        # TODO Direct reference to dynamic fields (link_1, link_2, link_3)
        links = [obj.link_1, obj.link_2, obj.link_3]
        links = list(filter(None, links))
        return links

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
                        entity: IntermediateMusicEntity = provider.create_intermediate_entity(url)
                        if entity:
                            entity.src_url = src_url
                            entities.add(entity)

            if not link_handled:
                # TODO Make a CLI option for this whether to store unknown links
                LOG.error("Found link that none of the providers can handle: %s", url)
        return entities
