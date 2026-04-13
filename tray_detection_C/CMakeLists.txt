cmake_minimum_required(VERSION 3.14)
project(tray_detector VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Platform selection ───────────────────────────────────────────────────
# Usage:
#   cmake .. -DTARGET_PLATFORM=PC        (default)
#   cmake .. -DTARGET_PLATFORM=RZV2H     (cross-compile for Renesas)
set(TARGET_PLATFORM "PC" CACHE STRING "Target platform: PC or RZV2H")

message(STATUS "========================================")
message(STATUS "  Target Platform : ${TARGET_PLATFORM}")
message(STATUS "========================================")

# ── Find Dependencies ────────────────────────────────────────────────────
find_package(OpenCV 4.0 REQUIRED COMPONENTS core imgproc imgcodecs highgui
             videoio dnn calib3d)
find_package(yaml-cpp REQUIRED)

# ── Source files ─────────────────────────────────────────────────────────
set(COMMON_SOURCES
    src/config.cpp
    src/method_a.cpp
    src/method_b.cpp
    src/method_c.cpp
    src/fusion.cpp
    src/camera_utils.cpp
    src/pipeline.cpp
    src/main.cpp
)

# Platform-specific detector backend
if(TARGET_PLATFORM STREQUAL "RZV2H")
    list(APPEND COMMON_SOURCES src/drpai_detector.cpp)
    add_definitions(-DUSE_DRPAI)
    message(STATUS "  Detector Backend: DRP-AI (NPU)")
else()
    list(APPEND COMMON_SOURCES src/onnx_detector.cpp)
    add_definitions(-DUSE_ONNX)
    message(STATUS "  Detector Backend: ONNX (OpenCV DNN)")
endif()

# ── Build executable ─────────────────────────────────────────────────────
add_executable(tray_detector ${COMMON_SOURCES})

target_include_directories(tray_detector PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(tray_detector PRIVATE
    ${OpenCV_LIBS}
    yaml-cpp
)

# ── DRP-AI linking (RZ/V2H only) ────────────────────────────────────────
if(TARGET_PLATFORM STREQUAL "RZV2H")
    # Uncomment and set path when DRP-AI SDK is available:
    # target_include_directories(tray_detector PRIVATE ${DRPAI_INCLUDE_DIR})
    # target_link_libraries(tray_detector PRIVATE ${DRPAI_LIBRARIES})
    message(STATUS "  NOTE: DRP-AI SDK paths must be configured manually")
endif()

# ── Optimization flags ───────────────────────────────────────────────────
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    if(TARGET_PLATFORM STREQUAL "RZV2H")
        target_compile_options(tray_detector PRIVATE -O2 -march=armv8.2-a)
    else()
        target_compile_options(tray_detector PRIVATE -O2 -march=native)
    endif()
endif()

message(STATUS "========================================")
