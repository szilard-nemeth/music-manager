import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Set, Iterable, Dict

from bs4 import BeautifulSoup
from requests import Response
from requests_html import HTMLSession

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration


LOG = logging.getLogger(__name__)
BS4_HTML_PARSER = "html.parser"


class BeautifulSoupHelper:
    @staticmethod
    def create_bs(html) -> BeautifulSoup:
        return BeautifulSoup(html, features=BS4_HTML_PARSER)


class ContentProviderAbs(ABC):
    @abstractmethod
    def can_handle_url(self, url):
        pass

    @abstractmethod
    def emit_links(self, url) -> Dict[str, None]:
        pass

    @abstractmethod
    def determine_duration_by_url(self, url: str) -> IntermediateMusicEntity:
        pass

    @abstractmethod
    def is_media_provider(self):
        pass

    @classmethod
    @abstractmethod
    def url_matchers(cls) -> Iterable[str]:
        pass


class JavaScriptRenderer(Enum):
    REQUESTS_HTML = 'requests-html'
    SELENIUM = 'selenium'


class JSRenderer:
    def __init__(self, js_renderer_type: JavaScriptRenderer, selenium):
        self.use_requests_html = False
        self.use_selenium = False
        self.fb_selenium = selenium

        if js_renderer_type == JavaScriptRenderer.REQUESTS_HTML:
            self.use_requests_html = True
        elif js_renderer_type == JavaScriptRenderer.SELENIUM:
            self.use_selenium = True

    def render_with_javascript(self, url) -> BeautifulSoup:
        if self.use_requests_html:
            html_content = JSRenderer._render_with_requests_html(url)
            return BeautifulSoupHelper.create_bs(html_content)
        elif self.use_selenium:
            return self.fb_selenium.load_url_as_soup(url)


    @staticmethod
    def _render_with_requests_html(url):
        session = HTMLSession()
        resp: Response = session.get(url)
        resp.html.render(timeout=20)
        html_content = resp.html.html
        return html_content

