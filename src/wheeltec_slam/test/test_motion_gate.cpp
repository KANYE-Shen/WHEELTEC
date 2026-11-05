#include <cmath>
#include <iostream>
#include <stdexcept>
#include "wheeltec_slam/motion_gate.hpp"
using wheeltec_slam::MotionGate;
void require(bool value) { if (!value) throw std::runtime_error("motion gate regression"); }
int main() {
  MotionGate gate(.03, .1);
  require(gate.accepts(0., 0., 0.));
  gate.commit(0., 0., 0.);
  for (int i = 0; i < 10000; ++i) require(!gate.accepts(0., 0., 0.));
  require(!gate.accepts(.01, -.01, .04));
  require(gate.accepts(.031, 0., 0.));
  require(gate.accepts(0., 0., .101)); // pure rotation must remain observable
  require(gate.accepts(0., 0., -.101));
  gate.commit(0., 0., 3.13);
  require(!gate.accepts(0., 0., -3.13)); // heading wraps across pi
  require(gate.accepts(0., 0., -3.0));
  require(!gate.accepts(NAN, 0., 0.));
  gate.reset();
  require(gate.accepts(0., 0., 3.13));
  std::cout << "stationary, translation, rotation, wrapping, invalid, reset passed\n";
}
