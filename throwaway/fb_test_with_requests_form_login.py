import os.path
from datetime import datetime
from os.path import expanduser
import requests
from file_utils import FileUtils
import logging
from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)
BS4_HTML_PARSER = "html.parser"


def create_bs(html):
    return BeautifulSoup(html, features=BS4_HTML_PARSER)


# BASED ON THIS SO ANSWER https://stackoverflow.com/a/21930636/1106893
def test():
    """
    """

    fb_base_url = "https://www.facebook.com"
    resp = requests.get(fb_base_url)
    soup = create_bs(resp.text)
    # print(soup.prettify())
    form = soup.find("form")
    if not form:
        raise ValueError("could not find form!")


    form_data = {}
    action = form.attrs['action']
    fb_login_url = fb_base_url + action

    inputs = form.findAll("input")
    for input in inputs:
        name = input.attrs['name']
        if 'value' in input.attrs:
            form_data[name] = input.attrs['value']
    print(form_data)

    form_data['email'] = "<EMAIL GOES HERE>"
    orig_pwd = "<PASSWORD GOES HERE>"
    fb_special_hashed_pwd = "#PWD_BROWSER:5:1657028452:AZVQACzwE3+e1cFKsk4bm4G3afaMC+REZa6t9GLIm9u+/zg6rpe05h23DPIdFOWxEyFNsoLo4ajzvISGH6k6KUzKz4+ThuAxrnH/1X0xF2DnYIAPn3uG7int5NowzJz5tjSBBkwgwJfqL+nA4hhwX22D7Of94kAMcWdeGNlFz0lacw=="
    # form_data['pass'] = pwd
    time = int(datetime.now().timestamp())
    # form_data['encpass'] = f'#PWD_BROWSER:0:{time}:{orig_pwd}'
    form_data['encpass'] = f'#PWD_BROWSER:5:{time}:{fb_special_hashed_pwd}'

    headers1 = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',
        'referer': 'https://www.facebook.com/',
    }

    headers2 = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-language": "en-GB,en;q=0.9,en-US;q=0.8,hu;q=0.7,de;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "cache-control": "max-age=0",
        "origin": "https://www.facebook.com",
        "referer": "https://www.facebook.com",
        "upgrade-insecure-requests": "1",
        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="101", "Google Chrome";v="101"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
    }

    s = requests.Session()
    r = s.post(fb_login_url, data=form_data, headers=headers2)
    r.raise_for_status()
    file_path = os.path.join(expanduser("~"), "Downloads", "untitled.html")
    FileUtils.write_to_file(file_path, r.text)


if __name__ == '__main__':
    test()
