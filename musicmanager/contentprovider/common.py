from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Set

from musicmanager.common import Duration
import logging
LOG = logging.getLogger(__name__)


class ContentProviderAbs(ABC):
    @abstractmethod
    def can_handle_url(self, url):
        pass

    @abstractmethod
    def emit_links(self, url) -> Set[str]:
        pass

    @abstractmethod
    def determine_duration_by_url(self, url: str) -> Tuple[Duration, str]:
        pass

    @abstractmethod
    def is_media_provider(self):
        pass
