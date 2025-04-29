#!/bin/bash

set -e

/usr/sbin/named -u named -g -c "$@"
