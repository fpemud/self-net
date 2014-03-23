#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

class LocalSockSendObj:
	dataObj = None							# obj

class LocalSockSetWorkState:
	workState = None						# enum

class LocalSockCall:
	funcName = None							# str
	funcArgs = None							# list<obj>

class LocalSockRetn:
	retVal = None							# obj, None means no return value

class LocalSockExcp:
	excObj = None							# str
	excInfo = None							# str

