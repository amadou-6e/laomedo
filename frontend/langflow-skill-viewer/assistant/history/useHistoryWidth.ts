import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

export default function useHistoryWidth(visible: boolean) {
  const panel = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(256);
  const [maximum, setMaximum] = useState(480);
  const drag = useRef({ start: 0, width: 256, moved: false });
  useEffect(() => {
    const parent = panel.current?.parentElement;
    if (!parent) return;
    const update = () => {
      const limit = Math.max(
        180,
        Math.min(480, parent.clientWidth * 0.75, parent.clientWidth - 280),
      );
      setMaximum(limit);
      setWidth((current) => Math.min(limit, Math.max(180, current)));
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const observer = new ResizeObserver(update);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const resize = (next: number) =>
    setWidth(Math.min(maximum, Math.max(180, next)));
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!visible || event.button !== 0) return;
    drag.current = { start: event.clientX, width, moved: false };
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget
      .querySelector("button")
      ?.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (
      !event.currentTarget
        .querySelector("button")
        ?.hasPointerCapture(event.pointerId)
    )
      return;
    if (Math.abs(event.clientX - drag.current.start) > 3)
      drag.current.moved = true;
    resize(drag.current.width + event.clientX - drag.current.start);
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const button = event.currentTarget.querySelector("button");
    if (button?.hasPointerCapture(event.pointerId))
      button.releasePointerCapture(event.pointerId);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (
      !visible ||
      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
    )
      return;
    event.preventDefault();
    resize(
      event.key === "Home"
        ? 180
        : event.key === "End"
          ? maximum
          : width + (event.key === "ArrowRight" ? 24 : -24),
    );
  };
  return {
    panel,
    width,
    maximum,
    drag,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onKeyDown,
  };
}
