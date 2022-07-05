import re
from typing import Tuple, Set, Iterable

import logging
import pickle
import re
from typing import Tuple, Set
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from requests import Response
from selenium.common import ElementNotVisibleException, ElementNotSelectableException, NoSuchElementException, \
    TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from string_utils import auto_str
from selenium import webdriver

from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

BS4_HTML_PARSER = "html.parser"
FACEBOOK_URL_FRAGMENT1 = "facebook.com"
FACEBOOK_REDIRECT_LINK = "https://l.facebook.com/l.php"
LOG = logging.getLogger(__name__)
from bs4 import BeautifulSoup, Comment
from requests_html import HTMLSession


def create_bs(html):
    return BeautifulSoup(html, features=BS4_HTML_PARSER)


@auto_str
class Facebook(ContentProviderAbs):
    HEADERS = {
        "accept-language": "en-US,en;q=0.9"
    }

    def __init__(self, config):
        self.config = config
        self.fb_selenium = FacebookSelenium(self.config)
        self.urls_to_match = None

    def url_matchers(self) -> Iterable[str]:
        return [FACEBOOK_REDIRECT_LINK]

    def is_media_provider(self):
        return False

    def can_handle_url(self, url):
        if FACEBOOK_URL_FRAGMENT1 in url:
            return True
        return False

    def determine_duration_by_url(self, url: str) -> Tuple[Duration, str]:
        return Duration.unknown(), url

    def emit_links(self, url) -> Set[str]:
        # TODO Introduce new class that ties together FB link parsing: FacebookLinkParser?
        LOG.info("Emitting links from provider '%s'", self)
        resp = requests.get(url, headers=Facebook.HEADERS)
        soup = create_bs(resp.text)

        private_post = self._find_private_fb_post_div(soup)
        private_group_post = self._find_private_fb_group_div(soup)

        private_group_soup = None
        if all([not private_post, not private_group_post]):
            # Try to read page with JS
            resp = Facebook._render_url_with_javascript(url)
            soup = create_bs(resp.html.html)
            private_group_post = self._find_private_fb_group_div(soup)
            if not private_group_post:
                # Finally, try with Selenium
                private_group_soup = self.fb_selenium.load_url_as_soup(url)
                private_group_post = self._find_private_fb_group_div(private_group_soup)

        if private_post:
            # Private FB post content
            links = self.fb_selenium.load_links_from_private_content(url)
            return self._filter_links(links)
        elif private_group_post:
            # Private FB group content
            if private_group_soup:
                links = self.fb_selenium.load_links_from_private_content_soup(private_group_soup)
            else:
                links = self.fb_selenium.load_links_from_private_content(url)
            return self._filter_links(links)
        else:
            # Public FB post
            data = soup.findAll('div', attrs={'class': 'userContentWrapper'})
            if not data:
                links = self._find_links_in_html_comments(url, soup)
                if not links:
                    LOG.info("Falling back to Javascript-rendered webpage scraping for URL '%s'", url)
                    links = self._find_links_with_js_rendering(url)
                return links
            else:
                # TODO implement?
                pass

    @staticmethod
    def _find_private_fb_post_div(soup):
        return soup.find_all("div", string="You must log in to continue.")

    @staticmethod
    def _find_private_fb_group_div(soup):
        return soup.find_all("div", string="Private group")

    def _filter_links(self, links, remove_fbclid=True):
        filtered_links = set()
        for link in links:
            for url_to_match in self.urls_to_match:
                if url_to_match in link:
                    if remove_fbclid:
                        mod_link = self._remove_fbclid(link)
                        filtered_links.add(mod_link)
                    else:
                        filtered_links.add(link)
                    break
        return filtered_links

    @staticmethod
    def _remove_fbclid(url):
        u = urlparse(url)
        query = parse_qs(u.query, keep_blank_values=True)
        query.pop('fbclid', None)
        u = u._replace(query=urlencode(query, True))
        return urlunparse(u)

    def _find_links_with_js_rendering(self, url):
        resp = self._render_url_with_javascript(url)
        links = resp.html.links
        filtered_links = self._filter_facebook_redirect_links(links)
        LOG.debug("[orig: %s] Found links on JS rendered page: %s", url, filtered_links)

        final_links = set()
        for link in filtered_links:
            unescaped_link = Facebook._get_final_link_from_fb_redirect_link(link, url)
            final_links.add(unescaped_link)
        return final_links

    @staticmethod
    def _render_url_with_javascript(url):
        session = HTMLSession()
        resp: Response = session.get(url)
        resp.html.render()
        return resp

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


class FacebookSelenium:
    CHROME_OPT_SELENIUM_PROFILE = "user-data-dir=selenium"
    COOKIES_FILE = "cookies.pkl"
    FACEBOOK_COM = 'https://www.facebook.com/'

    FEELING_BUTTON_TEXT = "Feeling/activity"
    FEELING_BUTTON_XPATH = '//span[text()="' + FEELING_BUTTON_TEXT + '"]'

    COOKIE_BUTTON_TEXT = "Allow essential and optional cookies"
    COOKIE_ACCEPT_BUTTON_XPATH = '//button[text()="' + COOKIE_BUTTON_TEXT + '"]'

    def __init__(self, config):
        self.config = config
        self.chrome_options = None
        self.driver = None

    def load_links_from_private_content(self, url):
        LOG.info("Loading private Facebook post content...")
        soup = self.load_url_as_soup(url)
        return self._find_links_in_soup(soup)

    def load_links_from_private_content_soup(self, soup):
        LOG.info("Loading private Facebook post content...")
        return self._find_links_in_soup(soup)

    def load_url_as_soup(self, url) -> BeautifulSoup:
        self._init_webdriver()
        self.driver.get(self.FACEBOOK_COM)
        loaded = self._wait_for_fb_page_load(timeout=5, throw_exception=False)
        if not loaded:
            self._do_initial_login()
        self.driver.get(url)
        html = self.driver.page_source
        return create_bs(html)

    def _init_webdriver(self):
        if not self.chrome_options:
            self.chrome_options = Options()
            self.chrome_options.add_argument(self.CHROME_OPT_SELENIUM_PROFILE)
        if not self.driver:
            self.driver = webdriver.Chrome(chrome_options=self.chrome_options)

    @staticmethod
    def _find_links_in_soup(soup: BeautifulSoup):
        links = soup.findAll("a")
        orig_links = [a['href'] for a in links]
        orig_links = set(orig_links)
        print("links: " + str(orig_links))
        return orig_links

    def _wait_for_fb_page_load(self, timeout, throw_exception=False):
        try:
            wait = WebDriverWait(self.driver, timeout=timeout, poll_frequency=4,
                                 ignored_exceptions=[NoSuchElementException, ElementNotVisibleException,
                                                     ElementNotSelectableException])
            success = wait.until(expected_conditions.element_to_be_clickable((By.XPATH, self.FEELING_BUTTON_XPATH)))
            return success
        except TimeoutException as e:
            if throw_exception:
                raise e
        return None

    def _do_initial_login(self):
        self.driver.get(self.FACEBOOK_COM)

        try:
            cookie_accept_button = self._find_cookie_accept_button()
            cookie_accept_button.click()
        except NoSuchElementException:
            logging.exception("An exception was thrown!")

        username_input = self.driver.find_element(By.ID, 'email')
        username_input.send_keys(self.config.fb_username)
        passwd_input = self.driver.find_element(By.ID, 'pass')
        passwd_input.send_keys(self.config.fb_password)
        login_button = self.driver.find_element(By.NAME, 'login')
        login_button.click()

        # Leave some time for manual 2FA authentication
        self._wait_for_fb_page_load(timeout=150, throw_exception=True)

    def _find_cookie_accept_button(self):
        return self.driver.find_element(By.XPATH, self.COOKIE_ACCEPT_BUTTON_XPATH)

    @staticmethod
    def _save_cookies(driver):
        pickle.dump(driver.get_cookies(), open(FacebookSelenium.COOKIES_FILE, "wb"))

    @staticmethod
    def _load_cookies(driver):
        try:
            cookies = pickle.load(open(FacebookSelenium.COOKIES_FILE, "rb"))
        except FileNotFoundError:
            print("Failed to load cookies from cookies.pkl")
            return
        for cookie in cookies:
            driver.add_cookie(cookie)
