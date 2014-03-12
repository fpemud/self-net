#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
import errno
import logging
import libasyncns
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
		logging.debug("SnPeerServer._onServerAccept: Start, %s", SnUtil.cbConditionToStr(cb_condition))

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
		self.asyncns = libasyncns.Asyncns()

	def dispose(self):
		self.handshaker.dispose()

	def connect(self, hostname, port):
		resq = self.asyncns.getaddrinfo(hostname, None)
		resq.userdata = { "hostname":hostname, "port":port }
		self.asyncns.wait(False)
		GLib.io_add_watch(self.asyncns.get_fd(), GLib.IO_IN | _flagError, self._onResolveComplete)

	def _onResolveComplete(self, source, cb_condition):
		logging.debug("SnPeerClient._onResolveComplete: Start, %s", SnUtil.cbConditionToStr(cb_condition))

		assert not (cb_condition & _flagError)
		assert source == self.asyncns.get_fd()

		# get resolve result
		hostname = None
		port = None
		hostaddr = None
		try:
			resq = self.asyncns.get_next()
			assert type(resq) == libasyncns.AddrInfoQuery
			hostname = resq.userdata["hostname"]
			port = resq.userdata["port"]
			hostaddr, dummy = resq.get_done()[0][4]
		except Exception as e:
			logging.debug("SnPeerClient._onResolveComplete: Failed, %s, %s", e.__class__, e)
			return False

		# do connect
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.setblocking(0)
		try:
			sock.connect((hostaddr, port))
		except socket.error as e:
			if e.errno == errno.EAGAIN or e.errno == errno.EINPROGRESS:
				pass
			else:
				logging.debug("SnPeerClient._onResolveComplete: Failed, %s, %s", e.__class__, e)
				sock.close()
				return False

		# give socket to _HandShaker
		self.handshaker.addSocket(sock, False, hostname, port)

		logging.debug("SnPeerClient._onResolveComplete: End")
		return False

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

	def addSocket(self, sock, serverSide, hostname=None, port=None):
		info = _HandShakerConnInfo()
		info.serverSide = serverSide
		info.state = _HandShaker.HANDSHAKE_NONE
		info.sslSock = None
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
				raise _ConnException("Socket error, %s"%(SnUtil.cbConditionToStr(cb_condition)))

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

				# give socket to connectFunc
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
	hostname = None				# str
	port = None					# int
	spname = None				# str

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
		return "%s, %d"%(info.hostname, info.port)

_flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL

