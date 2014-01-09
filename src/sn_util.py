#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import subprocess
import time
import grp
import pwd
import socket
import re
import ssl
import struct

class SnUtil:

	@staticmethod
	def getSysctl(name):
		msg = SnUtil.shell("/sbin/sysctl -n %s"%(name), "stdout")
		return msg.rstrip('\n')

	@staticmethod
	def setSysctl(name, value):
		return

	@staticmethod
	def copyToDir(srcFilename, dstdir, mode=None):
		"""Copy file to specified directory, and set file mode if required"""

		if not os.path.isdir(dstdir):
			os.makedirs(dstdir)
		fdst = os.path.join(dstdir, os.path.basename(srcFilename))
		shutil.copy(srcFilename, fdst)
		if mode is not None:
			SnUtil.shell("/bin/chmod " + mode + " \"" + fdst + "\"")

	@staticmethod
	def copyToFile(srcFilename, dstFilename, mode=None):
		"""Copy file to specified filename, and set file mode if required"""

		if not os.path.isdir(os.path.dirname(dstFilename)):
			os.makedirs(os.path.dirname(dstFilename))
		shutil.copy(srcFilename, dstFilename)
		if mode is not None:
			SnUtil.shell("/bin/chmod " + mode + " \"" + dstFilename + "\"")

	@staticmethod
	def readFile(filename):
		"""Read file, returns the whold content"""

		f = open(filename, 'r')
		buf = f.read()
		f.close()
		return buf

	@staticmethod
	def writeFile(filename, buf, mode=None):
		"""Write buffer to file"""

		f = open(filename, 'w')
		f.write(buf)
		f.close()
		if mode is not None:
			SnUtil.shell("/bin/chmod " + mode + " \"" + filename + "\"")

	@staticmethod
	def mkDirAndClear(dirname):
		SnUtil.forceDelete(dirname)
		os.mkdir(dirname)

	@staticmethod
	def touchFile(filename):
		assert not os.path.exists(filename)
		f = open(filename, 'w')
		f.close()

	@staticmethod
	def forceDelete(filename):
		if os.path.islink(filename):
			os.remove(filename)
		elif os.path.isfile(filename):
			os.remove(filename)
		elif os.path.isdir(filename):
			shutil.rmtree(filename)

	@staticmethod
	def forceSymlink(source, link_name):
		if os.path.exists(link_name):
			os.remove(link_name)
		os.symlink(source, link_name)

	@staticmethod
	def getFreeSocketPort(portType, portStart, portEnd):
		if portType == "tcp":
			sType = socket.SOCK_STREAM
		elif portType == "udp":
			assert False
		else:
			assert False

		for port in range(portStart, portEnd+1):
			s = socket.socket(socket.AF_INET, sType)
			try:
				s.bind((('', port)))
				return port
			except socket.error:
				continue
			finally:
				s.close()
		raise Exception("No valid %s port in [%d,%d]."%(portType, portStart, portEnd))

	@staticmethod
	def shell(cmd, flags=""):
		"""Execute shell command"""

		assert cmd.startswith("/")

		# Execute shell command, throws exception when failed
		if flags == "":
			retcode = subprocess.Popen(cmd, shell = True).wait()
			if retcode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d"%(cmd, retcode))
			return

		# Execute shell command, throws exception when failed, returns stdout+stderr
		if flags == "stdout":
			proc = subprocess.Popen(cmd,
				                    shell = True,
				                    stdout = subprocess.PIPE,
				                    stderr = subprocess.STDOUT)
			out = proc.communicate()[0]
			if proc.returncode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d"%(cmd, proc.returncode))
			return out

		# Execute shell command, returns (returncode,stdout+stderr)
		if flags == "retcode+stdout":
			proc = subprocess.Popen(cmd,
				                    shell = True,
				                    stdout = subprocess.PIPE,
				                    stderr = subprocess.STDOUT)
			out = proc.communicate()[0]
			return (proc.returncode, out)

		assert False

	@staticmethod
	def shellInteractive(cmd, strInput, flags=""):
		"""Execute shell command with input interaction"""

		assert cmd.startswith("/")

		# Execute shell command, throws exception when failed
		if flags == "":
			proc = subprocess.Popen(cmd,
									shell = True,
									stdin = subprocess.PIPE)
			proc.communicate(strInput)
			if proc.returncode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d"%(cmd, proc.returncode))
			return

		# Execute shell command, throws exception when failed, returns stdout+stderr
		if flags == "stdout":
			proc = subprocess.Popen(cmd,
									shell = True,
									stdin = subprocess.PIPE,
									stdout = subprocess.PIPE,
									stderr = subprocess.STDOUT)
			out = proc.communicate(strInput)[0]
			if proc.returncode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d, output %s"%(cmd, proc.returncode, out))
			return out

		# Execute shell command, returns (returncode,stdout+stderr)
		if flags == "retcode+stdout":
			proc = subprocess.Popen(cmd,
									shell = True,
									stdin = subprocess.PIPE,
									stdout = subprocess.PIPE,
									stderr = subprocess.STDOUT)
			out = proc.communicate(strInput)[0]
			return (proc.returncode, out)

		assert False

	@staticmethod
	def ipMaskToLen(mask):
		"""255.255.255.0 -> 24"""

		netmask = 0
		netmasks = mask.split('.')
		for i in range(0,len(netmasks)):
			netmask *= 256
			netmask += int(netmasks[i])
		return 32 - (netmask ^ 0xFFFFFFFF).bit_length()

	@staticmethod
	def loadKernelModule(modname):
		"""Loads a kernel module."""

		SnUtil.shell("/sbin/modprobe %s"%(modname))

	@staticmethod
	def initLog(filename):
		SnUtil.forceDelete(filename)
		SnUtil.writeFile(filename, "")

	@staticmethod
	def printLog(filename, msg):
		f = open(filename, 'a')
		if msg != "":
			f.write(time.strftime("%Y-%m-%d %H:%M:%S  ", time.localtime()))
			f.write(msg)
			f.write("\n")
		else:
			f.write("\n")
		f.close()

	@staticmethod
	def getUsername():
		return pwd.getpwuid(os.getuid())[0]

	@staticmethod
	def getGroups():
		"""Returns the group name list of the current user"""

		uname = pwd.getpwuid(os.getuid())[0]
		groups = [g.gr_name for g in grp.getgrall() if uname in g.gr_mem]
		gid = pwd.getpwnam(uname).pw_gid
		groups.append(grp.getgrgid(gid).gr_name)			# --fixme, should be prepend
		return groups

	@staticmethod
	def getPidBySocket(socketInfo):
		"""need to be run by root. socketInfo is like 0.0.0.0:80"""

		rc, ret = SnUtil.shell("/bin/netstat -anp | grep \"%s\""%(socketInfo), "retcode+stdout")
		if rc != 0:
			return -1
		print ret

		m = re.search(" +([0-9]+)/.*$", ret, re.MULTILINE)
		assert m is not None
		return int(m.group(1))

	@staticmethod
	def dbusGetUserName(connection, sender):
		if sender is None:
			return None
		uid = connection.get_unix_user(sender)
		return pwd.getpwuid(uid).pw_name

	@staticmethod
	def tdbFileCreate(filename):
		assert " " not in filename			# fixme, tdbtool can't operate filename with space

		inStr = ""
		inStr += "create %s\n"%(filename)
		inStr += "quit\n"
		SnUtil.shellInteractive("/usr/bin/tdbtool", inStr)

	@staticmethod
	def tdbFileAddUser(filename, username, password):
		"""can only add unix user"""

		assert " " not in filename			# fixme, v can't operate filename with space

		inStr = ""
		inStr += "%s\n"%(password)
		inStr += "%s\n"%(password)
		SnUtil.shellInteractive("/usr/bin/pdbedit -b tdbsam:%s -a \"%s\" -t"%(filename, username), inStr)

class Daemon:
	"""
	A generic daemon class.
       
	Usage: subclass the Daemon class and override the run() method
	"""
	def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
		self.stdin = stdin
		self.stdout = stdout
		self.stderr = stderr
		self.pidfile = pidfile
       
	def daemonize(self):
		"""
		do the UNIX double-fork magic, see Stevens' "Advanced
		Programming in the UNIX Environment" for details (ISBN 0201563177)
		http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
		"""
		try:
			pid = os.fork()
			if pid > 0:
				# exit first parent
				sys.exit(0)
		except OSError, e:
			sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)
       
		# decouple from parent environment
		os.chdir("/")
		os.setsid()
		os.umask(0)
       
		# do second fork
		try:
			pid = os.fork()
			if pid > 0:
				# exit from second parent
				sys.exit(0)
		except OSError, e:
			sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)
       
		# redirect standard file descriptors
		sys.stdout.flush()
		sys.stderr.flush()
		si = file(self.stdin, 'r')
		so = file(self.stdout, 'a+')
		se = file(self.stderr, 'a+', 0)
		os.dup2(si.fileno(), sys.stdin.fileno())
		os.dup2(so.fileno(), sys.stdout.fileno())
		os.dup2(se.fileno(), sys.stderr.fileno())
       
		# write pidfile
		atexit.register(self._delpid)
		pid = str(os.getpid())
		file(self.pidfile,'w+').write("%s\n" % pid)
       
	def _delpid(self):
		os.remove(self.pidfile)
 
	def start(self):
		"""
		Start the daemon
		"""
		# Check for a pidfile to see if the daemon already runs
		try:
			pf = file(self.pidfile,'r')
			pid = int(pf.read().strip())
			pf.close()
		except IOError:
			pid = None
       
		if pid:
			message = "pidfile %s already exist. Daemon already running?\n"
			sys.stderr.write(message % self.pidfile)
			sys.exit(1)
	       
		# Start the daemon
		self._daemonize()
		self.run()
 
	def stop(self):
		"""
		Stop the daemon
		"""
		# Get the pid from the pidfile
		try:
			pf = file(self.pidfile,'r')
			pid = int(pf.read().strip())
			pf.close()
		except IOError:
			pid = None
       
		if not pid:
			message = "pidfile %s does not exist. Daemon not running?\n"
			sys.stderr.write(message % self.pidfile)
			return # not an error in a restart
 
		# Try killing the daemon process       
		try:
			while 1:
				os.kill(pid, SIGTERM)
				time.sleep(0.1)
		except OSError, err:
			err = str(err)
			if err.find("No such process") > 0:
				if os.path.exists(self.pidfile):
					os.remove(self.pidfile)
			else:
				print str(err)
				sys.exit(1)
 
	def restart(self):
		"""
		Restart the daemon
		"""
		self.stop()
		self.start()
 
	def run(self):
		"""
		You should override this method when you subclass Daemon. It will be called after the process has been
		daemonized by start() or restart().
		"""
