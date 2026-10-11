#include <unistd.h>
int main(void){const char message[]="FRW_INERT_HELD_ELF_BODY\n";return write(1,message,sizeof(message)-1)==sizeof(message)-1?42:43;}
