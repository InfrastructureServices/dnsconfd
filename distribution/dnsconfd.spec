%global modulename dnsconfd
%global selinuxtype targeted

Name:           dnsconfd
Version:        1.7.3
Release:        1%{?dist}
Summary:        Local DNS cache configuration daemon
License:        MIT
URL:            https://github.com/InfrastructureServices/dnsconfd
Source0:        %{url}/archive/%{version}/%{name}-%{version}.tar.gz
Source1:        dnsconfd.sysusers

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-setuptools
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  systemd
BuildRequires:  systemd-rpm-macros
%if %{defined fedora} && 0%{?fedora} < 42 || %{defined rhel} && 0%{?rhel} < 11
%{?sysusers_requires_compat}
%endif

Requires:  (%{name}-selinux if selinux-policy-%{selinuxtype})
Requires:  python3-gobject-base
Requires:  python3-pyyaml
Requires:  python3-systemd
Recommends: python3-idna
Requires:  dbus-common
Requires:  %{name}-cache
Requires:  polkit
Suggests:  %{name}-unbound
Requires:  (%{name}-unbound = %{version}-%{release} if %{name}-unbound)

%?python_enable_dependency_generator

%description
Dnsconfd configures local DNS cache services.

# SELinux subpackage
%package selinux
Summary:             dnsconfd SELinux policy
BuildArch:           noarch
Requires:            %{name} = %{version}-%{release}
Requires:            selinux-policy-%{selinuxtype}
Requires(post):      selinux-policy-%{selinuxtype}
BuildRequires:       selinux-policy-devel
%{?selinux_requires}

%description selinux
Dnsconfd SELinux policy module.

%package micro
Summary:  Minimized native implementation of Dnsconfd
Requires:  %{name} = %{version}-%{release}
Requires:  (%{name}-selinux if selinux-policy-%{selinuxtype})
Suggests:  %{name}-unbound = %{version}-%{release}
BuildRequires: pkgconfig(glib-2.0)
BuildRequires: pkgconfig(gio-2.0)
BuildRequires: pkgconfig(libcurl)
BuildRequires: pkgconfig(check)
BuildRequires: pkgconfig(libsystemd)
BuildRequires: gcc
BuildRequires: cmake
Requires: glib2
Requires: libcurl
Requires: systemd-libs
Requires: unbound-dracut

%description micro
Minimized native implementation of Dnsconfd. Able to configure
Unbound according to NetworkManager global configuration.

%package unbound
Summary:             dnsconfd unbound module
BuildArch:           noarch
Requires:            %{name} = %{version}-%{release}
Requires:            unbound
Provides:            %{name}-cache = %{version}-%{release}

%description unbound
Dnsconfd management of unbound server

%package dracut
Summary:            dnsconfd dracut module
Requires:           %{name}-micro%{?_isa} = %{version}-%{release}
Requires:           unbound
Requires:           dracut
Requires:           dracut-network

%description dracut
Dnsconfd dracut module

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

%if %{defined fedora} && 0%{?fedora} < 40 || %{defined rhel} && 0%{?rhel} < 10
    echo '/var/run/dnsconfd(/.*)? gen_context(system_u:object_r:dnsconfd_var_run_t,s0)' >> distribution/dnsconfd.fc
%endif

make -f %{_datadir}/selinux/devel/Makefile %{modulename}.pp
bzip2 -9 %{modulename}.pp

### micro part

pushd micro-dnsconfd
%cmake
%cmake_build
popd

%install
%py3_install
mkdir   -m 0755 -p %{buildroot}%{_datadir}/dbus-1/system.d/
mkdir   -m 0755 -p %{buildroot}%{_datadir}/dbus-1/system-services/
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/unbound/conf.d/
mkdir   -m 0755 -p %{buildroot}%{_unitdir}
mkdir   -m 0755 -p %{buildroot}%{_unitdir}/unbound.service.d
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/sysconfig
mkdir   -m 0755 -p %{buildroot}/%{_mandir}/man8
mkdir   -m 0755 -p %{buildroot}/%{_mandir}/man5
mkdir   -m 0755 -p %{buildroot}%{_datadir}/polkit-1/rules.d/
mkdir   -m 0755 -p %{buildroot}%{_rundir}/dnsconfd
mkdir   -m 0755 -p %{buildroot}%{_tmpfilesdir}
mkdir   -m 0755 -p %{buildroot}%{_prefix}/lib/dracut/modules.d/99dnsconfd
mkdir   -m 0755 -p %{buildroot}%{_libexecdir}

install -m 0644 -p distribution/com.redhat.dnsconfd.conf %{buildroot}%{_datadir}/dbus-1/system.d/com.redhat.dnsconfd.conf
install -m 0644 -p distribution/com.redhat.dnsconfd.service %{buildroot}%{_datadir}/dbus-1/system-services/com.redhat.dnsconfd.service
install -m 0644 -p distribution/dnsconfd.sysconfig %{buildroot}%{_sysconfdir}/sysconfig/dnsconfd
install -m 0644 -p distribution/micro-dnsconfd.sysconfig %{buildroot}%{_sysconfdir}/sysconfig/micro-dnsconfd
install -m 0644 -p distribution/dnsconfd.service %{buildroot}%{_unitdir}/dnsconfd.service
install -m 0644 -p distribution/micro-dnsconfd.service %{buildroot}%{_unitdir}/micro-dnsconfd.service
install -m 0644 -p distribution/dnsconfd.conf %{buildroot}%{_sysconfdir}/dnsconfd.conf
install -m 0644 -p distribution/dnsconfd.rules %{buildroot}%{_datadir}/polkit-1/rules.d/dnsconfd.rules
install -m 0644 -p distribution/dnsconfd-tmpfiles.conf %{buildroot}%{_tmpfilesdir}/%{name}.conf
install -m 0644 -p distribution/dnsconfd-unbound-tmpfiles.conf %{buildroot}%{_tmpfilesdir}/%{name}-unbound.conf
install -m 0755 -p distribution/dracut_module/module-setup.sh %{buildroot}%{_prefix}/lib/dracut/modules.d/99dnsconfd
install -m 0755 -p distribution/dnsconfd-prepare.sh %{buildroot}%{_libexecdir}/dnsconfd-prepare
install -m 0755 -p distribution/dnsconfd-prepare.sh %{buildroot}%{_libexecdir}/dnsconfd-cleanup
install -m 0644 -p distribution/dracut_module/*.conf %{buildroot}%{_prefix}/lib/dracut/modules.d/99dnsconfd

touch %{buildroot}%{_rundir}/dnsconfd/unbound.conf
chmod 0644 %{buildroot}%{_rundir}/dnsconfd/unbound.conf

# hook to inform us about unbound stop
install -m 0644 -p distribution/dnsconfd.service.d-unbound.conf %{buildroot}%{_unitdir}/unbound.service.d/dnsconfd.conf

install -m 0644 -p distribution/unbound-dnsconfd.conf %{buildroot}%{_sysconfdir}/unbound/conf.d/unbound.conf

install -D -m 0644 %{modulename}.pp.bz2 %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2

install -m 0644 -p distribution/dnsconfd.8 %{buildroot}/%{_mandir}/man8/dnsconfd.8
install -m 0644 -p distribution/dnsconfd-config.8 %{buildroot}/%{_mandir}/man8/dnsconfd-config.8
install -m 0644 -p distribution/dnsconfd-reload.8 %{buildroot}/%{_mandir}/man8/dnsconfd-reload.8
install -m 0644 -p distribution/dnsconfd-status.8 %{buildroot}/%{_mandir}/man8/dnsconfd-status.8
install -m 0644 -p distribution/dnsconfd.conf.5 %{buildroot}/%{_mandir}/man5/dnsconfd.conf.5

install -p -D -m 0644 distribution/dnsconfd.sysusers %{buildroot}%{_sysusersdir}/dnsconfd.conf

### micro part

pushd micro-dnsconfd
%cmake_install
popd

%check
pushd micro-dnsconfd
%ctest
popd

%pre selinux
%selinux_relabel_pre -s %{selinuxtype}

%post selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2

%postun selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall -s %{selinuxtype} -p 200 %{modulename}
fi

%posttrans selinux
%selinux_relabel_post -s %{selinuxtype}

%if %{defined fedora} && 0%{?fedora} < 42 || %{defined rhel} && 0%{?rhel} < 11
%pre
%sysusers_create_compat %{SOURCE1}

%pre unbound
%sysusers_create_compat %{SOURCE1}
%endif

%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE
%{_bindir}/dnsconfd
%{python3_sitelib}/dnsconfd/
%{python3_sitelib}/dnsconfd-%{version}*
%{_datadir}/dbus-1/system.d/com.redhat.dnsconfd.conf
%{_datadir}/dbus-1/system-services/com.redhat.dnsconfd.service
%config(noreplace) %{_sysconfdir}/sysconfig/dnsconfd
%config(noreplace) %{_sysconfdir}/dnsconfd.conf
%{_unitdir}/dnsconfd.service
%{_libexecdir}/dnsconfd-prepare
%{_libexecdir}/dnsconfd-cleanup
%{_mandir}/man8/dnsconfd*.8*
%{_mandir}/man5/dnsconfd.conf.5*
%{_sysusersdir}/dnsconfd.conf
%doc README.md docs/com.redhat.dnsconfd.md
%{_datadir}/polkit-1/rules.d/dnsconfd.rules
%dir %attr(755,dnsconfd,dnsconfd) %{_rundir}/dnsconfd
%{_tmpfilesdir}/%{name}.conf

%files micro
%{_bindir}/micro-dnsconfd
%{_unitdir}/micro-dnsconfd.service
%config(noreplace) %{_sysconfdir}/sysconfig/micro-dnsconfd

%files selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.*
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{modulename}

%files unbound
%{_unitdir}/unbound.service.d/dnsconfd.conf
%config(noreplace) %attr(644,unbound,unbound) %{_sysconfdir}/unbound/conf.d/unbound.conf
%attr(664,dnsconfd,dnsconfd) %{_rundir}/dnsconfd/unbound.conf
%{_sysusersdir}/dnsconfd.conf
%{_tmpfilesdir}/dnsconfd-unbound.conf

%files dracut
%{_prefix}/lib/dracut/modules.d/99dnsconfd

%changelog
* Wed Apr 09 2025 Tomas Korbar <tkorbar@redhat.com> - 1.7.3-1
- Release 1.7.3

* Thu Feb 19 2025 Tomas Korbar <tkorbar@redhat.com> - 1.7.2-1
- Release 1.7.2

* Thu Feb 13 2025 Tomas Korbar <tkorbar@redhat.com> - 1.7.1-1
- Release 1.7.1

* Sun Jan 18 2025 Tomas Korbar <tkorbar@redhat.com> - 1.7.0-1
- Release 1.7.0

* Mon Nov 18 2024 Tomas Korbar <tkorbar@redhat.com> - 1.6.0-1
- Release 1.6.0

* Wed Oct 16 2024 Tomas Korbar <tkorbar@redhat.com> - 1.5.0-1
- Release 1.5.0

* Thu Oct 10 2024 Tomas Korbar <tkorbar@redhat.com> - 1.4.2-1
- Release 1.4.2

* Sat Sep 28 2024 Tomas Korbar <tkorbar@redhat.com> - 1.4.0-1
- Release 1.4.0

* Mon Sep 10 2024 Tomas Korbar <tkorbar@redhat.com> - 1.3.1-1
- Release 1.3.1

* Mon Sep 09 2024 Tomas Korbar <tkorbar@redhat.com> - 1.3.0-1
- Release 1.3.0

* Thu Aug 15 2024 Tomas Korbar <tkorbar@redhat.com> - 1.2.0-1
- Release 1.2.0

* Mon Jul 22 2024 Tomas Korbar <tkorbar@redhat.com> - 1.1.2-1
- Release 1.1.2

* Thu Jun 27 2024 Tomas Korbar <tkorbar@redhat.com> - 1.0.2-1
- Release 1.0.2

* Wed Jun 26 2024 Tomas Korbar <tkorbar@redhat.com> - 1.0.1-1
- Release 1.0.1

* Mon May 27 2024 Tomas Korbar <tkorbar@redhat.com> - 1.0.0-1
- Release 1.0.0

* Fri May 17 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.6-1
- Release 0.0.6

* Fri May 03 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.5-1
- Release 0.0.5

* Mon Apr 29 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.4-1
- Release 0.0.4

* Wed Jan 31 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.3-1
- Release 0.0.3

* Wed Jan 24 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.2-1
- Release 0.0.2

* Tue Aug 01 2023 Tomas Korbar <tkorbar@redhat.com> - 0.0.1-1
- Initial version of the package
