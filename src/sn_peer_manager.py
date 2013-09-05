#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GObject

class SnPeerManager(GObject.GObject):

	def __init__(self, param):
		GObject.GObject.__init__(self)
		self.param = param
		self.activePeerList = []

	def init(self):
		# create server socket

		# create peer probe timer

		# create peer keep-alive timer

	def getPeerList(self):
		pass

	def getPeer(self, peerName):
		pass

	def probePeers(self):
		"""Called once when selfnetd starts"""
		pass

GObject.type_register(SnPeerManager)

