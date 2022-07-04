from datetime import timedelta
from typing import List, Tuple
import logging
import youtube_dl
from musicmanager.common import Duration

YOUTUBE_URL2 = "youtu.be"
YOUTUBE_URL_1 = "www.youtube.com"
YOUTUBE_CHANNEL_URL_FRAGMENT = "channel/"
YOUTUBE_DL = youtube_dl.YoutubeDL({'outtmpl': '%(id)s.%(ext)s'})
LOG = logging.getLogger(__name__)


class Youtube:
    @staticmethod
    def determine_duration_by_urls(urls: List[str]) -> Tuple[Duration, str]:
        for url in urls:
            if url is None:
                url = ""
            duration: Duration = Youtube.determine_duration(url)
            if not duration.is_unknown():
                return duration, url
        return Duration.unknown(), None

    @staticmethod
    def determine_duration(url):
        if YOUTUBE_URL_1 in url or YOUTUBE_URL2 in url:
            if YOUTUBE_CHANNEL_URL_FRAGMENT in url:
                return Duration.unknown()
            video_info = Youtube._get_youtube_video_info(url)
            duration_seconds = video_info['duration']
            td = timedelta(seconds=duration_seconds)
            LOG.info("Duration of video '%s': %s", url, td)
            return Duration(duration_seconds)
        return Duration.unknown()

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
