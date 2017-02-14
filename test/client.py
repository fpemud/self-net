from gi.repository import GLib
from gi.repository import Gio

def on_connect(client, con, x):
    print "on_connect, %s, %s" % (client.__class__, con.__class, x.__class__)
    con.get_output_stream().write("abcdefg")

sc = Gio.SocketClient()
sc.connect_to_host_async("127.0.0.1", 2107)

GLib.MainLoop().run()
