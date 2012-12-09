'''
Created on Sep 8, 2011

@author: Spike
'''
from __future__ import with_statement

import os
import re
import pwd
import sys
import time
import logging
import subprocess

from . import lazy
from scalarizr.bus import bus
from scalarizr.util import initdv2, system2, run_detached, software, wait_until
from scalarizr.config import BuiltinBehaviours




SERVICE_NAME = CNF_SECTION = BuiltinBehaviours.RABBITMQ
RABBIT_CFG_PATH = '/etc/rabbitmq/rabbitmq.config'
COOKIE_PATH = '/var/lib/rabbitmq/.erlang.cookie'
RABBITMQ_ENV_CNF_PATH = '/etc/rabbitmq/rabbitmq-env.conf'
SCALR_USERNAME = 'scalr'


class NodeTypes:
	RAM = 'ram'
	DISK = 'disk'

RABBITMQCTL = software.which('rabbitmqctl')
RABBITMQ_SERVER = software.which('rabbitmq-server')

# RabbitMQ from ubuntu repo puts rabbitmq-plugins
# binary in non-obvious place
try:
	RABBITMQ_PLUGINS = software.which('rabbitmq-plugins')
except LookupError:
	possible_path = '/usr/lib/rabbitmq/bin/rabbitmq-plugins'

	if os.path.exists(possible_path):
		RABBITMQ_PLUGINS = possible_path
	else:
		raise



class RabbitMQInitScript(initdv2.ParametrizedInitScript):

	@lazy
	def __new__(cls, *args, **kws):
		obj = super(RabbitMQInitScript, cls).__new__(cls, *args, **kws)
		cls.__init__(obj)
		return obj
	
	def __init__(self):
		initdv2.ParametrizedInitScript.__init__(
				self,
				'rabbitmq',
				'/etc/init.d/rabbitmq-server',
				'/var/run/rabbitmq/pid',
				socks=[initdv2.SockParam(5672, timeout=20)]
				)
		
	def stop(self, reason=None):
		system2((RABBITMQCTL, 'stop'))
		wait_until(lambda: not self._running, sleep=2)
		
	
	def restart(self, reason=None):
		self.stop()
		self.start()

	reload = restart

	def start(self):
		env = {'RABBITMQ_PID_FILE': '/var/run/rabbitmq/pid',
			    'RABBITMQ_MNESIA_BASE': '/var/lib/rabbitmq/mnesia'}
		
		run_detached(RABBITMQ_SERVER, args=['-detached'], env=env)
		initdv2.wait_sock(self.socks[0])
				
		
	def status(self):
		if self._running:
			return initdv2.Status.RUNNING
		else:
			return initdv2.Status.NOT_RUNNING
		
	@property
	def _running(self):
		rcode = system2((RABBITMQCTL, 'status'), raise_exc=False)[2]
		return False if rcode else True
			
		
initdv2.explore(SERVICE_NAME, RabbitMQInitScript)

	
	
class RabbitMQ(object):
	_instance = None
	
	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(RabbitMQ, cls).__new__(
								cls, *args, **kwargs)
		return cls._instance
	

	def __init__(self):
		self._cnf = bus.cnf
		self._logger = logging.getLogger(__name__)

		for dirname in os.listdir('/usr/lib/rabbitmq/lib/'):
			if dirname.startswith('rabbitmq_server'):
				self.plugin_dir = os.path.join('/usr/lib/rabbitmq/lib/', dirname, 'plugins')
				break
		else:
			raise Exception('RabbitMQ plugin directory not found')
		
		self.service = initdv2.lookup(SERVICE_NAME)

	def set_cookie(self, cookie):
		cookie = self._cnf.rawini.get(CNF_SECTION, 'cookie')
		with open(COOKIE_PATH, 'w') as f:
			f.write(cookie)
		rabbitmq_user = pwd.getpwnam("rabbitmq")
		os.chmod(COOKIE_PATH, 0600)
		os.chown(COOKIE_PATH, rabbitmq_user.pw_uid, rabbitmq_user.pw_gid)


	def enable_plugin(self, plugin_name):
		system2((RABBITMQ_PLUGINS, 'enable', plugin_name), logger=self._logger)	
	
	
	def reset(self):
		system2((RABBITMQCTL, 'reset'), logger=self._logger)
	
	
	def stop_app(self):		
		system2((RABBITMQCTL, 'stop_app'), logger=self._logger)
	
	
	def start_app(self):
		system2((RABBITMQCTL, 'start_app'), logger=self._logger)
		
		
	def check_scalr_user(self, password):
		if SCALR_USERNAME in self.list_users():
			self.set_user_password(SCALR_USERNAME, password)
			self.set_user_tags(SCALR_USERNAME, 'administrator')
		else:
			self.add_user(SCALR_USERNAME, password, True)
			
		self.set_full_permissions(SCALR_USERNAME)
					
		
	def add_user(self, username, password, is_admin=False):
		system2((RABBITMQCTL, 'add_user', username, password), logger=self._logger)
		if is_admin:
			self.set_user_tags(username, 'administrator')			
	
	
	def delete_user(self, username):
		if username in self.list_users():
			system2((RABBITMQCTL, 'delete_user', username), logger=self._logger)
			
			
	def set_user_tags(self, username, tags):
		if type(tags) == str:
			tags = (tags,)
		system2((RABBITMQCTL, 'set_user_tags', username) + tags , logger=self._logger)
		
		
	def set_user_password(self, username, password):
		system2((RABBITMQCTL, 'change_password', username, password), logger=self._logger)
		
		
	def set_full_permissions(self, username):
		""" Set full permissions on '/' virtual host """ 
		permissions = ('.*', ) * 3
		system2((RABBITMQCTL, 'set_permissions', username) + permissions, logger=self._logger)
			

	def list_users(self):
		out = system2((RABBITMQCTL, 'list_users'), logger=self._logger)[0]
		users_strings = out.splitlines()[1:-1]
		return [user_str.split()[0] for user_str in users_strings]
	
	@property
	def node_type(self):
		return self._cnf.rawini.get(CNF_SECTION, 'node_type')
	
	
	def cluster_with(self, hostnames, do_reset=True):
		nodes = ['rabbit@%s' % host for host in hostnames]
		cmd = [RABBITMQCTL, 'cluster'] + nodes
		
		clustered = False
		
		while not clustered:
			self.stop_app()
			if do_reset:
				self.reset()
			system2(cmd, logger=self._logger)
			
			p = subprocess.Popen((RABBITMQCTL, 'start_app'))
			for i in range(15):
				if p.poll() is None:
					time.sleep(1)
					continue
								
				if p.returncode:
					raise Exception(p.stderr.read())
				else:
					clustered = True
					break
			else:
				p.kill()
				self.service.restart(force=True)
				
	
	def cluster_nodes(self):
		out = system2((RABBITMQCTL, 'cluster_status'),logger=self._logger)[0]
		nodes_raw = out.split('running_nodes')[0].split('\n', 1)[1]
		return re.findall("rabbit@([^']+)", nodes_raw)


rabbitmq = RabbitMQ()




		