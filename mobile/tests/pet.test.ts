import { COUNT, frameDuration, gaze, IDLE_SEQ, nextFrame, ROW, STATE_ROW } from "../src/pet";

describe("Malbolgato v2 frames follow Companion's sprite window", () => {
  it("idle walks the blink sequence (skipping the second closed-eye cell) and never ends", () => {
    let f = 0;
    const seen: number[] = [];
    for (let i = 0; i < 12; i++) { seen.push(f); const n = nextFrame(ROW.idle, f); expect(n.ended).toBe(false); f = n.frame; }
    expect(seen.slice(0, 6)).toEqual([...IDLE_SEQ]);
    expect(seen).not.toContain(4);
    expect(frameDuration(ROW.idle, 3)).toBe(1300);
  });

  it("other rows run through their real frame count and report the end", () => {
    for (const row of [ROW.wave, ROW.jump, ROW.fail, ROW.work, ROW.review, ROW.runL]) {
      let f = 0, steps = 0, n;
      do { n = nextFrame(row, f); f = n.frame; steps++; } while (!n.ended);
      expect(steps).toBe(COUNT[row]);
    }
    expect(frameDuration(ROW.wave, 0)).toBe(110);
  });

  it("app states map to the same rows Companion uses", () => {
    expect(STATE_ROW).toEqual({ idle: 0, thinking: 8, working: 7, waiting: 6, success: 3, error: 5 });
  });

  it("the gaze turns toward the touch, more the farther it is", () => {
    expect(gaze(120, 200)).toEqual({ row: ROW.lookR, frame: 4 });
    expect(gaze(-500, 200)).toEqual({ row: ROW.lookL, frame: 7 });
    expect(gaze(1, 200).frame).toBe(1);
  });
});
