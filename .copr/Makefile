outdir?=.
root=$(shell git rev-parse --show-toplevel)
srpm:
	rpm -q packit || dnf install -y packit
	cd $(root) && packit srpm --output=$(outdir)
