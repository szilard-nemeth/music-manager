import logging
import re
from typing import Tuple, Set

import requests
from requests import Response
from string_utils import auto_str

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

BS4_HTML_PARSER = "html.parser"

FACEBOOK_URL_FRAGMENT1 = "facebook.com"
FACEBOOK_REDIRECT_LINK = "https://l.facebook.com/l.php"
LOG = logging.getLogger(__name__)
from bs4 import BeautifulSoup, Comment
from requests_html import HTMLSession


def create_bs(url):
    return BeautifulSoup(url, features=BS4_HTML_PARSER)


@auto_str
class Facebook(ContentProviderAbs):
    def is_media_provider(self):
        return False

    def can_handle_url(self, url):
        if FACEBOOK_URL_FRAGMENT1 in url:
            return True
        return False

    def determine_duration_by_url(self, url: str) -> Tuple[Duration, str]:
        return Duration.unknown(), url

    def emit_links(self, url) -> Set[str]:
        LOG.info("Emitting links from provider '%s'", self)
        resp = requests.get(url)
        soup = create_bs(resp.text)
        data = soup.findAll('div', attrs={'class': 'userContentWrapper'})

        if not data:
            links = self._find_links_in_html_comments(url, soup)
            if not links:
                links = self._parse_page_with_javascript(url)
        return links

    def _parse_page_with_javascript(self, url):
        LOG.info("Falling back to Javascript-rendered webpage scraping for URL '%s'", url)
        session = HTMLSession()
        r: Response = session.get(url)
        r.html.render()
        links = r.html.links
        filtered_links = self._filter_facebook_redirect_links(links)
        LOG.debug("[orig: %s] Found links on rendered page: %s", url, filtered_links)

        final_links = set()
        for link in filtered_links:
            unescaped_link = Facebook._get_final_link_from_fb_redirect_link(link, url)
            final_links.add(unescaped_link)
        return final_links

    @staticmethod
    def _find_links_in_html_comments(url, soup) -> Set[str]:
        # Find in comments
        # Data can be in:
        # <div class="hidden_elem">
        #   <code id="u_0_m_lP">
        #   <!-- <div class="_4-u2 mbm _4mrt _5v3q _7cqq _4-u8" id="u_0_b_Ga">
        #          <div class="_3ccb" data-ft="&#123;&quot;tn&quot;:&quot;-R&quot;&#125;" data-gt="&#123;&quot;type&quot;:&quot;click2canvas&quot;,&quot;fbsource&quot;:703,&quot;ref&quot;:&quot;nf_generic&quot;&#125;" id="u_0_d_Q9">
        #          <div>
        #          </div>
        #          <div class="_5pcr userContentWrapper"
        found_links = set()
        comments = soup.find_all(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment_soup = create_bs(comment)
            divs = comment_soup.find_all('div', attrs={'class': 'userContentWrapper'})
            for div in divs:
                links = div.findAll('a')
                orig_links = [a['href'] for a in links]
                fb_redirect_links = Facebook._filter_facebook_redirect_links(orig_links)
                for redir_link in fb_redirect_links:
                    unescaped_link = Facebook._get_final_link_from_fb_redirect_link(redir_link, url)
                    found_links.add(unescaped_link)
        LOG.debug("[orig: %s] Found links: %s", url, found_links)
        return found_links

    @staticmethod
    def _get_final_link_from_fb_redirect_link(link, orig_url):
        resp = requests.get(link)
        # Example URL: https://l.facebook.com/l.php?u=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3DcI6tWuNlwZ4%26feature%3Dshare&h=AT2ELdFoLuLKA4TH-ft6vMySk5HQWZq6KNRPxHvdlBxOWqr4vYi-iujE5SaUn9oLwZLFYOvQsvcDo7JDUQ7yX2REXm7CIk3mJnPrXXWlMYxzh5uEVWeZwLFZlR0iZvTGIlnCiPseDFGbctntdYSg4456Prq-Oqc-ZT8aRR8QBNYC2A_DvNzzftV-al8RVSQSxI2N8Xw
        # Will give something like:
        # <script type="text/javascript" nonce="Fb99FNm1">
        #       document.location.replace("https:\\/\\/youtube.com\\/watch?v=cI6tWuNlwZ4&feature=share");
        # </script>
        LOG.debug("[orig: %s] Response of link '%s': %s", orig_url, link, resp.text)
        match = re.search(r"document\.location\.replace\(\"(.*)\"\)", resp.text)
        # TODO Error handling for not found group(1)
        found_group = match.group(1)
        unescaped_link = found_group.replace("\\/", "/")
        LOG.debug(unescaped_link)
        return unescaped_link

    @staticmethod
    def _filter_facebook_redirect_links(links) -> Set[str]:
        filtered_links = set(filter(lambda x: FACEBOOK_REDIRECT_LINK in x, links))
        return filtered_links

    @staticmethod
    def string_escape(s, encoding='utf-8'):
        # TODO remove?
        return (s.encode('latin1')  # To bytes, required by 'unicode-escape'
                .decode('unicode-escape')  # Perform the actual octal-escaping decode
                .encode('latin1')  # 1:1 mapping back to bytes
                .decode(encoding))

