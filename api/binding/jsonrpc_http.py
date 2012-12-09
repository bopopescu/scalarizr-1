'''
JSON-RPC over HTTP. 

Public Scalarizr API

- Simple to Learn
- Simple to Use
'''
from __future__ import with_statement

import os
import binascii
import logging
import sys
import time
import urllib2
import hashlib
import hmac
try:
	import json
except ImportError:
	import simplejson as json


from scalarizr import rpc
from scalarizr.util import cryptotool
from scalarizr.bus import bus

LOG_CATEGORY = 'scalarizr.api'
LOG = logging.getLogger(LOG_CATEGORY)



class Security(object):
	DATE_FORMAT = "%a %d %b %Y %H:%M:%S UTC"
	
	def __init__(self, crypto_key_path):
		self.crypto_key_path = crypto_key_path

	def _read_crypto_key(self):
		return binascii.a2b_base64(open(self.crypto_key_path).read().strip())
	
	def sign(self, data, key, timestamp=None):
		date = time.strftime(self.DATE_FORMAT, timestamp or time.gmtime())
		canonical_string = data + date
		
		digest = hmac.new(key, canonical_string, hashlib.sha1).digest()
		sign = binascii.b2a_base64(digest)
		if sign.endswith('\n'):
			sign = sign[:-1]
		return sign, date
	
	
	def check_signature(self, signature, data, timestamp):
		calc_signature = self.sign(data, self._read_crypto_key(), 
								time.strptime(timestamp, self.DATE_FORMAT))[0]
		assert signature == calc_signature, "Signature doesn't match"
	
	
	def decrypt_data(self, data):
		try:
			return cryptotool.decrypt(data, self._read_crypto_key())
		except:
			raise rpc.InvalidRequestError('Failed to decrypt data')

	def encrypt_data(self, data):
		try:
			return cryptotool.encrypt(data, self._read_crypto_key())
		except:
			raise rpc.InvalidRequestError('Failed to encrypt data. Error: %s' % (sys.exc_info()[1], ))


class WsgiApplication(Security):

	def __init__(self, req_handler, crypto_key_path):
		Security.__init__(self, crypto_key_path)
		self.req_handler = req_handler		
	
	
	def __call__(self, environ, start_response):
		try:
			length = int(environ['CONTENT_LENGTH'])
			data = environ['wsgi.input'].read(length)
		except:
			data = ''
		
		try:
			try:
				self.check_signature(environ['HTTP_X_SIGNATURE'], data, environ['HTTP_DATE'])
				data = self.decrypt_data(data)
			except:
				start_response('400 Bad request', [], sys.exc_info())
				return str(sys.exc_info()[1])
			
			LOG.debug('request: %s', data)
			req = json.loads(data)
			with self.handle_meta_params(req):
				result = self.req_handler.handle_request(req, namespace=environ['PATH_INFO'][1:] or None)
			LOG.debug('response: %s', result)		
			
			result = self.encrypt_data(result)
			sig, date = self.sign(result, self._read_crypto_key())
			headers = [('Content-type', 'application/json'), 
					('Content-length', str(len(result))),
					('X-Signature', sig),
					('Date', date)]
			
			start_response('200 OK', headers)
			return result
		except:
			start_response('500 Internal Server Error', [], sys.exc_info())
			LOG.exception('Unhandled exception')
			return ''


	def handle_meta_params(self, req):
		if 'params' in req and '_platform_access_data' in req['params']:
			pl = bus.platform
			pl.set_access_data(req['params']['_platform_access_data'])
			del req['params']['_platform_access_data']
		return self
			
	def __enter__(self):
		return self
	
	
	def __exit__(self, *args):
		pl = bus.platform
		pl.clear_access_data()


class HttpServiceProxy(rpc.ServiceProxy, Security):

	def __init__(self, endpoint, crypto_key_path):
		Security.__init__(self, crypto_key_path)
		rpc.ServiceProxy.__init__(self)
		self.endpoint = endpoint

	
	def exchange(self, jsonrpc_req):
		jsonrpc_req = self.encrypt_data(jsonrpc_req)
		sig, date = self.sign(jsonrpc_req, self._read_crypto_key())
		
		headers = {
			'Date': date,
			'X-Signature': sig
		}
		namespace = self.local.method[0] if len(self.local.method) > 1 else ''
		
		http_req = urllib2.Request(os.path.join(self.endpoint, namespace), jsonrpc_req, headers)
		try:
			jsonrpc_resp = urllib2.urlopen(http_req).read()
			return self.decrypt_data(jsonrpc_resp)
		except urllib2.HTTPError, e:
			raise Exception('%s: %s' % (e.code, e.read()))

