/* Experimental b11527 arm64/libc++ ABI shim, single HTP0 and immutable weights.
 * A fixed RPCMEM staging pool avoids touching a new DSP DMA mapping for every
 * model allocation. Every substitution is restored after flush_sync completes.
 * Never install this globally; the launcher must pin the original binary hash. */
typedef unsigned long size_t;
typedef unsigned long u64;
extern void *dlopen(const char*,int);
extern void *dlsym(void*,const char*);
extern void *memcpy(void*,const void*,size_t);
extern int dprintf(int,const char*,...);
extern void abort(void);
struct vec { void **begin, **end, **cap; };
struct mem { void *base; int fd; size_t size; };
struct shared { void *sess; struct mem *mem; void *control; struct vec extras; unsigned char mapped,pinned,extended; };
struct buffer { void *iface[11],*type; struct shared *context; size_t size; int usage; };
struct tensor { int type; struct buffer *buffer; long ne[4]; size_t nb[4]; int op; int op_params[16]; int flags; struct tensor *src[10]; struct tensor *view_src; size_t view_offs; void *data; };
struct node { void *tensor; int opcode; int params[32]; struct vec fused,dummy,inputs,outputs; };
_Static_assert(__builtin_offsetof(struct node,inputs)==192,"node ABI");
_Static_assert(__builtin_offsetof(struct shared,mapped)==48,"shared ABI");
/* ggml_tensor::data offset is checked against the pinned upstream header. */
static void *sym(const char*n){static void*h;if(!h)h=dlopen("libggml-hexagon.so",2);void*p=h?dlsym(h,n):0;if(!p){dprintf(2,"STAGING missing %s\n",n);abort();}return p;}
static u64 generation;
static int alloc_heap;static unsigned alloc_flags;
void *rpcmem_alloc2(int heap,unsigned flags,size_t size){static void*(*f)(int,unsigned,size_t);if(!f)f=sym("rpcmem_alloc2");alloc_heap=heap;alloc_flags=flags;generation++;return f(heap,flags,size);}
struct slot { struct mem mem; void *source; int source_fd; u64 gen,age; unsigned char mapped; };
static struct slot pool[5];
static u64 clock_tick,copies,copy_bytes,operations;
static void *one_session;
struct binding {struct shared *b;struct mem *original;unsigned char mapped;int slot;};
struct tensor_binding {struct tensor*t;void *data;};
void enqueue(void*s,const struct node*n) __asm__("_ZN20ggml_hexagon_session10enqueue_opERK10htp_opnode");
void enqueue(void*s,const struct node*n){
 static void(*original)(void*,const struct node*);static void(*flush)(void*,_Bool);
 static void*(*alloc)(int,unsigned,size_t);static int(*to_fd)(void*);
 if(!original){original=sym("_ZN20ggml_hexagon_session10enqueue_opERK10htp_opnode");flush=sym("_ZN20ggml_hexagon_session10flush_syncEb");alloc=sym("rpcmem_alloc2");to_fd=sym("rpcmem_to_fd");one_session=s;dprintf(2,"STAGING enabled: four 128MiB slots plus one large slot; sync before restore\n");}
 if(s!=one_session)abort();
 struct binding bindings[5];int nb=0;struct tensor_binding tensors[64];int nt=0;unsigned used=0;
 struct vec lists[2]={n->inputs,n->outputs};
 for(int l=0;l<2;l++){
  if(lists[l].end-lists[l].begin>64)abort();
  for(void**p=lists[l].begin;p<lists[l].end;p++){
   struct tensor*t=*p;if(!t||!t->buffer||t->buffer->usage!=1)continue;
   int duplicate=0;for(int i=0;i<nt;i++)if(tensors[i].t==t)duplicate=1;if(duplicate)continue;
   struct shared*b=t->buffer->context;if(!b||b->sess!=s||b->pinned||b->extended||!b->mem||nt==64)abort();
   int bi=-1;for(int i=0;i<nb;i++)if(bindings[i].b==b)bi=i;
   if(bi<0){
    if(nb==5||b->mapped)abort();struct mem *m=b->mem;int pi=-1;
    int begin=m->size>134217728?4:0,end=m->size>134217728?5:4;
    for(int i=begin;i<end;i++)if(!(used&(1u<<i))&&pool[i].source==m->base&&pool[i].source_fd==m->fd&&pool[i].gen==generation){pi=i;break;}
    if(pi<0)for(int i=begin;i<end;i++)if(!(used&(1u<<i))&&(pi<0||pool[i].age<pool[pi].age))pi=i;
    if(pi<0)abort();struct slot*slot=&pool[pi];
    if(!slot->mem.base){slot->mem.size=pi==4?((m->size+67108863)/67108864)*67108864:134217728;slot->mem.base=alloc(alloc_heap,alloc_flags,slot->mem.size);slot->mem.fd=to_fd(slot->mem.base);if(!slot->mem.base||slot->mem.fd<0)abort();}
    if(m->size>slot->mem.size)abort();
    if(slot->source!=m->base||slot->source_fd!=m->fd||slot->gen!=generation){memcpy(slot->mem.base,m->base,m->size);slot->source=m->base;slot->source_fd=m->fd;slot->gen=generation;copies++;copy_bytes+=m->size;}
    slot->age=++clock_tick;used|=1u<<pi;bi=nb++;bindings[bi]=(struct binding){b,m,b->mapped,pi};b->mem=&slot->mem;b->mapped=slot->mapped;
   }
   struct binding*binding=&bindings[bi];size_t off=(size_t)t->data-(size_t)binding->original->base;
   if(off>=binding->original->size) {dprintf(2,"STAGING tensor ABI/range mismatch off=%lu size=%lu\n",off,binding->original->size);abort();}
   tensors[nt++]=(struct tensor_binding){t,t->data};t->data=(char*)pool[binding->slot].mem.base+off;
  }
 }
 original(s,n);flush(s,1);
 for(int i=0;i<nt;i++)tensors[i].t->data=tensors[i].data;
 for(int i=0;i<nb;i++){struct binding*b=&bindings[i];pool[b->slot].mapped=b->b->mapped;b->b->mem=b->original;b->b->mapped=b->mapped;}
 operations++;if(operations%1000==0)dprintf(2,"STAGING ops=%lu copies=%lu copy_MiB=%lu\n",operations,copies,copy_bytes/1048576);
}
