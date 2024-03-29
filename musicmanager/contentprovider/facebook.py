import logging
import pickle
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Callable, Dict, Any
from typing import Set
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from selenium import webdriver
from selenium.common import ElementNotVisibleException, ElementNotSelectableException, NoSuchElementException, \
    TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from pythoncommons.string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs, HtmlParser
from bs4 import BeautifulSoup
from bs4.element import Comment, Tag

FACEBOOK_URL_FRAGMENT1 = "facebook.com"
FACEBOOK_REDIRECT_LINK = "https://l.facebook.com/l.php"
LOG = logging.getLogger(__name__)


class FacebookPostType(Enum):
    PRIVATE_POST = "private_post"
    PRIVATE_GROUP_POST = "private_group_post"
    PUBLIC_POST = "public_post"
    PUBLIC_GROUP_POST = "public_group_post"
    PUBLIC = "public"


@dataclass
class FacebookPostTypeWithSoup:
    type: FacebookPostType
    soup: BeautifulSoup


class FacebookLinkEmitter:
    def __init__(self, js_renderer, fb_selenium, fb_link_parser):
        self.fb_link_parser = fb_link_parser
        self.fb_selenium = fb_selenium
        self.js_renderer = js_renderer

    def emit_links(self, url) -> Dict[str, None]:
        soup = HtmlParser.create_bs_from_url(url, headers=Facebook.HEADERS)
        # TODO This is wrong: Selenium will pop up for public Facebook content as well!
        ptws = self._determine_if_private(soup, url)
        if ptws.type in [FacebookPostType.PUBLIC_POST, FacebookPostType.PUBLIC]:
            return self._parse_links_from_public_post(ptws.soup, url)
        elif ptws.type == FacebookPostType.PRIVATE_POST or (ptws.type == FacebookPostType.PRIVATE_POST and not ptws.soup):
            links: List[str] = self.fb_selenium.load_links_from_private_content(url)
            return self.fb_link_parser.filter_links(links)
        elif ptws.type == FacebookPostType.PRIVATE_GROUP_POST:
            links: List[str] = self.fb_selenium.load_links_from_private_content_soup(ptws.soup)
            return self.fb_link_parser.filter_links(links)

    def _parse_links_from_public_post(self, soup, url) -> Dict[str, None] or None:
        def f1(parser, url, soup) -> Dict[str, None]:
            # TODO not implemented yet
            usr_content_wrapper_divs = parser.find_user_content_wrapper_divs(soup)
            if usr_content_wrapper_divs:
                return {}
            return {}

        def f2(parser, url, soup) -> Dict[str, None]:
            divs_wo_class = parser.find_divs_with_empty_class(soup)
            links = []
            for div in divs_wo_class:
                links.extend(FacebookLinkParser.find_links_in_div(div))
            return parser.filter_links(links)

        def f3(parser, url, soup) -> Dict[str, None]:
            return parser.find_links_in_html_comments(url, soup)

        def f4(parser, url, soup) -> Dict[str, None]:
            # Fall back to JS rendering
            LOG.info("Falling back to Javascript-rendered webpage scraping for URL '%s'", url)
            soup = parser.render_with_javascript(url)
            return parser.find_links_with_js_rendering(soup, url)

        return self._chained_func_calls([f1, f2, f3, f4], url, soup)

    def _chained_func_calls(self, f_calls: List[Callable[[Any, str, BeautifulSoup], Dict[str, None]]], url, soup) -> Dict[str, None]:
        for f_call in f_calls:
            ret = f_call(self.fb_link_parser, url, soup)
            if ret is not None and len(ret) > 0:
                return ret
        raise ValueError("Could not find any meaningful value from function calls: {}".format(f_calls))

    def _determine_if_private(self, soup, url) -> FacebookPostTypeWithSoup:
        private_post = self.fb_link_parser.find_private_fb_post_div(soup)
        private_group_post = self.fb_link_parser.find_private_fb_group_div(soup)

        if all([private_post, private_group_post]):
            raise ValueError("Determined URL '{}' to be private and private group post at the same time!")
        if private_post:
            return FacebookPostTypeWithSoup(FacebookPostType.PRIVATE_POST, soup)
        elif private_group_post:
            return FacebookPostTypeWithSoup(FacebookPostType.PRIVATE_GROUP_POST, soup)

        if all([not private_post, not private_group_post]):
            # TODO this should not run as it could be public FB post
            # Try to read page with Javascript (requests-html) or Selenium
            soup = self.js_renderer.render_with_javascript(url)
            private_group_post = self.fb_link_parser.find_private_fb_group_div(soup)
            if private_group_post:
                return FacebookPostTypeWithSoup(FacebookPostType.PRIVATE_GROUP_POST, soup)

            if not private_group_post and not self.js_renderer.use_selenium:
                # Finally, force try with Selenium
                soup = self.fb_selenium.load_url_as_soup(url)
                private_group_post = self.fb_link_parser.find_private_fb_group_div(soup)
                if private_group_post:
                    return FacebookPostTypeWithSoup(FacebookPostType.PRIVATE_GROUP_POST, soup)
                elif not private_post:
                    # We now that this is not a private and not a private group post
                    return FacebookPostTypeWithSoup(FacebookPostType.PUBLIC, soup)
                else:
                    return FacebookPostTypeWithSoup(FacebookPostType.PRIVATE_POST, soup)
            else:
                return FacebookPostTypeWithSoup(FacebookPostType.PUBLIC, soup)


@auto_str
class Facebook(ContentProviderAbs):
    HEADERS = {
        "accept-language": "en-US,en;q=0.9"
    }

    def __init__(self, config, js_renderer, fb_selenium, fb_link_parser):
        self.config = config
        self.fb_link_emitter = FacebookLinkEmitter(js_renderer, fb_selenium, fb_link_parser)

    @classmethod
    def url_matchers(cls) -> Iterable[str]:
        return [FACEBOOK_REDIRECT_LINK]

    def is_media_provider(self):
        return False

    def can_handle_url(self, url):
        if FACEBOOK_URL_FRAGMENT1 in url:
            return True
        return False

    def create_intermediate_entity(self, url: str) -> IntermediateMusicEntity:
        title = self._determine_title_by_url(url)
        duration = self._determine_duration_by_url(url)
        ent_type = self._determine_entity_type(duration)
        return IntermediateMusicEntity(title, duration, ent_type, url)

    def _determine_title_by_url(self, url: str) -> str:
        return HtmlParser.get_title_from_url(url)

    def _determine_duration_by_url(self, url: str) -> Duration:
        return Duration.unknown()

    def emit_links(self, url) -> Dict[str, None]:
        # TODO Introduce new class that ties together the emitting logic: private post, private group post, public post, public group post
        LOG.info("Emitting links from provider '%s'", self)
        return self.fb_link_emitter.emit_links(url)

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

    LIKE_BUTTON_XPATH = '//span[text()="Like"]'
    SHARE_BUTTON_XPATH = '//span[text()="Share"]'
    COMMENT_BUTTON_XPATH = '//span[text()="Comment"]'

    def __init__(self, config, fb_link_parser):
        self.config = config
        self.fb_link_parser = fb_link_parser
        self.chrome_options = None
        self.driver = None
        self.logged_in = False
        self._init_logging()

    def load_links_from_private_content(self, url: str) -> List[str]:
        LOG.info("Loading private Facebook post content...")
        soup = self.load_url_as_soup(url)
        return self.fb_link_parser.find_links_in_soup(soup)

    def load_links_from_private_content_soup(self, soup: BeautifulSoup) -> List[str]:
        LOG.info("Loading private Facebook post content...")
        return self.fb_link_parser.find_links_in_soup(soup)

    def load_url_as_soup(self, url, timeout=25, poll_freq=2) -> BeautifulSoup:
        self._init_webdriver()
        if not self.logged_in:
            self._login()

        if self.driver.current_url != url:
            self._load_url(poll_freq, timeout, url)
        else:
            LOG.debug("Current URL matches desired URL '%s', not loading again", url)
        html = self.driver.page_source
        return HtmlParser.create_bs(html)

    def _load_url(self, poll_freq, timeout, url):
        self.driver.get(url)
        try:
            wait = WebDriverWait(self.driver, timeout=timeout, poll_frequency=poll_freq,
                                 ignored_exceptions=[NoSuchElementException, ElementNotVisibleException,
                                                     ElementNotSelectableException])
            success = wait.until(expected_conditions.all_of(
                expected_conditions.element_to_be_clickable((By.XPATH, self.COMMENT_BUTTON_XPATH))))
        except TimeoutException as e:
            raise e
        # TODO Add this to be more resilient for page load issues --> Should not have any of this "loading signs" in page!
        # <div class="..." style="animation-delay: 1000ms;"></div>

    def _login(self):
        self.driver.get(self.FACEBOOK_COM)
        loaded = self._wait_for_fb_page_load(timeout=20, throw_exception=False)
        if not loaded:
            self._do_initial_facebook_login()
        self.logged_in = True

    def _init_webdriver(self):
        if not self.chrome_options:
            self.chrome_options = Options()
            self.chrome_options.add_argument(self.CHROME_OPT_SELENIUM_PROFILE)
        if not self.driver:
            self.driver = webdriver.Chrome(chrome_options=self.chrome_options)

    def _wait_for_fb_page_load(self, timeout, throw_exception=False):
        try:
            wait = WebDriverWait(self.driver, timeout=timeout, poll_frequency=2,
                                 ignored_exceptions=[NoSuchElementException, ElementNotVisibleException,
                                                     ElementNotSelectableException])
            success = wait.until(expected_conditions.element_to_be_clickable((By.XPATH, self.FEELING_BUTTON_XPATH)))
            return success
        except TimeoutException as e:
            if throw_exception:
                raise e
        return None

    def _do_initial_facebook_login(self):
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

    def _init_logging(self):
        import logging
        from selenium.webdriver.remote.remote_connection import LOGGER
        LOGGER.setLevel(logging.INFO)


class FacebookLinkParser:
    def __init__(self, urls_to_match: List[str], fb_redirect_link_limit: int):
        self.urls_to_match = urls_to_match
        self.fb_redirect_link_limit = fb_redirect_link_limit

    @staticmethod
    def find_links_in_soup(soup: BeautifulSoup) -> List[str]:
        return HtmlParser.find_all_links(soup)

    def filter_links(self, links: List[str], remove_fbclid=True) -> Dict[str, None]:
        """

        Args:
            links:
            remove_fbclid:

        Returns:
            List of links, de-duplicated. The order is important as client classes could limit the number of links later.
        """
        # Use dict instead of set, as of Python 3.7, standard dict is preserving order: https://stackoverflow.com/a/53657523/1106893
        filtered_links = {}
        # TODO add FB redirect links to urls_to_match
        for link in links:
            for url_to_match in self.urls_to_match:
                if url_to_match in link:
                    if remove_fbclid:
                        mod_link = self.remove_fbclid(link)
                        filtered_links[mod_link] = None
                    else:
                        filtered_links[link] = None
                    break

        # TODO Migrate to: HtmlParser.filter_links_by_url_fragment
        fb_redirect_links = list(filter(lambda l: FACEBOOK_REDIRECT_LINK in l, filtered_links))
        if len(fb_redirect_links) > self.fb_redirect_link_limit:
            LOG.error("Found %d Facebook redirect links. Allowed limit is: %d", len(fb_redirect_links), self.fb_redirect_link_limit)
            return {}

        # TODO Facebook redirect links could resolve URLs like 'https://media0.giphy.com/media/J4yqIH28myeXRxTx56/giphy.gif?kid=be302117&ct=s&fbclid=IwAR3xJFupawFOaIpfxr_v9wnBT4DpQgWKhM28ZfYUz6Yv9Dc203_PfYFbS_E'
        #  Run FB redirect filtering first, then the urls_to_match filtering afterwards
        # Use dict instead of set, as of Python 3.7, standard dict is preserving order: https://stackoverflow.com/a/53657523/1106893
        final_links = {}
        for link in filtered_links:
            if FACEBOOK_REDIRECT_LINK in link:
                unescaped_link = self._get_final_link_from_fb_redirect_link(link, orig_url="unknown")
                if remove_fbclid:
                    unescaped_link = self.remove_fbclid(unescaped_link)
                    final_links[unescaped_link] = None
                else:
                    final_links[unescaped_link] = None
            else:
                final_links[link] = None
        return final_links

    @staticmethod
    def filter_facebook_redirect_links(links: Iterable[str]) -> Set[str]:
        return HtmlParser.filter_links_by_url_fragment(links, FACEBOOK_REDIRECT_LINK)

    @staticmethod
    def remove_fbclid(url: str) -> str:
        return HtmlParser.remove_query_param_from_url(url, "fbclid")

    def find_links_in_html_comments(self, url: str, soup:  BeautifulSoup) -> Dict[str, None]:
        # Find in comments
        # Data can be in:
        # <div class="hidden_elem">
        #   <code id="u_0_m_lP">
        #   <!-- <div class="_4-u2 mbm _4mrt _5v3q _7cqq _4-u8" id="u_0_b_Ga">
        #          <div class="_3ccb" data-ft="&#123;&quot;tn&quot;:&quot;-R&quot;&#125;" data-gt="&#123;&quot;type&quot;:&quot;click2canvas&quot;,&quot;fbsource&quot;:703,&quot;ref&quot;:&quot;nf_generic&quot;&#125;" id="u_0_d_Q9">
        #          <div>
        #          </div>
        #          <div class="_5pcr userContentWrapper"

        # Use dict instead of set, as of Python 3.7, standard dict is preserving order: https://stackoverflow.com/a/53657523/1106893
        found_links = {}
        comments = soup.find_all(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment_soup = HtmlParser.create_bs(comment)
            divs = comment_soup.find_all('div', attrs={'class': 'userContentWrapper'})
            for div in divs:
                # TODO Find all links by providers as well (not just FB redirect links)
                orig_links = FacebookLinkParser.find_links_in_div(div)
                fb_redirect_links = FacebookLinkParser.filter_facebook_redirect_links(orig_links)
                for redir_link in fb_redirect_links:
                    unescaped_link = self._get_final_link_from_fb_redirect_link(redir_link, url)
                    found_links[unescaped_link] = None
        LOG.debug("[orig: %s] Found links: %s", url, found_links)
        return found_links

    @staticmethod
    def find_links_in_div(div: Tag):
        return HtmlParser.find_links_in_div(div)

    def find_links_with_js_rendering(self, soup, url) -> Dict[str, None]:
        links: List[str] = FacebookLinkParser.find_links_in_soup(soup)
        filtered_links = self.filter_links(links)
        # filtered_links = FacebookLinkParser.filter_facebook_redirect_links(links)
        LOG.debug("[orig: %s] Found links on JS rendered page: %s", url, filtered_links)

        # Use dict instead of set, as of Python 3.7, standard dict is preserving order: https://stackoverflow.com/a/53657523/1106893
        final_links = {}
        for link in filtered_links:
            if link.startswith(FACEBOOK_REDIRECT_LINK):
                unescaped_link = self._get_final_link_from_fb_redirect_link(link, url)
                final_links[unescaped_link] = None
            else:
                final_links[link] = None
        return final_links

    @staticmethod
    def _get_final_link_from_fb_redirect_link(link, orig_url):
        """
        Example URL of Facebook redirect: https://l.facebook.com/l.php?u=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3DcI6tWuNlwZ4%26feature%3Dshare&h=AT2ELdFoLuLKA4TH-ft6vMySk5HQWZq6KNRPxHvdlBxOWqr4vYi-iujE5SaUn9oLwZLFYOvQsvcDo7JDUQ7yX2REXm7CIk3mJnPrXXWlMYxzh5uEVWeZwLFZlR0iZvTGIlnCiPseDFGbctntdYSg4456Prq-Oqc-ZT8aRR8QBNYC2A_DvNzzftV-al8RVSQSxI2N8Xw
        Will give something like:
        <script type="text/javascript" nonce="Fb99FNm1">
              document.location.replace("https:\\/\\/youtube.com\\/watch?v=cI6tWuNlwZ4&feature=share");
        </script>
        Args:
            link:
            orig_url:

        Returns:
        """
        new_link = HtmlParser.get_link_from_standard_redirect_page(orig_url, link)
        if not new_link:
            raise ValueError("Cannot find redirected link from source URL: {}".format(link))
        return new_link

    @staticmethod
    def find_private_fb_post_div(soup):
        return HtmlParser.find_divs_with_text(soup, "You must log in to continue.")

    @staticmethod
    def find_private_fb_group_div(soup):
        return HtmlParser.find_divs_with_text(soup, "Private group")

    @staticmethod
    def find_user_content_wrapper_divs(soup):
        return HtmlParser.find_divs_with_class(soup, 'userContentWrapper')

    @staticmethod
    def find_divs_with_empty_class(soup):
        return HtmlParser.find_divs_with_class(soup, None)
