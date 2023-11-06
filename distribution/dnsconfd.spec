# NOTE: sysusers installation disabled until NetworkManager problems are resolved

%global modulename dnsconfd
%global selinuxtype targeted

Name:           dnsconfd                                                   
Version:        0.0.1
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
Requires:  unbound
Requires:  python3-gobject

#Conflicts: systemd-resolved

%?python_enable_dependency_generator                                            

# SELinux subpackage
%package selinux
Summary:             dnsconfd SELinux policy
BuildArch:           noarch
Requires:            selinux-policy-%{selinuxtype}
Requires(post):      selinux-policy-%{selinuxtype}
BuildRequires:       selinux-policy-devel
%{?selinux_requires}

%description selinux
Dnsconfd SELinux policy module.

%description
Dnsconfd configures local DNS cache services.

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
mkdir   -m 0755 -p %{buildroot}%{_unitdir}
mkdir   -m 0755 -p %{buildroot}%{_sysconfdir}/sysconfig
mkdir   -m 0755 -p %{buildroot}%{_sbindir}
mkdir   -m 0755 -p %{buildroot}/var/log/dnsconfd
mkdir   -m 0755 -p %{buildroot}/%{_mandir}/man8

install -m 0644 -p %{SOURCE1} %{buildroot}%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
install -m 0644 -p %{SOURCE2} %{buildroot}%{_unitdir}/dnsconfd.service

echo "DBUS_NAME=org.freedesktop.resolve1" > %{buildroot}%{_sysconfdir}/sysconfig/dnsconfd
touch %{buildroot}/var/log/dnsconfd/unbound.log

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
systemctl enable dnsconfd.service &>/dev/null

%postun
%systemd_postun dnsconfd.service

%files
%license LICENSE
%{_sbindir}/dnsconfd
%{python3_sitelib}/dnsconfd/
%{python3_sitelib}/dnsconfd-%{version}*
%{_sysconfdir}/dbus-1/system.d/com.redhat.dnsconfd.conf
%config(noreplace) %{_sysconfdir}/sysconfig/dnsconfd
%{_unitdir}/dnsconfd.service
%attr(0755,root,root) /var/log/dnsconfd
%{_mandir}/man8/dnsconfd.8*
%ghost %{_sysusersdir}/dnsconfd.conf

%files selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.*
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{modulename}

%changelog
* Tue Aug 01 2023 Tomas Korbar <tkorbar@redhat.com> - 0.0.1-1
- Initial version of the package
