#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import socket
import pyinotify
from gi.repository import GObject

class SnCfgService:
	user = None
	name = None

class SnCfgHost:
	name = None
	port = None

class SnConfigManager(GObject.GObject):
	"""/etc/selfnetd
	    |----cert.pem							# mode 644
		|----privkey.pem						# mode 600
		|----ca-cert.pem						# mode 644
		|----ca-privkey.pem						# mode 600, only on the nexus machine
	    |----hosts.xml
	    |----selfnetd.conf"""

	__gsignals__ = {
		'host_added': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'host_changed': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'host_deleted': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'service_add': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
		'service_delete': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
	}

	def __init__(self, param):
		GObject.GObject.__init__(self)

		self.param = param
		self.hostList = []
		self.serviceDict = dict()

	def init(self):
		self._checkCertFiles()
		newHostList = self._parseHostsFile()
		self._updateHostList(newHostList)

	def addService(self, userName, serviceName, serviceObj):
		key = (userName, serviceName)
		assert key not in self.serviceDict
		self.serviceDict[key] = serviceObj

	def removeService(self, userName, serviceName):
		key = (userName, serviceName)
		self.serviceDict.remove(key)

	def getService(self, userName, serviceName):
		key = (userName, serviceName)
		assert key in self.serviceDict
		self.serviceDict[key]

	def _checkCertFiles(self):
		# check CA certificate
		x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, self.param.caCertFile)
		if x509.has_expired():
			raise Exception("CA certificate has expired")

		# check certificate
		x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, self.param.certFile)
		if x509.has_expired():
			raise Exception("Certificate has expired")

		foundCommonName = False
		for item in x509.get_subject().get_components():
			if item[0] == "CN":
				if item[1] != socket.gethostname():
					raise Exception("Common name in certificate must equal to hostname")
				foundCommonName = True
				break
		if not foundCommonName:
			raise Exception("No common name in certificate")

	def _parseHostsFile(self):
		class thehandler(xml.sax.handler.ContentHandler):
			INIT = 0
			IN_HOST = 1
			IN_HOST_NAME = 2
			IN_HOST_PORT = 3

			def __init__(self):
				self.hostList = []
				self.curHost = None
				self.state = INIT

			def startElement(self, name, attrs):
				if name == "host" and self.state == INIT:
					self.state = IN_HOST:
					self.curHost = SnCfgHost()
				elif name == "name" and self.state == IN_HOST:
					self.state = IN_HOST_NAME
				elif name == "port" and self.state == IN_HOST:
					self.state = IN_HOST_PORT
				else:
					raise Exception("Failed to parse hosts file")

			def endElement(self, name, attrs):
				if name == "host" and self.state == IN_HOST:
					self.hostList.append(self.curHost)
					self.curHost = None
					self.state = INIT
				elif name == "name" and self.state == IN_HOST_NAME:
					self.state = IN_HOST
				elif name == "port" and self.state == IN_HOST_PORT:
					self.state = IN_HOST
				else:
					raise Exception("Failed to parse hosts file")

			def characters(self, content):
				if self.stat == IN_HOST_NAME:
					self.curHost.name = content
				elif self.stat == IN_HOST_PORT:
					self.curHost.port = int(content)
				else:
					raise Exception("Failed to parse hosts file")

		h = thehandler()
		xml.sax.parse(self.param.hostsFile, h)

		found = False
		for nho in h.hostList:
			if nho.name == socket.gethostname():
				found = True
				break
		if not found:
			raise Exception("No localhost in hosts file")

		return h.hostList

	def _updateHostList(self, newHostList):
		for ho in self.hostList:
			found = False
			for nho in newHostList:
				if nho.name == ho.name:
					found = True
					break
			if not found:
				pass		# fire deletion event

		# check for modification
		for ho in self.hostList:
			for nho in newHostList:
				if nho.name == ho.name:
					if nho.port != ho.port:
						pass		# fire modification event

					break

		# check for addition
		for nho in newHostList:
			found = False
			for ho in self.hostList:
				if ho.name == nho.name:
					found = True
					break
			if not found:
				pass		# fire addition event

		self.hostList = newHostList

GObject.type_register(SnConfigManager)

