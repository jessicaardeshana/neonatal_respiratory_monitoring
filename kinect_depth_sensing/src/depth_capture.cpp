#define GL_SILENCE_DEPRECATION
#include <GLFW/glfw3.h>
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener.hpp>
#include <array>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <vector>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
using Frame = libfreenect2::Frame;
volatile std::sig_atomic_t stop_requested = 0;
void interrupt(int) { stop_requested = 1; }
std::string quoted(const std::string& s) { std::ostringstream o; o << std::quoted(s); return o.str(); }
int indexOf(Frame::Type type) { return type == Frame::Depth ? 0 : type == Frame::Ir ? 1 : 2; }

struct Sample {
  Frame::Type type;
  std::unique_ptr<Frame> frame;
  Clock::time_point received;
};
// SDK threads transfer frame ownership to this bounded queue. Disk writes and
// preview never run on the SDK threads. A full queue drops a new frame explicitly.
class CaptureQueue : public libfreenect2::FrameListener {
  std::mutex mutex;
  std::condition_variable ready;
  std::deque<Sample> pending;
  std::array<size_t, 3> dropped{};
public:
  bool onNewFrame(Frame::Type type, Frame* frame) override {
    const auto received = Clock::now();
    std::lock_guard<std::mutex> lock(mutex);
    if (pending.size() >= 24) { ++dropped[indexOf(type)]; return false; }
    pending.push_back({type, std::unique_ptr<Frame>(frame), received});
    ready.notify_one();
    return true;
  }
  bool pop(Sample& sample) {
    std::unique_lock<std::mutex> lock(mutex);
    ready.wait_for(lock, std::chrono::milliseconds(20), [&]{ return !pending.empty(); });
    if (pending.empty()) return false;
    sample = std::move(pending.front()); pending.pop_front(); return true;
  }
  std::array<size_t, 3> discardPending() {
    std::lock_guard<std::mutex> lock(mutex);
    std::array<size_t, 3> discarded{};
    for (const auto& sample : pending) ++discarded[indexOf(sample.type)];
    pending.clear(); // Release SDK-backed buffers before closing the device.
    return discarded;
  }
  std::array<size_t, 3> dropCounts() { std::lock_guard<std::mutex> lock(mutex); return dropped; }
};

struct StreamWriter {
  std::string name;
  size_t width, height, count = 0;
  bool color;
  int last_format = 0;
  std::ofstream data, timestamps;
  uint32_t previous_tick = 0;
  uint64_t elapsed_ticks = 0;
  StreamWriter(std::string n, size_t w, size_t h, bool c) : name(n), width(w), height(h), color(c) {}
  void open(const fs::path& out) {
    data.open(out / (name + (color ? ".u8" : ".f32")), std::ios::binary);
    timestamps.open(out / (name + "_timestamps.csv"));
    if (!data || !timestamps) throw std::runtime_error("Cannot open " + name + " recording files");
    timestamps << "frame,device_ticks,device_elapsed_s,arrival_timestamp_us,host_received_elapsed_s,sequence,status,format,exposure,gain,gamma\n" << std::setprecision(17);
  }
  void write(const Sample& sample, Clock::time_point origin) {
    const Frame& f = *sample.frame;
    if (f.width != width || f.height != height || f.bytes_per_pixel != 4 ||
        (color ? (f.format != Frame::BGRX && f.format != Frame::RGBX) : f.format != Frame::Float))
      throw std::runtime_error("Unexpected " + name + " frame format");
    if (count) elapsed_ticks += static_cast<uint32_t>(f.timestamp - previous_tick);
    previous_tick = f.timestamp;
    data.write(reinterpret_cast<const char*>(f.data), width * height * 4);
    timestamps << count << ',' << f.timestamp << ',' << elapsed_ticks * 0.000125 << ','
      << f.arrival_timestamp_us << ',' << std::chrono::duration<double>(sample.received - origin).count()
      << ',' << f.sequence << ',' << f.status << ',' << static_cast<int>(f.format) << ',' << f.exposure << ',' << f.gain << ',' << f.gamma << '\n';
    if (!data || !timestamps) throw std::runtime_error("Write failed for " + name + " (check free disk space)");
    last_format = static_cast<int>(f.format);
    ++count;
  }
  void flush() {
    if (!data.is_open()) return;
    data.flush(); timestamps.flush();
    if (!data || !timestamps) throw std::runtime_error("Flush failed for " + name);
  }
};

// Publish only after flushing all streams, so a preview never reads ahead of
// committed frame bytes. Atomic replacement keeps readers from seeing half JSON.
void publishStatus(const fs::path& out, const std::array<StreamWriter*, 3>& streams,
                   const std::array<size_t, 3>& drops, Clock::time_point origin,
                   const std::string& state, const std::string& reason) {
  const double elapsed = std::chrono::duration<double>(Clock::now() - origin).count();
  std::ofstream status(out / "status.tmp");
  status << std::setprecision(17) << "{\"state\": " << quoted(state)
    << ", \"reason\": " << quoted(reason) << ", \"elapsed_s\": " << elapsed
    << ", \"free_bytes\": " << fs::space(out).available << ", \"streams\": {";
  for (size_t i = 0; i < streams.size(); ++i) {
    const auto* s = streams[i];
    if (i) status << ',';
    status << quoted(s->name) << ": {\"frames\": " << s->count
      << ", \"bytes\": " << s->count * s->width * s->height * 4
      << ", \"queue_drops\": " << drops[i] << ", \"format\": " << s->last_format << '}';
  }
  status << "}}\n"; status.close();
  if (!status) throw std::runtime_error("Status write failed");
  fs::rename(out / "status.tmp", out / "status.json");
}

int main(int argc, char** argv) {
  std::cout << std::unitbuf;
  if (argc < 2 || argc > 3) {
    std::cerr << "Usage: depth_capture NEW_RECORDING_DIRECTORY [SECONDS | --continuous]\nOmit duration to record continuously. Close Protonect first. Esc or Ctrl+C stops.\n";
    return 1;
  }
  const bool continuous = argc == 2 || std::string(argv[2]) == "--continuous";
  double duration = 0;
  try { if (!continuous) { size_t n; duration = std::stod(argv[2], &n);
    if (n != std::string(argv[2]).size() || !std::isfinite(duration) || duration <= 0 || duration > 3600) throw std::runtime_error("duration");
  } } catch (...) { std::cerr << "SECONDS must be a number in (0, 3600].\n"; return 1; }
  const fs::path out(argv[1]);
  auto context = std::make_unique<libfreenect2::Freenect2>();
  CaptureQueue queue; // Outlives device threads, including during cleanup.
  libfreenect2::Freenect2Device* dev = nullptr;
  GLFWwindow* window = nullptr;
  bool started = false, glfw_ready = false, created = false;
  int result = 0;
  std::string stop_reason = "user_stop";
  constexpr uintmax_t disk_reserve = 2ULL * 1024 * 1024 * 1024;
  auto acquisition_origin = Clock::now();
  StreamWriter depth("depth", 512, 424, false), ir("ir", 512, 424, false), rgb("rgb", 1920, 1080, true);
  std::array<StreamWriter*, 3> streams{&depth, &ir, &rgb};
  std::signal(SIGINT, interrupt); std::signal(SIGTERM, interrupt);
  try {
    if (fs::exists(out)) throw std::runtime_error("Output already exists; choose a new directory");
    uint32_t endian = 1;
    if (*reinterpret_cast<unsigned char*>(&endian) != 1 || sizeof(float) != 4) throw std::runtime_error("Requires little-endian float32 host");
    if (!glfwInit()) throw std::runtime_error("GLFW initialization failed");
    glfw_ready = true;
    window = glfwCreateWindow(768, 636, "Recording depth + IR + RGB | Depth preview | Esc stops", nullptr, nullptr);
    if (!window) throw std::runtime_error("Preview window creation failed");
    if (!context->enumerateDevices()) throw std::runtime_error("No Kinect detected. Check power/USB and close Protonect");
    dev = context->openDevice(context->getDefaultDeviceSerialNumber());
    if (!dev) throw std::runtime_error("Could not open Kinect. Close Protonect and retry");
    dev->setIrAndDepthFrameListener(&queue);
    dev->setColorFrameListener(&queue);
    const libfreenect2::Freenect2Device::Config config;
    dev->setConfiguration(config);
    fs::create_directories(out.parent_path().empty() ? fs::path(".") : out.parent_path());
    if (!fs::create_directory(out)) throw std::runtime_error("Cannot create a new output directory");
    created = true;
    if (fs::space(out).available < disk_reserve)
      throw std::runtime_error("Less than 2 GiB available; choose another recording disk");
    for (auto* s : streams) s->open(out);
    std::ofstream metadata(out / "metadata.json");
    metadata << "{\n  \"schema_version\": 2,\n"
      << "  \"streams\": {\n"
      << "    \"depth\": {\"file\": \"depth.f32\", \"width\": 512, \"height\": 424, \"channels\": 1, \"dtype\": \"<f4\", \"units\": \"mm\"},\n"
      << "    \"ir\": {\"file\": \"ir.f32\", \"width\": 512, \"height\": 424, \"channels\": 1, \"dtype\": \"<f4\", \"units\": \"SDK intensity (nominal 0–65535)\"},\n"
      << "    \"rgb\": {\"file\": \"rgb.u8\", \"width\": 1920, \"height\": 1080, \"channels\": 4, \"dtype\": \"|u1\", \"units\": \"8-bit color; format column: 4=BGRX, 5=RGBX; X unused\"}\n  },\n"
      << "  \"device_tick_seconds\": 0.000125,\n"
      << "  \"serial\": " << quoted(dev->getSerialNumber()) << ",\n"
      << "  \"firmware\": " << quoted(dev->getFirmwareVersion()) << ",\n"
      << "  \"pipeline\": " << quoted(dev->getPacketPipelineName()) << ",\n"
      << "  \"library_version\": " << quoted(LIBFREENECT2_VERSION) << ",\n"
      << "  \"library_revision\": " << quoted(LIBFREENECT2_BUILD_REVISION) << ",\n"
      << "  \"start_unix_seconds\": " << std::setprecision(17) << std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count() << ",\n"
      << "  \"continuous\": " << (continuous ? "true" : "false") << ",\n"
      << "  \"requested_seconds\": " << (continuous ? "null" : std::to_string(duration)) << ",\n"
      << "  \"min_depth_m\": " << config.MinDepth << ", \"max_depth_m\": " << config.MaxDepth << ",\n"
      << "  \"bilateral_filter\": true, \"edge_aware_filter\": true,\n"
      << "  \"timing\": \"Separate streams, not synchronized triplets. Device elapsed has independent per-stream origins. Host receipt uses one callback clock origin. Arrival timestamps share host monotonic microseconds.\",\n"
      << "  \"data_description\": \"Unregistered SDK-decoded native frames; no custom filtering, rounding, or intensity normalization\"\n}\n";
    metadata.flush(); if (!metadata) throw std::runtime_error("Metadata write failed");
    const auto origin = Clock::now();
    acquisition_origin = origin;
    if (!dev->startStreams(true, true)) throw std::runtime_error("Streams failed to start");
    started = true;
    std::cout << "Pipeline: " << dev->getPacketPipelineName() << "; depth float32 mm, IR float32 intensity, RGB native 4-channel bytes.\n";
    auto first = Clock::now(), next_report = first;
    std::array<Clock::time_point, 3> last{first, first, first};
    bool have_first = false;
    std::vector<unsigned char> preview(512 * 424 * 3);
    while (!stop_requested && !glfwWindowShouldClose(window)) {
      glfwPollEvents();
      if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) break;
      const auto now = Clock::now();
      if (!continuous && have_first && std::chrono::duration<double>(now - first).count() >= duration) {
        stop_reason = "duration_reached"; break;
      }
      for (size_t i = 0; i < 3; ++i)
        if (std::chrono::duration<double>(now - last[i]).count() > 10) throw std::runtime_error("No " + streams[i]->name + " frames for 10 seconds");
      Sample sample;
      if (!queue.pop(sample)) continue;
      const int index = indexOf(sample.type);
      if (!have_first) { first = sample.received; have_first = true; }
      streams[index]->write(sample, origin);
      last[index] = Clock::now();
      if (sample.type == Frame::Depth) {
        const float* values = reinterpret_cast<const float*>(sample.frame->data);
        for (size_t i = 0; i < 512 * 424; ++i) {
          const bool valid = std::isfinite(values[i]) && values[i] > 0;
          const auto gray = valid ? static_cast<unsigned char>(255 * (1 - std::max(0.f, std::min(1.f, (values[i] - 500.f) / 4000.f)))) : 0;
          for (int c = 0; c < 3; ++c) preview[3*i+c] = gray;
        }
        glfwMakeContextCurrent(window);
        int w, h; glfwGetFramebufferSize(window, &w, &h);
        glViewport(0, 0, w, h); glClear(GL_COLOR_BUFFER_BIT);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1); glRasterPos2f(-1, 1);
        glPixelZoom(w / 512.f, -h / 424.f);
        glDrawPixels(512, 424, GL_RGB, GL_UNSIGNED_BYTE, preview.data());
        glfwSwapBuffers(window);
      }
      if (now >= next_report) {
        const auto drops = queue.dropCounts();
        for (size_t i = 0; i < 3; ++i) {
          std::cout << streams[i]->name << ": " << streams[i]->count << " frames (queue drops " << drops[i] << ") | ";
          streams[i]->flush();
        }
        const auto available = fs::space(out).available;
        if (available < disk_reserve) {
          stop_reason = "low_disk_space"; result = 1;
          std::cerr << "Stopping: less than 2 GiB disk space remains\n";
          break;
        }
        publishStatus(out, streams, drops, origin, "recording", "");
        std::cout << '\n'; next_report = now + std::chrono::seconds(1);
      }
    }
  } catch (const std::exception& e) { std::cerr << "Error: " << e.what() << '\n'; stop_reason = e.what(); result = 1; }
  if (started && !dev->stop()) { std::cerr << "SDK stop reported an error\n"; stop_reason = "sdk_stop_error"; result = 1; }
  const auto discarded = queue.discardPending();
  if (dev && !dev->close()) { std::cerr << "SDK close reported an error\n"; stop_reason = "sdk_close_error"; result = 1; }
  context.reset(); // Destroy SDK OpenGL resources while GLFW is still initialized.
  for (auto* s : streams) if (!s->count) result = 1;
  try {
    for (auto* s : streams) s->flush();
    if (created) {
      const auto drops = queue.dropCounts();
      std::ofstream summary(out / "summary.json");
      summary << "{\"exit_code\": " << result << ", \"stop_reason\": " << quoted(stop_reason) << ", \"streams\": {";
      for (size_t i = 0; i < 3; ++i) {
        if (i) summary << ',';
        summary << quoted(streams[i]->name) << ": {\"saved_frames\": " << streams[i]->count << ", \"queue_drops\": " << drops[i] << ", \"pending_at_stop\": " << discarded[i] << '}';
      }
      summary << "}}\n"; summary.flush();
      if (!summary) throw std::runtime_error("Summary write failed");
      publishStatus(out, streams, drops, acquisition_origin, result ? "error" : "stopped", stop_reason);
    }
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; result = 1; }
  if (window) glfwDestroyWindow(window);
  if (glfw_ready) glfwTerminate();
  for (auto* s : streams) {
    std::cout << s->name << ": " << s->count << " saved frames\n";
    if (!s->count) result = 1;
  }
  return result;
}
