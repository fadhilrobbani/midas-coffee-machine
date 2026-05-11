#!/bin/bash
set -e

echo "🧹 Membersihkan direktori build lama..."
rm -rf build
mkdir build
cd build

echo "⚙️  Menjalankan CMake..."
# Menggunakan Ninja untuk kompilasi yang jauh lebih cepat (opsional: hilangkan -G Ninja jika ingin menggunakan Make murni)
cmake -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ..

echo "🔨 Membangun project..."
# Jika Anda mengubahnya jadi Make, ganti 'ninja' di bawah ini dengan 'make -j$(nproc)'
ninja -j$(nproc)

echo "🚀 Menjalankan aplikasi..."
# (Opsional) Mengaktifkan font custom jika ada
# export FONTCONFIG_FILE=../config/fonts.conf

./fusion_app --camera 0
