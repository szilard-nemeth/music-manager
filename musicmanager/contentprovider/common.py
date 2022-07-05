from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Set, Iterable
from requests_html import HTMLSession
from requests import Response

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

    @abstractmethod
    def url_matchers(self) -> Iterable[str]:
        pass


class JSRenderer:
    @staticmethod
    def render_url_with_javascript(url):
        session = HTMLSession()
        resp: Response = session.get(url)
        resp.html.render()
        return resp
