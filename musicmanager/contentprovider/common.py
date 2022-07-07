from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Set, Iterable

from bs4 import BeautifulSoup
from requests_html import HTMLSession
from requests import Response

from musicmanager.commands.addnewentitiestosheet.add_new_music_entity_cmd import JavaScriptRenderer
from musicmanager.common import Duration
import logging

from musicmanager.contentprovider.facebook import create_bs, FacebookSelenium

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
    def __init__(self, js_renderer_type: JavaScriptRenderer, selenium: FacebookSelenium):
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
            return create_bs(html_content)
        elif self.use_selenium:
            return self.fb_selenium.load_url_as_soup(url)


    @staticmethod
    def _render_with_requests_html(url):
        session = HTMLSession()
        resp: Response = session.get(url)
        resp.html.render(timeout=20)
        html_content = resp.html.html
        return html_content

