import logging
import re
from typing import Tuple, Set

import requests

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

FACEBOOK_URL_FRAGMENT1 = "facebook.com"
FACEBOOK_REDIRECT_LINK = "https://l.facebook.com/l.php"
LOG = logging.getLogger(__name__)
from bs4 import BeautifulSoup, Comment


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
        resp = requests.get(url)
        soup = BeautifulSoup(resp.text, features="html.parser")
        data = soup.findAll('div', attrs={'class': 'userContentWrapper'})

        if not data:
            return self._find_links_in_html_comments(url, soup)

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
            comment_soup = BeautifulSoup(comment)
            divs = comment_soup.find_all('div', attrs={'class': 'userContentWrapper'})
            for div in divs:
                links = div.findAll('a')
                orig_hrefs = [a['href'] for a in links]
                hrefs = list(filter(lambda x: FACEBOOK_REDIRECT_LINK in x, orig_hrefs))
                for href in hrefs:
                    resp = requests.get(href)
                    # Example URL: https://l.facebook.com/l.php?u=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3DcI6tWuNlwZ4%26feature%3Dshare&h=AT2ELdFoLuLKA4TH-ft6vMySk5HQWZq6KNRPxHvdlBxOWqr4vYi-iujE5SaUn9oLwZLFYOvQsvcDo7JDUQ7yX2REXm7CIk3mJnPrXXWlMYxzh5uEVWeZwLFZlR0iZvTGIlnCiPseDFGbctntdYSg4456Prq-Oqc-ZT8aRR8QBNYC2A_DvNzzftV-al8RVSQSxI2N8Xw
                    # Will give something like:
                    # <script type="text/javascript" nonce="Fb99FNm1">
                    #       document.location.replace("https:\\/\\/youtube.com\\/watch?v=cI6tWuNlwZ4&feature=share");
                    # </script>
                    LOG.debug(resp.text)
                    match = re.search(r"document\.location\.replace\(\"(.*)\"\)", resp.text)
                    found_group = match.group(1)
                    unescaped_link = found_group.replace("\\/", "/")
                    LOG.debug(unescaped_link)
                    found_links.add(unescaped_link)
        LOG.debug("[%s] Found links: %s", url, found_links)
        return found_links

    @staticmethod
    def string_escape(s, encoding='utf-8'):
        return (s.encode('latin1')  # To bytes, required by 'unicode-escape'
                .decode('unicode-escape')  # Perform the actual octal-escaping decode
                .encode('latin1')  # 1:1 mapping back to bytes
                .decode(encoding))

