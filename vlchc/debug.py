# *!* coding: utf-8 *!*
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.autoreload
from tornado import gen
from tornado import httpclient

from .config import (vlc_password, vlc_passthru_port)


class PassThroughHandler(tornado.web.RequestHandler):
    @property
    def new_url(self):
        return ('http://127.0.0.1:{}{}'
                ''.format(vlc_passthru_port, self.request.uri))

    @gen.coroutine
    def get(self):
        client = httpclient.AsyncHTTPClient()

        req = httpclient.HTTPRequest(self.new_url,
                                     method=self.request.method,
                                     auth_username='',
                                     auth_password=vlc_password,
                                     auth_mode='basic')

        if self.request.method != 'GET':
            req.body = self.request.body

        try:
            response = yield client.fetch(req)
        except httpclient.HTTPError as ex:
            self.write('failed {}'.format(ex))
        except Exception as ex:
            self.write('failed {}'.format(ex))
        else:
            print('received', response)
            for key in ("Content-Type", "Content-Disposition"):
                if key in response.headers:
                    print('setting', key, response.headers[key])
                    self.set_header(key, response.headers[key])

            buf = response.buffer.read()
            self.write(buf)

            with open('passthrough_log.txt', 'at') as f:
                print('', file=f)
                print('-------------------------', file=f)
                print('request: ', str(req.url), file=f)
                f.write(bytes(buf).decode('ascii', errors='ignore'))
        finally:
            client.close()


