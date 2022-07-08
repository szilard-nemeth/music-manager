from abc import ABC, abstractmethod
from typing import Iterable

import requests


class URLResolutionServiceAbs(ABC):
    @abstractmethod
    def can_handle_url(self, url):
        pass

    @abstractmethod
    def resolve(self, url):
        pass

    @classmethod
    @abstractmethod
    def get_known_urls(cls) -> Iterable[str]:
        pass


class BitLyURLResolutionService(URLResolutionServiceAbs):
    BIT_LY_URL_FRAGMENT = "bit.ly"
    known_urls = [BIT_LY_URL_FRAGMENT]

    @classmethod
    def get_known_urls(cls) -> Iterable[str]:
        return cls.known_urls

    def __init__(self):
        pass

    def can_handle_url(self, url):
        for url_fragment in self.known_urls:
            if url_fragment in url:
                return True
        return False

    def resolve(self, url):
        session = requests.Session()  # so connections are recycled
        resp = session.head(url, allow_redirects=True)
        return resp.url


class URLResolutionServices:
    SERVICES = [BitLyURLResolutionService()]

    @classmethod
    def resolve_url_with_services(cls, url):
        for service in URLResolutionServices.SERVICES:
            if service.can_handle_url(url):
                return service.resolve(url)
        return None
