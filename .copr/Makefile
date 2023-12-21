outdir?=.
srpm:
	rpm -q git-core packit || dnf install -y git-core packit
	packit srpm --output=$(outdir)
