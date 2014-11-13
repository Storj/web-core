#!/usr/bin/env python

from __future__ import print_function

import file_encryptor
import webcore
from webcore import (index, settings)

WebCore  = webcore.webcore_.WebCore

import codecs
from io import BytesIO
import os
import time
import errno
import pprint

import unittest
import tempfile
import hashlib
import stat
import multiprocessing

import sqlite3
import flask
try:
    import flask.ext.api
    status = flask.ext.api.status
except ImportError as e:
    print('webcore tests require "Flask-API"')
import json
import os

import psycopg2
from psycopg2.extensions import STATUS_READY
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2 import ProgrammingError

import shutil

from six.moves import (SimpleHTTPServer, BaseHTTPServer)
from threading import Thread
from six.moves import socketserver
import socket
class MockAccountsServer(object):
    PORT = 32924 # TODO: can we be bound to an ephemeral port instead?
    Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    class Handler(SimpleHTTPServer.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(s):
            success = 'realtoken' in s.path
            s.send_response(200 if success else 404)
            s.end_headers()
        def do_GET(s):
            success = 'realtoken' in s.path
            s.send_response(200 if success else 404)
            s.end_headers()

    
    class ReuseTCPServer(socketserver.TCPServer):
        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(self.server_address)

    def __init__(self):
        self.httpd = MockAccountsServer.ReuseTCPServer(("", MockAccountsServer.PORT), MockAccountsServer.Handler)
        self.httpd_thread = Thread(target=self.httpd.serve_forever, group=None)
        self.httpd_thread.start()

    @property
    def url(self):
        return u'http://localhost:{}'.format(MockAccountsServer.PORT)

    def __del__(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd_thread.join()
        del self.httpd
        del self.httpd_thread


class MetaDiskWebCoreTestCase(unittest.TestCase):
    '''Tests the web API for the web-core package
    '''
    class FailedResponseException(Exception):
        def __init__(self, text = '', response = None):
            super(MetaDiskWebCoreTestCase.FailedResponseException, self).__init__(text)
            self.response = response

        def __str__(self):
            return super(MetaDiskWebCoreTestCase.FailedResponseException, self).__str__() + '-' + str(self.response)

    def setUp(self):
        self.SAMPLE_UPLOAD_SIZE_BYTES = 256
        self.storage_path = tempfile.mkdtemp()
        settings.CLOUDSYNC_WAIT = 1.
        settings.DATABASE_PATH = os.environ.get('DB_URL', 'postgres://postgres:postgres@localhost/')
        settings.STORAGE_PATH  = self.storage_path
        try:
            os.makedirs('./tmp/') # TODO override app.config['TEMP_STORAGE'] with self.storage_path?
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        settings.ACCOUNTS_API_ENABLED = False
        os.chmod(settings.STORAGE_PATH, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        def mockdc():
            class MockDc(object):
                def address(self, ident):
                    return '0'

                def balance(self):
                    return 0.

            return MockDc()
        settings.METACHAINS_OVERRIDE = mockdc

#       db_name = self.__class__.__name__ + str(int(time.time()))
        db_name = self.__class__.__name__
        self.db = self._init_db(settings.DATABASE_PATH, db_name)

        self.app = index.app.test_client()

#       self.accts_server = MockAccountsServer()

    def _init_db(self, database_path, db_name):
        '''Initialize the database to a known state.
        '''
        conn = psycopg2.connect(database_path)
        conn.autocommit = True
        with conn.cursor() as cursor:
            try:
                cursor.execute('DROP DATABASE {}'.format(db_name))
            except ProgrammingError as e:
                pass

            cursor.execute('CREATE DATABASE {}'.format(db_name))
            with open('tests/test_db_teardown.sql') as f:
                cursor.execute(f.read())

            with open('tests/test_db.sql') as f:
                cursor.execute(f.read())

        return conn

    def _find(self, filehash):
        response = self.app.get('/api/find/{}'.format(filehash))

        return response

    def _download(self, filehash, key, token = None):
        params = {'token': token, } if token else {}
        response = self.app.get('/api/download/{}'.format(filehash), query_string = params)

        if response.status_code != 200:
            raise self.FailedResponseException('Failed download', response)

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(response.data)
            f.close()

            key_ = codecs.decode(key, 'hex_codec')
            file_encryptor.convergence.decrypt_file_inline(f.name, key_)

        with open(f.name, 'rb') as f_:
            contents = f_.read()

        os.unlink(f.name)

        return contents


    def _upload(self, contents, **kwargs):
        upload_data = {
            'file': (BytesIO(contents), self.__class__.__name__),
        }
        upload_data.update(kwargs)

        response = self.app.post('/api/upload', data=upload_data,
            follow_redirects=True)

        if  response.status_code != status.HTTP_201_CREATED:
            raise self.FailedResponseException('Failed upload', response)
        fields = flask.json.loads(response.data)

        return fields['filehash'], fields['key']

    def test_find(self):
        '''Test GET /api/find/[hash]
        '''
        contents = os.urandom(self.SAMPLE_UPLOAD_SIZE_BYTES)
        filehash, key = self._upload(contents)

        failed_response = self._find(filehash)
        assert not status.is_success(failed_response.status_code)

        WebCore().cloud.cloud_sync()

        response = self._find(filehash)
        assert status.is_success(response.status_code)

        lookup = flask.json.loads(response.data)

        assert 'error' not in lookup
        assert lookup['filesize'] == self.SAMPLE_UPLOAD_SIZE_BYTES
        assert lookup['filehash'] == filehash


        # Hash not found case:
        response = self._find('bogushash')
        assert status.is_client_error(response.status_code)
        lookup = flask.json.loads(response.data)

        assert 'error' in lookup
        assert 'filesize' not in lookup

    def _get_filename(self, filehash):
        filename = '{}_{}'.format(filehash[:7], self.__class__.__name__)
        return os.path.join(self.storage_path, filename)

    def test_upload(self):
        '''Test POST /api/upload
        '''
        contents = b'i' * self.SAMPLE_UPLOAD_SIZE_BYTES
        filehash, key = self._upload(contents)
        filename = self._get_filename(filehash)

        file_stat = os.stat(filename)

        assert len(contents) == file_stat.st_size
        # file must not be executable
        assert (stat.S_IXUSR & file_stat.st_mode) == 0
        assert (stat.S_IXGRP & file_stat.st_mode) == 0
        assert (stat.S_IXOTH & file_stat.st_mode) == 0

        WebCore().cloud.cloud_sync()

        new_contents = self._download(filehash, key)

        assert contents == new_contents

    def test_not_in_cache(self):
        '''Cover the cache miss path
        '''
        contents = b'i' * self.SAMPLE_UPLOAD_SIZE_BYTES
        filehash, key = self._upload(contents)
        filename = self._get_filename(filehash)

        # If the file is missing, it's considered a cache miss.
        #   -- It appears more severe than just a cache miss, though.
        os.unlink(filename)

        WebCore().cloud.cloud_sync()

        with self.assertRaises(self.FailedResponseException) as download_exc:
            self._download(filehash, key)

    def test_upload_failures(self):
        '''Test file upload when the backend storage is unavailable and insufficient space.
        '''
        os.chmod(settings.STORAGE_PATH, ~stat.S_IRWXU)
        try:
            contents = os.urandom(self.SAMPLE_UPLOAD_SIZE_BYTES)

            with self.assertRaises(self.FailedResponseException) as upl_exc:
                filehash = self._upload(contents)

            assert status.is_server_error(upl_exc.exception.response.status_code)
        finally:
            os.chmod(settings.STORAGE_PATH, stat.S_IRWXU)


        orig_storage_size = settings.STORAGE_SIZE
        settings.STORAGE_SIZE     = 1
        try:
            contents = b'w' * self.SAMPLE_UPLOAD_SIZE_BYTES
            with self.assertRaises(self.FailedResponseException) as upl_exc:
                filehash = self._upload(contents)

            assert status.is_server_error(upl_exc.exception.response.status_code)
        finally:
            settings.STORAGE_SIZE = orig_storage_size

    def test_download_w_key(self):
        contents = os.urandom(self.SAMPLE_UPLOAD_SIZE_BYTES)
        filehash, key = self._upload(contents)
        response = self.app.get('/api/download/{}?key={}'.format(filehash, key))

        assert status.is_success(response.status_code)
        assert response.data == contents

    def test_download_invalid_hash(self):
        '''Test GET /api/download with an invalid hash
        '''
        with self.assertRaises(self.FailedResponseException) as down_exc:
            self._download('bogushash', 'boguskey')

        assert status.is_client_error(down_exc.exception.response.status_code)

    def test_status(self):
        '''Test GET /api/status
        '''
        response = self.app.get('/api/status')

        assert status.is_success(response.status_code)

        status_ = flask.json.loads(response.data)
        assert 'bandwidth' in status_
        assert 'storage' in status_ 
        assert 'sync' in status_ 

    @unittest.skip('this causes flask/werkzeug to fill memory, is this a real DoS?')
    def test_malicious_upload(self):
        '''Test POST /api/upload with malicious content
        '''
        # Ultimately, a node must have a ceiling at which
        #  it stops accepting uploaded content.
        class MaliciousUpload(object):
            def read(self, length):
                return bytes([1] * length)

            def close(self):
                pass

        response = self.app.post('/api/upload', data={
            'file': (MaliciousUpload(), 'malicious_'),
        }, follow_redirects=True)
        assert status.is_client_error(response.status_code)

    def test_insufficient_balance(self):
        contents = b'Z' * self.SAMPLE_UPLOAD_SIZE_BYTES
        filehash, key = self._upload(contents)

        orig_accts_api_enabled = settings.ACCOUNTS_API_ENABLED
        orig_accts_api_url     = settings.ACCOUNTS_API_BASE_URL
        accts_server = MockAccountsServer()
        settings.ACCOUNTS_API_ENABLED  = True
        settings.ACCOUNTS_API_BASE_URL = accts_server.url
        try:
            other_contents = b'P' * self.SAMPLE_UPLOAD_SIZE_BYTES
            with self.assertRaises(self.FailedResponseException) as upl_exc:
                self._upload(other_contents, token='invalidtoken')

            assert status.is_client_error(upl_exc.exception.response.status_code)

            with self.assertRaises(self.FailedResponseException) as down_exc:
                self._download(filehash, key, 'invalidtoken')

            assert status.is_client_error(down_exc.exception.response.status_code)

        finally:
            settings.ACCOUNTS_API_ENABLED  = orig_accts_api_enabled
            settings.ACCOUNTS_API_BASE_URL = orig_accts_api_url
            del accts_server

    @unittest.skip('Feature not yet developed, difficult to implement')
    def test_refund(self):
        '''Exercise the refund path by injecting a fault into cloudmanager.warm_up()
        '''
        from index import get_webcore
        def warm_up_always_fails(self, filehash):
            return None

        app = flask.Flask(index.__name__)
        with app.test_request_context('/api/download'):
            contents = b'q' * self.SAMPLE_UPLOAD_SIZE_BYTES
            filehash, key = self._upload(contents)

            WebCore().cloud.cloud_sync()

            cm = get_webcore().cloud
            from flask import g #FIXME: this 'g' instance is independent of the one to be used by index.download()
#           g._web_core.cloud.warm_up = warm_up_always_fails
            cm.warm_up = warm_up_always_fails

            with self.assertRaises(self.FailedResponseException) as download_exc:
                self._download(filehash, key)

            assert status.is_server_error(download_exc.exception.response.status_code)

    def tearDown(self):
        with self.db.cursor() as cursor:
            with open('tests/test_db_teardown.sql') as f:
                cursor.execute(f.read())

        self.db.close()
        shutil.rmtree(self.storage_path)

from webcore import accounts

class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.accts_server = MockAccountsServer()
        self.url = self.accts_server.url

    def test_accts(self):
        self.accts = accounts.create(True, self.url, b'falsekey')
        assert self.accts.consume('invalidtoken', 0.1) == None
        assert self.accts.deposit('invalidtoken', 0.1) == None

    def test_accts_failures(self):
        self.accts = accounts.create(True, self.url, b'falsekey')
        hdrs = self.accts.headers()

        response = self.accts.consume('realtoken', 0.1)
        assert response.token == 'realtoken'
        assert response.amount == 0.1
        response = self.accts.deposit('realtoken', 0.1)
        assert response.token == 'realtoken'
        assert response.amount == 0.1

    def tearDown(self):
        del self.accts_server


if __name__ == '__main__':
    unittest.main()
