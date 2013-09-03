PACKAGE_VERSION = `/bin/fgrep GK_V= genkernel | sed "s/.*GK_V='\([^']\+\)'/\1/"`
distdir = virt-service-$(PACKAGE_VERSION)
prefix=/usr

all:

clean:
	find . -name *.pyc | xargs rm -f

check-git-repository:
	git diff --quiet || { echo 'STOP, you have uncommitted changes in the working directory' ; false ; }
	git diff --cached --quiet || { echo 'STOP, you have uncommitted changes in the index' ; false ; }

dist: check-git-repository distclean
	mkdir "$(distdir)"
	git ls-files -z | xargs -0 cp --no-dereference --parents --target-directory="$(distdir)" 
	tar cf "$(distdir)".tar "$(distdir)"
	bzip2 -9v "$(distdir)".tar
	rm -Rf "$(distdir)"

distclean:
	rm -Rf "$(distdir)" "$(distdir)".tar "$(distdir)".tar.bz2

install:
	install -d -m 0755 "$(DESTDIR)/$(prefix)/share/dbus-1/system-services"
	install -m 0644 data/org.fpemud.VirtService.service "$(DESTDIR)/$(prefix)/share/dbus-1/system-services"

	install -d -m 0755 "$(DESTDIR)/etc/dbus-1/system.d"
	install -m 0644 data/org.fpemud.VirtService.conf "$(DESTDIR)/etc/dbus-1/system.d"

	install -d -m 0755 "$(DESTDIR)/$(prefix)/libexec/virt-service"
	cp -r src/* "$(DESTDIR)/$(prefix)/libexec/virt-service"
	find "$(DESTDIR)/$(prefix)/libexec/virt-service" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/libexec/virt-service" -type d | xargs chmod 755

#	install -d -m 0755 "$(DESTDIR)/etc/xdg/menus"
#	cp desktop/*.menu "$(DESTDIR)/etc/xdg/menus"
#	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib/desktop-directories"
#	cp desktop/*.directory "$(DESTDIR)/$(prefix)/lib/desktop-directories"

uninstall:
	rm -Rf "$(DESTDIR)/etc/dbus-1/system.d/org.fpemud.VirtService.conf"
	rm -Rf "$(DESTDIR)/$(prefix)/share/dbus-1/system-services/org.fpemud.VirtService.service"
	rm -Rf "$(DESTDIR)/$(prefix)/libexec/virt-service"

.PHONY: check-git-repository all clean dist distclean install uninstall

