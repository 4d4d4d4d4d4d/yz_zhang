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
    could still be waiting on it, and a global barrier is the ONLY thing
    that establishes that. An earlier version of this file allowed reuse on
    a single queue at a distance of WIN ops, on the argument that in-order
    delivery makes the issue window a contiguous run of program order. That
    argument is wrong: the window holds the oldest un-issued op plus later
    fetched ops, and as the ops between them issue and leave, fetching
    continues -- so the program-order span the window covers has no bound.
    Two consumers of one event can sit in it arbitrarily far apart. The
    testbench caught it as eleven wrong beats at the end of an encoder
    layer, which is what an under-constrained schedule looks like.

    Naive live-range colouring is NOT enough either:
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
from npu_isa import NEVT, NPIPE, WIN, CREDIT, nop

# The issue-window depth this build's programs are allowed to assume. The
# single-queue event-recycling rule below is sound only while the hardware
# window is no deeper than this: a deeper one can hold two consumers of the
# same event at once again, which is the anonymous-semaphore hazard all over
# again. Programs record the assumption and the testbench checks it against
# the CONFIG register, so a mismatch is a named failure rather than a hang.
_win_assumed = WIN


def set_window(n):
    global _win_assumed
    _win_assumed = int(n)


def window():
    return _win_assumed


class _NeedBarrier(Exception):
    """Raised during allocation when a region needs more than NEVT events."""

    def __init__(self, at):
        super().__init__("region needs a barrier before op %d" % at)
        self.at = at

EVT_MAX = 7                      # 2^EVT_W - 1, matches npu_pkg::EVT_W = 3


class Op:
    __slots__ = ("idx", "pipe", "qid", "mcu", "build", "reads", "writes",
                 "name", "evts", "waits", "bar_g")

    def __init__(self, pipe, build, reads, writes, qid, mcu, name):
        self.pipe, self.build = pipe, build
        self.reads, self.writes = frozenset(reads), frozenset(writes)
        self.qid, self.mcu, self.name = qid, mcu, name
        self.idx = -1
        self.evts = set()
        self.waits = set()
        self.bar_g = False


class Builder:
    """Collects ops, works out what must happen before what, and emits a
    descriptor stream with the events wired up."""

    def __init__(self, n_queues=1, verbose=False, single_queue=False):
        self.ops = []
        self.n_queues = n_queues
        self.verbose = verbose
        self.single_queue = single_queue
        self.stats = {}

    def add(self, pipe, build, reads=(), writes=(), qid=0, mcu=0, name=""):
        if self.single_queue and qid != 0:
            raise ValueError("single_queue builder: every op must use queue 0")
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
        # Allocation may be attempted several times, once per inserted
        # barrier. Every attempt starts from a clean slate: leaving the
        # previous attempt's event assignments in place emits a mixture of
        # two schedules, which is a program whose dependencies are simply
        # wrong -- it showed up as a store reading a buffer nothing had
        # written yet.
        for o in self.ops:
            o.evts = set()
            o.waits = set()
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

        # An event may be handed to a new producer only once a global
        # barrier separates it from the previous holder's last consumer.
        #
        # Two weaker rules were tried and both are unsound, for the same
        # underlying reason -- the counter carries no identity, so a
        # consumer cannot tell whose set it is taking:
        #
        #   "at least WIN ops apart on a single queue" assumed the issue
        #   window spans a bounded stretch of program order. It does not:
        #   the window holds the oldest un-issued op plus later fetched
        #   ops, and as the ops between them retire, fetching continues.
        #
        #   "a happens-before path from every old consumer to the new
        #   producer" is circular. The only thing ordering a new consumer
        #   is its own wait on this event, so the path runs through the
        #   very edge being aliased; an outstanding old set satisfies the
        #   new consumer and starves the old one.
        #
        # A barrier is the one construct that breaks the circularity,
        # because passing it requires the machine to be drained. The cost
        # is real -- ten barriers on an encoder layer -- and the honest
        # answer for a longer program is more events, not a cleverer rule.
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
                if free_until[e] >= j:
                    continue
                if any(free_until[e] < bb <= j for bb in bars):
                    got = e
                    break
            if got is None:
                raise _NeedBarrier(j)
            free_until[got] = end
            colour[si] = got

        # attach events
        for si, (j, cs, _end) in enumerate(slots):
            e = colour[si]
            self.ops[j].evts.add(e)
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
                by_event = bool(oj.evts & oi.waits)
                by_barrier = oi.bar_g or oj.bar_g
                if not (same_fifo or by_event or by_barrier):
                    raise AssertionError(
                        "unenforced dependency: op %d '%s' must follow "
                        "op %d '%s'" % (i, oi.name, j, oj.name))
        if self.verbose:
            print("  happens-before verified: %(ops)d ops -> %(emitted)d "
                  "descriptors (%(nops)d sync no-ops, %(events)d events)"
                  % self.stats)


# On-chip and external beats share one dependency namespace, kept disjoint
# by this offset. Tracking only on-chip beats leaves every producer/consumer
# pair that communicates THROUGH external memory unordered -- a weight tile
# streamed back in right after being stored out is exactly that shape, and
# it reads zeros if the schedule is allowed to reorder them. That bug hid
# behind an accidental on-chip serialisation for a long time.
EXT_BASE = 1 << 20


def beats(base, count, stride=1):
    """The set of on-chip beats an operand window touches."""
    return {base + i * stride for i in range(count)}


def ext_beats(base, count, stride=1):
    """The set of external beats a DMA window touches."""
    return {EXT_BASE + base + i * stride for i in range(count)}
