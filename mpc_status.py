import ast
import pathlib
import logging

import lxml
import lxml.html

from tornado import httpclient
from tornado import gen


import config


logger = logging.getLogger(__name__)


def parse_status(html_string):
    html_elem = lxml.html.fromstring(html_string)
    body = html_elem.body

    def _eval(text):
        try:
            return ast.literal_eval(text)
        except Exception:
            return text

    return {info_p.get('id'): _eval(info_p.text)
            for info_p in body.iterfind('p')}


def mpc_to_vlc(status):
    stats = dict.fromkeys(["inputbitrate", "sentbytes", "lostabuffers",
                           "averagedemuxbitrate", "readpackets",
                           "demuxreadpackets", "lostpictures",
                           "displayedpictures", "sentpackets",
                           "demuxreadbytes", "demuxbitrate", "playedabuffers",
                           "demuxdiscontinuity", "decodedaudio", "sendbitrate",
                           "readbytes", "averageinputbitrate",
                           "demuxcorrupted", "decodedvideo"],
                          0)
    if status['muted']:
        volume = 0
    else:
        volume = (status['volumelevel'] / 100) * 512

    duration = status['duration']
    if duration == 0:
        duration = 1

    # position is normalized
    position = (status['position'] / duration)
    vlc_time = status['position'] / 1000.0

    # mpc-hc duration in msec
    # vlc duration in seconds
    vlc_duration = int(duration / 1000.0)

    vlc_status = {
      "time": vlc_time,
      "volume": volume,
      "length": vlc_duration,
      "state": status['statestring'].lower(),

      "stats": stats,
      "fullscreen": False,
      "repeat": False,
      "subtitledelay": 0,
      "equalizer": [],

      "aspectratio": "default",
      "audiodelay": 0.0,
      "apiversion": 3,
      "currentplid": 4,
      "random": False,
      "audiofilters": {
        "filter_0": ""
      },
      "rate": status['playbackrate'],
      "videoeffects": {
        "hue": 0,
        "saturation": 1,
        "contrast": 1,
        "brightness": 1,
        "gamma": 1
      },
      "loop": False,
      "version": "2.2.1 Terry Pratchett (Weatherwax)",
      "position": position,
      "information": {
        "chapter": 0,
        "chapters": [0],
        "title": 0,
        "category": {
          "Stream 0": {
            "Frame_rate": "23.976216",
            "Decoded_format": "Planar 4: 2: 0 YVU",
            "Type": "Video",
            "Codec": "H264 - MPEG-4 AVC (part 10) (avc1)",
            "Display_resolution": "1920x1040",
            "Resolution": "1920x1040"
          },
          "Stream 1": {
            "Type": "Audio",
            "Channels": "3F2R/LFE",
            "AAC_extension": "SBR",
            "Sample_rate": "48000 Hz",
            "Codec": "MPEG AAC Audio (mp4a)"
          },
          # "meta": {
          #   "NUMBER_OF_FRAMES": "162607",
          #   "DURATION": "01: 55: 37.899000000",
          #   "filename": status['filepath'],
          #   "_STATISTICS_TAGS": ("BPS DURATION NUMBER_OF_FRAMES "
          #                        "NUMBER_OF_BYTES"),
          #   "NUMBER_OF_BYTES": "163113973",
          #   "_STATISTICS_WRITING_APP": ("mkvmerge v7.7.0 ('Six Voices')
          #                               "32bit"
          #                               "built on Feb 28 2015 23: 23: 00"),
          #   "BPS": "188084",
          #   "_STATISTICS_WRITING_DATE_UTC": "2015-09-13 03: 40: 53"
          # }
        },
        "titles": [0]
      },
    }

    vlc_playlist = {
      "ro": "rw",
      "type": "node",
      "name": "Undefined",
      "id": "1",
      "children": [{
          "ro": "ro",
          "type": "node",
          "name": "Playlist",
          "id": "2",
          "children": [{
              "ro": "rw",
              "type": "leaf",
              "name": status['file'],
              "id": "4",
              "duration": vlc_duration,
              "uri": pathlib.Path(status['filepath']).as_uri(),
              "current": "current"
            }]
        },
        {
          "ro": "ro",
          "type": "node",
          "name": "Media Library",
          "id": "3",
          "children": []
        }]
    }

    return vlc_status, vlc_playlist


def test():
    import pprint
    status = parse_status(open('status.html', 'rt').read())
    pprint.pprint(status)
    pprint.pprint(mpc_to_vlc(status))


class StatusPoller:
    def __init__(self, *, host=None, port=None, delay=0.1):
        super().__init__()
        StatusPoller.instance = self

        if host is None:
            host = config.host
        if port is None:
            port = config.mpc_port

        self.host = host
        self.port = port
        self.delay = delay
        self.status_url = ('http://{host}:{port}/variables.html'
                           ''.format(host=host, port=port))
        self.request = httpclient.HTTPRequest(self.status_url)
        logger.debug('Status request URL=%s', self.status_url)
        self.mpc_status = {}
        self.status = {}
        self.playlist = {}
        self.fullscreen = False

    @gen.coroutine
    def update_status(self):
        client = httpclient.AsyncHTTPClient()

        try:
            response = yield client.fetch(self.request)
            self._status_received(response.body)
        finally:
            client.close()

    def _status_received(self, status_html):
        mpc_status = parse_status(status_html)
        self.mpc_status = mpc_status
        self.status, self.playlist = mpc_to_vlc(mpc_status)
        self.status['fullscreen'] = self.fullscreen

    @gen.coroutine
    def run(self):
        logger.debug('Status poller started')
        while True:
            try:
                yield self.update_status()
            except Exception as ex:
                logger.warning('Update failed', exc_info=ex)
                yield gen.sleep(5 * self.delay)
            yield gen.sleep(self.delay)


if __name__ == '__main__':
    test()
