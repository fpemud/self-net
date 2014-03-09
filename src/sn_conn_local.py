#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import logging
from gi.repository import GLib
from sn_util import SnUtil

class SnLocalServer:

	def __init__(self, connectFunc):
		self.connectFunc = connectFunc
		self.serverSock = None
		self.serverSourceId = None

	def dispose(self):
		if self.serverSock is not None:
			self.stop()

	def start(self, path):
		assert self.serverSock is None
		assert not os.path.exists(path)
	
		self.serverSock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.serverSock.bind(path)
		self.serverSock.listen(5)
		self.serverSock.setblocking(0)
		self.serverSourceId = GLib.io_add_watch(self.serverSock, GLib.IO_IN | _flagError, self._onServerAccept)

	def stop(self):
		assert self.serverSock is not None

		ret = GLib.source_remove(self.serverSourceId)
		assert ret

		self.serverSock.close()
		self.serverSock = None

	def _onServerAccept(self, source, cb_condition):
		logging.debug("SnLocalServer._onServerAccept: Start, %s", SnUtil.cbConditionToStr(cb_condition))

		assert not (cb_condition & _flagError)
		assert source == self.serverSock

		try:
			new_sock, addr = self.serverSock.accept()
			self.connectFunc(new_sock)
			logging.debug("SnLocalServer._onServerAccept: End")
			return True
		except socket.error as e:
			logging.debug("SnLocalServer._onServerAccept: Failed, %s, %s", e.__class__, e)
			return True

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

