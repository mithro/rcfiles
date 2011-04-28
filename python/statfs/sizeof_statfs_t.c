
#include <stdio.h>
#include <sys/vfs.h>

int main() {
  printf("%ld\n", sizeof(struct statfs));
  return sizeof(struct statfs);
}
