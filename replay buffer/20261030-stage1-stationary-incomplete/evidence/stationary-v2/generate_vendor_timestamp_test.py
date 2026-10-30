# Generate C++ regression from collected vendor timestamp expressions, no camera access.
from pathlib import Path
import re,sys
root=Path(sys.argv[1]);out=Path(sys.argv[2]);cpp=(root/'src/usb_cam.cpp').read_text();utils=(root/'include/usb_cam/utils.hpp').read_text()
fn=re.search(r'inline time_t (get_epoch_time_shift(?:_us)?)\(\)\s*\{.*?\n\}',utils,re.S)
blocks=re.findall(r'      m_buffer_time_s =.*?m_image.stamp.tv_nsec = [^;]+;',cpp,re.S)
if not fn or len(blocks)!=2:raise ValueError('Unsupported timestamp code; manual review required')
if 'inline time_t get_epoch_time_shift_us()' in utils:
 fn=re.search(r'inline time_t (get_epoch_time_shift_us)\(\)\s*\{.*?\n\}',utils,re.S)
name=fn.group(1);legacy=name=='get_epoch_time_shift'
head='''
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
'''
body=head+fn.group(0)+'\n#undef gettimeofday\n#undef clock_gettime\n'
for i,block in enumerate(blocks):
 body+=f'timespec stamp{i}(timeval input,time_t shift){{\nstruct {{timeval timestamp;}} buf{{input}};struct {{timespec stamp;}} m_image;double m_buffer_time_s;time_t m_epoch_time_shift=shift;\n'+block.replace('m_epoch_time_shift_us','m_epoch_time_shift')+'\nreturn m_image.stamp; }\n'
body+='int main(){int fail=0,checks=0;auto check=[&](bool ok,const std::string& s){checks++;if(!ok){fail++;std::cout<<"FAIL "<<s<<"\\n";}};\n'
body+=f'auto shift={name}();check(shift'+('*1000000' if legacy else '')+'==1793352220700286LL,"fractional epoch offset");\n'
for i in range(2):
 shift=100 if legacy else 100700286
 body+=f'''{{auto a=stamp{i}({{10,499999}},{shift});auto b=stamp{i}({{10,500000}},{shift});auto c=stamp{i}({{10,999999}},{shift});auto d=stamp{i}({{11,0}},{shift});
 check(a.tv_sec==111 && a.tv_nsec==200285000,"branch {i} before half-second correct offset");
 check(b.tv_sec==111 && b.tv_nsec==200286000,"branch {i} half-second no extra second");
 check(c.tv_sec==111 && c.tv_nsec==700285000,"branch {i} subsecond carry");
 check(d.tv_sec>c.tv_sec || (d.tv_sec==c.tv_sec && d.tv_nsec>c.tv_nsec),"branch {i} rollover monotonic");
 check(a.tv_nsec>=0 && a.tv_nsec<1000000000 && b.tv_nsec>=0 && b.tv_nsec<1000000000,"branch {i} normalized ns");}}
'''
body+='std::cout<<"checks="<<checks<<" failures="<<fail<<"\\n";return fail?1:0;}\n'
out.write_text(body,encoding='utf-8')
