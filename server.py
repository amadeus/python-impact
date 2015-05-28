#!/usr/bin/env python

import BaseHTTPServer
import cgi
import glob
import json
import mimetypes
import os
import os.path
import urlparse

# Various config settings for the python server
SETTINGS = {
    'port':        8080,
    'logging':     False,

    'api-save':    '/lib/weltmeister/api/save.php',
    'api-browse':  '/lib/weltmeister/api/browse.php',
    'api-glob':    '/lib/weltmeister/api/glob.php',

    'image-types': ['.png', '.jpg', '.gif', '.jpeg'],

    'mimetypes': {
        'ogg': 'audio/ogg'
    }
}

# Override port if we are on a Heroku server
if os.environ.get('PORT'):
    SETTINGS['port'] = int(os.environ.get('PORT'))

# Get the current directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR[-1] != '/':
    BASE_DIR += '/'

# Blank favicon - prevents silly 404s from occuring if no favicon is supplied
FAVICON_GIF = 'GIF89a\x01\x00\x01\x00\xf0\x00\x00\xff\xff\xff\x00\x00\x00!\xff\x0bXMP DataXMP\x02?x\x00!\xf9\x04\x05\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00@\x02\x02D\x01\x00;'

class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def send_json(self, obj, code=200, headers=None):
        'Send response as JSON'
        if not headers:
            headers = {}
        headers['Content-Type'] = 'application/json'
        self.send_response(json.dumps(obj), code, headers)

    def send_response(self, mesg, code=200, headers=None):
        'Wraps sending a response down'
        if not headers:
            headers = {}
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'text/html'
        BaseHTTPServer.BaseHTTPRequestHandler.send_response(self, code)
        self.send_header('Content-Length', len(mesg))
        if headers:
            for k, v in headers.iteritems():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(mesg)

    def log_request(self, *args, **kwargs):
        'If logging is disabled '
        if SETTINGS['logging']:
            BaseHTTPServer.BaseHTTPRequestHandler.log_request(self, *args, **kwargs)

    def init_request(self):
        parts = self.path.split('?', 1)
        self.post_params = {}
        if len(parts) == 1:
            self.file_path = parts[0]
            self.query_params = {}
        else:
            self.file_path = parts[0]
            self.query_params = urlparse.parse_qs(parts[1])

    def do_GET(self):
        self.init_request()
        self.route_request('GET')

    def do_HEAD(self):
        self.init_request()
        self.send_response('')

    def do_POST(self):
        self.init_request()

        # From http://stackoverflow.com/questions/4233218/python-basehttprequesthandler-post-variables
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        if ctype == 'multipart/form-data':
            self.post_params = cgi.parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers.getheader('content-length'))
            self.post_params = cgi.parse_qs(self.rfile.read(length), keep_blank_values=1)

        self.route_request('POST')

    def route_request(self, method='GET'):
        if self.file_path == SETTINGS['api-save']:
            self.save()
        elif self.file_path == SETTINGS['api-browse']:
            self.browse()
        elif self.file_path == SETTINGS['api-glob']:
            self.glob()
        elif method == 'GET':
            self.serve_file()
        else:
            self.barf()

    def save(self):
        resp = {'error': 0}
        if 'path' in self.post_params and 'data' in self.post_params:
            path = self.post_params['path'][0]
            path = os.path.join(BASE_DIR, path.replace('..', ''))
            data = self.post_params['data'][0]

            if path.endswith('.js'):
                try:
                    open(path, 'w').write(data)
                except:
                    resp['error'] = 2
                    resp['msg'] = 'Couldn\'t write to file %d' % path

            else:
                resp['error'] = 3
                resp['msg'] = 'File must have a .js suffix'

        else:
            resp['error'] = 1
            resp['msg'] = 'No Data or Path specified'

        return self.send_json(resp)

    def browse(self):
        # Get the directory to scan
        dir = ''
        if 'dir' in self.query_params:
            dir = self.query_params['dir'][0].replace('..', '')
            if dir[-1] != '/':
                dir += '/'

        # Get the dir and files
        dirs = [os.path.join(dir, d) for d in os.listdir(os.path.join(BASE_DIR, dir))
                if os.path.isdir(os.path.join(dir, d))]

        files = glob.glob(dir + '*.*')

        # Filter on file types
        if 'type' in self.query_params:
            types = self.query_params['type']
            if 'images' in types:
                files = [f for f in files if os.path.splitext(f)[1] in SETTINGS['image-types']]
            elif 'scripts' in types:
                files = [f for f in files if os.path.splitext(f)[1] == '.js']

        if os.name == 'nt':
            files = [f.replace('\\', '/') for f in files]
            dirs = [d.replace('\\', '/') for d in dirs]

        response = {
            'files': files,
            'dirs': dirs,
            'parent': False if dir == './' else os.path.dirname(os.path.dirname(dir))
        }
        return self.send_json(response)

    def glob(self):
        globs = self.query_params['glob[]']
        files = []

        for g in globs:
            g = g.replace('..', '')
            more = glob.glob(g)
            files.extend(more)

        if os.name == 'nt':
            files = [f.replace('\\', '/') for f in files]

        return self.send_json(files)

    def guess_type(self, path):
        type, _ = mimetypes.guess_type(path)

        if not type:
            ext = path.split('.')[-1]
            if ext in SETTINGS['mimetypes'].keys():
                type = SETTINGS['mimetypes'][ext]

        # Winblows hack
        if os.name == "nt" and type.startswith("image"):
            type = type.replace("x-", "")

        return type

    def serve_file(self):
        path = self.file_path
        if path == '/':
            path = 'index.html'
        elif path == '/editor':
            path = 'weltmeister.html'

        # Remove the leading forward slash
        if path[0] == '/':
            path = path[1:]

        # Security, remove the ..
        path = path.replace('..', '')

        # Determine the fullpath
        path = os.path.join(BASE_DIR, path)

        try:
            data = open(path, 'rb').read()
            type = self.guess_type(path)
            self.send_response(data, 200, headers={'Content-Type': type})
        except:
            if '/favicon.ico' in path:
                self.send_response(FAVICON_GIF, 200, headers={'Content-Type': 'image/gif'})
            else:
                self.send_response('', 404)

    def barf(self):
        self.send_response('barf', 405)


def main():
    addr = ('', SETTINGS['port'])
    server = BaseHTTPServer.HTTPServer(addr, HTTPHandler)
    print 'Running ImpactJS Server\nGame:   http://localhost:%d\nEditor: http://localhost:%d/editor' % (addr[1], addr[1])
    server.serve_forever()

if __name__ == '__main__':
    main()

