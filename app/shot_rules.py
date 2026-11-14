"""Shot-writing rules appended to the Claude and Codex animation prompts.

They cover mistakes that passed contact-sheet review in real runs and that no metric detects.
"""

SHOT_RULES = """Shot-quality rules (learned from real runs; apply them to every shot you write):
- A figure that lies down (sleeping, resting, collapsed) is drawn rotated around its HIP, so its y is not its
  feet. With rot:Math.PI/2 and y at the mattress or floor, the body floats far above it. Build the figure options
  with y:0 and set fig.y=restOn(fig,surfaceY) (import restOn from '/engine/rig2d.js'), where surfaceY is the top of
  the bed, sofa or floor it touches. Draw the bed from the same surfaceY and put it under the body, not beside it.
- Every character stands or lies on something visible, and every prop is held (placed from jointWorld) or rests on a
  surface. Nothing floats, is cropped by the frame edge or hides behind the captions.
- A shot that is only text (title card, big line) still needs a visible character or object, strong contrast, text
  at least as large as the captions and some motion for its whole length. Never leave a dim, blurred, static frame.
- When you read the contact sheets, check each shot for: floating or sunken figures, missing contact with props,
  cropped or tiny objects, unreadable text. Fix them and re-check before the final render."""
