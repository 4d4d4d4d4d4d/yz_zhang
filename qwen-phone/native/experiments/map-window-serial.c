/* Diagnostic shim for the exact b11527 Android arm64 libc++ ABI only.
 * Never load this into another runtime or a multi-session configuration. */
typedef unsigned long size_t;
typedef unsigned long u64;
extern void *dlopen(const char*,int);
extern void *dlsym(void*,const char*);
extern int dprintf(int,const char*,...);
extern void abort(void);
struct vec { void **begin, **end, **cap; };
struct session { char name[24]; u64 handle; };
struct mem { void *base; int fd; size_t size; };
struct shared { struct session *sess; struct mem *mem; void *control; struct vec extras; unsigned char mapped,pinned,extended; };
struct buffer { void *iface[11],*type; struct shared *context; size_t size; int usage; };
struct tensor { int type; struct buffer *buffer; };
struct node { void *tensor; int opcode; int params[32]; struct vec fused,dummy,inputs,outputs; };
_Static_assert(__builtin_offsetof(struct node,inputs)==192,"node ABI");
_Static_assert(__builtin_offsetof(struct shared,mapped)==48,"buffer ABI");
static void *sym(const char*n){static void*h;if(!h)h=dlopen("libggml-hexagon.so",2);void*p=h?dlsym(h,n):0;if(!p){dprintf(2,"WINDOW missing %s\n",n);abort();}return p;}
static size_t live;
int fastrpc_mmap(int domain,int fd,void *addr,int offset,size_t length,int flags){
 static int(*f)(int,int,void*,int,size_t,int);if(!f)f=sym("fastrpc_mmap");int r=f(domain,fd,addr,offset,length,flags);if(!r)live+=length;else dprintf(2,"WINDOW MAPFAIL active=%lu requested=%lu fd=%d flags=%d\n",live,length,fd,flags);return r;
}
void enqueue(void*s,const struct node*n) __asm__("_ZN20ggml_hexagon_session10enqueue_opERK10htp_opnode");
void enqueue(void*s,const struct node*n){
    static void(*original)(void*,const struct node*);
    static void(*flush)(void*,_Bool);
    static int(*dsp_unmap)(u64,unsigned);
    static int(*host_unmap)(int,int,void*,size_t);
    static unsigned count;
    if(!original){original=sym("_ZN20ggml_hexagon_session10enqueue_opERK10htp_opnode");flush=sym("_ZN20ggml_hexagon_session10flush_syncEb");dsp_unmap=sym("htp_iface_munmap");host_unmap=sym("fastrpc_munmap");dprintf(2,"WINDOW serial synchronized weight eviction enabled\n");}
    static unsigned nodes; nodes++;
    if(nodes<4)for(void**p=n->inputs.begin;p<n->inputs.end;p++){struct tensor*t=*p;if(t&&t->buffer)dprintf(2,"WINDOW input usage=%d mapped=%d size=%lu\n",t->buffer->usage,t->buffer->context->mapped,t->buffer->context->mem->size);}
    original(s,n);
    flush(s,1);
    struct vec lists[2]={n->inputs,n->outputs};
    for(int l=0;l<2;l++){
        if(lists[l].end-lists[l].begin>256)abort();
        for(void**p=lists[l].begin;p<lists[l].end;p++){
            struct tensor*t=*p;if(!t||!t->buffer||t->buffer->usage!=1)continue;
            struct shared*b=t->buffer->context;
            if(!b||b->sess!=s||!b->mem||b->pinned||b->extended)abort();
            if(!b->mapped)continue;
            if(dsp_unmap(b->sess->handle,(unsigned)b->mem->fd)||host_unmap(3,b->mem->fd,b->mem->base,b->mem->size)){dprintf(2,"WINDOW unmap failed\n");abort();}
            live-=b->mem->size;b->mapped=0;count++;if(count<4)dprintf(2,"WINDOW evicted fd=%d size=%lu\n",b->mem->fd,b->mem->size);
        }
    }
    if(count && count%500==0)dprintf(2,"WINDOW evictions=%u\n",count);
}
