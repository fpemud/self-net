
import socket  
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop


def onServerSocketEvent(source, cb_condition):
	print "onServerSocketEvent %s,%d"%(source, cb_condition)

	if cb_condition & GLib.IO_IN:
		ss, addr = s.accept()  
		print 'got connected from', addr  
		GLib.io_add_watch(ss, GLib.IO_IN | GLib.IO_OUT | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, onSocketEvent)


def onSocketEvent(source, cb_condition):
	print "onSocketEvent %s,%d"%(source, cb_condition)

	if cb_condition & GLib.IO_OUT:
		source.send('byebye')  
		return

	if cb_condition & GLib.IO_IN:
		ra = source.recv(512)  
		print ra  
		source.close()  
		return



print "%d"%(GLib.IO_IN)
print "%d"%(GLib.IO_PRI)
print "%d"%(GLib.IO_OUT)
print "%d"%(GLib.IO_ERR)

# create main loop
DBusGMainLoop(set_as_default=True)
mainloop = GLib.MainLoop()
  
address = ('127.0.0.1', 31500)  
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(address)  
s.listen(5)  

GLib.io_add_watch(s, GLib.IO_IN | GLib.IO_OUT | GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP, onServerSocketEvent)

# start main loop
mainloop.run()
s.close()


