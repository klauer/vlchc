# https://gist.github.com/kelleyk/1073682
import base64
import logging


logger = logging.getLogger(__name__)


def after_login(*args, **kwargs):
    pass


def create_auth_header(handler, realm):
    handler.set_status(401)
    handler.set_header('WWW-Authenticate',
                       'Basic realm=%s' % realm)
    handler._transforms = []
    handler.finish()


def basic_auth(auth_func=lambda *args, **kwargs: True,
               after_login_func=after_login, realm='Restricted'):
    def basic_auth_decorator(handler_class):
        def wrap_execute(handler_execute):
            def require_basic_auth(handler, kwargs):
                auth_header = handler.request.headers.get('Authorization')

                if auth_header is None or not auth_header.startswith('Basic '):
                    create_auth_header(handler, realm)
                else:
                    auth_bytes = auth_header[6:].encode('ascii')
                    auth_decoded_bytes = base64.decodebytes(auth_bytes)
                    auth_decoded = auth_decoded_bytes.decode('ascii')
                    user, pwd = auth_decoded.split(':', 2)

                    if auth_func(user, pwd):
                        after_login_func(handler, kwargs, user, pwd)
                    else:
                        create_auth_header(handler, realm)

            def _execute(self, transforms, *args, **kwargs):
                require_basic_auth(self, kwargs)
                return handler_execute(self, transforms, *args, **kwargs)

            return _execute

        handler_class._execute = wrap_execute(handler_class._execute)
        return handler_class
    return basic_auth_decorator
