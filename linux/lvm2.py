'''
Created on Aug 28, 2012

@author: marat
'''

from __future__ import with_statement

import os
import logging
import base64
import collections

from scalarizr import linux

if not linux.which('lvs'):
	from scalarizr.linux import pkgmgr
	pkgmgr.installed('lvm2')


LOG = logging.getLogger(__name__)

class NotFound(linux.LinuxError):
	pass

def system(*args, **kwargs):
	kwargs['logger'] = LOG
	kwargs['close_fds'] = True
	'''
	To prevent this garbage in stderr (Fedora/CentOS):
	File descriptor 6 (/tmp/ffik4yjng (deleted)) leaked on lv* invocation. 
	Parent PID 29542: /usr/bin/python
	'''
	return linux.system(*args, **kwargs)


_columns = 'pv_name,vg_name,pv_fmt,pv_attr,pv_size,pv_free,pv_uuid'
class PVInfo(collections.namedtuple('PVInfo', _columns)):
	COLUMNS = _columns


_columns = 'vg_name,pv_count,lv_count,snap_count,vg_attr,vg_size,vg_free'
class VGInfo(collections.namedtuple('VGInfo', _columns)):
	COLUMNS = _columns
	
	@property
	def path(self):
		return '/dev/%s' % self.vg_name


_columns = 'vg_name,lv_uuid,lv_name,lv_attr,lv_major,lv_minor,lv_read_ahead,' \
		'lv_kernel_major,lv_kernel_minor,lv_kernel_read_ahead,lv_size,seg_count,' \
		'origin,origin_size,snap_percent,copy_percent,move_pv,convert_lv,' \
		'lv_tags,mirror_log,modules'
class LVInfo(collections.namedtuple('LVInfo', _columns)):
	COLUMNS = _columns
	@property
	def lv_path(self):
		return lvpath(self.vg_name, self.lv_name)
	path = lv_path
del _columns


def lvpath(volume_group_name, logical_volume_name):
	return '/dev/mapper/%s-%s' % (volume_group_name.replace('-', '--'), 
								logical_volume_name.replace('-', '--'))


def lvs(*volume_groups, **long_kwds):
	try:
		long_kwds.update({
			'options': LVInfo.COLUMNS,
			'separator': '|',
			'noheadings': True
		})
		out = linux.system(linux.build_cmd_args(
				executable='/sbin/lvs', 
				long=long_kwds, 
				params=volume_groups))[0]
		ret = {}
		for line in out.splitlines():
			item = LVInfo(*line.strip().split('|'))
			ret['%s/%s' % (item.vg_name, item.lv_name)] = item
		return ret
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def pvs(*physical_volumes, **long_kwds):
	try:
		long_kwds.update({
			'options': PVInfo.COLUMNS,
			'separator': '|',
			'noheadings': True
		})
		out = linux.system(linux.build_cmd_args(
				executable='/sbin/pvs', 
				long=long_kwds, 
				params=physical_volumes))[0]
		ret = {}
		for line in out.splitlines():
			item = PVInfo(*line.strip().split('|'))
			ret[item.pv_name] = item
		return ret
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def vgs(*volume_groups, **long_kwds):
	try:
		long_kwds.update({
			'options': VGInfo.COLUMNS,
			'separator': '|',
			'noheadings': True
		})
		out = linux.system(linux.build_cmd_args(
				executable='/sbin/vgs', 
				long=long_kwds, 
				params=volume_groups))[0]
		ret = {}
		for line in out.splitlines():
			item = VGInfo(*line.strip().split('|'))
			ret[item.vg_name] = item
		return ret
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise
	

def pvcreate(*physical_volumes, **long_kwds):
	long_kwds.update({'yes': True, 'force': True})
	return linux.system(linux.build_cmd_args(
			executable='/sbin/pvcreate', 
			long=long_kwds, 
			params=physical_volumes))


def pvchange(*physical_volume_paths, **long_kwds):
	try:
		return linux.system(linux.build_cmd_args(
				executable='/sbin/pvchange',
				long=long_kwds,
				params=physical_volume_paths))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def pvscan(**long_kwds):
	return linux.system(linux.build_cmd_args(
			executable='/sbin/pvscan',
			long=long_kwds))


def pvremove(*physical_volumes, **long_kwds):
	try:
		long_kwds.update({
			'force': True, 
			'yes': True
		})
		return linux.system(linux.build_cmd_args(
				executable='/sbin/pvremove', 
				long=long_kwds, 
				params=physical_volumes))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def vgcreate(volume_group_name, *physical_volumes, **long_kwds):
	return linux.system(linux.build_cmd_args(
			executable='/sbin/vgcreate', 
			long=long_kwds, 
			params=[volume_group_name] + list(physical_volumes)))


def vgchange(*volume_group_names, **long_kwds):
	try:
		return linux.system(linux.build_cmd_args(
				executable='/sbin/vgchange',
				long=long_kwds,
				params=volume_group_names))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def vgextend(volume_group_name, *physical_volumes, **long_kwds):
	try:
		long_kwds.update({
			'force': True, 
			'yes': True
		})
		return linux.system(linux.build_cmd_args(
				executable='/sbin/vgextend', 
				long=long_kwds, 
				params=[volume_group_name] + list(physical_volumes)))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise
		

def vgremove(*volume_group_names, **long_kwds):
	try:
		long_kwds.update({'force': True})
		return linux.system(linux.build_cmd_args(
				executable='/sbin/vgremove',
				long=long_kwds,
				params=volume_group_names))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def vgcfgrestore(volume_group_name, **long_kwds):
	return linux.system(linux.build_cmd_args(
		executable='/sbin/vgcfgrestore',
		long=long_kwds,
		params=[volume_group_name]))



def lvcreate(*params, **long_kwds):
	return linux.system(linux.build_cmd_args(
			executable='/sbin/lvcreate',
			long=long_kwds,
			params=params))


def lvchange(*logical_volume_path, **long_kwds):
	try:
		long_kwds.update({'yes': True})
		return linux.system(linux.build_cmd_args(
				executable='/sbin/lvchange', 
				long=long_kwds, 
				params=logical_volume_path))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise

def lvremove(*logical_volume_paths, **long_kwds):
	try:
		long_kwds.update({'force': True})
		return linux.system(linux.build_cmd_args(
				executable='/sbin/lvremove',
				long=long_kwds,
				params=logical_volume_paths))
	except linux.LinuxError, e:
		if e.returncode == 5:
			raise NotFound()
		raise


def lvextend(logical_volume_path, **long_kwds):
	return linux.system(linux.build_cmd_args(
		executable='/sbin/lvextend',
		long=long_kwds,
		params=[logical_volume_path]))



def backup_vg_config(vg_name):
	vgfile = '/etc/lvm/backup/%s' % os.path.basename(vg_name)
	if os.path.exists(vgfile):
		with open(vgfile) as f:
			return base64.b64encode(f.read())
	raise NotFound('Volume group %s not found' % vg_name)


def dmsetup(command, device=None, **long_kwargs):
	return linux.system(linux.build_cmd_args(
		executable='/sbin/dmsetup',
		short = [command, device or ''],
		long=long_kwargs
	))
