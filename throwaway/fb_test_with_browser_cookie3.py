import browser_cookie3
from requests import Response
from requests_html import HTMLSession
import logging

cookies = browser_cookie3.chrome(domain_name='.facebook.com')
LOG = logging.getLogger(__name__)


def test_with_cookies():
    """
    Unfortunately, this did not work for an unknown reason.
    All I got is a page that required login, even if the cookie header was correct.
    Returns:

    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-language": "en-GB,en;q=0.9,en-US;q=0.8,hu;q=0.7,de;q=0.6",
        "cache-control": "max-age=0",
        # "DNT":"1",
        # "Connection":"close",
        "upgrade-insecure-requests": "1",
        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="101", "Google Chrome";v="101"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
    }
    page = 'https://www.facebook.com/story.php?story_fbid=10159065418434624&id=758754623'
    # response = requests.get(page, verify=False, headers=headers, cookies=cookies, timeout=3)
    # print(response)

    fb_cookies = cookies._cookies[".facebook.com"]["/"]
    d = {k: v.value for k, v in fb_cookies.items()}
    LOG.info("FB cookies: " + str(d))

    session = HTMLSession()
    r: Response = session.get(page, verify=False, headers=headers, cookies=cookies, timeout=3)
    r.html.render()
    r.html.links


if __name__ == '__main__':
    test()