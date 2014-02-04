#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import logging

def basicConfig(**kwargs):
	logging.basicConfig(**kwargs)
	logging.getLogger().setFormatter(_LoggingFormatter())
	logging.getLogger().setLevel(logging.WARNING)

def setLogLevel(levelname):
	if levelname == "CRITICAL":
		logLevel = logging.CRITICAL
	elif levelname == "ERROR":
		logLevel = logging.ERROR
	elif levelname == "WARNING":
		logLevel = logging.WARNING
	elif levelname == "INFO":
		logLevel = logging.INFO
	elif levelname == "DEBUG":
		logLevel = logging.DEBUG
	else:
		assert False		
	logging.getLogger().setLevel(logLevel)

def debug(msg, *args, **kwargs):
	logging.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
	logging.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
	logging.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
	logging.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
	logging.critical(msg, *args, **kwargs)

def functionStart(*args, **kwargs):
	msg = _function_msg_helper("Start")
	logging.debug(msg)

def functionEnd(*args, **kwargs):
	msg = _function_msg_helper("End")
	logging.debug(msg)

def functionSucc(*args, **kwargs):
	msg = _function_msg_helper("Succ")
	logging.debug(msg)

def functionFail(*args, **kwargs):
	msg = _function_msg_helper("Fail")
	logging.debug(msg)

### implementation ###

class _LoggingFormatter:

	def __init__(self):
		self.formLevelGeneral = logging.Formatter()
		self.formLevelDebug = logging.Formatter("[%(funcName)()] %(message)s")

    def format(self, record):
		if record.levelno == logging.DEBUG:
			return self.formLevelDebug.format(record)
		else:
			return self.formLevelGeneral.format(record)

	def formatTime(self, record, datefmt=None):
		if record.levelno == logging.DEBUG:
			return self.formLevelDebug.formatTime(record, datefmt)
		else:
			return self.formLevelGeneral.formatTime(record, datefmt)

	def formatException(self, exc_info):
		return self.formLevelDebug.formatException(exc_info)

def _function_msg_helper(msg, *args, **kwargs):
	for i in args:
		msg += ", %s"%(i)
	for k, v in kwargs:
		msg += ", %s:%s"%(k, v)
	return msg

