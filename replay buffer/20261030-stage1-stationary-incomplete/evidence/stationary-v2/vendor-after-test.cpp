
#include <sys/time.h>
#include <ctime>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
static timeval epoch{1793352230,823742};
static timespec mono{10,123456000};
static int fake_gettimeofday(timeval* x,void*){*x=epoch;return 0;}
static int fake_clock_gettime(clockid_t,timespec* x){*x=mono;return 0;}
#define gettimeofday fake_gettimeofday
#define clock_gettime fake_clock_gettime
inline time_t get_epoch_time_shift_us()
{
  struct timeval epoch_time;
  struct timespec monotonic_time;
  gettimeofday(&epoch_time, NULL);
  clock_gettime(CLOCK_MONOTONIC, &monotonic_time);
  const int64_t epoch_us = static_cast<int64_t>(epoch_time.tv_sec) * 1000000 +
    epoch_time.tv_usec;
  const int64_t monotonic_us = static_cast<int64_t>(monotonic_time.tv_sec) * 1000000 +
    monotonic_time.tv_nsec / 1000;
  return static_cast<time_t>(epoch_us - monotonic_us);
}
#undef gettimeofday
#undef clock_gettime
timespec stamp0(timeval input,time_t shift){
struct {timeval timestamp;} buf{input};struct {timespec stamp;} m_image;double m_buffer_time_s;time_t m_epoch_time_shift=shift;
      m_buffer_time_s = buf.timestamp.tv_sec;
      const int64_t mmap_frame_us = static_cast<int64_t>(buf.timestamp.tv_sec) * 1000000 +
        buf.timestamp.tv_usec + m_epoch_time_shift;
      m_image.stamp.tv_sec = static_cast<time_t>(mmap_frame_us / 1000000);
      m_image.stamp.tv_nsec = (mmap_frame_us % 1000000) * 1000;
return m_image.stamp; }
timespec stamp1(timeval input,time_t shift){
struct {timeval timestamp;} buf{input};struct {timespec stamp;} m_image;double m_buffer_time_s;time_t m_epoch_time_shift=shift;
      m_buffer_time_s = buf.timestamp.tv_sec;
      const int64_t userptr_frame_us = static_cast<int64_t>(buf.timestamp.tv_sec) * 1000000 +
        buf.timestamp.tv_usec + m_epoch_time_shift;
      m_image.stamp.tv_sec = static_cast<time_t>(userptr_frame_us / 1000000);
      m_image.stamp.tv_nsec = (userptr_frame_us % 1000000) * 1000;
return m_image.stamp; }
int main(){int fail=0,checks=0;auto check=[&](bool ok,const std::string& s){checks++;if(!ok){fail++;std::cout<<"FAIL "<<s<<"\n";}};
auto shift=get_epoch_time_shift_us();check(shift==1793352220700286LL,"fractional epoch offset");
{auto a=stamp0({10,499999},100700286);auto b=stamp0({10,500000},100700286);auto c=stamp0({10,999999},100700286);auto d=stamp0({11,0},100700286);
 check(a.tv_sec==111 && a.tv_nsec==200285000,"branch 0 before half-second correct offset");
 check(b.tv_sec==111 && b.tv_nsec==200286000,"branch 0 half-second no extra second");
 check(c.tv_sec==111 && c.tv_nsec==700285000,"branch 0 subsecond carry");
 check(d.tv_sec>c.tv_sec || (d.tv_sec==c.tv_sec && d.tv_nsec>c.tv_nsec),"branch 0 rollover monotonic");
 check(a.tv_nsec>=0 && a.tv_nsec<1000000000 && b.tv_nsec>=0 && b.tv_nsec<1000000000,"branch 0 normalized ns");}
{auto a=stamp1({10,499999},100700286);auto b=stamp1({10,500000},100700286);auto c=stamp1({10,999999},100700286);auto d=stamp1({11,0},100700286);
 check(a.tv_sec==111 && a.tv_nsec==200285000,"branch 1 before half-second correct offset");
 check(b.tv_sec==111 && b.tv_nsec==200286000,"branch 1 half-second no extra second");
 check(c.tv_sec==111 && c.tv_nsec==700285000,"branch 1 subsecond carry");
 check(d.tv_sec>c.tv_sec || (d.tv_sec==c.tv_sec && d.tv_nsec>c.tv_nsec),"branch 1 rollover monotonic");
 check(a.tv_nsec>=0 && a.tv_nsec<1000000000 && b.tv_nsec>=0 && b.tv_nsec<1000000000,"branch 1 normalized ns");}
std::cout<<"checks="<<checks<<" failures="<<fail<<"\n";return fail?1:0;}
