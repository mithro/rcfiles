#!/bin/bash
#
# Author: mithro@mithis.com (Tim 'mithro' Ansell)

# $1 - boost1.38_1.38.0-3.dsc  - dsc file
# $2 - 0                       - PPA version
# $3 - hardy                   - Distro to upload for

if [ ! -f $1 ]; then
  echo "Could not find $1"
  exit
fi

export PACKAGE=`echo $1 | sed -e's/_.*//'`
export VERSION=`echo $1 | sed -e's/.*_//' -e's/.dsc//'`
export PPA_VERSION=$2
export DISTRO=$3
export UPSTREAM_VERSION=`echo $VERSION | sed -e's/-.*//'`
export DEBIAN_VERSION=`echo $VERSION | sed -e's/.*-//'`
export OUR_VERSION="$VERSION~$DISTRO$PPA_VERSION"
export SOURCE_DIR="$PACKAGE-$UPSTREAM_VERSION"

echo "Package: $PACKAGE"
echo "Version: $VERSION"
echo "PPA Version: $PPA_VERSION"
echo "Upstream Version: $UPSTREAM_VERSION"
echo "Debian Verison: $DEBIAN_VERSION"
echo "Source Dir: $SOURCE_DIR"

rm -rf $DISTRO

mkdir $DISTRO
cd $DISTRO

# Extract the "general package"
dpkg-source -x ../${PACKAGE}_${VERSION}.dsc

cd $SOURCE_DIR

# Add our custom changelog.
cat > ./debian/changelog <<EOF
$PACKAGE ($OUR_VERSION) $DISTRO; urgency=low

  * PPA push.

 -- Tim 'mithro' Ansell <mithro@mithis.com>  Sat, 04 Apr 2009 00:41:36 -0500
EOF

/usr/bin/debuild -S -sa
cd ..
dput my-ppa ${PACKAGE}_${OUR_VERSION}_source.changes
