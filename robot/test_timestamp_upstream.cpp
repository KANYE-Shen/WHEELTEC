// Deterministic arithmetic-only harness; actual pinned upstream utils.hpp included.
// No camera opens, ROS nodes, clocks changed, or real network access.
#include <sys/time.h>
#include <time.h>
#include <cstdint>
#include <cerrno>
#include <iostream>
#include <vector>
static timeval fake_epoch{946686580, 823742};
static timespec fake_monotonic{10, 123456000};
static int fake_gettimeofday(timeval* t, void*) { *t=fake_epoch; return 0; }
static int fake_clock_gettime(clockid_t, timespec* t) { *t=fake_monotonic; return 0; }
#define gettimeofday fake_gettimeofday
#define clock_gettime fake_clock_gettime
#include "usb_cam/utils.hpp"
#undef gettimeofday
#undef clock_gettime

static int checks=0, failures=0;
static void check(bool ok, const char* label) {
  ++checks; if(!ok) { ++failures; std::cout << "FAIL " << label << '\n'; }
}
static timespec stamp(timeval buffer, time_t shift) {
#ifdef LEGACY
  // Exact mmap read_frame arithmetic from the pinned legacy src/usb_cam.cpp.
  const int64_t buffer_s=buffer.tv_sec+static_cast<int64_t>(round(buffer.tv_usec/1000000.0));
  return {static_cast<time_t>(round(buffer_s))+shift, static_cast<int64_t>(buffer.tv_usec*1000.0)};
#else
  return usb_cam::utils::calc_img_timestamp(buffer,shift);
#endif
}
int main() {
#ifdef LEGACY
  const auto shift=usb_cam::utils::get_epoch_time_shift()*1000000;
#else
  const auto shift=usb_cam::utils::get_epoch_time_shift_us();
#endif
  check(shift==946686570700286LL,"epoch microseconds retained (ee0a2f7)");
#ifdef LEGACY
  const time_t frame_shift=100;
#else
  const time_t frame_shift=100000000;
#endif
  const auto a=stamp({10,499999},frame_shift), b=stamp({10,500000},frame_shift);
  check(a.tv_sec==110 && a.tv_nsec==499999000,"before half second");
  check(b.tv_sec==110 && b.tv_nsec==500000000,"half second stays in same second");
  const auto c=stamp({10,999999},frame_shift), d=stamp({11,0},frame_shift);
  check(c.tv_sec==110 && c.tv_nsec==999999000,"last microsecond does not round seconds");
  check(d.tv_sec>c.tv_sec || (d.tv_sec==c.tv_sec && d.tv_nsec>=c.tv_nsec),"no backward stamp at rollover");
#ifndef LEGACY
  const auto e=stamp({10,999999},946686570700286LL);
  check(e.tv_sec==946686581 && e.tv_nsec==700285000,"fractional offset carry");
  fake_epoch={100,0}; fake_monotonic={9,999999500};
  check(usb_cam::utils::get_epoch_time_shift_us()==90000000,"monotonic rounding carries");
  const auto f=stamp({11,0},100700286);
  check(f.tv_sec==111 && f.tv_nsec==700286000,"integer nanoseconds normalized");
#endif
  std::cout<<"checks="<<checks<<" failures="<<failures<<'\n';
  return failures?1:0;
}
