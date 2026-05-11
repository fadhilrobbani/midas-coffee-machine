/**
 * @file ring_buffer.h
 * @brief Lock-free SPSC ring buffer for pipeline frame passing.
 *
 * Single-Producer Single-Consumer design using atomics.
 * Zero-copy: stores cv::Mat in fixed-size circular array.
 */

#pragma once

#include <opencv2/core.hpp>
#include <atomic>
#include <array>
#include <optional>

namespace fusion {

template <size_t N = 4>
class RingBuffer {
public:
    /// Try to push a frame (returns false if full)
    bool try_push(const cv::Mat& frame) {
        size_t head = head_.load(std::memory_order_relaxed);
        size_t next = (head + 1) % N;
        if (next == tail_.load(std::memory_order_acquire)) {
            return false;  // Full — drop frame
        }
        buffer_[head] = frame.clone();
        head_.store(next, std::memory_order_release);
        return true;
    }

    /// Try to pop a frame (returns nullopt if empty)
    std::optional<cv::Mat> try_pop() {
        size_t tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire)) {
            return std::nullopt;  // Empty
        }
        cv::Mat frame = std::move(buffer_[tail]);
        tail_.store((tail + 1) % N, std::memory_order_release);
        return frame;
    }

    /// Check if buffer is empty
    bool empty() const {
        return tail_.load(std::memory_order_acquire) ==
               head_.load(std::memory_order_acquire);
    }

    /// Current fill level
    size_t size() const {
        size_t h = head_.load(std::memory_order_acquire);
        size_t t = tail_.load(std::memory_order_acquire);
        return (h >= t) ? (h - t) : (N - t + h);
    }

    static constexpr size_t capacity() { return N - 1; }

private:
    std::array<cv::Mat, N> buffer_;
    std::atomic<size_t> head_{0};
    std::atomic<size_t> tail_{0};
};

} // namespace fusion
