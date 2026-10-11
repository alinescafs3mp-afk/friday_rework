#define _GNU_SOURCE
/* SOURCE primitive only: no host/admission qualification or installation.
 * A terminally sealed main ELF, exact kernel fd identity, SHA and one owned
 * pre-exec release. Loader/DSO/import/ancestry/cgroup custody stays UNBOUND.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static const uint32_t k[64]={
 0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
 0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
 0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
 0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
 0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
 0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
typedef struct {uint32_t h[8];unsigned char block[64];size_t used;uint64_t length;} Hash;
static uint32_t rot(uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));}
static void transform(Hash *s,const unsigned char *p){
 uint32_t w[64],a,b,c,d,e,f,g,h;
 for(unsigned i=0;i<16;i++)w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|p[4*i+3];
 for(unsigned i=16;i<64;i++)w[i]=w[i-16]+(rot(w[i-15],7)^rot(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rot(w[i-2],17)^rot(w[i-2],19)^(w[i-2]>>10));
 a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
 for(unsigned i=0;i<64;i++){uint32_t t=h+(rot(e,6)^rot(e,11)^rot(e,25))+((e&f)^(~e&g))+k[i]+w[i];uint32_t u=(rot(a,2)^rot(a,13)^rot(a,22))+((a&b)^(a&c)^(b&c));h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;}
 s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void update(Hash *s,const unsigned char *p,size_t n){
 s->length+=n;
 while(n){size_t take=64-s->used;if(take>n)take=n;memcpy(s->block+s->used,p,take);s->used+=take;p+=take;n-=take;if(s->used==64){transform(s,s->block);s->used=0;}}
}
static void finish(Hash *s,char out[65]){
 uint64_t bits=s->length*8;unsigned char one=0x80,zero=0;update(s,&one,1);while(s->used!=56)update(s,&zero,1);
 unsigned char length[8];for(unsigned i=0;i<8;i++)length[7-i]=(unsigned char)(bits>>(i*8));update(s,length,8);
 for(unsigned i=0;i<8;i++){snprintf(out+8*i,9,"%08" PRIx32,s->h[i]);}
 out[64]=0;
}
static int refuse(const char *reason){fprintf(stdout,"{\"status\":\"REFUSED\",\"reason\":\"%s\",\"target_entered\":false,\"admission\":false}\n",reason);fflush(stdout);return 77;}
static int number(const char *p,uint64_t *v){
 if(!p||!*p||strlen(p)>20)return 0;
 for(const char *q=p;*q;q++)if(*q<'0'||*q>'9')return 0;
 errno=0;char *end=NULL;unsigned long long x=strtoull(p,&end,10);if(errno||!end||*end)return 0;*v=(uint64_t)x;return 1;
}
static uint64_t monotonic_ns(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000000000+(uint64_t)t.tv_nsec;}
static int exact_fd(int fd,const uint64_t *v,const char *expected){
 struct stat st;int seals=fcntl(fd,F_GET_SEALS);
 if(seals<0||(seals&(F_SEAL_SEAL|F_SEAL_SHRINK|F_SEAL_GROW|F_SEAL_WRITE))!=(F_SEAL_SEAL|F_SEAL_SHRINK|F_SEAL_GROW|F_SEAL_WRITE))return 0;
 if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_nlink!=0||st.st_uid!=getuid()||(st.st_mode&07777)!=0500||st.st_size<64||st.st_size>128*1024*1024)return 0;
 if((uint64_t)st.st_dev!=v[1]||(uint64_t)st.st_ino!=v[2]||(uint64_t)st.st_size!=v[3]||(uint64_t)st.st_uid!=v[4])return 0;
 if((uint64_t)st.st_mtim.tv_sec*1000000000+(uint64_t)st.st_mtim.tv_nsec!=v[5]||(uint64_t)st.st_ctim.tv_sec*1000000000+(uint64_t)st.st_ctim.tv_nsec!=v[6])return 0;
 unsigned char header[64];if(pread(fd,header,64,0)!=64||memcmp(header,"\x7f" "ELF",4)||header[4]!=2||header[5]!=1||header[6]!=1||header[18]!=62||header[19]!=0)return 0;
 Hash h={{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19},{0},0,0};unsigned char buf[65536];off_t off=0;
 while(off<st.st_size){size_t n=(size_t)(st.st_size-off);if(n>sizeof(buf))n=sizeof(buf);ssize_t got=pread(fd,buf,n,off);if(got<0&&errno==EINTR)continue;if(got<=0)return 0;update(&h,buf,(size_t)got);off+=got;}
 char actual[65];finish(&h,actual);if(strcmp(actual,expected))return 0;
 struct stat after;if(fstat(fd,&after)||after.st_dev!=st.st_dev||after.st_ino!=st.st_ino||after.st_size!=st.st_size||after.st_uid!=st.st_uid||after.st_mode!=st.st_mode||after.st_nlink!=st.st_nlink||after.st_mtim.tv_sec!=st.st_mtim.tv_sec||after.st_mtim.tv_nsec!=st.st_mtim.tv_nsec||after.st_ctim.tv_sec!=st.st_ctim.tv_sec||after.st_ctim.tv_nsec!=st.st_ctim.tv_nsec)return 0;
 return 1;
}
int main(int argc,char **argv){
 /* fd, dev, ino, size, uid, mtime_ns, ctime_ns, useful_monotonic_ns, digest. Fixed inert-target
  * argv/environment; a production command or admission manifest is unsupported.
  */
 uint64_t v[8];if(argc!=10)return refuse("EXACT_ARGUMENTS_REQUIRED");
 for(unsigned i=0;i<8;i++)if(!number(argv[i+1],&v[i]))return refuse("FINITE_DECIMAL_REQUIRED");
 if(v[0]<3||v[0]>1048575||strlen(argv[9])!=64)return refuse("EXACT_FD_DIGEST_REQUIRED");
 for(unsigned i=0;i<64;i++)if(!((argv[9][i]>='0'&&argv[9][i]<='9')||(argv[9][i]>='a'&&argv[9][i]<='f')))return refuse("LOWERCASE_SHA256_REQUIRED");
 uint64_t now=monotonic_ns();if(!now||now>=v[7]||v[7]-now>60000000000ULL)return refuse("ORIGINAL_FINITE_CLOCK_REQUIRED");
 int fd=(int)v[0];if(!exact_fd(fd,v,argv[9]))return refuse("SEALED_EXACT_ELF_SHA_REQUIRED");
 printf("{\"status\":\"READY_BEFORE_EXEC\",\"pid\":%ld,\"fd\":%d,\"main_elf_sha256\":\"%s\",\"admission\":false,\"loader_import_custody\":\"UNBOUND\"}\n",(long)getpid(),fd,argv[9]);fflush(stdout);
 struct pollfd input={STDIN_FILENO,POLLIN,0};int ready;
 for(;;){now=monotonic_ns();if(!now||now>=v[7])return refuse("ORIGINAL_CLOCK_EXPIRED");uint64_t millis=(v[7]-now+999999)/1000000;ready=poll(&input,1,(int)millis);if(ready<0&&errno==EINTR)continue;break;}
 if(ready<=0||!(input.revents&POLLIN))return refuse("NO_OWNED_RELEASE");
 unsigned char release;if(read(STDIN_FILENO,&release,1)!=1||release!='@')return refuse("EXACT_SINGLE_RELEASE_REQUIRED");
 /* The owner closes this pipe after its one-byte release. Extra or delayed
  * input cannot be treated as the exact release; use the original clock. */
 for(;;){
  now=monotonic_ns();if(!now||now>=v[7])return refuse("ORIGINAL_CLOCK_EXPIRED");
  uint64_t millis=(v[7]-now+999999)/1000000;ready=poll(&input,1,(int)millis);
  if(ready<0&&errno==EINTR)continue;
  if(ready<=0||!(input.revents&(POLLIN|POLLHUP)))return refuse("RELEASE_PIPE_NOT_CLOSED");
  ssize_t extra=read(STDIN_FILENO,&release,1);
  if(extra<0&&errno==EINTR)continue;
  if(extra!=0)return refuse("EXTRA_RELEASE_INPUT");
  break;
 }
 now=monotonic_ns();if(!now||now>=v[7])return refuse("ORIGINAL_CLOCK_EXPIRED");
 if(!exact_fd(fd,v,argv[9]))return refuse("FD_OR_BYTES_DRIFT_BEFORE_EXEC");
 now=monotonic_ns();if(!now||now>=v[7])return refuse("ORIGINAL_CLOCK_EXPIRED");
 char *target_argv[]={"frw-inert-held-elf",NULL};char *target_env[]={NULL};
 syscall(SYS_execveat,fd,"",target_argv,target_env,AT_EMPTY_PATH);
 return refuse("EXECVEAT_FAILED");
}
