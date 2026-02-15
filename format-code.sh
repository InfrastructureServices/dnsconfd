#!/bin/bash
find . -name "*.[ch]" -exec clang-format -style=file -i {} +
