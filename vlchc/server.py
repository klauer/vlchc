# *!* coding: utf-8 *!*
import os
import sys
import logging
import urllib.parse
import pathlib

import tornado.ioloop
import tornado.options
import tornado.web
import tornado.autoreload
from tornado import gen

import json

from .mpc_client import (mpc_command, vlc_to_mpc, send_command_request,
                         send_get_request)
from .mpc_status import StatusPoller

from .auth import basic_auth
from . import config
# from debug import PassThroughHandler


logger = logging.getLogger(__name__)
server_root = os.path.abspath(os.path.dirname(__file__))
vlc_static_root = os.path.join(server_root, 'vlc_static')


def json_response(handler, res):
    handler.clear()
    handler.set_status(200)
    handler.set_header("Content-Type", "text/json;charset=UTF-8")
    handler.write(json.dumps(res, ensure_ascii=False).encode('utf-8'))


class VlcStatusHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        logger.debug('------ FULL URI %s', self.request.uri)
        vlc_command = self.get_argument('command', '')

        try:
            cmd_func = vlc_to_mpc[vlc_command]
        except KeyError:
            pass
        else:
            logger.debug('     - vlc %s -> mpc %s', vlc_command, mpc_command)
            kw = dict(value=self.get_argument('val', default=0),
                      input_=self.get_argument('input', default=''),
                      )

            if kw['input_']:
                kw['input_'] = uri_to_filename(kw['input_'])

            try:
                command_dict = cmd_func(**kw)
            except Exception as ex:
                logger.error('Command failed (%s)', cmd_func, exc_info=ex)
            else:
                if 'url' in command_dict:
                    yield send_get_request(**command_dict)
                else:
                    yield send_command_request(command_dict)

        global status_poller
        json_response(self, status_poller.status)


class VlcPlaylistHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        global status_poller
        json_response(self, status_poller.playlist)


def get_file_info(fn):
    try:
        stat = os.stat(fn)
    except Exception:
        return None

    name = os.path.split(fn)[1]
    if not name:
        name = fn

    return {'type': 'dir' if os.path.isdir(fn) else 'file',
            'path': os.path.abspath(fn),
            'name': name,
            'access_time': stat.st_atime,
            'creation_time': stat.st_ctime,
            'modification_time': stat.st_mtime,
            'uid': stat.st_uid,
            'gid': stat.st_gid,
            'mode': stat.st_mode,
            'size': stat.st_size,
            'uri': pathlib.Path(fn).as_uri(),
            }


def auth_func(user, password):
    authenticated = (password == config.vlc_password)
    logger.debug('Auth attempt %r %r (authenticated=%s)',
                 user, password, authenticated)
    return authenticated


@basic_auth(auth_func=auth_func)
class AuthStaticHandler(tornado.web.StaticFileHandler):
    pass


@basic_auth(auth_func=auth_func)
class RootHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        logger.debug('root handler request %s', self.request)
        with open(os.path.join(vlc_static_root, "index.html"), 'rt') as f:
            self.write(f.read())


def uri_to_filename(uri):
    # TODO pathlib?

    # obviously i don't know what i'm doing
    # uri = self.decode_argument(self.get_argument('uri'))
    # local_path_bytes = urllib.parse.unquote_to_bytes(uri)
    # local_path = local_path_bytes.decode('utf-8', errors='ignore')

    res = urllib.parse.urlparse(uri)

    local_path = res.path[1:]
    local_path_bytes = urllib.parse.unquote_to_bytes(local_path)
    return local_path_bytes.decode('utf-8', errors='ignore')


class VlcBrowseHandler(tornado.web.RequestHandler):
    def path_list(self, local_path):
        if local_path.endswith('~') or not local_path:
            global status_poller
            try:
                status_poller.mpc_status['filedir']
            except KeyError:
                local_path = os.path.expanduser('~')

        if local_path in ('c:/..', 'Volumes', 'media'):
            if sys.platform in ('win32', ):
                drives = ['{}:/'.format(letter) for letter in
                          'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
                return [get_file_info(drive) for drive in drives]

            local_path = '/'

        logger.debug('local path is %r', local_path)

        if not os.path.exists(local_path):
            print("Path doesn't exist, using default")
            local_path = config.default_path

        return [get_file_info(os.path.join(local_path, fn))
                for fn in sorted(os.listdir(local_path))]

    @gen.coroutine
    def get(self):
        uri = self.get_argument('uri')
        local_path = uri_to_filename(uri)
        logger.debug('local path %s', local_path)

        file_info = self.path_list(local_path)
        # TODO something less lazy
        file_info = [info for info in file_info
                     if info is not None]

        res = {'element': file_info}
        json_response(self, res)


def make_app():
    return tornado.web.Application([
        # (r"(?P<url>.*)", PassThroughHandler),
        (r"/requests/status.json", VlcStatusHandler),
        (r"/requests/playlist.json", VlcPlaylistHandler),
        (r"/requests/browse.json", VlcBrowseHandler),
        (r"/.*", RootHandler),

        # vlc version unrecognized with this: :(
        # (r"/()", AuthStaticHandler,
        #  {"path": vlc_static_root, "default_filename": "index.html"})

        # pass-through for debugging
        # (r"/.*", PassThroughHandler),
    ]
    )


if __name__ == "__main__":
    app = make_app()
    app.listen(config.vlc_port)

    status_poller = StatusPoller()

    tornado.options.parse_command_line()
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.spawn_callback(status_poller.run)
    try:
        ioloop.start()
    except KeyboardInterrupt:
        ioloop.stop()
