outdir?=.
root=$(shell git rev-parse --show-toplevel)
srpm:
	rpm -q git-core packit || dnf install -y git-core packit
	if test -n "$(root)"; then cd $(root); fi && pwd && packit srpm --output=$(outdir)
