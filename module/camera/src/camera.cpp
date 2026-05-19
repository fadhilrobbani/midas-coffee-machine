#include <camera/camera.h>

/* =========================
 * Constructor / Destructor
 * ========================= */
Camera::Camera(std::variant<int, std::string> source, bool autostart)
    : camera_source(source), running(false) {
  if (autostart) {
    start_camera();
  }
}

Camera::~Camera() { stop_camera(); }

/* =========================
 * Control
 * ========================= */
void Camera::start_camera() {
  // Do nothing if already running
  if (running.load())
    return;

  running = true;
  camera_thread = std::thread(&Camera::camera_loop, this);
}

void Camera::stop_camera() {
  if (!running.load())
    return;

  running = false;

  if (camera_thread.joinable()) {
    camera_thread.join();
  }

  if (cap.isOpened()) {
    cap.release();
  }

  // Clear last frame
  {
    std::lock_guard<std::mutex> lock(frame_mutex);
    frame.release();
    frame = cv::Mat();
  }
}

/* =========================
 * Frame access
 * ========================= */
cv::Mat Camera::get_frame() {
  std::lock_guard<std::mutex> lock(frame_mutex);

  if (frame.empty()) {
    return cv::Mat();
  }

  cv::Mat resized_frame;

#ifdef V2H
#if INPUT_CAM_TYPE == 1
  cv::resize(frame, resized_frame, cv::Size(MIPI_WIDTH, MIPI_HEIGHT));
#else
  cv::resize(frame, resized_frame, cv::Size(USB_WIDTH, USB_HEIGHT));
#endif // INPUT_CAM_TYPE
#else
  resized_frame = frame;
#endif // V2H
  return resized_frame;
}

/* =========================
 * Internal capture loop
 * ========================= */
void Camera::camera_loop() {
  while (running.load()) {
    // Build GStreamer pipeline.
    // - int source  : build default JPEG fisheye pipeline (cup_cam)
    // - string source: use directly as custom pipeline (face_cam or any other)
    std::string pipeline;
    if (camera_source.index() == 0) {
      std::string index  = std::to_string(std::get<int>(camera_source));
      std::string device = "/dev/video" + index;
      pipeline = "v4l2src device=" + device +
                 " io-mode=2 do-timestamp=true "
                 "! image/jpeg,width=2592,height=1944,framerate=20/1 "
                 "! jpegdec "
                 "! videoconvert "
                 "! video/x-raw,format=BGR "
                 "! appsink max-buffers=1 drop=true sync=false";
    } else {
      // Custom pipeline string from config (e.g. face_cam with YUY2)
      pipeline = std::get<std::string>(camera_source);
    }

    bool opened = cap.open(pipeline, cv::CAP_GSTREAMER);

    if (!opened || !cap.isOpened()) {
      LOGR_WARN("Failed to open camera. Retrying in 1 second...");
      std::this_thread::sleep_for(std::chrono::seconds(1));
      continue;
    }

    LOGR_INFO("Camera opened successfully.");

    // Skip initial frames for stabilization
    cv::Mat skip_frame;
    for (int i = 0; i < 20 && running.load(); ++i) {
      cap >> skip_frame;
      std::this_thread::sleep_for(std::chrono::milliseconds(30));
    }

    // Main capture loop
    cv::Mat local_frame;
    while (running.load()) {
      if (!cap.read(local_frame) || local_frame.empty()) {
        LOGR_WARN("Empty frame received, restarting capture...");
        cap.release();
        break;
      }

      // Update internal frame buffer
      {
        std::lock_guard<std::mutex> lock(frame_mutex);
        local_frame.copyTo(frame);
      }

      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    cap.release();

    {
      std::lock_guard<std::mutex> lock(frame_mutex);
      frame.release();
    }
  }

  LOGR_INFO("Camera capture loop ended.");
}