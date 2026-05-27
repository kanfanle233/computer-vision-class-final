export function createVideoSync(video, getFps, onFrame) {
  let frame = 0;
  let rafId = 0;

  function tick() {
    const fps = Math.max(getFps(), 1);
    const nextFrame = Math.max(0, Math.floor(video.currentTime * fps));
    if (nextFrame !== frame) {
      frame = nextFrame;
      onFrame(frame);
    }
    rafId = requestAnimationFrame(tick);
  }

  function start() {
    if (!rafId) {
      rafId = requestAnimationFrame(tick);
    }
  }

  function stop() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  }

  function seekFrame(nextFrame) {
    const fps = Math.max(getFps(), 1);
    frame = Math.max(0, Math.floor(nextFrame));
    video.currentTime = frame / fps;
    onFrame(frame);
  }

  video.addEventListener("play", start);
  video.addEventListener("pause", stop);
  video.addEventListener("seeked", () => {
    const fps = Math.max(getFps(), 1);
    frame = Math.max(0, Math.floor(video.currentTime * fps));
    onFrame(frame);
  });
  video.addEventListener("loadedmetadata", () => seekFrame(0));

  return { start, stop, seekFrame };
}
