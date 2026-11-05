#include <memory>
#include <stdexcept>
#include <sys/resource.h>
#include "slam_toolbox/slam_toolbox_async.hpp"
#include "wheeltec_slam/motion_gate.hpp"

// Keep upstream scan receipt, timestamping, pause/throttle, mapping and services.
// Only avoid inserting an identical stationary keyframe into the graph.
class MotionGatedSlam : public slam_toolbox::AsynchronousSlamToolbox {
public:
  explicit MotionGatedSlam(const rclcpp::NodeOptions &options)
    : AsynchronousSlamToolbox(options) {}
  void configure() override {
    AsynchronousSlamToolbox::configure();
    // Humble's outer distance-only filter must stay zero for pure rotation.
    if (get_parameter("minimum_travel_distance").as_double() != 0.)
      throw std::invalid_argument("motion_gated_slam requires minimum_travel_distance=0");
    gate_ = wheeltec_slam::MotionGate(
      declare_parameter<double>("stationary_keyframe_distance", .03),
      get_parameter("minimum_travel_heading").as_double());
  }
protected:
  karto::LocalizedRangeScan *addScan(karto::LaserRangeFinder *laser,
      const sensor_msgs::msg::LaserScan::ConstSharedPtr &scan,
      karto::Pose2 &pose) override {
    const double x = pose.GetX(), y = pose.GetY(), yaw = pose.GetHeading();
    if (!gate_.accepts(x, y, yaw)) return nullptr;
    auto *added = SlamToolbox::addScan(laser, scan, pose);
    if (added) gate_.commit(x, y, yaw);
    return added;
  }
  bool deserializePoseGraphCallback(
      const std::shared_ptr<rmw_request_id_t> header,
      const std::shared_ptr<slam_toolbox::srv::DeserializePoseGraph::Request> request,
      std::shared_ptr<slam_toolbox::srv::DeserializePoseGraph::Response> response) override {
    const bool ok = AsynchronousSlamToolbox::deserializePoseGraphCallback(header, request, response);
    if (ok) gate_.reset();
    return ok;
  }
private:
  wheeltec_slam::MotionGate gate_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  struct rlimit limit;
  if (getrlimit(RLIMIT_STACK, &limit) != 0) return 2;
  if (limit.rlim_cur < 40000000) {
    limit.rlim_cur = 40000000;
    if (setrlimit(RLIMIT_STACK, &limit) != 0) return 2;
  }
  auto node = std::make_shared<MotionGatedSlam>(rclcpp::NodeOptions());
  node->configure();
  node->loadPoseGraphByParams();
  rclcpp::spin(node->get_node_base_interface());
  rclcpp::shutdown();
  return 0;
}
