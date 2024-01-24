# NOTE: sysusers installation disabled until NetworkManager problems are resolved

%global modulename dnsconfd
%global selinuxtype targeted

Name:           dnsconfd                                                   
Version:        0.0.2
Release:        1%{?dist}
Summary:        local DNS cache configuration daemon
License:        MIT
URL:            https://github.com/InfrastructureServices/dnsconfd
Source0:        %{url}/archive/%{version}/%{name}-%{version}.tar.gz
Source1:        com.redhat.dnsconfd.conf
Source2:        dnsconfd.service
#Source3:        dnsconfd.sysusers
Source4:        dnsconfd.fc
Source5:        dnsconfd.te
Source6:        LICENSE
Source7:        dnsconfd.8
Source8:        dnsconfd.sysconfig
Source9:        dnsconfd.service.d-unbound.conf
Source10:       unbound-dnsconfd.conf

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-setuptools
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  systemd
BuildRequires:  systemd-rpm-macros
%{?sysusers_requires_compat}

Requires:  (%{name}-selinux if selinux-policy-%{selinuxtype})
Requires:  python3-gobject-base
Requires:  dbus-common
Requires:  %{name}-cache
Suggests:  %{name}-unbound

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

%package unbound
Summary:             dnsconfd unbound module
BuildArch:           noarch
Requires:            %{name} = %{version}-%{release}
Requires:            unbound
Provides:            %{name}-cache = %{version}-%{release}

%description unbound
Dnsconfd management of unbound server

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

mkdir selinux
cp -p %{SOURCE4} selinux/
cp -p %{SOURCE5} selinux/

make -f %{_datadir}/selinux/devel/Makefile %{modulename}.pp
bzip2 -9 %{modulename}.pp

%install
%py3_install
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/dbus-1/system.d/
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/unbound/conf.d/
mkdir   -m 0755 -p %{buildroot}%{_unitdir}
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/sysconfig
mkdir   -m 0755 -p %{buildroot}%{_sbindir}
mkdir   -m 0755 -p %{buildroot}%{_var}/log/dnsconfd
mkdir   -m 0755 -p %{buildroot}/%{_mandir}/man8

install -m 0644 -p %{SOURCE1} %{buildroot}%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
install -m 0644 -p %{SOURCE8} %{buildroot}%{_sysconfdir}/sysconfig/dnsconfd
install -m 0644 -p %{SOURCE2} %{buildroot}%{_unitdir}/dnsconfd.service
#install -m 0644 -p %{SOURCE9} %{buildroot}%{_unitdir}/dnsconfd.service.d/unbound.conf
install -m 0644 -p %{SOURCE10} %{buildroot}%{_sysconfdir}/unbound/conf.d/unbound.conf

touch %{buildroot}%{_var}/log/dnsconfd/unbound.log

mv %{buildroot}%{_bindir}/dnsconfd %{buildroot}%{_sbindir}/dnsconfd

install -D -m 0644 %{modulename}.pp.bz2 %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2

install -m 0644 -p %{SOURCE7} %{buildroot}/%{_mandir}/man8/dnsconfd.8

%dnl install -p -D -m 0644 %{SOURCE3} %{buildroot}%{_sysusersdir}/dnsconfd.conf
install -p -D -m 0644 /dev/null %{buildroot}%{_sysusersdir}/dnsconfd.conf


%pre selinux
%selinux_relabel_pre -s %{selinuxtype}

%post selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2

%postun selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall -s %{selinuxtype} %{modulename}
fi

%posttrans selinux
%selinux_relabel_post -s %{selinuxtype}

%pre
%dnl %sysusers_create_compat %{SOURCE3}

%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE
%{_sbindir}/dnsconfd
%{python3_sitelib}/dnsconfd/
%{python3_sitelib}/dnsconfd-%{version}*
%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
%config(noreplace) %{_sysconfdir}/sysconfig/dnsconfd
%{_unitdir}/dnsconfd.service
#%dir %{_unitdir}/dnsconfd.service.d
%attr(0755,root,root) %{_var}/log/dnsconfd
%{_mandir}/man8/dnsconfd.8*
%ghost %{_sysusersdir}/dnsconfd.conf
%doc README.md

%files selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.*
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{modulename}

%files unbound
#%{_unitdir}/dnsconfd.service.d/unbound.conf
%config(noreplace) %{_sysconfdir}/unbound/conf.d/unbound.conf

%changelog
* Wed Jan 24 2024 Tomas Korbar <tkorbar@redhat.com> - 0.0.2-1
- Release 0.0.2

* Tue Aug 01 2023 Tomas Korbar <tkorbar@redhat.com> - 0.0.1-1
- Initial version of the package
