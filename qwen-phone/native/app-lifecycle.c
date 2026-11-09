/* APK model child: fail closed if the launching application goes away.
 * The Java launching thread must stay alive for the child's lifetime.
 */
extern int prctl(int, ...);
extern int getppid(void);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern int close(int);
extern long strtol(const char *, char **, int);
extern void _exit(int);
__attribute__((constructor)) static void bind_parent(void) {
    /* Android runs preload constructors before libc publishes getenv state. */
    char env[32768];
    int fd = open("/proc/self/environ", 0);
    if (fd < 0) _exit(125);
    long length = read(fd, env, sizeof(env)-1);close(fd);
    if (length <= 0 || length >= (long)sizeof(env)-1) _exit(125);
    env[length]=0;
    const char *value=0;const char prefix[]="QWEN_PARENT_PID=";
    for(long i=0;i<length;){int k=0;while(k<16 && i+k<length && env[i+k]==prefix[k])k++;
        if(k==16){value=env+i+16;break;}while(i<length && env[i])i++;i++;
    }
    if (!value) _exit(125);
    char *end = 0;
    long expected = strtol(value, &end, 10);
    if (!end || *end || expected <= 1 || expected > 2147483647L) _exit(125);
    if (prctl(1 /* PR_SET_PDEATHSIG */, 9 /* SIGKILL */, 0, 0, 0) != 0) _exit(125);
    /* Close the race where the parent exits before prctl. */
    if (getppid() != expected) _exit(125);
}
