#!/bin/bash
set -e

# Clean up old build artifacts
rm -rf package
rm -f ../handler.zip

# Create package directory
mkdir -p package

# Install dependencies to package directory (target Lambda platform)
pip3 install -r requirements.txt -t package/ --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

# Copy Lambda code to package directory
cp handler.py package/
cp -r events package/
cp -r services package/
cp -r utils package/

# Create zip file in parent directory
cd package
zip -r ../../handler.zip .
cd ..

# Clean up
rm -rf package

echo "Lambda package created: ../handler.zip"
