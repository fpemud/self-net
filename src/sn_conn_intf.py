#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class SnConnIntfSocket:

	def send(self, buf):
		assert False

	def recv(self, buf):
		assert False

class SnConnIntfBulk:

	def isBulkReady(self):
		assert False

	def readBulk(self):
		assert False

	def writeBulk(self, bulkBuf):
		assert False

	def clearBulk(self):
		assert False

