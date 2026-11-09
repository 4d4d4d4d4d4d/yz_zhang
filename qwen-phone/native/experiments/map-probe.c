typedef unsigned long size_t;
extern void *dlopen(const char*,int);
extern void *dlsym(void*,const char*);
extern int dprintf(int,const char*,...);
extern void abort(void);
static void *sym(const char*n){void*h=dlopen("libggml-hexagon.so",2);void*p=h?dlsym(h,n):0;if(!p){dprintf(2,"PROBE missing %s\n",n);abort();}return p;}
void *probe_tensor(void*s,const void*t) __asm__("_ZN20ggml_hexagon_session11mmap_tensorEPK11ggml_tensor");
void *probe_tensor(void*s,const void*t){static void*(*f)(void*,const void*);static int n;if(!f)f=sym("_ZN20ggml_hexagon_session11mmap_tensorEPK11ggml_tensor");if(n++<3)dprintf(2,"PROBE tensor entered\n");return f(s,t);}
