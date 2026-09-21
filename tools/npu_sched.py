"""Dependency analysis and event allocation.

The hardware gives ordering for free only inside one (pipe, queue). Every
other dependency has to be expressed with counting semaphores, and a
descriptor can set exactly ONE event. So a producer feeding N consumers
costs N-1 trailing no-ops on the producer's own pipe and queue, where
hardware ordering guarantees they retire after it.

Three things this has to get right, all of which are real limits of the
machine rather than choices:

  * event counters saturate at 2^EVT_W - 1. More than that many pending
    sets are swallowed and the matching waits hang forever, so the fan-out
    of one event is capped and a wide fan-out is split across events.
  * an event may not be recycled while an earlier producer's consumers
    could still be waiting on it. Naive live-range colouring is NOT enough:
    a counting semaphore is anonymous, so a much later consumer of the same
    event that happens to be sitting in the issue window will happily
    consume the earlier producer's set and the real consumer hangs. That is
    a genuine deadlock, and it is what the hardware's err_hang reports.
    The sound rule used here is that an event is never reused within a
    region; regions are separated by global barriers, which fence every
    younger op until the machine has drained. Running out of events inserts
    a barrier and re-runs the analysis.
  * the result is verified: for every true dependency there must be a
    happens-before path. verify() fails loudly rather than producing a
    program that passes by luck of the issue order.
"""
from npu_isa import NEVT, NPIPE, nop


class _NeedBarrier(Exception):
    """Raised during allocation when a region needs more than NEVT events."""

    def __init__(self, at):
        super().__init__("region needs a barrier before op %d" % at)
        self.at = at

EVT_MAX = 7                      # 2^EVT_W - 1, matches npu_pkg::EVT_W = 3


class Op:
    __slots__ = ("idx", "pipe", "qid", "mcu", "build", "reads", "writes",
                 "name", "evt", "waits", "bar_g", "fanout")

    def __init__(self, pipe, build, reads, writes, qid, mcu, name):
        self.pipe, self.build = pipe, build
        self.reads, self.writes = frozenset(reads), frozenset(writes)
        self.qid, self.mcu, self.name = qid, mcu, name
        self.idx = -1
        self.evt = None
        self.waits = set()
        self.bar_g = False
        self.fanout = 0


class Builder:
    """Collects ops, works out what must happen before what, and emits a
    descriptor stream with the events wired up."""

    def __init__(self, n_queues=1, verbose=False):
        self.ops = []
        self.n_queues = n_queues
        self.verbose = verbose
        self.stats = {}

    def add(self, pipe, build, reads=(), writes=(), qid=0, mcu=0, name=""):
        o = Op(pipe, build, reads, writes, qid, mcu, name)
        o.idx = len(self.ops)
        self.ops.append(o)
        return o

    def barrier(self, pipe=0, qid=0, mcu=0, name="barrier"):
        """A global barrier op: it issues only when it is the oldest op in
        the window and nothing at all is in flight."""
        o = self.add(pipe, lambda **kw: nop(pipe, **kw), (), (), qid, mcu, name)
        o.bar_g = True
        return o

    # ---------------- dependency analysis ----------------
    def _deps(self):
        """deps[i] = the set of ops that must happen before op i, with
        anything the hardware already orders removed."""
        n = len(self.ops)
        raw = [set() for _ in range(n)]
        for i, oi in enumerate(self.ops):
            for j in range(i):
                oj = self.ops[j]
                conflict = (oj.writes & oi.reads) or (oj.writes & oi.writes) \
                           or (oj.reads & oi.writes)
                if conflict:
                    raw[i].add(j)
            # a global barrier depends on everything before it, and
            # everything after it depends on the barrier
            if oi.bar_g:
                raw[i] |= set(range(i))
        for i, oi in enumerate(self.ops):
            for j in range(i):
                if self.ops[j].bar_g:
                    raw[i].add(j)

        # hardware already orders same (pipe, queue) -- but only a
        # dependency on the IMMEDIATE predecessor there, since the queue is
        # a FIFO. Keep it as an implicit edge for verification.
        implicit = [set() for _ in range(n)]
        for i, oi in enumerate(self.ops):
            for j in range(i - 1, -1, -1):
                oj = self.ops[j]
                if oj.pipe == oi.pipe and oj.qid == oi.qid:
                    implicit[i].add(j)
                    break

        # transitive reduction over (explicit | implicit)
        full = [raw[i] | implicit[i] for i in range(n)]
        reach = [set() for _ in range(n)]
        for i in range(n):
            r = set()
            for j in full[i]:
                r |= reach[j] | {j}
            reach[i] = r

        need = []
        for i in range(n):
            keep = set()
            for j in raw[i]:
                # already guaranteed transitively, or by the queue FIFO?
                covered = any(j in reach[k] or j == k
                              for k in (full[i] - {j}))
                if not covered:
                    keep.add(j)
            need.append(keep)
        return need, reach

    # ---------------- event allocation ----------------
    def build(self, max_passes=64):
        """Allocate events, inserting global barriers where a region needs
        more than the machine has."""
        for _ in range(max_passes):
            try:
                return self._build_once()
            except _NeedBarrier as nb:
                at = nb.at
                o = Op(self.ops[at].pipe,
                       (lambda pp: (lambda **kw: nop(pp, **kw)))(
                           self.ops[at].pipe),
                       (), (), self.ops[at].qid, self.ops[at].mcu,
                       "auto barrier")
                o.bar_g = True
                self.ops.insert(at, o)
                for k, op in enumerate(self.ops):
                    op.idx = k
        raise RuntimeError("event allocation did not converge")

    def _build_once(self):
        need, reach = self._deps()
        n = len(self.ops)

        # producers and their consumer lists
        cons = {}
        for i in range(n):
            for j in need[i]:
                cons.setdefault(j, []).append(i)

        # split a wide fan-out across several events: one counter cannot
        # hold more than EVT_MAX pending sets
        slots = []                       # (producer, [consumers], live_end)
        for j, cs in sorted(cons.items()):
            for k in range(0, len(cs), EVT_MAX):
                chunk = cs[k:k + EVT_MAX]
                slots.append([j, chunk, max(chunk)])

        # An event may be handed to a new producer only once a global barrier
        # separates it from the previous holder's last consumer. Without that
        # separation the new producer's set can be stolen by a stale waiter
        # that is still sitting in the issue window -- the counter carries no
        # identity, so "which set is this" is not a question the hardware can
        # answer. Running out of reusable events inserts a barrier.
        slots.sort(key=lambda s: s[0])
        bars = sorted(i for i, o in enumerate(self.ops) if o.bar_g)
        colour = {}
        free_until = [None] * NEVT           # last consumer index of the holder
        for si, (j, cs, end) in enumerate(slots):
            got = None
            for e in range(NEVT):
                if free_until[e] is None:
                    got = e
                    break
                if free_until[e] < j and any(free_until[e] < bb <= j
                                             for bb in bars):
                    got = e
                    break
            if got is None:
                raise _NeedBarrier(j)
            free_until[got] = end
            colour[si] = got

        # attach events
        for si, (j, cs, _end) in enumerate(slots):
            e = colour[si]
            self.ops[j].evt = e if self.ops[j].evt is None else self.ops[j].evt
            self.ops[j].fanout = max(self.ops[j].fanout, 0)
            for c in cs:
                self.ops[c].waits.add(e)

        # a producer owning several slots needs a set per slot
        per_op = {}
        for si, (j, cs, _e) in enumerate(slots):
            per_op.setdefault(j, []).append((colour[si], len(cs)))

        # ---------------- emit ----------------
        out = []
        for i, o in enumerate(self.ops):
            wm = 0
            for e in sorted(o.waits):
                wm |= 1 << e
            sets = per_op.get(i, [])
            first_evt, first_cnt = (sets[0] if sets else (0, 0))
            kw = dict(wait_mask=wm, tag=i & 0xFF, bar_g=1 if o.bar_g else 0)
            if sets:
                kw.update(set_en=1, set_evt=first_evt)
            out.append((o.qid, o.mcu, o.build(**kw)))

            # trailing no-ops: one descriptor sets one event once, so the
            # remaining sets are separate ops on the same pipe and queue
            extra = [(first_evt, first_cnt - 1)] + list(sets[1:])
            for e, cnt in extra:
                for _ in range(max(0, cnt)):
                    out.append((o.qid, o.mcu,
                                nop(o.pipe, set_en=1, set_evt=e, tag=i & 0xFF)))

        self.stats = {
            "ops": n,
            "emitted": len(out),
            "nops": len(out) - n,
            "events": len(set(colour.values())) if colour else 0,
        }
        self._verify(need, out)
        return out

    # ---------------- static happens-before verification ----------------
    def _verify(self, need, out):
        """Every true dependency must be enforced either by the (pipe,queue)
        FIFO or by an event edge. Anything else is a program that only works
        if the scheduler happens to pick a lucky order."""
        n = len(self.ops)
        for i in range(n):
            oi = self.ops[i]
            for j in need[i]:
                oj = self.ops[j]
                same_fifo = (oi.pipe == oj.pipe and oi.qid == oj.qid)
                by_event = (oj.evt is not None and oj.evt in oi.waits)
                by_barrier = oi.bar_g or oj.bar_g
                if not (same_fifo or by_event or by_barrier):
                    raise AssertionError(
                        "unenforced dependency: op %d '%s' must follow "
                        "op %d '%s'" % (i, oi.name, j, oj.name))
        if self.verbose:
            print("  happens-before verified: %(ops)d ops -> %(emitted)d "
                  "descriptors (%(nops)d sync no-ops, %(events)d events)"
                  % self.stats)


def beats(base, count, stride=1):
    """The set of on-chip beats an operand window touches."""
    return {base + i * stride for i in range(count)}
