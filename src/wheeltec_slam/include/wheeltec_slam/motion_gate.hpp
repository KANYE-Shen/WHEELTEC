#pragma once
#include <cmath>
#include <stdexcept>

namespace wheeltec_slam {
class MotionGate {
public:
  MotionGate(double distance = .03, double heading = .1)
    : distance_squared_(distance * distance), heading_(heading) {
    if (!std::isfinite(distance) || !std::isfinite(heading) ||
        distance <= 0. || heading <= 0.)
      throw std::invalid_argument("Keyframe thresholds must be finite and positive");
  }
  bool accepts(double x, double y, double yaw) const {
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(yaw)) return false;
    if (!have_pose_) return true;
    const double dx = x - x_, dy = y - y_;
    return dx * dx + dy * dy >= distance_squared_ ||
      std::abs(std::remainder(yaw - yaw_, 2. * std::acos(-1.))) >= heading_;
  }
  void commit(double x, double y, double yaw) {
    x_ = x; y_ = y; yaw_ = yaw; have_pose_ = true;
  }
  void reset() { have_pose_ = false; }
private:
  double distance_squared_, heading_, x_ = 0., y_ = 0., yaw_ = 0.;
  bool have_pose_ = false;
};
}
