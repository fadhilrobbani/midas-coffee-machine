# ═══════════════════════════════════════════════════════════════════════
# CMake Toolchain File for Renesas RZ/V2H (Kakip) Cross-Compilation
# ═══════════════════════════════════════════════════════════════════════
#
# Usage:
#   cmake .. -DTARGET_PLATFORM=RZV2H \
#            -DCMAKE_TOOLCHAIN_FILE=../toolchain_rzv2h.cmake
#
# Prerequisites:
#   - Renesas RZ/V2H Yocto SDK must be installed
#   - Source the SDK environment before running cmake:
#     source /opt/poky/3.1.x/environment-setup-aarch64-poky-linux
#
# ═══════════════════════════════════════════════════════════════════════

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# ── SDK root path (adjust to your installation) ─────────────────────────
# Typical Renesas RZ/V2H Yocto SDK install path:
set(SDK_ROOT "/opt/poky/3.1.31" CACHE PATH "Renesas Yocto SDK root")
set(SDK_SYSROOT "${SDK_ROOT}/sysroots/aarch64-poky-linux")
set(SDK_TOOLCHAIN "${SDK_ROOT}/sysroots/x86_64-pokysdk-linux/usr/bin/aarch64-poky-linux")

# ── Compilers ────────────────────────────────────────────────────────────
set(CMAKE_C_COMPILER   "${SDK_TOOLCHAIN}/aarch64-poky-linux-gcc")
set(CMAKE_CXX_COMPILER "${SDK_TOOLCHAIN}/aarch64-poky-linux-g++")

# ── Sysroot ──────────────────────────────────────────────────────────────
set(CMAKE_SYSROOT ${SDK_SYSROOT})
set(CMAKE_FIND_ROOT_PATH ${SDK_SYSROOT})

# ── Search behavior ─────────────────────────────────────────────────────
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# ── Compiler flags ───────────────────────────────────────────────────────
set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}   --sysroot=${SDK_SYSROOT}")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --sysroot=${SDK_SYSROOT}")
