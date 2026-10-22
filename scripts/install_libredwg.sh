#!/usr/bin/env bash
# GNU LibreDWG 의 dwg2dxf 를 sudo 없이 소스에서 빌드해 설치한다 (Linux).
#
#   scripts/install_libredwg.sh                  # ~/.local 에 설치 -> ~/.local/bin/dwg2dxf
#   scripts/install_libredwg.sh --prefix <폴더>   # <폴더>/bin/dwg2dxf
#
# Ubuntu 22.04·24.04 apt 에는 libredwg 가 없다. 버전은 동료 툴킷의 Windows dwg2dxf.exe 와
# 같은 0.14 다 (툴킷이 만든 DXF 첫 줄이 "999 / LibreDWG 0.14").
# Windows 는 빌드하지 않는다. 툴킷의 tools/dwg2png/libredwg/dwg2dxf.exe 를 쓰거나
# https://github.com/LibreDWG/libredwg/releases/tag/0.14 의 libredwg-0.14-win64.zip 을 풀어 PATH 에 둔다.
set -euo pipefail

VERSION=0.14
# ftp.gnu.org 와 mirrors.kernel.org 에서 받은 파일이 같고, GNU 서명(reini.urban@gmail.com)이 맞는 것을 확인한 값
SHA256=62ebb73b984f865960f20ed26619ea5f8789d5e3fd088fa40a2598384da81275
URL="https://ftp.gnu.org/gnu/libredwg/libredwg-$VERSION.tar.xz"

PREFIX="$HOME/.local"
if [[ "${1:-}" == "--prefix" ]]; then
    PREFIX="$2"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL -o "$work/libredwg.tar.xz" "$URL"
echo "$SHA256  $work/libredwg.tar.xz" | sha256sum -c -
tar -xf "$work/libredwg.tar.xz" -C "$work"

cd "$work/libredwg-$VERSION"
# 정적 링크: LD_LIBRARY_PATH 없이 dwg2dxf 하나로 돈다. SWIG 바인딩·문서는 쓰지 않는다
./configure --prefix="$PREFIX" --disable-shared --disable-bindings --disable-docs \
    --disable-werror >"$work/configure.log"
make -j"$(nproc)" >"$work/make.log"
make install >"$work/install.log"

"$PREFIX/bin/dwg2dxf" --version
if [[ "$(command -v dwg2dxf)" != "$PREFIX/bin/dwg2dxf" ]]; then
    echo "주의: $PREFIX/bin 이 PATH 에 없거나 다른 dwg2dxf 가 먼저 잡힌다" >&2
fi
