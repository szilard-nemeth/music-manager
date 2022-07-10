import logging
from datetime import timedelta
from typing import Iterable

import youtube_dl
from string_utils import auto_str

from musicmanager.commands.addnewentitiestosheet.music_entity_creator import IntermediateMusicEntity
from musicmanager.common import Duration
from musicmanager.contentprovider.common import ContentProviderAbs

YOUTUBE_URL_1 = "youtube.com"
YOUTUBE_URL_2 = "youtu.be"
YOUTUBE_CHANNEL_URL_FRAGMENT = "channel/"
YOUTUBE_DL = youtube_dl.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'})
LOG = logging.getLogger(__name__)


@auto_str
class Youtube(ContentProviderAbs):
    @classmethod
    def url_matchers(cls) -> Iterable[str]:
        return [YOUTUBE_URL_1, YOUTUBE_URL_2]

    def is_media_provider(self):
        return True

    def can_handle_url(self, url):
        if YOUTUBE_URL_1 in url or YOUTUBE_URL_2 in url:
            return True
        return False

    def emit_links(self, url):
        return []

    def create_intermediate_entity(self, url: str) -> IntermediateMusicEntity:
        # TODO
        duration = self._determine_duration_by_url(url)
        return IntermediateMusicEntity(duration, url)

    def _determine_title_by_url(self, url: str) -> Duration:
        # TODO implement
        pass

    def _determine_duration_by_url(self, url: str) -> Duration:
        # TODO Move this check elsewhere
        if url is None:
            url = ""
        duration: Duration = self._determine_duration(url)
        return duration

    @staticmethod
    def _determine_duration(url):
        if YOUTUBE_CHANNEL_URL_FRAGMENT in url:
            return Duration.unknown()
        video_info = Youtube._get_youtube_video_info(url)
        duration_seconds = video_info['duration']
        td = timedelta(seconds=duration_seconds)
        LOG.info("Determined duration of video '%s': %s", url, td)
        return Duration(duration_seconds)

    @staticmethod
    def _get_youtube_video_info(video_link):
        with YOUTUBE_DL:
            result = YOUTUBE_DL.extract_info(video_link, download=False)
        if 'entries' in result:
            # Can be a playlist or a list of videos
            video_info = result['entries'][0]
        else:
            # Just a video
            video_info = result
        return video_info
