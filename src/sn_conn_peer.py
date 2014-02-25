#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import errno
import pickle
import struct
import logging
from OpenSSL import SSL
from gi.repository import GLib
from sn_util import SnUtil

class SnPeerServer:

	def __init__(self, certFile, privkeyFile, caCertFile, connectFunc):
		self.handshaker = _HandShaker(certFile, privkeyFile, caCertFile, connectFunc)
		self.serverSock = None
		self.serverSourceId = None

	def dispose(self):
		if self.serverSock is not None:
			self.stop()
		self.handshaker.dispose()

	def start(self, port):
		assert self.serverSock is None
	
		self.serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.serverSock.bind(('0.0.0.0', port))
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
		logging.debug("SnPeerServer._onServerAccept: Start, %s", _cb_condition_to_str(cb_condition))

		assert not (cb_condition & _flagError)
		assert source == self.serverSock

		try:
			new_sock, addr = self.serverSock.accept()
			self.handshaker.addSocket(new_sock, True)

			logging.debug("SnPeerServer._onServerAccept: End")
			return True
		except socket.error as e:
			logging.debug("SnPeerServer._onServerAccept: Failed, %s, %s", e.__class__, e)
			return True

class SnPeerClient:

	def __init__(self, certFile, privkeyFile, caCertFile, connectFunc):
		self.handshaker = _HandShaker(certFile, privkeyFile, caCertFile, connectFunc)

	def dispose(self):
		self.handshaker.dispose()

	def connect(self, connectId, hostname, port):
		logging.debug("SnPeerClient.connect: Start, %d, %s, %d", connectId, hostname, port)

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.setblocking(0)

		try:
			sock.connect((hostname, port))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				pass
			else:
				logging.debug("SnPeerClient.connect: Failed, %s, %s", e.__class__, e)
				sock.close()
				return

		self.handshaker.addSocket(sock, False, connectId, hostname, port)

		logging.debug("SnPeerClient.connect: End")
		return

class _HandShaker:

	HANDSHAKE_NONE = 0
	HANDSHAKE_WANT_READ = 1
	HANDSHAKE_WANT_WRITE = 2
	HANDSHAKE_COMPLETE = 3

	def __init__(self, certFile, privkeyFile, caCertFile, connectFunc):
		self.certFile = certFile
		self.privkeyFile = privkeyFile
		self.caCertFile = caCertFile
		self.connectFunc = connectFunc
		self.sockDict = dict()

	def dispose(self):
		pass

	def addSocket(self, sock, serverSide, connectId=None, hostname=None, port=None):
		info = _HandShakerConnInfo()
		info.serverSide = serverSide
		info.state = _HandShaker.HANDSHAKE_NONE
		info.sslSock = None
		info.connectId = connectId
		info.hostname = hostname
		info.port = port
		info.spname = None					# value of socket.getpeername()
		self.sockDict[sock] = info

		sock.setblocking(0)
		GLib.io_add_watch(sock, GLib.IO_IN | GLib.IO_OUT | _flagError, self._onEvent)

	def _onEvent(self, source, cb_condition):
		info = self.sockDict[source]
		oldState = info.state

		try:
			# check error
			if cb_condition & _flagError:
				raise _ConnException("Socket error, %s"%(_cb_condition_to_str(cb_condition)))

			# HANDSHAKE_NONE
			if info.state == _HandShaker.HANDSHAKE_NONE:
				ctx = SSL.Context(SSL.SSLv3_METHOD)
				if info.serverSide:
					ctx.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, _sslVerifyDummy)
				else:
					ctx.set_verify(SSL.VERIFY_PEER, _sslVerifyDummy)
#				ctx.set_mode(SSL.MODE_ENABLE_PARTIAL_WRITE)					# fixme
				ctx.use_privatekey_file(self.privkeyFile)
				ctx.use_certificate_file(self.certFile)
				ctx.load_verify_locations(self.caCertFile)

				info.spname = str(source.getpeername())
				info.sslSock = SSL.Connection(ctx, source)
				if info.serverSide:
					info.sslSock.set_accept_state()
				else:
					info.sslSock.set_connect_state()
				info.state = _HandShaker.HANDSHAKE_WANT_WRITE

			# HANDSHAKE_WANT_READ & HANDSHAKE_WANT_WRITE
			if ((info.state == _HandShaker.HANDSHAKE_WANT_READ and cb_condition & GLib.IO_IN) or
					(info.state == _HandShaker.HANDSHAKE_WANT_WRITE and cb_condition & GLib.IO_OUT)):
				try:
					info.sslSock.do_handshake()
					info.state = _HandShaker.HANDSHAKE_COMPLETE
				except SSL.WantReadError:
					info.state = _HandShaker.HANDSHAKE_WANT_READ
				except SSL.WantWriteError:
					info.state = _HandShaker.HANDSHAKE_WANT_WRITE
				except SSL.Error as e:
					raise _ConnException("Handshake failed, %s"%(_handshake_info_to_str(info)), e)

			# HANDSHAKE_COMPLETE
			if info.state == _HandShaker.HANDSHAKE_COMPLETE:
				# check peer name
				peerName = SnUtil.getSslSocketPeerName(info.sslSock)
				if info.serverSide:
					if peerName is None:
						raise _ConnException("Hostname incorrect, %s, %s"%(_handshake_info_to_str(info), peerName))
				else:
					if peerName is None or peerName != info.hostname:
						raise _ConnException("Hostname incorrect, %s, %s"%(_handshake_info_to_str(info), peerName))

				# create SnPeerSocket
				del self.sockDict[source]
				self.connectFunc(info.sslSock)
				return False

		except _ConnException as e:
			del self.sockDict[source]
			source.close()
			if not e.hasExcObj:
				logging.debug("_HandShaker._onEvent: %s, %s", e.message, _handshake_info_to_str(info))
			else:
				logging.debug("_HandShaker._onEvent: %s, %s, %s, %s", e.message, _handshake_info_to_str(info),
						e.excName, e.excMessage)
			return False

		# register io watch callback again
		if info.state == _HandShaker.HANDSHAKE_WANT_READ:
			GLib.io_add_watch(source, GLib.IO_IN | _flagError, self._onEvent)
		elif info.state == _HandShaker.HANDSHAKE_WANT_WRITE:
			GLib.io_add_watch(source, GLib.IO_OUT | _flagError, self._onEvent)
		else:
			assert False

		return False

def _sslVerifyDummy(conn, cert, errnum, depth, ok):
	return ok

class _ConnException(Exception):
	def __init__(self, message, excObj=None):
		super(_ConnException, self).__init__(message)

		self.hasExcObj = False
		if excObj is not None:
			self.hasExcObj = True
			self.excName = excObj.__class__
			self.excMessage = excObj.message

class _HandShakerConnInfo:
	serverSide = None			# bool
	state = None				# enum
	sslSock = None				# obj
	connectId = None			# int
	hostname = None				# str
	port = None					# int
	spname = None				# str

def _cb_condition_to_str(cb_condition):
        ret = ""
        if cb_condition & GLib.IO_IN:
                ret += "IN "
        if cb_condition & GLib.IO_OUT:
                ret += "OUT "
        if cb_condition & GLib.IO_PRI:
                ret += "PRI "
        if cb_condition & GLib.IO_ERR:
                ret += "ERR "
        if cb_condition & GLib.IO_HUP:
                ret += "HUP "
        if cb_condition & GLib.IO_NVAL:
                ret += "NVAL "
        return ret

def _handshake_state_to_str(handshake_state):
	if handshake_state == _HandShaker.HANDSHAKE_NONE:
		return "NONE"
	elif handshake_state == _HandShaker.HANDSHAKE_WANT_READ:
		return "WANT_READ"
	elif handshake_state == _HandShaker.HANDSHAKE_WANT_WRITE:
		return "WANT_WRITE"
	elif handshake_state == _HandShaker.HANDSHAKE_COMPLETE:
		return "COMPLETE"
	else:
		assert False

def _handshake_info_to_str(info):
	if info.serverSide:
		return info.spname
	else:
		return "%d, %s, %d"%(info.connectId, info.hostname, info.port)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

