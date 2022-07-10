import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Iterable, Dict
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from requests import Response
from requests_html import HTMLSession

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration

LOG = logging.getLogger(__name__)
BS4_HTML_PARSER = "html.parser"


class HtmlParser:
    @staticmethod
    def create_bs(html) -> BeautifulSoup:
        return BeautifulSoup(html, features=BS4_HTML_PARSER)

    @staticmethod
    def find_divs_with_text(soup: BeautifulSoup, text: str):
        return soup.find_all("div", string=text)

    @staticmethod
    def find_divs_with_class(soup: BeautifulSoup, cl: str):
        return soup.findAll('div', attrs={'class': cl})

    @staticmethod
    def find_links_in_div(div: Tag):
        anchors = div.findAll('a')
        # TODO duplicated code fragment
        filtered_anchors = list(filter(lambda a: 'href' in a.attrs, anchors))
        links = [a['href'] for a in filtered_anchors]
        LOG.info("Found links: %s", links)
        return links

    @staticmethod
    def find_all_links(soup: BeautifulSoup):
        anchors = soup.findAll("a")
        filtered_anchors = list(filter(lambda a: 'href' in a.attrs, anchors))
        links = [a['href'] for a in filtered_anchors]
        LOG.info("Found links: %s", links)
        return links

    @classmethod
    def filter_links_by_url_fragment(cls, links, url_fragment):
        filtered_links = set(filter(lambda x: url_fragment in x, links))
        return filtered_links

    @classmethod
    def remove_query_param_from_url(cls, url, param_name):
        u = urlparse(url)
        query = parse_qs(u.query, keep_blank_values=True)
        query.pop(param_name, None)
        u = u._replace(query=urlencode(query, True))
        return urlunparse(u)

    @staticmethod
    def get_link_from_standard_redirect_page(orig_url, src_url):
        resp = requests.get(src_url)
        LOG.debug("[orig: %s] Response of link '%s': %s", orig_url, src_url, resp.text)
        match = re.search(r"document\.location\.replace\(\"(.*)\"\)", resp.text)
        # TODO Error handling for not found group(1)
        found_group = match.group(1)
        unescaped_link = found_group.replace("\\/", "/")
        LOG.debug("Link '%s' resolved to '%s'", src_url, unescaped_link)
        return unescaped_link


class ContentProviderAbs(ABC):
    @abstractmethod
    def can_handle_url(self, url):
        pass

    @abstractmethod
    def emit_links(self, url) -> Dict[str, None]:
        pass

    @abstractmethod
    def create_intermediate_entity(self, url: str) -> IntermediateMusicEntity:
        pass

    @abstractmethod
    def _determine_duration_by_url(self, url: str) -> Duration:
        pass

    @abstractmethod
    def _determine_title_by_url(self, url: str) -> Duration:
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
            return HtmlParser.create_bs(html_content)
        elif self.use_selenium:
            return self.fb_selenium.load_url_as_soup(url)

    @staticmethod
    def _render_with_requests_html(url):
        session = HTMLSession()
        resp: Response = session.get(url)
        resp.html.render(timeout=20)
        html_content = resp.html.html
        return html_content

