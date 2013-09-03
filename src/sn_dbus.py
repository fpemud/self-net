#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
from sn_util import VirtUtil

################################################################################
# DBus API Docs
################################################################################
#
# ==== Main Application ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet
# Object path           /
#
# Methods:
# array<peerId:int> GetPeerList()
#
# Signals:
#
# ==== Network ====
# Service               org.fpemud.SelfNet
# Interface             org.fpemud.SelfNet.Peer
# Object path           /Peer/{peerId:int}
#
# Methods:
# peerInfo:st       GetPeerInfo()
# bool              IsActive()
# 
# Signals:
#

class SelfNetException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.SelfNet.Exception'

class DbusMainObject(dbus.service.Object):

	def __init__(self, param):
		self.param = param
		self.netObjList = []
		self.dhcpServer = VirtDhcpServer(self.param)
		self.sambaServer = VirtSambaServer(self.param)

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')

	def release(self):
		assert len(self.netObjList) == 0

		self.remove_from_connection()
		self.sambaServer.release()
		self.dhcpServer.release()

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', 
	                     in_signature='s', out_signature='i')
	def NewNetwork(self, networkType, sender=None):
		# get user id
		uid = VirtUtil.dbusGetUserId(self.connection, sender)

		# find existing network object
		for no in self.netObjList:
			if no.uid == uid and no.networkType == networkType:
				no.refCount = no.refCount + 1
				return no.nid

		# allocate network id, range is [1, 6]
		nid = 1
		while True:
			found = False
			for no in self.netObjList:
				if no.uid == uid and no.nid == nid:
					found = True
			if not found:
				break
			if nid >= 6:
				raise Exception("network number limit is reached")
			nid = nid + 1
			continue

		# create new network object
		netObj = DbusNetworkObject(self.param, uid, nid, networkType, self.dhcpServer, self.sambaServer)
		netObj.refCount = 1												# fixme: strange, maintain refcount out side the object
		self.netObjList.append(netObj)

		# open ipv4 forwarding, now no other program needs it, so we do a simple implementation
		VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "1")

		return nid

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='i')
	def DeleteNetwork(self, nid, sender=None):
		# get user id
		uid = VirtUtil.dbusGetUserId(self.connection, sender)

		try:
			# find and delete network object
			found = False
			for i in range(0, len(self.netObjList)):
				if self.netObjList[i].uid == uid and self.netObjList[i].nid == nid:
					self.netObjList[i].refCount -= 1
					if self.netObjList[i].refCount == 0:
						no = self.netObjList.pop(i)
						no.release()
					found = True
					break
			if not found:
				raise Exception("the specified network does not exist")
		finally:
			# service exits when the last network is deleted
			if len(self.netObjList) == 0:
				VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")
#				self.param.mainloop.quit()

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='s', out_signature='s')
	def NewVfioDevicePci(self, devName, sender=None):
		uid = VirtUtil.dbusGetUserId(self.connection, sender)
		return self.param.vfioDevManager.newVfioDeviceVga(uid, devName)

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='s')
	def DeleteVfioDevice(self, devPath, sender=None):
		uid = VirtUtil.dbusGetUserId(self.connection, sender)
		self.param.vfioDevManager.releaseVfioDevice(uid, devPath)

class DbusNetworkObject(dbus.service.Object):

	def __init__(self, param, uid, nid, networkType, dhcpServer, sambaServer):
		self.param = param
		self.uid = uid
		self.nid = nid
		self.networkType = networkType
		self.gDhcpServer = dhcpServer
		self.gSambaServer = sambaServer

		# create network temp directory
		os.makedirs(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

		# create network object
		if self.networkType == "bridge":
			self.netObj = VirtNetworkBridge(self.param, self.uid, self.nid)
		elif self.networkType == "nat":
			self.netObj = VirtNetworkNat(self.param, self.uid, self.nid)
		elif self.networkType == "route":
			self.netObj = VirtNetworkRoute(self.param, self.uid, self.nid)
		elif self.networkType == "isolate":
			self.netObj = VirtNetworkIsolate(self.param, self.uid, self.nid)
		else:
			raise Exception("invalid networkType %s"%(networkType))

		# enable server
		if self.networkType in ["nat", "route"]:
			self.gDhcpServer.addNetwork(self.uid, self.nid, self.netObj.brname, self.netObj.brip, self.netObj.netip, self.netObj.netmask)
			self.gSambaServer.addNetwork(self.uid, self.nid, self.netObj.brname)

		# register host network callback
		if self.networkType in ["bridge", "nat", "route"]:
			self.param.hostNetwork.registerEventCallback(self.netObj)

		# create data structure
		self.vmIdDict = dict()		# vmName -> vmId

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d'%(self.uid, self.nid))

	def release(self):
		assert len(self.vmIdDict) == 0

		# deregister dbus object path
		self.remove_from_connection()

		# deregister host network callback
		if self.networkType in ["bridge", "nat", "route"]:
			self.param.hostNetwork.unregisterEventCallback(self.netObj)

		# disable server
		if self.networkType in ["nat", "route"]:
			self.gSambaServer.removeNetwork(self.uid, self.nid)
			self.gDhcpServer.removeNetwork(self.uid, self.nid)

		# release network object
		self.netObj.release()

		# delete network temp directory
		shutil.rmtree(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='s', out_signature='i')
	def AddVm(self, vmName, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmName in self.vmIdDict:
			raise Exception("virt-machine already exists")

		# allocate vmId, range is [0, 31]
		vmId = 0
		while True:
			if vmId not in self.vmIdDict.values():
				break
			if vmId >= 31:
				raise Exception("virtual machine number limit is reached")
			vmId = vmId + 1
			continue

		# add virtual machine
		self.netObj.addVm(vmId)
		self.vmIdDict[vmName] = vmId

		return vmId

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i')
	def DeleteVm(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		self.netObj.removeVm(vmId)

		for k in self.vmIdDict:
			if self.vmIdDict[k] == vmId:
				del self.vmIdDict[k]
				break

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapInterface(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# get tap interface
		return self.netObj.getTapInterface(vmId)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapVmMacAddress(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		return VirtUtil.getVmMacAddress(self.param.macOuiVm, self.uid, self.nid, vmId)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='issb')
	def SambaAddShare(self, vmId, shareName, srcPath, readonly, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		if not srcPath.startswith("/"):
			raise Exception("srcPath must be absoulte path")

		# do job
		return self.gSambaServer.networkAddShare(self.uid, self.nid, vmId, shareName, srcPath, readonly)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='is')
	def SambaDeleteShare(self, vmId, shareName, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# do job
		return self.gSambaServer.networkRemoveShare(self.uid, self.nid, vmId, shareName)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def SambaGetAccount(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# do job
		username, password = self.gSambaServer.networkGetAccountInfo(self.uid, self.nid)
		return "%s:%s"%(username, password)


