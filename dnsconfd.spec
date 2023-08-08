Name:           dnsconfd                                                   
Version:        0.0.1
Release:        1%{?dist}
Summary:        local DNS cache configuration daemon
License:        MIT
Source0:        %{name}-%{version}.tar.gz
Source1:        com.redhat.dnsconfd.conf
Source2:        dnsconfd.service

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-setuptools
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  systemd

Requires: unbound

%?python_enable_dependency_generator                                            

%description
Dnsconfd configures local DNS cache services.

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build                                                                      

%install
%py3_install
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/dbus-1/system.d/
mkdir   -m 0755 -p %{buildroot}%{_unitdir}
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/sysconfig
mkdir   -m 0755 -p %{buildroot}%{_sbindir}
mkdir   -m 0755 -p %{buildroot}/var/log/dnsconfd

install -m 0644 -p %{SOURCE1} %{buildroot}%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
install -m 0644 -p %{SOURCE2} %{buildroot}%{_unitdir}/dnsconfd.service

echo "DBUS_NAME=com.redhat.dnsconfd" > %{buildroot}%{_sysconfdir}/sysconfig/dnsconfd
touch %{buildroot}/var/log/dnsconfd/unbound.log

mv %{buildroot}%{_bindir}/dnsconfd %{buildroot}%{_sbindir}/dnsconfd

%post
%systemd_post dnsconfd.service

%postun
%systemd_postun dnsconfd.service

%files
%{_sbindir}/dnsconfd
%{python3_sitelib}/dnsconfd/
%{python3_sitelib}/dnsconfd-%{version}*
%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
%config(noreplace) %{_sysconfdir}/sysconfig/dnsconfd
%{_unitdir}/dnsconfd.service
/var/log/dnsconfd

%changelog
* Tue Aug 01 2023 Tomas Korbar <tkorbar@redhat.com> - 0.0.1-1
- Initial version of the package
