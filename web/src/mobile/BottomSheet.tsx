import { useEffect, useRef, useState, type ReactNode } from 'react';

export type Snap = 'peek' | 'half' | 'full';

const PEEK_PX = 172;

function heights(): Record<Snap, number> {
  const h = window.innerHeight;
  return { peek: PEEK_PX, half: Math.round(h * 0.5), full: Math.round(h * 0.88) };
}

/** A thumb-reachable sheet with three resting heights. Drag the grip, or tap it to step up and down. */
export function BottomSheet({
  snap,
  onSnap,
  header,
  children,
}: {
  snap: Snap;
  onSnap: (s: Snap) => void;
  header: ReactNode;
  children: ReactNode;
}) {
  const [dragH, setDragH] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const start = useRef<{ y: number; h: number; moved: boolean } | null>(null);
  const hs = heights();
  const height = dragH ?? hs[snap];

  useEffect(() => {
    const on = () => setTick((t) => t + 1);
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty('--sheet-h', `${hs[snap]}px`);
  }, [snap, hs]);

  return (
    <section className="m-sheet" style={{ height, transition: dragH == null ? 'height 0.22s ease' : 'none' }}>
      <div
        className="m-grip"
        role="button"
        tabIndex={0}
        aria-label={snap === 'peek' ? 'Expand details' : 'Collapse details'}
        onPointerDown={(e) => {
          start.current = { y: e.clientY, h: hs[snap], moved: false };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const s = start.current;
          if (!s) return;
          const dy = s.y - e.clientY;
          if (Math.abs(dy) > 6) s.moved = true;
          if (s.moved) setDragH(Math.max(120, Math.min(hs.full, s.h + dy)));
        }}
        onPointerUp={() => {
          const s = start.current;
          start.current = null;
          if (!s) return;
          if (!s.moved) {
            onSnap(snap === 'peek' ? 'half' : 'peek');
          } else if (dragH != null) {
            const order: Snap[] = ['peek', 'half', 'full'];
            onSnap(order.reduce((best, k) => (Math.abs(hs[k] - dragH) < Math.abs(hs[best] - dragH) ? k : best), 'peek' as Snap));
          }
          setDragH(null);
        }}
        onPointerCancel={() => {
          start.current = null;
          setDragH(null);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') onSnap(snap === 'peek' ? 'half' : 'peek');
        }}
      >
        <span />
      </div>
      <div className="m-sheet-head">{header}</div>
      <div className="m-sheet-body">{children}</div>
    </section>
  );
}
