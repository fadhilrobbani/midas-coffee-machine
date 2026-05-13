cmake_minimum_required(VERSION 3.16)
project(midas_aruco_fusion_cpp
    VERSION 1.0.0
    LANGUAGES CXX
    DESCRIPTION "ArUco + MiDaS + YOLO Cup Height Estimator (C++ Port)"
)

# ── C++17 Standard ──────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Compiler Flags ──────────────────────────────────────────────────────
add_compile_options(-Wall -Wextra -Wpedantic)
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    add_compile_options(-O2 -march=native)
endif()

# ── Dependencies ────────────────────────────────────────────────────────

# OpenCV 4.x (avoid highgui in REQUIRED — it pulls Qt6 which has pcre2 issues)
find_package(OpenCV 4 REQUIRED COMPONENTS
    core imgproc videoio imgcodecs aruco calib3d dnn
)
# highgui is optional (needed for imshow in headless mode)
find_package(OpenCV 4 OPTIONAL_COMPONENTS highgui)

# GTK (gtkmm-3.0) via pkg-config — optional for phased development
find_package(PkgConfig REQUIRED)
pkg_check_modules(GTKMM gtkmm-3.0)
if(GTKMM_FOUND)
    set(HAS_GTKMM ON)
    message(STATUS "gtkmm-3.0: FOUND")
else()
    set(HAS_GTKMM OFF)
    message(WARNING "gtkmm-3.0 not found. GUI will be disabled. Install: sudo pacman -S gtkmm3")
endif()

# yaml-cpp — disabled temporarily due to miniconda path conflict with system pcre2
# Camera calibration YAML will be parsed using OpenCV's FileStorage instead
# find_package(yaml-cpp REQUIRED)

# nlohmann/json (header-only)
find_package(nlohmann_json 3 QUIET)
if(NOT nlohmann_json_FOUND)
    message(STATUS "nlohmann_json not found via find_package. Fetching via CMake...")
    include(FetchContent)
    FetchContent_Declare(
        nlohmann_json
        URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
    )
    FetchContent_MakeAvailable(nlohmann_json)
endif()

# ONNX Runtime — manual find from prebuilt
# Set via: -DONNXRUNTIME_ROOT=/path/to/onnxruntime
if(DEFINED ONNXRUNTIME_ROOT)
    set(ONNXRUNTIME_INCLUDE_DIR "${ONNXRUNTIME_ROOT}/include")
    set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_ROOT}/lib")
    find_library(ONNXRUNTIME_LIB onnxruntime PATHS ${ONNXRUNTIME_LIB_DIR} NO_DEFAULT_PATH)
else()
    # Try system install
    find_library(ONNXRUNTIME_LIB onnxruntime)
    find_path(ONNXRUNTIME_INCLUDE_DIR onnxruntime_cxx_api.h
        PATH_SUFFIXES onnxruntime onnxruntime/core/session
    )
endif()

if(NOT ONNXRUNTIME_LIB)
    message(WARNING "ONNX Runtime not found. MiDaS and YOLO inference will be disabled.")
    set(HAS_ONNXRUNTIME OFF)
else()
    set(HAS_ONNXRUNTIME ON)
    message(STATUS "ONNX Runtime: ${ONNXRUNTIME_LIB}")
    message(STATUS "ONNX Runtime include: ${ONNXRUNTIME_INCLUDE_DIR}")
endif()

# GoogleTest via FetchContent (for TDD)
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# CLI11 (header-only CLI parser)
FetchContent_Declare(
    cli11
    GIT_REPOSITORY https://github.com/CLIUtils/CLI11.git
    GIT_TAG v2.4.1
)
FetchContent_MakeAvailable(cli11)

set(FUSION_CORE_SOURCES
    src/math/height_math.cpp
    src/math/volume_math.cpp
    src/io/calibration_storage.cpp
    src/io/image_preprocess.cpp
    src/io/session_reporter.cpp
    src/detectors/aruco_detector.cpp
    src/detectors/midas_depth.cpp
    src/detectors/yolo_detector.cpp
    src/calibration/calibration_routines.cpp
    src/fisheye/moil_undistorter.cpp
    src/fisheye/anypoint_controller.cpp
    src/pipeline/async_midas.cpp
    src/pipeline/live_pipeline.cpp
)

# Conditionally add GUI sources
if(HAS_GTKMM)
    list(APPEND FUSION_CORE_SOURCES src/gui/gui_fusion.cpp)
endif()

add_library(fusion_core STATIC ${FUSION_CORE_SOURCES})

target_include_directories(fusion_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/math
    ${CMAKE_CURRENT_SOURCE_DIR}/src/io
    ${CMAKE_CURRENT_SOURCE_DIR}/src/detectors
    ${CMAKE_CURRENT_SOURCE_DIR}/src/calibration
    ${CMAKE_CURRENT_SOURCE_DIR}/src/fisheye
    ${CMAKE_CURRENT_SOURCE_DIR}/src/pipeline
    ${CMAKE_CURRENT_SOURCE_DIR}/src/gui
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(fusion_core PUBLIC
    opencv_core opencv_imgproc opencv_videoio opencv_imgcodecs
    opencv_aruco opencv_calib3d opencv_dnn opencv_objdetect opencv_highgui
    nlohmann_json::nlohmann_json
    pthread
)

# Moildev Library (Static)
set(MOILDEV_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../weights/moil")
find_library(MOILDEV_LIB moildev PATHS ${MOILDEV_DIR} NO_DEFAULT_PATH)
if(MOILDEV_LIB)
    message(STATUS "Moildev Library: ${MOILDEV_LIB}")
    target_link_libraries(fusion_core PUBLIC ${MOILDEV_LIB})
else()
    message(WARNING "Moildev static library not found at ${MOILDEV_DIR}")
endif()

if(HAS_GTKMM)
    target_include_directories(fusion_core PUBLIC ${GTKMM_INCLUDE_DIRS})
    target_link_libraries(fusion_core PUBLIC ${GTKMM_LIBRARIES})
    target_link_directories(fusion_core PUBLIC ${GTKMM_LIBRARY_DIRS})
    target_compile_options(fusion_core PUBLIC ${GTKMM_CFLAGS_OTHER})
    target_compile_definitions(fusion_core PUBLIC HAS_GTKMM=1)
endif()

if(HAS_ONNXRUNTIME)
    target_include_directories(fusion_core PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
    target_link_libraries(fusion_core PUBLIC ${ONNXRUNTIME_LIB})
    target_compile_definitions(fusion_core PUBLIC HAS_ONNXRUNTIME=1)
endif()

# ── Main Executable ────────────────────────────────────────────────────
add_executable(fusion_app src/main.cpp)
target_link_libraries(fusion_app PRIVATE fusion_core CLI11::CLI11)

# ── Standalone Tools ───────────────────────────────────────────────────
add_executable(record_moildev src/tools/record_moildev.cpp)
target_link_libraries(record_moildev PRIVATE fusion_core CLI11::CLI11)

add_executable(calibrate_fisheye src/tools/calibrate_fisheye.cpp)
target_link_libraries(calibrate_fisheye PRIVATE fusion_core CLI11::CLI11)

add_executable(compare_anypoint_modes src/tools/compare_anypoint_modes.cpp)
target_link_libraries(compare_anypoint_modes PRIVATE fusion_core CLI11::CLI11)

# ── Tests (GoogleTest + CTest) ─────────────────────────────────────────
enable_testing()
include(GoogleTest)

# Macro to add a test target cleanly
macro(add_fusion_test TEST_NAME TEST_SRC)
    add_executable(${TEST_NAME} ${TEST_SRC})
    target_link_libraries(${TEST_NAME} PRIVATE fusion_core GTest::gtest_main)
    gtest_discover_tests(${TEST_NAME})
endmacro()

# Phase 1: Pure Math
add_fusion_test(test_height_math     tests/math/test_height_math.cpp)
add_fusion_test(test_volume_math     tests/math/test_volume_math.cpp)

# Phase 2: Data I/O
add_fusion_test(test_calibration_storage  tests/io/test_calibration_storage.cpp)
add_fusion_test(test_image_preprocess     tests/io/test_image_preprocess.cpp)

# Phase 3: Detectors
add_fusion_test(test_aruco_detector  tests/detectors/test_aruco_detector.cpp)
add_fusion_test(test_midas_depth     tests/detectors/test_midas_depth.cpp)
add_fusion_test(test_yolo_detector   tests/detectors/test_yolo_detector.cpp)

# Phase 4-8: Pipeline
add_fusion_test(test_fisheye_pipeline      tests/fisheye/test_fisheye_pipeline.cpp)
if(HAS_GTKMM)
    add_fusion_test(test_gui_fusion        tests/gui/test_gui_fusion.cpp)
endif()
add_fusion_test(test_calibration_routines  tests/calibration/test_calibration_routines.cpp)
add_fusion_test(test_integration_pipeline  tests/pipeline/test_integration_pipeline.cpp)

message(STATUS "")
message(STATUS "╔══════════════════════════════════════════════╗")
message(STATUS "║  MiDaS ArUco Fusion C++ — Build Config      ║")
message(STATUS "╠══════════════════════════════════════════════╣")
message(STATUS "║  C++ Standard  : C++${CMAKE_CXX_STANDARD}                      ║")
message(STATUS "║  Build Type    : ${CMAKE_BUILD_TYPE}                    ║")
message(STATUS "║  OpenCV        : ${OpenCV_VERSION}                      ║")
message(STATUS "║  gtkmm-3.0     : ${HAS_GTKMM}                        ║")
message(STATUS "║  ONNX Runtime  : ${HAS_ONNXRUNTIME}                        ║")
message(STATUS "╚══════════════════════════════════════════════╝")
message(STATUS "")
