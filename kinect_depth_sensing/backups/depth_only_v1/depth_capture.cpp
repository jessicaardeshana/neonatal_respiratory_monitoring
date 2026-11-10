#define GL_SILENCE_DEPRECATION
#include <GLFW/glfw3.h>
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <chrono>
#include <cmath>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <vector>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
volatile std::sig_atomic_t stop_requested = 0;
void interrupt(int) { stop_requested = 1; }
std::string quoted(const std::string& s) { std::ostringstream o; o << std::quoted(s); return o.str(); }

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "Usage: depth_capture NEW_RECORDING_DIRECTORY SECONDS\nClose Protonect first. Escape, window close, or Ctrl+C stops recording.\n";
    return 1;
  }
  double duration;
  try { size_t n; duration = std::stod(argv[2], &n);
    if (n != std::string(argv[2]).size() || !std::isfinite(duration) || duration <= 0 || duration > 3600) throw std::runtime_error("duration");
  } catch (...) { std::cerr << "SECONDS must be a number in (0, 3600].\n"; return 1; }
  const fs::path out(argv[1]);
  libfreenect2::Freenect2 context;
  // Listener must outlive the device's streaming threads.
  libfreenect2::SyncMultiFrameListener listener(libfreenect2::Frame::Depth);
  libfreenect2::Freenect2Device* dev = nullptr;
  GLFWwindow* window = nullptr;
  bool started = false, glfw_ready = false;
  size_t count = 0;
  int result = 0;
  std::ofstream raw, times, metadata;
  try {
    if (fs::exists(out)) throw std::runtime_error("Output already exists; choose a new directory.");
    if (!glfwInit()) throw std::runtime_error("GLFW initialization failed.");
    glfw_ready = true;
    // Initialize the preview before opening the device; the default depth
    // pipeline may also use GLFW and a separate OpenGL context.
    window = glfwCreateWindow(768, 636, "Depth preview: 500-4500 mm | Esc stops", nullptr, nullptr);
    if (!window) throw std::runtime_error("Preview window creation failed.");
    if (!context.enumerateDevices()) throw std::runtime_error("No Kinect detected. Check power/USB and close Protonect.");
    dev = context.openDevice(context.getDefaultDeviceSerialNumber());
    if (!dev) throw std::runtime_error("Could not open Kinect. Close Protonect and retry.");
    dev->setIrAndDepthFrameListener(&listener);
    const libfreenect2::Freenect2Device::Config config;
    dev->setConfiguration(config);
    fs::create_directories(out.parent_path().empty() ? fs::path(".") : out.parent_path());
    if (!fs::create_directory(out)) throw std::runtime_error("Cannot create a new output directory.");
    raw.open(out / "depth.f32", std::ios::binary);
    times.open(out / "timestamps.csv");
    metadata.open(out / "metadata.json");
    if (!raw || !times || !metadata) throw std::runtime_error("Cannot open recording files.");
    // This Mac is little endian; fail instead of silently mislabeling data.
    uint32_t endian = 1;
    if (*reinterpret_cast<unsigned char*>(&endian) != 1 || sizeof(float) != 4) throw std::runtime_error("Requires little-endian float32 host.");
    const auto wall = std::chrono::system_clock::now().time_since_epoch();
    metadata << "{\n  \"schema_version\": 1,\n  \"width\": 512, \"height\": 424,\n"
      << "  \"dtype\": \"<f4\", \"order\": \"C\", \"units\": \"mm\",\n"
      << "  \"invalid\": \"nonpositive or nonfinite; preserved unchanged\",\n"
      << "  \"device_tick_seconds\": 0.000125,\n"
      << "  \"serial\": " << quoted(dev->getSerialNumber()) << ",\n"
      << "  \"firmware\": " << quoted(dev->getFirmwareVersion()) << ",\n"
      << "  \"pipeline\": " << quoted(dev->getPacketPipelineName()) << ",\n"
      << "  \"library_version\": " << quoted(LIBFREENECT2_VERSION) << ",\n"
      << "  \"library_revision\": " << quoted(LIBFREENECT2_BUILD_REVISION) << ",\n"
      << "  \"start_unix_seconds\": " << std::setprecision(17) << std::chrono::duration<double>(wall).count() << ",\n"
      << "  \"requested_seconds\": " << duration << ",\n"
      << "  \"min_depth_m\": " << config.MinDepth << ", \"max_depth_m\": " << config.MaxDepth << ",\n"
      << "  \"bilateral_filter\": true, \"edge_aware_filter\": true,\n"
      << "  \"data_description\": \"SDK decoded native depth; no registration, rounding, or custom filtering\"\n}\n";
    metadata.flush();
    times << "frame,device_ticks,device_elapsed_s,arrival_timestamp_us,host_received_elapsed_s,sequence,status,valid_pixels\n";
    times << std::setprecision(17);
    if (!dev->startStreams(false, true)) throw std::runtime_error("Depth stream failed to start.");
    started = true;
    std::signal(SIGINT, interrupt);
    std::signal(SIGTERM, interrupt);
    std::cout << "Pipeline: " << dev->getPacketPipelineName() << "; recording float32 millimeters.\n";
    auto first = Clock::now(), last = first;
    uint32_t previous_tick = 0;
    uint64_t elapsed_ticks = 0;
    std::vector<unsigned char> preview(512 * 424 * 3);
    while (!stop_requested && !glfwWindowShouldClose(window)) {
      glfwPollEvents();
      if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) break;
      if (count && std::chrono::duration<double>(Clock::now() - first).count() >= duration) break;
      libfreenect2::FrameMap frames;
      if (!listener.waitForNewFrame(frames, 100)) {
        if (std::chrono::duration<double>(Clock::now() - last).count() > 10) throw std::runtime_error("No depth frames for 10 seconds.");
        continue;
      }
      // Always return frame ownership even if validation or disk writes fail.
      struct Release { libfreenect2::SyncMultiFrameListener& l; libfreenect2::FrameMap& f; ~Release() { l.release(f); } } release{listener, frames};
      const auto* f = frames.at(libfreenect2::Frame::Depth);
      if (f->width != 512 || f->height != 424 || f->bytes_per_pixel != 4 || f->format != libfreenect2::Frame::Float)
        throw std::runtime_error("Unexpected depth frame format.");
      const auto now = Clock::now();
      if (!count) { first = now; previous_tick = f->timestamp; }
      else elapsed_ticks += static_cast<uint32_t>(f->timestamp - previous_tick); // unwrap uint32 rollover
      previous_tick = f->timestamp;
      last = now;
      const double host_s = std::chrono::duration<double>(now - first).count();
      const float* depth = reinterpret_cast<const float*>(f->data);
      size_t valid = 0;
      double sum = 0;
      for (size_t i = 0; i < 512 * 424; ++i) {
        const bool ok = std::isfinite(depth[i]) && depth[i] > 0;
        if (ok) { ++valid; sum += depth[i]; }
        const auto gray = ok ? static_cast<unsigned char>(255 * (1 - std::max(0.f, std::min(1.f, (depth[i] - 500.f) / 4000.f)))) : 0;
        for (int c = 0; c < 3; ++c) preview[3*i+c] = gray;
      }
      raw.write(reinterpret_cast<const char*>(f->data), 512 * 424 * sizeof(float));
      times << count << ',' << f->timestamp << ',' << elapsed_ticks * 0.000125 << ',' << f->arrival_timestamp_us << ',' << host_s << ',' << f->sequence << ',' << f->status << ',' << valid << '\n';
      if (!raw || !times) throw std::runtime_error("Recording write failed (check free disk space).");
      ++count;
      if (count == 1 || count % 30 == 0) {
        std::cout << count << " frames | 512x424 float32 | " << (host_s > 0 ? (count-1)/host_s : 0)
          << " delivered fps | " << valid << " valid pixels | mean " << (valid ? sum/valid : 0) << " mm | status " << f->status << '\n';
        times.flush(); raw.flush();
      }
      glfwMakeContextCurrent(window);
      int w, h; glfwGetFramebufferSize(window, &w, &h);
      glViewport(0, 0, w, h);
      glClear(GL_COLOR_BUFFER_BIT);
      glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
      glRasterPos2f(-1, 1);
      glPixelZoom(w / 512.f, -h / 424.f);
      glDrawPixels(512, 424, GL_RGB, GL_UNSIGNED_BYTE, preview.data());
      glfwSwapBuffers(window);
    }
  } catch (const std::exception& e) { std::cerr << "Error: " << e.what() << '\n'; result = 1; }
  if (started) dev->stop();
  if (dev) dev->close();
  if (raw.is_open()) { raw.flush(); times.flush(); if (!raw || !times) { std::cerr << "Error flushing recording.\n"; result = 1; } }
  if (window) glfwDestroyWindow(window);
  if (glfw_ready) glfwTerminate();
  if (raw.is_open()) std::cout << "Saved " << count << " frames to " << out << '\n';
  return count == 0 ? 1 : result;
}
