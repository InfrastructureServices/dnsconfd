Name:           dnsconfd                                                   
Version:        0.0.1
Release:        37%{?dist}
Summary:        local DNS cache configuration daemon
License:        MIT
Source0:        %{name}-%{version}.tar.gz
Source1:        com.redhat.dnsconfd.conf
Source2:        dnsconfd.service
Source3:        dnsconfd.sysusers

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-setuptools
BuildRequires:  python3-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  systemd
BuildRequires:  systemd-rpm-macros
%{?sysusers_requires_compat}

Requires: unbound
Requires: python3-gobject
Conflicts: systemd-resolved

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

echo "DBUS_NAME=org.freedesktop.resolve1" > %{buildroot}%{_sysconfdir}/sysconfig/dnsconfd
touch %{buildroot}/var/log/dnsconfd/unbound.log

mv %{buildroot}%{_bindir}/dnsconfd %{buildroot}%{_sbindir}/dnsconfd

install -p -D -m 0644 %{SOURCE3} %{buildroot}%{_sysusersdir}/dnsconfd.conf

%pre
%sysusers_create_compat %{SOURCE3}
# This is neccessary because of NetworkManager.
# It checks whether /etc/resolv.conf is a link and in case, it is not
# it overwrites it, thus overwrites our configuration.
# The test of mountpoint ensures that we wont try to overwrite resolv.conf
# in container
if ! mountpoint /etc/resolv.conf &> /dev/null; then
    rm -f /etc/resolv.conf
    ln -s /usr/lib/systemd/resolv.conf /etc/resolv.conf
fi

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
%attr(0755,dnsconfd,dnsconfd) /var/log/dnsconfd
%{_sysusersdir}/dnsconfd.conf

%changelog
* Tue Aug 01 2023 Tomas Korbar <tkorbar@redhat.com> - 0.0.1-1
- Initial version of the package
