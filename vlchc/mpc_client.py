import logging
import functools
import urllib.parse

from tornado import httpclient
from tornado import gen

from . import config
from .mpc_reqs import MpcCommandEnum
from .mpc_status import StatusPoller


logger = logging.getLogger(__name__)


def get_mpc_host_port(host=None, port=None):
    if host is None:
        host = config.host
    if port is None:
        port = config.mpc_port

    return host, port


def mpc_command(data, *, host=None, port=None):
    host, port = get_mpc_host_port(host, port)

    command_url = ('http://{host}:{port}/command.html'
                   ''.format(host=host, port=port))
    logger.debug('Generating command request URL=%s', command_url)
    if 'wm_command' in data:
        data = dict(data)
        data['wm_command'] = int(data['wm_command'])

    return httpclient.HTTPRequest(command_url,
                                  method='POST',
                                  body=urllib.parse.urlencode(data),
                                  )
    # auth_username='',
    # auth_password=config.vlc_password,
    # auth_mode='basic'


@gen.coroutine
def send_command_request(cmd):
    client = httpclient.AsyncHTTPClient()
    req = mpc_command(cmd)
    logger.debug('req %s (data=%s)', req.url, cmd)

    try:
        response = yield client.fetch(req)
    finally:
        client.close()
    return response


@gen.coroutine
def send_get_request(url, *, host=None, port=None, **data):
    host, port = get_mpc_host_port(host, port)
    client = httpclient.AsyncHTTPClient()
    args = '&'.join('{}={}'.format(k, v) for k, v in data.items())
    command_url = ('http://{host}:{port}/{url}?{args}'
                   ''.format(host=host, port=port, url=url,
                             args=args))
    logger.debug('Generating command request URL=%s', command_url)
    req = httpclient.HTTPRequest(command_url,
                                 method='GET',
                                 # body=urllib.parse.urlencode(data),
                                 )
    try:
        response = yield client.fetch(req)
    finally:
        client.close()
    return response


def basic_command(wm_command):
    def wrapped(**kwargs):
        return dict(wm_command=wm_command)

    return wrapped


# in_enqueue=MpcCommandEnum.
vlc_to_mpc = dict(
    pl_play=basic_command(MpcCommandEnum.PLAY),
    pl_pause=basic_command(MpcCommandEnum.PAUSE),
    pl_forcepause=basic_command(MpcCommandEnum.PAUSE),
    pl_forceresume=basic_command(MpcCommandEnum.PLAY),
    pl_stop=basic_command(MpcCommandEnum.STOP),
    pl_next=basic_command(MpcCommandEnum.NEXT_FILE),
    pl_previous=basic_command(MpcCommandEnum.PREVIOUS_FILE),
    title=basic_command(MpcCommandEnum.DVD_TITLE_MENU),
    chapter=basic_command(MpcCommandEnum.DVD_CHAPTER_MENU),
    audio_track=basic_command(MpcCommandEnum.NEXT_AUDIO_TRACK),
    video_track=basic_command(MpcCommandEnum.DVD_NEXT_ANGLE),
    subtitle_track=basic_command(MpcCommandEnum.NEXT_SUBTITLE_TRACK),
    )


def handles(vlc_command):
    '''maps vlc_command to put args for mpc-hc request'''
    def wrapper(command_fcn):
        @functools.wraps(command_fcn)
        def wrapped(**kwargs):
            return command_fcn(**kwargs)

        global vlc_to_mpc
        vlc_to_mpc[vlc_command] = command_fcn
        return wrapped

    return wrapper


@handles('volume')
def mpc_volume(value=0, **kwargs):
    value = int(value)
    return dict(wm_command=MpcCommandEnum.CMD_SET_VOLUME,
                volume=int(100.0 * (value / 512)),
                )


@handles('key')
def mpc_key(value=0, **kwargs):
    keys = {'subdelay-down': MpcCommandEnum.SUBTITLE_DELAY_MINUS,
            'subdelay-up': MpcCommandEnum.SUBTITLE_DELAY_PLUS,
            'audiodelay-down': MpcCommandEnum.AUDIO_DELAY_MINUS10_MS,
            'audiodelay-up': MpcCommandEnum.AUDIO_DELAY_PLUS10_MS,
            'audio-track': MpcCommandEnum.NEXT_AUDIO_TRACK,
            'nav-left': MpcCommandEnum.DVD_MENU_LEFT,
            'nav-right': MpcCommandEnum.DVD_MENU_RIGHT,
            'nav-up': MpcCommandEnum.DVD_MENU_UP,
            'nav-down': MpcCommandEnum.DVD_MENU_DOWN,
            'nav-activate': MpcCommandEnum.DVD_MENU_ACTIVATE,
            # 'chapter-prev': ,
            # 'chapter-next': ,
            # 'title-prev': ,
            # 'title-next': ,
            }

    return dict(wm_command=keys[value])


@handles('fullscreen')
def fullscreen(**kwargs):
    poller = StatusPoller.instance
    poller.fullscreen = not poller.fullscreen
    return dict(wm_command=MpcCommandEnum.FULLSCREEN_NO_RES_CHANGE)


@handles('seek')
def seek(value=0, **kwargs):
    poller = StatusPoller.instance
    vlc_position = float(value)
    vlc_length = poller.status['length']
    percent = (vlc_position / vlc_length) * 100.0
    return dict(wm_command=MpcCommandEnum.CMD_SET_POSITION,
                percent=percent)


@handles('in_play')
def play_file(input_=0, **kwargs):
    return {'url': 'browser.html',
            'path': input_
            }


# @handles('pl_delete')
# @handles('pl_empty')
# @handles('pl_sort')
# @handles('pl_random')
# @handles('pl_loop')
# @handles('pl_repeat')
# @handles('pl_sd')
# @handles('snapshot')
# @handles('key')
# @handles('audiodelay') = mpc_audiodelay  #
# @handles('rate')
# @handles('aspectratio')
# @handles('preamp')
# @handles('equalizer')
# @handles('enableeq')
# @handles('setpreset')
